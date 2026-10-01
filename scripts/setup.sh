#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "          ThermalIntel Environment Setup Script          "
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

# 1. Environment template check
if [ ! -f "${ROOT_DIR}/.env" ]; then
    echo "[*] Creating .env from .env.example..."
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
fi

# 2. Python Virtual Environment Setup
VENV_DIR="${ROOT_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    echo "[*] Creating Python virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

echo "[*] Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

echo "[*] Installing Python backend & intelligence dependencies..."
pip install --upgrade pip
pip install -r "${ROOT_DIR}/services/api/requirements.txt"
pip install -r "${ROOT_DIR}/services/intelligence/requirements.txt"

# 3. Seed SQLite Database
echo "[*] Initializing and seeding SQLite database..."
python "${ROOT_DIR}/scripts/seed_data.py" --force

# 4. Frontend Dependencies Setup
echo "[*] Installing Next.js frontend dependencies..."
cd "${ROOT_DIR}/apps/web"
npm install

echo "=========================================================="
echo "          ThermalIntel Setup Complete! Ready to Run!       "
echo "=========================================================="
echo ""
echo "To start full stack development:"
echo "  bash scripts/dev.sh"
echo ""
echo "Or run services individually:"
echo "  API (Port 8000):  uvicorn services.api.main:app --reload --port 8000"
echo "  Web (Port 3000):  cd apps/web && npm run dev"
echo "=========================================================="
