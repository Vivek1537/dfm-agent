"""
Unit tests for candidate pull-direction generation and selection.

These test the direction stage in isolation — normalisation, deduplication,
the geometry-derived sources, and the lexicographic ordering — without needing
a full analysis run. The ordering tests in particular are built from
hand-constructed evaluations so the exact criterion under test is the only
thing that differs between two candidates.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.accessibility import (                              # noqa: E402
    AccessibilityResult,
    FaceAccessibility,
    MoldRegion,
)
from core.direction_evaluation import (                       # noqa: E402
    DirectionEvaluation,
    direction_sort_key,
    rank_directions,
    select_best_direction,
)
from core.pull_direction import (                             # noqa: E402
    SOURCE_DIAGONAL,
    SOURCE_FEATURE_AXIS,
    SOURCE_GLOBAL_AXIS,
    PullDirection,
    canonical,
    generate_candidate_directions,
    normalize,
    override_direction,
    principal_axes,
    same_axis,
)
from core.step_parser import parse_step                       # noqa: E402
from core.tolerances import AXIS_DEDUP_DOT, DEFAULT_CONFIG    # noqa: E402
from tests import synthetic_parts as sp                       # noqa: E402


# ------------------------------------------------------------- normalisation
def test_normalize_returns_unit_vectors():
    v = normalize((3.0, 4.0, 0.0))
    assert v is not None
    assert abs(math.sqrt(sum(c * c for c in v)) - 1.0) < 1e-12
    assert abs(v[0] - 0.6) < 1e-12 and abs(v[1] - 0.8) < 1e-12


def test_normalize_rejects_a_zero_vector():
    assert normalize((0.0, 0.0, 0.0)) is None


def test_override_of_a_zero_vector_is_an_error():
    with pytest.raises(ValueError):
        override_direction((0.0, 0.0, 0.0))


def test_override_keeps_its_sign():
    """An override carries the user's choice of which half is core."""
    assert override_direction((0.0, 0.0, -5.0)).vector == (0.0, 0.0, -1.0)


