# ThermalIntel V2 Integrated Architecture & Operations Guide

**Document Version:** 2.0.0  
**Status:** **ACTIVE & INTEGRATED**  
**Integration Branch:** `v2`  
**Date:** October 2026  

---

## 1. Integrated V2 Architecture

ThermalIntel V2 elevates the platform from an ephemeral anomaly viewer to an authoritative, persistent operational intelligence platform with strict provenance tracking, lifecycle incident management, transition-driven operational alerting, and deterministic evaluation replay.

### Subsystem Composition

```
ThermalIntel V2
├── Ingestion & Raw Payload Store (Agent A)
│   ├── NASA FIRMS VIIRS Client with backoff & timeout handling
│   ├── Content-addressed raw payload store (SHA-256 hash tracking)
│   ├── Strict quarantine engine for corrupt / out-of-bounds coordinates
│   └── ProviderRun execution audit logging
├── Contextual Enrichment Engine (Agent B)
│   ├── OpenStreetMap Overpass infrastructure & settlement buffers
│   ├── Open-Meteo synoptic weather & fire weather indices (FWI)
│   ├── 30d/90d localized spatial recurrence tracking
│   └── Explicit missing-value representation (truthful provenance, zero fabrication)
├── Explainable Intelligence Engine (Agent C)
│   ├── Multi-class classification (Vegetation Fire, Industrial, Controlled, Persistent, Unknown)
│   ├── Regional 3-sigma statistical anomaly deviation
│   ├── Calibrated 0–100 risk scoring with frozen factor weights
│   └── Reproducible Assessment generation with input_hash audit trail
├── Persistent Incident Lifecycle Engine (Agent D)
│   ├── Spatiotemporal correlation & clustering into stable incident IDs (INC-YYYYMMDD-XXXX)
│   ├── Immutable append-only IncidentEvent timeline (CREATED, ESCALATED, CLOSED, etc.)
│   └── Relational IncidentObservation associative mapping
├── Persistent Operational Alerts Layer (Agent E)
│   ├── Transition-driven AlertV2 generation with deterministic dedupe keys
│   ├── Anti-flood pacing, cooldown windows, and chattering incident suppression
│   ├── Persistent SQLite lifecycle state (Active → Acknowledged → Resolved → Suppressed)
│   └── /api/alerts/health noise and reliability telemetry
├── Deterministic Replay & Evaluation Subsystem (Agent G)
│   ├── Virtual SimulatedClock separating simulation time from database write time
│   ├── Curated scenario packs (SCN-001 through SCN-004)
│   └── Evaluation harness benchmarking confusion matrices, risk stability, and alert rates
└── Operational Command Center Frontend (Agent F)
    ├── Next.js 14 / TypeScript / Tailwind CSS / Leaflet
    ├── Multi-modal data provider abstraction (LIVE, CACHE, DEMO, REPLAY, SYNTHETIC)
    ├── Incident-first tactical map, queue, detail dossier, and alert drawers
    └── Comprehensive Vitest component and smoke test suite
```

---

## 2. Canonical Data Pipeline

The unidirectional pipeline processes raw telemetry into actionable operations without circular dependencies:

```
ProviderRun (telemetry audit)
    ↓
RawPayload (content-addressed archive)
    ↓
Observation (normalized UTC remote-sensing data)
    ↓
EnrichmentSnapshot (OSM infrastructure, Open-Meteo weather, recurrence)
    ↓
Assessment (explainable classification, anomaly sigma, 0-100 risk)
    ↓
Incident ↔ IncidentObservation (persistent correlation with stable identity)
    ↓
IncidentEvent (append-only timeline transition)
    ↓
AlertV2 (deduplicated, rate-limited, priority-sorted operational advisory)
```

---

## 3. API Surface & Additions

All endpoints are hosted at `http://localhost:8000/api`:

