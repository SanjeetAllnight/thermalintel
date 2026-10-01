"""Thermal anomaly ingestion module for NASA FIRMS, caching, and normalization."""

from services.api.ingestion.config import IngestionConfig, config
from services.api.ingestion.cache import DataCache, cache
from services.api.ingestion.normalizer import HotspotNormalizer, compute_baseline_risk
from services.api.ingestion.firms import FirmsClient, firms_client

__all__ = [
    "IngestionConfig",
    "config",
    "DataCache",
    "cache",
    "HotspotNormalizer",
    "compute_baseline_risk",
    "FirmsClient",
    "firms_client",
]
