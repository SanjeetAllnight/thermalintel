# ThermalIntel Frozen API Contract

> **FROZEN SPECIFICATION**: This API contract is locked. All agents (`agent-data`, `agent-ui`, `agent-intelligence`) must strictly adhere to these routes, request shapes, and response payloads.

Base URL: `http://localhost:8000/api`

---

## 1. System Health
### `GET /api/health`
Returns system status, active data mode (live vs. demo), and readiness of underlying subsystems.

#### Response `200 OK`
```json
{
  "status": "ok",
  "version": "0.1.0",
  "data_mode": "demo",
  "timestamp": "2026-10-01T10:30:00Z",
  "services": {
    "database": "connected",
    "firms_api": "ready",
    "intelligence_engine": "online"
  }
}
```

---

## 2. Hotspots Feed & Filtering
### `GET /api/hotspots`
Retrieves normalized satellite thermal anomalies with filtering and pagination.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `risk_level` | `string` | No | Filter by risk: `low`, `medium`, `high`, `critical` |
| `source_type` | `string` | No | Filter by source: `wildfire`, `industrial`, `agricultural`, `urban`, `volcanic`, `prescribed_burn`, `unknown` |
| `min_frp` | `float` | No | Minimum Fire Radiative Power (MW) |
| `min_confidence` | `string` | No | Minimum confidence: `nominal`, `high` |
| `is_anomaly` | `boolean` | No | Filter statistical anomalies (`true` / `false`) |
| `cluster_id` | `string` | No | Filter by cluster ID |
| `page` | `integer` | No | Page number (default: 1) |
| `page_size` | `integer` | No | Records per page (default: 50, max: 500) |

#### Response `200 OK`
```json
{
  "items": [
    {
      "id": "VIIRS-SNPP-20261001-001",
      "latitude": 38.7421,
      "longitude": -122.8105,
      "brightness": 352.4,
      "scan": 0.38,
      "track": 0.36,
      "acq_date": "2026-10-01",
      "acq_time": "0845",
      "satellite": "Suomi-NPP",
      "instrument": "VIIRS",
      "confidence": "high",
      "version": "2.0NRT",
      "bright_t31": 298.4,
      "frp": 142.8,
      "daynight": "N",
      "source_type": "wildfire",
      "risk_score": 92.5,
      "risk_level": "critical",
      "is_anomaly": true,
      "cluster_id": "CL-SONOMA-01",
      "cluster_size": 5,
      "nearest_place": "Geysers Basin, Sonoma County, CA",
      "last_updated": "2026-10-01T08:50:00Z"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 50,
  "data_mode": "demo",
  "generated_at": "2026-10-01T10:30:00Z"
}
```

---

## 3. Incident Deep-Dive Dossier
### `GET /api/hotspots/{id}`
Returns full enriched context (geospatial proximity, weather metrics, historical detection persistence, and explainable AI risk scoring).

#### Response `200 OK`
```json
{
  "hotspot": {
    "id": "VIIRS-SNPP-20261001-001",
    "latitude": 38.7421,
    "longitude": -122.8105,
    "brightness": 352.4,
    "scan": 0.38,
    "track": 0.36,
    "acq_date": "2026-10-01",
    "acq_time": "0845",
    "satellite": "Suomi-NPP",
    "instrument": "VIIRS",
    "confidence": "high",
    "version": "2.0NRT",
    "bright_t31": 298.4,
    "frp": 142.8,
    "daynight": "N",
    "source_type": "wildfire",
    "risk_score": 92.5,
    "risk_level": "critical",
    "is_anomaly": true,
    "cluster_id": "CL-SONOMA-01",
    "cluster_size": 5,
    "nearest_place": "Geysers Basin, Sonoma County, CA",
    "last_updated": "2026-10-01T08:50:00Z"
  },
  "geospatial": {
    "land_cover": "dense_coniferous_forest",
    "nearest_infrastructure": "State Route 175 & PG&E Transmission Corridor",
    "distance_to_infrastructure_meters": 450.0,
    "nearest_settlement": "Cobb Mountain Community & Geysers Resort",
    "distance_to_settlement_meters": 1200.0,
    "is_protected_area": true,
    "protected_area_name": "Boggs Mountain Demonstration State Forest",
    "elevation_meters": 985.0,
    "slope_degrees": 28.5,
    "fuel_load_estimate": "extreme_dry_chaparral"
  },
  "weather": {
    "temperature_celsius": 29.4,
    "relative_humidity_percent": 14.0,
    "wind_speed_kmh": 38.5,
    "wind_gust_kmh": 58.0,
    "wind_direction_degrees": 42.0,
    "wind_direction_cardinal": "NE",
    "precipitation_mm": 0.0,
    "fire_weather_index": 88.5,
    "forecast_summary": "Red Flag Warning active. Gusty Diablo winds and critically dry vegetation."
  },
  "historical": {
    "prior_detections_30d": 1,
    "prior_detections_90d": 3,
    "is_recurrent_site": false,
    "recurrent_pattern": "none",
    "first_detected_date": "2026-09-28",
    "detection_frequency_score": 0.12
  },
  "intelligence": {
    "hotspot_id": "VIIRS-SNPP-20261001-001",
    "classification": {
      "predicted_source": "wildfire",
      "confidence": 0.96,
      "probabilities": {
        "wildfire": 0.96,
        "prescribed_burn": 0.02,
        "agricultural": 0.01,
        "industrial": 0.005,
        "urban": 0.003,
        "volcanic": 0.002
      },
      "feature_importance": {
        "fire_radiative_power": 0.38,
        "wind_speed": 0.24,
        "land_cover_fuel": 0.22,
        "humidity": 0.16
      }
    },
    "anomaly": {
      "is_anomaly": true,
      "anomaly_score": 0.94,
      "baseline_deviation": 4.8,
      "anomaly_rationale": "FRP of 142.8 MW is 4.8 sigma above historical 30-day baseline for this grid cell."
    },
    "risk": {
      "risk_score": 92.5,
      "risk_level": "critical",
      "frp_component": 94.0,
      "weather_component": 96.0,
      "proximity_component": 88.0,
      "historical_component": 20.0,
      "explainable_factors": [
        {
          "factor": "Extreme Fire Radiative Power (142.8 MW)",
          "weight": 0.35,
          "impact": "critical",
          "description": "Intense convective thermal energy indicative of rapidly advancing canopy crown fire."
        },
        {
          "factor": "Critical Fire Weather (RH 14%, Winds 38.5 km/h)",
          "weight": 0.30,
          "impact": "critical",
          "description": "Offshore wind gusts exceeding 50 km/h align with steep slope, creating extreme forward spotting potential."
        },
        {
          "factor": "Settlement Proximity (< 1.5 km)",
          "weight": 0.25,
          "impact": "critical",
          "description": "Under 1.2 km from Cobb residential fringe and power transmission line corridor."
        }
      ],
      "recommended_action": "Issue immediate structural defense advisory and alert local CalFire dispatch unit."
    },
    "model_version": "v1.0-rf-heuristic",
    "evaluated_at": "2026-10-01T08:52:00Z"
  },
  "timeline": [
    {
      "timestamp": "2026-10-01T08:45:00Z",
      "event_type": "satellite_pass",
      "summary": "Suomi-NPP VIIRS pass detected 142.8 MW thermal anomaly",
      "details": {
        "satellite": "Suomi-NPP",
        "brightness_k": 352.4,
        "confidence": "high"
      }
    }
  ],
  "data_mode": "demo"
}
```

