"""
Synthetic reference parts with analytically known DfM answers.

Every part here is built from primitives so that its correct undercut set,
silhouette radius and core/cavity assignment follow from the construction
itself, not from anyone's judgement. That is the whole point: these parts are
the only ground truth in this project that does not depend on Bosch, on a
third-party CAD run, or on our own documentation.

Each builder returns (path_to_step, expected) where `expected` records the
answer implied by the geometry. Expectations are written from first principles
BEFORE running the engine — never adjusted to match what the engine happens to
produce.
"""

from __future__ import annotations

import math
import os
import tempfile

import cadquery as cq

_CACHE: dict[str, str] = {}
_OUTDIR = os.path.join(tempfile.gettempdir(), "dfm_synthetic_parts")


def _export(name: str, solid: cq.Workplane) -> str:
    """Export a solid to STEP once per session and cache the path."""
    if name in _CACHE and os.path.exists(_CACHE[name]):
        return _CACHE[name]
    os.makedirs(_OUTDIR, exist_ok=True)
    path = os.path.join(_OUTDIR, f"{name}.step")
    cq.exporters.export(solid, path)
    _CACHE[name] = path
    return path


# --------------------------------------------------------------------------
# P1 — solid cylinder. Convex body.
# --------------------------------------------------------------------------
def solid_cylinder(r: float = 30.0, h: float = 50.0):
    """
    A convex solid. A convex body has NO undercuts in ANY pull direction,
    because every surface point escapes along its own outward normal.

    Silhouette for a Z pull is the circle of radius r.
    """
    solid = cq.Workplane("XY").circle(r).extrude(h)
    expected = {
        "name": "solid_cylinder",
        "undercut_faces": 0,
        "undercut_faces_any_direction": 0,   # convexity
        "face_count": 3,                     # top disc, bottom disc, wall
        "silhouette_radius": r,
        "silhouette_area": math.pi * r * r,
    }
    return _export("p1_solid_cylinder", solid), expected


# --------------------------------------------------------------------------
# P2 — open cup. The mentor's own worked example.
# --------------------------------------------------------------------------
def open_cup(r_out: float = 30.0, wall: float = 3.0, h: float = 50.0,
             floor: float = 3.0):
    """
    A straight-walled open cup: the canonical two-plate moulding.

    Known by construction, and matching the mentor's stated rule that the core
    forms internal surfaces and the cavity forms external ones:
      inner wall  (cylinder r = r_out - wall) -> CORE
      inner floor (plane at z = floor, +Z)    -> CORE
      outer wall  (cylinder r = r_out)        -> CAVITY
      outer bottom(plane at z = 0, -Z)        -> CAVITY
    No undercuts: the core withdraws up, the cavity down.
    """
    r_in = r_out - wall
    solid = (
        cq.Workplane("XY").circle(r_out).extrude(h)
        .faces(">Z").workplane().circle(r_in).cutBlind(-(h - floor))
    )
    expected = {
        "name": "open_cup",
        "undercut_faces": 0,
        "silhouette_radius": r_out,
        "silhouette_area": math.pi * r_out * r_out,
        "r_inner": r_in,
        "r_outer": r_out,
        "floor_z": floor,
        "rim_z": h,
        # (surface_type, radius, expected mold_half)
        "core_faces": [("CYLINDER", r_in), ("PLANE", None)],
        "cavity_faces": [("CYLINDER", r_out)],
    }
    return _export("p2_open_cup", solid), expected


