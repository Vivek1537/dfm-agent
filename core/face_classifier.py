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
"""

from typing import List, Optional, Tuple

from core.models import FaceData, AnalysisResult, DirectionCandidate, compute_score
from core.undercut_detector import UndercutRaycaster

_PERP_EPS = 0.01


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def classify_faces(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    raycaster: Optional[UndercutRaycaster] = None,
    tie_half: str = "cavity",
) -> List[FaceData]:
    """
    Assign mold_half + classification to every face.
    Requires is_undercut (raycaster) and draft_angle/low_draft (draft step).

    `tie_half` decides the faces both halves can reach (see `tied_faces`).
    Reachability leaves these genuinely free, so this is not a heuristic gap
    to be filled with a better guess — it is the degree of freedom the mould
    designer actually exercises, and the literature resolves it by optimising
    parting-line flatness rather than by a fixed default.
    """
    # Area-weighted part centroid — fallback tie-break for vertical walls
    total_area = sum(f.area for f in faces) or 1.0
    cx = sum(f.center[0] * f.area for f in faces) / total_area
    cy = sum(f.center[1] * f.area for f in faces) / total_area
    cz = sum(f.center[2] * f.area for f in faces) / total_area

    pull = mold_direction
    neg_pull = (-pull[0], -pull[1], -pull[2])

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
            face.mold_half = _vertical_wall_half(
                face, pull, neg_pull, raycaster, (cx, cy, cz), tie_half
            )

        face.classification = "undercut" if face.is_undercut else face.mold_half

    _orient_halves(faces, raycaster)

    return faces


def tied_faces(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    raycaster: Optional[UndercutRaycaster],
) -> List[FaceData]:
    """Faces both mold halves can reach, and which are not internal.

    These are the ones `_vertical_wall_half` resolves with `tie_half`. Every
    other face is pinned by reachability, so this list is the whole of the
    split's freedom: on Part1 it is 8 faces (four skirt walls plus four
    corner rounds, 751.6 mm²), and assigning them to the core rather than the
    cavity is the entire difference between a flat rim at the top and a loop
    meandering around the snap-tab windows.
    """
    if raycaster is None:
        return []

    pull = mold_direction
    neg_pull = (-pull[0], -pull[1], -pull[2])
    out: List[FaceData] = []
    for face in faces:
        normals = face.sample_normals or [face.normal]
        w = face.area / len(normals) if normals else 0.0
        cavity_w = sum(w for nv in normals if _dot(nv, pull) > _PERP_EPS)
        core_w = sum(w for nv in normals if _dot(nv, pull) < -_PERP_EPS)
        if cavity_w != core_w:
            continue                      # decided by normal vote, not tied
        pts = face.sample_points or [face.center]
        n = min(len(pts), len(normals))
        if not n:
            continue
        reachable_both = all(
            not raycaster.is_blocked(pts[i], normals[i], d)
            for i in range(n) for d in (pull, neg_pull)
        )
        internal = sum(
            1 for i in range(n)
            if raycaster.is_blocked(pts[i], normals[i], normals[i])
        )
        if reachable_both and internal <= n / 2:
            out.append(face)
    return out


def _orient_halves(
    faces: List[FaceData],
    raycaster: Optional[UndercutRaycaster],
) -> None:
    """Name the half that forms the part's internal surfaces "core".

    Which faces group together is a geometric fact; which group is *called*
    core is a naming convention, and Bosch state it plainly: "even the
    internal surface will be formed by the core". Deriving the name from the
    pull sign instead conflates the two, so flipping the sign silently
    renamed a correct partition into a wrong one. Decide the partition on
    geometry, then fix the polarity here.

    No-op when the probe is unavailable or finds no internal surface at all
    (a solid boss has none), leaving the normal-vote naming untouched.
    """
    if raycaster is None:
        return

    internal_area = {"core": 0.0, "cavity": 0.0}
    for face in faces:
        pts = face.sample_points or [face.center]
        nrms = face.sample_normals or [face.normal]
        n = min(len(pts), len(nrms))
        if not n:
            continue
        # A sample whose own outward normal runs back into material across a
        # void is looking at the far side of an internal feature.
        hits = sum(
            1 for i in range(n)
            if raycaster.is_blocked(pts[i], nrms[i], nrms[i])
        )
        if hits > n / 2 and face.mold_half in internal_area:
            internal_area[face.mold_half] += face.area

    if internal_area["cavity"] > internal_area["core"]:
        for face in faces:
            if face.mold_half == "core":
                face.mold_half = "cavity"
            elif face.mold_half == "cavity":
                face.mold_half = "core"
            face.classification = (
                "undercut" if face.is_undercut else face.mold_half
            )


def _vertical_wall_half(
    face: FaceData,
    pull: Tuple[float, float, float],
    neg_pull: Tuple[float, float, float],
    raycaster: Optional[UndercutRaycaster],
    centroid: Tuple[float, float, float],
    tie_half: str = "cavity",
) -> str:
    """Mold half that PHYSICALLY forms a fully vertical wall.

    Reachability test: cast rays from the wall's sample points along the
    pull direction (toward the cavity half). If the part blocks that path
    (e.g. an internal bore under a closed top), the cavity steel can never
    touch this wall — the core forms it. And vice versa. Falls back to the
    centroid-side heuristic when no raycaster is available.
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
        if cav_blocked != core_blocked:
            # Blocked toward the cavity → only the core can form it.
            return "core" if cav_blocked > core_blocked else "cavity"
        if internal > n / 2:
            # Through-holes / internal channels: formed by a core pin
            # (judges' cap example: internal surfaces → core).
            return "core"
        # Reachable from both halves and not internal: the free set. Neither
        # assignment is more physical, so the caller decides — see `tied_faces`
        # and the parting-line optimisation that consumes it.
        return tie_half

    # No raycaster: which side of the centroid it sits on
    rel = (face.center[0] - centroid[0],
           face.center[1] - centroid[1],
           face.center[2] - centroid[2])
    return "cavity" if _dot(rel, pull) >= 0 else "core"


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
