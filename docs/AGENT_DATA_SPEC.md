# Specification for `agent-data` (Backend, Ingestion & Data)

**Ownership Zone**: `services/api/`, `data/`, `scripts/`  
**Strict Prohibition**: Do NOT touch `apps/web/` or `services/intelligence/`!

---

## Mission Objectives
1. Implement real-time ingestion from **NASA FIRMS** (VIIRS Suomi-NPP / NOAA-20 NRT CSV API).
2. Maintain 100% resilient fallback to `data/sample/sample_hotspots.json` when `FIRMS_MAP_KEY` is not provided or API calls fail.
3. Build the **Geospatial Enrichment** client using OpenStreetMap / Overpass API (querying nearest highways, power lines, towns, and protected forests within 5km radius).
4. Build the **Weather Enrichment** client using Open-Meteo free API (retrieving temperature, relative humidity, wind speed, wind direction at hotspot coordinates).
5. Build the **Historical Recurrence** analyzer (querying SQLite database for prior satellite passes within 1km over past 30 & 90 days).
6. Connect `services.intelligence.engine.ThermalIntelligenceEngine` to score and classify enriched hotspots during ingestion.
7. Maintain and fulfill the 7 frozen endpoints in `services/api/routers/api.py`.

---

## Key Modules to Implement

### 1. FIRMS Ingestion (`services/api/ingestion/firms.py`)
```python
# API Endpoint format:
# https://firms.modaps.eosdis.nasa.gov/api/area/csv/[MAP_KEY]/[SOURCE]/[BBOX]/[DAYS]
# Default source: VIIRS_SNPP_NRT
# If MAP_KEY is absent, load from data/sample/sample_hotspots.json
```
- Map raw CSV columns (`latitude`, `longitude`, `bright_ti4`, `scan`, `track`, `acq_date`, `acq_time`, `satellite`, `confidence`, `version`, `bright_ti5`, `frp`, `daynight`) to `services.api.schemas.Hotspot`.

### 2. OSM Overpass Client (`services/api/ingestion/overpass.py`)
```python
# Query Overpass API for assets around (lat, lon) within radius:
# - highway=*
# - power=line / power=substation
# - place=town / place=village / place=suburb
# - boundary=national_park / leisure=nature_reserve
```
- Cache Overpass query results in `data/cache/` to avoid rate limits.

### 3. Open-Meteo Weather Client (`services/api/ingestion/weather.py`)
```python
# Query https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation
```
- Parse and populate `WeatherContext`.

### 4. Recurrence & Spatial Clustering (`services/api/ingestion/clustering.py`)
- Group nearby hotspots (< 1km) into spatial clusters (`cluster_id`, `cluster_size`).
- Calculate historical recurrence frequency from `hotspots` table.

---

## Acceptance Criteria
- [ ] Running `POST /api/refresh` succeeds and refreshes database with either live FIRMS data or fallback sample data.
- [ ] `GET /api/hotspots/{id}` returns complete `geospatial` and `weather` dictionaries for the hotspot.
- [ ] No changes made outside `services/api/`, `data/`, or `scripts/`.
