-- Migration 0002: V2 Canonical Schema Foundation
-- Adds canonical domain tables: provider_runs, raw_payloads, observations,
-- enrichment_snapshots, assessments, incidents, incident_observations,
-- incident_events, alerts_v2.

-- 1. Raw Payloads Storage Metadata
CREATE TABLE IF NOT EXISTS raw_payloads (
    payload_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    product TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    retention_days INTEGER DEFAULT 90
);
CREATE INDEX IF NOT EXISTS idx_raw_payloads_hash ON raw_payloads(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_payloads_fetched ON raw_payloads(fetched_at_utc);

-- 2. Provider Run Audit & Observability Telemetry
CREATE TABLE IF NOT EXISTS provider_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    product TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL,
    rows_received INTEGER DEFAULT 0,
    duration_ms INTEGER,
    error_type TEXT,
    error_message TEXT,
    request_metadata_json TEXT,
    payload_id TEXT,
    FOREIGN KEY (payload_id) REFERENCES raw_payloads(payload_id)
);
CREATE INDEX IF NOT EXISTS idx_provider_runs_provider ON provider_runs(provider);
CREATE INDEX IF NOT EXISTS idx_provider_runs_status ON provider_runs(status);
CREATE INDEX IF NOT EXISTS idx_provider_runs_started ON provider_runs(started_at_utc);

-- 3. Canonical Observations (Pure Provider Evidence)
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    product TEXT NOT NULL,
    satellite TEXT,
    instrument TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    acquisition_time_utc TEXT NOT NULL,
    ingestion_time_utc TEXT NOT NULL,
    brightness REAL NOT NULL,
    bright_t31 REAL,
    frp REAL NOT NULL,
    scan REAL,
    track REAL,
    daynight TEXT NOT NULL,
    detection_confidence TEXT NOT NULL,
    source_attributes_json TEXT,
    raw_payload_id TEXT,
    schema_version TEXT DEFAULT '2.0',
    FOREIGN KEY (raw_payload_id) REFERENCES raw_payloads(payload_id)
);
CREATE INDEX IF NOT EXISTS idx_observations_spatial ON observations(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_observations_acquisition ON observations(acquisition_time_utc);
CREATE INDEX IF NOT EXISTS idx_observations_provider_product ON observations(provider, product);

-- 4. Contextual Enrichment Snapshots (Independent Provenance)
CREATE TABLE IF NOT EXISTS enrichment_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    context_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    product TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    freshness_state TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enrichment_target ON enrichment_snapshots(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_enrichment_context ON enrichment_snapshots(context_type);

-- 5. Canonical Assessments (Reproducible Intelligence Inferences)
CREATE TABLE IF NOT EXISTS assessments (
    assessment_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    predicted_source TEXT NOT NULL,
    classification_confidence REAL NOT NULL,
    class_probabilities_json TEXT NOT NULL,
    is_anomaly INTEGER NOT NULL DEFAULT 0,
    anomaly_score REAL NOT NULL,
    anomaly_rationale TEXT,
    risk_score REAL NOT NULL,
    severity TEXT NOT NULL,
    risk_factors_json TEXT NOT NULL,
    completeness_score REAL NOT NULL DEFAULT 1.0,
    uncertainty_score REAL NOT NULL DEFAULT 0.0,
    method TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    as_of_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessments_target ON assessments(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_assessments_input_hash ON assessments(input_hash);
CREATE INDEX IF NOT EXISTS idx_assessments_as_of ON assessments(as_of_utc);

-- 6. Canonical Incidents (Stable Real-World Entities)
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    first_seen_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL,
    centroid_latitude REAL NOT NULL,
    centroid_longitude REAL NOT NULL,
    geometry_geojson TEXT,
    nearest_place TEXT,
    peak_frp REAL NOT NULL,
    average_frp REAL NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    current_risk_score REAL NOT NULL,
    current_severity TEXT NOT NULL,
    current_classification TEXT NOT NULL,
    current_assessment_id TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY (current_assessment_id) REFERENCES assessments(assessment_id)
);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(current_severity);
CREATE INDEX IF NOT EXISTS idx_incidents_spatial ON incidents(centroid_latitude, centroid_longitude);
CREATE INDEX IF NOT EXISTS idx_incidents_updated ON incidents(updated_at_utc);

-- 7. Incident <-> Observation Associative Entity
CREATE TABLE IF NOT EXISTS incident_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    joined_at_utc TEXT NOT NULL,
    association_method TEXT NOT NULL DEFAULT 'dbscan_spatiotemporal',
    association_reason TEXT,
    UNIQUE (incident_id, observation_id),
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id) REFERENCES observations(observation_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_inc_obs_incident ON incident_observations(incident_id);
CREATE INDEX IF NOT EXISTS idx_inc_obs_observation ON incident_observations(observation_id);

-- 8. Incident Events (Immutable Append-Only Timeline)
CREATE TABLE IF NOT EXISTS incident_events (
    event_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system_correlator',
    reason TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_incident_events_incident ON incident_events(incident_id);
CREATE INDEX IF NOT EXISTS idx_incident_events_timestamp ON incident_events(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_incident_events_type ON incident_events(event_type);

-- 9. Canonical Operational Alerts
CREATE TABLE IF NOT EXISTS alerts_v2 (
    alert_id TEXT PRIMARY KEY,
    incident_id TEXT,
    observation_id TEXT,
    rule_id TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    priority TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    evidence_json TEXT,
    metadata_json TEXT,
    created_at_utc TEXT NOT NULL,
    acknowledged_at_utc TEXT,
    resolved_at_utc TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id) ON DELETE SET NULL,
    FOREIGN KEY (observation_id) REFERENCES observations(observation_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_v2_dedupe ON alerts_v2(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_alerts_v2_state ON alerts_v2(state);
CREATE INDEX IF NOT EXISTS idx_alerts_v2_priority ON alerts_v2(priority);
CREATE INDEX IF NOT EXISTS idx_alerts_v2_incident ON alerts_v2(incident_id);
CREATE INDEX IF NOT EXISTS idx_alerts_v2_created ON alerts_v2(created_at_utc);
