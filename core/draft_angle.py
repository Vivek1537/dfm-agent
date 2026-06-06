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
    Compute draft angle relative to the pulling direction.
    Because faces pull in the direction they point closest to,
    draft_angle will always be positive (0 to 90 degrees).
    True undercuts are handled by the physical raycaster, not by negative draft.
    """
    for face in faces:
        dot_val = _dot(face.normal, mold_direction)
        
        # Pull_dot is the projection along the assigned mold half's pull direction
        pull_dot = abs(dot_val)
        pull_dot = max(0.0, min(1.0, pull_dot))

        angle_from_opening_rad = math.acos(pull_dot)
        face.draft_angle = 90.0 - math.degrees(angle_from_opening_rad)

    return faces


def classify_draft(draft_angle: float) -> str:
    if draft_angle > 1.0:
        return "GOOD"
    elif draft_angle >= 0.0:
        return "WARNING"
    else:
        return "UNDERCUT" # Should no longer happen with the new logic


def get_draft_summary(faces: List[FaceData]) -> dict:
    good = sum(1 for f in faces if f.draft_angle > 1.0)
    warning = sum(1 for f in faces if 0.0 <= f.draft_angle <= 1.0)
    undercut = sum(1 for f in faces if f.draft_angle < 0.0)
    angles = [f.draft_angle for f in faces]

    return {
        "good_count": good,
        "warning_count": warning,
        "undercut_count": undercut,
        "min_draft": min(angles) if angles else 0.0,
        "max_draft": max(angles) if angles else 0.0,
        "avg_draft": sum(angles) / len(angles) if angles else 0.0,
    }
