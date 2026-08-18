"""
core/parting — Geometry-driven parting-line generation.

The parting line is derived from mold accessibility and region classification,
never from edge selection. Reading order:

    models.py       result objects shared by the stages
    boundary.py     which edges separate which mold regions
    loops.py        edge graph, traversal, ordered closed loops
    silhouette.py   horizon curves, for pulls that cross the part axis
    validation.py   topological / geometric / mold checks, ranking, confidence
    analyzer.py     orchestration

Upstream of this package, in `core/`: `pull_direction.py` generates candidate
axes, `accessibility.py` measures what each half can reach, and
`direction_evaluation.py` picks the axis. Those three are not parting-specific
-- draft analysis and undercut-region grouping use them too -- which is why
they sit outside.
"""

from core.parting.models import (  # noqa: F401
    BoundaryEdge,
    PartingLineResult,
    PartingLoop,
    ValidationCheck,
    ValidationResult,
)
from core.parting.analyzer import analyze_parting_line  # noqa: F401

__all__ = [
    "analyze_parting_line",
    "BoundaryEdge",
    "PartingLineResult",
    "PartingLoop",
    "ValidationCheck",
    "ValidationResult",
]
