"""Standardized event names for ThermalIntel structured observability.

Ensures deterministic, machine-readable log queryability across all system components.
"""

from __future__ import annotations

from enum import Enum


class LogEvent(str, Enum):
    """Canonical event taxonomy for ThermalIntel operations."""

    # Application Lifecycle
    APPLICATION_START = "application_start"
    APPLICATION_READY = "application_ready"
    APPLICATION_SHUTDOWN = "application_shutdown"

    # HTTP & API
    HTTP_REQUEST_STARTED = "http_request_started"
    HTTP_REQUEST_COMPLETED = "http_request_completed"
    HTTP_REQUEST_FAILED = "http_request_failed"

    # Ingestion & Provider Telemetry
    PROVIDER_RUN_STARTED = "provider_run_started"
    PROVIDER_RUN_COMPLETED = "provider_run_completed"
    PROVIDER_RUN_FAILED = "provider_run_failed"
    RAW_PAYLOAD_STORED = "raw_payload_stored"
    OBSERVATION_BATCH_PROCESSED = "observation_batch_processed"
    OBSERVATION_QUARANTINED = "observation_quarantined"

    # Enrichment (OSM, Open-Meteo, Recurrence)
    ENRICHMENT_STARTED = "enrichment_started"
    ENRICHMENT_COMPLETED = "enrichment_completed"
    ENRICHMENT_FAILED = "enrichment_failed"
    ENRICHMENT_FALLBACK_USED = "enrichment_fallback_used"

    # Intelligence & Scoring
    ASSESSMENT_STARTED = "assessment_started"
    ASSESSMENT_COMPLETED = "assessment_completed"
    ASSESSMENT_FAILED = "assessment_failed"
    ANOMALY_DETECTED = "anomaly_detected"

    # Incident Lifecycle
    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_TRANSITIONED = "incident_transitioned"
    INCIDENT_CLOSED = "incident_closed"

    # Operational Alerts
    ALERT_GENERATED = "alert_generated"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    ALERT_RESOLVED = "alert_resolved"
    ALERT_SUPPRESSED = "alert_suppressed"

    # Scheduler & Refresh
    SCHEDULER_STARTED = "scheduler_started"
    SCHEDULER_STOPPED = "scheduler_stopped"
    SCHEDULER_TICK = "scheduler_tick"
    SCHEDULER_FAILED = "scheduler_failed"
    REFRESH_STARTED = "refresh_started"
    REFRESH_COMPLETED = "refresh_completed"
    REFRESH_FAILED = "refresh_failed"
    REFRESH_COALESCED = "refresh_coalesced"

    # Database & Migrations
    DATABASE_MIGRATION_STARTED = "database_migration_started"
    DATABASE_MIGRATION_COMPLETED = "database_migration_completed"
    DATABASE_MIGRATION_FAILED = "database_migration_failed"
    DATABASE_SEED_EXECUTED = "database_seed_executed"

    def __str__(self) -> str:
        return self.value
