"""
core/parting/silhouette.py — Silhouette assistance (specification section 10).

WHY THIS EXISTS
---------------
Mold-region classification is per FACE, and the boundary between regions can
therefore only ever run along edges the B-rep already has. For most parts that
is right: the pull is along the part's dominant axis, the split falls on a rim,
and a rim is an edge.

It is wrong whenever the pull runs ACROSS the part's axis. Then the split is a
clamshell — a plane containing the axis — and it passes straight through the
middle of the outer wall, where there is no edge at all. A cylinder pulled
sideways is formed half by the core and half by the cavity, and no per-face
label can say that.

The symptom is unmistakable once you look for it. On the O-ring nozzle and the
grooved cylinder, both of which the direction search correctly pulls
perpendicular to their axis, every candidate loop the topological path
produces has a projected area of exactly 0.0 — they are circles lying in
planes parallel to the pull, which project to line segments. The engine then
picked whichever of those internal groove edges scored highest and reported it
as the parting line with no indication anything was wrong. Bosch drew this
exact part on the review call and stated the answer: "Parting plane will be
this plane. It splits the two halves."

WHAT THIS DOES
--------------
For a pull direction D, the silhouette of a face is the curve where the
surface normal is perpendicular to D — the horizon, where the surface turns
away from the mold. That curve IS the parting line on such a face, and it is
what this module extracts.

Following the specification, the silhouette does NOT replace topological
classification. It runs only when the topological result fails validation, and
its curves are added to the candidate edge set so the loop builder can chain
them together with real edges. On a part whose parting line is already a
proper rim, nothing here is invoked and nothing changes.

SCOPE
-----
Analytic silhouettes are computed for the surface types where they are exact
and cheap: cylinders and cones, which is what turned and moulded parts are
mostly made of, and planes (a plane parallel to the pull is entirely
silhouette; any other plane has none). Free-form surfaces are reported as
unsupported rather than approximated, so a part that needs one is told so
instead of being given a plausible-looking wrong answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane
from OCP.gp import gp_Pnt, gp_Pnt2d

from core.models import FaceData
from core.parting.models import (
    EDGE_PARTING,
    EDGE_SHUTOFF,
    BoundaryEdge,
    Vector3,
    cross,
    dot,
    norm,
)
from core.tolerances import AnalysisConfig, resolve


@dataclass
class SilhouetteCurve:
    """One silhouette curve found on one face."""

    face_id: int
    points: List[Vector3]
    surface_type: str
    # True when the curve was computed exactly, False when it is a sampled
    # approximation whose accuracy depends on the sampling density.
    exact: bool = True


# Points sampled along an analytic silhouette line. A straight generator on a
# cylinder needs only its two ends, but extra points let the loop builder's
# tangent-following traversal behave sensibly where curves meet.
_SILHOUETTE_SAMPLES = 9


def _uv_is_inside(face: Any, u: float, v: float, tol: float = 1e-6) -> bool:
    """True when a UV point lies inside the face's trimmed region."""
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    classifier = BRepClass_FaceClassifier()
    classifier.Perform(face, gp_Pnt2d(u, v), tol)
    return classifier.State() in (TopAbs_IN, TopAbs_ON)


# Bisection steps used to pin a run's end to the face's real trim boundary.
# 24 halvings resolve a 100 mm sweep to about 6e-6 mm, comfortably inside
# EDGE_MATCH_TOLERANCE.
_REFINE_STEPS = 24


