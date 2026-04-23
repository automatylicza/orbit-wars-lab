#!/usr/bin/env bash
# Native dev launcher — spins up backend + viewer in one terminal.
# For Docker: `docker compose up` instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Python ---
if [ ! -d .venv ]; then
  echo "→ Creating .venv (python3.12 required)..."
  python3.12 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet -r requirements.txt

# --- Node / pnpm ---
if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm not found — install it first: npm install -g pnpm" >&2
  exit 1
fi
pnpm install --silent

# --- Run both processes ---
# Backend serves API on :8000; Vite runs on :6001 with proxy → :8000.
uvicorn orbit_wars_app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

pnpm --filter @orbit-wars-lab/viewer dev --port 6001 --strictPort &
VIEWER_PID=$!

echo ""
echo "Orbit Wars Lab running:"
echo "  viewer:  http://localhost:6001"
echo "  api:     http://localhost:8000/api/health"
echo ""
echo "Ctrl+C to stop both."

cleanup() { kill "$BACKEND_PID" "$VIEWER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
wait
