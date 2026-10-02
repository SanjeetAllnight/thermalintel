"""Tests for hardened NASA FIRMS client with retry, backoff, and telemetry."""

import unittest
from unittest.mock import MagicMock, patch, call
import httpx

from services.api.ingestion.config import IngestionConfig
from services.api.ingestion.firms import FirmsClient, FirmsFetchResult, parse_retry_after, compute_backoff
from services.api.schemas.v2.common import ProviderStatus

SAMPLE_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
38.7421,-122.8105,352.4,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,298.4,142.8,N
38.7468,-122.8052,346.1,0.38,0.36,2026-10-01,0845,N,h,2.0NRT,296.2,118.2,N
"""

EMPTY_FIRMS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
"""


class TestV2FirmsClient(unittest.TestCase):
    def setUp(self):
        self.secret_key = "super_secret_firms_token_999"
        self.cfg = IngestionConfig(
            firms_map_key=self.secret_key,
            firms_base_url="https://firms.modaps.eosdis.nasa.gov/api",
            default_source="VIIRS_SNPP_NRT",
            default_area="USA_contiguous_and_Hawaii",
            default_days=1,
            timeout_seconds=5.0,
        )
        self.client = FirmsClient(self.cfg)
        self.slept_delays = []

    def mock_sleep(self, delay: float):
        self.slept_delays.append(delay)

    # 1. Successful fetch
    @patch("httpx.Client")
    def test_firms_success_telemetry(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_FIRMS_CSV

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_resp
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.rows_received, 2)
        self.assertFalse(result.is_empty)
        self.assertIsNone(result.error_type)
        self.assertGreaterEqual(result.duration_ms, 0)
        self.assertEqual(result.attempts, 1)

        # Convert to ProviderRun
        run = self.client.to_provider_run(result)
        self.assertEqual(run.status, ProviderStatus.SUCCESS)
        self.assertEqual(run.rows_received, 2)
        self.assertNotIn(self.secret_key, str(run.request_metadata))

    # 2. Empty feed (valid response with 0 fire observations)
    @patch("httpx.Client")
    def test_firms_empty_successful_feed(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = EMPTY_FIRMS_CSV

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = mock_resp
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "empty")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.rows_received, 0)
        self.assertTrue(result.is_empty)
        self.assertIsNone(result.error_type)

        # Ensure ProviderRun is SUCCESS (not an outage)
        run = self.client.to_provider_run(result)
        self.assertEqual(run.status, ProviderStatus.SUCCESS)
        self.assertEqual(run.rows_received, 0)

    # 3. Timeout with retry
    @patch("httpx.Client")
    def test_firms_timeout_retry_and_exhaustion(self, mock_client_cls):
        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.side_effect = httpx.TimeoutException("Read timed out")
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(max_retries=2, sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.error_type, "Timeout")
        self.assertEqual(result.attempts, 3)  # Initial + 2 retries
        self.assertEqual(len(self.slept_delays), 2)

        run = self.client.to_provider_run(result)
        self.assertEqual(run.status, ProviderStatus.FAILED)
        self.assertEqual(run.error_type, "Timeout")

    # 4. HTTP 429 Rate Limiting with Retry-After header
    @patch("httpx.Client")
    def test_firms_429_rate_limiting_with_retry_after(self, mock_client_cls):
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "3"}
        resp_429.text = "Too Many Requests"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.text = SAMPLE_FIRMS_CSV

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.side_effect = [resp_429, resp_200]
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(max_retries=2, sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(self.slept_delays), 1)
        self.assertEqual(self.slept_delays[0], 3.0)  # Honored Retry-After

    # 5. HTTP 500 Transient Server Error with recovery
    @patch("httpx.Client")
    def test_firms_500_transient_error_retry(self, mock_client_cls):
        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.headers = {}
        resp_500.text = "Internal Server Error"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.text = SAMPLE_FIRMS_CSV

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.side_effect = [resp_500, resp_200]
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(max_retries=2, sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(self.slept_delays), 1)

    # 6. HTTP 401/403 Permanent Error (Never Retried)
    @patch("httpx.Client")
    def test_firms_403_permanent_auth_error_no_retry(self, mock_client_cls):
        resp_403 = MagicMock()
        resp_403.status_code = 403
        resp_403.text = f"Forbidden: {self.secret_key} is invalid"

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = resp_403
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(max_retries=3, sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "auth_failed")
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.attempts, 1)  # Did NOT retry
        self.assertEqual(len(self.slept_delays), 0)

        # Ensure secret is redacted
        self.assertNotIn(self.secret_key, result.error_message)

    # 7. Body-level "Invalid map key" with HTTP 200 (Permanent Error, Never Retried)
    @patch("httpx.Client")
    def test_firms_body_error_permanent_no_retry(self, mock_client_cls):
        resp_200_err = MagicMock()
        resp_200_err.status_code = 200
        resp_200_err.text = f"Error: Invalid map key {self.secret_key} provided"

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = resp_200_err
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(max_retries=3, sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "auth_failed")
        self.assertEqual(result.error_type, "AuthFailed")
        self.assertEqual(result.attempts, 1)  # Did NOT retry
        self.assertNotIn(self.secret_key, result.error_message)

    # 8. Malformed HTML / non-CSV response
    @patch("httpx.Client")
    def test_firms_malformed_html_error(self, mock_client_cls):
        resp_html = MagicMock()
        resp_html.status_code = 200
        resp_html.text = "<html><body>502 Bad Gateway from Proxy</body></html>"

        mock_http = MagicMock()
        mock_http.__enter__.return_value = mock_http
        mock_http.get.return_value = resp_html
        mock_client_cls.return_value = mock_http

        result = self.client.fetch_raw(max_retries=1, sleep_fn=self.mock_sleep)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_type, "ApiError")

    # 9. Key Redaction Security Verification
    def test_key_redaction_in_all_surfaces(self):
        masked = self.client._mask_key(f"Query failed with key={self.secret_key} at /csv/{self.secret_key}/area")
        self.assertNotIn(self.secret_key, masked)
        self.assertIn("***KEY***", masked)


if __name__ == "__main__":
    unittest.main()
