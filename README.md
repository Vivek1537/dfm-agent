<div align="center">
  <img src="https://img.icons8.com/color/144/000000/engineering.png" alt="Logo" width="100" height="100">

  <h1 align="center">dfm-agent</h1>
  <p align="center">
    <strong>An Automated Design-for-Manufacturability (DfM) Analysis Engine</strong>
    <br />
    <em>Bridging the gap between CAD design and injection molding realities</em>
  </p>

  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.10%20--%203.13-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React">
    <img src="https://img.shields.io/badge/Three.js-black?style=for-the-badge&logo=three.js&logoColor=white" alt="Three.js">
  </p>
</div>

<hr />

## About The Project

**dfm-agent** is a rapid manufacturing analysis engine. You give it a standard `.stp` / `.step` CAD file, and it instantly shows you — in an interactive 3D view in your browser — how easy or hard that part will be to injection-mold. No manual geometry inspection needed.

<br />

## Key Features

| Feature | Description |
| :--- | :--- |
| **Parse STEP & Evaluate Pull Direction** | Loads `.stp` files and finds the optimal mold pull direction. Candidates come from global axes, 45° diagonals, cylinder/cone feature axes, dominant planar normals and principal axes; selection is lexicographic, so a tidier parting line can never outrank fewer undercuts. |
| **Ray-Based Undercut Detection** | Every face is probed along **+D and −D** from a grid of surface samples. A face is trapped when the half that *forms* it cannot pull away from it — not merely when its normal points the wrong way. |
| **Surface Normal & Draft Angle Analysis** | Classifies faces into Core, Cavity, Undercut and Warning, reconciled against accessibility and propagated over topology so fillets inherit their neighbours. |
| **Propose Core–Cavity Split** | Derives the parting line from the boundary between mold regions, traces it into **ordered closed loops**, and falls back to silhouette curves when the pull crosses the part axis and no B-rep edge lies on the split. |
| **Honest Validation** | Topological, geometric and mold checks with a confidence that is **capped by failures, never averaged with them**. A part needing a slider says so and names the mechanism. |
| **Declared Tooling Plans** | A part may declare feature groups formed by side cores or lifters (`assets/<Part>.tooling.json`). Those faces leave the main halves' books — and the required actions are reported beside the undercut count, never instead of it. |
| **Clear 3D Visualization** | React + Three.js viewer: continuous parting loops, pull-direction arrow, colour-coded core/cavity/undercut faces, exploded view, plus Required Tooling and Alternative Configurations panels. |

<br />

## What You Need Before Starting

You only need **two things** installed. The start script does everything else for you.

