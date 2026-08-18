"""
Tests for declared tooling plans (side-core delegation).

The property these pin down is not "Part 3 reports zero" — it is that a zero
reached by DELEGATION can never be mistaken for a zero reached by GEOMETRY.
Delegation always terminates at zero (any undercut set vanishes if you delegate
the faces that constitute it), so the number alone conveys nothing; the
required-actions list travelling beside it is what carries the meaning.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analyzer import analyze_part                          # noqa: E402
from core.delegation import (                                   # noqa: E402
    EMPTY_PLAN,
    DelegatedGroup,
    FaceSelector,
    ToolingPlan,
    load_plan,
    plan_for_part,
)
from core.step_parser import parse_step                          # noqa: E402
from tests import synthetic_parts as sp                          # noqa: E402

ASSETS = os.path.join(os.path.dirname(__file__), os.pardir, "assets")
PART1 = os.path.abspath(os.path.join(ASSETS, "Part1.stp"))
PART3 = os.path.abspath(os.path.join(ASSETS, "Part3.stp"))
PART3_PLAN = os.path.abspath(os.path.join(ASSETS, "Part3.tooling.json"))

part3 = pytest.mark.skipif(not os.path.exists(PART3), reason="Part3.stp not present")


# ---------------------------------------------------------------- selectors
def test_selector_matches_by_face_id():
    sel = FaceSelector(face_ids=(35, 319))
    faces, _ = parse_step(sp.solid_box()[0])
    assert sel.matches(type("F", (), {"face_id": 35, "center": (0, 0, 0),
                                      "surface_type": "PLANE"})())
    assert not sel.matches(faces[0]) or faces[0].face_id in (35, 319)


def test_selector_matches_by_z_band():
    sel = FaceSelector(z_min=10.0)
    faces, _ = parse_step(sp.stepped_cylinder()[0])
    for f in faces:
        assert sel.matches(f) == (f.center[2] >= 10.0)


def test_empty_selector_matches_nothing():
    """A group with no criteria must not silently swallow the whole part."""
    sel = FaceSelector()
    faces, _ = parse_step(sp.solid_box()[0])
    assert not any(sel.matches(f) for f in faces)


def test_group_with_zero_action_axis_is_rejected():
    with pytest.raises(ValueError):
        DelegatedGroup.from_dict(
            {"name": "bad", "action_axis": [0, 0, 0], "select": {"z_min": 0}}
        )


# --------------------------------------------------------------- plan loading
def test_a_part_with_no_plan_beside_it_gets_an_empty_plan():
    assert plan_for_part(sp.solid_box()[0]) is EMPTY_PLAN
    assert not EMPTY_PLAN


@part3
def test_part3_plan_is_found_and_declares_two_groups():
    plan = plan_for_part(PART3)
    assert plan, "Part3.tooling.json should be picked up beside the model"
    assert plan.source == "Part3.tooling.json"
    assert len(plan.groups) == 2
    names = {g.name for g in plan.groups}
    assert names == {"through-bore", "splined end"}


@part3
def test_both_part3_actions_travel_on_one_shared_axis():
    """Two mechanisms, both axial — one axis, not two. Opposed actions merge."""
    plan = load_plan(PART3_PLAN)
    assert plan.action_axis_count() == 1


@part3
def test_part3_groups_resolve_to_the_expected_geometry():
    plan = load_plan(PART3_PLAN)
    faces, _ = parse_step(PART3)
    groups = {g["name"]: g for g in plan.resolve(faces)}

    bore = groups["through-bore"]
    assert bore["face_count"] == 3
    assert abs(bore["area"] - 1548.1) < 1.0

    spline = groups["splined end"]
    assert spline["face_count"] == 280
    assert abs(spline["area"] - 1365.1) < 1.0

    # The two groups overlap on the bore's far chamfer, which must be counted
    # once, not twice.
    assert len(plan.delegated_face_ids(faces)) == 282


# -------------------------------------------------- delegation is opt-in only
@part3
def test_without_a_plan_part3_still_reports_its_88_undercuts():
    """Delegation must never be inferred.

    This is the guard against the whole feature becoming vacuous: with no
    declared plan the engine has to report what a straight pull actually
    traps, undiminished.
    """
    res = analyze_part(PART3, "part3", exact_candidates=False,
                       tooling_plan=EMPTY_PLAN)
    assert res.undercut_face_count == 88
    assert abs(res.undercut_area - 1366.8) < 1.0
    assert res.required_actions == []
    assert not res.parting_line.is_valid


@part3
def test_with_the_declared_plan_the_main_halves_are_clean():
    res = analyze_part(PART3, "part3", exact_candidates=False)
    assert res.undercut_face_count == 0
    assert res.undercut_area == 0.0
    assert res.parting_line.is_valid
    # ... and the price is stated.
    assert len(res.required_actions) == 2
    assert {a["name"] for a in res.required_actions} == {"through-bore", "splined end"}


@part3
def test_a_delegated_zero_is_distinguishable_from_a_geometric_zero():
    """The property the whole feature rests on.

    Part 1 draws clean with no side actions at all. Part 3 draws clean only
    because 2855 mm² is handed to separate tooling. Both report zero
    undercuts; nothing may present them as the same result.
    """
    p1 = analyze_part(PART1, "part1", exact_candidates=False)
    p3 = analyze_part(PART3, "part3", exact_candidates=False)

    assert p1.undercut_face_count == 0 and p3.undercut_face_count == 0

    assert p1.required_actions == [], "Part 1 needs no side actions"
    assert p3.required_actions, "Part 3's zero is bought with side actions"

    delegated = sum(a["area"] for a in p3.required_actions)
    assert delegated > 2800.0

    # And validation says so in words, not just in a field.
    check = next(c for c in p3.parting_line.validation.checks
                 if c.name == "side_actions_required")
    assert "ONLY because" in check.detail
    assert "separate tooling" in check.detail

    assert not any(c.name == "side_actions_required"
                   for c in p1.parting_line.validation.checks)


@part3
def test_delegated_faces_are_marked_and_excluded_from_the_tally():
    res = analyze_part(PART3, "part3", exact_candidates=False)
    delegated = [f for f in res.faces if f.is_delegated]
    assert len(delegated) == 282
    assert all(not f.is_undercut for f in delegated), (
        "a delegated face is neither released nor trapped by the pull"
    )
    assert all(f.mold_region == "delegated" for f in delegated)


# ------------------------------------------------- preferred direction check
@part3
def test_the_declared_direction_is_verified_and_accepted():
    res = analyze_part(PART3, "part3", exact_candidates=False)
    d = res.best_mold_direction
    assert abs(d[2]) < 0.01, "the declared split is a clamshell — no z component"
    t = math.degrees(math.atan2(d[1], d[0])) % 180
    assert abs(t - 35.0) < 1.0, f"expected the declared 35°, got {t:.1f}°"
    assert "accepted" in res.preferred_direction_note


@part3
def test_a_worse_declared_direction_is_rejected_not_obeyed():
    """A declared direction is verified, never trusted.

    Z traps the two slot regions, which the plan does NOT delegate, so
    declaring it must be refused in favour of what the search derived.
    """
    plan = load_plan(PART3_PLAN)
    bad = ToolingPlan(
        groups=plan.groups,
        source="test-bad-direction",
        preferred_direction=(0.0, 0.0, 1.0),
    )
    res = analyze_part(PART3, "part3", exact_candidates=False, tooling_plan=bad)

    assert "REJECTED" in res.preferred_direction_note
    assert abs(res.best_mold_direction[2]) < 0.01, (
        "the derived clamshell should stand, not the declared axial pull"
    )
    assert res.undercut_face_count == 0


# ------------------------------------------------------------- alternatives
@part3
def test_alternatives_always_include_an_axial_option():
    """The axial pull is the configuration a reader most needs to see next.

    It is the one needing no bore core and no spline insert, and its higher
    trapped area is the price of that. A truncated list that dropped it would
    present the clamshell as though it had no competition.
    """
    res = analyze_part(PART3, "part3", exact_candidates=False)
    assert res.alternatives
    axial = [a for a in res.alternatives if a["is_axial"]]
    assert axial, f"no axial alternative in {[a['label'] for a in res.alternatives]}"

    a = axial[0]
    assert a["undercut_count"] == 88
    assert abs(a["undercut_area"] - 1366.8) < 1.0
    assert a["would_need_further_actions"] is True

    # The axial pull needs NEITHER of the declared groups — it draws the bore
    # and the splined end cleanly, which is exactly why it is worth keeping in
    # view. Whether a configuration needs the plan is measured per direction,
    # not inherited from the primary.
    assert a["needs_declared_plan"] is False
    assert a["extra_action_axes"] == 0
    assert a["main_half_fraction"] > 0.8, (
        f"axial coverage {a['main_half_fraction']:.1%}; it forms everything "
        f"except the slots it traps, so it should be ~82%"
    )

    # Alternative 2: the same axial pull with its OWN trapped regions
    # delegated. Computed by the region grouper, not asserted.
    d = a["if_delegated"]
    assert d is not None, "the axial alternative should carry a delegated variant"
    assert d["undercut_area"] == 0.0
    assert d["region_count"] == 2, "the two rib-pocket regions"
    assert d["extra_action_axes"] == 1, "opposed sliders share one axis"
    assert "side-action slider" in d["mechanisms"]
    assert d["main_half_fraction"] > 0.8


@part3
def test_alternatives_report_main_half_coverage_not_just_undercuts():
    res = analyze_part(PART3, "part3", exact_candidates=False)
    for a in res.alternatives:
        for key in ("main_half_area", "main_half_fraction", "extra_action_axes",
                    "would_need_further_actions", "is_axial"):
            assert key in a, f"alternative missing {key}"


# ------------------------------------------------------ no effect elsewhere
def test_parts_without_a_plan_are_completely_unaffected():
    """Every synthetic fixture must behave exactly as it did before."""
    for builder in (sp.solid_box, sp.stepped_cylinder, sp.open_cup,
                    sp.flanged_boss):
        path, exp = builder()
        res = analyze_part(path, exp["name"])
        assert res.required_actions == []
        assert res.tooling_plan is EMPTY_PLAN
        assert not any(f.is_delegated for f in res.faces)
