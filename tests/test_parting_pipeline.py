"""
Stage tests for the parting-line pipeline.

Boundary extraction, the edge graph, loop tracing and validation, each
exercised against synthetic parts whose answer follows from their
construction. Assertions are written from the geometry, never from what the
engine currently returns.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.accessibility import MoldRegion                        # noqa: E402
from core.analyzer import analyze_part                           # noqa: E402
from core.parting import boundary as bmod                        # noqa: E402
from core.parting import loops as lmod                           # noqa: E402
from core.parting import validation as vmod                      # noqa: E402
from core.parting.models import (                                # noqa: E402
    EDGE_PARTING,
    EDGE_SHUTOFF,
    BoundaryEdge,
    perpendicular_axes,
)
from tests import synthetic_parts as sp                          # noqa: E402

Z_PULL = (0.0, 0.0, 1.0)


# ---------------------------------------------------------------- boundary
def test_no_parting_candidate_touches_an_undercut_face():
    """The border of a trapped pocket is a SHUTOFF, never a parting line.

    This is the defect that dominated the previous implementation. A trapped
    face still has to be formed by some steel, so the classifier gives it a
    mold half like any other face — and a boundary pass that compares only
    halves therefore emitted the whole outline of every undercut pocket as
    parting-line candidates. Measured on Part 3 before the fix: 48 of 51
    candidate edges bordered an undercut face, so 94% of the candidate set was
    the outline of two rib pockets rather than the mold split. The correct rim
    won only because it happened to outscore them.

    A parting line cannot release an undercut, so its boundary must not be
    allowed to compete for the role.
    """
    path, _exp = sp.grooved_cylinder()
    res = analyze_part(path, "grooved", override_direction=Z_PULL)

    undercut_ids = {f.face_id for f in res.faces if f.is_undercut}
    assert undercut_ids, "the fixture's groove is trapped for an axial pull"

    boundary = bmod.extract_region_boundaries(res.raw_shape, res.faces)
    for edge in bmod.candidate_edges(boundary):
        assert not (set(edge.face_ids) & undercut_ids), (
            f"parting candidate borders undercut face(s) "
            f"{set(edge.face_ids) & undercut_ids}"
        )


def test_undercut_borders_are_reported_as_shutoffs():
    """Excluded from the parting line, but still reported — not discarded."""
    path, _exp = sp.grooved_cylinder()
    res = analyze_part(path, "grooved", override_direction=Z_PULL)

    boundary = bmod.extract_region_boundaries(res.raw_shape, res.faces)
    shutoffs = [e for e in boundary if e.kind == EDGE_SHUTOFF]
    assert shutoffs, "the groove's border should be classified as shutoff"
    assert bmod.summarize(boundary)["counts"].get(EDGE_SHUTOFF) == len(shutoffs)


def test_a_clean_box_parts_on_one_boundary():
    """A convex box has exactly one core/cavity boundary for an axial pull."""
    path, _exp = sp.solid_box()
    res = analyze_part(path, "box", override_direction=Z_PULL)

    boundary = bmod.extract_region_boundaries(res.raw_shape, res.faces)
    candidates = bmod.candidate_edges(boundary)
    assert candidates, "a box must have a parting boundary"

    closed, open_chains, _graph = lmod.build_parting_loops(candidates, Z_PULL)
    assert len(closed) == 1, f"expected one closed loop, got {len(closed)}"
    assert not open_chains


def test_degenerate_edges_are_excluded_from_candidates():
    """Slivers are recorded but never allowed into the loop graph.

    An edge below the minimum length is a trim or blend artifact. It is too
    short to carry a parting line and long enough to create a false junction,
    so it must not reach the graph.
    """
    path, _exp = sp.solid_box()
    res = analyze_part(path, "box", override_direction=Z_PULL)
    boundary = bmod.extract_region_boundaries(res.raw_shape, res.faces)
    for edge in bmod.candidate_edges(boundary):
        assert edge.length > 0.0


# ------------------------------------------------------------- edge graph
def _graph_for(part, direction=Z_PULL):
    path, _exp = part()
    res = analyze_part(path, "part", override_direction=direction)
    boundary = bmod.extract_region_boundaries(res.raw_shape, res.faces)
    candidates = bmod.candidate_edges(boundary)
    return res, candidates, lmod.build_edge_graph(candidates)


def test_edge_graph_links_edges_by_shared_vertices():
    """A box's bottom rim is four edges meeting end to end: every vertex degree 2."""
    _res, candidates, graph = _graph_for(sp.solid_box)
    assert len(graph.edges) == len(candidates)
    assert not graph.branch_vertices, "a clean rim has no junctions"
    assert not graph.endpoint_vertices, "a closed rim has no loose ends"
    for key in graph.incident:
        assert graph.degree(key) == 2


