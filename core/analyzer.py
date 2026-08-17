"""
core/analyzer.py — Orchestrates the backend DfM analysis pipeline.
"""

import math
from typing import Optional, Tuple
from core.models import AnalysisResult, DirectionCandidate
from core.step_parser import parse_step, faces_from_shape
from core.mold_direction import find_best_mold_direction
from core.undercut_detector import UndercutRaycaster, evaluate_direction
from core.draft_angle import compute_draft_angles
from core.face_classifier import classify_faces, build_analysis_result
from core.parting_line import find_parting_line
from core.silhouette import split_at_silhouette
from core.undercut_regions import find_undercut_regions


def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-9:
        raise ValueError("Override direction must be a non-zero vector.")
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def analyze_part(
    filepath: str,
    part_name: str,
    override_direction: Optional[Tuple[float, float, float]] = None,
    exact_candidates: bool = True,
) -> AnalysisResult:
    """
    Orchestrate the backend logic on a given STEP file.

    If `override_direction` is provided, the expensive multi-axis search is
    skipped entirely and the analysis (undercuts, draft, classification,
    parting line, score) is computed for that direction only.

    `exact_candidates=False` uses branch-and-bound pruning during the axis
    sweep. The winning direction is identical either way, but the losing
    candidates come back with lower-bound counts instead of exact ones. The
    API uses the fast path so the part renders quickly, then fills in the
    exact ranking from a follow-up request.
    """
    # 1. Parse faces and get raw shape
    faces, shape = parse_step(filepath)
    if not faces:
        raise ValueError("No faces found in STEP file.")

    raycaster = UndercutRaycaster(faces)

    if override_direction:
        # 2a. User-chosen direction (e.g., flash placement, cosmetic surfaces)
        direction_to_use = _normalize(override_direction)
        evaluate_direction(raycaster, faces, direction_to_use, exact_fractions=True)
        best_candidate = DirectionCandidate(
            direction=direction_to_use,
            label=f"({direction_to_use[0]:.2f},{direction_to_use[1]:.2f},{direction_to_use[2]:.2f})",
            undercut_count=sum(1 for f in faces if f.is_undercut),
            undercut_area=sum(f.area for f in faces if f.is_undercut),
        )
        all_candidates = [best_candidate]
    else:
        # 2b. Full search over fixed + geometry-derived axes
        best_candidate, all_candidates = find_best_mold_direction(
            faces, raycaster, exact_candidates=exact_candidates
        )
        direction_to_use = best_candidate.direction

    # 2c. Subdivide faces the silhouette crosses, so the core/cavity boundary
    # can run down the middle of a face instead of being pinned to its edges.
    # A no-op for a pull along the part's own axis (nothing straddles), which
    # is every part validated so far; it engages on a perpendicular pull.
    split_shape = split_at_silhouette(shape, faces, direction_to_use)
    if split_shape is not None:
        split_faces = faces_from_shape(split_shape)
        if split_faces:
            faces, shape = split_faces, split_shape
            raycaster = UndercutRaycaster(faces)
            evaluate_direction(
                raycaster, faces, direction_to_use, exact_fractions=True
            )

    # 3. Compute draft angles (worst-case per face)
    compute_draft_angles(faces, direction_to_use)

    # 4. Assign mold halves + classify (core, cavity, undercut)
    classify_faces(faces, direction_to_use, raycaster, shape=shape)

    # 5. Extract Parting Line
    pl_edges = find_parting_line(shape, faces, direction_to_use)

    # 6. Build Final Result
    res = build_analysis_result(part_name, faces, best_candidate, all_candidates)
    res.raw_shape = shape
    res.parting_line_edges = pl_edges
    res.is_override = override_direction is not None
    # Group trapped faces into physical features. A face count is a topology
    # artifact; the tooling decision is made per region.
    res.undercut_regions = find_undercut_regions(
        shape, faces, direction_to_use, raycaster
    )
    return res
