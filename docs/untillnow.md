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

---

# 2026-08-17 16:44 IST — Parting line v4: geometry-driven rebuild

Everything above this line is the Part 1 flat-parting-line investigation and
still stands. This section records the rebuild of the parting-line pipeline
against `docs/prompts/parting-line-implementation.md`, and the two Part 3
investigations that followed it.

## What was rebuilt

The parting line is now derived from mold accessibility and region
classification instead of from edge selection. New package `core/parting/`
(boundary → loops → silhouette → validation → analyzer) plus three shared
modules outside it (`pull_direction.py`, `accessibility.py`,
`direction_evaluation.py`) and one config module (`tolerances.py`).

Public API unchanged: `find_parting_line`, `find_all_parting_lines`,
`compute_parting_line_result`, `CandidateLoop`, `CANDIDATE_AXES` all keep
their signatures. JSON response is additive only.

## Three defects found and fixed

**1. Undercut pollution of the candidate edge set.** A trapped face still gets
a mold half, so a boundary pass comparing only halves emitted the entire
outline of every undercut pocket as parting candidates. Measured on Part 3:
**48 of 51 candidate edges bordered an undercut face** — 94% of the candidate
set was two rib pockets. The correct rim won only by outscoring them; a larger
pocket would have won. Such edges are now classified as SHUTOFFS and excluded.

**2. Two degenerate scoring terms.** `projected_area` (40% weight) was
normalised against the other candidates, so the winner always scored 1.0 on it
and it carried no absolute signal. `outer_confidence` (20%) divided by a
BOUNDING BOX, capping any circular rim at pi/4 = 0.785 however well it matched
the part. Selection is now lexicographic against the true silhouette area.

**3. No answer for a non-axial pull.** When the pull crosses the part axis the
split is a clamshell plane through the middle of the outer wall, where the
B-rep has no edge at all. Every candidate loop then had projected area exactly
0.0 and the engine picked an internal groove edge, reporting 0.706 confidence
with no failure signal. `core/parting/silhouette.py` computes analytic horizon
curves (cylinder, cone, plane) and runs only when validation rejects the
topological result.

## Correction to "Silhouette splitting — no-op on Part 1" above

That line remains true **for Part 1** and for any part pulled along its own
dominant axis: 0 of 311 faces have the silhouette crossing them mid-surface.
It is NOT true in general. For a pull perpendicular to the part axis the
silhouette is the only thing that can produce a parting line, because no edge
lies on the split. The `oring_nozzle` fixture went from `xfail` to passing on
exactly this.

## More approaches that were measured wrong

Added to the list above so they are not retried.

- **Penalising NEUTRAL faces as parting complexity** — rewards tilting the axis
  a few degrees off the part's real axis, because every side wall then picks up
  a small non-zero `n·d` and stops reading as neutral. On `flanged_boss` this
  let an axis **3.9 degrees off Z** beat Z and put the flange and the boss in
  the same mold half. A clean two-plate mold is full of neutral faces; they are
  the surfaces the parting line runs along, not a defect.
- **Area balance as the primary complexity term** — a 45-degree pull splits most
  parts more evenly than their true axis, so balance alone chose a diagonal on
  `stepped_cylinder` where the answer is plainly Z. Balance survives only as a
  late tie-break.
- **Ranking global axes above feature axes** — the tie-break for "dominant
  geometric axis" was useless, because an axis is normally proposed by the
  fixed set BEFORE any geometry source sees it. On `flanged_boss` a sideways
  clamshell (Y−, zero undercuts, tied on every earlier criterion) beat the
  axial pull. An axis now accumulates every source that proposes it and takes
  the best rank.
- **Trusting principal axes at exact-axis precision** — UV sampling is not
  area-uniform (five samples round a cylinder land at 0.63, 1.88, 3.14, 4.40,
  5.65 rad), so a perfectly axisymmetric part yields a slightly
  non-axisymmetric covariance. Eigenvalue-separation alone does not fix it: on
  `flanged_boss` the top eigenvector was well-separated AND 3.9 degrees off Z.
  Principal axes are now deduplicated at 10 degrees, not 2.6.
