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

def create_3d_snapshot(faces: List[FaceData], parting_line_edges: List[Any], output_path: str = "assets/snapshot.png"):
    """
    Renders the faces in PyVista and exports a static PNG for the PDF report.
    (PyVista screenshot doesn't require asyncio/trame, so it's thread-safe).
    """
    plotter = pv.Plotter(off_screen=True)
    
    # 1. Plot faces
    for face_data in faces:
        if not face_data.face_shape:
            continue
        try:
            cq_face = cq.Face(face_data.face_shape)
            vertices, triangles = cq_face.tessellate(0.1)
            if not vertices or not triangles:
                continue
            pts = np.array([[v.x, v.y, v.z] for v in vertices])
            faces_arr = np.empty((len(triangles), 4), dtype=int)
            faces_arr[:, 0] = 3
            faces_arr[:, 1:] = triangles
            
            mesh = pv.PolyData(pts, faces_arr.flatten())
            color = COLORS.get(face_data.classification, "white")
            plotter.add_mesh(mesh, color=color, show_edges=True, edge_color="black", line_width=1, specular=0.1, diffuse=0.9)
        except Exception:
            pass
            
    # 2. Plot Parting Line Edges
    if parting_line_edges:
        for edge in parting_line_edges:
            try:
                cq_edge = cq.Edge(edge)
                pts = cq_edge.tessellate(0.1)
                if len(pts) > 1:
                    points = np.array([[v.x, v.y, v.z] for v in pts])
                    lines = np.hstack(([len(points)], np.arange(len(points))))
                    line_mesh = pv.PolyData(points)
                    line_mesh.lines = lines
                    plotter.add_mesh(line_mesh, color="cyan", line_width=8, render_lines_as_tubes=True)
            except Exception:
                pass
            
    plotter.set_background("white")  # White background for PDF
    plotter.view_isometric()
    plotter.reset_camera()
    plotter.screenshot(output_path)
    return output_path
