"""
Correctness tests against synthetic parts with analytically known answers.

These assertions are derived from each part's construction, not from the
engine's current output. A failure here means the engine is wrong, not that
the test needs updating. Do not "fix" a test by relaxing it to match what the
code currently returns — that converts a correctness test into a
change-detector and is exactly how the previous suite lost its value.

Run:  .venv/bin/python -m pytest tests/ -v
      .venv/bin/python tests/test_synthetic.py      (standalone summary)
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analyzer import analyze_part                      # noqa: E402
from core.step_parser import parse_step                     # noqa: E402
from core.undercut_detector import (                        # noqa: E402
    UndercutRaycaster,
    evaluate_direction,
)
from tests import synthetic_parts as sp                     # noqa: E402

Z_PULL = (0.0, 0.0, 1.0)
TOL = 0.05          # 5 % geometric tolerance


# ----------------------------------------------------------------- helpers
def _undercuts_for(path, direction):
    """Undercut faces for an explicit direction, bypassing the axis search."""
    faces, _shape = parse_step(path)
    rc = UndercutRaycaster(faces)
    evaluate_direction(rc, faces, np.array(direction, dtype=float))
    return [f for f in faces if f.is_undercut], faces


def _pl_points(result):
    """All vertex coordinates on the reported parting line."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    pts = []
    for edge in result.parting_line_edges or []:
        ex = TopExp_Explorer(edge, TopAbs_VERTEX)
        while ex.More():
            p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(ex.Current()))
            pts.append((p.X(), p.Y(), p.Z()))
            ex.Next()
    return pts


def _radius(face):
    return math.hypot(face.center[0], face.center[1])


# ------------------------------------------------------- P1 solid cylinder
def test_convex_cylinder_has_no_undercuts_in_any_direction():
    """A convex body cannot have an undercut in ANY pull direction."""
    path, exp = sp.solid_cylinder()
    for direction in [(0, 0, 1), (1, 0, 0), (0, 1, 0),
                      (1, 1, 1), (1, 0, 1), (0.5, -0.3, 0.8)]:
        uc, faces = _undercuts_for(path, direction)
        assert not uc, (
            f"convex cylinder reported {len(uc)} undercut(s) for pull "
            f"{direction}; a convex solid has none by definition"
        )


def test_solid_cylinder_topology():
    path, exp = sp.solid_cylinder()
    faces, _ = parse_step(path)
    assert len(faces) == exp["face_count"]


# ------------------------------------------------------------- P2 open cup
def test_open_cup_has_no_undercuts():
    path, exp = sp.open_cup()
    uc, _ = _undercuts_for(path, Z_PULL)
    assert not uc, f"straight-walled cup is a clean draw; got {len(uc)} undercuts"


@pytest.mark.parametrize("direction", [(0, 0, 1), (0, 0, -1)])
def test_open_cup_has_no_undercuts_under_either_axial_sign(direction):
    """
    Sign-independent physics: a straight-walled cup is a clean draw along its
    axis whichever way the mould opens, so the undercut set is empty for both
    +Z and -Z.

    (An earlier version of this test asserted that the inner and outer walls
    must land in opposite halves. That is FALSE for an arbitrary forced sign:
    a single tool may form both walls with the part retained by its base. The
    core/cavity relationship is only pinned down once the engine has chosen
    the optimal direction — see the test below.)
    """
    path, _exp = sp.open_cup()
    uc, _ = _undercuts_for(path, direction)
    assert not uc, (
        f"cup reported {len(uc)} undercut(s) for pull {direction}; a straight "
        f"draw has none in either axial sign"
    )


def test_open_cup_core_forms_inner_cavity_forms_outer_at_optimal_direction():
    """
    The mentor's rule at the engine's OWN chosen direction, which is what the
    tool is actually scored on: the core forms internal surfaces, the cavity
    forms external ones.
    """
    path, exp = sp.open_cup()
    res = analyze_part(path, "open_cup")           # let the engine choose

    inner = [f for f in res.faces
             if f.surface_type == "CYLINDER"
             and abs(_radius(f) - exp["r_inner"]) < 1.0]
    outer = [f for f in res.faces
             if f.surface_type == "CYLINDER"
             and abs(_radius(f) - exp["r_outer"]) < 1.0]
    floor = [f for f in res.faces if f.surface_type == "PLANE"
             and abs(f.center[2] - exp["floor_z"]) < 0.5]
    bottom = [f for f in res.faces if f.surface_type == "PLANE"
              and abs(f.center[2]) < 0.5]
    assert inner and outer and floor and bottom

    assert inner[0].mold_half == "core", (
        f"inner wall is an INTERNAL surface -> core, got {inner[0].mold_half}"
    )
    assert outer[0].mold_half == "cavity", (
        f"outer wall is an EXTERNAL surface -> cavity, got {outer[0].mold_half}"
    )
    assert floor[0].mold_half == "core", "inner floor is internal -> core"
    assert bottom[0].mold_half == "cavity", "outer bottom is external -> cavity"


