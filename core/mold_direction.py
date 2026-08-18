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
from core.undercut_detector import (
    UndercutRaycaster,
    evaluate_direction,
    refine_direction,
)

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


def _flip_direction_label(label: str) -> str:
    """Label for the opposite direction: 'Z+'↔'Z-', 'XZ+'↔'-XZ+', 'AX1(..)'↔'-AX1(..)'."""
    if label in ("Z+", "X+", "Y+"):
        return label[0] + "-"
    if label in ("Z-", "X-", "Y-"):
        return label[0] + "+"
    return label[1:] if label.startswith("-") else "-" + label


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
    Fast sweep heuristic: point the pull toward the side with the larger
    visible area (external/cosmetic side). Refined for the winning axis by
    `_pick_sign_internal`, which uses ray-based internality instead.
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


# Max surface samples per face when picking the pull sign (internality
# probing costs 3 rays per sample; 5 is plenty for a direction vote).
SIGN_SAMPLES_PER_FACE = 5


def _pick_sign_internal(
    faces: List[FaceData],
    axis: Tuple[float, float, float],
    raycaster: UndercutRaycaster,
) -> int:
    """Choose the pull sign from the part's INTERNAL features.

    Injection-molding convention (confirmed by the judges' cap example):
    the CORE forms the internal surfaces, entering through the side those
    pockets open toward; the CAVITY wraps the external shell on the
    opposite side. So: find samples that face other part material across
    a void (internal walls), see which way along the axis they escape,
    and put the core there — the pull (toward cavity) is the other way.

    Falls back to the visible-area heuristic when the part has no
    asymmetric internal features (e.g. a through-bore only).
    """
    neg_axis = (-axis[0], -axis[1], -axis[2])
    core_pos_w = 0.0   # internal features opening toward +axis
    core_neg_w = 0.0   # internal features opening toward -axis

    # Probe only the dominant faces (by area) — the sign is an area-weighted
    # vote, so faces in the small-area tail can't change the outcome.
    by_area = sorted(faces, key=lambda f: -f.area)
    total_area = sum(f.area for f in faces)
    probe_faces = []
    acc = 0.0
    for f in by_area:
        probe_faces.append(f)
        acc += f.area
        if acc >= total_area * 0.9:
            break

    for f in probe_faces:
        pts = f.sample_points or [f.center]
        nrms = f.sample_normals or [f.normal]
        n = min(len(pts), len(nrms), SIGN_SAMPLES_PER_FACE)
        if n == 0:
            continue
        w = f.area / n
        for p, nv in zip(pts[:n], nrms[:n]):
            # Internal wall: own normal points at more part material.
            if not raycaster.is_blocked(p, nv, nv):
                continue
            blocked_pos = raycaster.is_blocked(p, nv, axis)
            blocked_neg = raycaster.is_blocked(p, nv, neg_axis)
            if blocked_pos and not blocked_neg:
                core_neg_w += w      # opens toward -axis → core enters from -axis
            elif blocked_neg and not blocked_pos:
                core_pos_w += w      # opens toward +axis → core enters from +axis

    if core_pos_w == core_neg_w:
        return _pick_sign(faces, axis)
    # Pull points toward the cavity — the side opposite the core.
    return -1 if core_pos_w > core_neg_w else 1


def find_best_mold_direction(
    faces: List[FaceData],
    raycaster: Optional[UndercutRaycaster] = None,
    exact_candidates: bool = True,
) -> Tuple[DirectionCandidate, List[DirectionCandidate]]:
    """
    Search all candidate axes (fixed + geometry-derived) for the direction
    with the fewest trapped faces. Returns (best, all_candidates) and leaves
    `faces` fully evaluated (all samples) for the best direction.

    `exact_candidates` (default) evaluates every axis in full so each entry
    in the returned ranking carries a real undercut count and area.

    Branch-and-bound pruning (exact_candidates=False) finds the same winner
    roughly 5x faster, but it abandons a losing axis the moment its running
    undercut area passes the incumbent — and because faces are visited
    biggest-first, that is usually after a single face. Every loser then
    reports the same ">=1 undercuts", which is honest but tells a user
    nothing about how the directions compare. Since ranking candidate
    directions is the point of this panel, the exact numbers are worth the
    extra time; reducing sample density instead is NOT a valid trade, as it
    measurably reorders the ranking.
    """
    if raycaster is None:
        raycaster = UndercutRaycaster(faces)

    axes = list(CANDIDATE_AXES)
    for geo_axis, label in _geometry_axes(faces):
        if all(abs(_dot(geo_axis, a)) < AXIS_DEDUP_DOT for a, _ in axes):
            axes.append((geo_axis, label))

    candidates: List[DirectionCandidate] = []
    best_area_so_far: Optional[float] = None
    best_snapshot: Optional[List[Tuple[bool, float]]] = None

    for axis, axis_label in axes:
        undercut_count, undercut_area = evaluate_direction(
            raycaster, faces, axis,
            max_samples_per_face=SWEEP_SAMPLES_PER_FACE,
            abort_above_area=None if exact_candidates else best_area_so_far,
        )
        if best_area_so_far is None or undercut_area < best_area_so_far:
            best_area_so_far = undercut_area
            # Snapshot per-face verdicts of the incumbent best axis so we
            # don't have to re-run the whole sweep for the winner later.
            best_snapshot = [(f.is_undercut, f.trapped_fraction) for f in faces]

        sign = _pick_sign(faces, axis)
        direction = (axis[0] * sign, axis[1] * sign, axis[2] * sign)

        candidates.append(DirectionCandidate(
            direction=direction,
            label=_axis_label_to_direction_label(axis_label, sign),
            undercut_count=undercut_count,
            undercut_area=undercut_area,
            # Only a candidate whose evaluation actually aborted early carries
            # lower-bound counts (rendered as ">=N"). With exact_candidates the
            # sweep never aborts, so every figure here is a true total.
            pruned=(
                not exact_candidates
                and best_area_so_far is not None
                and undercut_area > best_area_so_far
            ),
        ))

    # Judges' guidance (2026-07-28): rank by undercut AREA first — a face
    # split into several small patches shouldn't outrank one large trapped
    # face. Count is the tie-break.
    candidates.sort(key=lambda c: (c.undercut_area, c.undercut_count))

    # Refine the WINNER's pull sign using internal-feature analysis (the
    # sweep uses a cheap area heuristic; sign doesn't affect undercuts,
    # but it decides which half is called core vs cavity downstream).
    best = candidates[0]
    axis = best.direction
    axis_mag = math.sqrt(sum(c * c for c in axis))
    unit_axis = tuple(c / axis_mag for c in axis)
    refined = _pick_sign_internal(faces, unit_axis, raycaster)
    refined_dir = tuple(c * refined for c in unit_axis)
    if any(abs(a - b) > 1e-9 for a, b in zip(refined_dir, best.direction)):
        best.label = _flip_direction_label(best.label)
        best.direction = refined_dir

    # Restore the winner's sweep verdicts, then re-check at full sample
    # resolution ONLY the faces that showed any trapping (huge speedup on
    # parts where most faces are free).
    if best_snapshot is not None:
        for f, (uc, frac) in zip(faces, best_snapshot):
            f.is_undercut = uc
            f.trapped_fraction = frac
        refine_direction(raycaster, faces, best.direction)
    else:
        evaluate_direction(raycaster, faces, best.direction, exact_fractions=True)

    return best, candidates
