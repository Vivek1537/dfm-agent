# Decision Log

This document records the key architectural and technical decisions made during the development of the AI-driven DfM (Design for Manufacturing) Tool.

## 1. Frontend Architecture: Streamlit vs. React + FastAPI
**Context**: The initial prototype was built using Streamlit (`app.py`) for rapid development and testing of the core python algorithms.
**Decision**: We transitioned to a separated architecture with a **FastAPI backend** and a **React frontend** (Vite + JavaScript).
**Rationale**: 
- Streamlit's 3D visualization capabilities (via PyVista/Trame) were clunky and limited for high-fidelity interactive models. 
- A React frontend using `@react-three/fiber` and `three.js` allows for a much more premium, dynamic, and responsive 3D viewer.
- The separation of concerns allows the backend to focus purely on heavy OpenCASCADE (cadquery) computations while the frontend handles rendering.

## 2. Undercut Detection Algorithm
**Context**: We needed a reliable way to determine if a face is an undercut (trapped) for a given mold pull direction.
**Decision (v2)**: Multi-sample physical raycasting using OpenCASCADE (`IntCurvesFace_ShapeIntersector`). Every face carries up to 15 surface samples (UV grid, `TopAbs_IN`-classified). Per sample: a face-cavity sample must escape along +pull, a face-core sample along −pull, a vertical-wall sample is trapped only if BOTH ways are blocked. A face is an undercut when ≥ 50% of its samples are trapped.
**Rationale**: Simple draft angle checks are insufficient for identifying true undercuts. Single-midpoint rays (v1, Phase 1) misclassified curved faces — a cylinder's midpoint normal misrepresents a surface whose normals span 360°. This was the root cause of the Phase 1 "wrongly marked undercut faces" feedback.

## 3. Tangential-Graze Filtering (replaces the v1 tiebreaker)
**Context**: Rays traveling parallel to vertical walls grazed adjacent blend fillets and reported phantom blockers — 4 false undercuts on the Phase 1 cap whose official answer is zero.
**Decision**: Only ray hits whose transition is `IntCurveSurface_In` (ray entering material) count as blockers; `Out`/`Tangent` hits are ignored. Minimum hit distance 0.1 mm, ray origin offset 0.01 mm.
**Rationale**: A grazing contact is not a physical obstruction to mold opening. After this filter, Part 1 reports exactly the judges' reference answer (0 undercuts).

## 4. Manufacturability Scoring Formula
**Context**: The initial score formula only penalized undercut *area*. Because of this, changing the pull direction often resulted in identical scores even if the *number* of undercut faces drastically increased.
**Decision**: We updated the scoring formula to penalize both undercut/warning **area** AND undercut/warning **count**.
**Rationale**: A part with 1 large undercut is often easier to fix than a part with 20 small scattered undercuts. Factoring in the face count provides a more nuanced, direction-sensitive manufacturability score.

## 5. Parting Line Identification
**Context**: Finding the optimal parting line for complex 3D shapes; Bosch requires ONE closed primary loop ("a discontinuous loop cannot form a surface — it is solid steel").
**Decision**: Extract all core↔cavity boundary edges, group into connected components, chain each component end-to-end with adaptive curve tessellation, verify closure, and rank with a 6-metric weighted score (projected area 40%, outer-boundary confidence 20%, moldability 15%, simplicity 10%, separation quality 10%, length 5%). Open chains are penalized 4× so they can never beat a closed loop. The top closed loop is the single primary parting line.
**Rationale**: Endpoint-only sampling collapsed curved rims (2 semicircular edges → zero-area "polygon") and let tiny feature loops win. Ordered tessellation + shoelace on the chained polygon is valid for non-convex rims and selects the true outer rim.

