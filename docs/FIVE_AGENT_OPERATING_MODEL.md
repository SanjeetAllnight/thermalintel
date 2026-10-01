# Five-Agent Parallel Operating Model & Governance

## 1. Operating Model Overview
ThermalIntel operates under a decentralized, parallel agentic architecture designed for 100% boundary isolation. The primary repository acts as the **Integration & Orchestration Workspace**. Five autonomous development agents execute in parallel inside dedicated git worktrees, each bound to an isolated branch with strict non-overlapping file ownership.

```
                                  [INTEGRATION WORKSPACE]
                              (thermalintel - branch: main)
                                            │
        ┌───────────────────┬───────────────┼───────────────┬───────────────────┐
        ▼                   ▼               ▼               ▼                   ▼
  [AGENT 1: DATA]    [AGENT 2: GEO]   [AGENT 3: ML]   [AGENT 4: INCIDENT]  [AGENT 5: UI]
   phase-1-data     phase-2-enrich   phase-3-intel   phase-4-incidents     phase-5-ui
   ../agent1-data   ../agent2-enrich ../agent3-intel ../agent4-incidents   ../agent5-ui
```

---

## 2. Worktree & Ownership Matrix

| Phase & Agent | Branch | Worktree Path | Owned Directories / Files | Forbidden Zones |
|---|---|---|---|---|
| **Phase 1: Data Engine** | `phase-1-data` | `../thermalintel-agent1-data` | `services/api/ingestion/`<br>`services/api/repositories/`<br>`services/api/data/`<br>`data/sample/`<br>`data/cache/`<br>`scripts/data/` | `apps/web/`<br>`services/intelligence/`<br>`services/api/schemas/` |
| **Phase 2: Enrichment** | `phase-2-enrichment` | `../thermalintel-agent2-enrichment` | `services/api/enrichment/`<br>`services/api/geospatial/`<br>`services/api/weather/`<br>`services/api/history/` | `apps/web/`<br>`services/intelligence/`<br>`services/api/ingestion/` |
| **Phase 3: Intelligence** | `phase-3-intelligence` | `../thermalintel-agent3-intelligence` | `services/intelligence/` | `apps/web/`<br>`services/api/routers/`<br>`services/api/schemas/` |
| **Phase 4: Incidents & Alerts** | `phase-4-incidents` | `../thermalintel-agent4-incidents` | `services/api/incidents/`<br>`services/api/alerts/`<br>`services/api/summary/` | `apps/web/`<br>`services/intelligence/`<br>`services/api/routers/` |
| **Phase 5: Command Center UI** | `phase-5-ui` | `../thermalintel-agent5-ui` | `apps/web/` | `services/api/**`<br>`services/intelligence/**`<br>`data/**` |

---

## 3. Strict Development Rules

1. **No Out-of-Bounds Edits**: No agent may create, edit, or delete files outside their assigned directories.
2. **Frozen API & Schema Contracts**: The API endpoints (`GET /api/health`, `GET /api/hotspots`, `GET /api/hotspots/{id}`, `GET /api/summary`, `GET /api/alerts`, `GET /api/sources`, `POST /api/refresh`) and schemas in `services/api/schemas/` and `apps/web/src/types/api.ts` are strictly locked.
3. **Standalone Modules Over Shared File Edits**: To eliminate merge conflicts, agents must implement logic in standalone services/modules in their own directories rather than modifying shared router or main files. Final wiring is performed in the integration workspace.
4. **Preserve Phase 0 Functionality**: Never delete baseline functionality or working mock fallbacks.
5. **No Docker / No Auth**: All code must run natively in Python 3.10+ virtual environments and Node 18+ environments without container or authentication requirements.
6. **Agent Delivery Protocol**: When an agent completes work, they must:
   - Commit all work cleanly to their assigned phase branch.
   - Run verification commands (unit/smoke tests, type checks).
   - Report changed files and test outputs back to the integration lead.

---

## 4. Phase Instructions & Deliverables

### Phase 1 — Data Engine (`phase-1-data`)
- **NASA FIRMS/VIIRS Ingestion**: Live ingestion from Suomi-NPP & NOAA-20 VIIRS NRT API.
- **Fallback Dataset**: Resilient fallback to `data/sample/` when API keys are absent or network is degraded.
- **Normalization**: Transform raw satellite CSV records to `Hotspot` models.
- **Caching**: Local ephemeral caching of raw responses in `data/cache/`.
- **Hotspot Retrieval & Refresh**: Repository querying and sync trigger handling.

### Phase 2 — Geo/Environment Enrichment (`phase-2-enrichment`)
- **OpenStreetMap / Overpass Client**: Query nearby critical infrastructure (power lines, substations, highways) and protected natural reserves.
- **Industrial Proximity**: Spatial proximity computation to industrial complexes and refineries.
- **Weather Enrichment**: Hyperlocal temperature, relative humidity, wind speed/direction from Open-Meteo.
- **Historical Recurrence**: Query 30-day and 90-day persistence to calculate recurrence frequency.
- **Enrichment Caching**: Cache GIS and weather API responses to prevent rate-limiting.

### Phase 3 — Intelligence Engine (`phase-3-intelligence`)
- **Thermal-Source Classification**: Calibrated classifier distinguishing:
  - `VEGETATION_FIRE`
  - `POTENTIAL_INDUSTRIAL_FIRE`
  - `CONTROLLED_HEAT_SOURCE`
  - `PERSISTENT_THERMAL_SOURCE`
  - `UNKNOWN`
- **Anomaly Detection**: Statistical deviation / IsolationForest flagging unprecedented thermal radiance surges.
- **Composite Risk Score (0 - 100)**: Multi-attribute formula with `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` levels.
- **Confidence & Explainability**: Feature importance and explainable `RiskFactor` objects with human-readable rationales.

### Phase 4 — Incident + Alert Engine (`phase-4-incidents`)
- **Incident Aggregation**: Combine normalized hotspots, GIS context, weather telemetry, and intelligence evaluation into unified incident models.
- **Incident Detail Generation**: Deep-dive dossier synthesis (`IncidentDetail`).
- **Alert Generation & Prioritization**: Threshold-based alert generation for critical hotspots near settlements/infrastructure with deduplication.
- **Dashboard Summary Calculations**: Top-level KPI counts, average/max FRP, active alerts tally.
- **Source & Risk Analytics**: Categorical aggregations and distribution metrics.

### Phase 5 — Command Center UI (`phase-5-ui`)
- **Dark Command-Center UI**: Modern, responsive geospatial dashboard.
- **Interactive Leaflet Map**: Render color-coded hotspot markers, risk halos, and dynamic clusters.
- **Incident Feed & Filters**: Real-time list with search and multi-axis filters (risk, source, FRP, confidence).
- **Incident Detail Drawer**: Full inspector showing weather dials, proximity cards, timeline, and explainable AI factors.
- **Recharts Analytics**: Visual distribution charts for sources and risk levels.
- **Operational Alerts Feed & KPIs**: Unread alert banner, critical incident alerts, and live/demo mode badge.
