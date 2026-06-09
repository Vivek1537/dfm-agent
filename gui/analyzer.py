"""
gui/analyzer.py — Wrapper for the backend DfM analysis.
"""

from typing import Optional, Tuple
from core.models import AnalysisResult
from core.step_parser import parse_step
from core.mold_direction import find_best_mold_direction
from core.undercut_detector import detect_undercuts
from core.draft_angle import compute_draft_angles
from core.face_classifier import classify_faces, build_analysis_result
from core.parting_line import find_parting_line


def analyze_part(filepath: str, part_name: str, override_direction: Optional[Tuple[float, float, float]] = None) -> AnalysisResult:
    """
    Orchestrate the backend logic on a given STEP file.
    Optionally override the mold direction.
    """
    # 1. Parse faces and get raw shape
    faces, shape = parse_step(filepath)
    if not faces:
        raise ValueError("No faces found in STEP file.")

    # 2. Find best mold direction (or use override)
    best_candidate, all_candidates = find_best_mold_direction(faces)
    
    direction_to_use = best_candidate.direction
    if override_direction:
        direction_to_use = override_direction
        
        # If overridden, we need to re-detect undercuts for the new direction
        # since find_best_mold_direction leaves the faces configured for `best_candidate`
        detect_undercuts(faces, direction_to_use)

    # 3. Compute draft angles
    compute_draft_angles(faces, direction_to_use)

    # 4. Classify faces (Core, Cavity, Undercut, Warning)
    classify_faces(faces, direction_to_use)
    
    # 5. Extract Parting Line
    pl_edges = find_parting_line(shape, faces)

    # 6. Build Final Result
    res = build_analysis_result(part_name, faces, best_candidate, all_candidates)
    res.raw_shape = shape
    res.parting_line_edges = pl_edges
    return res