def _clip_runs(
    is_inside,
    t0: float,
    t1: float,
    steps: int,
) -> List[Tuple[float, float]]:
    """Parameter intervals where `is_inside` holds, with refined endpoints.

    A coarse scan finds the runs; each boundary is then bisected between the
    last inside sample and the first outside one so the interval ends ON the
    face's trim rather than at whichever sample happened to be nearest.

    That refinement is not cosmetic. A silhouette segment across a disc has to
    meet the cylinder generator rising from its rim, and the loop graph joins
    endpoints by exact tolerance-matched coordinates. Unrefined, the segment
    stopped half a millimetre short of the rim, the two never shared a vertex,
    and a clamshell parting line came apart into a dozen open chains.

    Multiple runs are expected and correct: the line across an annular groove
    wall enters and leaves the material twice, once on each side of the bore.
    """
    if steps < 2 or t1 <= t0:
        return []

    def sample(i: int) -> float:
        return t0 + (t1 - t0) * i / steps

    def refine(t_in: float, t_out: float) -> float:
        for _ in range(_REFINE_STEPS):
            mid = 0.5 * (t_in + t_out)
            if is_inside(mid):
                t_in = mid
            else:
                t_out = mid
        return t_in

    runs: List[Tuple[float, float]] = []
    start: Optional[float] = None
    prev_t = sample(0)
    prev_in = is_inside(prev_t)
    if prev_in:
        start = prev_t

    for i in range(1, steps + 1):
        t = sample(i)
        inside = is_inside(t)
        if inside and not prev_in:
            start = refine(t, prev_t)
        elif prev_in and not inside:
            if start is not None:
                runs.append((start, refine(prev_t, t)))
            start = None
        prev_t, prev_in = t, inside

    if prev_in and start is not None:
        runs.append((start, prev_t))
    return runs


def _cylinder_silhouette(
    face: FaceData, adaptor: BRepAdaptor_Surface, pull: Vector3
) -> List[SilhouetteCurve]:
    """The two generator lines where a cylinder turns away from the pull.

    A cylinder's normal is radial. It is perpendicular to the pull exactly
    where the radial direction is perpendicular to the pull, which happens at
    two diametrically opposite angles — the two straight generators that form
    the cylinder's outline when viewed along the pull. Those generators are
    the parting line on this face.

    Returns nothing when the cylinder's axis is parallel to the pull: then the
    whole surface draws cleanly and there is no horizon on it.
    """
    cyl = adaptor.Cylinder()
    axis_dir = cyl.Axis().Direction()
    axis = norm((axis_dir.X(), axis_dir.Y(), axis_dir.Z()))

    # Axis along the pull: every normal is perpendicular to the pull, so the
    # whole face is "silhouette" and none of it is a parting curve.
    if abs(dot(axis, pull)) > 0.999:
        return []

    # The radial direction perpendicular to BOTH the axis and the pull. The
    # two silhouette generators sit at +/- this direction from the axis.
    radial = cross(axis, pull)
    if math.sqrt(sum(c * c for c in radial)) < 1e-9:
        return []
    radial = norm(radial)

    surface = adaptor.Cylinder()
    ref = surface.Position()
    x_dir = ref.XDirection()
    y_dir = ref.YDirection()
    x_vec = (x_dir.X(), x_dir.Y(), x_dir.Z())
    y_vec = (y_dir.X(), y_dir.Y(), y_dir.Z())

    v_min = adaptor.FirstVParameter()
    v_max = adaptor.LastVParameter()
    if not (math.isfinite(v_min) and math.isfinite(v_max)):
        return []

    return _generator_curves(
        face, adaptor, radial, x_vec, y_vec, v_min, v_max, "CYLINDER"
    )


def _cone_silhouette(
    face: FaceData, adaptor: BRepAdaptor_Surface, pull: Vector3
) -> List[SilhouetteCurve]:
    """Silhouette generators of a cone, by the same construction as a cylinder.

    A cone's normal tilts by the half-angle away from radial, so the exact
    silhouette angle differs from the cylinder case; the generators are still
    the two the outline runs along, and for the half-angles that occur on
    moulded parts (draft, chamfers) the difference is well under the
    classification tolerance.
    """
    cone = adaptor.Cone()
    axis_dir = cone.Axis().Direction()
    axis = norm((axis_dir.X(), axis_dir.Y(), axis_dir.Z()))
    if abs(dot(axis, pull)) > 0.999:
        return []

    radial = cross(axis, pull)
    if math.sqrt(sum(c * c for c in radial)) < 1e-9:
        return []
    radial = norm(radial)

    ref = cone.Position()
    x_dir, y_dir = ref.XDirection(), ref.YDirection()
    x_vec = (x_dir.X(), x_dir.Y(), x_dir.Z())
    y_vec = (y_dir.X(), y_dir.Y(), y_dir.Z())

    v_min, v_max = adaptor.FirstVParameter(), adaptor.LastVParameter()
    if not (math.isfinite(v_min) and math.isfinite(v_max)):
        return []

    return _generator_curves(
        face, adaptor, radial, x_vec, y_vec, v_min, v_max, "CONE"
    )


