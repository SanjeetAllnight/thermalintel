# ThermalIntel V2 Container Deployment & Operations Guide

## 1. Overview & Architecture

ThermalIntel V2 provides reproducible containerized packaging and local production-like orchestration across two decoupled services:

```
┌────────────────────────────────────────────────────────┐
│                   Docker Compose Stack                 │
│                                                        │
│  ┌───────────────────────┐   ┌───────────────────────┐ │
│  │ thermalintel-frontend │   │  thermalintel-backend │ │
│  │ (Next.js 14 / Alpine) │   │ (Python 3.11 / Debian)│ │
│  │ Port 3000             │   │ Port 8000             │ │
│  └───────────┬───────────┘   └───────────┬───────────┘ │
│              │                           │             │
│              │ /api rewrite              │             │
│              └───────────────────────────┘             │
│                                          │             │
│                                   ┌──────┴──────┐      │
│                                   │ Data Volume │      │
│                                   │ SQLite & GIS│      │
│                                   └─────────────┘      │
└────────────────────────────────────────────────────────┘
```

- **Backend Container (`Dockerfile` / `docker/Dockerfile.backend`)**:
  - Python 3.11-slim base image.
  - Runs as unprivileged system user (`thermalintel`, UID 10001).
  - Native Python readiness probe (`python -m services.observability.health --type=readiness`) avoiding external curl dependencies.
  - Standard Uvicorn execution with graceful shutdown timeout (`--timeout-graceful-shutdown 15`).
  - Persistent volume mount `/app/data` for SQLite database (`thermalintel.db`) and caches (`data/cache`).

- **Frontend Container (`docker/Dockerfile.frontend`)**:
  - Node 20 Alpine multi-stage build (deps → builder → runner).
  - Runs as unprivileged system user (`nextjs`, UID 10001).
  - Next.js rewrite rule maps `/api/*` requests internally to `http://backend:8000/api/*`.

---

## 2. Build & Run Instructions

### Prerequisites
- Docker Engine 24+ and Docker Compose v2 (or standalone docker-compose).
- 2GB+ available RAM.

### Quickstart (Single Command)
```bash
# 1. Copy environment template
cp .env.example .env

# 2. Build and launch services in detached mode
docker compose up --build -d

# 3. Stream combined structured logs
docker compose logs -f
```

The services will become available at:
- Frontend Command Center: `http://localhost:3000`
- Backend REST API: `http://localhost:8000/api`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Prometheus Metrics: `http://localhost:8000/metrics`
- Readiness Probe: `http://localhost:8000/health/ready`

### Standalone Backend Container Build
```bash
# Build the backend image
docker build -t thermalintel-backend:latest -f Dockerfile .

# Run with persistent volume and demo mode
docker run -d \
  --name thermalintel-backend \
  -p 8000:8000 \
  -e DATA_MODE=demo \
  -e ENVIRONMENT=production \
  -e LOG_FORMAT=json \
  -v thermalintel_data:/app/data \
  thermalintel-backend:latest
```

---

## 3. Environment Variables Reference

