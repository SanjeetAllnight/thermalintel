# ThermalIntel Intelligence & ML (`services/intelligence`)

Owned exclusively by **`agent-intelligence`**.

## Responsibilities
- AI Anomaly Detection (`AnomalyResult`)
- Thermal-Source Classification (`ClassificationResult`)
- Composite Risk & Severity Scoring (`RiskAssessment`)
- Explainable Risk Factor generation (`RiskFactor`)

## Key Entrypoint
The core evaluation engine is defined in `services.intelligence.engine.ThermalIntelligenceEngine`.

## Running Smoke Tests
```bash
python -c "from services.intelligence.engine import ThermalIntelligenceEngine; e = ThermalIntelligenceEngine(); print('Engine initialized successfully')"
```
