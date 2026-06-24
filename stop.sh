#!/bin/bash

# Navigate to the directory where this script is located
cd "$(dirname "$0")"

if [ -f .backend.pid ]; then
  kill $(cat .backend.pid) 2>/dev/null
  rm .backend.pid
fi
# Fallback: force kill anything holding the backend port
lsof -t -i:8000 | xargs kill -9 2>/dev/null
echo "Backend stopped."

if [ -f .frontend.pid ]; then
  kill $(cat .frontend.pid) 2>/dev/null
  rm .frontend.pid
fi
# Fallback: force kill anything holding the frontend port (like the vite child process)
lsof -t -i:5173 | xargs kill -9 2>/dev/null
echo "Frontend stopped."
