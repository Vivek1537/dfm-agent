#!/bin/bash

# Navigate to the directory where this script is located
cd "$(dirname "$0")"

if [ -f .backend.pid ]; then
  kill $(cat .backend.pid) 2>/dev/null
  rm .backend.pid
  echo "✅ Backend stopped."
else
  echo "Backend is not running."
fi

if [ -f .frontend.pid ]; then
  kill $(cat .frontend.pid) 2>/dev/null
  rm .frontend.pid
  echo "✅ Frontend stopped."
else
  echo "Frontend is not running."
fi