# --------------------------------------------------------------------------
# P3 — cylinder with a radial through-hole. Isolated, unambiguous undercut.
# --------------------------------------------------------------------------
def cylinder_radial_hole(r: float = 25.0, h: float = 40.0, hole_d: float = 8.0,
                         hole_z: float = 20.0):
    """
    A cylinder pierced by a hole whose axis is perpendicular to the pull.

    For a Z pull the hole wall cannot be released: its surface normals point
    radially inward in the XY plane, and both +Z and -Z escapes are blocked by
    the surrounding material. Everything else on the part is convex-releasable.

    Therefore the undercut set is EXACTLY the cylindrical face(s) of the hole,
    identified by having an axis perpendicular to Z.
    """
    solid = cq.Workplane("XY").circle(r).extrude(h)
    hole = cq.Solid.makeCylinder(
        hole_d / 2.0, 4 * r, cq.Vector(-2 * r, 0, hole_z), cq.Vector(1, 0, 0)
    )
    solid = solid.cut(cq.Workplane(obj=hole))
    expected = {
        "name": "cylinder_radial_hole",
        "undercut_axis_perpendicular_to_pull": True,
        "undercut_surface_type": "CYLINDER",
        "hole_radius": hole_d / 2.0,
        "silhouette_radius": r,
        "min_undercut_faces": 1,
        "max_undercut_faces": 2,   # CAD kernels split a through-hole in two
    }
    return _export("p3_cylinder_radial_hole", solid), expected


# --------------------------------------------------------------------------
# P4 — stepped cylinder. Pure silhouette-selection test.
# --------------------------------------------------------------------------
def stepped_cylinder(r_bot: float = 30.0, h_bot: float = 20.0,
                     r_top: float = 15.0, h_top: float = 30.0):
    """
    Two stacked cylinders, large diameter at the bottom.

    No undercuts for a Z pull (every face releases up or down). The only
    interesting question is WHERE the parting line goes: it must lie on the
    maximum silhouette, i.e. radius r_bot, never on the smaller r_top step.

    This is the synthetic analogue of Part3's flange, where our engine put the
    parting line at the flange OD. Here we can check that choice against a
    known answer instead of against an opinion.
    """
    solid = (
        cq.Workplane("XY").circle(r_bot).extrude(h_bot)
        .faces(">Z").workplane().circle(r_top).extrude(h_top)
    )
    expected = {
        "name": "stepped_cylinder",
        "undercut_faces": 0,
        "silhouette_radius": r_bot,       # NOT r_top
        "silhouette_area": math.pi * r_bot * r_bot,
        "wrong_radius": r_top,
        "step_z": h_bot,
    }
    return _export("p4_stepped_cylinder", solid), expected


# --------------------------------------------------------------------------
# P5 — circumferential groove. Synthetic stand-in for Part3's real feature.
# --------------------------------------------------------------------------
def grooved_cylinder(r: float = 25.0, h: float = 40.0, groove_r: float = 20.0,
                     z0: float = 15.0, z1: float = 20.0):
    """
    A cylinder with a full circumferential groove cut into its side.

    A closed groove around the part is a genuine undercut for an axial pull:
      - the lower annulus (normal +Z) is roofed by the material above it
      - the upper annulus (normal -Z) is floored by the material below it
      - the groove floor is a vertical wall blocked BOTH ways
    All three faces are trapped, so this needs a split cavity or a side action.

    This is deliberately the same class of feature as the grooves visible on
    the real Part3, but here the correct answer is known.
    """
    solid = cq.Workplane("XY").circle(r).extrude(h)
    ring = (
        cq.Workplane("XY").workplane(offset=z0)
        .circle(r + 1).circle(groove_r).extrude(z1 - z0)
    )
    solid = solid.cut(ring)
    expected = {
        "name": "grooved_cylinder",
        "undercut_faces": 3,             # 2 annuli + groove floor
        "groove_radius": groove_r,
        "groove_z": (z0, z1),
        "silhouette_radius": r,
        "outer_radius": r,
    }
    return _export("p5_grooved_cylinder", solid), expected


# --------------------------------------------------------------------------
# P6 — plain box. Convex, non-circular silhouette.
# --------------------------------------------------------------------------
def solid_box(x: float = 40.0, y: float = 30.0, z: float = 20.0):
    """
    Convex box: no undercuts in any direction. Silhouette for a Z pull is the
    x-by-y rectangle, so the parting line's projected area is exactly x*y.
    Checks that silhouette area is right for a non-circular outline.
    """
    solid = cq.Workplane("XY").box(x, y, z, centered=(True, True, False))
    expected = {
        "name": "solid_box",
        "undercut_faces": 0,
        "face_count": 6,
        "silhouette_area": x * y,
        "size": (x, y, z),
    }
    return _export("p6_solid_box", solid), expected


