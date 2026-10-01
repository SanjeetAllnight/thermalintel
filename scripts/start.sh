#!/usr/bin/env bash
# ThermalIntel — Single-command startup
# Usage: ./scripts/start.sh
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Backend ──────────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating Python virtualenv..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo "Starting ThermalIntel API on :8000..."
.venv/bin/uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# ── Frontend ─────────────────────────────────────────────────────────────────
cd apps/web
if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install --silent
fi

echo "Starting ThermalIntel UI on :3000..."
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ThermalIntel Command Center             ║"
echo "║  UI  → http://localhost:3000             ║"
echo "║  API → http://localhost:8000/docs        ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop all services."

wait $BACKEND_PID $FRONTEND_PID
