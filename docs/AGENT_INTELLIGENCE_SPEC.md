# Specification for `agent-intelligence` (ML & Risk Modeling)

**Ownership Zone**: `services/intelligence/`  
**Strict Prohibition**: Do NOT touch `apps/web/` or `services/api/`!

---

## Mission Objectives
1. Implement and refine the **Thermal Source Classifier** using `scikit-learn`:
   - Inputs: FRP, brightness temperature, land cover, historical recurrence, slope, protected area flag.
   - Outputs: Probabilities across `wildfire`, `industrial`, `agricultural`, `prescribed_burn`, `urban`, `volcanic`, `unknown`.
2. Implement **Statistical Anomaly Detection**:
   - Outlier detection via `scikit-learn` `IsolationForest` or rolling regional z-score deviation.
   - Outputs: `is_anomaly`, `anomaly_score` (0-1), `baseline_deviation`, human-readable `anomaly_rationale`.
3. Implement the **Composite 0-100 Risk & Severity Model**:
   - Multi-factor evaluation: FRP intensity, fire weather index (wind speed, low humidity, ambient heat), human settlement proximity, infrastructure proximity, historical site recurrence.
   - Output normalized score (0-100) and categorical level (`low`, `medium`, `high`, `critical`).
4. Implement the **Explainable AI Attribution Factor Generator**:
   - Produces 2 to 5 ranked `RiskFactor` objects explaining the decision:
     - `factor`: e.g. "Adverse Fire Weather (38 km/h, 14% RH)"
     - `weight`: float (0.0 to 1.0)
     - `impact`: `critical` | `high` | `medium` | `low`
     - `description`: Plain-language explanation of risk mechanism.
   - Generates actionable operational recommendations for first responders.

---

## Interface Invariants
The intelligence subsystem must implement `services.intelligence.engine.ThermalIntelligenceEngine` and return instances of the frozen Pydantic schemas:
- `ClassificationResult`
- `AnomalyResult`
- `RiskAssessment`
- `IntelligenceResult`

```python
engine = ThermalIntelligenceEngine()
result: IntelligenceResult = engine.evaluate_hotspot(
    hotspot_id="VIIRS-SNPP-001",
    frp=125.0,
    brightness=350.0,
    land_cover="dense_forest",
    historical_recurrence=1,
    is_protected_area=False,
    wind_speed_kmh=40.0,
    relative_humidity_percent=15.0,
    temperature_celsius=30.0,
    distance_to_settlement_m=1200.0,
    distance_to_infra_m=500.0,
    slope_degrees=25.0
)
```

---

## Acceptance Criteria
- [ ] Classification output includes calibrated probabilities across all 7 source types.
- [ ] Anomaly detection accurately flags high-FRP sudden spikes as anomalies while suppressing recurring industrial flares.
- [ ] Risk scoring outputs composite scores spanning 0 to 100 with clear explainable factor attributions.
- [ ] No changes made outside `services/intelligence/`.
