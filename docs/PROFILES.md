# ThermalIntel Profile Architecture & Reusability Specification

## 1. Overview & Architectural Mission

ThermalIntel Phase 7 transforms ThermalIntel from a single-domain wildland fire system into a **reusable geospatial thermal-intelligence platform**. By introducing a decoupled, profile-driven configuration architecture, the platform can support disparate operational domains—including wildland fire monitoring, industrial/refinery safety, agricultural burning, volcano surveillance, and defense asset monitoring—without modifying or duplicating the core canonical intelligence and incident engine pipelines.

```
                           +------------------------+
                           |  Domain Profile (JSON) |
                           |  (e.g., wildfire or    |
                           |   industrial-safety)   |
                           +-----------+------------+
                                       |
                                       v
                           +------------------------+
                           |     Profile Loader     |
                           |  (Deterministic &      |
                           |   Pydantic Validated)  |
                           +-----------+------------+
                                       |
    +----------------------------------+----------------------------------+
    |                  |               |                |                 |
    v                  v               v                v                 v
+--------+       +-----------+    +---------+     +------------+    +-----------+
|Providers|      | Taxonomy  |    |  Risk   |     | Incidents  |    |  Alerts   |
|Config  |       | & Rules   |    | Weights |     | Clustering |    |  Pacing   |
+---+----+       +-----+-----+    +----+----+     +-----+------+    +-----+-----+
    |                  |               |                |                 |
    +------------------+---------------+----------------+-----------------+
                                       |
                                       v
            +-------------------------------------------------------+
            |          CANONICAL THERMALINTEL V2 PIPELINE           |
            |                                                       |
            |  Raw Feeds -> Ingestion -> Normalization (V2 Obs)     |
            |  -> Geospatial Enrichment (AssetStore)                |
            |  -> Intelligence Classification & Risk Assessment     |
            |  -> Incident Clustering & Lifecycle State Machine     |
            |  -> Operational Alerts & Pacing Guardrails            |
            |  -> Deterministic Scenario Replay                     |
            +-------------------------------------------------------+
```

---

## 2. What Remains Generic vs. What Became Profile Configuration

A critical architectural principle of Phase 7 is: **no code-level domain branching (`if profile == 'wildfire'`)**. The core platform code does not branch on profile names; instead, engines read strongly-typed configuration parameters and execute invariant mathematical and relational algorithms.

| Subsystem | Generic Core Engine (Code) | Profile-Driven Configuration (Data) |
|---|---|---|
| **Data Contracts** | Frozen V2 schemas (`Observation`, `Assessment`, `Incident`, `AlertV2`, `ProviderRun`, `RawPayloadMetadata`). | Declared providers, default product sources, query parameters. |
| **Ingestion & Normalization** | Coordinate validation, timestamp ISO parsing, radiometric unit conversions, diagnostics tracking. | Active providers list, spatial bounding boxes, provider credentials (via env vars). |
| **Asset Store & Enrichment** | KD-Tree indexing (`cKDTree`), spatial radius queries, bounding box filtering, distance calculations. | Path to domain static assets (`GeoJSON`), asset categories, proximity thresholds. |
| **Classification Engine** | Multi-class evidence accumulation, confidence score calibration, spatial & temporal feature vectorization. | Domain taxonomy categories, prior weights, deterministic detection rules, FRP threshold limits. |
| **Risk Assessment** | Composite normalized score formulation (0–100), severity escalation logic, factor breakdown calculation. | Dimension weights (FRP, weather, proximity, anomaly, persistence), severity level cutoffs. |
| **Incident Correlator** | Spatial clustering (`cKDTree` / Haversine), temporal sliding window, incident ID generation, lifecycle transitions, event audit log. | Spatial correlation threshold (km), temporal window (hours), merge distance (km), reopen window (hours), mutually incompatible category pairs. |
| **Operational Alerts** | Transition detection, deduplication, sliding-window pacing, flood protection, cooldown timers. | Minimum alert severity, extreme FRP threshold, per-rule & global cooldown durations, max alerts/hour limit. |
| **Replay & Scenarios** | Deterministic step execution, virtual clock advancement, golden state comparison, snapshot generation. | Associated domain scenarios list, seed configurations, golden baseline reference files. |

---

## 3. Profile Schema Reference

Profiles are defined in `profile.json` files and validated at load time by strongly-typed Pydantic V2 models defined in `profiles/schema.py`:

