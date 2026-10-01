# ThermalIntel Intelligence & ML Engine (`services/intelligence`)

Owned exclusively by **`agent-intelligence`** (Phase 3).

## Architecture & Subsystems

1. **Feature Extraction & Normalization** (`features.py`):
   - Radiometric FRP, brightness temperature, satellite confidence, day/night flags.
   - Geospatial proximity (settlement, critical infrastructure, industrial site, protected reserve).
   - Environmental fire weather (temperature, relative humidity, wind speed, precipitation).
   - Historical recurrence (30-day/90-day passes, persistence score).
   - Resilient missing-data handling without synthetic hallucination.

2. **Source Classification** (`classifier.py`):
   - Five core intelligence classes:
     - `VEGETATION_FIRE`
     - `POTENTIAL_INDUSTRIAL_FIRE`
     - `CONTROLLED_HEAT_SOURCE`
     - `PERSISTENT_THERMAL_SOURCE`
     - `UNKNOWN`
   - Bi-directional mapping and calibrated probability distribution over all frozen `SourceType` members (`wildfire`, `industrial`, `agricultural`, `prescribed_burn`, `urban`, `volcanic`, `unknown`).
   - Dynamic confidence estimation reflecting evidence completeness, radiometric clarity, and class separation.

3. **Anomaly Detection** (`anomaly.py`):
   - Dual-mode detector:
     - `IsolationForest` (multi-variate, deterministic `random_state=42`) for population-level/batch analysis (N >= 5).
     - Deterministic z-score statistical baseline fallback for single-hotspot or small datasets (N < 5).
   - Suppression of routine industrial flaring while flagging unprecedented thermal radiance surges.

4. **Composite Risk & Severity Scoring** (`risk.py`):
   - Multi-criteria decision index normalized to 0 - 100.
   - Dynamic weight normalization across active features when contextual telemetry is offline.
   - Strict deterministic severity thresholds:
     - `0 - 24`: `LOW`
     - `25 - 49`: `MEDIUM`
     - `50 - 74`: `HIGH`
     - `75 - 100`: `CRITICAL`

5. **Explainability & Attribution** (`explain.py`):
   - Generates 2 to 4 ranked `RiskFactor` objects tied to actual input signals.
   - Ensures semantic consistency between calculated risk score and explanation tone.
   - Delivers actionable operational recommendations for first responders.

6. **Context Adapter for Phase 2** (`context.py`):
   - Clean `HotspotContext` data structure compatible with unmerged Phase 2 enrichment output (nested or flat).

## Public Entry Points (`engine.py`)

```python
from services.intelligence import ThermalIntelligenceEngine, HotspotContext

engine = ThermalIntelligenceEngine()

# 1. Single Hotspot with Context
result = engine.analyze_hotspot(
    hotspot={"id": "VIIRS-001", "frp": 140.0, "brightness": 360.0, "confidence": "high"},
    context=HotspotContext(
        land_cover="dense_forest",
        distance_to_settlement_m=1200.0,
        wind_speed_kmh=38.0,
        relative_humidity_pct=14.0,
    ),
)

# 2. Batch Analysis (IsolationForest across population)
results = engine.batch_analyze(hotspots=[...], contexts=[...])

# 3. Backwards-compatible Phase 0 method
result = engine.evaluate_hotspot(hotspot_id="VIIRS-001", frp=125.0, brightness=350.0)
```

## Running Tests

```bash
PYTHONPATH=. pytest services/intelligence/tests/
```
