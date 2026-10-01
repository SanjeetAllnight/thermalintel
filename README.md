# ThermalIntel

> **AI-Powered Satellite Thermal Anomaly Detection, Classification & Explainable Risk Intelligence**

ThermalIntel is an end-to-end geospatial intelligence system that detects, classifies, and assesses the risk of satellite thermal anomalies in real time by fusing NASA FIRMS/VIIRS satellite telemetry, OpenStreetMap geospatial context, Open-Meteo atmospheric fire weather, and historical detection persistence.

---

## Key Capabilities (18 Feature Matrix)
1. **NASA FIRMS/VIIRS Thermal Ingestion**: Automated ingestion from Suomi-NPP & NOAA-20 VIIRS sensors.
2. **Demo/Fallback Resilience**: Instant offline fallback to curated sample data when live APIs are unavailable or keys are omitted.
3. **Geospatial Enrichment**: Proximity analysis to critical infrastructure, human settlements, and conservation reserves via OpenStreetMap.
4. **Weather & Atmospheric Enrichment**: Hyperlocal temperature, relative humidity, wind speed, wind direction, and fire weather indices via Open-Meteo.
5. **Historical Anomaly Analysis**: Multi-month persistence and recurrence tracking to distinguish stationary industrial flaring from emergent wildfires.
6. **AI-Assisted Anomaly Detection**: Statistical sigma deviation and outlier detection flagging unprecedented thermal surges.
7. **Thermal-Source Classification**: Multi-class classification (Wildfire, Industrial, Agricultural, Prescribed Burn, Urban, Volcanic, Unknown).
8. **Composite Risk Scoring (0 - 100)**: Multi-attribute severity index combining radiometric heat, weather hazards, proximity, and recurrence.
9. **Explainable AI Attribution Factors**: Transparent attribution factors detailing *why* the model assigned the risk score.
10. **Interactive Geospatial Map**: Leaflet map surface with custom dark-mode styling and risk coloring.
11. **Hotspot Clustering**: Grouping of spatial anomaly clusters with aggregate intensity and radius indicators.
12. **Incident Feed**: Real-time list of detected anomalies with risk badges and FRP measurements.
13. **Incident Deep-Dive Dossier**: Comprehensive inspection drawer detailing GIS context, weather dials, timelines, and response advisories.
14. **Dynamic Filters**: Real-time filtering by risk category, thermal source, confidence, and minimum FRP.
15. **Operational Alerts**: Urgent triage notifications for critical-severity incidents threatening settlements or infrastructure.
16. **Dashboard Statistics**: Top-line operational KPIs (active anomalies, critical counts, peak/average FRP).
17. **Risk & Source Analytics**: Categorical source distribution and risk analytics powered by Recharts.
18. **Live vs. Demo Mode Indication**: Explicit visual indicator and manual telemetry synchronization trigger.

---

## System Architecture

```
thermalintel/
├── apps/
│   └── web/                   # Next.js 14 + TypeScript + Tailwind + Leaflet + Recharts (agent-ui)
├── services/
│   ├── api/                   # FastAPI backend service & SQLite persistence (agent-data)
│   │   ├── schemas/           # Frozen Pydantic domain models
│   │   └── routers/           # Frozen REST endpoints
│   └── intelligence/          # Scikit-learn classification & risk scoring engine (agent-intelligence)
├── data/
│   ├── sample/                # Deterministic fallback datasets for 100% demo reliability
│   └── cache/                 # Ephemeral query cache for OSM and weather telemetry
├── scripts/
│   ├── setup.sh               # One-click environment bootstrap
│   ├── dev.sh                 # Concurrent backend + frontend development server
│   └── seed_data.py           # Standalone SQLite database populator
├── docs/
│   ├── ARCHITECTURE.md        # Detailed system design & data flows
│   ├── API_CONTRACT.md        # Frozen HTTP API contract & JSON schemas
│   ├── MULTI_AGENT_PLAYBOOK.md# Multi-agent rules of engagement & worktree strategy
│   ├── AGENT_DATA_SPEC.md     # Implementation guide for agent-data
│   ├── AGENT_UI_SPEC.md       # Implementation guide for agent-ui
│   └── AGENT_INTELLIGENCE_SPEC.md # Implementation guide for agent-intelligence
├── .env.example               # Environment variables template
├── .gitignore
└── README.md
```

---

## Frozen API Contract

All subsystems communicate through this immutable REST contract hosted at `http://localhost:8000/api`:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | System health check, service readiness, and active data mode (`live` vs. `demo`) |
| `GET` | `/api/hotspots` | Paginated and filtered list of normalized thermal anomalies |
| `GET` | `/api/hotspots/{id}` | Complete incident dossier (geospatial, weather, historical, and explainable AI factors) |
| `GET` | `/api/summary` | Top-line dashboard KPIs, active alerts count, and dominant source types |
| `GET` | `/api/alerts` | Urgent operational alerts and emergency recommendations |
| `GET` | `/api/sources` | Categorical thermal source breakdown and risk profiles |
| `POST` | `/api/refresh` | Trigger NASA FIRMS sync or re-index fallback sample catalog |

---

## Multi-Agent Development Boundaries

To maximize parallel development velocity without merge conflicts:

| Agent | Isolated Worktree | Ownership Area | Restrictions |
|---|---|---|---|
| **`agent-data`** | `agent-data` | `services/api/`<br>`data/`<br>`scripts/` | **Must NOT** modify `apps/web/` or `services/intelligence/` |
| **`agent-ui`** | `agent-ui` | `apps/web/` | **Must NOT** modify `services/api/` or `services/intelligence/` |
| **`agent-intelligence`** | `agent-intelligence` | `services/intelligence/` | **Must NOT** modify `apps/web/` or `services/api/` |

---

## Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ & npm

### 2. One-Click Bootstrap
```bash
# Clone and enter directory:
cd /home/sanjeet/.gemini/antigravity-ide/scratch/thermalintel

# Run automated setup:
bash scripts/setup.sh
```

### 3. Start Development Servers
```bash
# Run both FastAPI (Port 8000) and Next.js (Port 3000) concurrently:
bash scripts/dev.sh
```

- **Frontend Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Specification**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## License
MIT
