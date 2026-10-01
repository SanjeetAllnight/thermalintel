# ThermalIntel API Backend (`services/api`)

Owned exclusively by **`agent-data`**.

## Responsibilities
- FastAPI REST service hosting the 7 frozen API endpoints.
- SQLite persistence layer (`database.py` and `thermalintel.db`).
- NASA FIRMS real-time ingestion with offline sample fallback.
- OpenStreetMap Overpass and Open-Meteo enrichment pipelines.

## Running Locally
```bash
# From repository root:
uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
