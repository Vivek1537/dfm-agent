"""Topology regression tests for the main parting line.

The earlier regression checks only asserted the pull sign, the undercut count
and that the primary loop was *closed*. All three stayed green while the Part 1
parting line silently moved off the flat rim and started climbing the snap
windows, so the visible topology regressed undetected.

These tests assert the geometric SHAPE of the selected loop instead. They are
written against invariants (planarity perpendicular to the pull, footprint
relative to the part) rather than face ids or literal coordinates, so they keep
working if the model is re-exported or the coordinate system changes.
"""

import math
import os

import cadquery as cq
import pytest

from core.analyzer import analyze_part
from core.parting_line import compute_parting_line_result

ASSETS = os.path.join(os.path.dirname(__file__), os.pardir, "assets")
PART1 = os.path.abspath(os.path.join(ASSETS, "Part1.stp"))


def _loop_points(loop):
    """Sample every edge of a loop into 3D points."""
    points = []
    for edge in loop.edges:
        curve = cq.Edge(edge)
        points.extend(curve.positionAt(t / 10.0) for t in range(11))
    return points


def _spread_along(points, axis):
    """Extent of a point set measured along a unit axis."""
    projections = [p.x * axis[0] + p.y * axis[1] + p.z * axis[2] for p in points]
    return max(projections) - min(projections)


@pytest.fixture(scope="module")
def part1():
    result = analyze_part(PART1, "Part1.stp")
    parting_line = compute_parting_line_result(
        result.raw_shape, result.faces, result.best_mold_direction
    )
    return result, parting_line


def test_part1_primary_loop_is_closed(part1):
    _, parting_line = part1
    assert parting_line.primary_loop.is_closed, (
        "an open chain cannot form solid steel — it is not manufacturable"
    )


def test_part1_primary_loop_is_planar_perpendicular_to_pull(part1):
    """The main parting line must sit in a plane normal to the pull direction.

    This is the assertion the previous suite lacked. A loop that detours up and
    over the snap-window shutoffs spreads along the pull axis; the flat rim does
    not. Measured against the part's own extent so it stays scale-independent.
    """
    result, parting_line = part1
    pull = result.best_mold_direction

    loop_spread = _spread_along(_loop_points(parting_line.primary_loop), pull)

    face_points = [
        cq.Vector(*point)
        for face in result.faces
        for point in (face.sample_points or [face.center])
    ]
    part_extent = _spread_along(face_points, pull)

    assert part_extent > 0
    assert loop_spread <= 0.10 * part_extent, (
        f"primary loop wanders {loop_spread:.2f} mm along the pull axis "
        f"({loop_spread / part_extent:.0%} of the part's {part_extent:.2f} mm "
        "extent) — it is detouring around side features instead of following "
        "the main rim"
    )


def test_part1_primary_loop_encloses_the_outer_silhouette(part1):
    """The main loop must be the outer rim, not a small feature loop.

    Guards the other half of the failure mode: a loop can be perfectly planar
    and still be a tiny lug or boss outline.
    """
    result, parting_line = part1
    pull = result.best_mold_direction

    # Cross-section of the part perpendicular to the pull direction.
    seed = (1.0, 0.0, 0.0) if abs(pull[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = cq.Vector(*pull).cross(cq.Vector(*seed)).normalized()
    v = cq.Vector(*pull).cross(u).normalized()

    face_points = [
        cq.Vector(*point)
        for face in result.faces
        for point in (face.sample_points or [face.center])
    ]
    width = _spread_along(face_points, (u.x, u.y, u.z))
    depth = _spread_along(face_points, (v.x, v.y, v.z))
    cross_section = width * depth

    assert cross_section > 0
    assert parting_line.primary_loop.projected_area >= 0.5 * cross_section, (
        f"primary loop encloses {parting_line.primary_loop.projected_area:.1f} mm² "
        f"of a {cross_section:.1f} mm² cross-section — too small to be the main "
        "parting line"
    )


def test_part1_has_no_undercuts(part1):
    """Bosch stated the optimal solution for Part 1 has zero undercuts."""
    result, _ = part1
    assert result.undercut_face_count == 0


def test_synthetic_cup_outer_wall_stays_cavity():
    """Ground-truth guard for the ambiguous-wall tie fallback.

    A plain shell's outer wall is reachable from both halves and its shared
    boundary is exactly equal on both sides, so it exercises the tie path in
    `_resolve_ambiguous_regions`. The mentor's rule for a cup is
    concave→core / convex→cavity.
    """
    cup = cq.Workplane("XY").circle(30).extrude(80).faces(">Z").shell(-3)
    path = os.path.join(os.path.dirname(__file__), "_cup_tmp.step")
    cq.exporters.export(cup, path)
    try:
        result = analyze_part(path, "cup.step")
    finally:
        os.unlink(path)

    cylinders = sorted(
        (f for f in result.faces if f.surface_type == "CYLINDER" and f.area > 1000),
        key=lambda f: f.area,
    )
    inner_wall, outer_wall = cylinders[0], cylinders[-1]

    assert outer_wall.mold_half == "cavity", "convex outer wall must be cavity"
    assert inner_wall.mold_half == "core", "concave inner wall must be core"
    assert result.undercut_face_count == 0