```python
ProfileConfig
├── metadata: MetadataConfig
│   ├── id: str                     # e.g., "wildfire", "industrial-safety"
│   ├── display_name: str           # Human-readable title
│   ├── description: str            # Domain scope explanation
│   ├── version: str                # Semantic version, e.g. "1.0.0"
│   └── author: Optional[str]
├── providers: ProvidersConfig
│   ├── enabled_providers: List[str]# e.g., ["NASA_FIRMS"]
│   ├── default_source: str         # e.g., "VIIRS_SNPP_NRT"
│   ├── default_bbox: Optional[Dict]
│   └── polling_interval_sec: int
├── taxonomy: TaxonomyConfig
│   ├── primary_source_types: List[str]      # e.g., ["wildfire", "prescribed_burn"]
│   ├── valid_classifications: List[str]
│   └── incompatible_pairs: List[Tuple[str, str]] # e.g. [("wildfire", "industrial")]
├── rules: ClassificationRulesConfig
│   ├── deterministic_rules_enabled: bool
│   ├── thresholds: ClassificationThresholds
│   │   ├── frp_high_mw: float               # e.g., 40.0 for wildfire, 25.0 for industrial
│   │   ├── recurrent_min_passes_30d: int
│   │   ├── industrial_immediate_m: float
│   │   └── settlement_critical_m: float
│   └── category_priorities: Dict[str, int]
├── risk: RiskProfileConfig
│   ├── weights: RiskWeights
│   │   ├── frp: float                       # 0.0 - 1.0 (sums to 1.0)
│   │   ├── weather: float
│   │   ├── proximity: float
│   │   ├── anomaly: float
│   │   └── history: float
│   ├── thresholds: RiskThresholds
│   │   ├── low: float                       # e.g., 25.0
│   │   ├── medium: float                    # e.g., 50.0
│   │   ├── high: float                      # e.g., 75.0
│   │   └── critical: float                  # e.g., 90.0
│   └── source_multipliers: Dict[str, float]
├── incidents: IncidentProfileConfig
│   ├── spatial_threshold_km: float          # e.g., 2.0 km (wildfire) vs 0.6 km (industrial)
│   ├── temporal_window_hours: float         # e.g., 24.0 h (wildfire) vs 12.0 h (industrial)
│   ├── merge_distance_km: float             # e.g., 3.0 km (wildfire) vs 1.0 km (industrial)
│   ├── reopen_window_hours: float
│   └── enforce_taxonomy_compatibility: bool
├── alerts: AlertProfileConfig
│   ├── min_alert_severity: str              # "medium", "high", "critical"
│   ├── extreme_frp_threshold: float         # e.g., 100.0 (wildfire) vs 40.0 (industrial)
│   ├── flood_protection: FloodProtectionProfileConfig
│   │   ├── per_rule_cooldown_seconds: int   # e.g. 1800 (wildfire) vs 300 (industrial)
│   │   ├── global_cooldown_seconds: int
│   │   └── max_alerts_per_hour: int
│   └── alertable_transitions: List[str]
├── assets: AssetsProfileConfig
│   ├── static_assets_path: Optional[str]
│   └── relevant_asset_categories: List[str]
└── scenarios: ScenariosProfileConfig
    └── available_scenarios: List[str]
```

---

## 4. Profile Loading and Resolution Architecture

Profiles are managed by `profiles/loader.py`:

1. **Resolution Priority**:
   - Explicit program argument: e.g. `set_active_profile("industrial-safety")`
   - Environment Variable: `THERMALINTEL_PROFILE`
   - Default: `"wildfire"` (ensuring strict 100% backwards compatibility)
2. **Deterministic Validation**:
   - Reads `profiles/{profile_id}/profile.json`.
   - Parses and validates JSON using `ProfileConfig.model_validate(raw)`.
   - Cached in-memory to prevent filesystem overhead during high-throughput ingestion.
   - Raises explicit `ProfileNotFoundError` if the profile directory or file does not exist.
   - Raises explicit `ProfileValidationError` if any configuration field violates schema rules or constraints.
3. **Configuration Safety & Zero-Secret Guarantee**:
   - Profiles contain **zero credentials or secrets**. All API keys remain in standard external environment variables (e.g. `FIRMS_MAP_KEY`).
   - Profile configurations are strictly data descriptions; no executable code or dynamic evaluation occurs inside profiles.

---

## 5. Provided Operational Profiles

### 5.1. Wildfire Profile (`profiles/wildfire/profile.json`)
- **Domain Focus**: Landscape-scale wildland fire detection, perimeter tracking, settlement threat warnings.
- **Key Characteristics**:
  - `spatial_threshold_km`: `2.0` (accounts for VIIRS 375m/750m pixel footprints and large fire fronts).
  - `temporal_window_hours`: `24.0` (standard satellite overpass cadence).
  - `merge_distance_km`: `3.0` (unifies spreading flanks into cohesive incidents).
  - `risk.weights`: FRP `0.35`, Weather `0.25`, Proximity `0.20`, Anomaly `0.10`, History `0.10`.
  - `alerts.extreme_frp_threshold`: `100.0 MW`.
  - `flood_protection.per_rule_cooldown_seconds`: `1800` (30 minutes).