## 6. Core/Cavity Assignment by Reachability (2026-07-30)
**Context**: Normal-voting cannot decide vertical walls, and the "larger visible area = cavity" sign heuristic mislabeled the interiors of both Bosch parts.
**Decision**: Vertical walls are assigned by reachability raycasts (blocked toward the cavity → core-formed); through-holes go to the core (core-pin convention); the pull sign is chosen so the core sits on the side the part's internal features open toward.
**Rationale**: Matches the judges' cap example exactly ("even the internal surface … will be formed by the core"); validated on Part 1, Part 2, a GrabCAD cup holder, and synthetic ground-truth parts.

## 5b. Parting Line v4 — geometry-driven, not edge-driven (2026-08-17)
**Context**: v3 (§5 above) selected a loop with a 6-metric weighted score. Three things were wrong with it, all measured:
1. **Undercut pollution.** A trapped face still gets a mold half, so comparing halves emitted the entire outline of every undercut pocket as a parting candidate. On Part 3: **48 of 51 candidate edges** bordered an undercut face — 94% of the candidate set was two rib pockets. The correct rim won only by outscoring them.
2. **Degenerate scoring terms.** `projected_area` (40% weight) was normalised against the other candidates, so the winner always scored 1.0 on it and it carried no absolute signal. `outer_confidence` (20%) divided by a **bounding box**, capping any circular rim at π/4 = 0.785 however perfectly it matched the part.
3. **No answer for a non-axial pull.** When the pull crosses the part axis the split is a clamshell plane through the middle of the outer wall, where the B-rep has *no edge at all*. Every candidate loop then had projected area exactly 0.0, and the engine picked an internal groove edge and reported it at 0.71 confidence with no failure signal.

**Decision**: Rebuilt as `core/parting/` following the spec pipeline — classify regions → extract region boundaries → trace an edge graph → silhouette fallback → validate. Edges bordering an `UNDERCUT` region are classified as **shutoffs** and excluded. Loop selection is **lexicographic** (closed → no branches → separates both halves → true silhouette coverage → planar → shorter), never a weighted sum. `core/parting/silhouette.py` computes analytic horizon curves for cylinders, cones and planes, and runs **only when validation rejects the topological result**.

**Rationale**: The parting line must be an *output* of accessibility and region classification. Lexicographic ordering makes "a shorter line beats fewer undercuts" impossible by construction rather than by hoping weights are large enough. The silhouette pass is gated so it cannot regress parts that already work (Part 1 is untouched — 0 of its 311 faces have a mid-surface silhouette for its pull).

**Result**: The `oring_nozzle` clamshell case — Bosch's own review-call example — went from `xfail` to passing. Grooved cylinder: one closed 12-edge loop, area 1950 mm², confidence 0.81, valid. Nozzle: two closed loops spanning the part axis, 40 mm of it flagged as side-core shutoff, and validation still failing `no_undercuts_remaining` because the bore genuinely needs a side core.

## 5c. Confidence Never Hides a Failure (2026-08-17)
**Context**: v3 used one score as both ranking key and confidence, so an unmanufacturable result could report 0.71.
**Decision**: `ValidationResult` carries named pass/fail checks in three groups (topological / geometric / mold) plus the six quality metrics the spec names. Confidence is computed from the metrics and then **capped** by the tightest ceiling any failed check imposes (`_FAILURE_CEILINGS`), never averaged with them.
**Rationale**: Spec §12: "do not hide failure conditions behind a high score." A capped confidence always has a stated reason next to it.

## 7. Direction Ranking & Sweep Performance (2026-07-30)
**Context**: Bosch guidance: rank candidate directions by undercut AREA (not count). Full sweeps took ~30 s on the Phase 2 part — too slow for a live demo.
**Decision**: Area-first ranking with count as tie-break; branch-and-bound pruning (biggest faces first, abort an axis once its area exceeds the incumbent best); winner verdicts snapshotted and only trapped-suspect faces re-checked at full resolution. Pruned candidates are displayed as lower bounds (≥ N), never as exact values.
**Rationale**: 2× speedup (Part 2: 29 s → 14 s) with byte-identical verdicts, and honest reporting.

