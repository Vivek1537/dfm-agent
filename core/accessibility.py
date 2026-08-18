"""
core/accessibility.py — Mold accessibility along a pull axis.

Specification section 4 asks for a geometry/visibility method rather than a
`dot(face_normal, D)` test, because a normal alone says nothing about whether
the geometry in front of a face blocks the tool from reaching it. This module
provides that: for every surface sample it casts a ray along +D and another
along -D and records BOTH answers, so downstream stages can ask the four-way
question the specification defines:

    accessible from +D only   -> formed by the half on the +D side
    accessible from -D only   -> formed by the half on the -D side
    accessible from both      -> neutral / near-parting / needs topology
    accessible from neither   -> trapped

The rays themselves come from `core.undercut_detector.UndercutRaycaster`,
which is already the specification's preferred approach (an OpenCASCADE
`IntCurvesFace_ShapeIntersector` over the whole solid, entering-material hits
only, built once per part). Nothing about the ray physics changes here; what
changes is that the answers are kept in a structure instead of being collapsed
to a boolean at the point of measurement.

TWO QUESTIONS, NOT ONE
----------------------
There are two distinct things one can ask of a sample, and conflating them is
a real source of wrong answers:

  REACHABILITY  Can a tool arriving from the +D side touch this point at all?
                That is `not blocked(+D)`, and it is what decides WHICH HALF
                forms the surface.

  RELEASE       Can the half that actually forms this surface pull away from
                it? A sample whose outward normal points toward the cavity is
                formed by the cavity steel, so it must release along +D. That
                the core could also reach it is irrelevant: the core is not
                what is touching it.

Release is the stricter test and it is the one that defines an undercut. A
face tucked under an overhang, normal pointing toward the cavity but roofed by
material above, is reachable from -D yet cannot be released by the half that
forms it, and it is a genuine undercut. The specification's four-way table
alone would call that "-D only -> opposite mold half" and miss it.

So this module measures reachability for the region question and release for
the undercut question, and reports both. The release rule is unchanged from
`core/undercut_detector.py`, where it is validated against Bosch's stated
answer for Part 1 (zero undercuts) and against a built mould's slide core for
the reference bush; the four-way reachability is the new information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from core.models import FaceData
from core.tolerances import AnalysisConfig, resolve
from core.undercut_detector import UndercutRaycaster

Vector3 = Tuple[float, float, float]


class MoldRegion(str, Enum):
    """Which mold region a face belongs to, per specification section 7.

    Inherits from `str` so the value serialises straight to JSON and compares
    equal to the plain strings the API and the viewer already use.
    """

    CORE = "core"
    CAVITY = "cavity"
    NEUTRAL = "neutral"
    UNDERCUT = "undercut"
    AMBIGUOUS = "ambiguous"
    # Formed by a declared side action, not by either main half. Such a
    # face is neither released nor trapped BY THE PULL DIRECTION -- the
    # pull was never asked to release it. See core/delegation.py.
    DELEGATED = "delegated"


# The two halves a parting line actually separates. NEUTRAL and AMBIGUOUS are
# resolved into one of these before boundary extraction; UNDERCUT never is.
MOLD_HALVES = (MoldRegion.CORE, MoldRegion.CAVITY)


@dataclass
class FaceAccessibility:
    """Per-face accessibility along one pull axis.

    Fractions are over the face's surface samples, so they are directly
    comparable across faces of different size and tessellation.
    """

    face_id: int
    sample_count: int

    plus_fraction: float          # samples a tool from +D can reach
    minus_fraction: float         # samples a tool from -D can reach
    both_fraction: float          # reachable from either side
    neither_fraction: float       # reachable from neither side

    trapped_fraction: float       # samples the forming half cannot release
    is_undercut: bool

    region: MoldRegion            # accessibility-derived, before propagation
    area: float = 0.0

    # False when this entry came from a sweep pass that measured only the
    # release verdict: `plus_fraction` / `minus_fraction` are then a normal-vote
    # proxy rather than ray measurements, and `region` is correspondingly
    # approximate. The winning direction is always re-measured with four_way
    # True before anything is reported or classified.
    four_way: bool = True

    @property
    def accessible(self) -> bool:
        """True when the face is released by a straight pull on this axis."""
        return not self.is_undercut


@dataclass
class AccessibilityResult:
    """Accessibility of a whole part along one pull axis."""

    direction: Vector3
    faces: Dict[int, FaceAccessibility] = field(default_factory=dict)

    total_area: float = 0.0
    undercut_area: float = 0.0
    undercut_count: int = 0
    accessible_area: float = 0.0

    # Area reachable from each side. A part where one side reaches almost
    # everything is easy to tool; one where both sides reach only half is a
    # deeper split. Used as the accessibility term of the direction score.
    plus_area: float = 0.0
    minus_area: float = 0.0

    # True when evaluation stopped early under branch-and-bound pruning, so
    # the counts above are lower bounds rather than totals.
    pruned: bool = False

    # False for a sweep pass that measured only the release verdict. See
    # FaceAccessibility.four_way.
    four_way: bool = True

    # Surface area formed by declared side actions. Not part of
    # total_area, so accessibility and severity are ratios over the
    # surface the two main halves are actually responsible for.
    delegated_area: float = 0.0

    @property
    def accessibility(self) -> float:
        """Share of surface area released by a straight pull, in [0, 1]."""
        if self.total_area <= 0.0:
            return 0.0
        return self.accessible_area / self.total_area

    @property
    def undercut_severity(self) -> float:
        """Share of surface area that is trapped, in [0, 1].

        Area normalised by the part's own surface, so it can be compared
        between parts and is not dominated by absolute size.
        """
        if self.total_area <= 0.0:
            return 0.0
        return self.undercut_area / self.total_area

    def region_of(self, face_id: int) -> MoldRegion:
        entry = self.faces.get(face_id)
        return entry.region if entry else MoldRegion.AMBIGUOUS


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class AccessibilityAnalyzer:
    """Answers accessibility questions about one part, caching ray results.

    A single part is probed along many candidate axes, and the axis sweep,
    the classifier and the undercut-region grouper all ask overlapping
    questions. The blocked/free answer for a given (sample, direction) is a
    pure function of the geometry, so it is memoised here and every later
    stage gets it for free.
    """

    def __init__(
        self,
        faces: List[FaceData],
        raycaster: Optional[UndercutRaycaster] = None,
        config: Optional[AnalysisConfig] = None,
        delegated: Optional[frozenset] = None,
    ):
        self.faces = faces
        self.config = resolve(config)
        # Face ids formed by a declared side action. Excluded from every
        # undercut tally, because the pull direction is not responsible
        # for releasing them.
        self.delegated = frozenset(delegated or ())
        self.raycaster = raycaster if raycaster is not None else UndercutRaycaster(faces)
        # (face_id, sample_index, rounded direction) -> blocked?
        self._cache: Dict[Tuple[int, int, Tuple[int, int, int]], bool] = {}

    # -- ray access ---------------------------------------------------------

    @staticmethod
    def _dir_key(d: Vector3) -> Tuple[int, int, int]:
        """Cache key for a direction, quantised to ~0.001 of a unit vector."""
        return (round(d[0] * 1000), round(d[1] * 1000), round(d[2] * 1000))

    def is_blocked(
        self,
        face_id: int,
        sample_index: int,
        point: Vector3,
        normal: Vector3,
        direction: Vector3,
    ) -> bool:
        key = (face_id, sample_index, self._dir_key(direction))
        hit = self._cache.get(key)
        if hit is None:
            hit = self.raycaster.is_blocked(point, normal, direction)
            self._cache[key] = hit
        return hit

    # -- per-face analysis --------------------------------------------------

    def _samples(
        self, face: FaceData, max_samples: Optional[int]
    ) -> List[Tuple[int, Vector3, Vector3]]:
        """(original index, point, normal) triples, optionally thinned.

        The original index is carried through so a thinned pass and a full
        pass share cache entries for the samples they have in common.
        """
        pts = face.sample_points or [face.center]
        nrms = face.sample_normals or [face.normal]
        n = min(len(pts), len(nrms))
        idxs = list(range(n))
        if max_samples is not None and 1 < max_samples < n:
            idxs = [round(i * (n - 1) / (max_samples - 1)) for i in range(max_samples)]
        return [(i, pts[i], nrms[i]) for i in idxs]

    def analyze_face(
        self,
        face: FaceData,
        direction: Vector3,
        max_samples: Optional[int] = None,
        four_way: bool = True,
    ) -> FaceAccessibility:
        """Accessibility of one face along `direction`.

        `four_way=True` measures reachability from BOTH sides, which is what
        the region classification and everything downstream of it need.

        `four_way=False` measures only the RELEASE verdict, which is all the
        direction sweep needs to rank axes. That halves the ray count: the
        release test consults one direction for any sample whose normal faces
        the mold, and only samples lying parallel to the pull need both.
        Measuring the full four-way for every candidate axis doubled the sweep
        cost on Part 3 (13s to 29s) to compute reachability numbers that only
        the winning axis ever uses. In this mode the region comes from the
        sample-normal vote instead, which is exactly the classifier's own
        first tier and is ample for a tie-break metric.
        """
        cfg = self.config
        eps = cfg.classification_epsilon
        pull = direction
        neg = (-pull[0], -pull[1], -pull[2])

        samples = self._samples(face, max_samples)
        total = len(samples)
        if total == 0:
            return FaceAccessibility(
                face_id=face.face_id, sample_count=0,
                plus_fraction=0.0, minus_fraction=0.0,
                both_fraction=0.0, neither_fraction=0.0,
                trapped_fraction=0.0, is_undercut=False,
                region=MoldRegion.AMBIGUOUS, area=face.area,
                four_way=four_way,
            )

        n_plus = n_minus = n_both = n_neither = 0
        n_trapped = 0
        # Normal-side tally: how the face's own samples face the pull axis.
        # Drives the CORE/CAVITY call when reachability cannot separate them.
        w_cavity = w_core = 0

        for idx, p, nv in samples:
            d = _dot(nv, pull)

            if four_way:
                blocked_plus = self.is_blocked(face.face_id, idx, p, nv, pull)
                blocked_minus = self.is_blocked(face.face_id, idx, p, nv, neg)
                free_plus = not blocked_plus
                free_minus = not blocked_minus

                if free_plus:
                    n_plus += 1
                if free_minus:
                    n_minus += 1
                if free_plus and free_minus:
                    n_both += 1
                if not free_plus and not free_minus:
                    n_neither += 1

            # RELEASE: the half that forms this sample must be able to pull
            # away from it. Which half that is comes from the sample normal.
            if d > eps:
                w_cavity += 1
                trapped = (
                    blocked_plus if four_way
                    else self.is_blocked(face.face_id, idx, p, nv, pull)
                )
            elif d < -eps:
                w_core += 1
                trapped = (
                    blocked_minus if four_way
                    else self.is_blocked(face.face_id, idx, p, nv, neg)
                )
            else:
                # Parallel to the pull axis: escapes with either half, so it
                # is trapped only when both ways are shut.
                if four_way:
                    trapped = blocked_plus and blocked_minus
                else:
                    trapped = (
                        self.is_blocked(face.face_id, idx, p, nv, pull)
                        and self.is_blocked(face.face_id, idx, p, nv, neg)
                    )
            if trapped:
                n_trapped += 1

        trapped_fraction = n_trapped / total
        is_undercut = trapped_fraction >= cfg.undercut_fraction_threshold

        entry = FaceAccessibility(
            face_id=face.face_id,
            sample_count=total,
            plus_fraction=n_plus / total if four_way else w_cavity / total,
            minus_fraction=n_minus / total if four_way else w_core / total,
            both_fraction=n_both / total if four_way else 0.0,
            neither_fraction=n_neither / total if four_way else 0.0,
            trapped_fraction=trapped_fraction,
            is_undercut=is_undercut,
            region=MoldRegion.AMBIGUOUS,
            area=face.area,
            four_way=four_way,
        )
        entry.region = (
            self._region_for(entry, w_cavity, w_core) if four_way
            else self._region_from_normals(entry, w_cavity, w_core)
        )
        return entry

    @staticmethod
    def _region_from_normals(
        a: FaceAccessibility, w_cavity: int, w_core: int
    ) -> MoldRegion:
        """Region from the sample-normal vote alone, for the sweep pass.

        No reachability rays. Used only to count connected same-half regions
        as the parting-complexity tie-break, where an approximation is
        appropriate; the winning direction is re-measured four-way.
        """
        if a.is_undercut:
            return MoldRegion.UNDERCUT
        if w_cavity > w_core:
            return MoldRegion.CAVITY
        if w_core > w_cavity:
            return MoldRegion.CORE
        return MoldRegion.NEUTRAL

    def _region_for(
        self, a: FaceAccessibility, w_cavity: int, w_core: int
    ) -> MoldRegion:
        """Turn accessibility fractions into a mold region.

        Follows the specification's table, with the release verdict taking
        precedence: a face the forming half cannot pull away from is an
        undercut whatever the reachability numbers say.
        """
        if a.is_undercut:
            return MoldRegion.UNDERCUT

        thresh = self.config.access_fraction_threshold
        reach_plus = a.plus_fraction >= thresh
        reach_minus = a.minus_fraction >= thresh

        # Pull points toward the cavity, so "+D only" means only the cavity
        # steel can touch this surface.
        if reach_plus and not reach_minus:
            return MoldRegion.CAVITY
        if reach_minus and not reach_plus:
            return MoldRegion.CORE
        if not reach_plus and not reach_minus:
            # Not released by either half, yet not flagged trapped: the
            # measurements disagree, so say so rather than guess.
            return MoldRegion.AMBIGUOUS

        # Reachable from both halves. If the face clearly faces one way, that
        # half forms it; if its samples are split or parallel to the axis, it
        # is a near-parting surface and topology has to decide.
        if w_cavity > w_core:
            return MoldRegion.CAVITY
        if w_core > w_cavity:
            return MoldRegion.CORE
        return MoldRegion.NEUTRAL

    # -- whole-part analysis ------------------------------------------------

    def analyze(
        self,
        direction: Vector3,
        max_samples: Optional[int] = None,
        abort_above_area: Optional[float] = None,
        faces: Optional[List[FaceData]] = None,
        four_way: bool = True,
    ) -> AccessibilityResult:
        """Accessibility of every face along `direction`.

        `abort_above_area` enables branch-and-bound pruning during the axis
        sweep: faces are visited largest-first and evaluation stops once the
        accumulated undercut area passes the incumbent best, because the axis
        has already lost. The result is then marked `pruned` and its counts
        are lower bounds.

        `four_way=False` is the cheap sweep pass — see `analyze_face`.
        """
        target = faces if faces is not None else self.faces
        ordered = (
            sorted(target, key=lambda f: -f.area)
            if abort_above_area is not None else target
        )

        result = AccessibilityResult(direction=direction, four_way=four_way)
        for face in ordered:
            if face.face_id in self.delegated:
                # A declared side action forms this face. It is neither
                # released nor trapped by the pull direction, so it is
                # recorded and then left out of every tally below.
                entry = self.analyze_face(face, direction, max_samples, four_way)
                entry.is_undercut = False
                entry.region = MoldRegion.DELEGATED
                result.faces[face.face_id] = entry
                result.delegated_area += face.area
                continue
            entry = self.analyze_face(face, direction, max_samples, four_way)
            result.faces[face.face_id] = entry
            result.total_area += face.area
            if entry.is_undercut:
                result.undercut_count += 1
                result.undercut_area += face.area
            else:
                result.accessible_area += face.area
            result.plus_area += face.area * entry.plus_fraction
            result.minus_area += face.area * entry.minus_fraction

            if abort_above_area is not None and result.undercut_area > abort_above_area:
                result.pruned = True
                break

        return result

    def apply_to_faces(
        self, result: AccessibilityResult, faces: Optional[List[FaceData]] = None
    ) -> None:
        """Write a result's verdicts onto the FaceData objects.

        The rest of the engine, the API and the viewer all read
        `face.is_undercut` / `face.trapped_fraction` / `face.mold_region`, so
        the chosen direction's result is stamped onto the faces once it is
        settled. Keeping this explicit is what lets several directions be
        evaluated without one clobbering another's numbers.
        """
        for face in (faces if faces is not None else self.faces):
            entry = result.faces.get(face.face_id)
            if entry is None:
                continue
            face.is_undercut = entry.is_undercut
            face.trapped_fraction = entry.trapped_fraction
            face.mold_region = entry.region.value
            face.is_delegated = entry.region == MoldRegion.DELEGATED
