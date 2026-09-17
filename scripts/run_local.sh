#!/usr/bin/env bash
# Convenience script: start backend and frontend for local development.
# Assumes .env has already been created (cp .env.example .env) and Python/Node
# dependencies are installed (see README "Local Setup").
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting backend on http://localhost:8000 ..."
(cd "$ROOT_DIR/backend" && uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
(cd "$ROOT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
wait
