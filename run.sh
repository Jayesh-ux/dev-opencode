#!/bin/bash
# Start the full AI Assistant stack
# Usage: ./run.sh

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend on port 8000..."
PYTHONPATH="$DIR/backend:$PYTHONPATH" \
  /data/data/com.termux/files/usr/bin/python3 -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 --log-level info &
BACKEND_PID=$!

echo "Starting frontend on port 3000..."
cd "$DIR/frontend" && npx next dev -H 127.0.0.1 -p 3000 &
FRONTEND_PID=$!

echo "Backend PID: $BACKEND_PID  Frontend PID: $FRONTEND_PID"
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
