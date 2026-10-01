# Ingestion & Enrichment Cache

This directory holds cached raw API responses to minimize latency and avoid hitting external rate limits:
- NASA FIRMS raw CSV / GeoJSON responses
- OpenStreetMap Overpass bounding box query results
- Open-Meteo local coordinate weather snapshots

Data in this directory is ephemeral and ignored by git.