| What | Which version | Where to get it |
| :--- | :--- | :--- |
| **Python** | 3.10, 3.11, 3.12 or 3.13 — **64-bit** | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js** | 22 LTS recommended (20.19 is the minimum) | [nodejs.org](https://nodejs.org/) |

**Important notes, please read:**

- **Python 3.14 or newer will NOT work.** The 3D engine (cadquery) only publishes prebuilt packages for Python 3.10–3.13. If you use a newer Python, the install fails with a long, confusing build error. When in doubt, install **Python 3.12**.
- **On Windows:** during the Python install, tick the checkbox **"Add python.exe to PATH"**.
- **Windows on ARM (some Surface laptops) is not supported** — the 3D engine has no ARM packages. Use a normal (x64) Windows PC, or run the project inside WSL.
- You do **not** need to create a virtual environment, run pip, or run npm yourself. The start script does all of that.

<br />

## How to Start the App

### On Windows

1. Download or clone this project.
2. Open the project folder.
3. **Double-click `app.bat`.** That is all.

A window opens and shows the progress. When it says both servers are running, open your browser at:

**http://localhost:5173**

### On macOS or Linux

Open a terminal in the project folder and run:

```bash
./app.sh
```

(If you get a "permission denied" message, run `chmod +x app.sh stop.sh` once, then try again.)

When it says both servers are running, open your browser at:

**http://localhost:5173**

### The first start is slow — this is normal

The very first run downloads all the packages the app needs (a few hundred MB, mostly the 3D geometry engine). This can take **several minutes** depending on your internet speed. Every start after that takes only a few seconds, because everything is already installed.

<br />

## What the Start Script Does For You

Every step below is automatic. It also checks itself at every step and prints a clear message if something is wrong:

1. **Finds the right Python** on your computer (3.10–3.13, 64-bit). If none is found, it tells you exactly which one to install.
2. **Creates a private virtual environment** (`.venv` folder) so nothing touches your system Python.
3. **Installs all Python packages** from `requirements.txt` (first run only).
4. **Checks the environment is healthy** — for example, it detects the broken state that happens if you moved or renamed the project folder, and tells you how to fix it.
5. **Checks port 8000 is free** — so you cannot accidentally start the app twice.
6. **Starts the backend** (FastAPI on port 8000) and **waits until it actually answers** before continuing. If it fails, it shows you the error from the log.
7. **Checks your Node.js version** is new enough, and tells you what to install if not.
8. **Installs all frontend packages** with npm (first run only).
9. **Starts the frontend** (Vite on port 5173) and prints the address to open.

<br />

## How to Stop the App

| System | Do this |
| :--- | :--- |
| **Windows** | Double-click **`stop.bat`** |
| **macOS / Linux** | Run **`./stop.sh`** |

This cleanly shuts down both servers, including all of their child processes. If the normal shutdown misses anything, it also force-frees ports 8000 and 5173.

<br />

## If Something Goes Wrong

| Message or problem | What it means | How to fix it |
| :--- | :--- | :--- |
| "No compatible Python found" | Python is missing, too old, too new (3.14+), or 32-bit | Install **64-bit Python 3.12** from python.org. On Windows, tick "Add python.exe to PATH" |
| "The virtual environment is broken" | This happens after moving or renaming the project folder | Delete the `.venv` folder and run the start script again |
| "Port 8000 is already in use" | The app (or something else) is already running | Run the stop script first, then start again |
| "Node.js … is too old" or "Node.js was not found" | Your Node.js is older than 20.19 or missing | Install **Node.js 22 LTS** from nodejs.org |
| "This machine is Windows on ARM64" | Your PC has an ARM chip — the 3D engine has no packages for it | Use an x64 PC, or run the project inside WSL |
| "Backend failed to start" | The Python server crashed on startup | The script prints the last lines of the log. Read them — they usually name the problem directly |
| A long red pip error mentioning "building wheel" | Wrong Python version slipped through (usually 3.14+) | Delete `.venv`, install Python 3.12, start again |
| The page loads but analyzing fails | Backend problem | Look at `backend.log` (and on Windows also `backend.err.log`) in the project folder |

**Where the logs are:** `backend.log` in the project folder, and `frontend.log` inside the `frontend` folder. On Windows there are also `backend.err.log` and `frontend.err.log`. When you ask for help, send these files.

<br />

## Inputs & Outputs

- **Input:** industry-standard CAD files (`.stp` / `.step`). Two reference parts are included in `assets/` (`Part1.stp`, `Part3.stp`).
- **Output:** an interactive browser-based 3D evaluation — manufacturability score, face classification, best pull direction (with manual override), parting loops, undercut regions with recommended tooling, and a validation report.

### How the parting line is derived

```text
STEP file
   └─ faces + surface samples          core/step_parser.py
      └─ candidate pull axes           core/pull_direction.py
         └─ ±D ray accessibility       core/accessibility.py
            └─ lexicographic choice    core/direction_evaluation.py
               └─ mold regions         core/face_classifier.py
                  └─ trapped features  core/undercut_regions.py
                     └─ PARTING LINE   core/parting/
```

The parting line comes **last** and depends on everything above it. That is the
design: it is an *output* of mold accessibility and region classification, not
an edge-selection heuristic. An edge becomes a candidate only because the faces
on either side of it belong to opposite mold halves.

Inside `core/parting/`:

| Module | Job |
| :--- | :--- |
| `boundary.py` | classify every edge by the regions either side; edges bordering an undercut are **shutoffs**, not parting line |
| `loops.py` | vertex-keyed edge graph → ordered closed loops, open chains, branch-point counting |
| `silhouette.py` | analytic horizon curves for cylinders, cones and planes, used only when the topological result fails validation |
| `validation.py` | topological / geometric / mold checks, quality metrics, ranking, confidence |
| `analyzer.py` | orchestration |

<br />

## Running the Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

103 tests, no network or GPU needed, about 230 seconds:

- `tests/test_synthetic.py` — parts built with cadquery, so the correct answer
  is known by construction (a cup's bore must belong to the core, a radial hole
  must be the only undercut under an axial pull, and so on).
- `tests/test_parting_line_topology.py` — the primary parting line is a single
  **closed, planar** loop, and the clamshell cases lie in a plane containing
  the part axis.
- `tests/test_pull_direction.py` — candidate generation, normalisation,
  deduplication, and the lexicographic direction ordering. Includes the rule
  that a shorter parting line can never buy off undercuts.
- `tests/test_parting_pipeline.py` — boundary classification, the edge graph,
  edge orientation, closed-loop and open-chain detection, and the acceptance
  cases: simple box, cylinder with a flange, and a re-entrant feature that must
  **not** be reported as solved.
- `tests/test_delegation.py` — declared tooling plans. The property under test
  is not "Part 3 reports zero" but that a zero reached by **delegation** can
  never be mistaken for one reached by **geometry**: delegation is opt-in only,
  a declared pull direction is verified rather than obeyed, and Part 1 (no side
  actions) stays distinguishable from Part 3 (two).

<br />

## Validation

Measured on the reference parts:

### Part 3 — three configurations

Part 3 is reported with a **declared tooling plan** (`assets/Part3.tooling.json`),
which states that a side core forms the through-bore and an axial insert forms
the splined end. The engine then finds the best split for what remains.

| | Pull | Undercuts on main halves | Extra tooling | Main-half surface | Motion axes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary — clamshell** | (0.819, 0.574, 0), 35° | **0** | bore side core + spline insert, both ±Z | 4706.7 mm² (62%) | 1 |
| **Alternative 1 — axial, as-is** | Z− | 88 faces / 1366.8 mm² | **none** | 6195.3 mm² (82%) | 0 |
| **Alternative 2 — axial + sliders** | Z− | **0** | 2 opposed sliders, 1 lateral axis | 6195.3 mm² (82%) | 1 |
| Other clamshell orientations | PN2 / XY+ / −AX2 | **0** | needs the same bore + spline delegation | ~72.5% | 1 |

Every figure is **measured, not asserted**. Whether a configuration needs the
declared plan is re-measured per direction (`_plan_area_needed_by`): the axial
pull draws the bore and splined end cleanly and so is charged nothing for them,
while every clamshell orientation genuinely cannot form them. Alternative 2 is
produced by the engine, running the same region grouper the primary path uses —
it reports 2 regions, `side-action slider` ×2, on axis (0.643, −0.766, 0).

**Read the whole row.** Both zeros are reached by *delegating*, and delegation
always terminates at zero — any undercut set vanishes if its faces are handed
to other tooling. What separates the configurations is the last two columns.

One asymmetry to keep in view: the primary is charged its **declared** groups
in full (2855.4 mm² — an insert forms the whole splined end, not only the
trapped subset), whereas alternatives are charged the **minimum** their
geometry forces. That is why neighbouring clamshell orientations show ~72.5%
against the primary's 62%. Both are honest; they answer different questions.

**Read the whole row, not the undercut column.** Both zeros are reached by
*delegating* features to side actions, and delegation always terminates at
zero — any undercut set vanishes if you hand its faces to other tooling. What
distinguishes the configurations is how much of the part the two main halves
still form, and how many independent motions the mold needs. Those columns are
the comparison; the undercut count on its own is not.

Alternative 1 is the only configuration that needs **no side actions at all**,
which is why it is kept in view even though its trapped area is the highest.

### Other reference parts

| Part | Pull | Undercuts | Primary parting line | Valid |
| :--- | :--- | :--- | :--- | :--- |
| Part 1 (Phase 1 cap) | Z+ | 0 — **and no side actions** | planar closed rim, 8 edges @ z=15 | ✓ 0.90 |
| O-ring nozzle (reviewer's sketch) | Y+ | 1 (the bore) | clamshell split through the part axis | ✗ 0.39 — side core forms the bore |
| Grooved cylinder | Y− | 0 | clamshell, 12 edges | ✓ 0.80 |

Part 1's zero and Part 3's zero are **not the same result**, and the tool never
presents them as such: Part 1 carries no `required_actions`, Part 3 carries two
totalling 2855.4 mm². A validation check named `side_actions_required` states
this in words next to the count.

Runtime on the reference parts (fast path, as the app uses it): Part 1 **1.5 s**,
Part 3 **17.1 s**. The exact direction ranking, served separately by
`POST /analyze/directions`, is 5.6 s and 33.5 s.

**Checked against a mould that was actually built.** A public GrabCAD
side-core mould ships its Cavity Plate and Core Plate alongside the parts they
produce. The plates meet at **z = 0**, and the engine independently places
PLASTIC BUSH's parting line at **z = 0.00** and flags 2 undercut regions — the
real mould uses a slide core. Those files are large third-party downloads and
are not tracked here.

**Part 3's 88 undercuts were independently verified as genuine** (see
`docs/untillnow.md`): the loop sits at the part's true silhouette maximum
(r=18.000; the valid split band is z ∈ [1.00, 4.50]), the trapped faces are two
circumferential slots at z ∈ [12.35, 21.65] with faces 21 and 23 blocked in
*both* ±Z, and six different forced parting-line placements produce a
byte-identical undercut set. A clamshell pull releases all 88 but traps the
through-bore (1432.6 mm²) and splines (589.7 mm²) instead, for 2080.0 mm²
against 1366.8 mm².

**Checked against a mould that was actually built.** A public GrabCAD
side-core mould ships its Cavity Plate and Core Plate alongside the parts they
produce. The plates meet at **z = 0**, and the engine independently places
PLASTIC BUSH's parting line at **z = 0.00** and flags 2 undercut regions — the
real mould uses a slide core. Coupler lands at z = 1.00, inside the plate
overlap. PLASTIC SLEEVE is the weakest case at z = 2.03, roughly 2 mm high.
Those files are large third-party downloads and are not tracked here.

<br />

## Project Architecture

```text
dfm-agent/
├── api.py           # FastAPI application entry point
├── core/            # DfM logic: pull direction, accessibility, classification
│   └── parting/     # region boundaries, loop tracing, silhouette, validation
├── frontend/        # React/Vite UI & Three.js viewer
├── tests/           # 103 tests: ground truth, pull direction, parting pipeline, delegation
├── app.sh           # One-click start for macOS / Linux
├── stop.sh          # One-click stop for macOS / Linux
├── app.bat          # One-click start for Windows (double-click this)
├── app.ps1          # The actual Windows start logic (run by app.bat)
├── stop.bat         # One-click stop for Windows (double-click this)
└── stop.ps1         # The actual Windows stop logic (run by stop.bat)
```

<hr />

<div align="center">
  <h3>Submitted for the DfM Agent Hackathon</h3>
  <p>
    <strong>Team Members:</strong> Vivek Boora, Ayush Pandey, Nitin, Afeera
  </p>
  <br />
  <em>Built for rapid prototyping and modern manufacturing.</em>
</div>
