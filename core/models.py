"""
core/models.py — Shared data structures (Interface Contract)

This file defines the dataclasses that both Person A (geometry engine)
and Person B (visualization/GUI) depend on. Written on Day 1 and
should rarely change.

All geometry analysis results flow through these structures:
  FaceData           → per-face geometry + classification
  DirectionCandidate → one candidate mold opening direction
  AnalysisResult     → complete analysis output for a part
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Any


@dataclass
class FaceData:
    """Represents a single face of the 3D part with its geometry and analysis results."""

    face_id: int
    face_shape: Any                          # OCP TopoDS_Face object (opaque to Person B)
    center: Tuple[float, float, float]       # (x, y, z) UV midpoint of the face
    normal: Tuple[float, float, float]       # (nx, ny, nz) outward unit normal (representative)
    area: float                              # surface area in mm²
    surface_type: str                        # "PLANE" / "CYLINDER" / "CONE" / "SPHERE" / "TORUS" / "BSPLINE"

    # ── Multi-point surface sampling (curved faces need >1 normal) ──
    sample_points: List[Tuple[float, float, float]] = field(default_factory=list)
    sample_normals: List[Tuple[float, float, float]] = field(default_factory=list)
    axis: Any = None                         # cylinder/cone axis direction, if applicable

    # ── Filled by analysis steps (Steps 3–5) ──
    classification: str = ""                 # "core" / "cavity" / "undercut"
    mold_half: str = ""                      # "core" / "cavity" — which half FORMS this face (always set)
    low_draft: bool = False                  # True when draft angle < 1° (ejection friction risk)
    draft_angle: float = 0.0                 # in degrees (worst-case across samples)
    is_undercut: bool = False
    trapped_fraction: float = 0.0            # fraction of surface samples that are trapped [0, 1]

    # ── Accessibility-derived region (core.accessibility.MoldRegion value) ──
    # "core" / "cavity" / "neutral" / "undercut" / "ambiguous".
    #
    # Kept ALONGSIDE mold_half rather than replacing it. mold_half answers
    # "which steel forms this face" and is always one of the two halves — the
    # API and the viewer are built on that, and a face has to be molded by
    # something. mold_region additionally records where the answer came from
    # and admits that it is sometimes undecided, which is what the parting
    # boundary needs: a NEUTRAL face borders both halves without separating
    # them, and an edge against an UNDERCUT face is a shutoff, not a parting
    # line. Collapsing the two would throw that distinction away.
    mold_region: str = ""
    # True when a declared side action forms this face, so the two main
    # halves are not responsible for releasing it. See core/delegation.py.
    is_delegated: bool = False


@dataclass
class DirectionCandidate:
    """One candidate mold opening direction and its undercut metrics.

    This is the shape the API response and the UI's direction panel are built
    on, so the first five fields do not change. `evaluation` and
    `accessibility` carry the richer per-direction analysis alongside for
    callers that want it, without forcing a schema migration on those that
    don't.
    """

    direction: Tuple[float, float, float]    # (nx, ny, nz) unit vector
    label: str                               # human-readable: "Z+" / "Z-" / "X+Y+" etc.
    undercut_count: int                      # number of faces that are undercut
    undercut_area: float                     # total undercut area in mm²
    pruned: bool = False                     # True: evaluation aborted early — count/area are lower bounds

    # core.direction_evaluation.DirectionEvaluation — severity, accessibility,
    # complexity and the display score for this direction.
    evaluation: Any = None
    # core.accessibility.AccessibilityResult for the winning direction only.
    accessibility: Any = None


@dataclass
class AnalysisResult:
    """Complete DfM analysis output for one part. Person B consumes this."""

    part_name: str
    total_faces: int
    best_mold_direction: Tuple[float, float, float]
    direction_candidates: List[DirectionCandidate]
    faces: List[FaceData]
    raw_shape: Any = None
    best_direction_label: str = ""
    is_override: bool = False

    # ── Parting line ──
    # Edges of the primary loop. A flat edge list is exactly the
    # "disconnected collection of edges" a parting line must not be presented
    # as, so it is kept only for the callers already typed against it; the
    # ordered loops, validation and confidence live on `parting_line`.
    parting_line_edges: List[Any] = field(default_factory=list)
    # core.parting.models.PartingLineResult for the chosen direction.
    parting_line: Any = None

    # ── Tooling ──
    # core.delegation.ToolingPlan: the feature groups the caller declared
    # are formed by side actions rather than by the two main halves. Empty
    # unless a plan was supplied. `required_actions` is the resolved,
    # reportable form and MUST be surfaced wherever undercut counts are:
    # a zero reached by delegation is not the same result as a zero
    # reached by geometry, and the two must never look alike.
    tooling_plan: Any = None
    required_actions: List[Any] = field(default_factory=list)
    # Outcome of verifying a plan's declared preferred direction against
    # what the search derived. Empty when no direction was declared.
    preferred_direction_note: str = ""
    # Alternative configurations evaluated for the same part, best first.
    alternatives: List[Any] = field(default_factory=list)

    # ── Summary counts (filled during face classification) ──
    core_face_count: int = 0
    cavity_face_count: int = 0
    undercut_face_count: int = 0
    warning_face_count: int = 0

    # ── Summary AREAS, mm² (filled during face classification) ──
    # Face counts are a poor measure of how a part divides between mold
    # halves: they track how finely the CAD happens to be subdivided, not
    # geometry. Area is the invariant, and it is the measure Bosch asked
    # for (2026-07-28): "area will be better to evaluate".
    core_area: float = 0.0
    cavity_area: float = 0.0
    undercut_area: float = 0.0
    warning_area: float = 0.0
    total_area: float = 0.0

    # ── Undercut features (trapped faces grouped into physical regions) ──
    undercut_regions: List[Any] = field(default_factory=list)

    # ── Overall score: 0 (worst) to 100 (best) ──
    manufacturability_score: float = 0.0


def compute_score(faces: List[FaceData]) -> float:
    """
    Compute a manufacturability score from 0–100.

    Penalty formula (area + count weighted):
      - Undercut area:  up to 30 points penalty
      - Undercut count: up to 20 points penalty
      - Warning area:   up to 15 points penalty
      - Warning count:  up to 5 points penalty
    """
    total_area = sum(f.area for f in faces)
    if total_area == 0 or len(faces) == 0:
        return 0.0

    bad_faces = [f for f in faces if f.is_undercut]
    warn_faces = [f for f in faces if f.low_draft and not f.is_undercut]

    bad_area = sum(f.area for f in bad_faces)
    warn_area = sum(f.area for f in warn_faces)

    bad_area_penalty = (bad_area / total_area) * 30
    bad_count_penalty = (len(bad_faces) / len(faces)) * 20
    warn_area_penalty = (warn_area / total_area) * 15
    warn_count_penalty = (len(warn_faces) / len(faces)) * 5

    score = 100.0 - bad_area_penalty - bad_count_penalty - warn_area_penalty - warn_count_penalty
    return max(0.0, min(100.0, score))
