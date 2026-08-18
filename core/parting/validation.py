"""
core/parting/validation.py — Parting-line validation (specification section 12).

Every generated parting result is checked against three groups of conditions
and reduced to a set of quality metrics and one confidence number.

The rule that shapes this module: **confidence never hides a failure.** A
failed check is reported as a failed check. Confidence is computed from the
metrics and then CAPPED by the checks, so a result that is not closed, or that
leaves undercuts, cannot come back wearing a high number. The previous
implementation had one score doing both jobs, which is how a nozzle whose
parting line was an internal groove edge came back at 0.706 with nothing to
suggest anything was wrong.

Loop SELECTION is here too, and it is lexicographic for the same reason
direction selection is: a weighted sum lets a short, tidy, wrong loop buy off
its wrongness. The order is

    1. closed before open          steel with a gap is not a mold face
    2. no branch points            a parting line cannot fork
    3. separates both halves       it must actually divide core from cavity
    4. larger projected footprint  the outer rim, not an internal feature
    5. planar before wandering     a flat rim is the two-plate ideal
    6. shorter before longer       among equals, the cleaner line
    7. deterministic tie-break

Criterion 4 uses the loop's projected area against the part's TRUE silhouette
area rather than its bounding box. The bounding box made this ratio meaningless
for round parts: a circle inscribed in its own bounding square can never exceed
pi/4 = 0.785, so every circular rim scored 0.785 no matter how perfectly it
matched the part.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple  # noqa: F401

from core.accessibility import AccessibilityResult, MoldRegion
from core.models import FaceData
from core.parting.models import (
    EDGE_NON_MANIFOLD,
    EDGE_SHUTOFF,
    BoundaryEdge,
    PartingLoop,
    ValidationResult,
    Vector3,
    dot,
    norm,
    perpendicular_axes,
    polygon_area_2d,
)
from core.tolerances import AnalysisConfig, resolve


# ---------------------------------------------------------------------------
# Geometry measures
# ---------------------------------------------------------------------------

def projected_area(loop: PartingLoop, u: Vector3, v: Vector3) -> float:
    """Area the loop encloses when projected along the pull direction."""
    pts = loop.vertex_coords
    if len(pts) < 3:
        return 0.0
    return polygon_area_2d([(dot(p, u), dot(p, v)) for p in pts])


# Points per edge when measuring the part's projected outline. Dense on
# purpose: the hull of a sparsely sampled circle is an inscribed polygon, and
# an inscribed n-gon underestimates its circle by roughly (2*pi^2)/(3*n^2).
# At n=32 that is 0.6%, comfortably inside the tolerance the ratio is used at.
_SILHOUETTE_EDGE_SAMPLES = 32


def part_silhouette_area(
    faces: Sequence[FaceData], u: Vector3, v: Vector3, shape: Any = None
) -> float:
    """True projected area of the part, from the convex hull of its outline.

    Replaces the bounding-box estimate the previous implementation used, which
    overstated a round part's footprint by 4/pi and so capped every circular
    rim's outer-boundary ratio at 0.785 no matter how perfectly it matched the
    part.

    Points come from the shape's EDGES when a shape is available, not only
    from surface samples. Surface samples are sparse by design — five per
    direction on a curved face — and the hull of five points around a circle
    is a pentagon enclosing 73% of it, which understates the silhouette badly
    enough to push a correct rim's ratio well above 1. Edges tessellate
    cheaply and densely, and it is the edges that bound the outline anyway.
    """
    pts_2d: List[Tuple[float, float]] = []

    if shape is not None:
        try:
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS

            from core.parting.loops import edge_polyline

            explorer = TopExp_Explorer(shape, TopAbs_EDGE)
            while explorer.More():
                edge = TopoDS.Edge_s(explorer.Current())
                for p in edge_polyline(edge, _SILHOUETTE_EDGE_SAMPLES):
                    pts_2d.append((dot(p, u), dot(p, v)))
                explorer.Next()
        except Exception:
            pts_2d = []

    # Surface samples too: a face whose interior bulges past its own edges
    # (a sphere, a torus) contributes silhouette that no edge describes.
    for f in faces:
        for p in (f.sample_points or [f.center]):
            pts_2d.append((dot(p, u), dot(p, v)))

    return polygon_area_2d(_convex_hull(pts_2d))


def _convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Monotone-chain convex hull. Returns vertices in order."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out: List[Tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2:
                ax, ay = out[-2]
                bx, by = out[-1]
                if (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) > 0:
                    break
                out.pop()
            out.append(p)
        return out

    lower = half(pts)
    upper = half(reversed(pts))
    return lower[:-1] + upper[:-1]


# ---------------------------------------------------------------------------
# Per-loop metrics
# ---------------------------------------------------------------------------

def score_loop(
    loop: PartingLoop,
    faces_by_id: Dict[int, FaceData],
    u: Vector3,
    v: Vector3,
    part_area: float,
) -> None:
    """Fill in a loop's metric fields in place."""
    loop.projected_area = projected_area(loop, u, v)
    loop.outer_boundary_confidence = (
        min(1.0, loop.projected_area / part_area) if part_area > 0 else 0.0
    )

    adjacent = [faces_by_id[i] for i in loop.face_ids if i in faces_by_id]
    total_adj = sum(f.area for f in adjacent) or 1.0

    warn_adj = sum(f.area for f in adjacent if f.low_draft)
    loop.moldability_contribution = 1.0 - (warn_adj / total_adj)

    cavity_adj = sum(f.area for f in adjacent if f.mold_half == "cavity")
    core_adj = sum(f.area for f in adjacent if f.mold_half == "core")
    biggest = max(cavity_adj, core_adj)
    loop.separation_quality = (
        min(cavity_adj, core_adj) / biggest if biggest > 0 else 0.0
    )

    loop.simplicity = 1.0 / (1.0 + math.log2(max(loop.num_edges, 1)))
    loop.score = _display_score(loop)


