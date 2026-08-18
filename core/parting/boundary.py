"""
core/parting/boundary.py — Region boundary extraction (specification section 8).

The parting line is the boundary BETWEEN mold regions, so this stage never
looks for "candidate edges" by orientation. It walks every topological edge of
the solid, asks which faces meet there and which mold region each of those
faces belongs to, and classifies the edge from that answer alone.

    CORE | CAVITY          -> parting candidate
    CORE | NEUTRAL         -> neutral transition, may join a loop
    anything | UNDERCUT    -> SHUTOFF, never a parting candidate
    same region either side-> interior, ignored

WHY UNDERCUT EDGES ARE EXCLUDED
-------------------------------
This is the fix for the single largest defect in the previous implementation.
A trapped face still has to be formed by some steel, so the classifier gives
it a mold half like any other face — and the old boundary pass, which only
compared halves, therefore emitted the entire outline of every undercut
pocket as parting-line candidates. Measured on Part 3: 48 of the 51 candidate
edges bordered an undercut face, so 94% of the candidate set was the outline
of two rib pockets rather than the mold split. The correct rim survived only
because it happened to outscore them; a larger pocket would have won.

Physically, the border of an undercut region is a SHUTOFF: the surface where
a slider or lifter meets the main halves. It is a real and useful curve, and
it is reported as such, but it is not the parting line and it must not be
allowed to compete for that role. A parting line cannot release an undercut
(specification section 11), so pretending its boundary is a parting line is
exactly the "hide undercuts by forcing a visually plausible line" failure the
specification forbids.

ROBUSTNESS
----------
Edges that are not cleanly manifold are classified rather than dropped
silently: seams and non-manifold edges get their own kind and are counted, so
validation can report "this part has N non-manifold edges" instead of the
boundary quietly coming up short. Edges shorter than the configured minimum
are rejected as numerical artifacts before they can inject a spurious branch
point into the loop graph.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.TopoDS import TopoDS

from core.accessibility import MoldRegion
from core.models import FaceData
from core.parting.models import (
    EDGE_DEGENERATE,
    EDGE_INTERIOR,
    EDGE_NEUTRAL_TRANSITION,
    EDGE_NON_MANIFOLD,
    EDGE_PARTING,
    EDGE_SHUTOFF,
    BoundaryEdge,
)
from core.tolerances import AnalysisConfig, resolve


def edge_length(edge: Any) -> float:
    """Accurate edge length via Gauss integration."""
    try:
        return GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(edge))
    except Exception:
        return 0.0


def _face_regions(faces: List[FaceData]) -> Dict[int, MoldRegion]:
    """{TopoDS_Face hash -> MoldRegion} for every parsed face.

    Reads `mold_region` when the accessibility-aware classifier has set it,
    and falls back to `mold_half` otherwise, so this module also works on a
    face list that only went through the legacy classification path.
    """
    out: Dict[int, MoldRegion] = {}
    for f in faces:
        if f.face_shape is None:
            continue
        if f.is_undercut:
            region = MoldRegion.UNDERCUT
        elif f.mold_region:
            try:
                region = MoldRegion(f.mold_region)
            except ValueError:
                region = MoldRegion.AMBIGUOUS
        elif f.mold_half:
            region = MoldRegion(f.mold_half)
        else:
            region = MoldRegion.AMBIGUOUS
        out[hash(f.face_shape)] = region
    return out


def _classify_pair(
    a: MoldRegion, b: MoldRegion, half_a: str, half_b: str
) -> str:
    """Edge kind implied by the two faces meeting there.

    HALVES decide whether the edge separates the mold, REGIONS decide whether
    it is a parting line or a shutoff. Both are needed:

      * An UNDERCUT face is formed by a side action, so its border is a
        shutoff no matter which half the classifier assigned it.
      * A NEUTRAL face -- one parallel to the pull -- has no region of its own
        but is still formed by one half. Judging such an edge on regions alone
        would call the boundary between a core-formed side wall and the core
        floor a "transition", and would miss that the same wall against a
        cavity-formed face is a genuine split. Ordinary two-plate parts are
        mostly neutral faces, so getting this wrong loses most of the line.
    """
    if MoldRegion.UNDERCUT in (a, b):
        return EDGE_SHUTOFF

    if not half_a or not half_b or half_a == half_b:
        return EDGE_INTERIOR

    # The halves differ, so the mold genuinely parts here. A boundary between
    # two confidently classified faces is a pure parting edge; one that leans
    # on a neutral or ambiguous face is flagged so the loop builder can prefer
    # the confident edges and reach for these only when a loop needs them.
    if a in (MoldRegion.CORE, MoldRegion.CAVITY) and b in (
        MoldRegion.CORE, MoldRegion.CAVITY
    ):
        return EDGE_PARTING
    return EDGE_NEUTRAL_TRANSITION


def extract_region_boundaries(
    shape: Any,
    faces: List[FaceData],
    config: Optional[AnalysisConfig] = None,
) -> List[BoundaryEdge]:
    """Classify every edge of the solid against the mold-region map.

    Returns ALL edges that carry information — parting candidates, neutral
    transitions, shutoffs and non-manifold oddities. Callers filter with
    `BoundaryEdge.is_candidate`; validation reads the rest.
    """
    cfg = resolve(config)

    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    regions = _face_regions(faces)
    face_ids = {
        hash(f.face_shape): f.face_id for f in faces if f.face_shape is not None
    }
    halves = {
        hash(f.face_shape): f.mold_half for f in faces if f.face_shape is not None
    }

    out: List[BoundaryEdge] = []
    for i in range(1, edge_face_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_face_map.FindKey(i))
        adj = edge_face_map.FindFromIndex(i)
        length = edge_length(edge)

        if length < cfg.min_edge_length:
            # A sliver left by a trim or a blend. Too short to carry a
            # parting line and long enough to create a false junction in the
            # loop graph, so it is recorded and excluded.
            out.append(BoundaryEdge(edge=edge, kind=EDGE_DEGENERATE, length=length))
            continue

        if adj.Extent() != 2:
            # Seam edges (one face twice), free edges on an open shell, and
            # genuine non-manifold junctions. None of them define a clean
            # two-sided boundary, so they are reported rather than guessed at.
            out.append(
                BoundaryEdge(edge=edge, kind=EDGE_NON_MANIFOLD, length=length)
            )
            continue

        f1 = TopoDS.Face_s(adj.First())
        f2 = TopoDS.Face_s(adj.Last())
        h1, h2 = hash(f1), hash(f2)

        r1 = regions.get(h1)
        r2 = regions.get(h2)
        if r1 is None or r2 is None:
            out.append(
                BoundaryEdge(edge=edge, kind=EDGE_NON_MANIFOLD, length=length)
            )
            continue

        out.append(
            BoundaryEdge(
                edge=edge,
                kind=_classify_pair(
                    r1, r2, halves.get(h1, ""), halves.get(h2, "")
                ),
                length=length,
                face_ids=(face_ids.get(h1, -1), face_ids.get(h2, -1)),
                regions=(r1, r2),
                halves=(halves.get(h1, ""), halves.get(h2, "")),
            )
        )

    return out


def candidate_edges(
    boundary: List[BoundaryEdge],
    include_neutral: bool = True,
) -> List[BoundaryEdge]:
    """The subset that may form a parting loop.

    `include_neutral=False` restricts the set to pure CORE|CAVITY edges,
    which is what the loop builder tries first: if the part yields a clean
    closed loop from those alone, pulling neutral transitions in as well
    could only add branches.
    """
    if include_neutral:
        return [e for e in boundary if e.is_candidate]
    return [e for e in boundary if e.kind == EDGE_PARTING]


def summarize(boundary: List[BoundaryEdge]) -> Dict[str, Any]:
    """Counts and total lengths per edge kind, for validation and debugging."""
    counts: Dict[str, int] = {}
    lengths: Dict[str, float] = {}
    for e in boundary:
        counts[e.kind] = counts.get(e.kind, 0) + 1
        lengths[e.kind] = lengths.get(e.kind, 0.0) + e.length
    return {
        "counts": counts,
        "lengths": {k: round(v, 3) for k, v in lengths.items()},
        "total_edges": len(boundary),
    }
