"""
core/step_parser.py — Read a STEP file and extract face geometry.

Reads a .stp/.step file using OCP (OpenCASCADE via CadQuery) and returns
a List[FaceData] with each face's shape, outward normal, area, and surface type.

Surface normal extraction per type:
  PLANE      → Z-axis of the plane's coordinate system
  CYLINDER   → radial direction at face centroid
  CONE       → radial direction at face centroid (adjusted for half-angle)
  SPHERE     → radial direction from center to face centroid
  TORUS      → computed via surface derivatives at UV midpoint
  BSPLINE    → computed via surface derivatives at UV midpoint
"""

import math
from typing import List, Tuple, Any

from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import (
    GeomAbs_Plane,
    GeomAbs_Cylinder,
    GeomAbs_Cone,
    GeomAbs_Sphere,
    GeomAbs_Torus,
    GeomAbs_BSplineSurface,
    GeomAbs_BezierSurface,
)
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.TopoDS import TopoDS
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.gp import gp_Pnt2d
from OCP.TopAbs import TopAbs_IN, TopAbs_ON

from core.models import FaceData


# ── Surface type label mapping ──────────────────────────────────────
_SURFACE_TYPE_MAP = {
    GeomAbs_Plane: "PLANE",
    GeomAbs_Cylinder: "CYLINDER",
    GeomAbs_Cone: "CONE",
    GeomAbs_Sphere: "SPHERE",
    GeomAbs_Torus: "TORUS",
    GeomAbs_BSplineSurface: "BSPLINE",
    GeomAbs_BezierSurface: "BEZIER",
}


def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Normalize a 3D vector to unit length. Returns (0,0,0) for zero vectors."""
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _get_face_normal(face, adaptor: BRepAdaptor_Surface) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Extract the outward surface normal at the UV midpoint of a face.

    Uses GeomLProp_SLProps with the underlying Geom_Surface for robust
    normal computation across all surface types.
    """
    u_min = adaptor.FirstUParameter()
    u_max = adaptor.LastUParameter()
    v_min = adaptor.FirstVParameter()
    v_max = adaptor.LastVParameter()

    # Clamp infinite parameters (some surfaces have unbounded UV domains)
    u_min = max(u_min, -1e6)
    u_max = min(u_max, 1e6)
    v_min = max(v_min, -1e6)
    v_max = min(v_max, 1e6)

    u_mid = (u_min + u_max) / 2.0
    v_mid = (v_min + v_max) / 2.0

    classifier = BRepClass_FaceClassifier()
    classifier.Perform(face, gp_Pnt2d(u_mid, v_mid), 1e-6)
    
    # If midpoint is in a hole or outside the trimmed face, search for a valid point
    if classifier.State() != TopAbs_IN:
        found = False
        for steps in (10, 50):  # Coarse then dense grid
            if found: break
            for i in range(1, steps):
                u = u_min + (u_max - u_min) * (i / float(steps))
                for j in range(1, steps):
                    v = v_min + (v_max - v_min) * (j / float(steps))
                    classifier.Perform(face, gp_Pnt2d(u, v), 1e-6)
                    if classifier.State() == TopAbs_IN:
                        u_mid, v_mid = u, v
                        found = True
                        break
                if found: break

    # Extract the underlying Geom_Surface from the TopoDS_Face
    geom_surface = BRep_Tool.Surface_s(face)

    # GeomLProp_SLProps: order=1 gives us the normal, tolerance for singularities
    props = GeomLProp_SLProps(geom_surface, u_mid, v_mid, 1, 1e-6)

    if props.IsNormalDefined():
        n = props.Normal()
        pnt = props.Value()
        return ((n.X(), n.Y(), n.Z()), (pnt.X(), pnt.Y(), pnt.Z()))

    # Fallback: try a slight offset from center (some surfaces are singular at center)
    u_off = u_min + (u_max - u_min) * 0.51
    v_off = v_min + (v_max - v_min) * 0.51
    props2 = GeomLProp_SLProps(geom_surface, u_off, v_off, 1, 1e-6)
    if props2.IsNormalDefined():
        n = props2.Normal()
        pnt = props2.Value()
        return ((n.X(), n.Y(), n.Z()), (pnt.X(), pnt.Y(), pnt.Z()))

    # Last resort: return zero normal (face will be flagged as warning)
    # Return (0,0,0) for normal, and evaluate center point normally
    pnt = geom_surface.Value(u_mid, v_mid)
    return ((0.0, 0.0, 0.0), (pnt.X(), pnt.Y(), pnt.Z()))


def _get_face_area(face) -> float:
    """Compute the surface area of a face in mm² using BRepGProp."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


def _get_surface_type_label(adaptor: BRepAdaptor_Surface) -> str:
    """Map OCP surface type enum to a human-readable string."""
    stype = adaptor.GetType()
    return _SURFACE_TYPE_MAP.get(stype, "OTHER")


def parse_step(filepath: str) -> Tuple[List[FaceData], Any]:
    """
    Parse a STEP file and return a list of FaceData for every face.

    Args:
        filepath: Path to .stp or .step file.

    Returns:
        Tuple containing:
        - List of FaceData with face_shape, normal, area, and surface_type populated.
        - The raw TopoDS_Shape representing the entire solid.

    Raises:
        RuntimeError: If the STEP file cannot be read.
    """
    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != 1:  # IFSelect_RetDone = 1
        raise RuntimeError(f"Failed to read STEP file: {filepath} (status={status})")

    reader.TransferRoots()
    shape = reader.OneShape()

    faces: List[FaceData] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0

    while explorer.More():
        topo_face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(topo_face)

        # Check face orientation — if reversed, flip the normal
        is_reversed = topo_face.Orientation() == 1  # TopAbs_REVERSED = 1

        # Extract normal and center at UV midpoint
        raw_normal, center = _get_face_normal(topo_face, adaptor)
        if is_reversed:
            raw_normal = (-raw_normal[0], -raw_normal[1], -raw_normal[2])

        normal = _normalize(raw_normal)

        # Extract area and surface type
        area = _get_face_area(topo_face)
        surface_type = _get_surface_type_label(adaptor)

        face_data = FaceData(
            face_id=face_id,
            face_shape=topo_face,
            center=center,
            normal=normal,
            area=area,
            surface_type=surface_type,
        )
        faces.append(face_data)

        face_id += 1
        explorer.Next()

    return faces, shape


if __name__ == "__main__":
    import os
    import sys

    # Default to the provided Part1.stp
    stp_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("assets", "Part1.stp")

    print(f"Parsing: {stp_path}")
    faces, shape = parse_step(stp_path)
    print(f"Total faces extracted: {len(faces)}")

    # Surface type breakdown
    type_counts: dict = {}
    for f in faces:
        type_counts[f.surface_type] = type_counts.get(f.surface_type, 0) + 1

    print("\nSurface type breakdown:")
    for stype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {stype:20s} {count:4d}")

    # Area statistics
    total_area = sum(f.area for f in faces)
    print(f"\nTotal surface area: {total_area:.2f} mm²")

    # Show first 5 faces as sample
    print("\nSample faces (first 5):")
    for f in faces[:5]:
        print(f"  Face {f.face_id:3d}: type={f.surface_type:10s}  "
              f"normal=({f.normal[0]:+.3f}, {f.normal[1]:+.3f}, {f.normal[2]:+.3f})  "
              f"area={f.area:.3f} mm²")

    # Validate we got the expected 311 faces
    if len(faces) == 311:
        print("\n✅ step_parser.py — 311 faces extracted (matches expected count)")
    else:
        print(f"\n⚠️  Expected 311 faces, got {len(faces)}")
