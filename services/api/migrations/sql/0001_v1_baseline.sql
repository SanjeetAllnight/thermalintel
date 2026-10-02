-- Migration 0001: V1 Baseline Schema
-- Establishes the initial V1 tables for backward compatibility.

CREATE TABLE IF NOT EXISTS hotspots (
    id TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    brightness REAL NOT NULL,
    scan REAL DEFAULT 0.375,
    track REAL DEFAULT 0.375,
    acq_date TEXT NOT NULL,
    acq_time TEXT NOT NULL,
    satellite TEXT NOT NULL,
    instrument TEXT DEFAULT 'VIIRS',
    confidence TEXT NOT NULL,
    version TEXT DEFAULT '2.0NRT',
    bright_t31 REAL,
    frp REAL NOT NULL,
    daynight TEXT NOT NULL,
    source_type TEXT NOT NULL,
    risk_score REAL NOT NULL,
    risk_level TEXT NOT NULL,
    is_anomaly INTEGER DEFAULT 0,
    cluster_id TEXT,
    cluster_size INTEGER DEFAULT 1,
    nearest_place TEXT,
    last_updated TEXT NOT NULL,
    data_mode TEXT DEFAULT 'demo'
);

CREATE TABLE IF NOT EXISTS incident_details (
    hotspot_id TEXT PRIMARY KEY,
    geospatial_json TEXT NOT NULL,
    weather_json TEXT NOT NULL,
    historical_json TEXT NOT NULL,
    intelligence_json TEXT NOT NULL,
    timeline_json TEXT NOT NULL,
    FOREIGN KEY (hotspot_id) REFERENCES hotspots(id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    hotspot_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    risk_score REAL NOT NULL,
    location_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timestamp TEXT NOT NULL,
    is_acknowledged INTEGER DEFAULT 0,
    recommended_action TEXT NOT NULL,
    tags_json TEXT,
    FOREIGN KEY (hotspot_id) REFERENCES hotspots(id)
);

CREATE TABLE IF NOT EXISTS system_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
