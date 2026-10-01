"""Configuration settings for NASA FIRMS ingestion and caching."""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class IngestionConfig:
    """Ingestion and NASA FIRMS configuration."""
    firms_map_key: str = os.getenv("FIRMS_MAP_KEY", "").strip()
    firms_base_url: str = os.getenv(
        "FIRMS_BASE_URL", "https://firms.modaps.eosdis.nasa.gov/api"
    ).rstrip("/")
    default_source: str = os.getenv("FIRMS_DEFAULT_SOURCE", "VIIRS_SNPP_NRT")
    default_area: str = os.getenv("FIRMS_DEFAULT_AREA", "USA_contiguous_and_Hawaii")
    default_days: int = int(os.getenv("FIRMS_DEFAULT_DAYS", "1"))
    timeout_seconds: float = float(os.getenv("FIRMS_TIMEOUT_SECONDS", "10.0"))
    
    # Cache settings
    cache_dir: Path = Path(os.getenv("CACHE_DIR", str(BASE_DIR / "data" / "cache")))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour
    
    # Sample fallback path
    sample_hotspots_path: Path = Path(
        os.getenv("SAMPLE_HOTSPOTS_PATH", str(BASE_DIR / "data" / "sample" / "sample_hotspots.json"))
    )

    @property
    def has_firms_key(self) -> bool:
        """Check if a valid FIRMS API key is configured."""
        return bool(self.firms_map_key and len(self.firms_map_key) >= 8)


# Default singleton instance
config = IngestionConfig()
