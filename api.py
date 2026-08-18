from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import cadquery as cq

from core.analyzer import analyze_part
from core.parting_line import compute_parting_line_result
<<<<<<< Updated upstream
=======
from core.step_parser import parse_step
from core.undercut_detector import UndercutRaycaster
from core.mold_direction import find_best_mold_direction
from core.undercut_regions import summarize_regions
from core.delegation import EMPTY_PLAN, load_plan
>>>>>>> Stashed changes

app = FastAPI(title="DfM API")

# Where declared tooling plans live. An upload is written to a temp file, so
# `core.delegation.plan_for_part` — which looks beside the model — can never
# find one. The plan is therefore resolved from the ORIGINAL upload filename
# against this directory instead.
PLANS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _plan_for_upload(filename: str):
    """Declared tooling plan matching an uploaded file, or the empty plan.

    `Part3.stp` -> `assets/Part3.tooling.json`. Basename only, so a path in
    the upload name cannot reach outside the plans directory.
    """
    if not filename:
        return EMPTY_PLAN
    stem = os.path.splitext(os.path.basename(filename))[0]
    candidate = os.path.join(PLANS_DIR, f"{stem}.tooling.json")
    if os.path.exists(candidate):
        try:
            return load_plan(candidate)
        except (ValueError, KeyError, OSError):
            # A malformed plan must not take the whole analysis down; the part
            # is simply analysed with no delegation, which is the honest
            # fallback.
            return EMPTY_PLAN
    return EMPTY_PLAN



def _direction_payload(c) -> dict:
    """One candidate pull direction, for the ranking panel.

    The first five keys are the historical contract. The rest come from the
    structured evaluation the direction search now produces, and exist so the
    ranking can be EXPLAINED: two directions that tie on undercuts are
    separated by accessibility and parting complexity, and a user looking at
    the panel should be able to see that rather than guess.
    """
    payload = {
        "direction": list(c.direction),
        "label": c.label,
        "undercut_count": c.undercut_count,
        "undercut_area": round(c.undercut_area, 1),
        "pruned": c.pruned,
    }
    ev = getattr(c, "evaluation", None)
    if ev is not None:
        payload.update(
            source=ev.direction.source,
            undercut_severity=round(ev.undercut_severity, 4),
            accessibility=round(ev.accessibility, 4),
            complexity=round(ev.complexity, 4),
            region_count=ev.region_count,
            score=round(ev.score, 4),
        )
    return payload

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
<<<<<<< Updated upstream
            result = analyze_part(tmp_filepath, file.filename, override_direction=override)
=======
            # Fast path: pruning finds the same winning direction ~5x quicker,
            # so the part renders promptly. The losing candidates come back as
            # lower bounds; the client fills in exact figures via
            # POST /analyze/directions while the user is already looking at
            # the model.
            result = analyze_part(
                tmp_filepath, file.filename,
                override_direction=override,
                exact_candidates=False,
                tooling_plan=_plan_for_upload(file.filename),
            )
