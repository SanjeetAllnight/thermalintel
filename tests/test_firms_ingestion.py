"""Unit tests for NASA FIRMS client ingestion."""

import unittest
from unittest.mock import MagicMock, patch
import httpx

from services.api.ingestion.config import IngestionConfig
from services.api.ingestion.firms import FirmsClient

SAMPLE_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,142.8,N
38.7468,-122.8052,346.1,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,296.2,118.2,N
"""


class TestFirmsClient(unittest.TestCase):
    def setUp(self):
        self.cfg_with_key = IngestionConfig(
            firms_map_key="test_api_key_123456",
            firms_base_url="https://firms.modaps.eosdis.nasa.gov/api",
            default_source="VIIRS_SNPP_NRT",
            default_area="USA_contiguous_and_Hawaii",
            default_days=1,
            timeout_seconds=5.0,
        )
        self.cfg_no_key = IngestionConfig(
            firms_map_key="",
            firms_base_url="https://firms.modaps.eosdis.nasa.gov/api",
        )

    def test_missing_api_key_returns_none(self):
        """When API key is missing, fetch_recent_csv must return None without making network calls."""
        client = FirmsClient(self.cfg_no_key)
        res = client.fetch_recent_csv()
        self.assertIsNone(res)

    def test_build_url_country_area(self):
        client = FirmsClient(self.cfg_with_key)
        url = client._build_url(source="VIIRS_SNPP_NRT", days=1, area="USA_contiguous_and_Hawaii")
        self.assertIn("country/csv/test_api_key_123456/VIIRS_SNPP_NRT/USA_contiguous_and_Hawaii/1", url)

    def test_build_url_bbox(self):
        client = FirmsClient(self.cfg_with_key)
        bbox = [-124.4, 32.5, -114.1, 42.0]
        url = client._build_url(source="VIIRS_SNPP_NRT", days=2, bbox=bbox)
        self.assertIn("area/csv/test_api_key_123456/VIIRS_SNPP_NRT/-124.4,32.5,-114.1,42.0/2", url)

    @patch("httpx.Client")
    def test_successful_fetch(self, mock_client_cls):
        """Test successful HTTP 200 response returning raw CSV."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_FIRMS_CSV

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        client = FirmsClient(self.cfg_with_key)
        csv_text = client.fetch_recent_csv()

        self.assertIsNotNone(csv_text)
        self.assertIn("bright_ti4", csv_text)
        self.assertIn("38.7421", csv_text)

    @patch("httpx.Client")
    def test_http_403_forbidden_handling(self, mock_client_cls):
        """HTTP error codes (e.g. 403 Forbidden) must return None without raising."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Invalid or expired MAP_KEY"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        client = FirmsClient(self.cfg_with_key)
        result = client.fetch_recent_csv()
        self.assertIsNone(result)

    @patch("httpx.Client")
    def test_timeout_handling(self, mock_client_cls):
        """Network timeouts must be caught and return None gracefully."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Read timed out")
        mock_client_cls.return_value = mock_client

        client = FirmsClient(self.cfg_with_key)
        result = client.fetch_recent_csv()
        self.assertIsNone(result)

    @patch("httpx.Client")
    def test_non_csv_error_response_handling(self, mock_client_cls):
        """FIRMS error text in body with 200 status code must be detected as failure."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Error: Invalid map key provided"

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        client = FirmsClient(self.cfg_with_key)
        result = client.fetch_recent_csv()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
