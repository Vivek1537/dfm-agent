"""
core/silhouette.py — subdivide faces at the silhouette before classification.

A face whose normal changes sign across the pull direction is formed by BOTH
mould halves: part of it faces one way, part the other. The classifier can only
hand a whole face to one half, so such a face pins the core/cavity boundary
onto its neighbours instead of letting it run down the middle where it belongs.

This never mattered while every validated part was drawn along its own axis —
Part1 has zero straddling faces under its pull. It matters completely for a
pull perpendicular to the axis: on the nozzle from the Phase 1 review call,
66% of the surface straddles, and the parting line came out as a circle across
the axis rather than the clamshell loop containing it.

The useful geometric fact: for any surface of revolution about an axis `a`,
with pull `d` perpendicular to `a`, the locus n·d = 0 sits at θ = ±90° — which
is exactly the plane containing `a` with normal `d`. So a single planar cut
produces every silhouette on the part at once, and that plane is the clamshell
parting plane a mould designer would draw.

The cut is applied to the SHELL, never the solid. Splitting a solid divides it
into two bodies and injects cross-section faces that are not part surfaces at
all, which corrupts both the undercut count and the parting line.
"""

from typing import Any, List, Optional, Tuple

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.TopTools import TopTools_ListOfShape
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from core.models import FaceData

# A sample counts as facing a half only beyond this; below it the sample is
# parallel to the pull and says nothing about which side forms it.
_STRADDLE_EPS = 0.02

# |axis · pull| below this treats the axis as perpendicular to the pull.
_PERP_EPS = 0.1

# Ignore a trickle of straddling area — a stray blend crossing the silhouette
# is not worth re-parsing the whole shape for.
_MIN_STRADDLE_FRACTION = 0.02


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def straddling_area(faces: List[FaceData],
                    direction: Tuple[float, float, float]) -> float:
    """Surface area whose normal changes sign across `direction`."""
    total = 0.0
    for face in faces:
        normals = face.sample_normals or [face.normal]
        dots = [_dot(n, direction) for n in normals]
        if max(dots) > _STRADDLE_EPS and min(dots) < -_STRADDLE_EPS:
            total += face.area
    return total


def _axis_location(face: FaceData) -> Optional[Tuple[float, float, float]]:
    """A point on a cylindrical/conical face's own axis (not its centroid)."""
    if face.face_shape is None:
        return None
    try:
        surface = BRepAdaptor_Surface(face.face_shape)
        kind = surface.GetType()
        if kind == GeomAbs_Cylinder:
            axis = surface.Cylinder().Axis()
        elif kind == GeomAbs_Cone:
            axis = surface.Cone().Axis()
        else:
            return None
        point = axis.Location()
        return (point.X(), point.Y(), point.Z())
    except Exception:
        return None


def silhouette_plane(
    faces: List[FaceData],
    direction: Tuple[float, float, float],
) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """(point, normal) of the plane carrying the silhouettes, or None.

    Chooses the largest revolved face whose axis is perpendicular to the pull
    and anchors the plane on that face's own axis, not on the part centroid —
    an axis offset from the centroid would otherwise put the cut in the wrong
    place. Returns None when no such axis exists, which is the signal that this
    part is not a perpendicular-pull case and should be left alone.
    """
    best_point = None
    best_area = 0.0
    for face in faces:
        if face.axis is None:
            continue
        if abs(_dot(tuple(face.axis), direction)) > _PERP_EPS:
            continue
        point = _axis_location(face)
        if point is None:
            continue
        if face.area > best_area:
            best_area, best_point = face.area, point
    if best_point is None:
        return None
    return best_point, direction


def split_at_silhouette(
    shape: Any,
    faces: List[FaceData],
    direction: Tuple[float, float, float],
) -> Optional[Any]:
    """Subdivide `shape`'s faces along the silhouette plane.

    Returns the new shape, or None when the split does not apply or fails —
    callers treat None as "carry on with the original shape", so this is always
    safe to attempt.
    """
    total_area = sum(f.area for f in faces)
    if total_area <= 0.0:
        return None
    if straddling_area(faces, direction) / total_area < _MIN_STRADDLE_FRACTION:
        return None                      # nothing meaningful crosses the pull

    plane = silhouette_plane(faces, direction)
    if plane is None:
        return None
    point, normal = plane

    explorer = TopExp_Explorer(shape, TopAbs_SHELL)
    if not explorer.More():
        return None
    shell = TopoDS.Shell_s(explorer.Current())

    # Size the cutting face from the part's own bounds so it spans it fully.
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    x0, y0, z0, x1, y1, z1 = box.Get()
    reach = max(x1 - x0, y1 - y0, z1 - z0) * 2.0 or 100.0

    try:
        plane_geom = gp_Pln(gp_Pnt(*point), gp_Dir(*normal))
        tool = BRepBuilderAPI_MakeFace(
            plane_geom, -reach, reach, -reach, reach
        ).Face()

        arguments = TopTools_ListOfShape()
        arguments.Append(shell)
        tools = TopTools_ListOfShape()
        tools.Append(tool)

        splitter = BRepAlgoAPI_Splitter()
        splitter.SetArguments(arguments)
        splitter.SetTools(tools)
        splitter.Build()
        result = splitter.Shape()
    except Exception:
        return None

    if result is None or result.IsNull():
        return None
    return result