def _display_score(loop: PartingLoop) -> float:
    """A 0..1 figure for the UI. Selection does not use it.

    Reported so a user can see how strongly one loop beat another, and
    weighted to agree with the lexicographic ordering in the ordinary case.
    An open or branching loop is floored near zero because it is not a
    manufacturable parting line at all, whatever else it scores.
    """
    if not loop.is_closed or loop.branch_points > 0:
        base = 0.15
    else:
        base = 1.0
    quality = (
        0.45 * loop.outer_boundary_confidence
        + 0.20 * loop.separation_quality
        + 0.15 * loop.moldability_contribution
        + 0.10 * loop.simplicity
        + 0.10 * (1.0 if loop.is_planar else 0.0)
    )
    return round(max(0.0, min(1.0, base * quality)), 4)


# ---------------------------------------------------------------------------
# Loop selection
# ---------------------------------------------------------------------------

def loop_sort_key(loop: PartingLoop) -> tuple:
    """Lexicographic ordering for parting loops. Lower is better."""
    return (
        0 if loop.is_closed else 1,
        loop.branch_points,
        0 if _separates_both_halves(loop) else 1,
        -round(loop.outer_boundary_confidence, 6),
        0 if loop.is_planar else 1,
        round(loop.loop_length, 6),
        # Deterministic final tie-break: never let traversal order decide.
        tuple(round(c, 6) for c in (loop.vertex_coords[0] if loop.vertex_coords else (0.0, 0.0, 0.0))),
    )


def _separates_both_halves(loop: PartingLoop) -> bool:
    """True when the loop genuinely has core on one side and cavity on the other."""
    return (
        MoldRegion.CORE.value in loop.separates
        and MoldRegion.CAVITY.value in loop.separates
    )


def rank_loops(loops: List[PartingLoop]) -> List[PartingLoop]:
    """Rank loops best-first and assign their 1-based candidate ids."""
    ordered = sorted(loops, key=loop_sort_key)
    for i, loop in enumerate(ordered, start=1):
        loop.candidate_id = i
        loop.is_selected = False
    if ordered:
        ordered[0].is_selected = True
    return ordered