- **Treating NEUTRAL faces as blocking region connectivity** — made an ordinary
  flanged boss read as 3 regions under its own axis while a sideways clamshell
  read as 2, so the optimiser preferred the clamshell. Neutral faces now
  conduct connectivity without belonging to either side.
- **Specification section 5 Priority 3, "maximize accessibility", as a sort
  criterion** — provably cannot discriminate. Accessibility is released area
  over total area, and total area is a property of the PART, identical for
  every candidate direction, so it is a strictly decreasing function of
  undercut area and criterion 2 already orders by it. Removed from the key,
  kept as a reported figure.

## Bugs the new tests caught during the rebuild

- Loop tracing seeded mid-path, splitting one gap into two open chains.
- Silhouette clipping stopped ~0.5 mm short of face boundaries, so nothing
  chained; endpoints are now bisection-refined to the trim.
- The parting plane was placed at the surface-sample centroid, which sampling
  bias put 6.7 mm off the axis of a symmetric part; now the bounding-box centre.
- Convex hull of sparse UV samples underestimated a circular silhouette by 27%;
  now sampled from the shape's edges at 32 points each.
- `tests/synthetic_parts._export` caches by NAME only, so calling a builder
  twice with different dimensions silently returns the first export. Documented,
  and `solid_cube` added as its own fixture rather than parameterising
  `solid_box`.

## Part 3 investigation A — is the parting line in the wrong place?

Hypothesis: the ø36 @ z=4 loop is a sub-feature, not the true silhouette, and
some of the 88 undercuts are a classification artifact like Part 1's.

**Verdict: no. The loop is at the true silhouette maximum and all 88 undercuts
are genuine.**

- Global max silhouette radius is **18.000**, not the 19.49 the bounding box
  reports — OCC bounds curved surfaces by control polygons (18 × 1.083).
- Running-max split test: the only band where nothing below and nothing above
  is wider is **z ∈ [1.00, 4.50]**. The loop sits at z=4.00, inside it.
- All 88 trapped faces are in **z ∈ [12.35, 21.65], r ∈ [9.50, 12.48]** — two
  stacked circumferential slots, two symmetric regions of 44 faces / 683.4 mm²
  each, 171.9° span.
- Ray probe: faces **21 (z=15.5) and 23 (z=18.5) are blocked in BOTH ±Z**
  (6.01 mm one way, 2.99 mm the other). No mold half, on any parting surface
  planar or stepped, can form them.
- **Forced-split invariance**: six placements (r=18/z=4, r=18/z=1, r=6/z=1,
  r=6/z=39) → undercut set **byte-identical**, 88 faces / 1366.8 mm², same IDs.
- Pocket fill: 1366.8 → **5.2 mm²**, parting line unchanged at r=18/z=4.

## Part 3 investigation B — second loop, and the clamshell hypothesis

**Second closed loop: real, and already reported.** ø12 at z=1.00, one full
circle (37.699 = 2π×6), between face **320** (bore lead-in chamfer, cavity) and
face **35** (the through-bore, core). It is the cavity/core-pin shutoff inside
the bore. Loop tracing always found it; before this rebuild `api.py` sent only
the primary loop unless `?debug=true`, so it never reached the viewer.

Boundary census on Part 3: `shutoff 216, interior 738, neutral 3, degenerate
24`. All **3** parting candidates are consumed — two half-circles at r=18 z=4
form the primary, one full circle at r=6 z=1 forms the second. Nothing dropped.

**Nothing exists at the back end.** Above z=30: **280 faces, all core, 0
undercut, 0 parting candidates**. The 12-tooth spline (z 32–40, r 8–12.1) is
fully releasable and geometrically separate from the 88.

**Clamshell hypothesis: evaluated, releases the slots, still loses.** A
clamshell's halves separate along the parting plane's NORMAL, so a
plane-through-axis split IS a single lateral pull; the production search
already tried 6 such orientations and the hemisphere sweep 12 more. A refined
36-orientation sweep at 5°:

