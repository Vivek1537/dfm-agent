"""
core/undercut_detector.py — Flag faces that are undercut using raycasting.

A true undercut in injection molding is a face that is physically trapped
and cannot be pulled out by either the Cavity or the Core mold half.

We determine this by:
1. Identifying which mold half the face belongs to (based on its normal).
2. Casting a ray from the face's center in its pull direction.
3. If the ray hits another part of the solid beyond the wall thickness,
   the face is a true undercut.
"""

from typing import List, Tuple

from core.models import FaceData

# OCP imports for raycasting
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin, gp_Dir, gp_Pnt

# Minimum ray hit distance (mm). Hits closer than this are treated as
# wall-thickness artifacts (e.g., inner face → shell wall → outer face)
# and NOT counted as true undercuts.
MIN_HIT_DISTANCE = 2.0


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
    If it hits the solid beyond MIN_HIT_DISTANCE, it's trapped (undercut).
    """
    if not faces:
        return faces

    # Build a single Compound shape containing all faces
    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    has_shapes = False
    for f in faces:
        if f.face_shape is not None:
            builder.Add(comp, f.face_shape)
            has_shapes = True

    if not has_shapes:
        # Fallback for synthetic/non-geometry tests
        for face in faces:
            dot_val = _dot(face.normal, mold_direction)
            face.is_undercut = dot_val < -0.01
        return faces

    # Initialize the raycaster
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(comp, 1e-6)

    for face in faces:
        dot_val = _dot(face.normal, mold_direction)

        def is_trapped_in_dir(p_dir: Tuple[float, float, float]) -> bool:
            epsilon = 0.1
            ox = face.center[0] + face.normal[0] * epsilon
            oy = face.center[1] + face.normal[1] * epsilon
            oz = face.center[2] + face.normal[2] * epsilon
            ray_origin = gp_Pnt(ox, oy, oz)
            ray_vec = gp_Dir(p_dir[0], p_dir[1], p_dir[2])
            line = gp_Lin(ray_origin, ray_vec)
            try:
                intersector.Perform(line, 1e-4, 1000.0)
                for i in range(1, intersector.NbPnt() + 1):
                    if intersector.WParameter(i) >= MIN_HIT_DISTANCE:
                        return True
            except Exception:
                pass
            return False

        # Determine which mold half this face is trying to pull with
        if dot_val > 0.01:
            face.is_undercut = is_trapped_in_dir(mold_direction)
        elif dot_val < -0.01:
            neg_dir = (-mold_direction[0], -mold_direction[1], -mold_direction[2])
            face.is_undercut = is_trapped_in_dir(neg_dir)
        else:
            # Near-perpendicular wall (within ~0.6° of parting plane).
            # Use a CONSISTENT direction (always mold_direction) so that
            # mirror-symmetric faces get identical treatment — no floating
            # point sign-bit asymmetry.
            face.is_undercut = is_trapped_in_dir(mold_direction)

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
