#!/bin/bash

# Navigate to the directory where this script is located
cd "$(dirname "$0")"

# --- BACKEND SETUP ---
# Check if the virtual environment exists, if not, create it and install dependencies
if [ ! -d ".venv" ]; then
    echo "📦 First time setup: Creating Python virtual environment..."
    python3 -m venv .venv
    echo "⏳ Installing backend requirements. This might take a minute..."
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "🟢 Starting FastAPI backend..."
nohup uvicorn api:app --reload > backend.log 2>&1 &
echo $! > .backend.pid

# --- FRONTEND SETUP ---
cd frontend
# Check if node_modules exists, if not, install dependencies
if [ ! -d "node_modules" ]; then
    echo "📦 First time setup: Installing frontend dependencies..."
    npm install
fi

echo "🟢 Starting Vite frontend..."
nohup npm run dev > frontend.log 2>&1 &
echo $! > ../.frontend.pid

echo ""
echo "🚀 Both servers are running in the background!"
echo "🌐 Backend is available at http://localhost:8000"
echo "🌐 Frontend is available at http://localhost:5173"
echo "🛑 To stop them, run: ./stop.sh"