### 5.2. Industrial Safety Profile (`profiles/industrial-safety/profile.json`)
- **Domain Focus**: Refinery flare monitoring, chemical complex heat signatures, asset boundary anomalies.
- **Key Characteristics**:
  - `spatial_threshold_km`: `0.6` (tighter spatial bounds preventing cross-facility cluster merging).
  - `temporal_window_hours`: `12.0` (higher temporal sensitivity to process excursions).
  - `merge_distance_km`: `1.0` (preserves distinct facility identification).
  - `risk.weights`: FRP `0.40`, Weather `0.15`, Proximity `0.25`, Anomaly `0.10`, History `0.10`.
  - `alerts.extreme_frp_threshold`: `40.0 MW` (flares exceeding 40 MW represent urgent safety hazards).
  - `flood_protection.per_rule_cooldown_seconds`: `300` (5 minutes rapid pacing for safety operators).
  - `assets.static_assets_path`: Dedicated high-resolution industrial asset database (`profiles/industrial-safety/assets/industrial_assets.geojson`).

---

## 6. How to Run with Different Profiles

### 6.1. Via Environment Variable (CLI / Docker / Deployment)
```bash
# Run with default wildfire profile:
python -m services.api.main

# Run with industrial safety profile:
THERMALINTEL_PROFILE=industrial-safety python -m services.api.main
```

### 6.2. Programmatic Selection
```python
from profiles.loader import set_active_profile, get_active_profile
from services.intelligence.engine import ThermalIntelligenceEngine

# Activate the industrial safety profile
profile = set_active_profile("industrial-safety")

# Instantiate generic intelligence engine with the active profile
engine = ThermalIntelligenceEngine(profile=profile)
```

### 6.3. API Inspection Endpoints
The platform exposes read-only profile inspection endpoints:
- `GET /api/v1/profile`: Returns metadata and configuration summary of the currently active profile.
- `GET /api/v1/profiles`: Lists all installed profiles discovered in the `profiles/` directory.
- `GET /`: Platform root health check includes `"active_profile": "..."`.

---

## 7. How to Add a New Domain Profile in 5 Steps

To introduce a new domain (e.g., `agricultural-monitoring`, `volcano-surveillance`, `defense-assets`):

### Step 1: Create the Profile Directory
```bash
mkdir -p profiles/agricultural-monitoring
```

### Step 2: Create `profile.json`
Define the configuration conforming to `ProfileConfig`:
```json
{
  "metadata": {
    "id": "agricultural-monitoring",
    "display_name": "Agricultural Crop & Stubble Burning",
    "description": "Seasonal crop residue burning detection and emission tracking",
    "version": "1.0.0"
  },
  "providers": {
    "enabled_providers": ["NASA_FIRMS"],
    "default_source": "VIIRS_SNPP_NRT"
  },
  "taxonomy": {
    "primary_source_types": ["agricultural_burn", "prescribed_burn"],
    "valid_classifications": ["agricultural_burn", "wildfire", "unknown"],
    "incompatible_pairs": [["agricultural_burn", "industrial"]]
  },
  "rules": {
    "deterministic_rules_enabled": true,
    "thresholds": {
      "frp_high_mw": 20.0,
      "recurrent_min_passes_30d": 3
    }
  },
  "risk": {
    "weights": {
      "frp": 0.25,
      "weather": 0.35,
      "proximity": 0.20,
      "anomaly": 0.10,
      "history": 0.10
    },
    "thresholds": {
      "low": 20.0,
      "medium": 45.0,
      "high": 70.0,
      "critical": 85.0
    }
  },
  "incidents": {
    "spatial_threshold_km": 1.0,
    "temporal_window_hours": 8.0,
    "merge_distance_km": 1.5,
    "reopen_window_hours": 24.0
  },
  "alerts": {
    "min_alert_severity": "medium",
    "extreme_frp_threshold": 35.0,
    "flood_protection": {
      "per_rule_cooldown_seconds": 600,
      "global_cooldown_seconds": 60,
      "max_alerts_per_hour": 50
    }
  }
}
```

### Step 3: (Optional) Add Domain Geospatial Assets
If your domain has specific infrastructure or boundary data, place a GeoJSON file in:
`profiles/agricultural-monitoring/assets/crop_zones.geojson` and reference it in `assets.static_assets_path`.

### Step 4: Verify Validation with Tests
Create a test in `tests/test_profiles/` or run the profile validation suite:
```bash
pytest tests/test_profiles/test_profile_loading_and_validation.py -v
```

### Step 5: Run or Deploy with the New Profile
```bash
THERMALINTEL_PROFILE=agricultural-monitoring uvicorn services.api.main:app --port 8000
```
No core engine code modifications, no new database tables, and no pipeline duplication required!
