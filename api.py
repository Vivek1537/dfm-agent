from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
async def analyze_endpoint(
    file: UploadFile = File(...),
    debug: bool = False,
    direction: str = Form(None),
):
    """Analyze a STEP file.

    `direction` (optional): override mold pull direction as "x,y,z".
    When provided, the automatic direction search is skipped and the whole
    analysis is computed for the given direction.
    """
    override = None
    if direction:
        try:
            parts = [float(v) for v in direction.split(",")]
            if len(parts) != 3 or all(abs(v) < 1e-9 for v in parts):
                raise ValueError
            override = tuple(parts)
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"detail": "direction must be 'x,y,z' with a non-zero vector"},
            )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_filepath = tmp_file.name

    try:
        # Run backend logic
        try:
            result = analyze_part(tmp_filepath, file.filename, override_direction=override)
        except (RuntimeError, ValueError) as e:
            return JSONResponse(status_code=400, content={"detail": f"Invalid CAD file: {str(e)}"})

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
                    "mold_half": face_data.mold_half,
                    "low_draft": face_data.low_draft,
                    "draft_angle": round(face_data.draft_angle, 2),
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
            "is_closed": pl_result.primary_loop.is_closed,
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
                    "is_closed": c.is_closed,
                    "segments": cand_segments,
                })
            parting_line_debug = {
                "total_candidates": pl_result.total_candidate_count,
                "is_ambiguous": pl_result.is_ambiguous,
                "candidates": candidates_summary,
            }

        response = {
            "part_name": result.part_name,
            "total_faces": result.total_faces,
            "score": result.manufacturability_score,
            "core_faces": result.core_face_count,
            "cavity_faces": result.cavity_face_count,
            "undercut_faces": result.undercut_face_count,
            "warning_faces": result.warning_face_count,
            "best_direction": result.best_mold_direction,
            "best_direction_label": result.best_direction_label or str(result.best_mold_direction),
            "is_override": result.is_override,
            "direction_candidates": [
                {
                    "direction": list(c.direction),
                    "label": c.label,
                    "undercut_count": c.undercut_count,
                    "undercut_area": round(c.undercut_area, 1),
                    "pruned": c.pruned,
                }
                for c in sorted(
                    result.direction_candidates,
                    key=lambda c: (c.undercut_area, c.undercut_count),
                )
            ],
            "geometry": {
                "faces": faces_data,
                "best_direction": result.best_mold_direction,
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

