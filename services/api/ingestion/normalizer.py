"""Normalization and validation engine for satellite thermal anomaly records.

Converts raw NASA FIRMS CSV/dict responses into validated, frozen Hotspot Pydantic models
and canonical V2 Observation models.
Enforces deterministic evidence-based IDs, strict coordinate boundaries, UTC timestamp
conformance, and forensic quarantine of malformed rows.
"""

import csv
import io
import math
import re
import logging
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.api.schemas import Hotspot, RiskLevel, SourceType
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.common import now_utc_iso
from services.api.ingestion.quarantine import QuarantineManager, quarantine_manager

logger = logging.getLogger(__name__)

# Satellite code to canonical display name
SATELLITE_MAP = {
    "N": "Suomi-NPP",
    "SNPP": "Suomi-NPP",
    "SUOMI-NPP": "Suomi-NPP",
    "1": "NOAA-20",
    "NOAA20": "NOAA-20",
    "NOAA-20": "NOAA-20",
    "JPSS-1": "NOAA-20",
    "2": "NOAA-21",
    "NOAA21": "NOAA-21",
    "NOAA-21": "NOAA-21",
    "JPSS-2": "NOAA-21",
    "T": "Terra",
    "TERRA": "Terra",
    "A": "Aqua",
    "AQUA": "Aqua",
}


def compute_baseline_risk(frp: float, brightness: float) -> Tuple[float, RiskLevel, bool]:
    """Compute initial heuristic baseline risk score and level prior to Phase 3 ML scoring."""
    if frp >= 100.0 or brightness >= 355.0:
        score = min(99.0, 75.0 + (frp - 100.0) * 0.15)
        level = RiskLevel.CRITICAL
        is_anomaly = True
    elif frp >= 50.0 or brightness >= 340.0:
        score = 60.0 + (frp - 50.0) * 0.3
        level = RiskLevel.HIGH
        is_anomaly = frp >= 80.0
    elif frp >= 20.0 or brightness >= 325.0:
        score = 35.0 + (frp - 20.0) * 0.8
        level = RiskLevel.MEDIUM
        is_anomaly = False
    else:
        score = max(5.0, frp * 1.5)
        level = RiskLevel.LOW
        is_anomaly = False

    return round(score, 1), level, is_anomaly