# --------------------------------------------------------------------------
# P7 / P8 — flanged boss and the SAME boss without its flange.
# --------------------------------------------------------------------------
def flanged_boss(r_flange: float = 18.0, h_flange: float = 4.0,
                 r_boss: float = 12.5, h_total: float = 40.0):
    """
    Part3's overall massing with none of its features: a wide flange at the
    bottom and a plain cylindrical boss above it.

    No undercuts. The maximum silhouette is the flange OD, so that is where
    the parting line belongs, and the two halves should be substantial —
    the flange underside on one, the boss on the other.

    Paired with `plain_boss` below, this isolates one question: does the
    presence of a wide flange at the bottom skew the core/cavity split?
    Compare the two ratios; only the flange differs.
    """
    solid = (
        cq.Workplane("XY").circle(r_flange).extrude(h_flange)
        .faces(">Z").workplane().circle(r_boss).extrude(h_total - h_flange)
    )
    expected = {
        "name": "flanged_boss",
        "undercut_faces": 0,
        "silhouette_radius": r_flange,
        "r_flange": r_flange,
        "r_boss": r_boss,
        "flange_top_z": h_flange,
    }
    return _export("p7_flanged_boss", solid), expected


def plain_boss(r_boss: float = 12.5, h_total: float = 40.0):
    """The flanged boss with its flange deleted — the control for P7."""
    solid = cq.Workplane("XY").circle(r_boss).extrude(h_total)
    expected = {
        "name": "plain_boss",
        "undercut_faces": 0,
        "silhouette_radius": r_boss,
    }
    return _export("p8_plain_boss", solid), expected


# --------------------------------------------------------------------------
# P9 — closed-top cup. Reachability, not normals.
# --------------------------------------------------------------------------
def capped_cup(r_out: float = 30.0, wall: float = 3.0, h: float = 50.0):
    """
    A cup closed at the top and open at the bottom.

    Same shell as `open_cup` but flipped, so the bore is reachable only from
    below. Nothing here can be decided by normal direction alone: the engine
    has to reason about which end the opening is on. Still a clean draw, so
    the undercut set is empty.
    """
    solid = (
        cq.Workplane("XY").circle(r_out).extrude(h)
        .faces("<Z").workplane().circle(r_out - wall).cutBlind(-(h - wall))
    )
    expected = {
        "name": "capped_cup",
        "undercut_faces": 0,
        "r_inner": r_out - wall,
        "r_outer": r_out,
        "opening_at": "bottom",
    }
    return _export("p9_capped_cup", solid), expected


# --------------------------------------------------------------------------
# P10 — lateral BLIND pocket. Undercut counting precision.
# --------------------------------------------------------------------------
def cylinder_blind_pocket(r: float = 25.0, h: float = 40.0,
                          pocket_d: float = 8.0, depth: float = 6.0,
                          pocket_z: float = 20.0):
    """
    A cylinder with a blind hole drilled radially inward (it does not break
    through). For an axial pull the pocket traps exactly two faces: its
    cylindrical wall and its flat end. A through-hole would trap only walls,
    so this checks the engine counts the floor too and does not over- or
    under-count a bounded recess.
    """
    solid = cq.Workplane("XY").circle(r).extrude(h)
    tool = cq.Solid.makeCylinder(
        pocket_d / 2.0, depth + 1.0,
        cq.Vector(r - depth, 0, pocket_z), cq.Vector(1, 0, 0),
    )
    solid = solid.cut(cq.Workplane(obj=tool))
    expected = {
        "name": "cylinder_blind_pocket",
        "undercut_faces": 2,          # pocket wall + pocket floor
        "pocket_z": pocket_z,
        "outer_radius": r,
    }
    return _export("p10_cylinder_blind_pocket", solid), expected


# --------------------------------------------------------------------------
# P11 — the real Part3 with its undercut volume suppressed.
# --------------------------------------------------------------------------
_PART3 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "assets", "Part3.stp")


