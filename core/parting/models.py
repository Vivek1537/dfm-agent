"""
core/parting/models.py — Result objects for the parting-line pipeline.

`PartingLoop` deliberately carries the full field set of the old
`CandidateLoop` alongside the new topology fields, and `core/parting_line.py`
aliases the old name to it. That keeps `api.py`, the CLI harness and the
existing tests working unchanged (specification section 20: do not break API
contracts without a migration) while giving the new stages somewhere to put
branch counts, planarity and provenance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.accessibility import MoldRegion

Vector3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Boundary edges
# ---------------------------------------------------------------------------

# How an edge relates to the mold split. Only PARTING edges may form the
# parting line; the rest are classified so they can be reported and reasoned
# about rather than silently dropped.
EDGE_PARTING = "parting"                # separates CORE from CAVITY
EDGE_NEUTRAL_TRANSITION = "neutral"     # touches a NEUTRAL face; may join a loop
EDGE_SHUTOFF = "shutoff"                # borders an UNDERCUT region
EDGE_INTERIOR = "interior"              # both faces on the same half
EDGE_NON_MANIFOLD = "non_manifold"      # not exactly two adjacent faces
EDGE_DEGENERATE = "degenerate"          # below the minimum edge length


@dataclass
class BoundaryEdge:
    """One topological edge, classified against the mold-region map."""

    edge: Any                              # TopoDS_Edge
    kind: str
    length: float
    face_ids: Tuple[int, ...] = ()
    regions: Tuple[MoldRegion, ...] = ()
    # The mold HALF of each adjacent face. Distinct from `regions`: a NEUTRAL
    # face has no region of its own but is still formed by one half, and it is
    # the halves that a parting line separates. Recording both is what lets an
    # edge be classified on regions while the loop is judged on halves.
    halves: Tuple[str, ...] = ()
    source: str = "topology"               # "topology" | "silhouette"

    @property
    def is_candidate(self) -> bool:
        """True when this edge may take part in a parting loop."""
        return self.kind in (EDGE_PARTING, EDGE_NEUTRAL_TRANSITION)


# ---------------------------------------------------------------------------
# Loops
# ---------------------------------------------------------------------------

@dataclass
class PartingLoop:
    """One connected chain of boundary edges, ordered end to end.

    The first block of fields is the historical `CandidateLoop` contract and
    must keep its names and meanings; the second block is new.
    """

    # ── legacy contract ──
    candidate_id: int                                # 1-indexed, ranked
    edges: List[Any] = field(default_factory=list)   # List[TopoDS_Edge]
    score: float = 0.0                               # overall score [0, 1]
    projected_area: float = 0.0                      # 2D footprint, mm²
    loop_length: float = 0.0                         # perimeter, mm
    outer_boundary_confidence: float = 0.0           # [0, 1]
    moldability_contribution: float = 0.0            # [0, 1]
    simplicity: float = 0.0                          # [0, 1]
    separation_quality: float = 0.0                  # [0, 1]
    num_edges: int = 0
    is_selected: bool = False                        # True = primary parting line
    is_closed: bool = True
    vertex_coords: List[Vector3] = field(default_factory=list)

    # ── topology (new) ──
    # Vertices where three or more candidate edges meet. A parting line
    # cannot branch: steel has one surface, not a Y-junction.
    branch_points: int = 0
    # Loop lies in a plane perpendicular to the pull axis, within tolerance.
    is_planar: bool = False
    # Spread of the loop along the pull axis, mm. Zero for a flat rim.
    axial_spread: float = 0.0
    # Face ids the loop borders, and which regions it actually separates.
    face_ids: Tuple[int, ...] = ()
    separates: Tuple[str, ...] = ()
    # "topology" when built from B-rep edges, "silhouette" when the loop
    # needed silhouette curves that no existing edge provided.
    source: str = "topology"
    # How much of the loop's length is SHUTOFF rather than main parting line —
    # the stretch where a side core or slider, not the two main halves, forms
    # the surface. Non-zero means the loop is only closed because a side action
    # closes it, which is a tooling fact the result must state rather than
    # absorb into a length figure.
    shutoff_length: float = 0.0

    @property
    def loop_id(self) -> int:
        return self.candidate_id

    @property
    def points(self) -> List[Vector3]:
        """Ordered polyline along the loop — what a viewer should draw."""
        return self.vertex_coords

    def __repr__(self) -> str:
        tag = " [PRIMARY]" if self.is_selected else ""
        closed = "closed" if self.is_closed else "OPEN"
        branch = f" branches={self.branch_points}" if self.branch_points else ""
        return (
            f"Loop-{self.candidate_id:02d}{tag}  "
            f"score={self.score:.3f}  area={self.projected_area:.1f}  "
            f"edges={self.num_edges}  length={self.loop_length:.1f}  "
            f"{closed}{branch}"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationCheck:
    """One named pass/fail check with a human-readable reason."""

    name: str
    category: str            # "topological" | "geometric" | "mold"
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class ValidationResult:
    """Outcome of validating one parting-line result.

    `confidence` is derived from the metrics, but `is_valid` is not derived
    from `confidence`: a failed check is reported as a failure regardless of
    how good the numbers look elsewhere. Specification section 12: "do not
    hide failure conditions behind a high score."
    """

    checks: List[ValidationCheck] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    # Feature groups a declared tooling plan hands to side actions. Non
    # empty means the checks above describe the two MAIN HALVES only, and
    # this list is the price of that. Callers must show it wherever they
    # show the undercut count.
    required_actions: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> List[ValidationCheck]:
        return [c for c in self.checks if not c.passed]

    def add(self, name: str, category: str, passed: bool, detail: str = "") -> None:
        self.checks.append(ValidationCheck(name, category, passed, detail))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 4),
            "checks": [c.to_dict() for c in self.checks],
            "failures": [c.name for c in self.failures],
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "required_actions": self.required_actions,
            "requires_side_actions": bool(self.required_actions),
        }


# ---------------------------------------------------------------------------
# Top-level result
# ---------------------------------------------------------------------------

@dataclass
class PartingLineResult:
    """Complete parting-line analysis for one part and one pull direction.

    The first five fields are the historical contract consumed by `api.py`,
    `scripts/analyze_cli.py` and the test suite. Everything below them is new
    and additive.
    """

    # ── legacy contract ──
    primary_loop: PartingLoop
    all_candidates: List[PartingLoop]
    pull_direction: Vector3
    is_ambiguous: bool
    total_candidate_count: int

    # ── new ──
    loops: List[PartingLoop] = field(default_factory=list)        # closed only
    open_chains: List[PartingLoop] = field(default_factory=list)
    undercuts: List[Any] = field(default_factory=list)            # UndercutRegion
    validation: Optional[ValidationResult] = None
    boundary_edges: List[BoundaryEdge] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return self.validation.confidence if self.validation else 0.0

    @property
    def is_valid(self) -> bool:
        return bool(self.validation and self.validation.is_valid)

    def to_dict(self) -> Dict[str, Any]:
        """API-facing summary. Geometry is tessellated by the caller."""
        return {
            "pull_direction": [round(c, 6) for c in self.pull_direction],
            "loop_count": len(self.loops),
            "open_chain_count": len(self.open_chains),
            "total_candidates": self.total_candidate_count,
            "is_ambiguous": self.is_ambiguous,
            "confidence": round(self.confidence, 4),
            "validation": self.validation.to_dict() if self.validation else None,
        }


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------

def dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(v: Vector3) -> Vector3:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def perpendicular_axes(pull_dir: Vector3) -> Tuple[Vector3, Vector3]:
    """Two orthogonal unit vectors spanning the plane normal to `pull_dir`."""
    seed = (1.0, 0.0, 0.0) if abs(pull_dir[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = norm(cross(pull_dir, seed))
    v = norm(cross(pull_dir, u))
    return u, v


def polygon_area_2d(points_2d: List[Tuple[float, float]]) -> float:
    """Shoelace area of an ORDERED polygon. Valid for non-convex outlines."""
    n = len(points_2d)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        j = (i + 1) % n
        total += points_2d[i][0] * points_2d[j][1]
        total -= points_2d[j][0] * points_2d[i][1]
    return abs(total) / 2.0