#### Error Response `404 Not Found`
```json
{
  "detail": "Hotspot with ID 'UNKNOWN-ID' not found"
}
```

---

## 4. Dashboard Summary & KPIs
### `GET /api/summary`
Retrieves top-level operational statistics and dominant risk patterns.

#### Response `200 OK`
```json
{
  "total_active_hotspots": 10,
  "critical_risk_count": 4,
  "high_risk_count": 2,
  "medium_risk_count": 3,
  "low_risk_count": 1,
  "active_alerts_count": 3,
  "average_frp": 67.06,
  "max_frp": 165.0,
  "average_risk_score": 62.4,
  "data_mode": "demo",
  "last_sync_time": "2026-10-01T08:50:00Z",
  "dominant_source": "wildfire",
  "source_counts": {
    "wildfire": 4,
    "industrial": 1,
    "agricultural": 1,
    "prescribed_burn": 1,
    "urban": 1,
    "volcanic": 1
  },
  "recent_critical_hotspots": [...]
}
```

---

## 5. Alerts Feed
### `GET /api/alerts`
Retrieves operational notifications and alerts.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `severity` | `string` | No | Filter by severity: `info`, `warning`, `critical` |
| `unread_only` | `boolean` | No | If true, returns only unacknowledged alerts |

#### Response `200 OK`
```json
{
  "items": [
    {
      "id": "ALT-20261001-001",
      "hotspot_id": "VIIRS-SNPP-20261001-001",
      "severity": "critical",
      "title": "Rapid Convective Flare & Settlement Threat - Sonoma Basin",
      "message": "FRP peaked at 142.8 MW within 1.2km of Cobb settlement. High wind gusts (58 km/h NE) creating extreme spotting hazard.",
      "risk_score": 92.5,
      "location_name": "Geysers Basin, Sonoma County, CA",
      "latitude": 38.7421,
      "longitude": -122.8105,
      "timestamp": "2026-10-01T08:50:00Z",
      "is_acknowledged": false,
      "recommended_action": "Trigger emergency zone alert; coordinate structural defense with CalFire Unit Sonoma-Lake-Napa.",
      "tags": ["wildfire", "high_wind", "settlement_proximity", "critical_frp"]
    }
  ],
  "total": 3,
  "unread_count": 2,
  "generated_at": "2026-10-01T10:30:00Z"
}
```

---

## 6. Sources Analytics Breakdown
### `GET /api/sources`
Retrieves aggregate distribution and risk profiles grouped by classified thermal source.

#### Response `200 OK`
```json
{
  "sources": [
    {
      "source_type": "wildfire",
      "display_name": "Wildfire / Forest Fire",
      "count": 4,
      "percentage": 40.0,
      "average_frp": 97.9,
      "average_risk": 84.2,
      "primary_driver": "Vegetative dry fuel & wind propagation"
    },
    {
      "source_type": "industrial",
      "display_name": "Industrial Facility / Flare Stack",
      "count": 1,
      "percentage": 10.0,
      "average_frp": 24.3,
      "average_risk": 26.5,
      "primary_driver": "Petrochemical, refining, & gas processing"
    }
  ],
  "total_evaluated": 10,
  "dominant_source": "wildfire",
  "data_mode": "demo",
  "generated_at": "2026-10-01T10:30:00Z"
}
```

---

## 7. Data Sync / Refresh Trigger
### `POST /api/refresh`
Triggers synchronization from live NASA FIRMS API or re-indexes local fallback data.

#### Request Body (Optional)
```json
{
  "force_sample": false,
  "bbox": [-124.4, 32.5, -114.1, 42.0],
  "days": 1
}
```

#### Response `200 OK`
```json
{
  "status": "success",
  "message": "Synchronization completed successfully. Hotspot catalog refreshed.",
  "ingested_count": 10,
  "data_mode": "demo",
  "timestamp": "2026-10-01T10:30:00Z",
  "execution_time_seconds": 0.042
}
```
