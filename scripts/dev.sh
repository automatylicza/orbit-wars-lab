#!/usr/bin/env bash
# Uruchamia backend FastAPI (:8000) + Vite dev (:5173) jednocześnie.
# Ctrl+C zabija oba procesy.
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Run 'bash scripts/setup.sh' first to create .venv"
    exit 1
fi

trap 'kill 0' SIGINT SIGTERM

source .venv/bin/activate
uvicorn orbit_wars_app.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

(cd viewer && pnpm dev) &
FRONTEND_PID=$!

echo ""
echo "================================"
echo " Backend : http://localhost:8000"
echo " Viewer  : http://localhost:5173"
echo " Ctrl+C  : stop both"
echo "================================"

wait $BACKEND_PID $FRONTEND_PID
