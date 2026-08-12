"""
core/analyzer.py — Orchestrates the backend DfM analysis pipeline.
"""

import math
from typing import Optional, Tuple
from core.models import AnalysisResult, DirectionCandidate
from core.step_parser import parse_step
from core.mold_direction import find_best_mold_direction
from core.undercut_detector import UndercutRaycaster, evaluate_direction
from core.draft_angle import compute_draft_angles
from core.face_classifier import classify_faces, build_analysis_result
from core.parting_line import find_parting_line


def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-9:
        raise ValueError("Override direction must be a non-zero vector.")
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def analyze_part(filepath: str, part_name: str, override_direction: Optional[Tuple[float, float, float]] = None) -> AnalysisResult:
    """
    Orchestrate the backend logic on a given STEP file.

    If `override_direction` is provided, the expensive multi-axis search is
    skipped entirely and the analysis (undercuts, draft, classification,
    parting line, score) is computed for that direction only.
    """
    # 1. Parse faces and get raw shape
    faces, shape = parse_step(filepath)
    if not faces:
        raise ValueError("No faces found in STEP file.")

    raycaster = UndercutRaycaster(faces)

    if override_direction:
        # 2a. User-chosen direction (e.g., flash placement, cosmetic surfaces)
        direction_to_use = _normalize(override_direction)
        evaluate_direction(raycaster, faces, direction_to_use)
        best_candidate = DirectionCandidate(
            direction=direction_to_use,
            label=f"({direction_to_use[0]:.2f},{direction_to_use[1]:.2f},{direction_to_use[2]:.2f})",
            undercut_count=sum(1 for f in faces if f.is_undercut),
            undercut_area=sum(f.area for f in faces if f.is_undercut),
        )
        all_candidates = [best_candidate]
    else:
        # 2b. Full search over fixed + geometry-derived axes
        best_candidate, all_candidates = find_best_mold_direction(faces, raycaster)
        direction_to_use = best_candidate.direction

    # 3. Compute draft angles (worst-case per face)
    compute_draft_angles(faces, direction_to_use)

    # 4. Assign mold halves + classify (core, cavity, undercut)
    classify_faces(faces, direction_to_use, raycaster)

    # 5. Extract Parting Line
    pl_edges = find_parting_line(shape, faces, direction_to_use)

    # 6. Build Final Result
    res = build_analysis_result(part_name, faces, best_candidate, all_candidates)
    res.raw_shape = shape
    res.parting_line_edges = pl_edges
    res.is_override = override_direction is not None
    return res
