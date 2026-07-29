"""
core/mold_direction.py — Find the optimal mold opening direction.

v2 (Phase 2 rewrite):
- Undercut detection is symmetric in +d / -d (a face is trapped for the
  mold AXIS, not the sign), so we search unique axes only — half the rays.
- Candidate axes: 9 fixed axes (3 cartesian + 6 diagonals, symmetric set)
  PLUS geometry-driven axes extracted from cylinder/cone faces (a turned
  part's optimal pull is almost always a dominant feature axis).
- One shared UndercutRaycaster across the whole sweep (was rebuilt 13×).
- Reduced per-face sampling during the sweep; full sampling for the winner.
- Sign convention: the pull direction points toward the CAVITY half, chosen
  as the side with the larger visible area (external/cosmetic side).
"""

import math
from typing import List, Optional, Tuple

from core.models import FaceData, DirectionCandidate
from core.undercut_detector import UndercutRaycaster, evaluate_direction

_INV_SQRT2 = 1.0 / math.sqrt(2.0)

# Unique search axes (sign chosen later). Symmetric diagonal coverage.
CANDIDATE_AXES: List[Tuple[Tuple[float, float, float], str]] = [
    ((0.0, 0.0, 1.0), "Z"),
    ((1.0, 0.0, 0.0), "X"),
    ((0.0, 1.0, 0.0), "Y"),
    ((_INV_SQRT2, 0.0, _INV_SQRT2), "XZ+"),
    ((_INV_SQRT2, 0.0, -_INV_SQRT2), "XZ-"),
    ((0.0, _INV_SQRT2, _INV_SQRT2), "YZ+"),
    ((0.0, -_INV_SQRT2, _INV_SQRT2), "YZ-"),
    ((_INV_SQRT2, _INV_SQRT2, 0.0), "XY+"),
    ((_INV_SQRT2, -_INV_SQRT2, 0.0), "XY-"),
]

# Legacy alias kept for the API layer (label lookup).
CANDIDATE_DIRECTIONS: List[Tuple[Tuple[float, float, float], str]] = [
    ((0.0, 0.0, -1.0), "Z-"), ((0.0, 0.0, 1.0), "Z+"),
    ((1.0, 0.0, 0.0), "X+"), ((-1.0, 0.0, 0.0), "X-"),
    ((0.0, 1.0, 0.0), "Y+"), ((0.0, -1.0, 0.0), "Y-"),
]

# Max surface samples per face during the axis sweep (full set for winner).
SWEEP_SAMPLES_PER_FACE = 5

# Two axes closer than this (|dot|) are considered duplicates.
AXIS_DEDUP_DOT = 0.999


def _norm(v: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-9:
        return None
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _canonical(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Flip an axis so its dominant component is positive (dedup helper)."""
    ax = max(range(3), key=lambda i: abs(v[i]))
    return v if v[ax] >= 0 else (-v[0], -v[1], -v[2])


def _geometry_axes(faces: List[FaceData], max_axes: int = 3) -> List[Tuple[Tuple[float, float, float], str]]:
    """
    Extract dominant rotational-feature axes (cylinders/cones), weighted by
    face area. These are the natural pull-direction candidates for real parts.
    """
    clusters: List[Tuple[Tuple[float, float, float], float]] = []  # (axis, cum_area)
    for f in faces:
        if f.axis is None:
            continue
        a = _norm(tuple(f.axis))
        if a is None:
            continue
        a = _canonical(a)
        for i, (c_axis, c_area) in enumerate(clusters):
            if abs(_dot(a, c_axis)) > AXIS_DEDUP_DOT:
                clusters[i] = (c_axis, c_area + f.area)
                break
        else:
            clusters.append((a, f.area))

    clusters.sort(key=lambda t: t[1], reverse=True)

    result = []
    for i, (axis, _area) in enumerate(clusters[:max_axes]):
        label = f"AX{i + 1}({axis[0]:.2f},{axis[1]:.2f},{axis[2]:.2f})"
        result.append((axis, label))
    return result


def _axis_label_to_direction_label(axis_label: str, sign: int) -> str:
    """Human label for the signed direction of a named axis."""
    if axis_label in ("Z", "X", "Y"):
        return f"{axis_label}{'+' if sign > 0 else '-'}"
    return axis_label if sign > 0 else f"-{axis_label}"


def _pick_sign(
    faces: List[FaceData],
    axis: Tuple[float, float, float],
) -> int:
    """
    Choose the pull sign so the direction points toward the CAVITY half.
    Convention: the cavity forms the external (larger visible-area) side.
    Uses per-sample normals so curved faces vote proportionally.
    """
    pos_area = 0.0
    neg_area = 0.0
    for f in faces:
        nrms = f.sample_normals or [f.normal]
        if not nrms:
            continue
        w = f.area / len(nrms)
        for nv in nrms:
            d = _dot(nv, axis)
            if d > 0.01:
                pos_area += w
            elif d < -0.01:
                neg_area += w
    return 1 if pos_area >= neg_area else -1


def find_best_mold_direction(
    faces: List[FaceData],
    raycaster: Optional[UndercutRaycaster] = None,
) -> Tuple[DirectionCandidate, List[DirectionCandidate]]:
    """
    Search all candidate axes (fixed + geometry-derived) for the direction
    with the fewest trapped faces. Returns (best, all_candidates) and leaves
    `faces` fully evaluated (all samples) for the best direction.
    """
    if raycaster is None:
        raycaster = UndercutRaycaster(faces)

    axes = list(CANDIDATE_AXES)
    for geo_axis, label in _geometry_axes(faces):
        if all(abs(_dot(geo_axis, a)) < AXIS_DEDUP_DOT for a, _ in axes):
            axes.append((geo_axis, label))

    candidates: List[DirectionCandidate] = []

    for axis, axis_label in axes:
        evaluate_direction(
            raycaster, faces, axis, max_samples_per_face=SWEEP_SAMPLES_PER_FACE
        )

        undercut_count = sum(1 for f in faces if f.is_undercut)
        undercut_area = sum(f.area for f in faces if f.is_undercut)

        sign = _pick_sign(faces, axis)
        direction = (axis[0] * sign, axis[1] * sign, axis[2] * sign)

        candidates.append(DirectionCandidate(
            direction=direction,
            label=_axis_label_to_direction_label(axis_label, sign),
            undercut_count=undercut_count,
            undercut_area=undercut_area,
        ))

    # Judges' guidance (2026-07-28): rank by undercut AREA first — a face
    # split into several small patches shouldn't outrank one large trapped
    # face. Count is the tie-break.
    candidates.sort(key=lambda c: (c.undercut_area, c.undercut_count))

    # Full-resolution evaluation for the winning direction so downstream
    # classification uses the most accurate per-face verdicts.
    best = candidates[0]
    evaluate_direction(raycaster, faces, best.direction)

    return best, candidates
