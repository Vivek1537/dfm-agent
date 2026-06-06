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
    normal: Tuple[float, float, float]       # (nx, ny, nz) outward unit normal
    area: float                              # surface area in mm²
    surface_type: str                        # "PLANE" / "CYLINDER" / "CONE" / "SPHERE" / "TORUS" / "BSPLINE"

    # ── Filled by analysis steps (Steps 3–5) ──
    classification: str = ""                 # "core" / "cavity" / "undercut" / "warning"
    draft_angle: float = 0.0                 # in degrees (negative = undercut)
    is_undercut: bool = False


@dataclass
class DirectionCandidate:
    """One candidate mold opening direction and its undercut metrics."""

    direction: Tuple[float, float, float]    # (nx, ny, nz) unit vector
    label: str                               # human-readable: "Z+" / "Z-" / "X+Y+" etc.
    undercut_count: int                      # number of faces that are undercut
    undercut_area: float                     # total undercut area in mm²


@dataclass
class AnalysisResult:
    """Complete DfM analysis output for one part. Person B consumes this."""

    part_name: str
    total_faces: int
    best_mold_direction: Tuple[float, float, float]
    direction_candidates: List[DirectionCandidate]
    faces: List[FaceData]

    # ── Filled by Person B (parting line detection) ──
    parting_line_edges: List[Any] = field(default_factory=list)

    # ── Summary counts (filled during face classification) ──
    core_face_count: int = 0
    cavity_face_count: int = 0
    undercut_face_count: int = 0
    warning_face_count: int = 0

    # ── Overall score: 0 (worst) to 100 (best) ──
    manufacturability_score: float = 0.0


def compute_score(faces: List[FaceData]) -> float:
    """
    Compute a manufacturability score from 0–100.

    Penalty formula:
      - Undercut faces penalize up to 60 points (area-weighted)
      - Warning faces (draft < 1°) penalize up to 20 points (area-weighted)
    """
    total_area = sum(f.area for f in faces)
    if total_area == 0:
        return 0.0

    bad_area = sum(f.area for f in faces if f.is_undercut)
    warn_area = sum(
        f.area for f in faces
        if f.draft_angle < 1.0 and not f.is_undercut
    )

    score = 100.0 - (bad_area / total_area * 60) - (warn_area / total_area * 20)
    return max(0.0, min(100.0, score))


if __name__ == "__main__":
    # Quick smoke test — verify dataclasses instantiate correctly
    face = FaceData(
        face_id=0,
        face_shape=None,
        center=(0.0, 0.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        area=12.5,
        surface_type="PLANE",
    )
    print(f"FaceData:  id={face.face_id}, normal={face.normal}, "
          f"area={face.area}, type={face.surface_type}")

    candidate = DirectionCandidate(
        direction=(0.0, 0.0, 1.0),
        label="Z+",
        undercut_count=5,
        undercut_area=3.2,
    )
    print(f"Candidate: {candidate.label} → {candidate.undercut_count} undercuts, "
          f"{candidate.undercut_area:.1f} mm² undercut area")

    result = AnalysisResult(
        part_name="Element_Packaging_Cap",
        total_faces=311,
        best_mold_direction=(0.0, 0.0, 1.0),
        direction_candidates=[candidate],
        faces=[face],
    )
    print(f"Result:    {result.part_name}, {result.total_faces} faces, "
          f"best dir={result.best_mold_direction}")

    # Test score function
    face_good = FaceData(0, None, (0.0, 0.0, 0.0), (0, 0, 1), 80.0, "PLANE", draft_angle=5.0)
    face_warn = FaceData(1, None, (0.0, 0.0, 0.0), (1, 0, 0), 10.0, "PLANE", draft_angle=0.5)
    face_bad = FaceData(2, None, (0.0, 0.0, 0.0), (0, 0, -1), 10.0, "PLANE", is_undercut=True, draft_angle=-5.0)
    score = compute_score([face_good, face_warn, face_bad])
    print(f"Score:     {score:.1f}/100  (80mm² good, 10mm² warn, 10mm² undercut)")

    print("\n✅ models.py — all dataclasses OK")
