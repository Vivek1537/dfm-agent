"""
core/pull_direction.py — Candidate mold pull directions.

The algorithm must not assume a fixed global axis is correct, so this module
generates candidate pull directions from several independent sources and
hands them to the evaluator as a normalised, deduplicated, deterministically
ordered list.

Sources, in the order they are emitted:

  1. Global axes            X, Y, Z
  2. Quadrant diagonals     the six 45 deg axes
  3. Rotational feature axes cylinder / cone axes, clustered by area
  4. Dominant planar normals the normals of the largest flat regions
  5. Principal axes          eigenvectors of the area-weighted point spread

Sources 1 and 2 are what Bosch described on the 2026-07-28 review call:
"usually it will be in X Y Z, in most cases", plus "1,1,1 and -1,1,1 ... a 45
degree" for rare edge cases, with an explicit statement that sweeping every
5 degrees is NOT required. Sources 3-5 are the geometry-driven additions: a
turned part's optimal pull is almost always a dominant feature axis, and a
part whose features are not axis-aligned would otherwise never be offered a
direction that fits it.

AXIS, NOT DIRECTION
-------------------
Undercut trapping is symmetric in +d / -d: a face is trapped for the mold
AXIS, not for the sign. The search therefore works on unique axes and halves
the ray count. The sign only decides which half is called core and which
cavity, and it is chosen separately once the winning axis is known (see
`core/mold_direction.py`). Candidates are canonicalised so that +D and -D
collapse to one entry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from core.models import FaceData
from core.tolerances import AnalysisConfig, NORMAL_CLUSTER_DOT, resolve

Vector3 = Tuple[float, float, float]

_INV_SQRT2 = 1.0 / math.sqrt(2.0)


# ---------------------------------------------------------------------------
# Source tags
# ---------------------------------------------------------------------------

SOURCE_GLOBAL_AXIS = "global_axis"
SOURCE_DIAGONAL = "diagonal"
SOURCE_FEATURE_AXIS = "feature_axis"
SOURCE_PLANAR_NORMAL = "planar_normal"
SOURCE_PRINCIPAL_AXIS = "principal_axis"
SOURCE_OVERRIDE = "override"

# Sources ranked by how strongly each is evidence that an axis is the part's
# DOMINANT GEOMETRIC AXIS — specification section 6, tie-break 3. Used only
# when two candidates are otherwise indistinguishable.
#
# Note the ordering: a rotational feature axis outranks a plain global axis.
# Z being one of the cartesian axes says nothing about the part; Z being the
# axis every cylinder on the part shares says a great deal. Ranking the global
# axes first instead made this tie-break useless, because an axis is normally
# proposed by the fixed set BEFORE any geometry source sees it — on the
# flanged boss that let a sideways clamshell pull (Y−, zero undercuts, tied on
# every earlier criterion) beat the axial pull the part is obviously built
# for.
# Principal axes rank LAST among the geometry sources, below even a plain
# global axis. Feature axes and planar normals are exact facts read off the
# B-rep — this cylinder's axis, this plane's normal. A principal axis is a
# statistical estimate over a point cloud that is not area-uniform, so it is
# the one source that can invent a direction the part does not have. On the
# O-ring nozzle, whose two radial eigenvalues are equal in exact geometry,
# sampling noise alone produced a "dominant axis" at (0.31, 0.95, 0) and it
# beat plain Y. Both are valid clamshell pulls on an axisymmetric part, but
# reporting an 18-degrees-off-axis vector as the recommended mold direction is
# strictly worse than reporting Y, and it is noise that chose it. A principal
# axis should win only when nothing better is tied with it — which is exactly
# the case it exists for, a part whose real axis is genuinely oblique.
_SOURCE_RANK = {
    SOURCE_OVERRIDE: 0,
    SOURCE_FEATURE_AXIS: 1,
    SOURCE_PLANAR_NORMAL: 2,
    SOURCE_GLOBAL_AXIS: 3,
    SOURCE_PRINCIPAL_AXIS: 4,
    SOURCE_DIAGONAL: 5,
}


@dataclass(frozen=True)
class PullDirection:
    """One candidate mold opening axis.

    `vector` is a unit axis in canonical form (dominant component positive).
    `label` is the human-readable name used by the API and the UI; it names
    the AXIS, and `core.mold_direction` turns it into a signed direction
    label once the sign is picked.
    """

    vector: Vector3
    source: str
    label: str
    weight: float = 0.0          # area (mm^2) backing a geometry-derived axis
    score: Optional[float] = None
    # EVERY source that proposed this axis, not just the first. One axis is
    # routinely proposed several times over — a turned part's axis is both a
    # cartesian axis and the axis its cylinders share — and it is the
    # strongest such claim that says how much the axis reflects the part.
    sources: Tuple[str, ...] = ()

    @property
    def rank(self) -> int:
        """Best (lowest) rank among the sources that proposed this axis."""
        return min(
            (_SOURCE_RANK.get(s, 99) for s in (self.sources or (self.source,))),
            default=99,
        )


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def normalize(v: Sequence[float]) -> Optional[Vector3]:
    """Unit vector, or None if the input is degenerate."""
    mag = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if mag < 1e-9:
        return None
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def canonical(v: Vector3) -> Vector3:
    """Flip an axis so its dominant component is positive.

    This is what makes +D and -D the same candidate. Ties on |component| are
    resolved by index order so the result is deterministic for axes like
    (0.707, -0.707, 0).
    """
    ax = 0
    best = abs(v[0])
    for i in (1, 2):
        if abs(v[i]) > best + 1e-12:
            best = abs(v[i])
            ax = i
    return v if v[ax] >= 0 else (-v[0], -v[1], -v[2])


def same_axis(a: Vector3, b: Vector3, dedup_dot: float) -> bool:
    """True when two axes point along the same line (either sign)."""
    return abs(dot(a, b)) > dedup_dot


# ---------------------------------------------------------------------------
# Fixed candidate set
# ---------------------------------------------------------------------------

# The 3 cartesian axes plus the 6 quadrant diagonals. Order is load-bearing:
# candidate evaluation sorts stably, so two axes with identical undercut
# figures keep this relative order, and it is the order the engine has
# always used.
FIXED_AXES: List[Tuple[Vector3, str, str]] = [
    ((0.0, 0.0, 1.0), "Z", SOURCE_GLOBAL_AXIS),
    ((1.0, 0.0, 0.0), "X", SOURCE_GLOBAL_AXIS),
    ((0.0, 1.0, 0.0), "Y", SOURCE_GLOBAL_AXIS),
    ((_INV_SQRT2, 0.0, _INV_SQRT2), "XZ+", SOURCE_DIAGONAL),
    ((_INV_SQRT2, 0.0, -_INV_SQRT2), "XZ-", SOURCE_DIAGONAL),
    ((0.0, _INV_SQRT2, _INV_SQRT2), "YZ+", SOURCE_DIAGONAL),
    ((0.0, -_INV_SQRT2, _INV_SQRT2), "YZ-", SOURCE_DIAGONAL),
    ((_INV_SQRT2, _INV_SQRT2, 0.0), "XY+", SOURCE_DIAGONAL),
    ((_INV_SQRT2, -_INV_SQRT2, 0.0), "XY-", SOURCE_DIAGONAL),
]


# ---------------------------------------------------------------------------
# Geometry-derived candidates
# ---------------------------------------------------------------------------

def _cluster_axes(
    items: Sequence[Tuple[Vector3, float]],
    dedup_dot: float,
) -> List[Tuple[Vector3, float]]:
    """Collapse near-parallel axes, accumulating their weights.

    Returns clusters sorted by descending weight, with exact ties broken on
    the rounded vector so the order never depends on face iteration order.
    """
    clusters: List[List] = []  # [axis, weight]
    for axis, weight in items:
        for cluster in clusters:
            if same_axis(axis, cluster[0], dedup_dot):
                cluster[1] += weight
                break
        else:
            clusters.append([axis, weight])
    clusters.sort(key=lambda c: (-c[1], tuple(round(x, 6) for x in c[0])))
    return [(c[0], c[1]) for c in clusters]


def feature_axes(
    faces: List[FaceData], config: Optional[AnalysisConfig] = None
) -> List[Tuple[Vector3, float]]:
    """Rotational feature axes (cylinders, cones), weighted by face area.

    For a turned or moulded part these are the natural pull candidates: the
    bore, the boss and the outer wall all share one axis, so their areas add
    up and that axis dominates.
    """
    cfg = resolve(config)
    items: List[Tuple[Vector3, float]] = []
    for f in faces:
        if f.axis is None:
            continue
        a = normalize(tuple(f.axis))
        if a is None:
            continue
        items.append((canonical(a), f.area))
    return _cluster_axes(items, cfg.axis_dedup_dot)[: cfg.max_geometry_axes]


def planar_normal_axes(
    faces: List[FaceData], config: Optional[AnalysisConfig] = None
) -> List[Tuple[Vector3, float]]:
    """Dominant planar face normals, weighted by area.

    A mold most often opens perpendicular to the part's largest flat regions,
    so the normal of the biggest plane cluster is a strong candidate. Only
    planes contribute: a curved face's representative normal says nothing
    about a global direction.
    """
    cfg = resolve(config)
    items: List[Tuple[Vector3, float]] = []
    for f in faces:
        if f.surface_type != "PLANE":
            continue
        n = normalize(f.normal)
        if n is None:
            continue
        items.append((canonical(n), f.area))
    # Planes are clustered on a tighter tolerance than features: two planes
    # 2 degrees apart really are two different directions, whereas two
    # nominally coaxial bores that differ by 2 degrees are one axis with
    # rounding error.
    return _cluster_axes(items, NORMAL_CLUSTER_DOT)[: cfg.max_geometry_axes]


# An eigenvalue must exceed its neighbour by this relative margin for the
# corresponding eigenvector to count as a real geometric direction.
#
# When two eigenvalues are close the part is (near-)isotropic in that plane
# and the eigenvectors spanning it are ARBITRARY — any rotation of them
# diagonalises the covariance equally well, so which one comes back is decided
# by numerical noise. On the flanged boss, whose surface samples come from a
# 5x5 UV grid that is not rotationally symmetric, that noise alone produced a
# "principal axis" 3.9 degrees off Z, far enough to escape axis dedup and be
# offered as a distinct candidate on an axisymmetric part whose only real axis
# is Z. Requiring separation discards those.
PRINCIPAL_AXIS_SEPARATION = 0.15

# Dedup tolerance for principal axes: cos(10 degrees). See the note in
# `generate_candidate_directions` for why a statistical estimate gets a far
# looser tolerance than an exactly-known geometric axis.
PRINCIPAL_AXIS_DEDUP_DOT = math.cos(math.radians(10.0))


def principal_axes(
    faces: List[FaceData], config: Optional[AnalysisConfig] = None
) -> List[Tuple[Vector3, float]]:
    """Well-separated principal axes of the area-weighted surface point spread.

    Eigenvectors of the covariance of every surface sample, each weighted by
    the area its face contributes. For a part whose features are not aligned
    to the global frame this is the only source that can propose the axis the
    part is actually built around.

    Only eigenvectors whose eigenvalue stands clear of its neighbours are
    returned; see `PRINCIPAL_AXIS_SEPARATION`. An axisymmetric part therefore
    contributes at most its one true axis, and a sphere or a cube contributes
    nothing, which is correct — neither has a distinguished direction.
    """
    cfg = resolve(config)
    try:
        import numpy as np
    except ImportError:      # pragma: no cover - numpy is a hard requirement
        return []

    pts: List[Vector3] = []
    wts: List[float] = []
    for f in faces:
        samples = f.sample_points or [f.center]
        if not samples:
            continue
        w = f.area / len(samples)
        for p in samples:
            pts.append(p)
            wts.append(w)

    if len(pts) < 3:
        return []

    P = np.asarray(pts, dtype=float)
    W = np.asarray(wts, dtype=float)
    total = float(W.sum())
    if total <= 0.0:
        return []

    mean = (P * W[:, None]).sum(axis=0) / total
    D = P - mean
    cov = (D * W[:, None]).T @ D / total

    try:
        vals, vecs = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:      # pragma: no cover - defensive
        return []

    order = list(np.argsort(vals)[::-1])
    sorted_vals = [float(vals[i]) for i in order]
    largest = sorted_vals[0] if sorted_vals else 0.0
    if largest <= 0.0:
        return []

    out: List[Tuple[Vector3, float]] = []
    for rank, i in enumerate(order):
        value = sorted_vals[rank]
        # Separation from whichever neighbour is closer in magnitude. An
        # eigenvalue wedged between two similar ones names no direction.
        neighbours = [
            sorted_vals[j] for j in (rank - 1, rank + 1)
            if 0 <= j < len(sorted_vals)
        ]
        gap = min(abs(value - n) for n in neighbours) if neighbours else value
        if gap / largest < PRINCIPAL_AXIS_SEPARATION:
            continue
        a = normalize(tuple(float(x) for x in vecs[:, i]))
        if a is None:
            continue
        out.append((canonical(a), value))
    return out[: cfg.max_geometry_axes]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _geometry_label(prefix: str, index: int, axis: Vector3) -> str:
    return f"{prefix}{index}({axis[0]:.2f},{axis[1]:.2f},{axis[2]:.2f})"


def generate_candidate_directions(
    faces: List[FaceData],
    config: Optional[AnalysisConfig] = None,
) -> List[PullDirection]:
    """Build the full candidate axis list for a part.

    Fixed axes come first and always survive, then each geometry-derived
    source contributes any axis the list does not already cover. The result
    is capped at `config.max_candidate_directions`; because the fixed set is
    emitted first, raising or lowering the cap only ever changes how much of
    the geometry-derived tail is kept.
    """
    cfg = resolve(config)
    out: List[PullDirection] = []

    def add(
        axis: Vector3,
        label: str,
        source: str,
        weight: float = 0.0,
        dedup_dot: Optional[float] = None,
    ) -> bool:
        """Add an axis, or record `source` against the entry that covers it."""
        a = normalize(axis)
        if a is None:
            return False
        a = canonical(a)
        tol = cfg.axis_dedup_dot if dedup_dot is None else dedup_dot
        for i, existing in enumerate(out):
            if same_axis(a, existing.vector, tol):
                # Already present. Do NOT discard the fact that this source
                # also proposed it — that is what tells the tie-break the axis
                # is the part's own, not merely one of the cartesian three.
                if source not in existing.sources:
                    out[i] = replace(
                        existing,
                        sources=existing.sources + (source,),
                        weight=max(existing.weight, weight),
                    )
                return False
        out.append(PullDirection(
            vector=a, source=source, label=label, weight=weight,
            sources=(source,),
        ))
        return True

    for axis, label, source in FIXED_AXES:
        add(axis, label, source)

    # AX* keeps the historical label prefix for rotational feature axes so the
    # UI and any saved output stay readable across this change.
    for i, (axis, area) in enumerate(feature_axes(faces, cfg), start=1):
        add(axis, _geometry_label("AX", i, axis), SOURCE_FEATURE_AXIS, area)

    for i, (axis, area) in enumerate(planar_normal_axes(faces, cfg), start=1):
        add(axis, _geometry_label("PN", i, axis), SOURCE_PLANAR_NORMAL, area)

    # Principal axes are deduplicated at a much looser angle than the exact
    # sources, because they are a STATISTICAL estimate and cannot be trusted
    # to better than a few degrees. The surface samples they are computed from
    # are laid out on a UV grid, which is not area-uniform: five samples round
    # a cylinder sit at 0.63, 1.88, 3.14, 4.40 and 5.65 radians, so even a
    # perfectly axisymmetric part yields a covariance that is not quite
    # axisymmetric. On the flanged boss the top eigenvector came out 3.9
    # degrees off Z — well-separated from the others, so no eigenvalue test
    # rejects it, but wrong all the same, and close enough to Z to win the
    # ranking and put the flange and the boss in the same mold half.
    #
    # Within PRINCIPAL_AXIS_DEDUP_DOT of an axis already on the list, the
    # estimate is that axis measured noisily and the exact one already covers
    # it. Beyond that the part really does have an oblique axis, and it is
    # offered.
    for i, (axis, spread) in enumerate(principal_axes(faces, cfg), start=1):
        add(
            axis, _geometry_label("PA", i, axis), SOURCE_PRINCIPAL_AXIS, spread,
            dedup_dot=PRINCIPAL_AXIS_DEDUP_DOT,
        )

    return out[: cfg.max_candidate_directions]


def override_direction(vector: Sequence[float]) -> PullDirection:
    """Wrap a user-supplied vector as a PullDirection.

    Not canonicalised: an override carries its sign deliberately (the user is
    choosing which half is core), so it is passed through as given.

    Raises ValueError on a zero vector.
    """
    v = normalize(vector)
    if v is None:
        raise ValueError("Override direction must be a non-zero vector.")
    return PullDirection(
        vector=v,
        source=SOURCE_OVERRIDE,
        label=f"({v[0]:.2f},{v[1]:.2f},{v[2]:.2f})",
    )
