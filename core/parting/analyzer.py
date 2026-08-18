"""
core/parting/analyzer.py — Parting-line orchestration (specification section 17).

The pipeline, in the order the specification defines it:

    mold regions            (already classified upstream)
        |
    extract region boundaries       boundary.py
        |
    trace connected edge chains     loops.py
        |
    [silhouette assistance]         silhouette.py   -- only if the above fails
        |
    rank, validate, select          validation.py
        |
    PartingLineResult

The parting line is the OUTPUT of this chain, never an input to it. Nothing
here looks for an edge and then justifies the choice; edges become candidates
only because the faces on either side of them belong to opposite mold halves.

SILHOUETTE FALLBACK
-------------------
The topological path runs first and, on a part whose pull is along its
dominant axis, produces the answer on its own. It fails in one specific and
detectable way: when the pull runs ACROSS the part, the true split is a plane
containing the part axis, no B-rep edge lies on it, and every loop the
topological path can build has a projected footprint of essentially zero.

That is exactly what `loop_footprint_non_degenerate` checks, so the fallback
is triggered by a validation failure rather than by guessing in advance. When
it fires, silhouette curves are added to the candidate set and the loop
builder runs again; the better of the two results is kept, and the result
records which path produced it.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from core.accessibility import AccessibilityResult
from core.models import FaceData
from core.parting import boundary as boundary_mod
from core.parting import loops as loops_mod
from core.parting import silhouette as silhouette_mod
from core.parting import validation as validation_mod
from core.parting.models import (
    BoundaryEdge,
    PartingLineResult,
    PartingLoop,
    ValidationResult,
    Vector3,
    norm,
    perpendicular_axes,
)
from core.tolerances import AnalysisConfig, resolve


def _empty_loop() -> PartingLoop:
    """Placeholder primary loop for a part with no boundary at all.

    Returned rather than raising so a caller always gets a result object it
    can render and report on; validation marks it invalid with confidence 0.
    """
    return PartingLoop(candidate_id=1, is_selected=True, is_closed=False)


def _build(
    candidate: Sequence[BoundaryEdge],
    faces: Sequence[FaceData],
    pull_dir: Vector3,
    u: Vector3,
    v: Vector3,
    part_area: float,
    config: AnalysisConfig,
) -> Tuple[List[PartingLoop], List[PartingLoop]]:
    """Trace, score and rank one candidate edge set."""
    closed, open_chains, _graph = loops_mod.build_parting_loops(
        candidate, pull_dir, config
    )
    faces_by_id = {f.face_id: f for f in faces}
    for loop in list(closed) + list(open_chains):
        validation_mod.score_loop(loop, faces_by_id, u, v, part_area)
    return validation_mod.rank_loops(closed), validation_mod.rank_loops(open_chains)


def analyze_parting_line(
    shape: Any,
    faces: List[FaceData],
    pull_direction: Vector3,
    access: Optional[AccessibilityResult] = None,
    undercut_regions: Sequence[Any] = (),
    config: Optional[AnalysisConfig] = None,
    tooling_plan: Any = None,
) -> PartingLineResult:
    """Derive the parting line for a part and a chosen pull direction.

    `faces` must already carry their mold regions (see
    `core.face_classifier.classify_mold_regions`); this stage classifies
    edges, not faces.
    """
    cfg = resolve(config)
    pull_dir = norm(pull_direction)
    u, v = perpendicular_axes(pull_dir)
    part_area = validation_mod.part_silhouette_area(faces, u, v, shape)

    # ── Extract region boundaries ──
    boundary = boundary_mod.extract_region_boundaries(shape, faces, cfg)
    candidate = boundary_mod.candidate_edges(boundary, include_neutral=True)

    if candidate:
        closed, open_chains = _build(
            candidate, faces, pull_dir, u, v, part_area, cfg
        )
    else:
        closed, open_chains = [], []
    validation = validation_mod.validate_parting_result(
        faces, pull_dir, closed, open_chains, boundary, access,
        undercut_regions, cfg, tooling_plan,
    )

    # ── Silhouette assistance, only where the topology genuinely failed ──
    if cfg.enable_silhouette and _needs_silhouette(validation):
        alt = _with_silhouette(
            shape, faces, pull_dir, u, v, part_area, boundary, candidate,
            access, undercut_regions, cfg, tooling_plan,
        )
        if alt is not None:
            alt_loops, alt_open, alt_boundary, alt_validation = alt
            if _is_better(alt_validation, validation):
                closed, open_chains = alt_loops, alt_open
                boundary, validation = alt_boundary, alt_validation

    ranked = list(closed) + list(open_chains)
    primary = ranked[0] if ranked else _empty_loop()
    primary.is_selected = True

    return PartingLineResult(
        primary_loop=primary,
        all_candidates=ranked or [primary],
        pull_direction=pull_dir,
        is_ambiguous=validation_mod.is_ambiguous(closed, cfg),
        total_candidate_count=len(ranked),
        loops=closed,
        open_chains=open_chains,
        undercuts=list(undercut_regions),
        validation=validation,
        boundary_edges=boundary,
    )


# ---------------------------------------------------------------------------
# Silhouette fallback
# ---------------------------------------------------------------------------

# Failures that silhouette curves can actually repair. A part that fails only
# `no_undercuts_remaining`, say, has a perfectly good parting line and a real
# undercut; adding silhouette curves would not help and would risk replacing a
# correct answer with a noisier one.
_SILHOUETTE_REPAIRABLE = {
    "loop_footprint_non_degenerate",
    "has_parting_line",
    "separates_core_and_cavity",
    "primary_loop_closed",
}


def _needs_silhouette(validation: ValidationResult) -> bool:
    return any(c.name in _SILHOUETTE_REPAIRABLE for c in validation.failures)


def _with_silhouette(
    shape: Any,
    faces: List[FaceData],
    pull_dir: Vector3,
    u: Vector3,
    v: Vector3,
    part_area: float,
    boundary: List[BoundaryEdge],
    candidate: List[BoundaryEdge],
    access: Optional[AccessibilityResult],
    undercut_regions: Sequence[Any],
    cfg: AnalysisConfig,
    tooling_plan: Any = None,
):
    """Re-run loop building with silhouette curves added to the candidates."""
    sil_edges, unsupported = silhouette_mod.silhouette_boundary_edges(
        faces, pull_dir, cfg, shape=shape
    )
    if not sil_edges:
        return None

    # Keep only the topological edges that actually LIE IN the parting plane.
    #
    # A parting line lies in the parting surface, and in the clamshell case
    # that surface is the plane the silhouette curves were computed on. The
    # topological candidates that survive to this point do not: they are the
    # rims of features seen edge-on, circles standing perpendicular to the
    # plane that touch it at two points. Merging them in wholesale makes those
    # two points into branch vertices, and the branching tangle then outranks
    # the clean clamshell loop that the silhouette curves form on their own.
    #
    # Measured on the grooved cylinder: with all four topological circles
    # merged in, the graph gained 4 branch vertices and the primary loop came
    # back as a zero-area groove circle; restricted to the plane, the same
    # inputs give one closed 12-edge loop enclosing the full silhouette.
    plane_point = silhouette_mod._parting_plane_point(faces, pull_dir, shape)
    in_plane = [
        e for e in candidate
        if _lies_in_plane(e, pull_dir, plane_point)
    ]

    combined_boundary = list(boundary) + sil_edges
    combined_candidates = in_plane + sil_edges

    closed, open_chains = _build(
        combined_candidates, faces, pull_dir, u, v, part_area, cfg
    )
    validation = validation_mod.validate_parting_result(
        faces, pull_dir, closed, open_chains, combined_boundary, access,
        undercut_regions, cfg, tooling_plan,
    )
    if unsupported:
        validation.add(
            "silhouette_surfaces_supported", "geometric", False,
            f"{len(unsupported)} face(s) straddle the horizon on a surface type "
            f"whose silhouette is not computed exactly; the parting line across "
            f"them is approximate",
        )
        validation.confidence = min(validation.confidence, 0.6)
    return closed, open_chains, combined_boundary, validation


# How far a point may sit off the parting plane and still count as lying in
# it. Absolute, in mm, and far below any real feature — an edge either lies in
# the plane or it does not.
_PLANE_TOLERANCE = 1e-3


def _lies_in_plane(
    edge: BoundaryEdge, normal: Vector3, point: Vector3
) -> bool:
    """True when every sampled point of an edge lies in the given plane."""
    from core.parting.loops import edge_polyline
    from core.parting.models import dot

    offset = dot(point, normal)
    try:
        pts = edge_polyline(edge.edge, 8)
    except Exception:
        return False
    if not pts:
        return False
    return all(abs(dot(p, normal) - offset) <= _PLANE_TOLERANCE for p in pts)


def _is_better(candidate: ValidationResult, incumbent: ValidationResult) -> bool:
    """Whether a silhouette-assisted result should replace the topological one.

    Fewer failures wins; on a tie, higher confidence wins. Deliberately
    conservative: the topological result keeps the tie, because it is derived
    entirely from geometry the CAD file states outright, whereas silhouette
    curves are computed.
    """
    if len(candidate.failures) != len(incumbent.failures):
        return len(candidate.failures) < len(incumbent.failures)
    return candidate.confidence > incumbent.confidence
