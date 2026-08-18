#!/bin/bash

# Navigate to the directory where this script is located
cd "$(dirname "$0")"

# --- BACKEND SETUP ---
if [ ! -d ".venv" ]; then
    echo "First time setup: Finding compatible Python version (3.10 to 3.13)..."

    BEST_PYTHON=""
    for py in python3.12 python3.11 python3.10 python3.13 python3; do
        if command -v "$py" >/dev/null 2>&1; then
            version=$("$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            major=$(echo $version | cut -d. -f1)
            minor=$(echo $version | cut -d. -f2)
            if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ] && [ "$minor" -le 13 ]; then
                BEST_PYTHON="$py"
                break
            fi
        fi
    done

    if [ -z "$BEST_PYTHON" ]; then
        echo "ERROR: Could not find Python 3.10, 3.11, 3.12 or 3.13 installed on your system."
        echo "The 3D engine (cadquery) only ships prebuilt packages for those versions."
        echo "Please install Python 3.12 from https://www.python.org/downloads/ and try again."
        exit 1
    fi

    echo "Using $BEST_PYTHON to create virtual environment..."
    if ! "$BEST_PYTHON" -m venv .venv; then
        echo "ERROR: Failed to create the virtual environment."
        exit 1
    fi

    echo "Installing backend requirements. This might take a minute..."
    source .venv/bin/activate
    if ! pip install -r requirements.txt; then
        echo "ERROR: Failed to install Python dependencies. Please check the logs above."
        exit 1
    fi
else
    source .venv/bin/activate
fi

# Double check the venv actually works before starting. A venv that was created
# under a different path (e.g. the project folder was moved or renamed) still has
# all its files, but every script inside it points at an interpreter that no
# longer exists — so test that the interpreter runs and uvicorn imports.
if ! .venv/bin/python -c "import uvicorn" >/dev/null 2>&1; then
    echo "ERROR: The virtual environment is broken (its Python or uvicorn is unusable)."
    echo "This usually happens after moving or renaming the project folder."
    echo "Please run: rm -rf .venv && ./app.sh"
    exit 1
fi

# If something already listens on 8000, uvicorn would crash with "address in
# use" while the health check below happily answers from the OLD process -
# reporting success against a stale server. Refuse instead.
if lsof -t -i:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: Port 8000 is already in use - a backend is probably still running."
    echo "Run ./stop.sh first, then start again."
    exit 1
fi

echo "Starting FastAPI backend..."
# Invoke via 'python -m' rather than .venv/bin/uvicorn so the hardcoded shebang
# inside the console script can never break this.
nohup .venv/bin/python -m uvicorn api:app --reload > backend.log 2>&1 &
echo $! > .backend.pid

# Wait for the backend to actually come up; otherwise the frontend proxy just
# returns 500s and the real error stays buried in backend.log.
for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! curl -fsS http://127.0.0.1:8000/openapi.json >/dev/null 2>&1; then
    echo "ERROR: Backend failed to start. Last lines of backend.log:"
    tail -20 backend.log
    exit 1
fi

# --- FRONTEND SETUP ---
# Vite 5.4 itself only wants Node 18+, but camera-controls (via
# @react-three/drei) declares >=22 and the eslint toolchain wants >=20.19,
# so 20.19 is the honest floor.
if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: Node.js was not found. Install Node.js 22 LTS from https://nodejs.org/"
    echo "Stopping the backend that was just started..."
    ./stop.sh
    exit 1
fi
NODE_VERSION=$(node -v | sed 's/^v//')
node_major=$(echo "$NODE_VERSION" | cut -d. -f1)
node_minor=$(echo "$NODE_VERSION" | cut -d. -f2)
if [ "$node_major" -lt 20 ] || { [ "$node_major" -eq 20 ] && [ "$node_minor" -lt 19 ]; }; then
    echo "ERROR: Node.js $NODE_VERSION is too old for this project."
    echo "Node 20.19 or newer is required (22 LTS recommended): https://nodejs.org/"
    echo "Stopping the backend that was just started..."
    ./stop.sh
    exit 1
fi

cd frontend
if [ ! -d "node_modules" ]; then
    echo "First time setup: Installing frontend dependencies..."
    if ! npm install; then
        echo "ERROR: Failed to install frontend dependencies."
        exit 1
    fi
fi

echo "Starting Vite frontend..."
nohup npm run dev > frontend.log 2>&1 &
echo $! > ../.frontend.pid

echo ""
echo "Both servers are running in the background!"
echo "Backend is available at http://127.0.0.1:8000"
echo "Frontend is available at http://localhost:5173"
echo "To stop them, run: ./stop.sh"
