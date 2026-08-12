"""
core/draft_angle.py — Compute the draft angle for each face.

Draft angle is always computed relative to the mold half the face
is assigned to pull from.
Cavity faces pull in `mold_direction`. Core faces pull in `-mold_direction`.
"""

import math
from typing import List, Tuple

from core.models import FaceData


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def compute_draft_angles(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> List[FaceData]:
    """
    Compute the WORST-CASE draft angle across all surface samples of each face.

    Per sample: draft = 90° - angle(normal, pull-of-its-half) = asin(|n·d|).
    A curved face reports its most critical (lowest-draft) region — a single
    midpoint value hides zero-draft bands on wrapped faces.
    True undercuts are handled by the physical raycaster, not by negative draft.
    """
    for face in faces:
        normals = face.sample_normals or [face.normal]
        worst = 90.0
        for nv in normals:
            pull_dot = abs(_dot(nv, mold_direction))
            pull_dot = max(0.0, min(1.0, pull_dot))
            draft = math.degrees(math.asin(pull_dot))
            if draft < worst:
                worst = draft
        face.draft_angle = worst
        face.low_draft = worst < 1.0

    return faces


def classify_draft(draft_angle: float) -> str:
    if draft_angle >= 1.0:
        return "GOOD"
    return "WARNING"


def get_draft_summary(faces: List[FaceData]) -> dict:
    good = sum(1 for f in faces if not f.low_draft)
    warning = sum(1 for f in faces if f.low_draft)
    angles = [f.draft_angle for f in faces]

    return {
        "good_count": good,
        "warning_count": warning,
        "undercut_count": sum(1 for f in faces if f.is_undercut),
        "min_draft": min(angles) if angles else 0.0,
        "max_draft": max(angles) if angles else 0.0,
        "avg_draft": sum(angles) / len(angles) if angles else 0.0,
    }