def _generator_curves(
    face: FaceData,
    adaptor: BRepAdaptor_Surface,
    radial: Vector3,
    x_vec: Vector3,
    y_vec: Vector3,
    v_min: float,
    v_max: float,
    label: str,
) -> List[SilhouetteCurve]:
    """The two silhouette generators of a surface of revolution.

    Shared by the cylinder and cone cases: both have their horizon at the two
    diametrically opposite angles where the radial direction is perpendicular
    to the pull, and both are parametrised with U around the axis and V along
    it. Runs are clipped to the trim with refined endpoints so a generator
    meets the face edges above and below it exactly.
    """
    curves: List[SilhouetteCurve] = []
    for sign in (1.0, -1.0):
        target = (radial[0] * sign, radial[1] * sign, radial[2] * sign)
        u = math.atan2(dot(target, y_vec), dot(target, x_vec)) % (2.0 * math.pi)

        def inside(v: float, _u=u) -> bool:
            return _uv_is_inside(face.face_shape, _u, v)

        for v_start, v_end in _clip_runs(inside, v_min, v_max, 64):
            pts: List[Vector3] = []
            for i in range(_SILHOUETTE_SAMPLES):
                v = v_start + (v_end - v_start) * i / (_SILHOUETTE_SAMPLES - 1)
                p = adaptor.Value(u, v)
                pts.append((p.X(), p.Y(), p.Z()))
            if len(pts) >= 2:
                curves.append(
                    SilhouetteCurve(face.face_id, pts, label, exact=True)
                )
    return curves