## 8. Direction Selection is Lexicographic (2026-08-17)
**Context**: Ranking was a bare `(undercut_area, undercut_count)` sort with the sweep's generation order as an implicit tie-break, and `evaluate_direction` mutated `FaceData` in place so nothing per-direction could be retained or explained.
**Decision**: `DirectionEvaluation` holds each axis's measurements; `direction_sort_key` orders them by **undercut existence → area → count → accessibility → parting complexity → source rank → balance → canonical vector**.
**Rationale**: Spec §5 states Priority 1 as "undercut existence/count"; Bosch (2026-07-28) states area evaluates better than count. Splitting Priority 1 into *existence* then *area* satisfies both — nothing with undercuts can beat something without them, and among the rest area leads. The final vector tie-break makes the answer independent of dict ordering and machine.

## 9. Two Proxies for Parting Complexity That Are Wrong (2026-08-17)
Recorded so they are not reintroduced; both were measured causing wrong answers.
- **Penalising NEUTRAL faces.** Rewards tilting the axis a few degrees off the part's real axis, because every side wall then picks up a small non-zero `n·d` and stops reading as neutral. On `flanged_boss` this let an axis **3.9° off Z** beat Z and put the flange and the boss in the same mold half. A clean two-plate mold is *full* of neutral faces — they are the surfaces the parting line runs along.
- **Area balance as the primary term.** A 45° pull splits most parts more evenly than their true axis, so balance alone chose a diagonal on `stepped_cylinder`, where the answer is plainly Z. Balance survives only as a late tie-break.
The measure actually used is the **count of connected same-half regions**: two regions means one loop, and every extra alternation means another.

## 10. Principal Axes Need a Loose Dedup, Not Just a Degeneracy Test (2026-08-17)
**Context**: Surface samples sit on a UV grid, which is not area-uniform — five samples round a cylinder land at 0.63, 1.88, 3.14, 4.40 and 5.65 rad. A perfectly axisymmetric part therefore yields a slightly non-axisymmetric covariance.
**Decision**: Reject eigenvectors whose eigenvalue is not clearly separated from its neighbours (a cube proposes none), **and** deduplicate principal axes against existing candidates at **10°** rather than the 2.6° used for exact axes.
**Rationale**: The degeneracy test alone does not help when the bias is in the data — on `flanged_boss` the top eigenvector was well-separated *and* 3.9° off Z. A statistical estimate deserves a dedup tolerance matching its real precision; beyond 10° the part genuinely does have an oblique axis and it is offered.

## 11. Part 3's 88 Undercuts Are Genuine — Verified, Not Assumed (2026-08-17)
**Context**: Part 3 reports 88 trapped faces and an invalid parting line. Two hypotheses were raised: that the ø36 @ z=4 loop was a sub-feature rather than the true silhouette (the Part 1 bug class), and that a clamshell split would release the slots.
**Decision**: Both were tested and both are answered NO. Recorded here so they are not re-opened without new evidence.
**Evidence**:
- **Silhouette** — global max radius is **18.000**; the only valid straight-pull split band is **z ∈ [1.00, 4.50]**; the loop sits at z=4.00 inside it. The 19.49 in `Bnd_Box` is an OCC control-polygon overestimate (18 × 1.083), not geometry.
- **Both-ways blocked** — faces **21** (z=15.5) and **23** (z=18.5) are blocked along **both** ±Z (6.01 mm and 2.99 mm). No mold half on any parting surface, planar or stepped, can form them.
- **Invariance** — six forced parting-line placements (ø36@z=4 → ø12@z=39) give a **byte-identical** 88-face / 1366.8 mm² undercut set.
- **Suppression** — filling the pockets drops undercut area to **5.2 mm²** with the parting line unmoved.
- **Clamshell** — swept at 5° over 36 plane-through-axis orientations. Best (t=35°) releases **all 88** but traps the through-bore (face 35, **1432.6 mm²**, alone larger than the entire axial set) plus splines (589.7 mm²): **2080.0 mm² vs 1366.8 mm²**.
**Rationale**: A clamshell's halves separate along the parting plane's *normal*, so a plane-through-axis split is a single lateral pull — already covered by the candidate search. The bore's axis lies in that plane and needs an axial side core. Axial Z− with two opposed sliders is correct.

