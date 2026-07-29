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
walls (all samples perpendicular) are assigned by which side of the part
centroid they sit on along the pull axis.
"""

from typing import List, Tuple

from core.models import FaceData, AnalysisResult, DirectionCandidate, compute_score

_PERP_EPS = 0.01


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def classify_faces(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> List[FaceData]:
    """
    Assign mold_half + classification to every face.
    Requires is_undercut (raycaster) and draft_angle/low_draft (draft step).
    """
    # Area-weighted part centroid — used to break ties for vertical walls
    total_area = sum(f.area for f in faces) or 1.0
    cx = sum(f.center[0] * f.area for f in faces) / total_area
    cy = sum(f.center[1] * f.area for f in faces) / total_area
    cz = sum(f.center[2] * f.area for f in faces) / total_area

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
            # Fully vertical wall: assign by position along the pull axis
            rel = (face.center[0] - cx, face.center[1] - cy, face.center[2] - cz)
            face.mold_half = "cavity" if _dot(rel, mold_direction) >= 0 else "core"

        face.classification = "undercut" if face.is_undercut else face.mold_half

    return faces


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
