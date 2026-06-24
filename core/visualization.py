import cadquery as cq
import pyvista as pv
import plotly.graph_objects as go
import numpy as np
from typing import List, Any
from core.models import FaceData

# Colors for different classifications
COLORS = {
    "core": "lightgrey",
    "cavity": "lightgrey",
    "undercut": "red",
    "warning": "lightgrey",
    "": "lightgrey"  # unclassified / fallback
}

def create_interactive_3d(faces: List[FaceData], parting_line_edges: List[Any]) -> go.Figure:
    """
    Renders the faces and parting line as a Plotly Figure.
    This is 100% thread-safe for Streamlit.
    """
    fig = go.Figure()
    
    # 1. Plot faces
    for face_data in faces:
        if not face_data.face_shape:
            continue
            
        try:
            cq_face = cq.Face(face_data.face_shape)
            vertices, triangles = cq_face.tessellate(0.1)
            
            if not vertices or not triangles:
                continue
                
            x = [v.x for v in vertices]
            y = [v.y for v in vertices]
            z = [v.z for v in vertices]
            
            i = [t[0] for t in triangles]
            j = [t[1] for t in triangles]
            k = [t[2] for t in triangles]
            
            color = COLORS.get(face_data.classification, "white")
            
            fig.add_trace(go.Mesh3d(
                x=x, y=y, z=z,
                i=i, j=j, k=k,
                color=color,
                opacity=1.0,
                flatshading=True,
                name=face_data.classification.capitalize(),
                showscale=False
            ))
        except Exception:
            pass

    # 2. Plot Parting Line Edges
    if parting_line_edges:
        for edge in parting_line_edges:
            try:
                cq_edge = cq.Edge(edge)
                pts = cq_edge.tessellate(0.1)
                if len(pts) > 1:
                    x = [v.x for v in pts]
                    y = [v.y for v in pts]
                    z = [v.z for v in pts]
                    fig.add_trace(go.Scatter3d(
                        x=x, y=y, z=z,
                        mode='lines',
                        line=dict(color='cyan', width=8),
                        name='Parting Line',
                        showlegend=False
                    ))
            except Exception:
                pass
                
    fig.update_layout(
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            aspectmode='data'
        ),
        paper_bgcolor="#0b0f19",
        plot_bgcolor="#0b0f19",
        margin=dict(l=0, r=0, t=0, b=0)
    )
    return fig

