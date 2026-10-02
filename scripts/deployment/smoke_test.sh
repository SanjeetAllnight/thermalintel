#!/usr/bin/env bash
# ==============================================================================
# ThermalIntel V2 Container Build & Smoke Test Script
# ==============================================================================
# Validates container reproducibility, environment initialization, health probes,
# and graceful process termination.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

echo "=========================================================="
echo " ThermalIntel V2 Container Deployment Smoke Test"
echo "=========================================================="

CONTAINER_NAME="thermalintel-smoke-test-$$"
BACKEND_TAG="thermalintel-backend:smoke-test"
FRONTEND_TAG="thermalintel-frontend:smoke-test"
PORT=8008

cleanup() {
    echo ""
    echo "[SMOKE-TEST] Cleaning up test resources..."
    if command -v docker &>/dev/null && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
        docker stop -t 10 "${CONTAINER_NAME}" 2>/dev/null || true
        docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Check if Docker daemon is accessible
if command -v docker &>/dev/null && docker info &>/dev/null; then
    echo "[1/4] Docker daemon detected. Building backend container image..."
    docker build -t "${BACKEND_TAG}" -f Dockerfile .

    echo "[2/4] Starting container in isolated demo mode on port ${PORT}..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        -p "${PORT}:8000" \
        -e DATA_MODE=demo \
        -e ENVIRONMENT=production \
        -e LOG_FORMAT=json \
        -e PORT=8000 \
        "${BACKEND_TAG}"

    echo "[3/4] Testing container health and endpoint responses..."
    sleep 4

    echo "Running native health check inside container..."
    docker exec "${CONTAINER_NAME}" python -m services.observability.health --type=readiness

    echo "Verifying HTTP GET http://localhost:${PORT}/api/health..."
    if command -v curl &>/dev/null; then
        curl -s -f "http://localhost:${PORT}/api/health" || {
            echo "Failed to query HTTP health endpoint!"
            docker logs "${CONTAINER_NAME}"
            exit 1
        }
    fi

    echo "[4/4] Verifying graceful container termination (SIGTERM)..."
    docker stop -t 15 "${CONTAINER_NAME}"
    EXIT_CODE=$(docker inspect "${CONTAINER_NAME}" --format='{{.State.ExitCode}}')
    echo "Container exited cleanly with exit code: ${EXIT_CODE}"

    if [ "${EXIT_CODE}" -ne 0 ]; then
        echo "Error: Container did not exit cleanly (code ${EXIT_CODE})"
        exit 1
    fi

    echo "=========================================================="
    echo " SUCCESS: Docker container smoke test passed!"
    echo "=========================================================="
else
    echo "[NOTICE] Docker daemon socket is not directly accessible in this shell environment."
    echo "[1/3] Validating Dockerfile instructions and build context..."
    test -f "Dockerfile"
    test -f "docker/Dockerfile.backend"
    test -f "docker/Dockerfile.frontend"
    test -f "docker-compose.yml"
    test -f ".dockerignore"

    echo "[2/3] Validating Python environment and health probe CLI..."
    PYTHON_BIN="${PYTHON_BIN:-python3}"
    if [ -x ".venv/bin/python" ]; then
        PYTHON_BIN=".venv/bin/python"
    elif [ -x "/home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel/.venv/bin/python" ]; then
        PYTHON_BIN="/home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel/.venv/bin/python"
    fi

    DATA_MODE=demo "${PYTHON_BIN}" -m services.observability.health --type=readiness
    DATA_MODE=demo "${PYTHON_BIN}" -m services.observability.health --type=liveness

    echo "[3/3] Validating structured logging and metrics output..."
    "${PYTHON_BIN}" -c "
from services.observability import get_operational_metrics, export_prometheus, configure_logging, get_logger
configure_logging(log_format='json')
logger = get_logger('smoke_test')
logger.info('Smoke test logger validation')
m = get_operational_metrics()
m.http_requests_total.inc(method='GET', status_code='200', endpoint='/api/health')
prom = export_prometheus()
assert 'http_requests_total' in prom
print('Metrics and structured logging verified successfully.')
"

    echo "=========================================================="
    echo " SUCCESS: Emulated container runtime validation passed!"
    echo "=========================================================="
fi