### V1 Baseline Endpoints (Preserved)
- `GET /api/health` — System readiness, database status, active data mode.
- `GET /api/hotspots` — Paginated, filtered thermal anomaly hotspots.
- `GET /api/hotspots/{id}` — Comprehensive incident detail dossier.
- `GET /api/summary` — High-performance SQL aggregate KPIs (active, critical, averages).
- `GET /api/alerts` — Operational risk alerts with unread counts.
- `GET /api/sources` — Intelligence distribution and categorical breakdown.
- `POST /api/refresh` — Data synchronization trigger (protected by `ADMIN_API_KEY`).

### V2 Endpoint Additions
- `GET /api/alerts/health` — Operational alert health metrics (rate/hr, priority mix, chatter).
- `GET /api/alerts/{id}` — Retrieve canonical AlertV2 or legacy alert by ID.
- `POST /api/alerts/{id}/acknowledge` — Persistently acknowledge an active alert in SQLite.
- `GET /api/incidents` — Persistent incident catalog with status and min_risk filtering.
- `GET /api/incidents/{id}` — Persistent incident by permanent identifier.
- `GET /api/incidents/{id}/timeline` — Chronological lifecycle events timeline.
- `GET /api/incidents/{id}/observations` — Satellite observations linked to an incident.

---

## 4. Startup & Execution Commands

### Prerequisites
- Python 3.10+ (virtualenv at `.venv`)
- Node.js 18+ & npm

### Backend Server
```bash
# Activate virtual environment
source .venv/bin/activate

# Apply migrations
python3 -c "from services.api.database import init_db; init_db()"

# Start FastAPI dev server
uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Server
```bash
cd apps/web
npm run dev
# Accessible at http://localhost:3000
```

### Testing Suites
```bash
# Run entire backend test suite (364+ tests)
.venv/bin/pytest tests/ services/ scenarios/ evaluation/

# Run frontend test suite (37 tests)
cd apps/web && npm test

# Run frontend typecheck
cd apps/web && npx tsc --noEmit

# Run frontend production build
cd apps/web && npm run build
```

### Running Replay Evaluation
```bash
# Execute evaluation harness on golden scenario
python3 -c "
from scenarios.loader import load_scenario_from_file
from services.replay.player import ReplayPlayer
from evaluation.harness import EvaluationHarness
from pathlib import Path

scenario = load_scenario_from_file(Path('scenarios/data/scenario_1_industrial_spike.json'))
player = ReplayPlayer(scenario=scenario)
history = player.run_to_completion()
harness = EvaluationHarness()
report = harness.evaluate_replay(player.pipeline, scenario=scenario)
print(f'Evaluation Report Status: {report.metrics.keys()}')
"
```

---

## 5. Environment Variables & Security

| Variable | Default | Purpose |
|---|---|---|
| `FIRMS_MAP_KEY` | *(empty)* | NASA FIRMS 32-char hex key. If omitted, demo fallback is used. |
| `DATABASE_PATH` | `thermalintel.db` | Local SQLite database file path. |
| `DATA_MODE` | `demo` | Operational mode (`live` or `demo`). |
| `ADMIN_API_KEY` | *(empty)* | API key required for `POST /api/refresh`. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,...` | Restricted CORS origin whitelist. |

**Security Rules:**
- `.env` and `apps/web/.env.local` are git-ignored.
- No secrets are exposed to client-side bundles or HTTP responses.
- Provider errors sanitize credentials before logging.

---

## 6. Known Limitations & Deferred Scope
1. **Multi-GB Historical Archives:** Offline historical evaluation uses curated JSON scenario packs; live streaming of historical multi-GB FIRMS archives is deferred.
2. **Interactive UI Replay Scrubbing:** The frontend provides playback status indicators and data provider hooks; real-time canvas scrubbing controls remain in development.
3. **ML Training Pipelines:** Heuristic rule weights and isolation forest scoring are utilized; automated continuous online model retraining is out of scope for V2.
