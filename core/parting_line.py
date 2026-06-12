"""
core/parting_line.py — Parting Line Extraction Algorithm (v3)

v3 Fixes (over v2):
1. Candidate loop ranking: Instead of returning ALL cope↔drag transition edges
   as "the parting line", this version scores and ranks every disconnected loop
   independently and selects the dominant mold-split boundary.
2. 6-metric weighted scoring per loop:
     - Projected enclosed area (40%)   — outermost rim has the largest 2D footprint
     - Outer boundary confidence (20%) — ratio of loop area to full part cross-section
     - Moldability contribution (15%)  — low-draft adjacent faces penalized
     - Loop simplicity (10%)           — fewer edges preferred
     - Core/cavity separation quality (10%) — balanced cope/drag adjacent area
     - Loop length penalty (5%)        — shorter perimeters preferred
3. Ambiguity detection: if top two loops score within 5%, returns both flagged.
4. Backward-compatible find_parting_line() wrapper preserved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.TopoDS import TopoDS

from core.models import FaceData


# ---------------------------------------------------------------------------
# Low-level math helpers
# ---------------------------------------------------------------------------

def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _sub(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


# ---------------------------------------------------------------------------
# OCP geometry helpers
# ---------------------------------------------------------------------------

def _edge_length(edge: Any) -> float:
    """Accurate edge length via Gauss integration (OCP)."""
    try:
        curve = BRepAdaptor_Curve(edge)
        return GCPnts_AbscissaPoint.Length_s(curve)
    except Exception:
        return 0.0


def _edge_vertex_coords(edge: Any) -> List[Tuple[float, float, float]]:
    """Extract both endpoint 3D coordinates from a TopoDS_Edge."""
    coords: List[Tuple[float, float, float]] = []
    exp = TopExp_Explorer(edge, TopAbs_VERTEX)
    while exp.More():
        v = TopoDS.Vertex_s(exp.Current())
        pnt = BRep_Tool.Pnt_s(v)
        coords.append((round(pnt.X(), 6), round(pnt.Y(), 6), round(pnt.Z(), 6)))
        exp.Next()
    return coords


def _edge_vertex_set(edge: Any) -> frozenset:
    """Frozenset of vertex coordinate tuples — used for loop connectivity."""
    return frozenset(_edge_vertex_coords(edge))


# ---------------------------------------------------------------------------
# Utility: compute two orthogonal axes perpendicular to pull_dir
# ---------------------------------------------------------------------------

def _perpendicular_axes(
    pull_dir: Tuple[float, float, float],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Return two mutually orthogonal unit vectors both perpendicular to pull_dir."""
    # Pick a seed vector not parallel to pull_dir
    seed = (1.0, 0.0, 0.0) if abs(pull_dir[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _norm(_cross(pull_dir, seed))
    v = _norm(_cross(pull_dir, u))
    return u, v


# ---------------------------------------------------------------------------
# Phase 1: Find all cope↔drag boundary edges for a given pull direction
# ---------------------------------------------------------------------------

def _build_face_side_map(
    faces: List[FaceData],
    pull_dir: Tuple[float, float, float],
) -> Dict[int, str]:
    """Build {hash(TopoDS_Face) -> 'cope' | 'drag'} lookup."""
    face_side: Dict[int, str] = {}
    for f in faces:
        if f.face_shape is not None:
            d = _dot(f.normal, pull_dir)
            face_side[hash(f.face_shape)] = "cope" if d >= 0 else "drag"
    return face_side


def _find_boundary_edges(
    shape: Any,
    faces: List[FaceData],
    pull_dir: Tuple[float, float, float],
) -> Tuple[List[Any], Dict[int, Tuple[str, str]]]:
    """
    Find all edges where a COPE face meets a DRAG face.

    Returns:
        boundary_edges: list of TopoDS_Edge
        edge_adj_sides: map of edge index -> (side_of_f1, side_of_f2) for metric use
    """
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    face_side = _build_face_side_map(faces, pull_dir)

    boundary_edges: List[Any] = []
    edge_adj_sides: Dict[int, Tuple[str, str]] = {}

    for i in range(1, edge_face_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_face_map.FindKey(i))
        adj = edge_face_map.FindFromIndex(i)

        if adj.Extent() != 2:
            continue

        f1 = TopoDS.Face_s(adj.First())
        f2 = TopoDS.Face_s(adj.Last())

        s1 = face_side.get(hash(f1))
        s2 = face_side.get(hash(f2))

        if s1 and s2 and s1 != s2:
            edge_idx = len(boundary_edges)
            boundary_edges.append(edge)
            edge_adj_sides[edge_idx] = (s1, s2)

    return boundary_edges, edge_adj_sides


# ---------------------------------------------------------------------------
# Phase 1b: Group edges into connected loops
# ---------------------------------------------------------------------------

def _group_into_loops(edges: List[Any]) -> List[List[int]]:
    """
    Group edge indices into connected components (loops) by shared vertices.
    Returns list of groups, each group is a list of edge indices.
    """
    if not edges:
        return []

    vert_map = [_edge_vertex_set(e) for e in edges]
    remaining = list(range(len(edges)))
    loops: List[List[int]] = []

    while remaining:
        loop = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            loop_verts: frozenset = frozenset()
            for idx in loop:
                loop_verts = loop_verts | vert_map[idx]
            still_remaining = []
            for idx in remaining:
                if loop_verts & vert_map[idx]:
                    loop.append(idx)
                    changed = True
                else:
                    still_remaining.append(idx)
            remaining = still_remaining
        loops.append(loop)

    return loops


# ---------------------------------------------------------------------------
# Phase 2: Per-loop metrics
# ---------------------------------------------------------------------------

def _projected_polygon_area(
    coords_3d: List[Tuple[float, float, float]],
    u_axis: Tuple[float, float, float],
    v_axis: Tuple[float, float, float],
) -> float:
    """
    Project 3D points onto the (u_axis, v_axis) plane and compute the
    enclosed polygon area using the Shoelace formula.
    Points are sorted by angle around their centroid before Shoelace.
    """
    if len(coords_3d) < 3:
        return 0.0

    pts_2d = [((_dot(p, u_axis)), (_dot(p, v_axis))) for p in coords_3d]

    cx = sum(p[0] for p in pts_2d) / len(pts_2d)
    cy = sum(p[1] for p in pts_2d) / len(pts_2d)

    # Angular sort around centroid
    pts_sorted = sorted(pts_2d, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))

    # Shoelace formula
    n = len(pts_sorted)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts_sorted[i][0] * pts_sorted[j][1]
        area -= pts_sorted[j][0] * pts_sorted[i][1]
    return abs(area) / 2.0


def _part_projected_area(
    shape: Any,
    pull_dir: Tuple[float, float, float],
    u_axis: Tuple[float, float, float],
    v_axis: Tuple[float, float, float],
) -> float:
    """
    Approximate the part's overall cross-sectional area projected onto the
    plane perpendicular to pull_dir.  Uses the global bounding box projected
    onto u/v axes as an upper-bound estimate.
    """
    try:
        bnd = Bnd_Box()
        BRepBndLib.Add_s(shape, bnd)
        xmin, ymin, zmin, xmax, ymax, zmax = bnd.Get()

        # All 8 corners of the bounding box
        corners = [
            (xmin, ymin, zmin), (xmax, ymin, zmin),
            (xmin, ymax, zmin), (xmax, ymax, zmin),
            (xmin, ymin, zmax), (xmax, ymin, zmax),
            (xmin, ymax, zmax), (xmax, ymax, zmax),
        ]

        return _projected_polygon_area(corners, u_axis, v_axis)
    except Exception:
        return 1.0  # Fallback: avoid division by zero


def _get_adjacent_faces_for_loop(
    loop_edge_indices: List[int],
    all_boundary_edges: List[Any],
    faces: List[FaceData],
    shape: Any,
) -> List[FaceData]:
    """
    For a set of edges, find all FaceData objects that are adjacent to any
    of those edges.  Uses the edge->face map for an O(E) pass.
    """
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    # Build reverse lookup: TopoDS_Face hash -> FaceData
    face_lookup: Dict[int, FaceData] = {}
    for f in faces:
        if f.face_shape is not None:
            face_lookup[hash(f.face_shape)] = f

    # Build set of edge hashes we care about
    loop_edge_hashes = {hash(all_boundary_edges[i]) for i in loop_edge_indices}

    adjacent: Dict[int, FaceData] = {}
    for i in range(1, edge_face_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_face_map.FindKey(i))
        if hash(edge) not in loop_edge_hashes:
            continue
        adj = edge_face_map.FindFromIndex(i)
        # TopTools_ListOfShape has no iterator; use First()/Last() (manifold edges have exactly 2)
        for getter in (adj.First, adj.Last):
            try:
                face_topo = TopoDS.Face_s(getter())
                h = hash(face_topo)
                if h in face_lookup and h not in adjacent:
                    adjacent[h] = face_lookup[h]
            except Exception:
                pass

    return list(adjacent.values())


def _score_loop(
    loop_edge_indices: List[int],
    all_boundary_edges: List[Any],
    faces: List[FaceData],
    shape: Any,
    pull_dir: Tuple[float, float, float],
    u_axis: Tuple[float, float, float],
    v_axis: Tuple[float, float, float],
    part_proj_area: float,
) -> Dict[str, float]:
    """
    Compute all 6 metrics for a single candidate loop.
    Returns raw (un-normalized) metric values.
    """
    loop_edges = [all_boundary_edges[i] for i in loop_edge_indices]

    # --- Collect all vertex coords for this loop ---
    all_coords: List[Tuple[float, float, float]] = []
    total_length = 0.0
    for e in loop_edges:
        all_coords.extend(_edge_vertex_coords(e))
        total_length += _edge_length(e)

    # 1. Projected enclosed area
    projected_area = _projected_polygon_area(all_coords, u_axis, v_axis)

    # 2. Outer boundary confidence
    outer_confidence = projected_area / part_proj_area if part_proj_area > 0 else 0.0
    outer_confidence = min(1.0, outer_confidence)  # clamp

    # 3. Moldability contribution — penalize low-draft adjacent faces
    # Use classification already set on FaceData by face_classifier.py
    adjacent_faces = _get_adjacent_faces_for_loop_fast(loop_edge_indices, all_boundary_edges, faces, shape)
    total_adj_area = sum(f.area for f in adjacent_faces) or 1.0
    warning_adj_area = sum(f.area for f in adjacent_faces if f.draft_angle < 0.5)
    moldability = 1.0 - (warning_adj_area / total_adj_area)

    # 4. Loop simplicity
    num_edges = len(loop_edges)
    simplicity = 1.0 / (1.0 + math.log2(max(num_edges, 1)))

    # 5. Core/cavity separation quality
    cope_adj = sum(f.area for f in adjacent_faces if f.classification == "cavity")
    drag_adj = sum(f.area for f in adjacent_faces if f.classification == "core")
    max_adj = max(cope_adj, drag_adj)
    separation_quality = (min(cope_adj, drag_adj) / max_adj) if max_adj > 0 else 0.0

    # 6. Loop length penalty (shorter = better)
    length_score = 1.0 / (1.0 + total_length * 0.001)

    return {
        "projected_area": projected_area,
        "outer_confidence": outer_confidence,
        "moldability": moldability,
        "simplicity": simplicity,
        "separation_quality": separation_quality,
        "length_score": length_score,
        "total_length": total_length,
        "num_edges": num_edges,
    }


def _get_adjacent_faces_for_loop_fast(
    loop_edge_indices: List[int],
    all_boundary_edges: List[Any],
    faces: List[FaceData],
    shape: Any,
) -> List[FaceData]:
    """
    Faster version: build the edge->face map once externally; here we rebuild
    per-call but use hash lookups throughout to stay O(E*F_adj).
    """
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    face_lookup: Dict[int, FaceData] = {
        hash(f.face_shape): f for f in faces if f.face_shape is not None
    }

    # Build a set of edge topology hashes for this loop
    loop_edge_set = {hash(all_boundary_edges[i]) for i in loop_edge_indices}

    adjacent: Dict[int, FaceData] = {}
    for i in range(1, edge_face_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_face_map.FindKey(i))
        if hash(edge) not in loop_edge_set:
            continue
        adj_list = edge_face_map.FindFromIndex(i)
        # TopTools_ListOfShape has no Python iterator; use First()/Last() for manifold edges
        for getter in (adj_list.First, adj_list.Last):
            try:
                face_topo = TopoDS.Face_s(getter())
                h = hash(face_topo)
                if h in face_lookup:
                    adjacent[h] = face_lookup[h]
            except Exception:
                pass

    return list(adjacent.values())


# ---------------------------------------------------------------------------
# Phase 3: Weighted scoring and normalization
# ---------------------------------------------------------------------------

WEIGHTS = {
    "projected_area": 0.40,
    "outer_confidence": 0.20,
    "moldability": 0.15,
    "simplicity": 0.10,
    "separation_quality": 0.10,
    "length_score": 0.05,
}


def _compute_weighted_score(metrics: Dict[str, float], norm_proj_area: float) -> float:
    """
    Compute the final weighted score [0, 1] for one loop.
    projected_area is normalized against the maximum across all loops.
    """
    norm_area = metrics["projected_area"] / norm_proj_area if norm_proj_area > 0 else 0.0
    norm_area = min(1.0, norm_area)

    return (
        WEIGHTS["projected_area"] * norm_area
        + WEIGHTS["outer_confidence"] * metrics["outer_confidence"]
        + WEIGHTS["moldability"] * metrics["moldability"]
        + WEIGHTS["simplicity"] * metrics["simplicity"]
        + WEIGHTS["separation_quality"] * metrics["separation_quality"]
        + WEIGHTS["length_score"] * metrics["length_score"]
    )


# ---------------------------------------------------------------------------
# Return types (dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class CandidateLoop:
    candidate_id: int                                        # 1-indexed, sorted by score
    edges: List[Any]                                         # List[TopoDS_Edge]
    score: float                                             # Weighted overall score [0, 1]
    projected_area: float                                    # 2D footprint (mm²)
    loop_length: float                                       # Total perimeter (mm)
    outer_boundary_confidence: float                         # [0, 1]
    moldability_contribution: float                          # [0, 1]
    simplicity: float                                        # [0, 1]
    separation_quality: float                                # [0, 1]
    num_edges: int
    is_selected: bool                                        # True = primary parting line
    vertex_coords: List[Tuple[float, float, float]] = field(default_factory=list)

    def __repr__(self) -> str:
        tag = " [PRIMARY]" if self.is_selected else ""
        return (
            f"Loop-{self.candidate_id:02d}{tag}  "
            f"score={self.score:.3f}  area={self.projected_area:.1f}  "
            f"edges={self.num_edges}  length={self.loop_length:.1f}"
        )


@dataclass
class PartingLineResult:
    primary_loop: CandidateLoop                              # The selected dominant loop
    all_candidates: List[CandidateLoop]                      # ALL loops, ranked best-first
    pull_direction: Tuple[float, float, float]
    is_ambiguous: bool                                       # True if top two loops tie
    total_candidate_count: int


# ---------------------------------------------------------------------------
# Phase 4: Primary loop selection + ambiguity detection
# ---------------------------------------------------------------------------

AMBIGUITY_THRESHOLD = 0.05   # within 5% → ambiguous
MIN_SCORE_THRESHOLD = 0.10   # if best loop is below this, still select it


def _select_primary(candidates: List[CandidateLoop]) -> Tuple[CandidateLoop, bool]:
    """
    Select the primary parting line from a ranked list of CandidateLoops.
    Returns (primary, is_ambiguous).
    """
    if not candidates:
        raise ValueError("No candidate loops to select from.")

    best = candidates[0]
    is_ambiguous = False

    if len(candidates) >= 2:
        second = candidates[1]
        score_gap = best.score - second.score
        # Relative gap: if within 5% of best score, call it ambiguous
        if best.score > 0 and (score_gap / best.score) < AMBIGUITY_THRESHOLD:
            is_ambiguous = True

    best.is_selected = True
    return best, is_ambiguous


# ---------------------------------------------------------------------------
# Public API — main entry point
# ---------------------------------------------------------------------------

def find_all_parting_lines(
    shape: Any,
    faces: List[FaceData],
    pull_dir: Tuple[float, float, float],
    debug: bool = False,
) -> PartingLineResult:
    """
    4-phase pipeline:
      1. Find all cope↔drag boundary edges.
      2. Group into connected loops.
      3. Score each loop on 6 metrics.
      4. Select the dominant mold-split boundary loop.

    Args:
        shape:    The TopoDS_Shape (full solid from STEP parser).
        faces:    List[FaceData] — must have classification and draft_angle set.
        pull_dir: The mold pull (opening) direction.
        debug:    If True, all candidates are fully populated. Otherwise only primary.

    Returns:
        PartingLineResult with primary_loop, all_candidates, and ambiguity flag.
    """
    pull_dir = _norm(pull_dir)
    u_axis, v_axis = _perpendicular_axes(pull_dir)
    part_proj_area = _part_projected_area(shape, pull_dir, u_axis, v_axis)

    # Phase 1: boundary edges + grouping
    boundary_edges, _ = _find_boundary_edges(shape, faces, pull_dir)
    if not boundary_edges:
        # Return an empty result rather than crashing
        empty_loop = CandidateLoop(
            candidate_id=1, edges=[], score=0.0, projected_area=0.0,
            loop_length=0.0, outer_boundary_confidence=0.0,
            moldability_contribution=0.0, simplicity=0.0,
            separation_quality=0.0, num_edges=0, is_selected=True,
        )
        return PartingLineResult(
            primary_loop=empty_loop,
            all_candidates=[empty_loop],
            pull_direction=pull_dir,
            is_ambiguous=False,
            total_candidate_count=0,
        )

    loop_groups = _group_into_loops(boundary_edges)  # List[List[int]]

    # Phase 2: Compute metrics for every loop
    raw_metrics: List[Dict[str, float]] = []
    for group in loop_groups:
        m = _score_loop(group, boundary_edges, faces, shape, pull_dir, u_axis, v_axis, part_proj_area)
        raw_metrics.append(m)

    # Phase 3: Normalize projected_area and compute weighted scores
    max_proj = max(m["projected_area"] for m in raw_metrics) or 1.0

    scored_loops: List[Tuple[float, List[int], Dict[str, float]]] = []
    for group, metrics in zip(loop_groups, raw_metrics):
        score = _compute_weighted_score(metrics, max_proj)
        scored_loops.append((score, group, metrics))

    # Sort descending by score
    scored_loops.sort(key=lambda t: t[0], reverse=True)

    # Build CandidateLoop objects
    candidate_list: List[CandidateLoop] = []
    for cid, (score, group, metrics) in enumerate(scored_loops, start=1):
        loop_edges = [boundary_edges[i] for i in group]
        # Collect vertex coords for frontend rendering
        verts: List[Tuple[float, float, float]] = []
        for e in loop_edges:
            verts.extend(_edge_vertex_coords(e))

        candidate_list.append(CandidateLoop(
            candidate_id=cid,
            edges=loop_edges,
            score=round(score, 4),
            projected_area=round(metrics["projected_area"], 2),
            loop_length=round(metrics["total_length"], 2),
            outer_boundary_confidence=round(metrics["outer_confidence"], 4),
            moldability_contribution=round(metrics["moldability"], 4),
            simplicity=round(metrics["simplicity"], 4),
            separation_quality=round(metrics["separation_quality"], 4),
            num_edges=int(metrics["num_edges"]),
            is_selected=False,
            vertex_coords=verts,
        ))

    # Phase 4: Select primary + detect ambiguity
    primary, is_ambiguous = _select_primary(candidate_list)

    return PartingLineResult(
        primary_loop=primary,
        all_candidates=candidate_list,
        pull_direction=pull_dir,
        is_ambiguous=is_ambiguous,
        total_candidate_count=len(candidate_list),
    )


# ---------------------------------------------------------------------------
# Backward-compatible wrapper (legacy API — used by gui/analyzer.py)
# ---------------------------------------------------------------------------

def find_parting_line(
    shape: Any,
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> List[Any]:
    """
    Legacy API — returns edges of the primary parting line only.
    All callers (gui/analyzer.py, tests) continue to work unchanged.
    """
    result = find_all_parting_lines(shape, faces, mold_direction)
    return result.primary_loop.edges


# ---------------------------------------------------------------------------
# Helper: expose PartingLineResult from analyzer result for the API layer
# ---------------------------------------------------------------------------

def compute_parting_line_result(
    shape: Any,
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> PartingLineResult:
    """
    Convenience wrapper for api.py that returns the full PartingLineResult.
    Use this in /analyze endpoint instead of find_parting_line() to get
    rich candidate data for the frontend.
    """
    return find_all_parting_lines(shape, faces, mold_direction)