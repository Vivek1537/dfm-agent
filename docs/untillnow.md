# Flat parting line — what was wrong and what fixed it

## Symptom

Part 1's main parting line rendered as a 32-edge loop meandering between
z = 3 and z = 10, climbing around each snap-tab window. The Phase 1
submission had produced a flat 8-edge rim, which Bosch scored 2/2 ("closest
to a correct solution in terms of parting line").

## Cause

Not the pull direction, and not the parting-line module. `_vertical_wall_half`
in `core/face_classifier.py` classified a wall by reachability: blocked toward
the cavity means the core forms it, and vice versa. For Part 1's four outer
skirt walls and four corner rounds — 8 faces, 751.6 mm² — **both** halves
reach the wall and neither probe fires. Those faces fell through to a fixed
default of `cavity`, while every face around them (window lips, bottom
chamfer, brim undersides) resolved to `core`. The core↔cavity interface was
therefore forced to detour around all eight windows.

The ambiguity is real, not a gap in the probes: physics does not decide these
faces, and either assignment yields a manufacturable mould. Fu/Nee/Fuh (CAD
2002) and Majhi et al. treat exactly this set as free and resolve it by
optimising parting-line flatness. Bosch said the same thing in the review
call — "there could be multiple [parting lines] … this is also one of the
solution".

## Fix

Ambiguous walls are deferred, grouped into connected **regions**, and each
region is assigned by the **shared edge length** it has with already-decided
faces (`_resolve_ambiguous_regions`). The side with the greater shared length
wins, which yields the shorter core↔cavity interface — the mould-design
principle of keeping the split on the shortest closed boundary.

Two details carry the result:

- **Edge length, not face area.** Edge length is precisely the parting line
  produced; face area never appears in the boundary. Weighting the same vote
  by area makes the rule look like a no-op (Part 1's skirt reads 212 mm²
  cavity vs 27 mm² core and does not move).
- **Per region, not one global default.** This is what lets Part 1's 8-face
  skirt group go to the core while the synthetic cup fixtures' outer walls
  correctly stay on the cavity. A single global choice cannot separate them.

Undercut faces are excluded from voting: a side action releases them, so they
must not steer the main parting line.

## Result

| | before | after |
|---|---|---|
| Part 1 parting line | 32 edges, non-planar, z 3–10 | **8 edges, planar, z = 15** |
| Part 1 pull / undercuts | Z+ / 0 | Z+ / 0 (unchanged) |
| Part 3, cup holder, PLASTIC BUSH, PLASTIC SLEEVE, Coupler | — | byte-identical |

The change is surgical: only Part 1 moves. PLASTIC BUSH's parting line stays
at z = 0.00, which is the measured interface of the real mould's Cavity and
Core plates, so the external validation survives the fix.

## Approaches that were measured wrong

Kept so they are not retried without new evidence.

- **Selecting the pull sign by parting-line score** — inverts core/cavity on
  `capped_cup`. `projected_area` is normalised per run, so each sign's winning
  loop scores 1.0 on that term and it carries no cross-sign signal at all.
- **Resolving the ambiguous set by parting-line score** — picks the CLOSED end
  on both cup fixtures (0.763 vs 0.713) where the open end is correct, and
  produces a degenerate split with 12% of area in one half.
- **Parting-line-relative undercut marking** — vacuous. The classifier assigns
  every face to a half that can already reach it, so no face is ever assigned
  to a half that cannot release it.
- **Silhouette splitting** — no-op on Part 1: 0 of 311 faces have the
  silhouette crossing them mid-surface, so there is no curve to split at.

## Why it went unnoticed

The regression suite asserted pull sign, undercut count and "loop is closed",
but never planarity or location. `tests/test_parting_line_topology.py` now
asserts the primary loop is a single closed **planar** loop.
