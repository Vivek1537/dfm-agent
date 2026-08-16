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
| **Parse STEP & Evaluate Pull Direction** | Loads `.stp` files and automatically calculates the mathematically optimal mold pull direction. |
| **Surface Normal & Draft Angle Analysis** | Classifies faces into Core, Cavity, Undercut, and Warning categories with draft angle evaluation against the resolved mold-pull direction. |
| **Propose Core–Cavity Split** | Generates highly accurate 3D parting line loops to define the core and cavity separation. |
| **Clear 3D Visualization** | A rich React + Three.js frontend to visualize analysis results directly in your browser. |

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

- **Input:** industry-standard CAD files (`.stp` / `.step`). A sample part is included in `assets/`.
- **Output:** an interactive browser-based 3D evaluation — manufacturability score, face classification, best pull direction (with manual override), and parting lines.

<br />

## Project Architecture

```text
dfm-agent/
├── api.py           # FastAPI application entry point
├── core/            # DfM logic (parting lines, surface classification)
├── frontend/        # React/Vite UI & Three.js viewer
├── tests/           # Backend unit tests
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
