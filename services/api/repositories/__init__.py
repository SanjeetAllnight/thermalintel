"""Hotspot persistence repository module."""

from services.api.repositories.hotspot_repository import (
    HotspotRepository,
    hotspot_repo,
    row_to_hotspot,
)

__all__ = ["HotspotRepository", "hotspot_repo", "row_to_hotspot"]