| Variable | Required/Optional | Default | Purpose |
|---|---|---|---|
| `DATA_MODE` | **REQUIRED** | `demo` | `demo` (100% offline sample data) or `live` (NASA FIRMS & live GIS APIs). |
| `DATABASE_PATH` | **REQUIRED** | `thermalintel.db` | Path to SQLite database file. In container, set to `/app/data/thermalintel.db`. |
| `CACHE_DIR` | **REQUIRED** | `data/cache` | Path for ephemeral GIS and weather cache JSON files. |
| `PORT` | **REQUIRED** | `8000` | Backend listening port. |
| `HOST` | **REQUIRED** | `0.0.0.0` | Backend bind host. |
| `ENVIRONMENT` | Optional | `development` | Runtime environment name (`development`, `staging`, `production`, `test`). |
| `LOG_FORMAT` | Optional | `text` (dev) / `json` (prod) | Output format: `json` (machine-readable single line) or `text` (colorized console). |
| `LOG_LEVEL` | Optional | `INFO` | Logger verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `SERVICE_NAME` | Optional | `thermalintel-backend` | Service tag for structured logs and telemetry. |
| `FIRMS_MAP_KEY` | Optional (Required for live) | *(empty)* | NASA FIRMS 32-character hex key. If omitted in live mode, falls back to demo data. |
| `ADMIN_API_KEY` | Optional | *(empty)* | Secret key required for mutation endpoints like `POST /api/refresh`. |
| `CORS_ALLOWED_ORIGINS` | Optional | `http://localhost:3000,...` | Comma-separated list of allowed CORS origins. |
| `BACKEND_INTERNAL_URL`| Optional | `http://backend:8000/api/:path*` | Internal URL used by frontend Next.js rewrite in Docker networks. |

---

## 4. State Persistence & Volumes

In containerized deployments, data persistence is maintained across container restarts via named volumes:

- Volume: `thermalintel_data` mounted at `/app/data` in the backend container.
  - `/app/data/thermalintel.db`: Authoritative SQLite database containing observations, incidents, events, and alerts.
  - `/app/data/cache/`: Overpass OSM and Open-Meteo response cache.
  - `/app/data/raw/`: Content-addressed raw payload archive (SHA-256).
  - `/app/data/quarantine/`: Corrupt or out-of-bounds telemetry records for forensic auditing.

To reset persistent state:
```bash
docker compose down -v
```

---

## 5. Health Checks & Diagnostic Probes

The backend exposes native health and readiness checks accessible via HTTP and CLI:

1. **Readiness Probe (`GET /health/ready` or CLI)**:
   - Validates that SQLite database is connected and initialized.
   - Validates that the storage volume is writable.
   - Validates configuration mode.
   - CLI execution:
     ```bash
     python -m services.observability.health --type=readiness
     ```

2. **Liveness Probe (`GET /health/live` or CLI)**:
   - Validates that the application process is responsive.
   - CLI execution:
     ```bash
     python -m services.observability.health --type=liveness
     ```

3. **Prometheus Operational Metrics (`GET /metrics`)**:
   - Exposes request counts, latency distributions, provider ingestion counters, quarantine metrics, and incident transitions.

---

## 6. CI/CD Quality Gates

The GitHub Actions workflow at `.github/workflows/ci.yml` enforces automated quality gates on all pushes and PRs:

1. **`backend-quality-and-tests`**:
   - Compiles Python bytecode.
   - Runs database migration and seeding verification.
   - Executes entire 364+ test suite (`pytest tests/ services/ scenarios/ evaluation/`).
   - Verifies native health probe CLI execution.
2. **`frontend-quality-and-build`**:
   - Runs `npm ci`.
   - Executes Vitest test suite (`npm test -- --run`).
   - Runs TypeScript strict typecheck (`npx tsc --noEmit`).
   - Generates production Next.js build bundle (`npm run build`).
3. **`container-build-and-smoke`**:
   - Builds backend and frontend Docker images using Buildx.
   - Executes isolated container smoke test with healthcheck validation and graceful SIGTERM verification.

---

## 7. Known Limitations & Integration Boundaries

1. **Cross-Phase API Integration**:
   - The Phase 4 observability subsystem provides clean ASGI middleware (`ObservabilityMiddleware`) and router factories (`create_observability_router()`).
   - Final route registration on `services.api.main:app` or router unification is reconciled during the parallel phase integration to prevent merge conflicts with Phase 3.
2. **Docker In Docker in Sandboxed Environments**:
   - In environments where the host Docker daemon socket `/var/run/docker.sock` is restricted to root or specific groups, `scripts/deployment/smoke_test.sh` automatically falls back to emulated container runtime validation, verifying build manifests, health CLI probes, and metrics export.
