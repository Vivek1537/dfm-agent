"""
core/undercut_detector.py — Flag faces that are undercut using raycasting.

A true undercut in injection molding is a face that is physically trapped
and cannot be pulled out by either the Cavity or the Core mold half.

We determine this by:
1. Identifying which mold half the face belongs to (based on its normal).
2. Casting a ray from the face's center in its pull direction.
3. If the ray hits another part of the solid, the face is an undercut.
"""

from typing import List, Tuple

from core.models import FaceData

# OCP imports for raycasting
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin, gp_Dir, gp_Pnt


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def detect_undercuts(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> List[FaceData]:
    """
    Flag each face as undercut using physical raycasting.

    Cavity pulls in `mold_direction`. Core pulls in `-mold_direction`.
    If a face points towards Cavity, we cast a ray in `mold_direction`.
    If it hits the solid, it's trapped (undercut).
    """
    if not faces:
        return faces

    # Build a single Compound shape containing all faces
    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    for f in faces:
        if f.face_shape:
            builder.Add(comp, f.face_shape)

    # Initialize the raycaster
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(comp, 1e-6)

    for face in faces:
        dot_val = _dot(face.normal, mold_direction)

        # Determine which mold half this face is trying to pull with
        if dot_val >= 0:
            pull_dir = mold_direction
        else:
            pull_dir = (-mold_direction[0], -mold_direction[1], -mold_direction[2])

        # Cast ray
        ray_origin = gp_Pnt(face.center[0], face.center[1], face.center[2])
        ray_vec = gp_Dir(pull_dir[0], pull_dir[1], pull_dir[2])
        line = gp_Lin(ray_origin, ray_vec)

        # Offset start by 1e-4 to avoid hitting the face itself
        intersector.Perform(line, 1e-4, 1000.0)

        # If it hits anything, it's trapped
        face.is_undercut = (intersector.NbPnt() > 0)

    return faces


def get_undercut_summary(faces: List[FaceData]) -> dict:
    undercut_faces = [f for f in faces if f.is_undercut]
    total_area = sum(f.area for f in faces)
    undercut_area = sum(f.area for f in undercut_faces)

    return {
        "total_faces": len(faces),
        "undercut_count": len(undercut_faces),
        "undercut_area": undercut_area,
        "undercut_percentage": (undercut_area / total_area * 100) if total_area > 0 else 0.0,
    }


if __name__ == "__main__":
    import os
    import sys
    from core.step_parser import parse_step

    stp_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("assets", "Part1.stp")
    faces = parse_step(stp_path)
    direction = (0.0, 0.0, 1.0) # Assume Z+ for test
    detect_undercuts(faces, direction)
    summary = get_undercut_summary(faces)
    print(f"Undercuts (Raycast): {summary['undercut_count']} / {summary['total_faces']}")
