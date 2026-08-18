"""
core/face_classifier.py — Assign every face to a mold half and classify it.

v2 (Phase 2 rewrite):
Mold-half assignment and draft status are ORTHOGONAL attributes:
  face.mold_half  — "core" | "cavity": which half FORMS the face. ALWAYS set,
                    even for undercut and low-draft faces (a vertical wall is
                    still molded by one of the halves — it just needs draft).
  face.low_draft  — True when the worst-case draft angle < 1°.
  face.classification — "undercut" | "core" | "cavity" (rendering label).

Half assignment uses per-sample normal voting (area-weighted): curved faces
vote proportionally to how much of their surface faces each half. Vertical
walls (all samples perpendicular) are assigned by REACHABILITY: if the wall
can be reached from the cavity side (ray along +pull escapes) it is formed
by the cavity steel; if only the core side reaches it, by the core. An
internal bore is blocked toward +pull by the part's own top — so it is
correctly formed by the core, matching the judges' cap example ("even the
internal surface … will be formed by the core").

An external vertical wall that BOTH halves can reach is genuinely ambiguous:
physics alone does not decide it, and either assignment yields a
manufacturable mold. Such walls are resolved last, per connected REGION, by
minimum parting-interface length (`_resolve_ambiguous_regions`) — the mold
principle that the core/cavity split should follow the shortest boundary
that separates the halves.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.TopoDS import TopoDS

from core.models import FaceData, AnalysisResult, DirectionCandidate, compute_score
from core.undercut_detector import UndercutRaycaster

logger = logging.getLogger(__name__)

from core.tolerances import CLASSIFICATION_EPSILON as _PERP_EPS

# Fallback when adjacency offers no discriminator (no decided neighbour, or an
# exact tie): keep the historical convention — the cavity wraps the part's
# cosmetic exterior and the parting line sits at the rim. This is the mentor's
# rule for a plain shell ("convex/outer surfaces → cavity") and it is what a
# symmetric wall (equal boundary either way) gets on both synthetic ground-truth
# models, whose outer walls tie exactly.
_EXTERNAL_TIE_DEFAULT = "cavity"


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def classify_faces(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    raycaster: Optional[UndercutRaycaster] = None,
    shape: Any = None,
) -> List[FaceData]:
    """
    Assign mold_half + classification to every face.
    Requires is_undercut (raycaster) and draft_angle/low_draft (draft step).

    `shape` (the parent TopoDS_Shape) enables region-level resolution of
    genuinely ambiguous external vertical walls; without it those walls fall
    back to `_EXTERNAL_TIE_DEFAULT`.
    """
    # Area-weighted part centroid — fallback tie-break for vertical walls
    total_area = sum(f.area for f in faces) or 1.0
    cx = sum(f.center[0] * f.area for f in faces) / total_area
    cy = sum(f.center[1] * f.area for f in faces) / total_area
    cz = sum(f.center[2] * f.area for f in faces) / total_area

    pull = mold_direction
    neg_pull = (-pull[0], -pull[1], -pull[2])

    deferred: List[FaceData] = []
    tie_evidence: Dict[int, Dict[str, Any]] = {}

    for face in faces:
        normals = face.sample_normals or [face.normal]
        w = face.area / len(normals) if normals else 0.0

        cavity_w = 0.0
        core_w = 0.0
        for nv in normals:
            d = _dot(nv, mold_direction)
            if d > _PERP_EPS:
                cavity_w += w
            elif d < -_PERP_EPS:
                core_w += w

        if cavity_w > core_w:
            face.mold_half = "cavity"
        elif core_w > cavity_w:
            face.mold_half = "core"
        else:
            evidence: Dict[str, Any] = {}
            half = _vertical_wall_half(
                face, pull, neg_pull, raycaster, (cx, cy, cz), evidence
            )
            if half is None:
                # Reachable from both halves and not internal: physics does
                # not decide. Resolve per region once every other face is set.
                face.mold_half = ""
                tie_evidence[face.face_id] = evidence
                deferred.append(face)
            else:
                face.mold_half = half

    if deferred:
        _resolve_ambiguous_regions(faces, deferred, shape, tie_evidence)

    for face in faces:
        face.classification = "undercut" if face.is_undercut else face.mold_half

    return faces


def _vertical_wall_half(
    face: FaceData,
    pull: Tuple[float, float, float],
    neg_pull: Tuple[float, float, float],
    raycaster: Optional[UndercutRaycaster],
    centroid: Tuple[float, float, float],
    evidence: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Mold half that PHYSICALLY forms a fully vertical wall.

    Reachability test: cast rays from the wall's sample points along the
    pull direction (toward the cavity half). If the part blocks that path
    (e.g. an internal bore under a closed top), the cavity steel can never
    touch this wall — the core forms it. And vice versa. Falls back to the
    centroid-side heuristic when no raycaster is available.

    Returns None when the wall is external and equally reachable from both
    halves — physics does not decide, so the caller resolves it per region.
    """
    if raycaster is not None:
        pts = face.sample_points or [face.center]
        nrms = face.sample_normals or [face.normal]
        n = min(len(pts), len(nrms))
        cav_blocked = 0
        core_blocked = 0
        internal = 0
        for p, nv in zip(pts[:n], nrms[:n]):
            if raycaster.is_blocked(p, nv, pull):
                cav_blocked += 1
            if raycaster.is_blocked(p, nv, neg_pull):
                core_blocked += 1
            # Internal-channel probe: a wall whose outward normal points
            # at more part material across a void (e.g. a bore wall facing
            # the opposite bore wall) belongs to an internal feature.
            if raycaster.is_blocked(p, nv, nv):
                internal += 1
        if evidence is not None:
            evidence.update(
                samples=n,
                cav_blocked=cav_blocked,
                core_blocked=core_blocked,
                internal=internal,
            )
        if cav_blocked != core_blocked:
            # Blocked toward the cavity → only the core can form it.
            return "core" if cav_blocked > core_blocked else "cavity"
        if internal > n / 2:
            # Through-holes / internal channels: formed by a core pin
            # (judges' cap example: internal surfaces → core).
            return "core"
        # External wall, equally reachable from both halves. Either steel
        # could form it, so defer to the region pass.
        return None

    # No raycaster: which side of the centroid it sits on
    rel = (face.center[0] - centroid[0],
           face.center[1] - centroid[1],
           face.center[2] - centroid[2])
    return "cavity" if _dot(rel, pull) >= 0 else "core"


