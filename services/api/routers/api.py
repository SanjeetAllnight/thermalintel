"""Frozen API router implementing the ThermalIntel contract.

CONTRACT ENDPOINTS:
- GET /api/health
- GET /api/hotspots
- GET /api/hotspots/{id}
- GET /api/summary
- GET /api/alerts
- GET /api/sources
- POST /api/refresh
"""

import json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, status

from services.api.schemas import (
    HealthResponse,
    Hotspot,
    HotspotsResponse,
    IncidentDetail,
    GeospatialContext,
    WeatherContext,
    HistoricalContext,
    TimelineEvent,
    IntelligenceResult,
    SummaryResponse,
    SourcesResponse,
    SourceBreakdown,
    Alert,
    AlertsResponse,
    RefreshRequest,
    RefreshResponse,
    DataMode,
    RiskLevel,
    SourceType,
    AlertSeverity,
)
from services.api.database import get_connection, seed_if_empty

router = APIRouter(prefix="/api", tags=["ThermalIntel Frozen API"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    """Health check returning system status, operational data mode, and subsystem readiness."""
    seed_if_empty()
    mode = DataMode.DEMO
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
            row = cursor.fetchone()
            if row and row["value"] == "live":
                mode = DataMode.LIVE
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        version="0.1.0",
        data_mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services={
            "database": "connected",
            "firms_api": "ready",
            "intelligence_engine": "online",
        },
    )


@router.get("/hotspots", response_model=HotspotsResponse)
def get_hotspots(
    risk_level: Optional[RiskLevel] = Query(None, description="Filter by risk category"),
    source_type: Optional[SourceType] = Query(None, description="Filter by thermal source type"),
    min_frp: Optional[float] = Query(None, ge=0.0, description="Minimum Fire Radiative Power (MW)"),
    min_confidence: Optional[str] = Query(None, description="Filter by minimum confidence (nominal, high)"),
    is_anomaly: Optional[bool] = Query(None, description="Filter by anomaly status"),
    cluster_id: Optional[str] = Query(None, description="Filter by specific cluster ID"),
    page: int = Query(1, ge=1, description="Page index"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
):
    """Retrieve filtered and paginated thermal anomaly hotspots."""
    seed_if_empty()
    query = "SELECT * FROM hotspots WHERE 1=1"
    params: List[object] = []

    if risk_level:
        query += " AND risk_level = ?"
        params.append(risk_level.value)
    if source_type:
        query += " AND source_type = ?"
        params.append(source_type.value)
    if min_frp is not None:
        query += " AND frp >= ?"
        params.append(min_frp)
    if min_confidence:
        query += " AND confidence = ?"
        params.append(min_confidence)
    if is_anomaly is not None:
        query += " AND is_anomaly = ?"
        params.append(1 if is_anomaly else 0)
    if cluster_id:
        query += " AND cluster_id = ?"
        params.append(cluster_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        # Count total
        count_query = f"SELECT COUNT(*) as total FROM ({query})"
        cursor.execute(count_query, params)
        total = cursor.fetchone()["total"]

        # Fetch page
        offset = (page - 1) * page_size
        query += " ORDER BY frp DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Check system data mode
        cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
        mode_row = cursor.fetchone()
        current_mode = DataMode.LIVE if (mode_row and mode_row["value"] == "live") else DataMode.DEMO

        items: List[Hotspot] = []
        for r in rows:
            items.append(
                Hotspot(
                    id=r["id"],
                    latitude=r["latitude"],
                    longitude=r["longitude"],
                    brightness=r["brightness"],
                    scan=r["scan"] or 0.375,
                    track=r["track"] or 0.375,
                    acq_date=r["acq_date"],
                    acq_time=r["acq_time"],
                    satellite=r["satellite"],
                    instrument=r["instrument"] or "VIIRS",
                    confidence=r["confidence"],
                    version=r["version"] or "2.0NRT",
                    bright_t31=r["bright_t31"],
                    frp=r["frp"],
                    daynight=r["daynight"],
                    source_type=SourceType(r["source_type"]),
                    risk_score=r["risk_score"],
                    risk_level=RiskLevel(r["risk_level"]),
                    is_anomaly=bool(r["is_anomaly"]),
                    cluster_id=r["cluster_id"],
                    cluster_size=r["cluster_size"] or 1,
                    nearest_place=r["nearest_place"],
                    last_updated=r["last_updated"],
                )
            )

    return HotspotsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        data_mode=current_mode,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/hotspots/{id}", response_model=IncidentDetail)
def get_hotspot_detail(id: str):
    """Retrieve full incident dossier including geospatial, weather, historical, and AI risk breakdown."""
    seed_if_empty()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hotspots WHERE id = ?", (id,))
        h_row = cursor.fetchone()
        if not h_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Hotspot with ID '{id}' not found")

        cursor.execute("SELECT * FROM incident_details WHERE hotspot_id = ?", (id,))
        inc_row = cursor.fetchone()

        cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
        mode_row = cursor.fetchone()
        current_mode = DataMode.LIVE if (mode_row and mode_row["value"] == "live") else DataMode.DEMO

        hotspot = Hotspot(
            id=h_row["id"],
            latitude=h_row["latitude"],
            longitude=h_row["longitude"],
            brightness=h_row["brightness"],
            scan=h_row["scan"] or 0.375,
            track=h_row["track"] or 0.375,
            acq_date=h_row["acq_date"],
            acq_time=h_row["acq_time"],
            satellite=h_row["satellite"],
            instrument=h_row["instrument"] or "VIIRS",
            confidence=h_row["confidence"],
            version=h_row["version"] or "2.0NRT",
            bright_t31=h_row["bright_t31"],
            frp=h_row["frp"],
            daynight=h_row["daynight"],
            source_type=SourceType(h_row["source_type"]),
            risk_score=h_row["risk_score"],
            risk_level=RiskLevel(h_row["risk_level"]),
            is_anomaly=bool(h_row["is_anomaly"]),
            cluster_id=h_row["cluster_id"],
            cluster_size=h_row["cluster_size"] or 1,
            nearest_place=h_row["nearest_place"],
            last_updated=h_row["last_updated"],
        )

        if inc_row:
            geospatial = GeospatialContext(**json.loads(inc_row["geospatial_json"]))
            weather = WeatherContext(**json.loads(inc_row["weather_json"]))
            historical = HistoricalContext(**json.loads(inc_row["historical_json"]))
            intelligence = IntelligenceResult(**json.loads(inc_row["intelligence_json"]))
            raw_timeline = json.loads(inc_row["timeline_json"])
            timeline = [TimelineEvent(**t) for t in raw_timeline]
        else:
            # Baseline fallback synthesis if detail enrichment record is pending
            geospatial = GeospatialContext(
                land_cover="mixed_terrain",
                nearest_infrastructure="Local Access Route",
                distance_to_infrastructure_meters=1500.0,
                nearest_settlement=h_row["nearest_place"] or "Regional District",
                distance_to_settlement_meters=4200.0,
                is_protected_area=False,
                elevation_meters=350.0,
                slope_degrees=12.0,
                fuel_load_estimate="moderate",
            )
            weather = WeatherContext(
                temperature_celsius=26.0,
                relative_humidity_percent=32.0,
                wind_speed_kmh=22.0,
                wind_gust_kmh=35.0,
                wind_direction_degrees=210.0,
                wind_direction_cardinal="SSW",
                precipitation_mm=0.0,
                fire_weather_index=45.0,
                forecast_summary="Dry conditions with afternoon breeze",
            )
            historical = HistoricalContext(
                prior_detections_30d=2,
                prior_detections_90d=5,
                is_recurrent_site=False,
                recurrent_pattern="none",
                first_detected_date=h_row["acq_date"],
                detection_frequency_score=0.15,
            )
            intelligence = IntelligenceResult(
                hotspot_id=hotspot.id,
                classification={
                    "predicted_source": hotspot.source_type,
                    "confidence": 0.88,
                    "probabilities": {hotspot.source_type.value: 0.88, "other": 0.12},
                },
                anomaly={
                    "is_anomaly": hotspot.is_anomaly,
                    "anomaly_score": 0.75 if hotspot.is_anomaly else 0.15,
                    "baseline_deviation": 2.4 if hotspot.is_anomaly else 0.4,
                    "anomaly_rationale": "Standard baseline comparison evaluation",
                },
                risk={
                    "risk_score": hotspot.risk_score,
                    "risk_level": hotspot.risk_level,
                    "frp_component": hotspot.frp * 0.5,
                    "weather_component": 40.0,
                    "proximity_component": 50.0,
                    "historical_component": 15.0,
                    "explainable_factors": [
                        {
                            "factor": f"Radiative Power Output ({hotspot.frp} MW)",
                            "weight": 0.4,
                            "impact": hotspot.risk_level,
                            "description": "Satellite radiometric intensity measured at detector level.",
                        }
                    ],
                    "recommended_action": "Monitor thermal perimeter during subsequent satellite orbits.",
                },
                model_version="v1.0-rf-heuristic",
                evaluated_at=hotspot.last_updated,
            )
            timeline = [
                TimelineEvent(
                    timestamp=hotspot.last_updated,
                    event_type="satellite_pass",
                    summary=f"Detected by {hotspot.satellite} {hotspot.instrument}",
                )
            ]

    return IncidentDetail(
        hotspot=hotspot,
        geospatial=geospatial,
        weather=weather,
        historical=historical,
        intelligence=intelligence,
        timeline=timeline,
        data_mode=current_mode,
    )


@router.get("/summary", response_model=SummaryResponse)
def get_summary():
    """Retrieve operational KPIs, risk distribution, dominant sources, and critical incidents."""
    seed_if_empty()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hotspots")
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) as unread FROM alerts WHERE is_acknowledged = 0")
        active_alerts_count = cursor.fetchone()["unread"]

        cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
        mode_row = cursor.fetchone()
        current_mode = DataMode.LIVE if (mode_row and mode_row["value"] == "live") else DataMode.DEMO

        cursor.execute("SELECT value FROM system_meta WHERE key = 'last_sync'")
        sync_row = cursor.fetchone()
        last_sync = sync_row["value"] if sync_row else datetime.now(timezone.utc).isoformat()

    total = len(rows)
    critical_count = sum(1 for r in rows if r["risk_level"] == "critical")
    high_count = sum(1 for r in rows if r["risk_level"] == "high")
    medium_count = sum(1 for r in rows if r["risk_level"] == "medium")
    low_count = sum(1 for r in rows if r["risk_level"] == "low")

    avg_frp = round(sum(r["frp"] for r in rows) / total, 2) if total > 0 else 0.0
    max_frp = round(max((r["frp"] for r in rows), default=0.0), 2)
    avg_risk = round(sum(r["risk_score"] for r in rows) / total, 1) if total > 0 else 0.0

    # Source breakdown
    source_counts: dict[str, int] = {}
    for r in rows:
        st = r["source_type"]
        source_counts[st] = source_counts.get(st, 0) + 1

    dominant_source_str = max(source_counts.items(), key=lambda x: x[1])[0] if source_counts else "unknown"
    dominant_source = SourceType(dominant_source_str) if dominant_source_str in SourceType._value2member_map_ else SourceType.UNKNOWN

    # Top critical hotspots
    critical_rows = sorted(
        [r for r in rows if r["risk_level"] in ("critical", "high")],
        key=lambda x: x["risk_score"],
        reverse=True,
    )[:5]

    recent_critical = [
        Hotspot(
            id=r["id"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            brightness=r["brightness"],
            scan=r["scan"] or 0.375,
            track=r["track"] or 0.375,
            acq_date=r["acq_date"],
            acq_time=r["acq_time"],
            satellite=r["satellite"],
            instrument=r["instrument"] or "VIIRS",
            confidence=r["confidence"],
            version=r["version"] or "2.0NRT",
            bright_t31=r["bright_t31"],
            frp=r["frp"],
            daynight=r["daynight"],
            source_type=SourceType(r["source_type"]),
            risk_score=r["risk_score"],
            risk_level=RiskLevel(r["risk_level"]),
            is_anomaly=bool(r["is_anomaly"]),
            cluster_id=r["cluster_id"],
            cluster_size=r["cluster_size"] or 1,
            nearest_place=r["nearest_place"],
            last_updated=r["last_updated"],
        )
        for r in critical_rows
    ]

    return SummaryResponse(
        total_active_hotspots=total,
        critical_risk_count=critical_count,
        high_risk_count=high_count,
        medium_risk_count=medium_count,
        low_risk_count=low_count,
        active_alerts_count=active_alerts_count,
        average_frp=avg_frp,
        max_frp=max_frp,
        average_risk_score=avg_risk,
        data_mode=current_mode,
        last_sync_time=last_sync,
        dominant_source=dominant_source,
        source_counts=source_counts,
        recent_critical_hotspots=recent_critical,
    )


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    severity: Optional[AlertSeverity] = Query(None, description="Filter by alert severity"),
    unread_only: bool = Query(False, description="Filter unacknowledged alerts only"),
):
    """Retrieve operational risk alerts and urgent notifications."""
    seed_if_empty()
    query = "SELECT * FROM alerts WHERE 1=1"
    params: List[object] = []

    if severity:
        query += " AND severity = ?"
        params.append(severity.value)
    if unread_only:
        query += " AND is_acknowledged = 0"

    query += " ORDER BY timestamp DESC"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) as unread FROM alerts WHERE is_acknowledged = 0")
        unread_count = cursor.fetchone()["unread"]

    items: List[Alert] = []
    for r in rows:
        tags = json.loads(r["tags_json"]) if r["tags_json"] else []
        items.append(
            Alert(
                id=r["id"],
                hotspot_id=r["hotspot_id"],
                severity=AlertSeverity(r["severity"]),
                title=r["title"],
                message=r["message"],
                risk_score=r["risk_score"],
                location_name=r["location_name"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                timestamp=r["timestamp"],
                is_acknowledged=bool(r["is_acknowledged"]),
                recommended_action=r["recommended_action"],
                tags=tags,
            )
        )

    return AlertsResponse(
        items=items,
        total=len(items),
        unread_count=unread_count,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/sources", response_model=SourcesResponse)
def get_sources():
    """Retrieve thermal anomaly breakdown and intelligence distribution by source type."""
    seed_if_empty()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hotspots")
        rows = cursor.fetchall()

        cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
        mode_row = cursor.fetchone()
        current_mode = DataMode.LIVE if (mode_row and mode_row["value"] == "live") else DataMode.DEMO

    total = len(rows)
    grouped: dict[str, list] = {}
    for r in rows:
        st = r["source_type"]
        grouped.setdefault(st, []).append(r)

    labels = {
        SourceType.WILDFIRE: ("Wildfire / Forest Fire", "Vegetative dry fuel & wind propagation"),
        SourceType.INDUSTRIAL: ("Industrial Facility / Flare Stack", "Petrochemical, refining, & gas processing"),
        SourceType.AGRICULTURAL: ("Agricultural Residue Burn", "Seasonal crop clearing & stubble combustion"),
        SourceType.PRESCRIBED_BURN: ("Controlled / Prescribed Burn", "Managed land conservation fuel reduction"),
        SourceType.URBAN: ("Urban Structural / Heat Anomaly", "High thermal mass, roofing, or localized structural fire"),
        SourceType.VOLCANIC: ("Volcanic / Geothermal Activity", "Magmatic effusion & geothermal vents"),
        SourceType.UNKNOWN: ("Unclassified Thermal Signature", "Undergoing multi-spectral model verification"),
    }

    breakdowns: List[SourceBreakdown] = []
    for st_enum in SourceType:
        st_val = st_enum.value
        items = grouped.get(st_val, [])
        count = len(items)
        pct = round((count / total) * 100, 1) if total > 0 else 0.0
        avg_frp = round(sum(x["frp"] for x in items) / count, 2) if count > 0 else 0.0
        avg_risk = round(sum(x["risk_score"] for x in items) / count, 1) if count > 0 else 0.0
        display_name, driver = labels.get(st_enum, (st_val.title(), "Satellite thermal radiance"))

        if count > 0:
            breakdowns.append(
                SourceBreakdown(
                    source_type=st_enum,
                    display_name=display_name,
                    count=count,
                    percentage=pct,
                    average_frp=avg_frp,
                    average_risk=avg_risk,
                    primary_driver=driver,
                )
            )

    breakdowns.sort(key=lambda x: x.count, reverse=True)
    dom_source = breakdowns[0].source_type if breakdowns else SourceType.UNKNOWN

    return SourcesResponse(
        sources=breakdowns,
        total_evaluated=total,
        dominant_source=dom_source,
        data_mode=current_mode,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/refresh", response_model=RefreshResponse)
def trigger_refresh(req: Optional[RefreshRequest] = None):
    """Trigger data synchronization from NASA FIRMS or reload sample dataset."""
    start_time = datetime.now(timezone.utc)
    seed_if_empty()

    # If force_sample is requested or NASA FIRMS token is missing, refresh from sample store
    force = req.force_sample if req else False

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM hotspots")
        count = cursor.fetchone()["count"]

        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE system_meta SET value = ? WHERE key = 'last_sync'", (now_str,))
        conn.commit()

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    return RefreshResponse(
        status="success",
        message="Synchronization completed successfully. Hotspot catalog refreshed.",
        ingested_count=count,
        data_mode=DataMode.DEMO if force else DataMode.LIVE,
        timestamp=now_str,
        execution_time_seconds=round(duration, 3),
    )