| | faces | area | slots trapped |
|---|---|---|---|
| Axial Z | 88 | 1366.8 mm² (18.1%) | 16/16 |
| Best clamshell, t=35° | 155 | **2080.0 mm²** (27.5%) | **0/16** |

The two undercut sets are **entirely disjoint** — the clamshell releases all 88
and traps 155 others. What it trades them for: face **35, the bore, 1432.57 mm²
at trapped_fraction 1.00**, which alone exceeds the whole axial undercut set (a
through-bore whose axis lies in the parting plane needs an axial side core),
plus **589.7 mm²** of spline teeth. Axial Z− with two opposed sliders stays the
answer.

**Measurement artifact found and discarded.** A "permissive" rule (trapped only
if blocked both ways) suggested the clamshell was better, 227.8 vs 893.7 mm².
It is wrong: probing the bore shows the −D ray re-enters solid material at
**0.0305 mm**, below `MIN_HIT_DISTANCE = 0.1 mm`, so the graze filter discards
a genuine obstruction and the face reads free. The engine does not use that
rule — it was invented for the analysis — so there is no production impact, but
the graze filter can mask an obstruction within 0.1 mm and that is worth
knowing.

## Test suite

**31 passed / 1 xfail → 86 passed, 0 failures.** The `oring_nozzle` clamshell
case that Bosch drew on the review call went from expected-failure to passing.
New files: `tests/test_pull_direction.py` (30 tests), `tests/test_parting_pipeline.py`
(21 tests).

---

# 2026-08-18 08:55 IST — Part 3 clamshell with delegated side cores

Follow-on to the 2026-08-17 Part 3 work. Same part, same engine, no code
changed — this section is measurement only. It revisits the clamshell
hypothesis under a different **accounting rule**, and the conclusion moves.

## The reference source now exists in the repo

`docs/bosch-nozzle-review-transcript.md` was added on 2026-08-18. The two
earlier investigations recorded that no transcript existed and fell back to the
quote preserved in `tests/synthetic_parts.py`. The transcript confirms that
quote and adds two things worth recording:

- **02:11.7** — *"Even if you bring the parting line here or if you bring the
  parting line here, then, uh, some — one of the features will be locked by the
  … steel."* Independent confirmation of the forced-split invariance measured
  on 2026-08-17: moving a parting line cannot release an undercut.
- **00:42.8 / 01:28.5** — the model is two main halves plus **one** side core,
  for the internal passage of a part that has no splines. Delegating a *second*
  feature group is an extrapolation of that principle, not something the video
  shows.

## Investigation C — clamshell with the bore delegated

Earlier runs counted the through-bore as trapped *by* the clamshell. Modelling
it the way the video does — a dedicated side core forms it, so it does not
count against the pull direction — changes the answer.

Excluded: faces **35** (bore, r=6), **319**, **320** (mouth chamfers) =
1548.1 mm². The same exclusion applied to axial changes nothing, because the
bore is not trapped under an axial pull — which is itself the finding: axial
needs no side core for it.

| | trapped faces | trapped area |
|---|---|---|
| Axial Z−, all faces | 88 | 1366.8 mm² |
| Axial Z−, bore excluded | 88 | 1366.8 mm² |
| Clamshell t=35°, all faces | 155 | 2080.0 mm² |
| **Clamshell t=35°, bore excluded** | **152** | **531.9 mm²** |

**−834.9 mm², 61% less trapped area**, and **0/16** of the named slot faces
still trapped (19, 1, 23, 5, 21, 3, 25, 7 and 20, 2, 24, 6 all go 1.00 → 0.00;
322, 323, 363, 364 go 0.57 → 0.00).

Re-swept all 36 orientations with the bore excluded: range **531.9–727.9 mm²**,
**every one beats axial's 1366.8**. Best t=35° (tied 65°, 155°). At every
orientation 100% of the remaining area is the splined section.