def _edge_length(edge: Any) -> float:
    """Accurate edge length via Gauss integration (OCP)."""
    try:
        return GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(edge))
    except Exception:
        return 0.0


def _shared_edge_lengths(
    shape: Any, faces: List[FaceData]
) -> Dict[int, Dict[int, float]]:
    """{face_id: {neighbour_face_id: total shared edge length}}.

    Only true B-rep adjacency counts: an edge shared by exactly two faces.
    """
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    face_id_of: Dict[int, int] = {
        hash(f.face_shape): f.face_id for f in faces if f.face_shape is not None
    }

    adjacency: Dict[int, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for i in range(1, edge_face_map.Extent() + 1):
        adjacent = edge_face_map.FindFromIndex(i)
        if adjacent.Extent() != 2:
            continue
        a = face_id_of.get(hash(TopoDS.Face_s(adjacent.First())))
        b = face_id_of.get(hash(TopoDS.Face_s(adjacent.Last())))
        if a is None or b is None or a == b:
            continue
        length = _edge_length(TopoDS.Edge_s(edge_face_map.FindKey(i)))
        adjacency[a][b] += length
        adjacency[b][a] += length
    return adjacency


def face_adjacency(shape: Any, faces: List[FaceData]) -> Dict[int, Set[int]]:
    """{face_id: {neighbouring face ids}} over shared B-rep edges.

    The unweighted view of `_shared_edge_lengths`, published because the
    direction evaluator needs it to count connected mold regions and it would
    otherwise build its own second copy of the same traversal.
    """
    if shape is None:
        return {}
    return {
        fid: set(neighbours)
        for fid, neighbours in _shared_edge_lengths(shape, faces).items()
    }


def _connected_regions(
    member_ids: Set[int], adjacency: Dict[int, Dict[int, float]]
) -> List[List[int]]:
    """Group member faces into connected components over shared edges.

    A physical wall is usually several faces (four planes plus four corner
    rounds on Part 1), so ambiguity must be resolved for the whole wall at
    once — otherwise adjacent tied faces would vote on each other and the
    outcome would depend on traversal order. Seeds and output are sorted by
    face_id so the grouping is reproducible.
    """
    regions: List[List[int]] = []
    unassigned = set(member_ids)
    for seed in sorted(member_ids):
        if seed not in unassigned:
            continue
        stack = [seed]
        region: List[int] = []
        while stack:
            current = stack.pop()
            if current not in unassigned:
                continue
            unassigned.discard(current)
            region.append(current)
            for neighbour in sorted(adjacency.get(current, {})):
                if neighbour in unassigned:
                    stack.append(neighbour)
        regions.append(sorted(region))
    return regions


def _resolve_ambiguous_regions(
    faces: List[FaceData],
    ambiguous: List[FaceData],
    shape: Any,
    tie_evidence: Dict[int, Dict[str, Any]],
) -> None:
    """Assign a mold half to external walls that physics left undecided.

    Rule — MINIMUM PARTING INTERFACE. Assigning a region to one half creates
    parting-line edges exactly where it borders the other half, so the
    boundary produced is the shared edge length with the OPPOSITE side.
    Taking the side with the greater shared length therefore yields the
    shorter core↔cavity interface, which is what a mold designer does: keep
    the split on the shortest closed boundary rather than letting it detour
    around every side feature.

    Votes are weighted by shared EDGE LENGTH (not face area) because edge
    length is precisely the amount of parting line created — face area does
    not appear in the boundary at all.

    Only faces already decided by the physical rules vote. Excluded voters:
      * the ambiguous region itself (a face may not vote on its own side),
      * undercut faces — they are released by a side action, not by either
        main half, so they must not steer the main parting line.
    """
    ambiguous_ids = {f.face_id for f in ambiguous}

    if shape is None:
        for face in ambiguous:
            face.mold_half = _EXTERNAL_TIE_DEFAULT
        logger.debug(
            "ambiguous walls: %d face(s) defaulted to %s (no shape for adjacency)",
            len(ambiguous), _EXTERNAL_TIE_DEFAULT,
        )
        return

    adjacency = _shared_edge_lengths(shape, faces)
    face_by_id = {f.face_id: f for f in faces}

    for region_index, region in enumerate(_connected_regions(ambiguous_ids, adjacency)):
        weights = {"core": 0.0, "cavity": 0.0}
        for face_id in region:
            for neighbour_id in sorted(adjacency.get(face_id, {})):
                if neighbour_id in ambiguous_ids:
                    continue
                neighbour = face_by_id.get(neighbour_id)
                if neighbour is None or neighbour.is_undercut:
                    continue
                if neighbour.mold_half in weights:
                    weights[neighbour.mold_half] += adjacency[face_id][neighbour_id]

        if weights["cavity"] > weights["core"]:
            half, reason = "cavity", "shorter interface on the cavity side"
        elif weights["core"] > weights["cavity"]:
            half, reason = "core", "shorter interface on the core side"
        else:
            half = _EXTERNAL_TIE_DEFAULT
            reason = (
                "no decided neighbour" if weights["core"] == 0.0
                else "exact tie — no discriminator"
            )

        for face_id in region:
            face_by_id[face_id].mold_half = half

        if logger.isEnabledFor(logging.DEBUG):
            evidence = tie_evidence.get(region[0], {})
            logger.debug(
                "ambiguous region %d: faces=%s area=%.1f cav_blocked=%s "
                "core_blocked=%s internal=%s/%s shared_len[cavity]=%.2f "
                "shared_len[core]=%.2f -> %s (%s)",
                region_index, region,
                sum(face_by_id[i].area for i in region),
                evidence.get("cav_blocked"), evidence.get("core_blocked"),
                evidence.get("internal"), evidence.get("samples"),
                weights["cavity"], weights["core"], half, reason,
            )


# ---------------------------------------------------------------------------
# Accessibility-consistent regions (specification section 7)
# ---------------------------------------------------------------------------

def classify_mold_regions(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    access: Any = None,
    raycaster: Optional[UndercutRaycaster] = None,
    shape: Any = None,
    config: Any = None,
) -> List[FaceData]:
    """Assign `mold_half` AND `mold_region` to every face.

    Three stages, in order of authority:

      1. NORMAL VOTING + REACHABILITY -- `classify_faces` above, unchanged.
         This is the validated classifier: it reproduces the mentor's cup
         example, both Bosch parts and every synthetic ground-truth fixture,
         and it already resolves vertical walls by raycast and genuinely
         ambiguous walls per region by shortest interface.

      2. ACCESSIBILITY RECONCILIATION -- specification section 7 requires the
         final classification to be consistent with accessibility. Where the
         four-way probe is DECISIVE (one side reaches the face, the other
         essentially cannot) and disagrees with stage 1, accessibility wins:
         steel that cannot touch a surface cannot form it. Where the probe is
         not decisive, stage 1 stands, because a normal vote carries real
         information that reachability alone does not.

      3. TOPOLOGY PROPAGATION -- sliver faces and faces the earlier stages
         left undecided take the half their neighbours agree on, weighted by
         shared edge length. A 0.2 mm fillet has no reliable normal and no
         meaningful reachability of its own; letting it disagree with the wall
         it blends into puts a spurious loop of parting line around it.

    `mold_half` keeps its exact previous meaning -- one of the two halves,
    always set. `mold_region` records the richer answer including NEUTRAL and
    UNDERCUT, which is what the parting boundary needs.
    """
    from core.accessibility import MoldRegion
    from core.tolerances import resolve

    cfg = resolve(config)

    # Stage 1 — the validated classifier.
    classify_faces(faces, mold_direction, raycaster, shape=shape)

    adjacency = _shared_edge_lengths(shape, faces) if shape is not None else {}
    by_id = {f.face_id: f for f in faces}

    # Stage 2 — reconcile with accessibility where it is decisive.
    reconciled = 0
    for face in faces:
        if getattr(face, "is_delegated", False):
            # Formed by a declared side action. It still gets a mold_half so
            # the viewer has something to colour, but its REGION records that
            # neither main half is responsible for it, and nothing downstream
            # may quietly reassign that.
            face.mold_region = MoldRegion.DELEGATED.value
            if not face.mold_half:
                face.mold_half = _EXTERNAL_TIE_DEFAULT
            continue
        if face.is_undercut:
            face.mold_region = MoldRegion.UNDERCUT.value
            continue

        entry = access.faces.get(face.face_id) if access is not None else None
        if entry is None:
            face.mold_region = face.mold_half or MoldRegion.AMBIGUOUS.value
            continue

        thresh = cfg.access_fraction_threshold
        reach_plus = entry.plus_fraction >= thresh
        reach_minus = entry.minus_fraction >= thresh

        decisive_half: Optional[str] = None
        if reach_plus and not reach_minus:
            decisive_half = "cavity"      # pull points toward the cavity
        elif reach_minus and not reach_plus:
            decisive_half = "core"

        if decisive_half is not None and face.mold_half != decisive_half:
            logger.debug(
                "face %d: accessibility overrides %s -> %s "
                "(reach +%.2f / -%.2f)",
                face.face_id, face.mold_half, decisive_half,
                entry.plus_fraction, entry.minus_fraction,
            )
            face.mold_half = decisive_half
            reconciled += 1

        face.mold_region = entry.region.value
        # NEUTRAL and AMBIGUOUS faces still need a forming half for the API
        # and the viewer; stage 1 supplied one and it stands.
        if entry.region in (MoldRegion.NEUTRAL, MoldRegion.AMBIGUOUS):
            if not face.mold_half:
                face.mold_half = _EXTERNAL_TIE_DEFAULT

    if reconciled:
        logger.debug("accessibility reconciled %d face(s)", reconciled)

    # Stage 3 — propagate over topology.
    _propagate_slivers(faces, by_id, adjacency, cfg)

    for face in faces:
        face.classification = "undercut" if face.is_undercut else face.mold_half

    return faces


def _propagate_slivers(
    faces: List[FaceData],
    by_id: Dict[int, FaceData],
    adjacency: Dict[int, Dict[int, float]],
    cfg: Any,
) -> None:
    """Give sliver faces the half their neighbours agree on.

    Runs to a fixed point so a chain of slivers resolves consistently rather
    than depending on iteration order, bounded so a pathological mesh cannot
    spin. Slivers never vote — only faces large enough to have a trustworthy
    classification do — which is what stops two adjacent slivers from
    confirming each other's noise.
    """
    if not adjacency:
        return

    slivers = [
        f for f in faces
        if not f.is_undercut
        and not getattr(f, "is_delegated", False)
        and 0.0 < f.area < cfg.sliver_face_area
    ]
    if not slivers:
        return

    sliver_ids = {f.face_id for f in slivers}
    moved = 0
    for _ in range(4):
        changed = False
        for face in slivers:
            weights = {"core": 0.0, "cavity": 0.0}
            for neighbour_id, shared in sorted(adjacency.get(face.face_id, {}).items()):
                if neighbour_id in sliver_ids:
                    continue
                neighbour = by_id.get(neighbour_id)
                if neighbour is None or neighbour.is_undercut:
                    continue
                if getattr(neighbour, "is_delegated", False):
                    # A delegated face is formed by other tooling, so it says
                    # nothing about where the main halves' split should run.
                    continue
                if neighbour.mold_half in weights:
                    weights[neighbour.mold_half] += shared
            if weights["core"] == weights["cavity"]:
                continue          # no discriminator: leave it where it is
            winner = "cavity" if weights["cavity"] > weights["core"] else "core"
            if face.mold_half != winner:
                face.mold_half = winner
                face.mold_region = winner
                changed = True
                moved += 1
        if not changed:
            break

    if moved:
        logger.debug(
            "topology propagation moved %d sliver face(s) below %.2f mm²",
            moved, cfg.sliver_face_area,
        )


def build_analysis_result(
    part_name: str,
    faces: List[FaceData],
    best_candidate: DirectionCandidate,
    all_candidates: List[DirectionCandidate],
) -> AnalysisResult:
    return AnalysisResult(
        part_name=part_name,
        total_faces=len(faces),
        best_mold_direction=best_candidate.direction,
        best_direction_label=best_candidate.label,
        direction_candidates=all_candidates,
        faces=faces,
        core_face_count=sum(1 for f in faces if f.classification == "core"),
        cavity_face_count=sum(1 for f in faces if f.classification == "cavity"),
        undercut_face_count=sum(1 for f in faces if f.classification == "undercut"),
        warning_face_count=sum(1 for f in faces if f.low_draft and not f.is_undercut),
        # Areas use the same predicates as the counts above, so the two can
        # never disagree. Report area ahead of count in the UI: a face count
        # reflects how the CAD kernel happened to subdivide the surface, area
        # reflects how the part actually divides between the mold halves.
        core_area=sum(f.area for f in faces if f.classification == "core"),
        cavity_area=sum(f.area for f in faces if f.classification == "cavity"),
        undercut_area=sum(f.area for f in faces if f.classification == "undercut"),
        warning_area=sum(f.area for f in faces if f.low_draft and not f.is_undercut),
        total_area=sum(f.area for f in faces),
        manufacturability_score=compute_score(faces),
    )


def get_classification_summary(faces: List[FaceData]) -> dict:
    summary = {}
    for label in ("core", "cavity", "undercut"):
        matching = [f for f in faces if f.classification == label]
        summary[label] = {
            "count": len(matching),
            "area": sum(f.area for f in matching),
        }
    warn = [f for f in faces if f.low_draft and not f.is_undercut]
    summary["warning"] = {
        "count": len(warn),
        "area": sum(f.area for f in warn),
    }
    return summary