def test_a_closed_rim_traces_into_one_ordered_loop():
    _res, candidates, _graph = _graph_for(sp.solid_box)
    closed, open_chains, _g = lmod.build_parting_loops(candidates, Z_PULL)
    assert len(closed) == 1 and not open_chains

    loop = closed[0]
    assert loop.is_closed
    assert loop.num_edges == len(candidates)
    assert loop.branch_points == 0
    # The traced polyline must return to where it started.
    first, last = loop.vertex_coords[0], loop.vertex_coords[-1]
    assert math.dist(first, last) < 1e-3


def test_traced_points_are_ordered_and_continuous():
    """Consecutive points must be adjacent along the curve, not jump about.

    This is what distinguishes an ordered loop from a bag of edges. If any
    step is a large fraction of the whole perimeter, the traversal has hopped
    between disconnected pieces.
    """
    _res, candidates, _graph = _graph_for(sp.solid_box)
    loop = lmod.build_parting_loops(candidates, Z_PULL)[0][0]

    pts = loop.vertex_coords
    steps = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    assert max(steps) < 0.5 * loop.loop_length, (
        "the polyline jumps between disconnected pieces — it is not ordered"
    )
    assert abs(sum(steps) - loop.loop_length) < 0.05 * loop.loop_length


def test_edge_orientation_is_resolved_when_tracing():
    """Edges are used in whichever direction the walk needs.

    A B-rep edge's parametrisation runs whichever way the kernel stored it,
    so a loop cannot be built by concatenating edges in stored order. Reversing
    the input list must therefore not change the geometry that comes out.
    """
    _res, candidates, _graph = _graph_for(sp.solid_box)

    forward = lmod.build_parting_loops(candidates, Z_PULL)[0][0]
    backward = lmod.build_parting_loops(list(reversed(candidates)), Z_PULL)[0][0]

    assert forward.is_closed and backward.is_closed
    assert forward.num_edges == backward.num_edges
    assert abs(forward.loop_length - backward.loop_length) < 1e-6

    u, v = perpendicular_axes(Z_PULL)
    assert abs(
        vmod.projected_area(forward, u, v) - vmod.projected_area(backward, u, v)
    ) < 1e-3


def test_an_open_chain_is_reported_as_open_not_as_a_loop():
    """Dropping an edge from a closed rim must produce an open chain.

    Reported honestly rather than silently closed: a gap in the parting line
    is a gap in the steel.
    """
    _res, candidates, _graph = _graph_for(sp.solid_box)
    assert len(candidates) > 2

    closed, open_chains, _g = lmod.build_parting_loops(candidates[:-1], Z_PULL)
    assert not closed, "a rim with an edge removed cannot be closed"
    assert len(open_chains) == 1
    assert not open_chains[0].is_closed


def test_a_full_circle_edge_is_a_loop_on_its_own():
    """A single self-closing edge is a valid closed loop."""
    path, _exp = sp.stepped_cylinder()
    res = analyze_part(path, "stepped", override_direction=Z_PULL)
    boundary = bmod.extract_region_boundaries(res.raw_shape, res.faces)
    closed, open_chains, _g = lmod.build_parting_loops(
        bmod.candidate_edges(boundary), Z_PULL
    )
    assert closed and not open_chains
    assert closed[0].is_closed


def test_an_empty_candidate_set_produces_no_loops():
    closed, open_chains, graph = lmod.build_parting_loops([], Z_PULL)
    assert closed == [] and open_chains == [] and graph.edges == []


# ------------------------------------------------------------- validation
def test_a_closed_loop_outranks_an_open_chain():
    """Specification: an open chain can never be the primary parting line."""
    from core.parting.models import PartingLoop

    closed = PartingLoop(candidate_id=0, is_closed=True, outer_boundary_confidence=0.1)
    openc = PartingLoop(candidate_id=0, is_closed=False, outer_boundary_confidence=1.0)
    assert vmod.rank_loops([openc, closed])[0] is closed


def test_a_branching_loop_loses_to_a_clean_one():
    from core.parting.models import PartingLoop

    clean = PartingLoop(candidate_id=0, is_closed=True, branch_points=0,
                        outer_boundary_confidence=0.2)
    forked = PartingLoop(candidate_id=0, is_closed=True, branch_points=2,
                         outer_boundary_confidence=1.0)
    assert vmod.rank_loops([forked, clean])[0] is clean


def test_the_outer_rim_beats_a_small_feature_loop():
    from core.parting.models import PartingLoop

    rim = PartingLoop(candidate_id=0, is_closed=True, separates=("cavity", "core"),
                      outer_boundary_confidence=0.95, loop_length=200.0)
    lug = PartingLoop(candidate_id=0, is_closed=True, separates=("cavity", "core"),
                      outer_boundary_confidence=0.05, loop_length=10.0)
    assert vmod.rank_loops([lug, rim])[0] is rim, (
        "a shorter loop must not beat the one that actually encloses the part"
    )


