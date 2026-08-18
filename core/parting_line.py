"""
core/parting_line.py — Public entry point for parting-line extraction.

The implementation now lives in the `core.parting` package, which follows the
pipeline the specification lays out: classify mold regions, extract the edges
where opposite regions meet, trace those into ordered loops, fall back to
silhouette curves where no edge can carry the split, then validate.

This module stays as the published surface. `find_parting_line`,
`find_all_parting_lines` and `compute_parting_line_result` keep their exact
signatures and return shapes, so `api.py`, `scripts/analyze_cli.py` and the
existing tests are unaffected — specification section 20 forbids breaking API
contracts without a migration, and there is no reason to force one here.

WHAT CHANGED BENEATH
--------------------
The previous implementation collected every edge where the two adjacent faces
had different mold halves, grouped those into connected components, and ranked
the components with a six-metric weighted score. Three things were wrong with
it and all three are fixed in the package:

  * Undercut faces have a mold half like any other face, so the outline of
    every trapped pocket was emitted as a parting candidate. On Part 3 that
    was 48 of 51 candidate edges. Those edges are now classified as SHUTOFFS
    and excluded (`core/parting/boundary.py`).

  * A connected component is not a loop. Components with a branch point, or
    containing two disjoint loops, were reported as a single open chain. The
    graph traversal in `core/parting/loops.py` decomposes them properly and
    counts branch points.

  * The weighted score let a tidy, short, wrong loop outrank a correct one,
    and its two heaviest terms were degenerate — projected area was
    normalised against the other candidates so the winner always scored 1.0
    on it, and outer-boundary confidence divided by a BOUNDING BOX, capping
    any circular rim at pi/4. Selection is now lexicographic against the true
    silhouette area (`core/parting/validation.py`).
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from core.accessibility import AccessibilityResult
from core.models import FaceData
from core.parting.analyzer import analyze_parting_line
from core.parting.models import (  # noqa: F401  (re-exported)
    BoundaryEdge,
    PartingLineResult,
    PartingLoop,
    ValidationCheck,
    ValidationResult,
)
from core.tolerances import AnalysisConfig

# The loop type used to be called CandidateLoop and carried a subset of these
# fields. Aliased rather than renamed so existing imports keep working.
CandidateLoop = PartingLoop


def find_all_parting_lines(
    shape: Any,
    faces: List[FaceData],
    pull_dir: Tuple[float, float, float],
    debug: bool = False,
    access: Optional[AccessibilityResult] = None,
    undercut_regions: Sequence[Any] = (),
    config: Optional[AnalysisConfig] = None,
    tooling_plan: Any = None,
) -> PartingLineResult:
    """Full parting-line analysis for one part and one pull direction.

    Args:
        shape:            TopoDS_Shape of the whole solid.
        faces:            FaceData with mold regions already assigned.
        pull_dir:         The chosen mold opening direction.
        debug:            Accepted for backward compatibility; all candidates
                          are always populated now, so it has no effect.
        access:           Accessibility result for `pull_dir`, when available.
                          Used for the classification-confidence metric.
        undercut_regions: Trapped features, reported alongside the result so
                          a caller cannot read the parting line without also
                          seeing what it does not solve.

    Returns:
        PartingLineResult with `primary_loop`, ranked `all_candidates`,
        `loops`, `open_chains`, `validation` and `confidence`.
    """
    return analyze_parting_line(
        shape=shape,
        faces=faces,
        pull_direction=pull_dir,
        access=access,
        undercut_regions=undercut_regions,
        config=config,
        tooling_plan=tooling_plan,
    )


def find_parting_line(
    shape: Any,
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    config: Optional[AnalysisConfig] = None,
) -> List[Any]:
    """Legacy API — the edges of the primary parting loop only.

    Kept because `AnalysisResult.parting_line_edges` is typed as a flat edge
    list and several tests read it. Prefer `find_all_parting_lines`, whose
    result carries the ordered polyline that a viewer should actually draw:
    a bare list of edges is precisely the "disconnected collection of edges"
    the specification says must not be presented as a parting line.
    """
    return find_all_parting_lines(
        shape, faces, mold_direction, config=config
    ).primary_loop.edges


def compute_parting_line_result(
    shape: Any,
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    access: Optional[AccessibilityResult] = None,
    undercut_regions: Sequence[Any] = (),
    config: Optional[AnalysisConfig] = None,
    tooling_plan: Any = None,
) -> PartingLineResult:
    """Convenience wrapper used by `api.py` and the CLI harness."""
    return find_all_parting_lines(
        shape, faces, mold_direction,
        access=access, undercut_regions=undercut_regions, config=config,
        tooling_plan=tooling_plan,
    )
