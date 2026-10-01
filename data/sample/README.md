# Sample & Demo Datasets

This directory contains deterministic sample data used for:
1. **Fallback Operation**: When NASA FIRMS API keys are missing, quota-exceeded, or network connectivity is lost.
2. **Deterministic Integration Tests**: Allowing UI and Intelligence agents to develop against stable, known datasets.
3. **Seeding Initial SQLite Database**: Fast local bootstrapping for hackathon evaluation.

---

## 1. Hotspots Dataset (`sample_hotspots.json`)

The sample dataset contains 30 high-fidelity satellite thermal anomaly records. It can be validated and regenerated deterministically at any time via:
```bash
python scripts/data/generate_sample_data.py
```

### Hotspot Schema
| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique identifier (e.g. `VIIRS-SNPP-20261001-001`) |
| `latitude` | `float` | WGS84 latitude (-90.0 to 90.0) |
| `longitude` | `float` | WGS84 longitude (-180.0 to 180.0) |
| `brightness` | `float` | Channel 21 / I-4 brightness temperature (Kelvin) |
| `scan` | `float` | Along-scan pixel resolution in km (nominal 0.375) |
| `track` | `float` | Along-track pixel resolution in km (nominal 0.375) |
| `acq_date` | `string` | Acquisition date (`YYYY-MM-DD`) |
| `acq_time` | `string` | UTC acquisition time (`HHMM`) |
| `satellite` | `string` | Satellite platform (`Suomi-NPP`, `NOAA-20`, `NOAA-21`) |
| `instrument` | `string` | Sensor instrument (`VIIRS`) |
| `confidence` | `string` | Detection confidence (`low`, `nominal`, `high`) |
| `version` | `string` | Processing stream version (`2.0NRT`) |
| `bright_t31` | `float \| null` | Channel 31 / I-5 brightness temperature (Kelvin) |
| `frp` | `float` | Fire Radiative Power (MW) |
| `daynight` | `string` | Pass daylight flag (`D` or `N`) |
| `source_type` | `string` | Classified source (`wildfire`, `industrial`, `agricultural`, `prescribed_burn`, `urban`, `volcanic`) |
| `risk_score` | `float` | Evaluated composite risk score (0.0 to 100.0) |
| `risk_level` | `string` | Categorical risk rating (`low`, `medium`, `high`, `critical`) |
| `is_anomaly` | `boolean` | Flagged statistical anomaly indicator |
| `cluster_id` | `string \| null` | Multi-pixel spatial cluster ID |
| `cluster_size`| `integer` | Count of pixels grouped in the spatial cluster |
| `nearest_place`| `string \| null`| Human-readable locality or administrative district |
| `last_updated`| `string` | ISO 8601 UTC timestamp |

### Multi-Pixel Spatial Clusters
- `CL-SONOMA-01`: 6 detections along the Geysers / Cobb Mountain wildfire complex in Northern California.
- `CL-ANGELES-01`: 4 detections across the San Gabriel Ridge in Southern California.
- `CL-SIERRA-01`: 4 detections in the Feather River Canyon / Plumas National Forest.
- `CL-GULF-IND`: 3 detections at Houston Ship Channel, Baytown, and Texas City petrochemical complexes.
- `CL-VALLEY-AG`: 3 detections in Central Valley agricultural crop residue burn parcels.
- `CL-IDAHO-01`: 3 forest wildfire detections in Boise National Forest.
- `CL-OREGON-PB`: 2 controlled understory prescribed burns in Deschutes National Forest.
- `CL-KILAUEA`: 2 active volcanic fissure detections in Hawaii Volcanoes National Park.
- `CL-UTAH-IND`: Persistent industrial smelting heat source in Salt Lake County.

---

## 2. Additional Bundled Datasets
- `sample_incidents.json`: Full deep-dive enriched objects (geospatial context, weather metrics, historical persistence, ML feature attributions, explainable risk factors).
- `sample_alerts.json`: Notification alerts corresponding to active high-risk hotspots.