# --------------------------------------------- P3 cylinder w/ radial hole
def test_radial_hole_is_the_only_undercut():
    """
    Only the hole wall is trapped for an axial pull. Its axis is perpendicular
    to the pull direction, which is how we identify it without relying on
    face ids.
    """
    path, exp = sp.cylinder_radial_hole()
    uc, faces = _undercuts_for(path, Z_PULL)

    assert exp["min_undercut_faces"] <= len(uc) <= exp["max_undercut_faces"], (
        f"expected the hole wall only ({exp['min_undercut_faces']}-"
        f"{exp['max_undercut_faces']} faces), got {len(uc)}"
    )
    for f in uc:
        assert f.surface_type == "CYLINDER", (
            f"undercut should be the hole's cylindrical wall, got "
            f"{f.surface_type}"
        )
        assert f.axis is not None and abs(f.axis[2]) < 0.1, (
            "the trapped face must be the radial hole (axis perpendicular to "
            f"pull); got axis {f.axis}"
        )


def test_radial_hole_outer_wall_is_not_undercut():
    path, exp = sp.cylinder_radial_hole()
    uc, faces = _undercuts_for(path, Z_PULL)
    outer = [f for f in faces if f.surface_type == "CYLINDER"
             and f.axis is not None and abs(f.axis[2]) > 0.9]
    assert outer, "no axial outer wall found"
    for f in outer:
        assert not f.is_undercut, (
            "the outer wall is a plain vertical draw face, not an undercut"
        )


# ------------------------------------------------------ P4 stepped cylinder
def test_stepped_cylinder_has_no_undercuts():
    path, exp = sp.stepped_cylinder()
    uc, _ = _undercuts_for(path, Z_PULL)
    assert not uc, f"stacked cylinders release axially; got {len(uc)} undercuts"


def test_parting_line_sits_on_the_maximum_silhouette():
    """
    The parting line must lie on the largest cross-section (r=30), never on
    the smaller upper step (r=15). This is the synthetic analogue of Part3's
    flange and the one place we can check silhouette selection against a
    known answer.
    """
    path, exp = sp.stepped_cylinder()
    res = analyze_part(path, "stepped_cylinder", override_direction=Z_PULL)
    pts = _pl_points(res)
    assert pts, "engine reported no parting line at all"

    rmax = max(math.hypot(x, y) for x, y, _ in pts)
    assert abs(rmax - exp["silhouette_radius"]) < TOL * exp["silhouette_radius"], (
        f"parting line max radius {rmax:.2f}, expected the silhouette "
        f"{exp['silhouette_radius']:.2f} (the smaller step is "
        f"{exp['wrong_radius']:.2f})"
    )


# ------------------------------------------------------ P5 grooved cylinder
def test_circumferential_groove_is_detected_as_undercut():
    """
    A closed groove around the part traps three faces: both annular walls and
    the groove floor. This is the same feature class as the real Part3
    grooves, but here the answer is known.
    """
    path, exp = sp.grooved_cylinder()
    uc, faces = _undercuts_for(path, Z_PULL)
    z0, z1 = exp["groove_z"]

    assert len(uc) == exp["undercut_faces"], (
        f"expected {exp['undercut_faces']} trapped faces (2 annuli + groove "
        f"floor), got {len(uc)}: "
        + ", ".join(f"{f.surface_type}@z={f.center[2]:.1f}" for f in uc)
    )
    for f in uc:
        assert z0 - 0.6 <= f.center[2] <= z1 + 0.6, (
            f"undercut face at z={f.center[2]:.2f} lies outside the groove "
            f"band z={z0}..{z1}"
        )


