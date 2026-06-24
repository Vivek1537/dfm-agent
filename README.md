<div align="center">
  <img src="https://img.icons8.com/color/144/000000/engineering.png" alt="Logo" width="100" height="100">
  
  <h1 align="center">🛠️ dfm-agent</h1>
  <p align="center">
    <strong>An AI-driven Design for Manufacturability (DfM) Copilot</strong>
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

## 🌟 About The Project

**dfm-agent** is a rapid manufacturing analysis engine. By ingesting standard `.stp`/`.step` CAD files, it provides instant, interactive 3D feedback on manufacturability constraints, eliminating hours of manual geometry inspection.

> **Hackathon Ready**: We built this repository for a seamless, zero-configuration evaluation experience. 

<br />

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| 🎯 **Mold Direction** | Automatically calculates the mathematically optimal mold pull direction. |
| 🧩 **Surface Classification**| Intelligently tags 3D faces into Core, Cavity, Undercut, or Warning categories. |
| ✂️ **Parting Lines** | Generates highly accurate 3D parting line loops for injection molds. |
| 🌐 **Interactive 3D Viewer** | A rich React + Three.js frontend to visualize analysis results directly in your browser. |

<br />

## 🚀 Zero-Config Setup & Run

We've completely automated the setup process so you don't have to fiddle with dependencies. Our single startup script handles creating the virtual environment, fetching Python packages, and installing Node modules.

### 1️⃣ Clone the repository
```bash
git clone https://github.com/your-username/dfm-agent.git
cd dfm-agent
```

### 2️⃣ Run the Magic Script
```bash
./app.sh
```

**That's it! Here is what happens under the hood:**
- 📦 **First-Time Setup:** Auto-creates a `.venv` folder, installs `requirements.txt`, and installs `node_modules`.
- ⚙️ **Backend:** Starts the FastAPI server in the background at `http://localhost:8000`.
- 🎨 **Frontend:** Starts the Vite React app in the background at `http://localhost:5173`.

*Your terminal is immediately freed up. Simply open [http://localhost:5173](http://localhost:5173) in your browser!*

<br />

## 🛑 Stopping the App

To cleanly shut down the background processes, just run:
```bash
./stop.sh
```

<br />

## 📁 Project Architecture

```text
dfm-agent/
├── api.py           # 🚀 FastAPI application entry point
├── core/            # 🧠 DfM logic (parting lines, surface classification)
├── frontend/        # 🖥️ React/Vite UI & Three.js viewer
├── tests/           # 🧪 Backend unit tests
├── app.sh           # ▶️ Zero-config auto-startup script
└── stop.sh          # ⏹️ Safe teardown script
```

<hr />

<div align="center">
  <h3>🏆 Submitted for the DfM Agent Hackathon</h3>
  <p>
    <strong>Team Members:</strong> Vivek Boora, Ayush Pandey, Nitin
  </p>
  <br />
  <em>Built with ❤️ for rapid prototyping and modern manufacturing.</em>
</div>
