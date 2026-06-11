from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import os
import cadquery as cq

from gui.analyzer import analyze_part

app = FastAPI(title="DfM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze_endpoint(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_filepath = tmp_file.name

    try:
        # Run backend logic
        result = analyze_part(tmp_filepath, file.filename)

        # Convert to JSON serializable representation
        faces_data = []
        for face_data in result.faces:
            if not face_data.face_shape:
                continue
            
            try:
                cq_face = cq.Face(face_data.face_shape)
                vertices, triangles = cq_face.tessellate(0.1)
                
                if not vertices or not triangles:
                    continue
                
                faces_data.append({
                    "classification": face_data.classification,
                    "vertices": [[v.x, v.y, v.z] for v in vertices],
                    "triangles": [[t[0], t[1], t[2]] for t in triangles]
                })
            except Exception:
                pass
                
        def count_loops(raw_edges):
            from collections import defaultdict
            import cadquery as cq
            adj = defaultdict(list)
            edges = []
            for e in raw_edges:
                try:
                    edges.append(cq.Edge(e))
                except: pass
            
            for i, cq_e in enumerate(edges):
                try:
                    v1, v2 = cq_e.startPoint(), cq_e.endPoint()
                    p1 = (round(v1.x,2), round(v1.y,2), round(v1.z,2))
                    p2 = (round(v2.x,2), round(v2.y,2), round(v2.z,2))
                    adj[p1].append(i)
                    adj[p2].append(i)
                except:
                    pass
            
            visited = set()
            loops = 0
            for i in range(len(edges)):
                if i not in visited:
                    loops += 1
                    q = [i]
                    while q:
                        curr = q.pop()
                        visited.add(curr)
                        try:
                            cq_e = edges[curr]
                            v1, v2 = cq_e.startPoint(), cq_e.endPoint()
                            p1 = (round(v1.x,2), round(v1.y,2), round(v1.z,2))
                            p2 = (round(v2.x,2), round(v2.y,2), round(v2.z,2))
                            for n in adj[p1] + adj[p2]:
                                if n not in visited:
                                    visited.add(n)
                                    q.append(n)
                        except: pass
            return loops
            
        parting_line_data = []
        loop_count = 0
        if result.parting_line_edges:
            loop_count = count_loops(result.parting_line_edges)
            for edge in result.parting_line_edges:
                try:
                    cq_edge = cq.Edge(edge)
                    # Sample 10 points along the edge
                    pts = [cq_edge.positionAt(t / 10.0) for t in range(11)]
                    parsed_pts = [[v.x, v.y, v.z] for v in pts]
                    parting_line_data.append(parsed_pts)
                except Exception as e:
                    print(f"EDGE TESSELLATE ERROR: {e}")
                    pass

        from core.mold_direction import CANDIDATE_DIRECTIONS
        best_dir_label = next((l for d, l in CANDIDATE_DIRECTIONS if d == result.best_mold_direction), str(result.best_mold_direction))

        return {
            "part_name": result.part_name,
            "total_faces": result.total_faces,
            "score": result.manufacturability_score,
            "core_faces": result.core_face_count,
            "cavity_faces": result.cavity_face_count,
            "undercut_faces": result.undercut_face_count,
            "warning_faces": result.warning_face_count,
            "best_direction": result.best_mold_direction,
            "best_direction_label": best_dir_label,
            "geometry": {
                "faces": faces_data,
                "parting_lines": parting_line_data,
                "parting_line_loops": loop_count
            }
        }
    finally:
        os.unlink(tmp_filepath)

from fastapi.responses import FileResponse
from gui.visualization import create_3d_snapshot
from gui.report import generate_pdf_report

@app.post("/report")
async def report_endpoint(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_filepath = tmp_file.name
        
    try:
        result = analyze_part(tmp_filepath, file.filename)
        snapshot_path = os.path.join(tempfile.gettempdir(), "dfm_snapshot.png")
        report_path = os.path.join(tempfile.gettempdir(), "dfm_report.pdf")
        
        create_3d_snapshot(result.faces, result.parting_line_edges, snapshot_path)
        generate_pdf_report(result, snapshot_path, report_path)
        
        return FileResponse(path=report_path, filename=f"{result.part_name}_DfM_Report.pdf", media_type='application/pdf')
    finally:
        os.unlink(tmp_filepath)