def is_ambiguous(
    ranked: Sequence[PartingLoop], config: Optional[AnalysisConfig] = None
) -> bool:
    """True when the top two loops are too close to call.

    Compared on the outer-boundary ratio rather than the display score,
    because that ratio is an absolute measure of the part while the score
    mixes in terms that are only meaningful relative to the other candidates.
    """
    cfg = resolve(config)
    if len(ranked) < 2:
        return False
    best, second = ranked[0], ranked[1]
    if best.is_closed != second.is_closed:
        return False
    top = best.outer_boundary_confidence
    if top <= 0.0:
        return False
    return (top - second.outer_boundary_confidence) / top < cfg.ambiguity_threshold


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_parting_result(
    faces: Sequence[FaceData],
    pull_dir: Vector3,
    loops: Sequence[PartingLoop],
    open_chains: Sequence[PartingLoop],
    boundary: Sequence[BoundaryEdge],
    access: Optional[AccessibilityResult],
    undercut_regions: Sequence[Any] = (),
    config: Optional[AnalysisConfig] = None,
    tooling_plan: Any = None,
) -> ValidationResult:
    """Run every check and compute the quality metrics and confidence."""
    resolve(config)
    result = ValidationResult()
    primary = loops[0] if loops else None

    total_area = sum(f.area for f in faces) or 1.0
    undercut_area = sum(f.area for f in faces if f.is_undercut)
    delegated_area = sum(f.area for f in faces if getattr(f, 'is_delegated', False))
    actions = tooling_plan.resolve(faces) if tooling_plan else []

    # ── A. Topological validity ──
    result.add(
        "has_parting_line", "topological", primary is not None,
        "no core/cavity boundary was found for this pull direction"
        if primary is None else "",
    )
    result.add(
        "primary_loop_closed", "topological",
        bool(primary and primary.is_closed),
        "" if primary and primary.is_closed
        else "an open chain cannot form a mold face — it is solid steel",
    )
    result.add(
        "no_branch_points", "topological",
        bool(primary and primary.branch_points == 0),
        "" if not primary or primary.branch_points == 0
        else f"loop forks at {primary.branch_points} vertex/vertices; a parting "
             f"line cannot branch",
    )
    result.add(
        "no_open_chains", "topological", len(open_chains) == 0,
        "" if not open_chains
        else f"{len(open_chains)} boundary chain(s) did not close",
    )

    # ── B. Geometric validity ──
    non_manifold = [e for e in boundary if e.kind == EDGE_NON_MANIFOLD]
    result.add(
        "manifold_boundary", "geometric", not non_manifold,
        "" if not non_manifold
        else f"{len(non_manifold)} edge(s) are seams or non-manifold and were "
             f"excluded from the boundary",
    )
    result.add(
        "loop_has_geometry", "geometric",
        bool(primary and len(primary.vertex_coords) >= 3),
        "" if primary and len(primary.vertex_coords) >= 3
        else "primary loop has too few points to describe a curve",
    )
    # A loop whose footprint collapses to nothing is lying in a plane that
    # CONTAINS the pull direction. That is the clamshell case: the topological
    # boundary cannot express it, and silhouette assistance is what fixes it.
    degenerate = bool(primary and primary.outer_boundary_confidence < 0.05)
    result.add(
        "loop_footprint_non_degenerate", "geometric", not degenerate,
        "" if not degenerate
        else "primary loop encloses almost no area when projected along the "
             "pull — it lies in a plane containing the pull direction, so it "
             "cannot separate the two halves",
    )

    # ── C. Mold validity ──
    result.add(
        "separates_core_and_cavity", "mold",
        bool(primary and _separates_both_halves(primary)),
        "" if primary and _separates_both_halves(primary)
        else "primary loop does not have core on one side and cavity on the other",
    )
    shutoffs = [e for e in boundary if e.kind == EDGE_SHUTOFF]
    result.add(
        "no_undercuts_remaining", "mold", undercut_area <= 0.0,
        "" if undercut_area <= 0.0
        else f"{undercut_area:.1f} mm² ({100 * undercut_area / total_area:.1f}%) "
             f"remains trapped in {len(undercut_regions) or '?'} region(s); a "
             f"parting line cannot release an undercut — side action required",
    )
    # A zero reached by DELEGATION is not a zero reached by geometry. When
    # feature groups were handed to side actions, the checks above are about
    # the two main halves ONLY, and the price of that has to travel with the
    # result rather than being absorbed into a passing tick. This check is
    # informational -- it does not fail -- but its detail is what stops
    # "0 undercuts" from being read as "no tooling needed".
    if actions:
        axes = tooling_plan.action_axis_count()
        summary = "; ".join(
            f"{a['name']} → {a['mechanism']} along "
            f"({a['action_axis'][0]:.2f},{a['action_axis'][1]:.2f},{a['action_axis'][2]:.2f}) "
            f"[{a['face_count']} faces, {a['area']:.1f} mm²]"
            for a in actions
        )
        result.add(
            "side_actions_required", "mold", True,
            f"the two main halves are clean ONLY because {len(actions)} feature "
            f"group(s) totalling {delegated_area:.1f} mm² are formed by separate "
            f"tooling on {axes} additional axis/axes: {summary}",
        )

    # ── D. Quality metrics ──
    result.metrics = {
        "parting_line_length": primary.loop_length if primary else 0.0,
        "number_of_loops": float(len(loops)),
        "number_of_open_chains": float(len(open_chains)),
        "number_of_branch_points": float(primary.branch_points if primary else 0),
        "undercut_area_remaining": undercut_area,
        "undercut_fraction_remaining": undercut_area / total_area,
        "outer_boundary_ratio": primary.outer_boundary_confidence if primary else 0.0,
        "classification_confidence": _classification_confidence(faces, access),
        "delegated_area": delegated_area,
        "delegated_group_count": float(len(actions)),
        "required_action_axes": float(
            tooling_plan.action_axis_count() if tooling_plan else 0),
        "main_half_area": total_area,
        "main_half_area_fraction": (
            total_area / (total_area + delegated_area)
            if (total_area + delegated_area) > 0 else 0.0),
        "shutoff_edge_count": float(len(shutoffs)),
        "non_manifold_edge_count": float(len(non_manifold)),
    }
    result.required_actions = actions
    result.confidence = _confidence(result, primary)
    return result


