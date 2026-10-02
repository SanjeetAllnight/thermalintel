"""Tests for GeoJSONAssetStore local spatial index and static asset queries."""

from pathlib import Path
import pytest

from services.api.geospatial.asset_store import GeoJSONAssetStore
from services.api.geospatial.overpass import FeatureCategory


def test_asset_store_load_default_reference_assets():
    """Verify loading default reference static assets for demonstration regions."""
    store = GeoJSONAssetStore(auto_load=True)
    assert store.count() > 0

    # Verify presence of Sonoma, Houston, Fresno assets
    names = [f.name for f in store._features]
    assert any("Geysers" in n for n in names)
    assert any("Baytown" in n for n in names)
    assert any("Boggs Mountain" in n for n in names)


def test_asset_store_query_radius():
    """Test KD-Tree radius querying for nearby industrial and infrastructure assets."""
    store = GeoJSONAssetStore(auto_load=True)

    # Query near The Geysers plant: (38.7421, -122.8105) with 2000m radius
    results = store.query_radius(38.7421, -122.8105, radius_meters=2000.0)
    assert len(results) >= 2

    # Category filtered query
    ind_results = store.query_radius(
        38.7421, -122.8105, radius_meters=2000.0,
        categories=[FeatureCategory.INDUSTRIAL.value]
    )
    assert len(ind_results) >= 1
    assert ind_results[0].category == FeatureCategory.INDUSTRIAL


def test_asset_store_query_bbox():
    """Test bounding box filtering across regions."""
    store = GeoJSONAssetStore(auto_load=True)

    # Sonoma County bounding box
    sonoma_feats = store.query_bbox(south=38.70, west=-122.90, north=38.80, east=-122.60)
    assert len(sonoma_feats) >= 3

    # Houston area bounding box
    houston_feats = store.query_bbox(south=29.60, west=-95.30, north=29.80, east=-94.90)
    assert len(houston_feats) >= 2


def test_asset_store_find_nearest():
    """Test finding nearest feature and distance computation."""
    store = GeoJSONAssetStore(auto_load=True)

    # Nearest industrial facility to The Geysers hotspot (38.7421, -122.8105)
    nearest = store.find_nearest(38.7421, -122.8105, category=FeatureCategory.INDUSTRIAL.value)
    assert nearest is not None
    feat, dist = nearest
    assert "Geysers" in feat.name
    assert dist < 300.0


def test_asset_store_check_protected_area_polygon():
    """Real polygon containment check for Boggs Mountain State Forest."""
    store = GeoJSONAssetStore(auto_load=True)

    # Point inside polygon: (38.7400, -122.8150)
    is_inside, name, geom_status = store.check_protected_area(38.7400, -122.8150)
    assert is_inside is True
    assert "Boggs Mountain" in (name or "")
    assert geom_status == "verified_polygon"

    # Point outside polygon: (38.7000, -122.8000)
    is_out, out_name, out_status = store.check_protected_area(38.7000, -122.8000)
    assert is_out is False
    assert out_status == "none"
