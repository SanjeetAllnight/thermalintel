# Sample & Demo Datasets

This directory contains deterministic sample data used for:
1. **Fallback Operation**: When NASA FIRMS API keys are missing, quota-exceeded, or network connectivity is lost.
2. **Deterministic Integration Tests**: Allowing UI and Intelligence agents to develop against stable, known datasets.
3. **Seeding Initial SQLite Database**: Fast local bootstrapping for hackathon evaluation.

### Files
- `sample_hotspots.json`: 10 realistic VIIRS satellite anomalies covering wildfires, industrial stacks, agricultural burns, controlled burns, and volcanic activity.
- `sample_incidents.json`: Full deep-dive enriched objects (geospatial context, weather metrics, historical persistence, ML feature attributions, explainable risk factors).
- `sample_alerts.json`: Notification alerts corresponding to active high-risk hotspots.