def test_grooved_cylinder_outer_walls_are_clean():
    path, exp = sp.grooved_cylinder()
    uc, faces = _undercuts_for(path, Z_PULL)
    outer = [f for f in faces if f.surface_type == "CYLINDER"
             and abs(_radius(f) - exp["outer_radius"]) < 1.0]
    for f in outer:
        assert not f.is_undercut, (
            f"outer wall at z={f.center[2]:.1f} draws straight off the tool"
        )


# ------------------------------------------------------------- P6 solid box
def test_solid_box_has_no_undercuts():
    path, exp = sp.solid_box()
    uc, _ = _undercuts_for(path, Z_PULL)
    assert not uc, f"convex box has no undercuts; got {len(uc)}"


def test_box_parting_line_matches_rectangular_silhouette():
    """Non-circular silhouette: the parting line outline must be x by y."""
    path, exp = sp.solid_box()
    res = analyze_part(path, "solid_box", override_direction=Z_PULL)
    pts = _pl_points(res)
    assert pts, "engine reported no parting line at all"

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    width, depth = max(xs) - min(xs), max(ys) - min(ys)
    ex, ey, _ = exp["size"]
    assert abs(width - ex) < TOL * ex and abs(depth - ey) < TOL * ey, (
        f"parting line outline {width:.1f}x{depth:.1f}, expected {ex}x{ey}"
    )


# ------------------------------------------- P7/P8 does a flange skew the split?
def test_flanged_boss_splits_at_the_flange_and_is_not_degenerate():
    """
    Part3's massing without its features. The correct split puts the flange
    underside on one half and the boss on the other, with the parting line on
    the flange OD (the maximum silhouette).

    This is the controlled test of the claim that a wide bottom flange
    poisons the classifier and forces a near-empty second half. If this part
    splits sensibly, a lopsided ratio on the real Part3 is geometry, not a
    flange bug.
    """
    path, exp = sp.flanged_boss()
    res = analyze_part(path, "flanged_boss")

    uc = [f for f in res.faces if f.is_undercut]
    assert not uc, f"plain flanged boss has no undercuts; got {len(uc)}"

    flange_od = [f for f in res.faces if f.surface_type == "CYLINDER"
                 and abs(_radius(f) - exp["r_flange"]) < 1.0]
    boss_od = [f for f in res.faces if f.surface_type == "CYLINDER"
               and abs(_radius(f) - exp["r_boss"]) < 1.0]
    assert flange_od and boss_od

    assert flange_od[0].mold_half != boss_od[0].mold_half, (
        "flange OD and boss OD must be formed by different halves; the "
        "parting line runs between them"
    )

    halves = {"core": 0.0, "cavity": 0.0}
    for f in res.faces:
        halves[f.mold_half] = halves.get(f.mold_half, 0.0) + f.area
    total = sum(halves.values())
    minority = min(halves.values()) / total
    assert minority > 0.05, (
        f"minority half holds only {minority:.1%} of surface area — a split "
        f"this degenerate cannot be a mould"
    )

    pts = _pl_points(res)
    assert pts, "no parting line reported"
    rmax = max(math.hypot(x, y) for x, y, _ in pts)
    assert abs(rmax - exp["r_flange"]) < TOL * exp["r_flange"], (
        f"parting line at r={rmax:.1f}, expected the flange OD "
        f"r={exp['r_flange']}"
    )


# ------------------------------------------------------- P9 closed-top cup
def test_capped_cup_bore_is_core_shell_is_cavity():
    """
    Opening at the BOTTOM this time, so the answer cannot come from normal
    direction alone — the engine has to work out which end the bore opens
    toward. Internal surface still belongs to the core.
    """
    path, exp = sp.capped_cup()
    res = analyze_part(path, "capped_cup")

    uc = [f for f in res.faces if f.is_undercut]
    assert not uc, f"capped cup is a clean draw; got {len(uc)} undercuts"

    inner = [f for f in res.faces if f.surface_type == "CYLINDER"
             and abs(_radius(f) - exp["r_inner"]) < 1.0]
    outer = [f for f in res.faces if f.surface_type == "CYLINDER"
             and abs(_radius(f) - exp["r_outer"]) < 1.0]
    assert inner and outer
    assert inner[0].mold_half == "core", (
        f"bore is internal -> core, got {inner[0].mold_half}"
    )
    assert outer[0].mold_half == "cavity", (
        f"shell is external -> cavity, got {outer[0].mold_half}"
    )


