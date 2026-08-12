"""
core/undercut_detector.py — Flag faces that are undercut using raycasting.

A true undercut in injection molding is a face that is physically trapped
and cannot be pulled out by either the Cavity or the Core mold half.

v2 (Phase 2 rewrite):
- Multi-sample raycasting: every face is tested at several surface sample
  points (from step_parser), not just its UV midpoint. Curved faces
  (cylinders, splines) have normals spanning a wide arc — a single
  midpoint normal misrepresents them, which was the root cause of the
  Phase 1 undercut false positives.
- Per-sample verdicts are aggregated into a trapped fraction; a face is
  flagged as an undercut when the majority of its surface is trapped.
- The raycaster (compound + intersector) is built once and reused across
  all candidate directions via `UndercutRaycaster`.
- Ray length is derived from the part's bounding box instead of a
  hardcoded 1000mm.
"""

from typing import List, Optional, Tuple

from core.models import FaceData

# OCP imports for raycasting
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.IntCurveSurface import IntCurveSurface_In
from OCP.gp import gp_Lin, gp_Dir, gp_Pnt

# Minimum ray hit distance (mm). Hits closer than this are treated as
# self-intersection / numerical grazing artifacts, NOT true blockers.
# Real molded walls are >= ~0.5mm, so 0.1mm is a safe cutoff.
MIN_HIT_DISTANCE = 0.1

# Offset of the ray origin along the surface normal (mm), to escape the
# face's own surface before testing for blockers.
RAY_ORIGIN_OFFSET = 0.01

# |dot(normal, pull)| below this → sample lies on a vertical wall
# (~0.6° from the parting plane); it escapes with EITHER mold half.
PERP_EPS = 0.01

# A face is an undercut when at least this fraction of its surface
# samples are trapped.
UNDERCUT_FRACTION_THRESHOLD = 0.5


