# LLM CONTEXT — Bosch DfM Agent (Team Stack) — Complete Project Knowledge Base

> **Purpose of this file**: Single-source context for an LLM with ZERO prior
> knowledge of this project. It contains the hackathon background, the domain
> primer, every evaluation input we received (with source references), the
> full data model, EVERY algorithm with its exact calculation, every constant
> and its value, every engineering decision with its rationale and the
> evidence that triggered it, the validation history with numbers, and the
> known limitations. Read this and you know everything the team knows.
> Last updated: 2026-07-30.

---

## 1. PROJECT BACKGROUND

### 1.1 What this project is
A **Design-for-Manufacturing (DfM) analyzer for injection molding**, built by
**Team Stack** for a hackathon run by **Bosch (RB-CoC Plastics, India / BGSW)**.
The tool ingests a 3D CAD model (STEP file) of a plastic part and computes:

1. The **optimal mold opening (pull) direction** — the direction that traps
   the least part surface.
2. **Undercut faces** — features that cannot be released from the mold.
3. **Core / cavity classification** — which mold half forms each face.
4. The **main parting line** — ONE closed loop where core and cavity steel meet.
5. A **manufacturability score** (0–100) and **low-draft warnings**.
6. A **manual override** mode: the user picks any pull direction and the whole
   analysis recomputes for it.

Everything is visualized in a web UI (3D viewer with color-coded faces,
exploded core/cavity view, parting line rendering, direction override panel).

### 1.2 Hackathon timeline & status
- **Phase 1** (May–July 2026): all teams analyzed `assets/Part1.stp` (a Bosch
  **packaging cap**, 311 faces). Team Stack placed **3rd of 4 shortlisted
  teams (score 6)** — see §3.1 for the exact scoresheet.
- **Phase 1 results call** (recording: `WhatsApp Video 2026-07-21 at
  7.51.19 PM.mp4`, 20:37 min — transcribed by us; key facts in §3.2).
- **Phase 2** (current): a more complex part `assets/Part3.stp` (internally
  named "Part2" in its STEP header, 414 faces, exported from Siemens NX 2412).
  Q&A meeting held 2026-07-28 (recording `Recording 2026-07-28 195016.mp4`,
  44:47 min — transcribed; full notes in `docs/meeting-notes-2026-07-28.md`,
  distilled in §3.3).
- **Deadline: submission by 14 August 2026** (hard, no extensions). Interim
  review call week of Aug 5–6. Final presentation at the BGSW office where
  **every team member must present and validate their individual
  contribution** (explicitly part of the evaluation).
- Winner of Phase 2/Level 2 wins the hackathon (per the official PPT
  evaluation matrix); winners may get to work on the real Bosch problem
  (internship-style, "Level 3").

### 1.3 Deliverables required (from the official Phase 1 PPT)
1. Working demo (GUI).
2. **Methodology report — algorithm + flowchart** (now written:
   `docs/technical-document.md`, with 4 Mermaid flowcharts).
3. Source code that is "easy to update".

---

## 2. DOMAIN PRIMER (injection molding, as the judges define it)

- A mold is (at minimum) two steel halves. The **cavity** forms the part's
  **external** (cosmetic) surfaces; the **core** forms the **internal**
  surfaces. The mold opens along the **pull/mold direction**.