# --------------------------------------------------- P10 lateral blind pocket
def test_blind_pocket_traps_wall_and_floor_under_axial_pull():
    """
    Forced axial pull: a blind radial pocket traps exactly two faces, its
    wall and its floor. Counting only the wall would mean the engine ignores
    the bottom of a bounded recess.
    """
    path, exp = sp.cylinder_blind_pocket()
    uc, _faces = _undercuts_for(path, Z_PULL)
    assert len(uc) == exp["undercut_faces"], (
        f"expected pocket wall + floor ({exp['undercut_faces']} faces), got "
        f"{len(uc)}: "
        + ", ".join(f"{f.surface_type}@z={f.center[2]:.1f}" for f in uc)
    )


def test_blind_pocket_is_released_by_pulling_along_its_own_axis():
    """
    The pocket axis is a legitimate pull direction that removes the undercut
    entirely, so the direction search should find a zero-undercut answer
    rather than settling for the axial pull.
    """
    path, _exp = sp.cylinder_blind_pocket()
    res = analyze_part(path, "cylinder_blind_pocket")
    uc = [f for f in res.faces if f.is_undercut]
    assert not uc, (
        f"a pull along the pocket axis releases it; search returned "
        f"{res.best_direction_label} with {len(uc)} undercuts"
    )


# --------------------------------------- P11 undercut suppression on real Part3
@pytest.mark.skipif(not os.path.exists(sp._PART3), reason="Part3.stp not present")
def test_filling_part3_pockets_removes_essentially_all_undercuts():
    """
    Suppressing the two rib-pocket regions must clear the undercut set. What
    survives should be negligible slivers left by the crude plug, not real
    trapped geometry — so this asserts on AREA, which is also the metric
    Bosch asked us to rank on.
    """
    path, exp = sp.part3_pockets_filled()
    uc, faces = _undercuts_for(path, (0, 0, -1))
    residual = sum(f.area for f in uc)
    total = sum(f.area for f in faces)
    assert residual < exp["residual_undercut_area_max"], (
        f"{residual:.1f} mm2 of undercut survives after suppression "
        f"({100*residual/total:.2f}% of the part); expected only fill slivers"
    )


@pytest.mark.skipif(not os.path.exists(sp._PART3), reason="Part3.stp not present")
def test_parting_line_is_invariant_under_undercut_suppression():
    """
    The parting line must be a property of the part's silhouette, not of its
    undercuts. Filling recesses that sit 5+ mm inside the maximum silhouette
    cannot legitimately move the line, so if it moves, the line was being
    driven by feature edges rather than by the outline.
    """
    filled_path, exp = sp.part3_pockets_filled()

    before = analyze_part(sp._PART3, "part3", override_direction=(0, 0, -1))
    after = analyze_part(filled_path, "part3_filled", override_direction=(0, 0, -1))

    pb, pa = _pl_points(before), _pl_points(after)
    assert pb and pa, "parting line missing on one of the two bodies"

    rb = max(math.hypot(x, y) for x, y, _ in pb)
    ra = max(math.hypot(x, y) for x, y, _ in pa)
    zb = sum(p[2] for p in pb) / len(pb)
    za = sum(p[2] for p in pa) / len(pa)

    assert abs(rb - ra) < 0.5, (
        f"parting line radius moved {rb:.2f} -> {ra:.2f} when undercuts were "
        f"suppressed; it was being driven by feature edges, not the silhouette"
    )
    assert abs(zb - za) < 0.5, (
        f"parting line height moved z={zb:.2f} -> z={za:.2f} under undercut "
        f"suppression"
    )
    assert abs(ra - exp["pl_radius"]) < 0.5, (
        f"parting line at r={ra:.2f}, expected the flange OD "
        f"r={exp['pl_radius']}"
    )


# ------------------------------------- undercut regions vs a real mold's tooling
_BUSH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "assets", "sidecore", "PLASTIC BUSH.stp")