def _classification_confidence(
    faces: Sequence[FaceData], access: Optional[AccessibilityResult]
) -> float:
    """How decisive the core/cavity call was, area-weighted, in [0, 1].

    A face whose samples voted unanimously contributes 1; one that split down
    the middle contributes 0. Ambiguous faces contribute nothing. This is a
    measure of the CLASSIFICATION, kept separate from the loop geometry so a
    tidy loop over a shaky classification cannot look confident.
    """
    if access is None:
        return 0.0
    total = 0.0
    weighted = 0.0
    for f in faces:
        entry = access.faces.get(f.face_id)
        if entry is None:
            continue
        total += f.area
        if entry.region == MoldRegion.AMBIGUOUS:
            continue
        # Distance from a 50/50 split of the reachability vote, rescaled to
        # [0, 1]: unanimous reads 1, evenly divided reads 0.
        margin = abs(entry.plus_fraction - entry.minus_fraction)
        if entry.region == MoldRegion.NEUTRAL:
            # Neutral is a definite answer about an indefinite surface; it is
            # correct but it carries no separating information.
            margin = 0.5
        weighted += f.area * min(1.0, margin)
    return weighted / total if total > 0 else 0.0


# Confidence ceilings imposed by specific failures. The lowest applicable
# ceiling wins, so a result that fails several checks cannot average its way
# back up.
_FAILURE_CEILINGS = {
    "has_parting_line": 0.0,
    "primary_loop_closed": 0.30,
    "loop_footprint_non_degenerate": 0.25,
    "separates_core_and_cavity": 0.30,
    "no_branch_points": 0.50,
    "loop_has_geometry": 0.10,
    "no_open_chains": 0.75,
    "no_undercuts_remaining": 0.85,
    "manifold_boundary": 0.90,
}


def _confidence(result: ValidationResult, primary: Optional[PartingLoop]) -> float:
    """Overall confidence, capped by whatever failed.

    Built from the quality metrics, then clamped to the tightest ceiling any
    failed check imposes. The clamping is the point: it is what stops a
    plausible-looking but unmanufacturable answer from being reported as a
    confident one.
    """
    if primary is None:
        return 0.0

    m = result.metrics
    base = (
        0.40 * m.get("outer_boundary_ratio", 0.0)
        + 0.25 * m.get("classification_confidence", 0.0)
        + 0.20 * (1.0 - min(1.0, m.get("undercut_fraction_remaining", 0.0) * 4.0))
        + 0.15 * (1.0 if primary.is_planar else 0.0)
    )

    ceiling = 1.0
    for check in result.failures:
        ceiling = min(ceiling, _FAILURE_CEILINGS.get(check.name, 0.95))

    return round(max(0.0, min(base, ceiling)), 4)
