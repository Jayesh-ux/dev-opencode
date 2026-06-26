#!/bin/bash
# Start the FastAPI backend server
# Usage: ./run.sh [port]
PORT=${1:-8000}
PYTHON=/data/data/com.termux/files/usr/bin/python3
DIR="$(cd "$(dirname "$0")" && pwd)"

export PYTHONPATH="$DIR:$PYTHONPATH"
export GEMINI_API_KEY="${GEMINI_API_KEY:-$(grep GEMINI_API_KEY "$DIR/.env" 2>/dev/null | cut -d= -f2-)}"
export GEMINI_MODEL_VERSION="${GEMINI_MODEL_VERSION:-$(grep GEMINI_MODEL_VERSION "$DIR/.env" 2>/dev/null | cut -d= -f2-)}"

exec "$PYTHON" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --log-level info \
  --timeout-keep-alive 30
