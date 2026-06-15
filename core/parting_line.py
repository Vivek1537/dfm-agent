"""
core/parting_line.py — Parting Line Extraction Algorithm
"""

from typing import List, Any
from OCP.TopExp import TopExp
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.TopoDS import TopoDS

from core.models import FaceData

from typing import Tuple

def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def find_parting_line(shape: Any, faces: List[FaceData], mold_direction: Tuple[float, float, float]) -> List[Any]:
    """
    Finds the main parting line by identifying edges that are shared by 
    one face facing the core direction and one facing the cavity direction.
    """
    parting_line_edges = []
    
    # Map all edges to their adjacent faces
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)
    
    # Map TopoDS_Face back to our FaceData classification
    for i in range(1, edge_face_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_face_map.FindKey(i))
        adjacent_faces_list = edge_face_map.FindFromIndex(i)
        
        # We only care about edges shared by exactly 2 faces
        if adjacent_faces_list.Extent() == 2:
            face1_topo = TopoDS.Face_s(adjacent_faces_list.First())
            face2_topo = TopoDS.Face_s(adjacent_faces_list.Last())
            
            face1_data = None
            face2_data = None
            
            for f in faces:
                if f.face_shape.IsSame(face1_topo):
                    face1_data = f
                elif f.face_shape.IsSame(face2_topo):
                    face2_data = f
                
                if face1_data and face2_data:
                    break
                    
            if face1_data and face2_data:
                dot1 = _dot(face1_data.normal, mold_direction)
                dot2 = _dot(face2_data.normal, mold_direction)
                
                # If one is >= 0 (cavity-facing) and one is < 0 (core-facing)
                if (dot1 >= 0 and dot2 < 0) or (dot1 < 0 and dot2 >= 0):
                    parting_line_edges.append(edge)
                    
    return parting_line_edges
