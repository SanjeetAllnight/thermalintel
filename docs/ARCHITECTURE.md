# ThermalIntel Architecture Documentation

## Executive Overview
**ThermalIntel** is an AI-powered geospatial decision-support system designed to detect, classify, and assess the risk of satellite thermal anomalies in real time. Built under rapid hackathon constraints (< 3 hours to full prototype), it is partitioned for zero-conflict parallel development across three autonomous agents.

```
                              ┌───────────────────────────────────────────────┐
                              │            NASA FIRMS (VIIRS / MODIS)        │
                              └──────────────────────┬────────────────────────┘
                                                     │ Satellite Thermal Radiance
                                                     ▼
┌───────────────────────────┐         ┌───────────────────────────────────────┐         ┌───────────────────────────┐
│ OpenStreetMap (Overpass)  │────────▶│      Thermal Anomaly Ingestion        │◀────────│   Open-Meteo Weather API  │
│ (Assets, settlements, GIS)│         │     & Normalization Pipeline          │         │(Temp, RH, wind speed/dir) │
└───────────────────────────┘         └──────────────────┬────────────────────┘         └───────────────────────────┘
                                                         │
                                                         ▼
                                      ┌───────────────────────────────────────┐
                                      │      Intelligence Subsystem (ML)      │
                                      │  - Thermal Source Classification     │
                                      │  - Statistical Anomaly Detection      │
                                      │  - 0-100 Risk / Severity Scoring      │
                                      │  - Explainable Risk Factor Engine     │
                                      └──────────────────┬────────────────────┘
                                                         │
                                                         ▼
                                      ┌───────────────────────────────────────┐
                                      │        SQLite Persistent Store        │
                                      │  (hotspots, details, alerts, meta)    │
                                      └──────────────────┬────────────────────┘
                                                         │
                                                         ▼
                                      ┌───────────────────────────────────────┐
                                      │       FastAPI Backend Service         │
                                      │         (Frozen API Contract)         │
                                      └──────────────────┬────────────────────┘
                                                         │ REST JSON (Port 8000)
                                                         ▼
                                      ┌───────────────────────────────────────┐
                                      │       Next.js 14 Frontend Web App     │
                                      │   - Interactive Leaflet Map           │
                                      │   - Hotspot Clustering / Heatmap      │
                                      │   - Incident Feed & Filters           │
                                      │   - Detail Drawer with AI Factors     │
                                      │   - Recharts Risk & Source Analytics  │
                                      └───────────────────────────────────────┘
```

---

## Subsystem Architecture & Boundaries

### 1. Ingestion & Data Subsystem (`services/api/` + `data/` + `scripts/`) — Owned by `agent-data`
- **NASA FIRMS Ingestion**: Fetches near-real-time (NRT) satellite thermal anomaly CSV/GeoJSON from Suomi-NPP / NOAA-20 VIIRS instruments.
- **Fallback / Demo Engine**: When `FIRMS_MAP_KEY` is missing or network connectivity is severed, seamlessly falls back to curated sample datasets in `data/sample/`.
- **Geospatial Enrichment**: Queries OpenStreetMap Overpass API for nearest human settlements, critical infrastructure (power lines, substations, pipelines, highways), and protected conservation reserves.
- **Environmental Enrichment**: Queries Open-Meteo for ambient air temperature, relative humidity, wind speed, wind direction, and recent precipitation.
- **Historical Recurrence**: Evaluates localized 30-day and 90-day thermal detection history in the same spatial grid to differentiate routine industrial flaring from emergent wildland ignitions.
- **SQLite Persistence**: Stores normalized hotspots, deep-dive incident JSONs, and operational alert items.

