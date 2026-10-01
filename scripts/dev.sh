#!/usr/bin/env bash
# Start both FastAPI backend and Next.js frontend concurrently for local development

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Activate virtual environment if present
if [ -d "${ROOT_DIR}/venv" ]; then
    source "${ROOT_DIR}/venv/bin/activate"
elif [ -d "${ROOT_DIR}/../venv" ]; then
    source "${ROOT_DIR}/../venv/bin/activate"
fi

echo "=========================================================="
echo "          ThermalIntel Concurrent Dev Server             "
echo "=========================================================="
echo "  Backend API:   http://localhost:8000 (Swagger: /docs)"
echo "  Frontend Web:  http://localhost:3000"
echo "=========================================================="

cleanup() {
    echo ""
    echo "[*] Shutting down ThermalIntel development servers..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 1. Start FastAPI Backend (Port 8000)
cd "${ROOT_DIR}"
echo "[*] Starting FastAPI Backend on port 8000..."
uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait briefly for backend to initialize
sleep 2

# 2. Start Next.js Frontend (Port 3000)
cd "${ROOT_DIR}/apps/web"
echo "[*] Starting Next.js Web on port 3000..."
npm run dev &
FRONTEND_PID=$!

wait
