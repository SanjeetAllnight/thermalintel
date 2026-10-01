"""Normalization engine for satellite thermal anomaly records.

Converts raw NASA FIRMS CSV/dict responses into validated, frozen Hotspot Pydantic models.
"""

import csv
import io
import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.api.schemas import Hotspot, RiskLevel, SourceType

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
    # FRP is the primary physical radiometric indicator of fire intensity
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
    """Normalizes raw satellite records into validated Hotspot models."""

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
        # Check numeric confidence (MODIS standard 0-100)
        try:
            num = float(val)
            if num >= 80.0:
                return "high"
            if num >= 30.0:
                return "nominal"
            return "low"
        except ValueError:
            return val

    @staticmethod
    def normalize_acq_time(raw_time: Optional[Any]) -> str:
        """Format acquisition time as standard 4-digit HHMM."""
        if not raw_time:
            return "0000"
        s = re.sub(r"\D", "", str(raw_time))
        return s.zfill(4)[:4]

    @staticmethod
    def normalize_daynight(raw_dn: Optional[Any], acq_time: str) -> str:
        """Normalize day/night flag to 'D' or 'N'."""
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
    ) -> str:
        """Generate a deterministic, human-readable unique identifier."""
        sat_code = satellite.replace(" ", "").replace("-", "").upper()
        date_code = acq_date.replace("-", "")
        if sequence is not None:
            return f"{instrument}-{sat_code}-{date_code}-{sequence:04d}"
        
        # Unique coordinate digest
        coord_key = f"{lat:.4f}_{lon:.4f}_{acq_time}"
        import hashlib
        short_hash = hashlib.md5(coord_key.encode("utf-8")).hexdigest()[:6].upper()
        return f"{instrument}-{sat_code}-{date_code}-{short_hash}"

    @classmethod
    def normalize_row(cls, row: Dict[str, Any], sequence: Optional[int] = None) -> Optional[Hotspot]:
        """Convert a single raw dictionary / CSV row to a Hotspot model.
        
        Returns:
            Validated Hotspot or None if record is invalid/corrupt.
        """
        try:
            # Case-insensitive column resolution
            ci_row = {k.strip().lower(): v for k, v in row.items() if k is not None}

            # 1. Coordinates validation
            lat_str = ci_row.get("latitude") or ci_row.get("lat")
            lon_str = ci_row.get("longitude") or ci_row.get("lon")
            if lat_str is None or lon_str is None:
                logger.debug("Row missing latitude or longitude.")
                return None

            lat = float(lat_str)
            lon = float(lon_str)
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                logger.warning(f"Coordinates out of bounds: lat={lat}, lon={lon}")
                return None

            # 2. Brightness
            bright_str = ci_row.get("bright_ti4") or ci_row.get("brightness") or ci_row.get("bright_k")
            if bright_str is None:
                return None
            brightness = float(bright_str)
            if brightness <= 0.0 or brightness > 1000.0:
                logger.warning(f"Unrealistic brightness temperature: {brightness}")
                return None

            # 3. Fire Radiative Power (FRP)
            frp_str = ci_row.get("frp")
            frp = float(frp_str) if frp_str not in (None, "") else 0.0
            if frp < 0.0:
                frp = 0.0

            # 4. Dates and times
            acq_date = str(ci_row.get("acq_date") or "").strip()
            if not acq_date:
                acq_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            acq_time = cls.normalize_acq_time(ci_row.get("acq_time"))
            daynight = cls.normalize_daynight(ci_row.get("daynight"), acq_time)

            # 5. Satellite and Instrument
            satellite = cls.normalize_satellite_name(ci_row.get("satellite"))
            instrument = str(ci_row.get("instrument") or "").strip().upper()
            if not instrument:
                instrument = "MODIS" if satellite in ("Terra", "Aqua") else "VIIRS"

            # 6. Spatial resolution & confidence
            scan = float(ci_row.get("scan", 0.375) or 0.375)
            track = float(ci_row.get("track", 0.375) or 0.375)
            confidence = cls.normalize_confidence(ci_row.get("confidence"))
            version = str(ci_row.get("version") or "2.0NRT").strip()

            # 7. Brightness T31 / I-5
            bright_t31_raw = ci_row.get("bright_t31") or ci_row.get("bright_ti5")
            bright_t31 = float(bright_t31_raw) if bright_t31_raw not in (None, "") else None

            # 8. Identifier
            existing_id = ci_row.get("id")
            hotspot_id = str(existing_id) if existing_id else cls.generate_id(
                instrument=instrument,
                satellite=satellite,
                acq_date=acq_date,
                acq_time=acq_time,
                lat=lat,
                lon=lon,
                sequence=sequence,
            )

            # 9. Intelligence / classification fields
            # If already provided in input (e.g. sample JSON), preserve them; else compute defaults
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
            last_updated = ci_row.get("last_updated") or datetime.now(timezone.utc).isoformat()

            return Hotspot(
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
        except Exception as e:
            logger.warning(f"Error normalizing hotspot row: {e}")
            return None

    @classmethod
    def normalize_csv(cls, csv_text: str) -> List[Hotspot]:
        """Parse raw CSV text returned by NASA FIRMS into Hotspot objects."""
        if not csv_text or not csv_text.strip():
            return []

        # Sanitize any unexpected non-CSV error messages (e.g. FIRMS error strings)
        lines = [line.strip() for line in csv_text.strip().splitlines() if line.strip()]
        if not lines:
            return []

        # Check if response is an error message rather than CSV
        header_candidate = lines[0].lower()
        if "invalid" in header_candidate or "error" in header_candidate or "html" in header_candidate:
            logger.warning(f"NASA FIRMS returned non-CSV text: {lines[0]}")
            return []

        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        hotspots: List[Hotspot] = []
        seen_ids = set()

        for idx, row in enumerate(reader, start=1):
            hotspot = cls.normalize_row(row, sequence=idx)
            if hotspot and hotspot.id not in seen_ids:
                seen_ids.add(hotspot.id)
                hotspots.append(hotspot)

        return hotspots

    @classmethod
    def normalize_records(cls, records: List[Dict[str, Any]]) -> List[Hotspot]:
        """Convert a list of dictionaries into Hotspot objects with deduplication."""
        hotspots: List[Hotspot] = []
        seen_ids = set()

        for idx, rec in enumerate(records, start=1):
            hotspot = cls.normalize_row(rec, sequence=idx)
            if hotspot and hotspot.id not in seen_ids:
                seen_ids.add(hotspot.id)
                hotspots.append(hotspot)

        return hotspots
