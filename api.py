from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import os
import cadquery as cq

from core.analyzer import analyze_part
from core.parting_line import compute_parting_line_result

app = FastAPI(title="DfM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/analyze")
async def analyze_endpoint(file: UploadFile = File(...), debug: bool = False):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_filepath = tmp_file.name

    try:
        # Run backend logic
        result = analyze_part(tmp_filepath, file.filename)

        # Convert faces to JSON-serializable tessellated representation
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

        # ── Parting line: use full PartingLineResult ──────────────────────
        pl_result = compute_parting_line_result(
            result.raw_shape, result.faces, result.best_mold_direction
        )

        def _tessellate_edge(edge):
            """Sample 11 points along an OCP edge for frontend line rendering."""
            try:
                cq_edge = cq.Edge(edge)
                pts = [cq_edge.positionAt(t / 10.0) for t in range(11)]
                return [[v.x, v.y, v.z] for v in pts]
            except Exception:
                return []

        # Primary parting line loop — always included
        primary_segments = []
        for edge in pl_result.primary_loop.edges:
            pts = _tessellate_edge(edge)
            if pts:
                primary_segments.append(pts)

        parting_lines = [{
            "loop_id": 0,
            "candidate_id": pl_result.primary_loop.candidate_id,
            "is_primary": True,
            "score": pl_result.primary_loop.score,
            "segments": primary_segments,
        }]

        # Debug: include all candidate loops
        parting_line_debug = None
        if debug:
            candidates_summary = []
            for c in pl_result.all_candidates:
                cand_segments = []
                for edge in c.edges:
                    pts = _tessellate_edge(edge)
                    if pts:
                        cand_segments.append(pts)
                candidates_summary.append({
                    "candidate_id": c.candidate_id,
                    "score": c.score,
                    "projected_area": c.projected_area,
                    "loop_length": c.loop_length,
                    "outer_boundary_confidence": c.outer_boundary_confidence,
                    "moldability_contribution": c.moldability_contribution,
                    "simplicity": c.simplicity,
                    "separation_quality": c.separation_quality,
                    "num_edges": c.num_edges,
                    "is_selected": c.is_selected,
                    "segments": cand_segments,
                })
            parting_line_debug = {
                "total_candidates": pl_result.total_candidate_count,
                "is_ambiguous": pl_result.is_ambiguous,
                "candidates": candidates_summary,
            }

        from core.mold_direction import CANDIDATE_DIRECTIONS
        best_dir_label = next(
            (l for d, l in CANDIDATE_DIRECTIONS if d == result.best_mold_direction),
            str(result.best_mold_direction)
        )

        response = {
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
                "parting_lines": parting_lines,
                "parting_line_loops": pl_result.total_candidate_count,
                "parting_line_is_ambiguous": pl_result.is_ambiguous,
            }
        }
        if parting_line_debug is not None:
            response["parting_line_debug"] = parting_line_debug

        return response
    finally:
        os.unlink(tmp_filepath)

from fastapi.responses import FileResponse
from core.visualization import create_3d_snapshot
from core.report import generate_pdf_report

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