- **Undercut** *(mentor's exact definition, Phase 1 results call)*: “any
  feature which cannot be released from the mold” for the chosen direction.
  Undercuts are direction-dependent: choosing a different parting line /
  direction can create or remove undercuts.
- **Parting line / parting curve** *(mentor's exact definition)*: “wherever
  core surfaces and cavity surfaces meet, that will become the parting
  curve.” It must be **one continuous closed loop** — from the 2026-07-28
  meeting: “when it is disconnected … in the physical sense it is not
  possible … it is solid steel; if the loop is discontinuous it cannot form
  a surface.”
- **Draft angle**: small taper added to walls so the part can eject. Bosch
  **does not add draft at the design stage** (stated 2026-07-28): the CAD we
  receive has 0° walls by design; the mold vendor adds draft later from the
  2D drawing. Therefore vertical walls are NOT undercuts and low draft is a
  warning, not a defect.
- **Side core / lifter**: extra moving steel that releases lateral features
  (e.g. a snap-fit clip or a lateral hole). Its parting line generation is a
  "Level 3" topic — **not evaluated this round** (confirmed 2026-07-28:
  “the lifter and that part we have not considered for the evaluation …
  nobody has even attempted it”).
- Rule-of-thumb the mentor gave for validation: for a simple cup, **concave
  (inner) surfaces → core, convex (outer) surfaces → cavity**.

---

## 3. EVALUATION INPUTS (what the judges told us, with sources)

### 3.1 Phase 1 scoresheet & mentor feedback
Source: `mentor_feedback_report.md` (in repo root) + the results-call
recording.

Phase 1 criteria (0/1/2 each): optimal mold direction detection; ability to
override mold direction; main parting line creation; core & cavity
extraction; side core & lifter PL generation; GUI/visualization quality.

Team Stack's Phase 1 outcome (total 6, 3rd place):
- Optimal mold direction: **0** — our undercut detection was wrong, so the
  direction ranking was wrong.
- Override direction: **0** — we had not implemented it.
- Main parting line: **2 (best in class)**.
- Core/cavity extraction: **2** — mentor: Stack was “somewhat closer to the
  identified classification of core and cavity surfaces … but there also we
  saw that they had wrongly marked undercut faces.”
- Side core/lifter: 0 (every team scored 0; excluded from evaluation).
- GUI: 2 (all qualified teams scored max — “teams … have done a very good
  job in terms of GUI and visualization”).

Mentor's summary of the field: “Most teams failed to identify the optimal
solution for the provided example (a packaging cap), **which would have
resulted in zero undercuts**.” ← This sentence is the single most important
calibration fact for our undercut detector: **the official answer for Part 1
is ZERO undercuts.**

### 3.2 Phase 1 results call (video, 20:37) — key verbatim facts
Source: our transcription of `WhatsApp Video 2026-07-21 at 7.51.19 PM.mp4`.

- The Phase 1 part is a **packaging cap**; the optimal solution (pull along
  Z, parting line at the bottom outer rim) has **no undercuts**: “Even the
  internal surface and everywhere, it will be formed by the core. And then it
  releases and there are no undercuts.” ← Source for our **internal
  surfaces → core** convention.
- If a *different* parting line is chosen, specific faces become undercuts,
  and the tool must then classify them as such (this is what override mode
  must demonstrate).
- Multiple valid parting lines can exist: “your solution can give one correct
  answer, then also it is a good solution.”
- Hand-drawn example: a nozzle with a lateral pin + O-ring groove → Y-axis
  mold direction, main parting plane splits the halves, a **side core** forms
  the pin; whichever way you pull, some feature is locked unless a side core
  is used.
- Phase 2 = same parameters (“no new parameters”), more complex part,
  “robustness has to be improved. Currently … none of the teams have solved
  that problem, so the benchmark has been lowered.”

### 3.3 Phase 2 Q&A meeting (2026-07-28, 44:47) — decisions that bind us
Source: `docs/meeting-notes-2026-07-28.md` (full timestamped notes from our
transcription of `Recording 2026-07-28 195016.mp4`).

| Topic | Bosch's answer | Consequence in our code |
|---|---|---|
| Weightage | “We have kept it equal for all” criteria | Cover all four criteria; don't over-optimize one |
| Ranking metric | “It would be better if you take area … if there is some cut in a face, if you count it as one — area will be better to evaluate” | Candidates ranked by **undercut area first**, count as tie-break |
| Pull directions | “Usually it will be in X Y Z … you can have for 1,1,1 … a 45 degree … going for every 5 degrees, that is not required” | 9-axis sweep (3 cartesian + 6 diagonals) + geometry-derived axes is MORE than required |
| Parting line topology | “One primary loop … it is solid steel … if the loop is discontinuous it cannot form a surface” | Loop chaining + closure detection; open chains penalized ×0.25 |
| Override | “That is just a UI and you have to take that value to your backend. That's the vector that you have to input … it is a simple problem” | Dropdown of ranked candidates + custom vector input + reset |
| Side core / lifter | Excluded from evaluation | Deprioritized (undercut regions still shown visually) |
| Draft | “For our solution, drafting we are not considering” (Bosch designs carry no draft) | Draft = warning only; never influences undercut verdicts |
| Wall thickness | Not part of the problem (exists in NX etc.) | Out of scope |
| LLM/agent/chat | “As of now that is not required … API integration and chat window … not currently requested” | No chatbot; computational geometry is the evaluated core |
| Reference answer for Part 3 | Refused — “that is the solution” | Validate on public parts: GrabCAD (mentor shared a cup-holder link + a core/cavity example image in chat) |
| # faces in model | Irrelevant to scoring; mesh resolution is our choice, “that could be also a user input” | We work on exact B-rep; sampling density is a constant we control |
| Philosophy | “Sometimes we do not need a very complex solution — think in a simple way, maybe we will get a better answer” | Prefer simple physical rules over ML/complex heuristics |

### 3.4 Official PPT evaluation matrix (by level)
- Level 1 (Part 1): optimal mold direction, main PL, GUI.
- **Level 2 (Part 2 = the current round): optimal mold direction, main PL,
  core+cavity extraction, GUI. “Solve Level 2 → Winner of the hackathon.”**
- Level 3 (post-hackathon internship): + override polish, side core/lifter PL.
- Note the tension: the Phase 1 SCORESHEET still awarded points for override,
  and the 2026-07-28 meeting confirmed override remains expected (it's easy).

---

## 4. REPOSITORY MAP & RUNTIME

```
dfm-agent/
├── api.py                     # FastAPI app: POST /analyze (file + optional direction)
├── app.sh / stop.sh           # start/stop backend (uvicorn :8000) + frontend (vite :5173)
├── requirements.txt           # fastapi, uvicorn, cadquery (brings OCP), numpy...
├── mentor_feedback_report.md  # Phase 1 feedback summary (source doc)
├── assets/
│   ├── Part1.stp              # Phase 1 packaging cap, 311 faces
│   ├── Part3.stp              # Phase 2 part ("Part2" in STEP header), 414 faces, NX 2412
│   └── cupshot_in_bus_v2.STEP # GrabCAD cup holder (mentor-suggested validation), 56 faces
├── core/
│   ├── models.py              # FaceData / DirectionCandidate / AnalysisResult + score
│   ├── step_parser.py         # STEP → FaceData list (+ multi-point surface sampling)
│   ├── undercut_detector.py   # UndercutRaycaster + per-sample trapped logic
│   ├── mold_direction.py      # axis sweep, area ranking, pruning, sign selection
│   ├── draft_angle.py         # worst-case draft per face
│   ├── face_classifier.py     # core/cavity/undercut assignment
│   ├── parting_line.py        # boundary edges → chained loops → primary loop
│   └── analyzer.py            # orchestrates the whole pipeline
├── scripts/analyze_cli.py     # headless regression harness (run this after ANY change)
├── frontend/src/App.jsx       # metrics sidebar, override panel, upload
├── frontend/src/ModelViewer.jsx # three.js scene: face meshes, exploded view, PL lines
└── docs/
    ├── technical-document.md      # METHODOLOGY REPORT (algorithms + 4 flowcharts) — deliverable
    ├── product-document.md        # product/feature description
    ├── decision-log.md            # architectural decision record
    ├── product-walkthrough.md     # demo script
    └── meeting-notes-2026-07-28.md # full Phase 2 Q&A notes (source doc)
```

Run: `./app.sh` (backend log `backend.log`, frontend log `frontend.log`).
Python venv: `.venv` (Python 3.12; OCP/OpenCASCADE via cadquery).
Regression: `.venv/bin/python scripts/analyze_cli.py assets/Part3.stp`
(supports `--direction x,y,z` for override testing).

---

## 5. DATA MODEL (`core/models.py`)

**FaceData** — one entry per topological face of the part:
- `face_id: int` — index in parse order (stable per file; used in tests).
- `face_shape` — the OCP `TopoDS_Face` (needed for raycasting/parting line).
- `surface_type: str` — "PLANE" | "CYLINDER" | "CONE" | "SPHERE" | "TORUS" |
  "BSPLINE" | ...
- `area: float` (mm²), `center: (x,y,z)` — via `GProp_GProps`.
- `normal: (x,y,z)` — outward normal at the UV midpoint (fallback only).
- `sample_points: List[(x,y,z)]`, `sample_normals: List[(x,y,z)]` — the
  multi-point surface samples (§6.1). ALL downstream verdicts use these.
- `axis: Optional[(x,y,z)]` — rotation axis if cylinder/cone (else None).
- `is_undercut: bool`, `trapped_fraction: float` — set per evaluated direction.
- `mold_half: "core"|"cavity"` — which half FORMS this face. Always set,
  even for undercuts (an undercut is still molded by one half).
- `low_draft: bool` — worst-case draft < 1° (orthogonal warning flag).
- `draft_angle: float` — worst-case draft in degrees.
- `classification: "core"|"cavity"|"undercut"` — render label
  (= "undercut" if is_undercut else mold_half).

**DirectionCandidate**: `direction (unit vector, signed)`, `label`
("Z-", "XY+", "-AX2(-0.64,0.77,0.00)", or "(1.00,0.00,0.00)" for custom
override), `undercut_count`, `undercut_area`, `pruned: bool` (True = counts
are lower bounds because evaluation aborted early; UI shows "≥N").

**AnalysisResult**: part_name, total_faces, best_mold_direction,
best_direction_label, direction_candidates (ranked), faces, core/cavity/
undercut/warning counts, manufacturability_score, raw_shape, is_override,
parting_line_edges.

---

## 6. THE PIPELINE — EVERY CALCULATION IN DETAIL

### 6.0 The v1 system (Phase 1 submission) — how it worked, every malfunction, and why v2

Understanding v1 matters: its failures are what the mentors scored us on, and
every v2 design choice is a direct answer to a specific v1 defect.

**6.0.1 v1 undercut detection — single-ray-from-center**

How it calculated: each face was represented by exactly ONE point (the UV
midpoint of its parametric surface) and ONE normal (evaluated at that
midpoint). The candidate escape side was chosen by the sign of
`normal · pull`. One ray was cast from the midpoint (offset along the
normal); if the intersector registered ANY hit farther than a minimum
distance, the face was declared an undercut. The intersector was rebuilt
from scratch for every direction tested (13 rebuilds per analysis), and the
ray length was a hardcoded 1000 mm.

Malfunctions (each observed, not hypothetical):
1. **Curved faces misrepresented** — a full cylinder's surface normals span
   360°, so its midpoint normal is an arbitrary pick. The `normal · pull`
   sign routed the ray to the wrong side, and one center ray said nothing
   about the rest of the surface. This is THE defect behind the mentor
   verdict "Stack … wrongly marked undercut faces" (Phase 1 results call):
   Part 1 reported 4 undercuts where the official answer is **zero**, and
   Part 3 reported 96 where careful analysis shows 88 genuine ones.
2. **Midpoint not guaranteed on the face** — for trimmed faces (a plate with
   a hole in the middle), the UV midpoint can fall INSIDE the hole, i.e. not
   on the material at all. v1 never classified the point (`TopAbs_IN` check
   was missing), so some faces were tested from a point that doesn't exist
   on the part.
3. **Any-hit = blocked** — grazing/tangential contacts counted as blockers.
   A ray sliding parallel to a vertical wall that clips an adjacent blend
   fillet registered a "hit" and trapped the face. (Concrete case, found
   post-v1 with the v2 diagnostics: Part 1 corner fillets were "blocked"
   by a 1.27 mm² bottom-lip round, hit transition `Out` = exiting, not a
   physical obstruction.)
4. **The vertical-wall "tiebreaker" hack** — v1 docs (old decision-log §3)
   record that near-perpendicular faces "always use a consistent tiebreaker
   direction" to fix mirror-asymmetry caused by floating-point sign noise
   (`+1e-7` vs `-1e-7` routing mirrored walls to opposite rays). The hack
   made mirrored walls consistent but physically WRONG: a vertical wall was
   tested in only ONE arbitrary direction, when the correct physics is that
   it is trapped only if BOTH pull directions are blocked (it slides out
   with either half otherwise). The v2 rule replaced the hack with physics.
5. **Contradictory thresholds** — the v1 technical doc said the minimum hit
   distance was 2.0 mm while the decision log said 0.01 mm (the code
   drifted from the docs). 2.0 mm masks real thin-wall blockers; 0.01 mm
   admits numerical noise. v2 settles on 0.1 mm PLUS the transition filter,
   with the rationale written down (§6.2).
6. **Waste** — rebuilding the intersector 13× and the fixed 1000 mm ray were
   pure overhead/fragility (a part larger than 1000 mm would silently miss
   blockers; a tiny part wastes range). v2 builds once and scales the ray to
   1.5× the bbox diagonal.

Why it looked plausible anyway: on mostly-planar faces the midpoint normal
is exact, so v1 got planes right; the errors concentrated on cylinders,
fillets, and splines — which is exactly where the judges looked.

**6.0.2 v1 direction search — 12 signed directions, count-first**

How it calculated: evaluated 12 SIGNED directions (±X, ±Y, ±Z, and 6
diagonals), each with the full (single-ray) undercut pass, then sorted by
`(undercut_count, undercut_area)` — count first.

Malfunctions:
1. **Half the work was redundant** — the trapped test is symmetric in ±d
   (measured: Z+ and Z− always return identical counts/areas), so 12
   directions did the work of 6 axes. v2 searches unique axes and picks the
   sign separately.
2. **Count-first ranking contradicts the judges** — 2026-07-28: "area will
   be better to evaluate" (a face split into several small patches must not
   outrank one large trapped face). v2 ranks by area, count as tie-break.
3. **No geometry awareness** — a turned part whose natural pull is a
   feature axis not among the 12 fixed directions was unfindable. v2 adds
   cylinder/cone axes (area-ranked, deduplicated) as candidates.
4. **Sign semantics broken** — v1 had no principled rule for which end of
   the winning axis is "toward the cavity". See 6.0.3 for the visible
   damage.

**6.0.3 v1 core/cavity classification — dot sign + a frontend swap hack**

How it calculated: `classification = "cavity" if normal·pull ≥ 0 else
"core"` using the single midpoint normal — and "warning" (low draft)
REPLACED the mold-half label entirely, so a low-draft face lost its
core/cavity identity. Vertical walls fell to the same sign test on
floating-point noise.

Malfunctions:
1. **Part 3 result: 242 core / 3 cavity** — physically meaningless for a
   cap (a mold whose cavity half touches 3 faces is not a mold). The root
   causes: single-normal voting + no vertical-wall logic + wrong sign
   convention.
2. **The frontend swap hack** — `ModelViewer.jsx` rendered backend
   `'cavity'` faces in the CORE visual group and vice versa (a hard-coded
   label swap), because at some point the 3D view "looked wrong" and was
   patched in the viewer instead of fixing the backend semantics. The hack
   masked the backend defect from visual inspection while the JSON (which
   the judges scripted against) still carried the wrong labels. Removed in
   v2 (DECISION #11); classification is now fixed at the source.
3. **"warning" as a classification** — draft status and mold-half are
   orthogonal facts; conflating them meant warning faces vanished from the
   core/cavity accounting. v2 keeps `mold_half` always set and `low_draft`
   as a separate boolean.

**6.0.4 v1 parting line — endpoint polygons and angular sort**

How it calculated: boundary edges between "cope" and "drag" faces were
grouped into connected components (same as v2), but each loop's projected
area — the dominant scoring metric at 40 % weight — was computed from edge
ENDPOINTS only, angular-sorted around their 2D centroid, then shoelace.

Malfunctions:
1. **Curved rims collapsed to zero area** — Part 3's true outer rim is 2
   long curved edges ⇒ 2 endpoints ⇒ "polygon" with area 0.0 ⇒ the real
   parting line ranked LAST and a 90.7 mm snap-leg lug loop at z≈21 was
   selected as primary. (Found 2026-07-29; fixed by tessellating along the
   curves and chaining, §6.7.)
2. **Angular sort is invalid for non-convex loops** — sorting vertices by
   angle around the centroid silently reorders concave outlines into a
   different (convex-ish) polygon, producing a wrong area for exactly the
   complex parts Phase 2 is about.
3. **No closure concept** — v1 happily returned open chains and reported
   "14 loops" (Part 1) / "19 loops" (Part 3) with no single-loop selection
   discipline. The judges' requirement (2026-07-28) is ONE closed primary
   loop ("solid steel … cannot form a surface" otherwise). v2 chains edges
   end-to-end, verifies closure, and gates open chains at ×0.25 score.
4. Per-loop metric passes rebuilt the edge→face map repeatedly (O(loops ×
   edges) waste) — tolerable at 311 faces, painful at 414+.

**6.0.5 v1 miscellany**

- **No override mode at all** — no API parameter, no UI. Scored 0/2 in
  Phase 1. (v2: §6.4.)
- **Draft** was computed from the single midpoint normal too — a curved
  face's worst-case draft was invisible. (v2: min over all samples.)
- **Score formula** had already evolved within v1 (area-only → area+count,
  old decision-log §4) — the only v1 calculation that survived into v2
  unchanged.

**6.0.6 Why the move to v2 was a rewrite, not a patch**

The Phase 1 scoresheet (0 on optimal direction, 0 on override, mentor:
"wrongly marked undercut faces") traced every lost point to the same root:
verdicts derived from ONE sample per face plus label conventions that were
never physically grounded. Multi-sampling changes the data model
(`FaceData` gains `sample_points/sample_normals/axis/mold_half/low_draft/
trapped_fraction`), which touches every downstream consumer — detector,
direction search, classifier, draft, parting line, API, and viewer. Patching
v1 piecemeal would have kept the old data model and its blind spots; the v2
rewrite (2026-07-27) replaced the representation first and rebuilt each
stage on top, then validated each stage against ground truth the judges
gave us (Part 1 = zero undercuts; internal surfaces = core; one closed PL
loop). The v1→v2 numeric evolution is tabulated in §8.1.



**The v2 pipeline (current) — order of operations**
(`core/analyzer.py::analyze_part`):
1. `parse_step` → faces + shape.
2. Build `UndercutRaycaster` (once).
3. If override direction given → normalize it, evaluate just that direction.
   Else → `find_best_mold_direction` (full sweep).
4. `compute_draft_angles` for the chosen direction.
5. `classify_faces` (needs the raycaster for vertical walls).
6. `find_parting_line` → primary loop edges.
7. Assemble `AnalysisResult` + score.

### 6.1 STEP parsing & surface sampling (`core/step_parser.py`)

- Read with `STEPControl_Reader`; explore `TopAbs_FACE`; area/centroid via
  `BRepGProp.SurfaceProperties_s`; surface type via `BRepAdaptor_Surface`.
- **Multi-point sampling** (`_sample_face`): sample a UV grid over the face's
  parametric bounds — grid size `_SAMPLE_GRID`: **3×3 for PLANE** (normal is
  constant; points still matter for ray origins), **5×5 for curved types**,
  hard cap `_MAX_SAMPLES = 15`. Each UV point is kept ONLY if
  `BRepClass_FaceClassifier` says `TopAbs_IN` — i.e., the point is on the
  trimmed face, not in a hole or outside the boundary. Normal at each kept
  point from `GeomLProp_SLProps`, flipped if the face orientation is
  `TopAbs_REVERSED`. If the coarse grid finds nothing (thin or heavily holed
  faces), a denser scan runs as fallback; final fallback = UV midpoint.
- **Axis extraction** (`_get_face_axis`): for CYLINDER/CONE surfaces store
  the rotation axis direction — these feed geometry-driven direction
  candidates (a turned part's natural pull is a feature axis).

WHY multi-sampling (DECISION #1, the Phase 1 root-cause fix): a curved
face's midpoint normal misrepresents it — a full cylinder's normals span
360°, so a single-normal dot product classifies it arbitrarily, and a single
center ray misses local blockage. This was why "Stack … wrongly marked
undercut faces" in Phase 1. Every verdict is now an area-weighted vote over
up to 15 real surface samples.

### 6.2 The raycaster (`core/undercut_detector.py::UndercutRaycaster`)

- All faces are added to one `TopoDS_Compound`; an
  `IntCurvesFace_ShapeIntersector` is loaded once with tolerance `1e-6`.
  Built **once per part** and reused for every direction test (v1 rebuilt it
  per direction — 13× waste).
- Ray length `_max_dist` = 1.5 × part bounding-box diagonal (min 10 mm).
  (v1 used a hardcoded 1000 mm.)

**`is_blocked(point, normal, direction) -> bool`** — the atomic escape test:
1. Offset the ray origin by `RAY_ORIGIN_OFFSET = 0.01 mm` along the surface
   normal (escape the face's own surface).
2. Cast an infinite line in `direction`; `Perform(line, 0, max_dist)`.
3. For each hit: ignore if `WParameter < MIN_HIT_DISTANCE = 0.1 mm`
   (self-intersection / numerical grazing; real molded walls are ≥ ~0.5 mm).
4. **Transition filter**: count the hit as a blocker ONLY if
   `Transition(i) == IntCurveSurface_In` — i.e., the ray is ENTERING
   material. `Out` and `Tangent` hits are ignored.

WHY the transition filter (DECISION #2, calibrated against the judges'
answer): rays hugging vertical walls tangentially grazed adjacent blend
fillets. Concrete evidence: on Part 1, four corner-fillet faces were flagged
as undercuts because their downward rays grazed a 1.27 mm² bottom-lip round
(face id 259) at z=0.02 with transition `Out`. The judges stated Part 1's
optimal solution has ZERO undercuts (§3.1/3.2). After filtering non-entering
hits: Part 1 = 0 undercuts (exact match), while all 88 genuine Part 3
undercuts remain. History of this constant: v1 used MIN_HIT=2.0 mm (masked
some real hits), an interim build used 0.01 mm (too noisy), final = 0.1 mm +
transition filter (physically justified).

**`sample_trapped(point, normal, pull, neg_pull) -> bool`** — per-sample rule:
- `d = normal · pull`; `PERP_EPS = 0.01` (≈ 0.6°).
- `d > +ε` (sample faces the cavity half): trapped ⇔ blocked along **+pull**.
- `d < −ε` (faces the core half): trapped ⇔ blocked along **−pull**.
- `|d| ≤ ε` (vertical wall): trapped ⇔ blocked along **BOTH** ±pull.
  (A vertical wall slides out with either half; it is only trapped if
  material blocks both ways — e.g., inside a lateral hole.)
- Note: this rule is **symmetric in pull ↔ −pull**. Undercuts depend only on
  the mold AXIS. (DECISION #3: search unique axes, halving the sweep; the
  ± sign is chosen later by a separate convention, §6.3.)

**`evaluate_direction(raycaster, faces, direction, max_samples_per_face=None,
abort_above_area=None) -> (count, area)`** — face-level verdicts:
- For each face: take its samples (optionally evenly subsampled to
  `max_samples_per_face`), count trapped ones.
- **Face is an undercut ⇔ trapped_samples ≥ 50 % of samples**
  (`UNDERCUT_FRACTION_THRESHOLD = 0.5`). `trapped_fraction` is stored.
- Early exit per face once the majority is decided either way (saves rays).
- **Branch-and-bound** (DECISION #12, performance): when `abort_above_area`
  is set (during the axis sweep), faces are evaluated biggest-first and the
  whole direction is abandoned the moment accumulated undercut area exceeds
  the incumbent best. Partial results are returned and the candidate is
  marked `pruned=True` (displayed as "≥N", never as an exact value — honest
  reporting was a deliberate choice).

**`refine_direction`**: after the sweep, only faces with
`trapped_fraction > 0` are re-evaluated at FULL sample resolution — a face
whose evenly-spread sweep samples all escaped will not become
majority-trapped with more samples (geometric plausibility argument).

### 6.3 Optimal mold direction (`core/mold_direction.py`)

**Candidate axes** (sign-less, per the ± symmetry):
- Fixed 9: Z, X, Y, XZ±, YZ±, XY± (diagonals at 1/√2). This exceeds the
  judges' stated requirement (±XYZ + optionally 45° diagonals; “every 5
  degrees … not required” — 2026-07-28).
- Plus **geometry axes**: cylinder/cone axes clustered by direction
  (duplicate if |dot| > `AXIS_DEDUP_DOT = 0.999`), ranked by cumulative face
  area, top 3, labeled `AX1(x,y,z)`… Deduplicated against the fixed set.

**Sweep**: for each axis, `evaluate_direction` with
`SWEEP_SAMPLES_PER_FACE = 5` and `abort_above_area = best_so_far`. When an
axis strictly improves the best area, a **snapshot** of all per-face verdicts
is taken (so the winner needs no full re-sweep later).

**Ranking** (DECISION #4, direct judge guidance 2026-07-28):
`sort(key = (undercut_area, undercut_count))` — area first, count as
tie-break. (“If you count it as one instead of count, area will be better to
evaluate.”) The same ordering is used in the API response and CLI output.

**Sign selection** (DECISION #5, the subtle one — 2026-07-30):
Undercut math is sign-symmetric but core-vs-cavity naming is NOT. The v2
heuristic “cavity = side with larger visible area” was WRONG on both Bosch
parts. The physically correct convention comes from the judges' cap example
(“even the internal surface … will be formed by the core”): **the core forms
internal surfaces and enters from the side those internal features open
toward; the pull (which points toward the cavity) is the opposite way.**

`_pick_sign_internal(faces, axis, raycaster)`:
1. Probe the dominant faces only — faces sorted by area until 90 % of total
   surface area is covered; ≤ `SIGN_SAMPLES_PER_FACE = 5` samples each
   (performance: the vote is area-weighted; the small-area tail can't flip it).
2. A sample is on an **internal feature** iff a ray along its own normal is
   blocked (`is_blocked(p, n, n)`) — i.e., the wall "sees" more part
   material across a void (bore walls, pocket walls).
3. For each internal sample: if blocked along +axis but free along −axis, the
   feature opens toward −axis (area-weight vote `core_neg_w`); vice versa for
   `core_pos_w`.
4. Core goes on the side with the larger opening weight; pull = other side.
   Tie or no internal features → fall back to the visible-area heuristic.

Evidence this is right (measured, 2026-07-30): Part 1 internal features
open −Z by 1133 mm² vs 15 mm² (→ core below, pull Z+); Part 3 opens +Z by
650 mm² vs 146 mm² (→ core above, pull Z−). With these signs, both parts
match the judges' cap topology: smooth outer shell = cavity, detailed side +
interior = core, parting line at the outer rim.

**Winner finalization**: restore the snapshot verdicts, then
`refine_direction` (full-res re-check of suspicious faces only). If the sign
flipped relative to the sweep's heuristic, the label is flipped via
`_flip_direction_label` ("Z+"↔"Z-", "XZ+"↔"-XZ+", "AX1(..)"↔"-AX1(..)").

### 6.4 Manual override (`core/analyzer.py`, `api.py`)

`POST /analyze` with form field `direction="x,y,z"` (e.g. "0,0,1"):
- Parse & normalize; invalid input (wrong arity, zero vector) → HTTP 422
  with `"direction must be 'x,y,z' with a non-zero vector"`.
- The multi-axis search is SKIPPED entirely; the given vector is evaluated at
  full resolution; a single `DirectionCandidate` labeled
  `"(x.xx,y.yy,z.zz)"` is produced; `is_override=True` in the response.
- Draft, classification, parting line, and score all recompute for that
  direction — so choosing a bad direction visibly creates undercuts, exactly
  the behavior the judges described (§3.2).
- Frontend (`App.jsx`): ranked candidate buttons (top 6, with "(auto-best)"
  marker and "≥" prefix on pruned counts), a custom "x,y,z" text input with
  Apply, and a "Reset to auto-detected direction" button when overridden.
  The candidate list from the auto run is preserved across override calls.

WHY this design (DECISION #6): the judges said override is “just a UI …
take that value to your backend. That's the vector that you have to input”
(2026-07-28, answering OUR question about why override was scored in Phase 1
despite being "Level 3"). We match their description literally.

### 6.5 Draft angle (`core/draft_angle.py`)

For the chosen pull direction `d`, per face:
- **Worst-case draft** = min over all samples of `asin(|n_i · d|)` in
  degrees (the shallowest spot on the face governs ejection).
- `low_draft = (worst < 1.0°)` → "warning" in the UI (yellow).
WHY warnings-not-undercuts (DECISION #7): Bosch designs intentionally carry
no draft (§3.3); flagging vertical walls as defects would be wrong. Draft
does NOT enter the undercut logic at all.

### 6.6 Core/cavity classification (`core/face_classifier.py`)

Every face gets `mold_half` by a 4-rule cascade:
1. **Normal voting**: area-weighted over samples; `n·d > +0.01` votes
   cavity, `n·d < −0.01` votes core. Majority wins.
2. **Vertical walls** (tie, all samples perpendicular): **reachability
   raycast** — from each sample, is the path blocked toward the cavity side
   (`is_blocked(p, n, pull)`) vs toward the core side (`neg_pull`)? If more
   samples are blocked toward the cavity, only the core can touch the wall →
   `core`; vice versa → `cavity`.
3. **Through-holes / internal channels** (reachable both ways, but the
   majority of samples face part material across a void — the same
   internality probe as §6.3): → `core` (core-pin convention; judges' cap:
   internal surfaces → core).
4. **External tie** (reachable both ways, not internal): → `cavity` (the
   cavity wraps the cosmetic exterior; the PL sits at the rim).
Fallback without a raycaster: centroid-side heuristic (which side of the
area-weighted centroid the face sits on along the pull axis).

WHY (DECISION #8, 2026-07-30): the centroid heuristic mislabeled Part 3's
main internal bore (face id 35, a 1433 mm² inward-facing cylinder) as
"cavity" — physically impossible steel. Reachability + internality are
direction-aware physical tests, not positional guesses. Validated: Part 3
bore → core; synthetic cup inner wall+floor → core, outer wall+bottom →
cavity; Part 1 pocket walls (ids 278/267/260/274) → core.

`classification = "undercut" if is_undercut else mold_half`. Note
`mold_half` stays set for undercuts too (an undercut face is still formed by
one half; it just needs a side action).

### 6.7 Parting line (`core/parting_line.py`) — 4-phase pipeline

**Phase 1 — boundary edges**: map every edge to its 2 adjacent faces
(`TopExp.MapShapesAndAncestors_s`). A face-side lookup assigns each face
"cope" (cavity) or "drag" (core) from `mold_half` (dot-product fallback).
Keep edges whose two adjacent faces are on OPPOSITE sides — the core↔cavity
boundary, exactly the judges' parting-curve definition.

**Phase 2 — loop grouping**: connected components over shared edge-endpoint
vertices (rounded to 6 decimals).

**Phase 3 — chaining + metrics per loop** (DECISION #9, 2026-07-29 — the
"single closed loop" requirement from §3.3):
- `_edge_polyline(edge, n)`: tessellate each edge into ordered points ALONG
  its curve via `BRepAdaptor_Curve` parameter stepping. **Adaptive density**:
  `pts_per_edge = max(8, 64 // n_edges)` — a rim made of 2 semicircular
  edges gets ~32 points each, so its polygon is faithful.
- `_chain_loop_points`: order the edges end-to-end by endpoint matching
  (keys rounded to 4 decimals), orienting each edge to continue the walk;
  start from a degree-1 endpoint if one exists (open chain), else anywhere.
  `is_closed = (all edges used exactly once) ∧ (≥4 points) ∧ (walk returns
  to start)`.
- **Projected area**: project the chained polygon onto the plane ⊥ pull
  (basis `u,v` from cross products), apply the **shoelace formula on the
  ORDERED polygon** — valid for non-convex rims.
  (The old code angular-sorted vertices around their centroid — invalid for
  non-convex shapes — and used only edge ENDPOINTS, which collapsed Part 3's
  true outer rim (2 long edges → 2 points → area 0.0) and let a tiny lug
  loop win primary. Concrete before/after: Part 3 primary was a 90.7 mm lug
  loop at z≈21; now the 113.1 mm square outer rim at z=1, area ≈1016 mm².)
- Six metrics per loop:
  - `projected_area` (normalized to the max across loops) — weight **0.40**
  - `outer_confidence` = projected_area / part bbox cross-section — **0.20**
  - `moldability` = 1 − (low-draft adjacent area / total adjacent area) — **0.15**
  - `simplicity` = 1 / (1 + log2(num_edges)) — **0.10**
  - `separation_quality` = min(cope_adj_area, drag_adj_area) / max(...) — **0.10**
  - `length_score` = 1 / (1 + 0.001·length) — **0.05**
- **Closure gate**: open chains get `score × OPEN_LOOP_FACTOR (0.25)` — they
  can never beat a closed loop (physically unmanufacturable per §3.3), but
  they stay ranked for debug display.

**Phase 4 — selection**: sort by score; top loop = PRIMARY (single parting
line, `is_selected=True`); if the top two scores are within
`AMBIGUITY_THRESHOLD = 5 %`, the result is flagged `is_ambiguous` and the UI
notes it. API returns the primary loop's tessellated segments always, all
candidates under `?debug=true`.

### 6.8 Manufacturability score (`core/models.py::compute_score`)

```
score = 100
      − (undercut_area / total_area) × 30
      − (undercut_count / total_faces) × 20
      − (warning_area / total_area) × 15
      − (warning_count / total_faces) × 5      → clamped to [0, 100]
```
WHY area AND count (DECISION #10): area-only made the score insensitive to
direction changes that scattered many small undercuts; one big undercut is
usually easier to fix than twenty small ones.

### 6.9 API response shape (`api.py`)

`POST /analyze` (multipart `file`, optional `direction`, optional
`?debug=true`) returns JSON:
- Top level: `score`, `best_direction_label`, `is_override`, `core_faces`,
  `cavity_faces`, `undercut_faces`, `warning_faces`, `total_faces`.
- `direction_candidates`: ranked `[{direction, label, undercut_count,
  undercut_area, pruned}]`.
- `geometry`: `faces` (per-face tessellation + `classification`, `mold_half`,
  `low_draft`, `draft_angle`), `best_direction`,
  `parting_lines` `[{loop_id, candidate_id, is_primary, is_closed, score,
  segments: [[pt×11]...]}]` (11 points per edge via cadquery `positionAt`),
  `parting_line_loops` (candidate count), `parting_line_is_ambiguous`.
- `parting_line_debug` (debug only): every candidate loop with all 6 metrics.

### 6.10 Frontend behavior (`frontend/src/`)

- `ModelViewer.jsx`: builds three.js meshes per face, colored by
  `classification` (core=blue-ish group, cavity=warm group, undercut=red,
  low-draft=yellow tint). Exploded "Both" view translates the cavity group
  along +pull and core along −pull (**the v1 code swapped backend labels in
  the frontend — a hack that hid the backend's wrong semantics; removed in
  v2** — DECISION #11). Parting line rendered as cyan tube segments.
- `App.jsx`: score/faces/direction/undercut/PL metric cards, face
  classification counts, Mold Direction override panel (§6.4), view presets.

---

## 7. DECISION LOG — CONSOLIDATED (what, why, evidence, source)

| # | Decision | Why / evidence | Source |
|---|---|---|---|
| 0 | React+FastAPI over Streamlit | Streamlit 3D too limited; separation of concerns | `docs/decision-log.md` §1 |
| 1 | Multi-point surface sampling (≤15 IN-classified UV samples/face) replaces single midpoint | Phase 1 root cause: curved-face normals misrepresented; "Stack wrongly marked undercut faces" | mentor report §3; results call |
| 2 | Ray hits count only when `IntCurveSurface_In` (entering material); MIN_HIT 0.1 mm; origin offset 0.01 mm | 4 false undercuts on Part 1 from tangential fillet grazes (face 259 evidence); judges: Part 1 optimal = ZERO undercuts | results-call transcript; measured |
| 3 | Search unique AXES not signed directions | Trapped test proven symmetric in ±d (identical counts measured for Z+/Z−) | measured on Part 1/3 |
| 4 | Rank candidates by undercut AREA, count tie-break | Judge: "area will be better to evaluate" | 2026-07-28 meeting ~09:15 |
| 5 | Pull sign from internal-feature opening direction (core = internal side) | "Even the internal surface … formed by the core"; area heuristic failed on BOTH Bosch parts; ray-measured 1133 vs 15 mm² (P1), 650 vs 146 mm² (P3) | results call; measured 2026-07-30 |
| 6 | Override = ranked dropdown + custom vector + full recompute, HTTP 422 on bad input | Judge: "that is just a UI … the vector that you have to input" | 2026-07-28 meeting ~06:40 |
| 7 | Draft <1° = warning only, never undercut | Bosch adds no design draft; vendor drafts later from 2D | 2026-07-28 meeting ~26:00 |
| 8 | Vertical walls by reachability raycast; through-holes → core; external tie → cavity | Part 3 bore (1433 mm²) was labeled cavity = impossible steel; cup ground truth | measured 2026-07-30; mentor's cup rule |
| 9 | PL loops chained along curves (adaptive tessellation), ordered shoelace, closure gate ×0.25 | "One primary loop … solid steel … cannot form a surface"; Part 3 rim area-0.0 bug (2 points from 2 edges) | 2026-07-28 meeting ~38:20; measured |
| 10 | Score penalizes area AND count | Direction changes were score-invisible with area-only | `docs/decision-log.md` §4 |
| 11 | Removed frontend core/cavity label swap hack | Frontend must not mask backend semantics; broke after backend fix | code review 2026-07-27 |
| 12 | Branch-and-bound sweep pruning + verdict snapshot + suspicious-only refinement; pruned counts shown as "≥N" | Live-demo latency: Part 3 29→14 s with identical results; honesty in UI | measured 2026-07-30 |
| 13 | Side core / lifter PL deprioritized | "Not considered for the evaluation … nobody attempted" | 2026-07-28 meeting ~06:20 |
| 14 | No LLM/chat features this phase | "As of now that is not required" | 2026-07-28 meeting ~36:00 |
| 15 | Validate on GrabCAD + synthetic ground-truth parts | Bosch refused a reference answer for Part 3 ("that is the solution"); mentor suggested GrabCAD cup | 2026-07-28 meeting ~21:30 |

---

## 8. VALIDATION HISTORY (numbers you can quote)

### 8.1 Result evolution on the two Bosch parts

| Build | Part 1 (311 faces) | Part 3 (414 faces) |
|---|---|---|
| v1 (Phase 1 submission) | Z−, 4 undercuts (FALSE), 24/209 core/cav, 14 PL loops, 5.0 s | Z−, 96 uc, **242 core / 3 cavity (broken)**, 19 loops, 10.2 s |
| v2 P0 rewrite (07-27): multi-sampling, axis sweep, mold_half voting | Z−, 4 uc, 62/245, 7 loops, 6.3 s | Z+, 88 uc, 22/304, 8 loops, 28.2 s |
| + transition filter (07-27) | Z−, **0 uc = judges' answer**, 64/247, score 88.0 | Z+, 88 uc (all genuine), 22/304 |
| + PL chaining + area ranking (07-29) | primary rim closed, area corrected | primary = TRUE outer rim (z=4, ~1016 mm²) vs old lug loop |
| + reachability + sign fix + pruning (07-30, current) | **Z+, 0 uc, 261 core / 50 cavity, 1 closed PL loop (32 edges), 2.1 s** | **Z−, 88 uc, 322 core / 4 cavity, closed square rim 36×36 @ z=1, 14.3 s** |

Part 3's 88 undercuts are GENUINE side-action features: two symmetric
snap-leg/lug clusters at z≈12–22 with normals ≈ ±(0.77, 0.64, 0) — exactly
the kind of feature the judges' nozzle example says needs a side core.

### 8.2 External validation (mentor-suggested method)

- **GrabCAD cup holder** (`cupshot_in_bus_v2.STEP`, from the link the mentor
  shared: grabcad.com/library/cup-holder-for-dodge-ram-van-1): Z−, score
  95.9, 8 undercuts = the two symmetric mounting snap-clips at y≈±46 (correct
  side-action features), 42 core / 6 cavity, primary PL = closed 101×100 mm
  outer rim at z≈70 (score 0.82 vs 0.42 runner-up). Verified end-to-end
  through the web UI including exploded view.
- **Synthetic cup** (cadquery: ø60 × 80 mm, 3 mm wall, open top): 0
  undercuts; inner wall + inner floor = core, outer wall + bottom = cavity
  (mentor's concave/convex rule); single closed rim loop; projected area
  within **0.16 %** of exact π r².
- **Synthetic cap with lateral hole** (ø50 × 30 mm, ø8 side hole): exactly
  the 2 hole-wall half-cylinders flagged as undercuts; rim loop correct.
- These are encoded in a **9-assertion regression suite** (inline script,
  see session notes) that gates every algorithm change: Part1 pull=Z+ /
  pockets=core / 0 uc; Part3 pull=Z− / bore=core / 88 uc; cupholder 8 uc;
  cup halves correct; sidehole 2 uc. Current status: **9/9 PASS**.

### 8.3 Performance profile (Part 3, WSL2 single core)
parse 1.1 s · raycaster build 0.0 s · winning axis eval ~4 s · losing axes
~0 s each (pruned) · sign refinement ~2 s (area-capped) · winner refinement
~4 s · parting line 0.05 s → **14.3 s total** (was 29 s before pruning).

---

## 9. KNOWN LIMITATIONS & OPEN WORK (be honest if asked)

1. **Side core / lifter PL generation** not implemented (deliberately — not
   evaluated this round). The 88 Part 3 undercut faces are detected and
   visualized but not clustered into side-action regions with pull vectors.
2. **Part 3 shows 6 PL candidate loops** (1 primary + 5 feature loops at the
   snap legs). The primary is correct; the extras are real core/cavity
   transitions around undercut regions — arguably features, but a cleaner
   story would merge/suppress loops around undercut faces.
3. **No silhouette splitting**: a parting line crossing the MIDDLE of a tall
   vertical face (not along existing edges) can't be found — we only use
   existing B-rep edges. Real mold tools split faces at the silhouette curve.
4. Performance is single-core Python; scaling path (per our roadmap):
   multiprocess the per-face rays, batch/BVH raycasting (e.g. embree on a
   fine mesh for the sweep, exact B-rep for the winner), cache by file hash.
5. Single-solid assumption: no multi-body assemblies, no STEP
   repair/validation pass for dirty exports.
6. Constants (50 % trapped threshold, 90 % sign-vote coverage, 1° draft
   warning, sampling grids) are fixed; production would expose them as user
   parameters (the judges explicitly blessed resolution-as-user-input).
7. The "agent" vision (LLM layer that explains verdicts / suggests fixes over
   the JSON API) is future scope — Bosch said LLM is NOT required this phase.

---

## 10. QUOTE BANK (verbatim, for presentations & tie-breaks)

- "Undercut is nothing but any feature which cannot be released from the
  mold." — Phase 1 results call
- "Once this classification of core surface and cavity surface, wherever
  these two surfaces meet, that will become … the parting curve." — same
- "This is the optimal solution wherein there are no undercuts. Even the
  internal surface and everywhere, it will be formed by the core." — same,
  about Part 1
- "Your solution can give one correct answer, then also it is a good
  solution." — same
- "Area will be better to evaluate." — 2026-07-28, on ranking directions
- "One primary loop … it is solid steel … if the loop is discontinuous it
  cannot form a surface." — 2026-07-28, on the parting line
- "That is just a UI and you have to take that value to your backend." —
  2026-07-28, on override
- "Nowadays using AI, coming up with beautiful interfaces has been easy …
  coming up with algorithms is what we are looking at." — 2026-07-28
- "Sometimes we do not need a very complex solution — think in a simple way,
  maybe we will get a better answer." — 2026-07-28

---

## 11. GLOSSARY (quick lookup)

| Term | Meaning here |
|---|---|
| Pull / mold direction | Unit vector the mold opens along; by our convention it points toward the CAVITY half |
| Core | Mold half forming internal surfaces (detailed side) |
| Cavity | Mold half forming external/cosmetic surfaces |
| Undercut | Face majority-trapped for the chosen axis (≥50 % samples blocked per §6.2) |
| Trapped fraction | Share of a face's surface samples that cannot escape |
| Parting line (PL) | The closed loop of edges where core faces meet cavity faces |
| Cope/drag | Internal PL-code synonyms for cavity/core sides |
| Draft | Wall taper for ejection; <1° ⇒ warning flag only |
| Side action / side core / lifter | Extra mold movement releasing lateral features; out of scope this round |
| Pruned candidate | Direction whose sweep was aborted early; its counts are lower bounds ("≥N") |
| Override | User-forced pull direction; full recompute, no search |
| B-rep | Boundary representation (exact CAD surfaces, not mesh) |
| OCP | Python bindings to OpenCASCADE used for all geometry |

---
*End of context file. Companion documents: `docs/technical-document.md`
(methodology + flowcharts), `docs/meeting-notes-2026-07-28.md` (full Q&A),
`mentor_feedback_report.md` (Phase 1 feedback), `docs/decision-log.md`
(ADR-style log), `docs/product-document.md` (product view).*