def _plane_silhouette(
    face: FaceData,
    adaptor: BRepAdaptor_Surface,
    pull: Vector3,
    plane_point: Vector3,
) -> List[SilhouetteCurve]:
    """Where the parting plane crosses a face that is parallel to the pull.

    A plane whose normal is perpendicular to the pull stands edge-on to the
    mold: neither half faces it, and the split runs straight across it. This
    is the case the clamshell needs. On a cylinder pulled sideways, the two
    silhouette generators climb the wall and then have to get from one side of
    the part to the other — they do it across the end faces, along exactly
    this line. Without it the loop can never close and the fallback produces
    nothing.

    The line is the intersection of the face's own plane with the parting
    plane (normal `pull`, through `plane_point`). It is then clipped to the
    face's trimmed region, which may leave SEVERAL segments: the line across
    an annular groove wall crosses it twice, once on each side.

    Returns nothing for a plane that faces the mold — such a face is formed
    cleanly by one half and carries no horizon.
    """
    plane = adaptor.Plane()
    n_dir = plane.Axis().Direction()
    n = norm((n_dir.X(), n_dir.Y(), n_dir.Z()))

    # Facing the mold rather than standing edge-on: no horizon here.
    if abs(dot(n, pull)) > 0.01:
        return []

    line_dir = cross(n, pull)
    if math.sqrt(sum(c * c for c in line_dir)) < 1e-9:
        return []
    line_dir = norm(line_dir)

    pos = plane.Position()
    loc = pos.Location()
    origin = (loc.X(), loc.Y(), loc.Z())
    x_dir, y_dir = pos.XDirection(), pos.YDirection()
    x_vec = (x_dir.X(), x_dir.Y(), x_dir.Z())
    y_vec = (y_dir.X(), y_dir.Y(), y_dir.Z())

    # A point on the intersection line: start from the face's own origin and
    # slide along the in-plane direction perpendicular to the line until the
    # parting plane is met.
    across = cross(n, line_dir)
    denom = dot(across, pull)
    if abs(denom) < 1e-12:
        return []
    offset = dot(
        (plane_point[0] - origin[0],
         plane_point[1] - origin[1],
         plane_point[2] - origin[2]),
        pull,
    ) / denom
    base = (
        origin[0] + across[0] * offset,
        origin[1] + across[1] * offset,
        origin[2] + across[2] * offset,
    )

    # Sweep the line across the face's parametric extent and keep the runs
    # that fall inside the trim.
    u_min, u_max = adaptor.FirstUParameter(), adaptor.LastUParameter()
    v_min, v_max = adaptor.FirstVParameter(), adaptor.LastVParameter()
    if not all(math.isfinite(x) for x in (u_min, u_max, v_min, v_max)):
        return []
    reach = max(abs(u_min), abs(u_max), abs(v_min), abs(v_max)) * 2.0
    if reach <= 0.0:
        return []

    def point_at(t: float) -> Vector3:
        return (
            base[0] + line_dir[0] * t,
            base[1] + line_dir[1] * t,
            base[2] + line_dir[2] * t,
        )

    def inside(t: float) -> bool:
        p = point_at(t)
        rel = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
        return _uv_is_inside(face.face_shape, dot(rel, x_vec), dot(rel, y_vec))

    curves: List[SilhouetteCurve] = []
    for t_start, t_end in _clip_runs(inside, -reach, reach, 200):
        pts = [
            point_at(t_start + (t_end - t_start) * i / (_SILHOUETTE_SAMPLES - 1))
            for i in range(_SILHOUETTE_SAMPLES)
        ]
        curves.append(SilhouetteCurve(face.face_id, pts, "PLANE", exact=True))
    return curves


def face_silhouette(
    face: FaceData,
    pull: Vector3,
    plane_point: Vector3 = (0.0, 0.0, 0.0),
    config: Optional[AnalysisConfig] = None,
) -> List[SilhouetteCurve]:
    """Silhouette curves on one face for the given pull direction.

    Empty when the face has no horizon (it faces the mold cleanly), and empty
    when the surface type is not one this module handles exactly.

    `plane_point` positions the parting plane along the pull axis; it only
    affects planar faces, where the split has to be placed rather than derived.
    """
    resolve(config)
    if face.face_shape is None:
        return []
    try:
        adaptor = BRepAdaptor_Surface(face.face_shape)
        stype = adaptor.GetType()
    except Exception:
        return []

    if stype == GeomAbs_Cylinder:
        return _cylinder_silhouette(face, adaptor, pull)
    if stype == GeomAbs_Cone:
        return _cone_silhouette(face, adaptor, pull)
    if stype == GeomAbs_Plane:
        return _plane_silhouette(face, adaptor, pull, plane_point)
    return []


def unsupported_faces(faces: Sequence[FaceData], pull: Vector3) -> List[int]:
    """Face ids whose silhouette this module cannot compute exactly.

    Reported so validation can say "this part needs silhouette curves on N
    free-form faces that are not supported" rather than quietly returning a
    boundary with holes in it.
    """
    out: List[int] = []
    for f in faces:
        if f.surface_type in ("PLANE", "CYLINDER", "CONE"):
            continue
        # Only faces that actually straddle the horizon matter: one whose
        # samples all face the same way has no silhouette on it.
        normals = f.sample_normals or [f.normal]
        signs = {1 if dot(n, pull) > 0 else -1 for n in normals}
        if len(signs) > 1:
            out.append(f.face_id)
    return out