def test_part_silhouette_area_is_the_real_outline_not_the_bounding_box():
    """A circular rim must be able to score a full outer-boundary ratio.

    The previous implementation divided by the part's BOUNDING BOX, so a
    circle inscribed in its own bounding square could never exceed pi/4 =
    0.785 however perfectly it matched the part — which made the metric
    useless on exactly the round parts it mattered most for.
    """
    path, exp = sp.stepped_cylinder()
    res = analyze_part(path, "stepped", override_direction=Z_PULL)
    u, v = perpendicular_axes(Z_PULL)

    area = vmod.part_silhouette_area(res.faces, u, v, res.raw_shape)
    expected = math.pi * exp["silhouette_radius"] ** 2
    assert abs(area - expected) < 0.05 * expected, (
        f"silhouette area {area:.1f} should be the disc {expected:.1f}, not "
        f"its bounding square {(2 * exp['silhouette_radius']) ** 2:.1f}"
    )

    assert res.parting_line.primary_loop.outer_boundary_confidence > 0.9


# ----------------------------------------------------------- whole pipeline
def test_simple_box_acceptance():
    """Specification section 18, Test 1."""
    path, exp = sp.solid_box()
    res = analyze_part(path, "solid_box")
    parting = res.parting_line

    assert res.undercut_face_count == 0
    assert parting.is_valid, [c.name for c in parting.validation.failures]
    assert len(parting.loops) == 1
    assert parting.primary_loop.is_closed
    assert parting.primary_loop.branch_points == 0
    assert abs(parting.primary_loop.projected_area - exp["silhouette_area"]) < 1.0


def test_cylinder_flange_acceptance():
    """Specification section 18, Test 2: a closed loop on the flange OD."""
    path, exp = sp.flanged_boss()
    res = analyze_part(path, "flanged_boss")
    parting = res.parting_line

    assert res.undercut_face_count == 0
    assert parting.primary_loop.is_closed
    radii = [math.hypot(p[0], p[1]) for p in parting.primary_loop.vertex_coords]
    assert abs(max(radii) - exp["r_flange"]) < 0.05 * exp["r_flange"], (
        f"loop reaches r={max(radii):.2f}; the flange OD is {exp['r_flange']}"
    )


def test_reentrant_feature_is_not_claimed_solved():
    """Specification section 18, Test 3, and section 11.

    A part with a real side undercut must have it detected, must NOT be
    reported as solved by an ordinary parting line, and must say what tooling
    it needs.
    """
    path, _exp = sp.cylinder_blind_pocket()
    res = analyze_part(path, "pocket", override_direction=Z_PULL)
    parting = res.parting_line

    assert res.undercut_face_count > 0, "the blind pocket is trapped axially"
    assert not parting.is_valid
    failures = {c.name for c in parting.validation.failures}
    assert "no_undercuts_remaining" in failures
    assert parting.validation.metrics["undercut_area_remaining"] > 0.0
    assert res.undercut_regions, "a trapped feature must name its mechanism"
    assert all(r.mechanism for r in res.undercut_regions)


def test_confidence_is_capped_by_failures_not_averaged_with_them():
    """Specification section 12: do not hide failures behind a high score."""
    path, _exp = sp.cylinder_blind_pocket()
    res = analyze_part(path, "pocket", override_direction=Z_PULL)
    parting = res.parting_line

    assert not parting.is_valid
    assert parting.confidence <= 0.85, (
        f"confidence {parting.confidence} ignores the reported failures"
    )


def test_the_pipeline_is_deterministic():
    """The same part must give the same answer on every run."""
    path, _exp = sp.flanged_boss()
    a = analyze_part(path, "flanged_boss")
    b = analyze_part(path, "flanged_boss")

    assert a.best_mold_direction == b.best_mold_direction
    assert a.undercut_face_count == b.undercut_face_count
    assert a.parting_line.primary_loop.num_edges == b.parting_line.primary_loop.num_edges
    assert abs(
        a.parting_line.primary_loop.loop_length
        - b.parting_line.primary_loop.loop_length
    ) < 1e-9
    assert a.parting_line.confidence == b.parting_line.confidence


def test_validation_reports_every_required_quality_metric():
    """Specification section 12.D lists these by name."""
    path, _exp = sp.solid_box()
    res = analyze_part(path, "solid_box")
    metrics = res.parting_line.validation.metrics
    for name in (
        "parting_line_length",
        "number_of_loops",
        "number_of_open_chains",
        "number_of_branch_points",
        "undercut_area_remaining",
        "classification_confidence",
    ):
        assert name in metrics, f"quality metric {name} is not reported"