>>>>>>> Stashed changes
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

        # ── Parting line ──────────────────────────────────────────────────
        # Computed once, during analyze_part, and read back here. It used to
        # be recomputed at this point from the same inputs — the same work
        # twice, with two code paths that could drift apart.
        pl_result = result.parting_line or compute_parting_line_result(
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

        def _loop_payload(loop, loop_id, is_primary):
            """One loop, as both per-edge segments and an ordered polyline.

            `segments` is the historical shape and stays; `polyline` is the
            loop's points in traversal order, which is what a viewer should
            actually draw. Rendering the segments independently produces a
            disconnected collection of edges — the thing a parting line must
            never be presented as — and the ordered points were already being
            computed and thrown away.
            """
            segments = []
            for edge in loop.edges:
                pts = _tessellate_edge(edge)
                if pts:
                    segments.append(pts)
            return {
                "loop_id": loop_id,
                "candidate_id": loop.candidate_id,
                "is_primary": is_primary,
                "is_closed": loop.is_closed,
                "score": loop.score,
                "segments": segments,
                "polyline": [[p[0], p[1], p[2]] for p in loop.vertex_coords],
                "length": round(loop.loop_length, 2),
                "projected_area": round(loop.projected_area, 2),
                "branch_points": loop.branch_points,
                "is_planar": loop.is_planar,
                "source": loop.source,
                # Length formed by a side action rather than by the two main
                # halves. Non-zero means the loop only closes because a slider
                # or lifter closes it.
                "shutoff_length": round(loop.shutoff_length, 2),
            }

        parting_lines = [_loop_payload(pl_result.primary_loop, 0, True)]
        # Every other CLOSED loop. A part with a through-hole legitimately
        # parts on more than one loop, and sending only the primary hid that.
        for i, loop in enumerate(pl_result.loops, start=1):
            if loop is pl_result.primary_loop:
                continue
            parting_lines.append(_loop_payload(loop, i, False))

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
<<<<<<< Updated upstream
=======
            # Surface area per class. Report these ahead of the counts: a face
            # count reflects CAD subdivision, area reflects how the part
            # actually divides between the mold halves.
            "areas": {
                "core": round(result.core_area, 1),
                "cavity": round(result.cavity_area, 1),
                "undercut": round(result.undercut_area, 1),
                "warning": round(result.warning_area, 1),
                "total": round(result.total_area, 1),
            },
            # Trapped faces grouped into physical features, each with the mold
            # mechanism that would release it. The face count is a topology
            # artifact; tooling is decided per region.
            "undercut_regions": [r.to_dict() for r in result.undercut_regions],
            "undercut_summary": summarize_regions(result.undercut_regions),
            # ── Tooling ──
            # Feature groups a DECLARED plan hands to side actions. When this
            # is non-empty the undercut counts above describe the two MAIN
            # HALVES only, and this is the price of that. A zero reached by
            # delegation is not the same result as a zero reached by geometry,
            # so any client showing the undercut count must show this too.
            "tooling": {
                "declared": bool(result.required_actions),
                "source": getattr(result.tooling_plan, "source", ""),
                "required_actions": result.required_actions,
                "action_count": len(result.required_actions),
                "action_axis_count": (
                    result.tooling_plan.action_axis_count()
                    if result.tooling_plan else 0),
                # Deduplicated: groups may overlap, so summing per-group
                # areas would double-count the intersection.
                "delegated_area": round(
                    sum(f.area for f in result.faces if f.is_delegated), 1),
                # Share of the part the two MAIN HALVES still form. The
                # discriminating number once side actions are allowed —
                # trapped area alone stops telling configurations apart.
                "main_half_fraction": round(
                    sum(f.area for f in result.faces
                        if not f.is_delegated and not f.is_undercut)
                    / (sum(f.area for f in result.faces) or 1.0), 4),
                "preferred_direction_note": result.preferred_direction_note,
            },
            # Runner-up configurations, each with the tooling it would need.
            # Present so the choice is visible rather than asserted: once side
            # actions are allowed, trapped area alone stops discriminating.
            "alternatives": result.alternatives,
>>>>>>> Stashed changes
            "best_direction": result.best_mold_direction,
            "best_direction_label": result.best_direction_label or str(result.best_mold_direction),
            "is_override": result.is_override,
            "direction_candidates": [
                _direction_payload(c)
                for c in sorted(
                    result.direction_candidates,
                    key=lambda c: (c.undercut_area, c.undercut_count),
                )
            ],
            # Validation of the parting line: which checks passed, which
            # failed and why, the quality metrics, and a confidence that is
            # CAPPED by the failures rather than averaged with them. A caller
            # can therefore never read a high confidence off a result that is
            # not manufacturable.
            "parting_line": pl_result.to_dict(),
            "geometry": {
                "faces": faces_data,
                "best_direction": result.best_mold_direction,
                "parting_lines": parting_lines,
                "parting_line_loops": pl_result.total_candidate_count,
                "parting_line_is_ambiguous": pl_result.is_ambiguous,
                "parting_line_confidence": round(pl_result.confidence, 4),
                "parting_line_is_valid": pl_result.is_valid,
            }
        }
        if parting_line_debug is not None:
            response["parting_line_debug"] = parting_line_debug

        return response
    finally:
        os.unlink(tmp_filepath)

<<<<<<< Updated upstream
=======

@app.post("/analyze/directions")
def directions_endpoint(file: UploadFile = File(...)):
    """Exact undercut figures for every candidate pull direction.

    Deliberately separate from /analyze. Evaluating all axes without pruning
    is the slow part of the pipeline, but it only feeds the Mold Direction
    ranking panel — not the 3D view, the score or the parting line. Splitting
    it out lets the client render the part immediately and show the ranking
    as "calculating" until this returns.

    Runs its own parse rather than sharing state with /analyze: the per-face
    undercut flags are mutated in place during a sweep, so a shared cache
    would let one request corrupt another's results.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_file:
        tmp_file.write(file.file.read())
        tmp_filepath = tmp_file.name

    try:
        try:
            faces, _shape = parse_step(tmp_filepath)
        except (RuntimeError, ValueError) as e:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid CAD file: {str(e)}"},
            )
        if not faces:
            return JSONResponse(
                status_code=400, content={"detail": "No faces found in STEP file."}
            )

        raycaster = UndercutRaycaster(faces)
        _best, candidates = find_best_mold_direction(
            faces, raycaster, exact_candidates=True, shape=_shape
        )

        return {
            "direction_candidates": [
                _direction_payload(c)
                for c in sorted(
                    candidates, key=lambda c: (c.undercut_area, c.undercut_count)
                )
            ]
        }
    finally:
        os.unlink(tmp_filepath)

>>>>>>> Stashed changes