@pytest.mark.skipif(not os.path.exists(_BUSH), reason="reference bush not present")
def test_bush_undercuts_match_the_reference_slide_core():
    """
    External ground truth, from a working mold design.

    GrabCAD "Side Core_injection Mold Design" ships both the moulded part and
    the tooling that releases it. Its `Slide Core.stp` carries forming pins at
    z = -2.18 on axis (+/-1, 0, 0). Whatever we flag as trapped on the part
    must therefore be at that height, and the mechanism we recommend must be a
    slider travelling along X — not a lifter, and not the mould's pull axis.

    This is the only external validation in the project that is neither the
    judges' word nor our own construction, so it is worth failing loudly on.
    """
    from core.undercut_regions import find_undercut_regions, summarize_regions

    faces, shape = parse_step(_BUSH)
    rc = UndercutRaycaster(faces)
    evaluate_direction(rc, faces, np.array([0.0, 0.0, 1.0]), exact_fractions=True)

    trapped = [f for f in faces if f.is_undercut]
    assert trapped, "reference part has undercuts the mould solves with a slide core"

    for f in trapped:
        assert abs(f.center[2] - (-2.18)) < 0.3, (
            f"trapped face at z={f.center[2]:.2f}; the slide core forms features "
            f"at z=-2.18"
        )

    regions = find_undercut_regions(shape, faces, (0.0, 0.0, 1.0), rc)
    assert regions, "trapped faces did not group into any region"

    for r in regions:
        assert not r.is_internal, (
            "a side hole is an EXTERNAL undercut (Qlution lists 'side holes, "
            "lateral slots' explicitly); calling it internal recommends a "
            "lifter where the real mould uses a slide core"
        )
        assert "slider" in r.mechanism, (
            f"expected a side-action slider, got '{r.mechanism}'"
        )
        d = r.side_action_direction
        assert abs(abs(d[0]) - 1.0) < 0.2 and abs(d[2]) < 0.2, (
            f"slider must travel along X to match the reference pins; got {d}"
        )

    assert summarize_regions(regions)["side_action_axes"] == 1, (
        "opposed pins share one axis, so the tooling needs a single slider axis"
    )


@pytest.mark.skipif(not os.path.exists(sp._PART3), reason="Part3.stp not present")
def test_part3_eighty_eight_faces_are_two_features():
    """
    The 88 trapped faces on Part3 are two physical pockets, not 88 problems.
    Guards the reporting fix: if region grouping regresses, the tool goes back
    to quoting a topology artifact as an engineering result.
    """
    from core.undercut_regions import find_undercut_regions

    faces, shape = parse_step(sp._PART3)
    rc = UndercutRaycaster(faces)
    evaluate_direction(rc, faces, np.array([0.0, 0.0, -1.0]), exact_fractions=True)
    regions = find_undercut_regions(shape, faces, (0.0, 0.0, -1.0), rc)

    assert len(regions) == 2, (
        f"expected 2 undercut features, got {len(regions)}"
    )
    assert all(not r.is_internal for r in regions), (
        "the rib pockets open radially outward — they are external"
    )
    areas = sorted(r.area for r in regions)
    assert abs(areas[0] - areas[1]) < 1.0, (
        "the two pockets are symmetric and should have matching area"
    )


# ------------------------------------------------- sampling adequacy (real bug)
_REAL_PARTS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "assets", name)
    for name in ("Part1.stp", "Part3.stp")
]

_MIN_SAMPLES = 3
_SIGNIFICANT_AREA = 10.0     # mm^2


@pytest.mark.parametrize("path", [p for p in _REAL_PARTS if os.path.exists(p)],
                         ids=lambda p: os.path.basename(p))
def test_every_significant_face_gets_enough_samples(path):
    """
    A face's undercut verdict is a majority vote over its surface samples. A
    face judged on ONE sample is a single-ray verdict — precisely the Phase 1
    defect that cost us the optimal-direction score, and which the decision
    log records as fixed.

    Any face with meaningful area must therefore carry at least a few
    IN-classified samples. This is a property of the sampler alone and does
    not depend on knowing the right answer for the part.
    """
    faces, _shape = parse_step(path)
    starved = [f for f in faces
               if f.area >= _SIGNIFICANT_AREA
               and len(f.sample_points) < _MIN_SAMPLES]
    detail = ", ".join(
        f"id={f.face_id} {f.surface_type} area={f.area:.1f}mm2 "
        f"n={len(f.sample_points)}"
        for f in sorted(starved, key=lambda f: -f.area)[:8]
    )
    assert not starved, (
        f"{len(starved)} face(s) >= {_SIGNIFICANT_AREA} mm2 carry fewer than "
        f"{_MIN_SAMPLES} surface samples, so their undercut verdict rests on "
        f"one or two rays: {detail}"
    )


# ------------------------------------------------------------- standalone
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short", "-p", "no:cacheprovider"]))
