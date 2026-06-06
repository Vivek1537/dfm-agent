"""
core/mold_direction.py — Find the optimal mold opening direction.

Tests 12 candidate directions. For each direction, it uses the true
raycast undercut detector to find how many faces are trapped.
Returns the direction with the fewest trapped faces.
"""

import math
from typing import List, Tuple

from core.models import FaceData, DirectionCandidate
from core.undercut_detector import detect_undercuts

_INV_SQRT2 = 1.0 / math.sqrt(2.0)

CANDIDATE_DIRECTIONS: List[Tuple[Tuple[float, float, float], str]] = [
    ((0.0, 0.0, 1.0),  "Z+"), ((0.0, 0.0, -1.0), "Z-"),
    ((1.0, 0.0, 0.0),  "X+"), ((-1.0, 0.0, 0.0), "X-"),
    ((0.0, 1.0, 0.0),  "Y+"), ((0.0, -1.0, 0.0), "Y-"),
    ((_INV_SQRT2, 0.0, _INV_SQRT2),  "X+Z+"), ((_INV_SQRT2, 0.0, -_INV_SQRT2), "X+Z-"),
    ((-_INV_SQRT2, 0.0, _INV_SQRT2), "X-Z+"), ((-_INV_SQRT2, 0.0, -_INV_SQRT2), "X-Z-"),
    ((0.0, _INV_SQRT2, _INV_SQRT2),  "Y+Z+"), ((0.0, -_INV_SQRT2, _INV_SQRT2), "Y-Z+"),
]

def find_best_mold_direction(
    faces: List[FaceData],
) -> Tuple[DirectionCandidate, List[DirectionCandidate]]:
    candidates: List[DirectionCandidate] = []

    for direction, label in CANDIDATE_DIRECTIONS:
        # detect_undercuts modifies faces in-place
        detect_undercuts(faces, direction)
        
        undercut_count = sum(1 for f in faces if f.is_undercut)
        undercut_area = sum(f.area for f in faces if f.is_undercut)

        candidates.append(DirectionCandidate(
            direction=direction,
            label=label,
            undercut_count=undercut_count,
            undercut_area=undercut_area,
        ))

    candidates.sort(key=lambda c: (c.undercut_count, c.undercut_area))
    
    # Re-run detect_undercuts for the best direction so the faces are left in the correct state
    best = candidates[0]
    detect_undercuts(faces, best.direction)

    return best, candidates
