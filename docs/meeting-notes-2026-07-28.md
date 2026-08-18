# Bosch Phase 2 Q&A Meeting — 28 July 2026

Source: `Recording 2026-07-28 195016.mp4` (44:47, Bosch screen-share + Q&A).
Full transcript: machine-transcribed; timestamps below are approximate.

---

## 1. TL;DR — What changed for us

| Topic | Decision from Bosch | Impact on our tool |
|---|---|---|
| Evaluation weightage | **All criteria weighted EQUAL** — no criterion has higher weightage | Don't over-invest in any single metric; cover all four solidly |
| Direction ranking metric | **Undercut AREA preferred over face count** ("area will be better to evaluate") | Rank candidates primarily by undercut area, count as tie-break |
| Candidate pull directions | ±X/Y/Z is standard ("90% of cases"); optionally 45° quadrant diagonals (e.g. 1,1,1) as rare edge case; **every-5° sweep NOT required** | Our 9-axis + geometry-axis sweep already exceeds the expectation |
| Parting line | **MUST be ONE primary continuous loop.** "When the loop is discontinuous it cannot form a surface — it is solid steel. Physically not possible." | **Highest-priority fix: we currently emit 7–8 loops → must merge/select into one closed primary loop** |
| Override mold direction | **IS evaluated** (was scored in Phase 1 too). But it's "just a UI" — dropdown / custom vector passed to backend, recompute. "Simple problem" | Already implemented (candidates panel + custom vector + reset) ✔ |
| Side core / lifter PL | **NOT considered for evaluation** — "nobody has even attempted it" | Deprioritize side-core PL generation; keep undercut region detection as bonus polish |
| Draft angle | Bosch does **NOT add draft at design phase**; shared parts have **no draft**; vendor adds it later from 2D drawing. "Drafting we are not considering" | Draft-angle analysis is not scored. Keep low-draft warnings as UI extra only |
| Wall thickness | Explicitly NOT part of the problem (exists in NX etc.) — shown only as an example of resolution/algorithm trade-offs | Out of scope |
| UI marks | UI/visualization has one equal point; **all teams already get max for UI**; marks deducted only if features can't be checked | UI is table stakes — make every feature demonstrable, don't add more chrome |
| LLM / "agent" | **Not required this phase.** "API integration and chat window… not currently requested." Computational geometry approach is fine; AI allowed but not judged | No chatbot needed; focus on geometry algorithms |
| Reference answer for Part 2 | **Will NOT be shared** ("that is the solution") | Validate on public parts instead (see §4) |
| Deadline | **Submit by 14 August 2026** (link from Pranit). Mid-review call week of **Aug 5–6** ("ensure you're on the right track"). **No extensions** | Lock scope now; be demo-ready before the Aug 5–6 call |

---

## 2. Problem statement for Phase 2 (restated by Bosch, ~02:00–03:20)

The part (our `assets/Part3.stp`) is "somewhat more complex" — the Phase 1 part
"didn't have any undercuts as such". The pipeline expected is unchanged:

1. Work out the **optimal molding direction** — based on number/area of undercuts
   per candidate direction, pick the best.
2. For that direction, **classify core, cavity, and undercut surfaces** separately.
3. **Identify the parting line where core and cavity faces meet** — one primary loop.

Explicit quote (~03:45): *"Coming up with beautiful interfaces has been easy…
working on this type of core algorithms is what we are looking at — to identify
the core, cavity and undercut surfaces."*

---

## 3. Detailed Q&A (with timestamps)

### Override direction & scoring criteria (our question, ~05:32–08:10)
- We raised that Phase 1 scored "override mold direction" even though the May
  briefing put it at Level 3. Bosch's answer: lifter/side-core was excluded from
  evaluation, but **override stays** — and it is deliberately easy: *"He can have
  a dropdown where they can select X or Y or some other custom value. That is
  just a UI and you have to take that value to your backend. That's the vector
  you have to input."*
- *"Finding out the optimal mold direction is the main challenging problem…
  calculating the undercut, developing an algorithm for that, is the more
  challenging and technical part. Once you identify the undercut, then you can
  override it."*

### Weightage (our question, ~08:50–09:13)
- Q: Is undercut detection / parting line / optimal direction weighted differently?
- A: **"Now we have kept it equal for all."**

### Count vs area ranking (our question, ~09:15–10:40)
- Q: Is optimal direction ranked by min undercut count, min area, or combined?
- A: Combined; count and area are "directly proportional", **but**: *"It would be
  better if you take area… if there is some cut/mark in a face, if you count it
  as one — area will be better to evaluate."*

### Face count of the model (~10:58–14:40)
- A team asked how many faces the model has (to verify parsing). Bosch: not
  relevant; extract it from the STEP yourself; *"the original CAD model number of
  surfaces doesn't matter"* for solving. Mesh resolution (if you triangulate) is
  your choice and **can be a user input**.

### Wall-thickness detour (~17:35–18:53)
- Showed NX wall-thickness analysis (sample-point spacing coarse→fine; ray vs
  rolling-ball methods) purely as an example: *"You have to focus more on such
  algorithms… not on the number of faces."* Wall thickness itself is not given
  as a problem "because it is there in most CAD software."