def _make_edge(points: Sequence[Vector3]) -> Optional[Any]:
    """A TopoDS_Edge spanning a sampled curve's endpoints.

    The loop builder needs a real edge to hang geometry on. Silhouette curves
    handled here are straight generators, so a straight edge between the ends
    reproduces them exactly.
    """
    if len(points) < 2:
        return None
    try:
        maker = BRepBuilderAPI_MakeEdge(
            gp_Pnt(*points[0]), gp_Pnt(*points[-1])
        )
        if not maker.IsDone():
            return None
        return maker.Edge()
    except Exception:
        return None


def silhouette_boundary_edges(
    faces: Sequence[FaceData],
    pull: Vector3,
    config: Optional[AnalysisConfig] = None,
    shape: Any = None,
) -> Tuple[List[BoundaryEdge], List[int]]:
    """Silhouette curves for a whole part, as boundary edges.

    Returns (edges, unsupported_face_ids). The edges are tagged
    `source="silhouette"` so a loop built from them is reported as such and
    never mistaken for one the B-rep already contained.
    """
    cfg = resolve(config)
    out: List[BoundaryEdge] = []
    plane_point = _parting_plane_point(faces, pull, shape)

    for face in faces:
        for curve in face_silhouette(face, pull, plane_point, cfg):
            edge = _make_edge(curve.points)
            if edge is None:
                continue
            length = math.dist(curve.points[0], curve.points[-1])
            if length < cfg.min_edge_length:
                continue
            out.append(
                BoundaryEdge(
                    edge=edge,
                    # A trapped face is formed by a side action, so its
                    # horizon is a SHUTOFF -- the surface where that action
                    # meets the main halves -- not main parting line.
                    #
                    # It is still emitted, because it is what closes the loop.
                    # On the O-ring nozzle the split runs down the outer wall,
                    # across each end face, and is then interrupted by the
                    # through bore that a side core forms; without the bore's
                    # shutoff the profile stays two open chains. In the real
                    # mold the side core's shutoff face closes exactly that
                    # gap, so including it is what the tooling does. It is
                    # tagged so the result can say how much of the loop is
                    # shutoff rather than quietly counting it as parting line.
                    kind=EDGE_SHUTOFF if face.is_undercut else EDGE_PARTING,
                    length=length,
                    face_ids=(face.face_id,),
                    regions=(),
                    # A silhouette curve splits ONE face between the halves,
                    # so by construction it has core on one side and cavity on
                    # the other. Stating that lets validation's
                    # separates_core_and_cavity check see a clamshell loop for
                    # what it is.
                    halves=("core", "cavity"),
                    source="silhouette",
                )
            )

    return out, unsupported_faces(faces, pull)


def _parting_plane_point(
    faces: Sequence[FaceData], pull: Vector3, shape: Any = None
) -> Vector3:
    """Where along the pull axis to place the parting plane.

    The centre of the part's bounding box. For the clamshell case that is the
    plane through the part's own axis, which is where a mold designer puts the
    split: it maximises the projected footprint and gives both halves an equal
    draw.

    Taken from the kernel's bounding box rather than from the surface samples,
    because sample-derived centres are not trustworthy here. A UV grid on a
    cylinder is not rotationally symmetric — five samples land at 0.63, 1.88,
    3.14, 4.40 and 5.65 radians, whose average is nowhere near the axis — so
    the sample centroid of a perfectly symmetric part sits well off centre. On
    the grooved cylinder that put the parting plane several millimetres off
    axis, far enough that the plane segments missed the cylinder generators
    and the loop could never close.
    """
    if shape is not None:
        try:
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib

            box = Bnd_Box()
            BRepBndLib.Add_s(shape, box)
            xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
            return (
                0.5 * (xmin + xmax),
                0.5 * (ymin + ymax),
                0.5 * (zmin + zmax),
            )
        except Exception:
            pass

    # Fallback: midpoint of the sample EXTREMES, which is immune to the
    # averaging bias above because the extremes come in antipodal pairs.
    pts = [p for f in faces for p in (f.sample_points or [f.center])]
    if not pts:
        return (0.0, 0.0, 0.0)
    return tuple(
        0.5 * (min(p[i] for p in pts) + max(p[i] for p in pts)) for i in range(3)
    )