def _dot(a: Tuple[float, float, float],
         b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class UndercutRaycaster:
    """Reusable raycaster over the whole part (build once, query many)."""

    def __init__(self, faces: List[FaceData]):
        builder = BRep_Builder()
        comp = TopoDS_Compound()
        builder.MakeCompound(comp)
        for f in faces:
            if f.face_shape:
                builder.Add(comp, f.face_shape)

        self._intersector = IntCurvesFace_ShapeIntersector()
        self._intersector.Load(comp, 1e-6)

        # Ray length: part bounding-box diagonal (plus margin)
        try:
            bnd = Bnd_Box()
            BRepBndLib.Add_s(comp, bnd)
            xmin, ymin, zmin, xmax, ymax, zmax = bnd.Get()
            dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
            self._max_dist = max((dx * dx + dy * dy + dz * dz) ** 0.5 * 1.5, 10.0)
        except Exception:
            self._max_dist = 1000.0

    def is_blocked(
        self,
        point: Tuple[float, float, float],
        normal: Tuple[float, float, float],
        direction: Tuple[float, float, float],
    ) -> bool:
        """Cast a ray from `point` (offset along `normal`) in `direction`.
        Returns True if the geometry blocks the escape path."""
        ox = point[0] + normal[0] * RAY_ORIGIN_OFFSET
        oy = point[1] + normal[1] * RAY_ORIGIN_OFFSET
        oz = point[2] + normal[2] * RAY_ORIGIN_OFFSET
        try:
            line = gp_Lin(gp_Pnt(ox, oy, oz), gp_Dir(*direction))
            self._intersector.Perform(line, 0.0, self._max_dist)
            for i in range(1, self._intersector.NbPnt() + 1):
                if self._intersector.WParameter(i) < MIN_HIT_DISTANCE:
                    continue
                # Only hits where the ray ENTERS material block the escape
                # path. Tangential grazes along adjacent walls / blend
                # fillets (transition Tangent) and exit-side hits
                # (transition Out) are not physical blockers — they were
                # the source of false-positive undercuts on vertical
                # corner fillets.
                if self._intersector.Transition(i) == IntCurveSurface_In:
                    return True
        except Exception:
            pass
        return False

    def sample_trapped(
        self,
        point: Tuple[float, float, float],
        normal: Tuple[float, float, float],
        pull: Tuple[float, float, float],
        neg_pull: Tuple[float, float, float],
    ) -> bool:
        """Determine whether one surface sample is trapped for the given pull axis.

        A sample escapes with the mold half it faces:
          normal · pull > 0  → cavity side → must escape along +pull
          normal · pull < 0  → core side   → must escape along -pull
          normal ⊥ pull      → vertical wall → escapes if EITHER way is free
        Note this is symmetric in pull ↔ -pull: undercuts depend only on the
        mold AXIS, not on which half is called cavity.
        """
        d = _dot(normal, pull)
        if d > PERP_EPS:
            return self.is_blocked(point, normal, pull)
        if d < -PERP_EPS:
            return self.is_blocked(point, normal, neg_pull)
        return (
            self.is_blocked(point, normal, pull)
            and self.is_blocked(point, normal, neg_pull)
        )


def _face_samples(
    face: FaceData,
    max_samples: Optional[int],
) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
    """Return (points, normals) for a face, optionally subsampled evenly."""
    pts = face.sample_points or [face.center]
    nrms = face.sample_normals or [face.normal]
    n = len(pts)
    if max_samples is not None and 1 < max_samples < n:
        idxs = [round(i * (n - 1) / (max_samples - 1)) for i in range(max_samples)]
        pts = [pts[i] for i in idxs]
        nrms = [nrms[i] for i in idxs]
    return pts, nrms


def evaluate_direction(
    raycaster: UndercutRaycaster,
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    max_samples_per_face: Optional[int] = None,
    abort_above_area: Optional[float] = None,
) -> Tuple[int, float]:
    """
    Flag each face as undercut for `mold_direction` using per-sample raycasts.
    Updates face.is_undercut and face.trapped_fraction in place.

    Returns (undercut_count, undercut_area). When `abort_above_area` is
    given, evaluation runs biggest-faces-first and stops as soon as the
    accumulated undercut area exceeds it (branch-and-bound pruning during
    the axis sweep) — the returned partial values are then lower bounds
    that are already worse than the incumbent best axis.
    """
    pull = mold_direction
    neg_pull = (-pull[0], -pull[1], -pull[2])

    ordered = (
        sorted(faces, key=lambda f: -f.area)
        if abort_above_area is not None else faces
    )

    uc_count = 0
    uc_area = 0.0
    for face in ordered:
        pts, nrms = _face_samples(face, max_samples_per_face)
        total = len(pts)
        need = total * UNDERCUT_FRACTION_THRESHOLD
        trapped = 0

        for k, (p, nv) in enumerate(zip(pts, nrms)):
            if raycaster.sample_trapped(p, nv, pull, neg_pull):
                trapped += 1
            # Early exit: verdict already decided either way
            remaining = total - (k + 1)
            if trapped >= need or trapped + remaining < need:
                break

        face.trapped_fraction = trapped / total if total else 0.0
        face.is_undercut = total > 0 and trapped >= need
        if face.is_undercut:
            uc_count += 1
            uc_area += face.area
            if abort_above_area is not None and uc_area > abort_above_area:
                break

    return uc_count, uc_area


def refine_direction(
    raycaster: UndercutRaycaster,
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
) -> None:
    """Full-resolution re-evaluation of SUSPICIOUS faces only.

    After a low-resolution sweep pass, faces with zero trapped samples
    keep their free verdict — evenly-spread sweep samples all escaping
    while the full set is majority-trapped is geometrically implausible.
    Every face that showed any trapping is re-checked with all samples.
    """
    borderline = [f for f in faces if f.trapped_fraction > 0.0]
    evaluate_direction(raycaster, borderline, mold_direction)


def detect_undercuts(
    faces: List[FaceData],
    mold_direction: Tuple[float, float, float],
    max_samples_per_face: Optional[int] = None,
) -> List[FaceData]:
    """
    Backward-compatible entry point: builds a raycaster and evaluates one
    direction. Prefer `UndercutRaycaster` + `evaluate_direction` when
    testing many directions on the same part.
    """
    if not faces:
        return faces
    raycaster = UndercutRaycaster(faces)
    evaluate_direction(raycaster, faces, mold_direction, max_samples_per_face)
    return faces


def get_undercut_summary(faces: List[FaceData]) -> dict:
    undercut_faces = [f for f in faces if f.is_undercut]
    total_area = sum(f.area for f in faces)
    undercut_area = sum(f.area for f in undercut_faces)

    return {
        "total_faces": len(faces),
        "undercut_count": len(undercut_faces),
        "undercut_area": undercut_area,
        "undercut_percentage": (undercut_area / total_area * 100) if total_area > 0 else 0.0,
    }