class HotspotNormalizer:
    """Normalizes raw satellite records into validated Hotspot and Observation models."""

    @staticmethod
    def normalize_satellite_name(raw_sat: Optional[str]) -> str:
        """Map raw satellite code/string to standard identifier."""
        if not raw_sat:
            return "Suomi-NPP"
        cleaned = str(raw_sat).strip().upper()
        return SATELLITE_MAP.get(cleaned, str(raw_sat).strip())

    @staticmethod
    def normalize_confidence(raw_conf: Optional[Any]) -> str:
        """Map raw confidence to 'low', 'nominal', 'high' or percentage string."""
        if raw_conf is None:
            return "nominal"
        val = str(raw_conf).strip().lower()
        if val in ("l", "low"):
            return "low"
        if val in ("n", "nominal", "med", "medium"):
            return "nominal"
        if val in ("h", "high"):
            return "high"

        # Check numeric confidence (MODIS standard 0-100 or percentage string like '85%')
        clean_num_str = val.rstrip("%").strip()
        try:
            num = float(clean_num_str)
            if math.isnan(num) or math.isinf(num):
                return "nominal"
            if num >= 80.0:
                return "high"
            if num >= 30.0:
                return "nominal"
            return "low"
        except ValueError:
            return val

    @staticmethod
    def normalize_acq_time(raw_time: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
        """Format acquisition time as standard 4-digit HHMM and validate hours and minutes.
        
        Returns:
            Tuple of (formatted_time_hhmm, error_message).
        """
        if raw_time is None or str(raw_time).strip() == "":
            return "0000", None

        s = re.sub(r"\D", "", str(raw_time)).strip()
        if not s:
            return None, f"Malformed acquisition time: '{raw_time}' contains no digits"

        padded = s.zfill(4)[:4]
        try:
            hour = int(padded[:2])
            minute = int(padded[2:])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None, f"Acquisition time out of bounds (HHMM): '{padded}'"
            return padded, None
        except ValueError:
            return None, f"Cannot parse acquisition time: '{raw_time}'"

    @staticmethod
    def normalize_acq_date(raw_date: Optional[Any]) -> Tuple[Optional[str], Optional[str]]:
        """Validate and format acquisition date as YYYY-MM-DD.
        
        Returns:
            Tuple of (formatted_date, error_message).
        """
        if not raw_date or not str(raw_date).strip():
            return datetime.now(timezone.utc).strftime("%Y-%m-%d"), None

        cleaned = str(raw_date).strip().replace("/", "-")
        # Validate format
        try:
            parsed = datetime.strptime(cleaned, "%Y-%m-%d")
            return parsed.strftime("%Y-%m-%d"), None
        except ValueError:
            return None, f"Invalid acquisition date format: '{raw_date}' (expected YYYY-MM-DD)"

    @staticmethod
    def normalize_daynight(raw_dn: Optional[Any], acq_time: str) -> str:
        """Normalize day/night flag strictly to 'D' or 'N'."""
        if raw_dn:
            val = str(raw_dn).strip().upper()
            if val in ("D", "DAY"):
                return "D"
            if val in ("N", "NIGHT"):
                return "N"
        # Infer roughly from UTC time if missing
        try:
            hour = int(acq_time[:2])
            return "D" if 6 <= hour <= 18 else "N"
        except Exception:
            return "N"

    @classmethod
    def generate_id(
        cls,
        instrument: str,
        satellite: str,
        acq_date: str,
        acq_time: str,
        lat: float,
        lon: float,
        sequence: Optional[int] = None,
        daynight: Optional[str] = None,
    ) -> str:
        """Generate a deterministic unique identifier.
        
        If sequence is provided (legacy test mode), generates sequence-based ID.
        Otherwise, generates an immutable evidence digest based on sensor, date, time,
        spatial coordinates, and solar cycle.
        """
        sat_code = satellite.replace(" ", "").replace("-", "").upper()
        date_code = acq_date.replace("-", "")
        if sequence is not None:
            return f"{instrument}-{sat_code}-{date_code}-{sequence:04d}"

        # Immutable evidence digest: sensor + platform + date + time + coordinates + daynight
        dn = (daynight or "N").upper()
        evidence = f"{instrument.upper()}|{sat_code}|{date_code}|{acq_time}|{lat:.5f}|{lon:.5f}|{dn}"
        evidence_hash = hashlib.sha256(evidence.encode("utf-8")).hexdigest()[:8].upper()
        return f"{instrument}-{sat_code}-{date_code}-{evidence_hash}"

    @classmethod
    def generate_observation_id(
        cls,
        instrument: str,
        satellite: str,
        acq_date: str,
        acq_time: str,
        lat: float,
        lon: float,
        daynight: str = "N",
    ) -> str:
        """Generate canonical V2 observation_id prefixed with 'OBS-'."""
        base_id = cls.generate_id(
            instrument=instrument,
            satellite=satellite,
            acq_date=acq_date,
            acq_time=acq_time,
            lat=lat,
            lon=lon,
            sequence=None,
            daynight=daynight,
        )
        return f"OBS-{base_id}"

    @classmethod
    def normalize_row_with_diagnostics(
        cls,
        row: Dict[str, Any],
        sequence: Optional[int] = None,
        provider: str = "NASA_FIRMS",
        product: str = "VIIRS_SNPP_NRT",
        raw_payload_id: Optional[str] = None,
    ) -> Tuple[Optional[Hotspot], Optional[Observation], Optional[str]]:
        """Validate and normalize a raw record into both V1 Hotspot and V2 Observation models.
        
        Returns:
            Tuple of (hotspot, observation, rejection_reason).
            If valid: rejection_reason is None.
            If invalid: hotspot and observation are None, rejection_reason contains explanation.
        """
        try:
            # Case-insensitive column resolution
            ci_row = {k.strip().lower(): v for k, v in row.items() if k is not None}

            # 1. Coordinates validation
            lat_str = ci_row.get("latitude") if ci_row.get("latitude") is not None else ci_row.get("lat")
            lon_str = ci_row.get("longitude") if ci_row.get("longitude") is not None else (
                ci_row.get("lon") if ci_row.get("lon") is not None else ci_row.get("lng")
            )
            if lat_str is None or lon_str is None or str(lat_str).strip() == "" or str(lon_str).strip() == "":
                return None, None, "Missing required coordinate: latitude or longitude absent"

            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except (ValueError, TypeError):
                return None, None, f"Malformed non-numeric coordinates: lat='{lat_str}', lon='{lon_str}'"

            if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
                return None, None, f"Malformed non-finite coordinates: lat={lat}, lon={lon}"

            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                return None, None, f"Coordinates out of bounds: lat={lat}, lon={lon} (expected [-90,90], [-180,180])"

            # 2. Brightness temperature validation (handles VIIRS bright_ti4 and MODIS brightness)
            bright_str = (
                ci_row.get("bright_ti4")
                if ci_row.get("bright_ti4") is not None
                else (
                    ci_row.get("brightness")
                    if ci_row.get("brightness") is not None
                    else ci_row.get("bright_k")
                )
            )
            if bright_str is None or str(bright_str).strip() == "":
                return None, None, "Missing required brightness temperature"

            try:
                brightness = float(bright_str)
            except (ValueError, TypeError):
                return None, None, f"Malformed non-numeric brightness: '{bright_str}'"

            if math.isnan(brightness) or math.isinf(brightness):
                return None, None, f"Malformed non-finite brightness: {brightness}"

            if brightness <= 0.0 or brightness > 1000.0:
                return None, None, f"Unrealistic brightness temperature: {brightness}K (expected (0, 1000])"

            # 3. Fire Radiative Power (FRP) validation
            frp_str = ci_row.get("frp") if ci_row.get("frp") is not None else ci_row.get("fire_radiative_power")
            if frp_str in (None, ""):
                frp = 0.0
            else:
                try:
                    frp = float(frp_str)
                except (ValueError, TypeError):
                    return None, None, f"Malformed non-numeric FRP: '{frp_str}'"
                if math.isnan(frp) or math.isinf(frp):
                    return None, None, f"Malformed non-finite FRP: {frp}"
                if frp < 0.0:
                    frp = 0.0

            # 4. Dates and times
            acq_date, date_err = cls.normalize_acq_date(ci_row.get("acq_date") or ci_row.get("date"))
            if date_err:
                return None, None, date_err

            acq_time, time_err = cls.normalize_acq_time(ci_row.get("acq_time") or ci_row.get("time"))
            if time_err:
                return None, None, time_err

            daynight = cls.normalize_daynight(ci_row.get("daynight") or ci_row.get("day_night"), acq_time)

            # Strict UTC timestamp conforming to frozen UTC standard
            hh = acq_time[:2]
            mm = acq_time[2:]
            acq_time_utc = f"{acq_date}T{hh}:{mm}:00Z"

            # 5. Satellite and Instrument resolution
            satellite = cls.normalize_satellite_name(ci_row.get("satellite") or ci_row.get("sat"))
            instrument = str(ci_row.get("instrument") or "").strip().upper()
            if not instrument:
                instrument = "MODIS" if satellite in ("Terra", "Aqua") else "VIIRS"

            # 6. Spatial resolution & confidence
            def _parse_pos_float(val: Any, default: float) -> float:
                try:
                    num = float(val)
                    return num if num > 0.0 and not math.isnan(num) and not math.isinf(num) else default
                except (ValueError, TypeError):
                    return default

            scan_default = 1.0 if instrument == "MODIS" else 0.375
            track_default = 1.0 if instrument == "MODIS" else 0.375
            scan = _parse_pos_float(ci_row.get("scan"), scan_default)
            track = _parse_pos_float(ci_row.get("track"), track_default)
            confidence = cls.normalize_confidence(ci_row.get("confidence") or ci_row.get("conf"))
            version = str(ci_row.get("version") or "2.0NRT").strip()

            # 7. Secondary Brightness (VIIRS bright_ti5 vs MODIS bright_t31)
            bright_t31_raw = (
                ci_row.get("bright_t31")
                if ci_row.get("bright_t31") is not None
                else (
                    ci_row.get("bright_ti5")
                    if ci_row.get("bright_ti5") is not None
                    else ci_row.get("bright_31")
                )
            )
            bright_t31 = None
            if bright_t31_raw not in (None, ""):
                try:
                    b31_candidate = float(bright_t31_raw)
                    if not math.isnan(b31_candidate) and not math.isinf(b31_candidate) and 0.0 < b31_candidate <= 1000.0:
                        bright_t31 = b31_candidate
                except (ValueError, TypeError):
                    bright_t31 = None

            # 8. Identifier generation
            existing_id = ci_row.get("id")
            hotspot_id = str(existing_id) if existing_id else cls.generate_id(
                instrument=instrument,
                satellite=satellite,
                acq_date=acq_date,
                acq_time=acq_time,
                lat=lat,
                lon=lon,
                sequence=sequence,
                daynight=daynight,
            )

            # Canonical V2 observation ID
            obs_id = f"OBS-{hotspot_id}" if not hotspot_id.startswith("OBS-") else hotspot_id

            # 9. Baseline heuristic intelligence fields for V1 backward compatibility
            risk_score_raw = ci_row.get("risk_score")
            risk_level_raw = ci_row.get("risk_level")
            is_anomaly_raw = ci_row.get("is_anomaly")
            source_type_raw = ci_row.get("source_type")

            if risk_score_raw is not None and risk_level_raw is not None:
                risk_score = float(risk_score_raw)
                risk_level = RiskLevel(risk_level_raw) if isinstance(risk_level_raw, str) else risk_level_raw
                is_anomaly = bool(is_anomaly_raw)
            else:
                risk_score, risk_level, is_anomaly = compute_baseline_risk(frp, brightness)

            source_type = SourceType(source_type_raw) if source_type_raw in SourceType._value2member_map_ else SourceType.UNKNOWN
            cluster_id = ci_row.get("cluster_id")
            cluster_size = int(ci_row.get("cluster_size", 1) or 1)
            nearest_place = ci_row.get("nearest_place")
            last_updated = ci_row.get("last_updated") or now_utc_iso()

            hotspot = Hotspot(
                id=hotspot_id,
                latitude=lat,
                longitude=lon,
                brightness=brightness,
                scan=scan,
                track=track,
                acq_date=acq_date,
                acq_time=acq_time,
                satellite=satellite,
                instrument=instrument,
                confidence=confidence,
                version=version,
                bright_t31=bright_t31,
                frp=frp,
                daynight=daynight,
                source_type=source_type,
                risk_score=risk_score,
                risk_level=risk_level,
                is_anomaly=is_anomaly,
                cluster_id=cluster_id,
                cluster_size=cluster_size,
                nearest_place=nearest_place,
                last_updated=last_updated,
            )

            observation = Observation(
                observation_id=obs_id,
                provider=provider,
                product=product,
                satellite=satellite,
                instrument=instrument,
                latitude=lat,
                longitude=lon,
                acquisition_time_utc=acq_time_utc,
                ingestion_time_utc=last_updated,
                brightness=brightness,
                bright_t31=bright_t31,
                frp=frp,
                scan=scan,
                track=track,
                daynight=daynight,
                detection_confidence=confidence,
                source_attributes={
                    "legacy_v1_id": hotspot_id,
                    "version": version,
                },
                raw_payload_id=raw_payload_id,
                schema_version="2.0",
            )

            return hotspot, observation, None

        except Exception as e:
            return None, None, f"Unexpected error during normalization: {e}"

    @classmethod
    def normalize_row(cls, row: Dict[str, Any], sequence: Optional[int] = None) -> Optional[Hotspot]:
        """Convert a single raw dictionary to a Hotspot model (V1 compatibility)."""
        hotspot, _, err = cls.normalize_row_with_diagnostics(row, sequence=sequence)
        if err:
            logger.warning(f"Error normalizing hotspot row: {err}")
        return hotspot

    @classmethod
    def normalize_csv_with_quarantine(
        cls,
        csv_text: str,
        provider: str = "NASA_FIRMS",
        product: str = "VIIRS_SNPP_NRT",
        run_id: Optional[str] = None,
        quarantine_mgr: Optional[QuarantineManager] = None,
        raw_payload_id: Optional[str] = None,
    ) -> Tuple[List[Observation], List[Hotspot], int]:
        """Parse raw CSV text into Observation and Hotspot models, quarantining invalid rows.
        
        Returns:
            Tuple of (observations, hotspots, quarantined_count).
        """
        if not csv_text or not csv_text.strip():
            return [], [], 0

        lines = [line.strip() for line in csv_text.strip().splitlines() if line.strip()]
        if not lines:
            return [], [], 0

        # Detect error responses returned with HTTP 200
        header_candidate = lines[0].lower()
        if "invalid" in header_candidate or "error" in header_candidate or "html" in header_candidate:
            logger.warning(f"NASA FIRMS returned non-CSV text: {lines[0]}")
            return [], [], 0

        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        observations: List[Observation] = []
        hotspots: List[Hotspot] = []
        quarantined_count = 0
        seen_obs_ids = set()
        qm = quarantine_mgr or quarantine_manager
        current_run = run_id or f"RUN-PARSE-{now_utc_iso()}"

        for row in reader:
            hotspot, observation, err = cls.normalize_row_with_diagnostics(
                row,
                sequence=None,  # Stable deterministic evidence-based IDs!
                provider=provider,
                product=product,
                raw_payload_id=raw_payload_id,
            )

            if err or not observation or not hotspot:
                quarantined_count += 1
                qm.quarantine(
                    provider=provider,
                    product=product,
                    run_id=current_run,
                    reason=err or "Unknown validation failure",
                    row=row,
                )
                continue

            if observation.observation_id not in seen_obs_ids:
                seen_obs_ids.add(observation.observation_id)
                observations.append(observation)
                hotspots.append(hotspot)

        return observations, hotspots, quarantined_count

    @classmethod
    def normalize_csv(cls, csv_text: str) -> List[Hotspot]:
        """Parse raw CSV text returned by NASA FIRMS into Hotspot objects."""
        _, hotspots, _ = cls.normalize_csv_with_quarantine(csv_text)
        return hotspots

    @classmethod
    def normalize_records(cls, records: List[Dict[str, Any]]) -> List[Hotspot]:
        """Convert a list of dictionaries into Hotspot objects with deduplication."""
        hotspots: List[Hotspot] = []
        seen_ids = set()

        for rec in records:
            hotspot = cls.normalize_row(rec, sequence=None)
            if hotspot and hotspot.id not in seen_ids:
                seen_ids.add(hotspot.id)
                hotspots.append(hotspot)

        return hotspots