# ------------------------------------------------------------ canonical form
@pytest.mark.parametrize("vector", [
    (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
    (0.6, -0.8, 0.0), (-0.5, 0.5, 0.7071),
])
def test_canonical_collapses_a_direction_and_its_opposite(vector):
    """+D and -D are the same mold AXIS and must not be evaluated twice."""
    opposite = tuple(-c for c in vector)
    assert canonical(vector) == canonical(opposite)


def test_canonical_is_idempotent():
    v = canonical((-0.5, 0.5, 0.7071))
    assert canonical(v) == v


def test_same_axis_is_sign_independent():
    assert same_axis((0.0, 0.0, 1.0), (0.0, 0.0, -1.0), AXIS_DEDUP_DOT)
    assert not same_axis((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), AXIS_DEDUP_DOT)


# ------------------------------------------------------ candidate generation
def test_generation_always_includes_the_three_global_axes():
    """Bosch: "usually it will be in X Y Z, in most cases"."""
    faces, _ = parse_step(sp.solid_box()[0])
    vectors = [c.vector for c in generate_candidate_directions(faces)]
    for axis in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
        assert any(same_axis(axis, v, AXIS_DEDUP_DOT) for v in vectors), (
            f"global axis {axis} missing from the candidate set"
        )


def test_generated_candidates_are_unit_length_and_unique():
    faces, _ = parse_step(sp.flanged_boss()[0])
    candidates = generate_candidate_directions(faces)
    assert candidates

    for c in candidates:
        assert abs(math.sqrt(sum(x * x for x in c.vector)) - 1.0) < 1e-9

    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            assert not same_axis(a.vector, b.vector, AXIS_DEDUP_DOT), (
                f"{a.label} and {b.label} are the same axis"
            )


def test_generation_is_deterministic():
    faces, _ = parse_step(sp.flanged_boss()[0])
    first = [(c.vector, c.label, c.source) for c in generate_candidate_directions(faces)]
    second = [(c.vector, c.label, c.source) for c in generate_candidate_directions(faces)]
    assert first == second


def test_generation_respects_the_candidate_cap():
    faces, _ = parse_step(sp.flanged_boss()[0])
    cfg = DEFAULT_CONFIG.with_overrides(max_candidate_directions=5)
    assert len(generate_candidate_directions(faces, cfg)) == 5


def test_a_turned_part_offers_its_own_feature_axis():
    """A cylinder's axis is the natural pull for a turned part."""
    faces, _ = parse_step(sp.stepped_cylinder()[0])
    candidates = generate_candidate_directions(faces)
    z = (0.0, 0.0, 1.0)
    assert any(same_axis(c.vector, z, AXIS_DEDUP_DOT) for c in candidates)


def test_the_pocket_axis_is_offered_for_a_lateral_feature():
    """The blind pocket's axis is what releases it, so it must be a candidate."""
    faces, _ = parse_step(sp.cylinder_blind_pocket()[0])
    candidates = generate_candidate_directions(faces)
    x = (1.0, 0.0, 0.0)
    assert any(same_axis(c.vector, x, AXIS_DEDUP_DOT) for c in candidates)


# -------------------------------------------------------------- principal axes
def test_an_axisymmetric_part_offers_no_spurious_near_axis_candidate():
    """Sampling noise must not reach the candidate set as a distinct axis.

    Surface samples sit on a UV grid, which is not area-uniform: five samples
    round a cylinder land at 0.63, 1.88, 3.14, 4.40 and 5.65 radians. So even
    a perfectly axisymmetric part yields a slightly non-axisymmetric
    covariance, and on the flanged boss the top eigenvector came out 3.9
    degrees off Z. That is a well-separated eigenvalue, so no degeneracy test
    rejects it, yet it is not a real axis of the part — and it was close
    enough to Z to win the ranking while putting the flange and the boss in
    the same mold half.

    The estimator is allowed to return it; what matters is that generation
    recognises it as Z measured noisily and does not offer it as a separate
    candidate.
    """
    faces, _ = parse_step(sp.flanged_boss()[0])
    cartesian = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    for candidate in generate_candidate_directions(faces):
        if candidate.source != "principal_axis":
            continue
        near_a_real_axis = any(
            same_axis(candidate.vector, unit, math.cos(math.radians(10.0)))
            for unit in cartesian
        )
        assert not near_a_real_axis, (
            f"candidate {candidate.label} sits {math.degrees(math.acos(min(1.0, max(abs(candidate.vector[0]), abs(candidate.vector[1]), abs(candidate.vector[2]))))):.1f} "
            f"degrees from a cartesian axis — it is sampling noise around an "
            f"axis the fixed set already covers, not a distinct direction"
        )


def test_principal_axes_reject_degenerate_eigenvalues():
    """A shape with no distinguished direction must propose none.

    A cube's three eigenvalues are equal, so its eigenvectors are arbitrary —
    any rotation of them diagonalises the covariance equally well. Returning
    one would be reporting noise as geometry.
    """
    path, exp = sp.solid_cube()
    faces, _ = parse_step(path)
    axes = principal_axes(faces)
    assert len(axes) == exp["principal_axes"], (
        f"a cube has no distinguished direction, but {len(axes)} principal "
        f"axis/axes were proposed: {[a for a, _ in axes]}"
    )


# ------------------------------------------------------------------- ordering
def _evaluation(
    label="T", source=SOURCE_GLOBAL_AXIS, vector=(0.0, 0.0, 1.0),
    undercut_count=0, undercut_area=0.0, accessibility=1.0,
    complexity=0.0, balance=0.0,
) -> DirectionEvaluation:
    """A DirectionEvaluation with everything but the field under test fixed."""
    return DirectionEvaluation(
        direction=PullDirection(vector=vector, source=source, label=label),
        accessibility_result=AccessibilityResult(direction=vector),
        undercut_count=undercut_count,
        undercut_area=undercut_area,
        accessibility=accessibility,
        complexity=complexity,
        balance=balance,
    )


def test_zero_undercuts_beats_any_number_of_undercuts():
    """The specification's Priority 1, stated as a hard rule."""
    clean = _evaluation(label="clean")
    dirty = _evaluation(label="dirty", undercut_count=1, undercut_area=0.01)
    assert select_best_direction([dirty, clean]) is clean


def test_a_shorter_parting_line_cannot_buy_off_undercuts():
    """The failure the specification forbids outright.

    A direction with undercuts must never win because everything downstream of
    the undercut criteria favours it. Here the undercut-bearing candidate is
    better on accessibility, complexity, source rank and balance — every
    remaining criterion — and it must still lose.
    """
    clean = _evaluation(
        label="clean", source=SOURCE_DIAGONAL, vector=(0.7071, 0.0, 0.7071),
        accessibility=0.10, complexity=0.99, balance=0.99,
    )
    dirty = _evaluation(
        label="dirty", source=SOURCE_GLOBAL_AXIS, vector=(0.0, 0.0, 1.0),
        undercut_count=12, undercut_area=500.0,
        accessibility=1.0, complexity=0.0, balance=0.0,
    )
    assert select_best_direction([dirty, clean]) is clean


def test_area_outranks_count():
    """Bosch, 2026-07-28: "area will be better to evaluate".

    A face the CAD kernel happened to split into many patches must not outrank
    one large trapped face.
    """
    many_small = _evaluation(label="many", undercut_count=20, undercut_area=5.0)
    one_large = _evaluation(label="one", undercut_count=1, undercut_area=500.0)
    assert select_best_direction([one_large, many_small]) is many_small


def test_count_breaks_a_tie_on_equal_area():
    fewer = _evaluation(label="fewer", undercut_count=2, undercut_area=100.0)
    more = _evaluation(label="more", undercut_count=9, undercut_area=100.0)
    assert select_best_direction([more, fewer]) is fewer


def test_simpler_parting_topology_wins_among_equals():
    simple = _evaluation(label="simple", complexity=0.0)
    tangled = _evaluation(label="tangled", complexity=0.8)
    assert select_best_direction([tangled, simple]) is simple


def test_a_dominant_geometric_axis_beats_an_arbitrary_diagonal():
    """Specification section 6, tie-break 3."""
    axis = _evaluation(
        label="Z", source=SOURCE_FEATURE_AXIS, vector=(0.0, 0.0, 1.0)
    )
    diagonal = _evaluation(
        label="XZ+", source=SOURCE_DIAGONAL, vector=(0.7071, 0.0, 0.7071)
    )
    assert select_best_direction([diagonal, axis]) is axis


def test_selection_is_deterministic_for_identical_candidates():
    """Two indistinguishable axes must resolve the same way on every run."""
    a = _evaluation(label="A", vector=(0.0, 0.0, 1.0))
    b = _evaluation(label="B", vector=(1.0, 0.0, 0.0))
    assert select_best_direction([a, b]) is select_best_direction([b, a])


def test_ranking_is_a_total_order_with_no_ties():
    """Every candidate must sort to a distinct position.

    If two sort keys can be equal the ranking depends on input order, which is
    exactly the non-determinism the final tie-break exists to prevent.
    """
    faces, _ = parse_step(sp.flanged_boss()[0])
    evaluations = [
        _evaluation(label=c.label, source=c.source, vector=c.vector)
        for c in generate_candidate_directions(faces)
    ]
    keys = [direction_sort_key(e) for e in evaluations]
    assert len(set(keys)) == len(keys)


def test_rank_directions_orders_best_first():
    worst = _evaluation(label="worst", undercut_count=5, undercut_area=300.0)
    middle = _evaluation(label="middle", undercut_count=1, undercut_area=10.0)
    best = _evaluation(label="best")
    ranked = rank_directions([middle, worst, best])
    assert [e.direction.label for e in ranked] == ["best", "middle", "worst"]


def test_selection_rejects_an_empty_candidate_list():
    with pytest.raises(ValueError):
        select_best_direction([])


# ----------------------------------------------------------- accessibility
def test_region_reflects_which_side_can_reach_the_face():
    """The specification's four-way table, applied directly."""
    def entry(plus, minus, undercut=False):
        a = FaceAccessibility(
            face_id=0, sample_count=10,
            plus_fraction=plus, minus_fraction=minus,
            both_fraction=min(plus, minus),
            neither_fraction=max(0.0, 1.0 - plus - minus),
            trapped_fraction=1.0 if undercut else 0.0,
            is_undercut=undercut, region=MoldRegion.AMBIGUOUS,
        )
        return a

    from core.accessibility import AccessibilityAnalyzer

    # Region derivation only needs the config, not the geometry.
    analyzer = AccessibilityAnalyzer.__new__(AccessibilityAnalyzer)
    analyzer.config = DEFAULT_CONFIG

    assert analyzer._region_for(entry(1.0, 0.0), 5, 0) == MoldRegion.CAVITY
    assert analyzer._region_for(entry(0.0, 1.0), 0, 5) == MoldRegion.CORE
    assert analyzer._region_for(entry(1.0, 1.0), 3, 3) == MoldRegion.NEUTRAL
    assert analyzer._region_for(entry(0.0, 0.0), 0, 0) == MoldRegion.AMBIGUOUS
    assert analyzer._region_for(entry(1.0, 1.0, True), 3, 3) == MoldRegion.UNDERCUT