### 2. Intelligence & ML Subsystem (`services/intelligence/`) — Owned by `agent-intelligence`
- **Thermal-Source Classifier**: Distinguishes between:
  1. `wildfire`: High FRP, forested/chaparral land cover, steep slopes, high fire weather index.
  2. `industrial`: High historical recurrence, located in heavy industrial or refinery zones, steady thermal signature.
  3. `agricultural`: Cropland/farmland, seasonal burn pattern, moderate FRP.
  4. `prescribed_burn`: Managed forest/park parcel, controlled intensity.
  5. `urban`: Commercial/dense urban footprint, high thermal mass.
  6. `volcanic`: Remote geothermal/caldera feature, extreme radiative power.
- **AI Anomaly Detector**: Evaluates sigma deviation against rolling 30-day baseline radiance; identifies statistical outliers.
- **Composite Risk Scorer (0 - 100)**: Multi-attribute decision matrix incorporating:
  - Fire Radiative Power (FRP component)
  - Atmospheric fire weather (Wind + Humidity + Temperature component)
  - Proximity to vulnerable human settlements and critical infrastructure
  - Historical recurrence penalty/mitigation
- **Explainable Attribution Engine**: Produces human-interpretable risk factor items with weights, categorical impact, and operational recommendation text.

### 3. User Interface Subsystem (`apps/web/`) — Owned by `agent-ui`
- **Interactive Geospatial Map**: Leaflet map displaying thermal anomalies with color-coded risk markers, dynamic clustering, and radius buffers.
- **Incident Feed & Filtering**: Real-time list of detected anomalies with interactive filters for risk severity, source type, minimum FRP, and text search.
- **Incident Deep-Dive Inspector**: Slide-over drawer detailing:
  - Settlement and infrastructure proximity
  - Environmental weather gauges (wind direction arrow, humidity, temp)
  - Historical satellite pass timeline
  - Explainable AI risk factors with interactive weight breakdown
  - Recommended response action
- **Analytics & Dashboard KPIs**:
  - Top-line KPI summary (Total hotspots, Critical, High, Mean FRP, Active Alerts)
  - Source distribution breakdown (Recharts)
  - Live vs. Demo mode indicator and manual sync trigger

---

## Database Schema (SQLite)

```sql
CREATE TABLE hotspots (
    id TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    brightness REAL NOT NULL,
    scan REAL,
    track REAL,
    acq_date TEXT NOT NULL,
    acq_time TEXT NOT NULL,
    satellite TEXT NOT NULL,
    instrument TEXT DEFAULT 'VIIRS',
    confidence TEXT NOT NULL,
    version TEXT,
    bright_t31 REAL,
    frp REAL NOT NULL,
    daynight TEXT NOT NULL,
    source_type TEXT NOT NULL,
    risk_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    is_anomaly INTEGER DEFAULT 0,
    cluster_id TEXT,
    cluster_size INTEGER DEFAULT 1,
    nearest_place TEXT,
    last_updated TEXT NOT NULL,
    data_mode TEXT DEFAULT 'demo'
);

CREATE TABLE incident_details (
    hotspot_id TEXT PRIMARY KEY,
    geospatial_json TEXT NOT NULL,
    weather_json TEXT NOT NULL,
    historical_json TEXT NOT NULL,
    intelligence_json TEXT NOT NULL,
    timeline_json TEXT NOT NULL,
    FOREIGN KEY (hotspot_id) REFERENCES hotspots(id)
);

CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    hotspot_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    risk_score REAL NOT NULL,
    location_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timestamp TEXT NOT NULL,
    is_acknowledged INTEGER DEFAULT 0,
    recommended_action TEXT NOT NULL,
    tags_json TEXT,
    FOREIGN KEY (hotspot_id) REFERENCES hotspots(id)
);

CREATE TABLE system_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

---

## Integration Invariants
1. **API Contract is Frozen**: Neither `agent-ui` nor `agent-intelligence` may alter endpoint paths, query parameters, or schema properties.
2. **Offline-First Resilience**: Backend must serve from `data/sample/` if external APIs are unreachable or keys are omitted.
3. **No Auth Dependency**: Local development proceeds without authentication overhead to maximize velocity.
4. **No Docker Requirement**: Direct local runtime via Python `venv` and Node `npm run dev`.
