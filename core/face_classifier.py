"""
core/face_classifier.py — Classify each face as core, cavity, undercut, or warning.

Labels:
  "undercut" — face is physically trapped (from raycast)
  "warning"  — draft angle is dangerously low (< 0.5°)
  "cavity"   — normal points towards Cavity pull direction (mold_direction)
  "core"     — normal points towards Core pull direction (-mold_direction)
"""

from typing import List, Tuple

from core.models import FaceData, AnalysisResult, DirectionCandidate, compute_score


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def classify_faces(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> List[FaceData]:
    """
    Assign a classification label to every face using physically sound logic.
    """
    for face in faces:
        dot_val = _dot(face.normal, mold_direction)

        if face.is_undercut:
            face.classification = "undercut"
        elif face.draft_angle < 0.5:
            face.classification = "warning"
        elif dot_val >= 0:
            face.classification = "cavity"
        else:
            face.classification = "core"

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
        direction_candidates=all_candidates,
        faces=faces,
        core_face_count=sum(1 for f in faces if f.classification == "core"),
        cavity_face_count=sum(1 for f in faces if f.classification == "cavity"),
        undercut_face_count=sum(1 for f in faces if f.classification == "undercut"),
        warning_face_count=sum(1 for f in faces if f.classification == "warning"),
        manufacturability_score=compute_score(faces),
    )


def get_classification_summary(faces: List[FaceData]) -> dict:
    summary = {}
    for label in ("core", "cavity", "undercut", "warning"):
        matching = [f for f in faces if f.classification == label]
        summary[label] = {
            "count": len(matching),
            "area": sum(f.area for f in matching),
        }
    return summary
