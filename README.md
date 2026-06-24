<div align="center">
  <img src="https://img.icons8.com/color/144/000000/engineering.png" alt="Logo" width="100" height="100">
  
  <h1 align="center">dfm-agent</h1>
  <p align="center">
    <strong>An Automated Design-for-Manufacturability (DfM) Analysis Engine</strong>
    <br />
    <em>Bridging the gap between CAD design and injection molding realities</em>
  </p>
  
  <p align="center">
    <img src="https://img.shields.io/badge/Python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React">
    <img src="https://img.shields.io/badge/Three.js-black?style=for-the-badge&logo=three.js&logoColor=white" alt="Three.js">
  </p>
</div>

<hr />

## About The Project

**dfm-agent** is a rapid manufacturing analysis engine. By ingesting standard `.stp`/`.step` CAD files, it provides instant, interactive 3D feedback on manufacturability constraints, eliminating hours of manual geometry inspection.

> **Hackathon Ready**: Designed for automotive injection-molded components — reduces DfM review cycles from 3–4 hours of manual expert inspection to 5–10 minutes of automated analysis. 

<div align="center">
  <em>Interactive 3D viewer featuring Core/Cavity outlines, Undercut detection, and Parting Lines.</em><br/>
  <strong>(Please add a screenshot of your app running here!)</strong>
</div>

<br />

## Key Features

| Feature | Description |
| :--- | :--- |
| **Parse STEP & Evaluate Pull Direction** | Loads `.stp` files and automatically calculates the mathematically optimal mold pull direction. |
| **Surface Normal & Draft Angle Analysis**| Classifies faces into Core, Cavity, Undercut, and Warning categories with draft angle evaluation against the resolved mold-pull direction. |
| **Propose Core–Cavity Split** | Generates highly accurate 3D parting line loops to define the core and cavity separation. |
| **Clear 3D Visualization** | A rich React + Three.js frontend to visualize analysis results directly in your browser. |

<br />

## Inputs & Outputs

- **Input:** Accepts industry-standard CAD design files (`.stp` / `.step`), perfectly handling the Two Design Files required by the brief.
- **Outputs:**
  - **Working Demo:** Full interactive browser-based 3D evaluation.
  - **Source Code:** Complete architecture, automatically deployable via shell script.
  - **Methodology Report:** Automated payload summarizing part manufacturability scoring and classifications.

<br />

## Zero-Config Setup & Run

The setup process has been entirely automated. A single startup script handles creating the virtual environment, fetching Python packages, and installing Node modules.

### 1. Clone the repository
```bash
git clone https://github.com/Vivek1537/dfm-agent.git
cd dfm-agent
```

### 2. Run the Initialization Script
```bash
./app.sh
```

**System Operations Overview:**
- **First-Time Setup:** Auto-creates a `.venv` directory, installs `requirements.txt`, and installs `node_modules`.
- **Backend:** Starts the FastAPI server in the background at `http://localhost:8000`.
- **Frontend:** Starts the Vite React app in the background at `http://localhost:5173`.

*Your terminal is immediately freed up. Navigate to [http://localhost:5173](http://localhost:5173) in your browser to access the interface.*

<br />

## Stopping the Application

To cleanly shut down the background processes, run:
```bash
./stop.sh
```

<br />

## Project Architecture

```text
dfm-agent/
├── api.py           # FastAPI application entry point
├── core/            # DfM logic (parting lines, surface classification)
├── frontend/        # React/Vite UI & Three.js viewer
├── tests/           # Backend unit tests
├── app.sh           # Zero-config auto-startup script
└── stop.sh          # Safe teardown script
```

<hr />

<div align="center">
  <h3>Submitted for the DfM Agent Hackathon</h3>
  <p>
    <strong>Team Members:</strong> Vivek Boora, Ayush Pandey, Nitin
  </p>
  <br />
  <em>Built for rapid prototyping and modern manufacturing.</em>
</div>