## 12. Part 3's Second Parting Loop (2026-08-17)
**Context**: A second closed loop appears around the bore in the viewer; was it real or the outer loop seen end-on?
**Decision**: Real and distinct. **ø12 at z=1.00**, one full-circle edge (37.699 = 2π×6), between face **320** (bore lead-in chamfer, cavity) and face **35** (the through-bore, core) — the cavity/core-pin shutoff inside the bore.
**Rationale**: Loop tracing always found it; before v4 `api.py` sent only the primary loop unless `?debug=true`, so it never reached the viewer. All 3 of Part 3's parting candidates are consumed (two half-circles at r=18 z=4 → primary; one circle at r=6 z=1 → second); nothing is dropped. Above z=30 there are **280 faces, all core, 0 undercut, 0 parting candidates**, so no loop can exist at the splined end.

## 13. Clamshell for Part 3 Is Viable Once Side Cores Are Modelled (2026-08-18)
**Context**: Entry 11 rejected the clamshell on 2080.0 mm² vs axial's 1366.8 mm². That comparison counted the through-bore as trapped *by* the clamshell — but `docs/bosch-nozzle-review-transcript.md` (00:42.8, 01:28.5) models exactly this case as two main halves **plus a dedicated side core** for the internal passage. Under that accounting the bore should not count against the pull direction.
**Decision**: Re-measured. The earlier rejection was **too strong** and is corrected here.
**Evidence**:
- Bore delegated (faces 35/319/320, 1548.1 mm²): clamshell t=35° drops to **531.9 mm² vs axial 1366.8 mm² — 61% less**, with **0/16** slot faces trapped. All 36 orientations beat axial (range 531.9–727.9 mm²).
- Bore **and** splines delegated: **exactly 0 faces / 0.00 mm²** trapped at full sample resolution, under both a narrow (152 trapped faces) and a strict (whole z≥31 section, 280 faces) definition of the spline group.
- The optimum is a **plateau, 30°–50°**, not a knife-edge — plus an isolated zero at 130°. Worst orientation is 154.8 mm² at t=100°.
**Rationale**: A clamshell's halves separate along the parting plane's normal, so this is still a single lateral pull; what changed is the accounting, not the geometry. Entry 11's *geometric* findings all stand — the slots are genuinely trapped axially, and parting-line placement is still irrelevant to that.

## 14. Trapped Area Stops Discriminating Once Side Cores Are Allowed (2026-08-18)
**Context**: Entry 13's zero invites the reading that the clamshell is simply better.
**Decision**: Do **not** treat "zero trapped area under delegation" as a ranking signal. Applied symmetrically, it is vacuous.
**Evidence**: Delegating axial's slot regions — which is exactly what the engine already recommends, 2 opposed sliders on 1 axis — also gives **0 faces / 0.0 mm²**, while leaving **326 faces / 6195.3 mm² (82%)** on the two main halves. The clamshell reaches the same zero with **132 faces / 4706.7 mm² (62%)** on the halves. Both need **two delegated actions on one extra axis**.
**Rationale**: Any undercut set reaches zero if you delegate the faces that constitute it, so trapped area cannot rank configurations once side cores are in play. The metrics that do discriminate are surface retained by the main halves and the number of independent mold motions. Which is cheaper to build is a tooling-cost judgement, not a geometric one, and no measurement here settles it.

## 15. No Pipeline Change Follows From Entries 13–14 (2026-08-18)
**Decision**: The engine keeps ranking single pull directions with nothing delegated.
**Rationale**: It cannot know in advance which features a mold designer intends to put on side cores, and guessing would bake a tooling assumption into a geometry result. The honest default is to report what a straight pull traps and let `undercut_regions` name the mechanism — which it already does. A "delegate this feature group" input is a **new capability with its own API**, not a fix to the current one, and `docs/meeting-notes-2026-07-28.md:17` records side-core parting lines as *"NOT considered for evaluation"* this round.
