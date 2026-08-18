"""
core/tolerances.py — Centralised numerical tolerances and analysis config.

CAD geometry is noisy: STEP files carry accumulated float error, kernels
shatter one physical wall into a dozen faces, and blend fillets leave slivers
below any sane feature size. Every stage of this pipeline therefore compares
with a tolerance rather than for equality, and until now each of those
tolerances lived as a private constant next to the code that used it. Two
modules had already drifted into keeping their own copy of the same number
(`PERP_EPS` in the undercut detector and `_PERP_EPS` in the face classifier).

This module is the single place those values are defined. The names follow the
parting-line specification (§14); the values are exactly the ones the modules
carried before, so importing them here is behaviour-preserving.

`AnalysisConfig` bundles the knobs a caller may legitimately want to turn —
sampling density, tolerances, how many pull directions to try, whether to run
the expensive silhouette pass. Every stage accepts one, and `DEFAULT_CONFIG`
reproduces the historical behaviour, so `config=None` anywhere means "what the
engine did before".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


# ---------------------------------------------------------------------------
# Angular tolerances (dimensionless dot products unless stated otherwise)
# ---------------------------------------------------------------------------

# |dot(normal, pull)| below this -> the sample lies on a wall parallel to the
# pull axis (~0.6 deg off the parting plane). Such a sample faces neither mold
# half, so it escapes with EITHER of them and has to be decided some other way.
# Shared by the accessibility probe and the face classifier, which previously
# kept two independent copies of the same 0.01.
CLASSIFICATION_EPSILON = 0.01

# Two candidate pull axes closer than this |dot| are the same axis. 0.999 is
# about 2.6 deg, which is coarse enough to collapse the near-duplicate axes a
# STEP file produces for nominally coaxial features.
AXIS_DEDUP_DOT = 0.999

# Face normals within this |dot| of each other are treated as one direction
# when clustering dominant planar normals into candidate pull axes.
NORMAL_CLUSTER_DOT = 0.995

# General angular tolerance, radians (~0.57 deg). Used where an angle is
# compared directly rather than through a dot product.
ANGULAR_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Linear tolerances (millimetres — every part in this project is in mm)
# ---------------------------------------------------------------------------

# Ray hits closer than this to the ray origin are self-intersection and
# grazing artifacts, not blockers. Real molded walls are >= ~0.5 mm, so 0.1 mm
# is comfortably below any true obstruction.
MIN_HIT_DISTANCE = 0.1

# Ray origins are lifted this far along the surface normal so the ray starts
# outside the face it was cast from.
RAY_ORIGIN_OFFSET = 0.01

# General linear tolerance for "same point" / "zero length" decisions.
LINEAR_TOLERANCE = 1e-6

# Two edge endpoints within this distance are the same graph vertex. Looser
# than LINEAR_TOLERANCE on purpose: STEP endpoints that a kernel considers
# coincident routinely differ in the fifth decimal, and a parting loop that
# fails to close because of 1e-5 mm is a false negative.
EDGE_MATCH_TOLERANCE = 1e-4

# Edges shorter than this are numerical artifacts of a blend or a trim, not
# real boundary. They are dropped before the loop graph is built so they
# cannot introduce spurious branch points.
MIN_EDGE_LENGTH = 1e-3

# Faces below this area (mm^2) are slivers. They get their mold region from
# their neighbours rather than from their own samples, whose normals are
# unreliable at this scale.
SLIVER_FACE_AREA = 0.5


# ---------------------------------------------------------------------------
# Voting / aggregation thresholds
# ---------------------------------------------------------------------------

# A face is an undercut when at least this fraction of its surface samples are
# trapped. A simple majority: the face is more trapped than not.
UNDERCUT_FRACTION_THRESHOLD = 0.5

# A face counts as accessible from one side when at least this fraction of its
# samples can escape that way. Deliberately the same majority rule as above so
# that "accessible from neither side" and "is an undercut" cannot disagree.
ACCESS_FRACTION_THRESHOLD = 0.5

# Two parting-loop candidates whose scores are within this relative gap are
# reported as ambiguous rather than silently ranked.
AMBIGUITY_THRESHOLD = 0.05


# ---------------------------------------------------------------------------
# Coordinate rounding (graph keys)
# ---------------------------------------------------------------------------

# Decimal places used when a 3D point becomes a dict key. 4 places = 0.1 um,
# consistent with EDGE_MATCH_TOLERANCE.
COORD_KEY_DECIMALS = 4


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

# UV samples per direction by surface type. A plane's normal is constant, but
# its sample POSITIONS still matter for raycasting, hence 3x3 rather than 1.
# Curved faces carry normals spanning a wide arc and need the denser grid.
SAMPLE_GRID: Dict[str, int] = {
    "PLANE": 3,
    "CYLINDER": 5,
    "CONE": 5,
    "SPHERE": 5,
    "TORUS": 5,
    "BSPLINE": 5,
    "BEZIER": 5,
    "OTHER": 5,
}

MAX_SAMPLES_PER_FACE = 15

# Below this many samples a face's verdict is effectively a single-ray
# decision, so the sampler retries on a denser UV grid before giving up.
MIN_SAMPLES_PER_FACE = 4

# Samples per face during the direction sweep. The winner is re-checked at
# full resolution afterwards, so this only has to be good enough to rank.
SWEEP_SAMPLES_PER_FACE = 5

# Samples per face when probing internal features to pick the pull SIGN.
# Each sample costs three rays and the result is an area-weighted vote, so
# five is plenty.
SIGN_SAMPLES_PER_FACE = 5


# ---------------------------------------------------------------------------
# Analysis configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalysisConfig:
    """Tunable parameters for one analysis run.

    Defaults reproduce the engine's historical behaviour exactly, so any code
    path that passes `None` behaves as it did before this module existed.
    """

    # ── Sampling ──
    sampling_resolution: int = MAX_SAMPLES_PER_FACE
    sweep_samples_per_face: int = SWEEP_SAMPLES_PER_FACE
    min_samples_per_face: int = MIN_SAMPLES_PER_FACE

    # ── Tolerances ──
    angular_tolerance: float = ANGULAR_TOLERANCE
    linear_tolerance: float = LINEAR_TOLERANCE
    edge_match_tolerance: float = EDGE_MATCH_TOLERANCE
    classification_epsilon: float = CLASSIFICATION_EPSILON
    axis_dedup_dot: float = AXIS_DEDUP_DOT
    min_edge_length: float = MIN_EDGE_LENGTH
    sliver_face_area: float = SLIVER_FACE_AREA

    # ── Ray casting ──
    min_hit_distance: float = MIN_HIT_DISTANCE
    ray_origin_offset: float = RAY_ORIGIN_OFFSET

    # ── Aggregation ──
    undercut_fraction_threshold: float = UNDERCUT_FRACTION_THRESHOLD
    access_fraction_threshold: float = ACCESS_FRACTION_THRESHOLD
    ambiguity_threshold: float = AMBIGUITY_THRESHOLD

    # ── Direction search ──
    # 9 fixed axes (3 cartesian + 6 diagonals) plus geometry-derived axes.
    # Bosch's guidance is that +-X/Y/Z covers "90% of cases" and a 5-degree
    # sweep is explicitly not required, so the cap exists to bound the
    # geometry-derived tail, not to truncate the fixed set.
    max_candidate_directions: int = 16
    max_geometry_axes: int = 3

    # ── Parting line ──
    # Silhouette assistance is expensive and only matters when the
    # topological boundary fails validation, so it runs on demand rather
    # than on every part. See core/parting/silhouette.py.
    enable_silhouette: bool = True

    # Whether to evaluate every candidate direction exactly, or allow
    # branch-and-bound pruning (same winner, lower-bound losers).
    exact_candidates: bool = True

    def with_overrides(self, **kwargs) -> "AnalysisConfig":
        """Return a copy with the given fields replaced."""
        from dataclasses import replace
        return replace(self, **kwargs)


DEFAULT_CONFIG = AnalysisConfig()


def resolve(config: "AnalysisConfig | None") -> AnalysisConfig:
    """Normalise an optional config argument to a real one."""
    return config if config is not None else DEFAULT_CONFIG
