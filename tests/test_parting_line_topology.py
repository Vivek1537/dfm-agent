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


# --------------------------------------------------------------- area totals
def test_area_fields_are_populated_and_consistent():
    """Areas must be reported, and must agree with the face counts.

    The five area fields existed on AnalysisResult but nothing filled them, so
    /analyze returned {"core": 0.0, "cavity": 0.0, "total": 0.0} and the UI's
    area-led bars rendered from zeros while the counts looked fine. Assert the
    totals are non-zero and that every class with faces also has area, which is
    what a silent regression would break.
    """

    res = analyze_part(PART1, "Part1")

    assert res.total_area > 0.0, "total_area is zero — areas are not populated"
    assert abs(res.total_area - sum(f.area for f in res.faces)) < 1e-6

    parts = res.core_area + res.cavity_area + res.undercut_area
    assert abs(parts - res.total_area) < 1e-3, (
        f"core+cavity+undercut ({parts:.3f}) must cover the whole surface "
        f"({res.total_area:.3f}); the three classifications are exhaustive"
    )

    for count, area, label in (
        (res.core_face_count, res.core_area, "core"),
        (res.cavity_face_count, res.cavity_area, "cavity"),
        (res.undercut_face_count, res.undercut_area, "undercut"),
        (res.warning_face_count, res.warning_area, "warning"),
    ):
        assert (count > 0) == (area > 0.0), (
            f"{label}: {count} faces but {area} mm² — counts and areas disagree"
        )


# ---------------------------------------------------- P12 nozzle (customer answer)
#
# The only fixture whose expected answer comes from Bosch rather than from our
# own construction: on the Phase 1 review call the reviewer drew this nozzle and
# stated that an axial (Z) pull traps the O-ring groove, so the pull is taken
# perpendicular to the part axis, the parting plane contains that axis, and a
# side core forms the bore.

def _nozzle():
    from tests import synthetic_parts as sp
    return sp.oring_nozzle()


def test_nozzle_pull_is_perpendicular_to_the_part_axis():
    """An axial draw cannot release a 360° external groove, at any PL height."""
    path, exp = _nozzle()
    res = analyze_part(path, "oring_nozzle")

    axis = exp["part_axis"]
    along = abs(sum(a * b for a, b in zip(res.best_mold_direction, axis)))
    assert along < 0.1, (
        f"pull {res.best_mold_direction} runs along the part axis {axis}; the "
        f"circumferential groove makes that a trapped draw — the reviewer's "
        f"answer is a perpendicular pull"
    )


def test_nozzle_bore_is_released_by_an_axial_side_core():
    """"the internal wall will be formed by a side core" — and it runs axially."""
    path, exp = _nozzle()
    res = analyze_part(path, "oring_nozzle")

    assert res.undercut_regions, "no side action proposed for the bore"
    axis = exp["part_axis"]
    for region in res.undercut_regions:
        direction = region.to_dict().get("side_action_direction")
        assert direction, "region carries no side-action direction"
        along = abs(sum(a * b for a, b in zip(direction, axis)))
        assert along > 0.9, (
            f"side core pulls {direction}; the bore is released along the part "
            f"axis {axis}"
        )


def test_nozzle_parting_line_contains_the_part_axis():
    """The clamshell split: the loop must span the part along its own axis.

    Was an expected failure until silhouette assistance existed. A pull
    perpendicular to the part axis splits it like a clamshell, and that plane
    passes through the middle of the outer wall where the B-rep has no edge at
    all — so no amount of edge selection could produce it, and the engine
    returned a circle perpendicular to the axis, which cannot part the halves.
    `core/parting/silhouette.py` computes the horizon curves the split needs.
    """
    path, exp = _nozzle()
    res = analyze_part(path, "oring_nozzle")
    loop = res.parting_line.primary_loop

    points = _loop_points(loop)
    axis = exp["part_axis"]
    spread = _spread_along(points, axis)
    assert spread > exp["height"] * 0.5, (
        f"loop spans only {spread:.1f} mm along the part axis but the part is "
        f"{exp['height']} mm tall — the loop lies across the axis instead of "
        f"containing it, so it cannot part the two halves"
    )


def test_nozzle_parting_line_lies_in_a_plane_containing_the_axis():
    """The other half of the clamshell claim: the loop is FLAT and vertical.

    Spanning the axis is necessary but not sufficient — a loop could zigzag up
    and down the wall and still span it. The reviewer's answer is a plane, so
    the loop must have no extent at all along the pull direction.
    """
    path, exp = _nozzle()
    res = analyze_part(path, "oring_nozzle")
    loop = res.parting_line.primary_loop

    spread = _spread_along(_loop_points(loop), res.best_mold_direction)
    assert spread < 0.1, (
        f"loop wanders {spread:.3f} mm along the pull direction; the clamshell "
        f"split lies in a single plane normal to the pull"
    )


def test_nozzle_reports_the_bore_as_a_side_action_not_as_solved():
    """The parting line must not claim to have released the bore.

    The loop only CLOSES because a side core forms the bore, and the result
    has to say so: `shutoff_length` records how much of it is side-action
    surface, and validation must still be failing on the remaining undercut.
    A parting line cannot release an undercut, and a result that looked valid
    here would be exactly the "hide undercuts behind a plausible line" failure.
    """
    path, _exp = _nozzle()
    res = analyze_part(path, "oring_nozzle")
    parting = res.parting_line

    assert parting.primary_loop.shutoff_length > 0.0, (
        "the bore is formed by a side core, so part of this loop is shutoff"
    )
    assert not parting.is_valid, "a part with a real undercut is not fully solved"
    assert any(c.name == "no_undercuts_remaining" for c in parting.validation.failures)
    assert parting.confidence <= 0.85, (
        f"confidence {parting.confidence} is not capped by the undercut failure"
    )