### Allowed pull directions (chat question, ~19:36–21:10)
- Q: Are pull directions always ±X/±Y/±Z, or angled/mixed?
- A: *"Usually it will be in X Y Z, in most cases."* You can additionally test
  quadrant diagonals *"1,1,1 and −1,1,1… a 45 degree"* for rare edge cases.
  *"Going for every 5 degrees — that is not required."*

### Reference parting line for the new part (chat question, ~21:29–23:40)
- Q: Can we get the parting line of the new STEP to verify our generator?
- A: **No — "that is the solution."** Mentoring possible "with reference to other
  parts". Suggested workflow: take a simple cap/cup from **GrabCAD**, verify
  core/cavity/PL there ("if it works for the earlier part, it will work for this
  also"), then run the Phase 2 part. A sample part link + a core/cavity
  classification image were posted in the meeting chat.

### Core/cavity rule of thumb (~23:43–24:17)
- For a simple cup: **concave side = cavity? NO — corrected: "concave will be
  cavity and convex will be core"** … (speaker corrected himself mid-sentence;
  final statement: *concave → cavity, convex → core* for the cup example as
  searched online; i.e. the half forming the outer visible surface is the
  cavity, the half forming the inner surface is the core).

### Draft angle (audience question, ~25:00–27:05)
- Q: Will the test STEP have 1–2° taper/draft added?
- A: **No.** *"In Bosch we don't provide draft angle during the design phase…
  the part will not have draft; the drawing will contain that information; the
  vendor does the drafting when developing the tool. For our solution, drafting
  we are not considering."*

### Timeline (~28:08–29:54)
- **Final submission: by 14 August 2026** ("maybe 14th… ahead of 15th").
- One more review call **week of 5–6 August** to check teams are on track.
- *"Unlike last time we would not have much time to extend the deadline."*
- Submission link comes from Pranit after the review meeting.

### Product-designer / mold-engineer workflow (audience question, ~29:59–34:45)
- The tool models the mold engineer's screening step. There's no hard "send it
  back" line — it's collaborative iteration; the tool should reduce (not
  eliminate) iterations between product design and molding.
- *"This is one step towards solving a bigger problem… there may be another five
  set of criteria — that will come later, that is not used for judging now."*
- **"Sometimes we do not need a very complex solution — think in a simple way,
  maybe we will get a better answer."**
- Winner opportunity: *"You may also get an opportunity to work on the real
  problem."*

### Is the "agent"/LLM part in scope? (our question, ~35:45–37:55)
- A: Not required. *"That plan is there in the future… LLM interaction also. But
  as of now that is not required."* They noticed teams over-invested in "API
  integration and chat window" — *"that is not currently requested of you."*
- All teams used computational geometry; AI-based solutions allowed, not judged
  differently.

### Parting-line loop topology (our question, ~38:13–39:09) ⭐
- Q: Are multiple disconnected loops acceptable, or one primary loop?
- A: **"One primary loop. That is the main parting line… when it is
  disconnected, in the physical sense it is not possible — it is solid steel;
  if the loop is discontinuous it cannot form a surface."**

### UI marks (audience question, ~39:46–41:40)
- UI/visualization carries one point like everything else; all teams got top
  UI marks in Phase 1; points are deducted **only if the UI prevents checking
  the features**. *"Everybody will be able to implement a beautiful UI."*

### Closing advice (~39:15, ~42:27–44:20)
- Study what a mold/undercut physically is, not just the code.
- Send questions **in advance** (WhatsApp group or direct numbers) so mentors
  can prepare; mentoring covers understanding, not the solution itself.
- *"The bottom line is: the more you clarify your questions, the closer you get
  to the solution."*

---

## 4. Action items for Team Stack (priority order)

1. **Single primary parting-line loop (P0 — new hard requirement).**
   Merge/select our 7–8 loops on Part3 into ONE closed continuous loop at the
   core/cavity boundary. Secondary loops (holes etc.) may exist internally but
   the deliverable is the main loop.
2. **Rank direction candidates by undercut AREA first** (count as tie-break) —
   matches the judges' stated metric. (Small change in `mold_direction.py` sort key.)
3. **Keep override exactly as built** (dropdown + custom vector) — it is scored
   and our implementation matches their description verbatim.
4. **Deprioritize side-core/lifter PL generation** — not evaluated this round.
   Showing detected undercut regions visually is enough as a differentiator.
5. **Drop/park anything LLM/chat-related**; no draft-angle scoring; no wall
   thickness.
6. **Validate on external GrabCAD parts** (simple cup/cap, the shared cup-holder
   model) to prove robustness before the Aug 5–6 review call.
7. **Be demo-complete before the week of Aug 5–6** (review call), final
   **submission 14 Aug 2026** — no extensions.
8. Send prepared questions to mentors ahead of the next call.

---

## 5. Evaluation criteria (as confirmed in this meeting)

Equal weight, "3–4 criteria" for this round:

1. Optimal mold direction (ranked by undercut area across ±X/±Y/±Z + optional diagonals)
2. Undercut surface identification (correct, for any chosen direction)
3. Core & cavity surface classification
4. Main parting line — **one primary continuous loop** where core and cavity meet
5. (+) GUI/visualization — equal single point, deducted only if features can't be verified
6. (+) Override mold direction — scored, but treated as simple UI + recompute

Not evaluated: side core / lifter PL, draft angle, wall thickness, LLM/agent features.