Region grouper on the remaining 531.9 mm²: **12 regions**, spans 0.8°–9.7°, and
**10 of the 12 report side-action axis (0, 0, ±1)** — the part axis. Axial for
comparison: **2 regions**, 171.9° span each, `side_action_axes = 1`.

## Investigation D — clamshell with bore AND splines delegated

Spline group defined two ways, because the brief's definition is
orientation-dependent and cannot survive a re-sweep:

- **(a)** the 152 faces / 531.9 mm² trapped at t=35°. (Face 319 also sits at
  z ≥ 31 but belongs to the bore group; counting it gives the 153 / 589.7 mm²
  figure that appears in the raw output.)
- **(b)** the whole splined section, z ≥ 31: **280 faces / 1365.1 mm²**. The
  physically coherent model — an axial insert forming that end forms every
  surface on it.

At t=35°, **full sample resolution**:

| | surface left to the 2 halves | still trapped |
|---|---|---|
| (a) bore + trapped-only splines | 259 faces / 5482.1 mm² | **0 / 0.00 mm²** |
| (b) bore + whole z≥31 section | 132 faces / 4706.7 mm² | **0 / 0.00 mm²** |

**Genuinely zero, not near-zero.** (b) is the stricter test: it leaves less
delegated slack, 62% of the part still on the two halves, and all of it
releases.

The optimum is a **plateau, not a point** — re-checked at full resolution:

```
t= 25.0   10 faces /  19.52 mm2   [328,329,333,337,341,387,388,392,396,400]
t= 30.0    0 faces /   0.00 mm2
t= 35.0    0 faces /   0.00 mm2
t= 40.0    0 faces /   0.00 mm2
t= 45.0    0 faces /   0.00 mm2
t= 50.0    0 faces /   0.00 mm2
t= 55.0    2 faces /   0.74 mm2   [346, 369]
t=130.0    0 faces /   0.00 mm2
```

Continuous zero from **30° to 50°** plus an isolated zero at 130°, degrading
gently outside it. Worst orientation over all 36 is t=100° at 154.8 mm². The
orientation does not need to be hit precisely.

## Investigation E — the symmetric check that reframes it

If the clamshell may delegate its bore and splines, axial may delegate its
slots. Measured:

```
AXIAL Z- trapped (nothing delegated):  88 faces / 1366.8 mm2
         after delegating the slots :   0 faces /    0.0 mm2
         surface still on 2 halves  : 326 faces / 6195.3 mm2
```

| | main halves | delegated actions | motion axes | remaining trapped | surface on the halves |
|---|---|---|---|---|---|
| Axial Z− | ±Z | 2 opposed sliders, 1 lateral axis | 2 | **0** | 326 faces / **6195.3 mm²** (82%) |
| Clamshell t=35° | ±D=(0.8192,0.5736,0) | bore core ±Z + spline core ±Z | 2 | **0** | 132 faces / **4706.7 mm²** (62%) |

**Both reach zero. Both need two delegated actions on one extra axis.** The
clamshell needs four pieces of steel and three distinct motions (±D for the
halves, ±Z for both cores).

## Verdict

The clamshell hypothesis is **viable** — not blocked by geometry, with a real
30°–50° solution window. It was wrong to treat the earlier 2080.0 mm² figure as
settling the question; that number counted the bore against the clamshell while
the reference model puts it on a side core.

But **delegation always terminates at zero**: any undercut set reaches zero if
you delegate the faces that constitute it. Trapped area is therefore not the
discriminating metric once side cores are in play. The metrics that do
discriminate are how much surface the main halves retain (82% axial vs 62%
clamshell) and how many independent actions the mold needs (2 either way).
Which is cheaper to build is a tooling-cost judgement, not a geometry one, and
is not settled by any measurement in this document.

**No pipeline change follows from this.** The engine ranks single pull
directions with nothing delegated, which is the right default: it cannot know
in advance which features a mold designer intends to put on side cores. If a
"delegate this feature group" input is ever wanted, that is a new capability
with its own API, not a fix.
