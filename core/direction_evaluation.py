"""
core/direction_evaluation.py — Scoring and selecting a mold pull direction.

Specification sections 5 and 6: every candidate axis is evaluated into a
structured result, and the best one is chosen by an explicit, deterministic,
lexicographic comparison rather than by a weighted sum of loosely-scaled
numbers.

WHY LEXICOGRAPHIC
-----------------
A weighted sum lets a large advantage on a cheap term buy off a small
disadvantage on an expensive one. That is exactly the failure the
specification forbids: a direction with many undercuts must never win because
its parting line happens to be shorter. Undercuts cost tooling — a slider, a
lifter, a split cavity — and no amount of parting-line elegance compensates.
Ordering the criteria makes that impossible by construction rather than by
hoping the weights are large enough.

THE ORDER
---------
    1. undercut existence      any undercuts at all?
    2. undercut area           how much surface is trapped
    3. undercut count          how many faces
    4. parting complexity      how tangled the resulting split would be
    5. source rank             prefer a dominant geometric axis
    6. balance                 how evenly the part divides between halves
    7. canonical vector        final deterministic tie-break

Criterion 1 is the specification's Priority 1, which it words as "minimize
undercut existence/count". Criteria 2 and 3 order area ahead of count, which
is Bosch's explicit instruction from the 2026-07-28 review call: "if there is
some cut/mark in a face, if you count it as one -- area will be better to
evaluate". A face that the CAD kernel happened to split into six patches must
not outrank one large trapped face. Splitting the specification's Priority 1
into existence-then-area is what satisfies both: nothing with undercuts can
ever beat something without them, and among the rest area leads.

Criteria 6 and 7 exist so the answer never depends on dictionary ordering,
face iteration order or floating-point noise. Two genuinely equivalent axes
resolve to the same one on every run and every machine.

A 0..1 `score` is also reported for display and for the API. It is derived
from the same numbers but it is NOT what selection uses, so a rounding
artifact in the score can never change which direction wins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from core.accessibility import AccessibilityResult, MoldRegion
from core.pull_direction import PullDirection

Vector3 = Tuple[float, float, float]


@dataclass
class DirectionEvaluation:
    """Everything measured about one candidate pull axis."""

    direction: PullDirection
    accessibility_result: AccessibilityResult

    undercut_count: int = 0
    undercut_area: float = 0.0
    undercut_severity: float = 0.0      # trapped area / total area, [0, 1]
    accessibility: float = 0.0          # released area / total area, [0, 1]
    complexity: float = 0.0             # estimated parting topology cost, [0, 1]
    region_count: int = 0               # connected same-half regions
    balance: float = 0.0                # 0 even split, 1 all one side
    score: float = 0.0                  # display only — selection uses sort_key

    # True when branch-and-bound pruning stopped this evaluation early, so
    # count and area are lower bounds rather than totals.
    pruned: bool = False

    @property
    def vector(self) -> Vector3:
        return self.direction.vector

    @property
    def has_undercuts(self) -> bool:
        return self.undercut_count > 0

    def to_dict(self) -> dict:
        return {
            "direction": list(self.vector),
            "label": self.direction.label,
            "source": self.direction.source,
            "undercut_count": self.undercut_count,
            "undercut_area": round(self.undercut_area, 1),
            "undercut_severity": round(self.undercut_severity, 4),
            "accessibility": round(self.accessibility, 4),
            "complexity": round(self.complexity, 4),
            "score": round(self.score, 4),
            "pruned": self.pruned,
        }


# ---------------------------------------------------------------------------
# Parting complexity
# ---------------------------------------------------------------------------

def count_mold_regions(
    access: AccessibilityResult,
    adjacency: dict,
) -> int:
    """Number of connected same-half regions the surface breaks into.

    This is the honest measure of parting topology, and it is cheap: one core
    region facing one cavity region produces ONE parting loop, while every
    extra alternation adds another. Neutral and ambiguous faces are treated as
    transparent — they conduct connectivity without belonging to either side —
    because a side wall parallel to the pull does not interrupt a region, it
    is the surface the parting line runs along.

    Returns 0 when nothing is classified, which the caller treats as maximally
    complex.
    """
    members = {
        fid: entry.region
        for fid, entry in access.faces.items()
        if entry.region in (MoldRegion.CORE, MoldRegion.CAVITY)
    }
    if not members:
        return 0

    # Faces that belong to neither half but do not interrupt one either.
    passthrough = {
        fid for fid, entry in access.faces.items()
        if entry.region in (MoldRegion.NEUTRAL, MoldRegion.AMBIGUOUS)
    }

    seen: set = set()
    # A pass-through face can conduct for BOTH halves — a side wall with core
    # below it and cavity above — so it is visited once per half.
    seen_passthrough: set = set()
    components = 0

    for seed in sorted(members):
        if seed in seen:
            continue
        components += 1
        half = members[seed]
        stack = [seed]
        while stack:
            current = stack.pop()
            if current in members:
                if current in seen:
                    continue
                seen.add(current)
            else:
                if (current, half) in seen_passthrough:
                    continue
                seen_passthrough.add((current, half))

            for neighbour in sorted(adjacency.get(current, ())):
                if neighbour in members:
                    # Same half continues the region; the opposite half is
                    # where the parting line runs, so the walk stops there.
                    if members[neighbour] == half and neighbour not in seen:
                        stack.append(neighbour)
                elif neighbour in passthrough:
                    # Conduct THROUGH: a face parallel to the pull is the
                    # surface the parting line runs along, not a break in the
                    # region. Counting it as a break made an ordinary flanged
                    # boss read as 3 regions under its own axis (flange
                    # underside, flange top, boss top — the last two separated
                    # only by the neutral boss wall between them) while a
                    # sideways clamshell read as 2, so the optimiser preferred
                    # the clamshell on a part that is plainly an axial draw.
                    if (neighbour, half) not in seen_passthrough:
                        stack.append(neighbour)
    return components


def region_balance(access: AccessibilityResult) -> float:
    """How lopsided the core/cavity split is, 0 (even) to 1 (all one side).

    A direction that puts almost everything on one side leaves a parting line
    that has to detour around every feature on the thin side. Used late in
    the ordering, as a numeric tie-break, never as a primary criterion.
    """
    core = sum(
        e.area for e in access.faces.values() if e.region == MoldRegion.CORE
    )
    cavity = sum(
        e.area for e in access.faces.values() if e.region == MoldRegion.CAVITY
    )
    total = core + cavity
    if total <= 0.0:
        return 1.0
    return abs(core - cavity) / total


def estimate_parting_complexity(
    access: AccessibilityResult,
    face_adjacency: Optional[dict] = None,
) -> float:
    """Cheap estimate of how tangled this direction's parting line will be.

    Building the real loops for every candidate axis would mean running the
    whole downstream pipeline once per direction, which is far too expensive
    for a sweep, so the region COUNT stands in for it: two regions means one
    loop, and every extra alternation means another. Scaled so two regions —
    the two-plate ideal — reads 0.

    Falls back to the area balance when no adjacency is available, which is
    weaker but never worse than nothing.

    TWO PROXIES THAT WERE TRIED AND ARE WRONG, kept here so they are not
    reintroduced:

      NEUTRAL-FACE PENALTY. Counting faces parallel to the pull as complexity
      rewards tilting the axis a few degrees off the part's real axis, because
      then every side wall picks up a small non-zero `n·d` and stops reading
      as neutral. On the flanged boss that let an axis 3.9 degrees off Z beat
      Z itself and put the flange and the boss in the same mold half. A clean
      two-plate mold is FULL of neutral faces; they are the surfaces the
      parting line runs along, not a defect.

      AREA BALANCE AS THE PRIMARY TERM. A 45-degree pull splits most parts
      more evenly than their true axis does, so balance alone preferred a
      diagonal on the stepped cylinder, where the answer is plainly Z. Balance
      does capture something real — a 99/1 split is a bad split — so it
      survives as a late numeric tie-break in the sort key, but it cannot
      lead.

    Returns 0 (simple) to 1 (tangled).
    """
    if face_adjacency:
        regions = count_mold_regions(access, face_adjacency)
        if regions <= 0:
            return 1.0
        # 2 regions -> 0.0, 3 -> 0.33, 4 -> 0.5, 10 -> 0.8.
        return max(0.0, 1.0 - 2.0 / max(2, regions))

    return min(1.0, region_balance(access))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_pull_direction(
    direction: PullDirection,
    access: AccessibilityResult,
    face_adjacency: Optional[dict] = None,
) -> DirectionEvaluation:
    """Package one direction's accessibility measurements into a score.

    Named for the specification's pseudocode (section 5) and deliberately NOT
    `evaluate_direction`, which already exists in `core.undercut_detector`
    with a different signature and return type.

    `face_adjacency` ({face_id: {neighbour ids}}) enables the region-count
    complexity measure; without it the estimate falls back to area balance.
    """
    ev = DirectionEvaluation(
        direction=direction,
        accessibility_result=access,
        undercut_count=access.undercut_count,
        undercut_area=access.undercut_area,
        undercut_severity=access.undercut_severity,
        accessibility=access.accessibility,
        complexity=estimate_parting_complexity(access, face_adjacency),
        region_count=count_mold_regions(access, face_adjacency) if face_adjacency else 0,
        balance=region_balance(access),
        pruned=access.pruned,
    )
    ev.score = _display_score(ev)
    return ev


def _display_score(ev: DirectionEvaluation) -> float:
    """A 0..1 number for the UI. Never used to choose a direction.

    Weighted so the reported figure agrees with the lexicographic ordering in
    the common cases: undercut severity dominates, accessibility and
    simplicity fill in the rest. Its only job is to let a user see at a glance
    how far apart two candidates are.
    """
    severity_term = 1.0 - min(1.0, ev.undercut_severity)
    access_term = ev.accessibility
    simplicity_term = 1.0 - ev.complexity
    score = 0.70 * severity_term + 0.20 * access_term + 0.10 * simplicity_term
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

# Undercut areas within this many mm^2 of each other are treated as equal, so
# that float noise on two geometrically identical axes cannot decide the
# winner. Well below any real trapped feature.
_AREA_EQUAL_TOL = 1e-6

# Accessibility and complexity are ratios; quantise before comparing so a
# difference in the twelfth decimal does not pre-empt the source tie-break.
_RATIO_DECIMALS = 6


def direction_sort_key(ev: DirectionEvaluation) -> tuple:
    """Lexicographic ordering key. Lower is better.

    See the module docstring for why each criterion sits where it does.
    """
    return (
        # 1. Any undercuts at all — the dominant question.
        1 if ev.has_undercuts else 0,
        # 2. Trapped AREA (Bosch: area evaluates better than count).
        round(ev.undercut_area / _AREA_EQUAL_TOL),
        # 3. Trapped face COUNT, as the tie-break within equal area.
        ev.undercut_count,
        # NOTE ON THE SPECIFICATION'S PRIORITY 3, "maximize accessibility":
        # it is not a separate criterion here because it cannot be one.
        # `accessibility` is released area over total area, and total area is
        # a property of the PART, identical for every candidate direction. So
        # accessibility is a strictly decreasing function of undercut area and
        # criterion 2 already orders by it — a comparison here would never
        # fire. It stays on DirectionEvaluation and in the API because it is a
        # meaningful figure to show a user, but adding it to this key would be
        # a criterion that looks like it discriminates and never does. The
        # work Priority 3 is reaching for is done by parting complexity below,
        # which measures something genuinely independent.
        #
        # 4. Prefer the simpler parting topology. Region-count based, so it is
        #    naturally coarse: directions that genuinely produce the same
        #    number of loops tie here and fall through to the axis preference
        #    below, rather than being separated by a meaningless decimal.
        round(ev.complexity, _RATIO_DECIMALS),
        # 5. Prefer a dominant geometric axis over an arbitrary diagonal.
        #    Specification section 6 puts this after parting topology.
        ev.direction.rank,
        # 6. Prefer the more even split. A 99/1 division is a shallow parting
        #    line that has to work around everything on the thin side. Placed
        #    below the axis preference on purpose: a diagonal pull balances
        #    most parts better than their true axis does, so letting balance
        #    lead picks diagonals on parts whose answer is plainly an axis.
        round(ev.balance, _RATIO_DECIMALS),
        # 7. Deterministic final tie-break on the axis itself.
        tuple(round(c, 9) for c in ev.vector),
    )


def select_best_direction(
    evaluations: Sequence[DirectionEvaluation],
) -> DirectionEvaluation:
    """Pick the winning direction. Deterministic for a given part."""
    if not evaluations:
        raise ValueError("No candidate directions to select from.")
    return min(evaluations, key=direction_sort_key)


def rank_directions(
    evaluations: Sequence[DirectionEvaluation],
) -> List[DirectionEvaluation]:
    """All candidates, best first, by the same ordering used to select."""
    return sorted(evaluations, key=direction_sort_key)