def part3_pockets_filled():
    """
    Part3 with its rib pockets filled in — the casting literature's
    "suppression of external undercut volume" step, done by hand.

    The pockets are blind recesses cut from the boss OD (r=12.5) inward to
    r=9.5, in two z-bands separated by a rib, and they do NOT break through
    to the central bore (r~6). Filling them therefore means unioning back an
    annular band that spans the pocket depth while leaving the bore open.

    This is the ground truth for what undercut suppression / shut-off
    generation SHOULD produce, established before building that feature. The
    important property it pins down is that suppressing the undercuts must
    not move the parting line: if the line is genuinely the part's maximum
    silhouette it cannot depend on features that sit well inside it.

    Note the fill is deliberately crude (a plain annulus), so a handful of
    sub-millimetre spline slivers survive at the pocket corner radii where
    the plug meets the original blends. They are fill artifacts, not part
    features, which is why the test below asserts on undercut AREA rather
    than face count.
    """
    name = "p11_part3_pockets_filled"
    expected = {
        "name": name,
        "available": os.path.exists(_PART3),
        "source": _PART3,
        "pl_radius": 18.0,
        "pl_z": 4.0,
        "residual_undercut_area_max": 20.0,   # mm^2, fill slivers only
    }
    if not expected["available"]:
        return None, expected
    if name in _CACHE and os.path.exists(_CACHE[name]):
        return _CACHE[name], expected

    part = cq.importers.importStep(_PART3)
    plug = (cq.Workplane("XY").workplane(offset=11.0)
            .circle(12.5).circle(7.0).extrude(12.0))
    filled = part.union(plug)
    return _export(name, filled), expected


# ------------------------------------------------- P12 nozzle (mentor's sketch)
def oring_nozzle(r_out: float = 20.0, groove_r: float = 14.0,
                 r_bore: float = 8.0, h: float = 40.0,
                 gz0: float = 15.0, gz1: float = 25.0):
    """The nozzle Bosch drew on the Phase 1 review call, with a stated answer.

    Reconstructed from the NX sequence in the recording: revolve about the
    vertical axis, cut a circumferential groove around the waist (the O-ring
    seat), bore through the middle for the fluid.

    This is the only fixture whose answer comes from the customer rather than
    from our own construction. His words:

      "This and these features will become undercut ... if you take Z-axis as
       the molding direction. So we give Y-axis as the molding direction ...
       Parting plane will be this plane. It splits the two halves, and then
       there will be a side core ... the internal wall will be formed by a
       side core."

    So the expected answer is a pull PERPENDICULAR to the part's own axis, a
    parting plane CONTAINING that axis (the clamshell split), and an axial
    side core for the bore. X and Y are interchangeable here because the part
    is axisymmetric.

    The groove is the crux: a 360 degree external recess cannot be released by
    an axial draw at any parting-line height, so no choice of parting line
    rescues a Z pull.
    """
    solid = cq.Workplane("XY").circle(r_out).extrude(h)
    solid = solid.cut(
        cq.Workplane("XY").workplane(offset=gz0)
        .circle(r_out + 1.0).circle(groove_r)
        .extrude(gz1 - gz0)
    )
    solid = solid.cut(cq.Workplane("XY").circle(r_bore).extrude(h))

    expected = {
        "name": "oring_nozzle",
        "part_axis": (0.0, 0.0, 1.0),
        "r_outer": r_out,
        "r_groove": groove_r,
        "r_bore": r_bore,
        "height": h,
        "groove_z": (gz0, gz1),
        # Pull must be perpendicular to the part axis, not along it.
        "pull_is_perpendicular_to_axis": True,
        # The bore is formed by a core running along the part axis.
        "side_action_along_axis": True,
    }
    return _export("p12_oring_nozzle", solid), expected


ALL_PARTS = [
    solid_cylinder,
    open_cup,
    cylinder_radial_hole,
    stepped_cylinder,
    grooved_cylinder,
    solid_box,
    flanged_boss,
    plain_boss,
    capped_cup,
    cylinder_blind_pocket,
    oring_nozzle,
]
