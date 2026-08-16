"""Regression tests for the gateway local API energy accumulator merge (#221):

- get_api_meters_aggregates() merges lifetime energy_imported/energy_exported
  from the native /api/meters/aggregates payload and appends a provenance note
  to each merged section's disclaimer
- A missing/unavailable native endpoint leaves the synthesized 0 values and
  original disclaimers untouched
- TEDAPI.get_native_meters_aggregates() backs off for NATIVE_FAIL_RETRY seconds
  when the endpoint is unavailable, and caches successful fetches
"""
import time
from unittest.mock import patch

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI

VALID_NATIVE = {
    "site": {
        "instant_power": -51,
        "energy_exported": 1469391,
        "energy_imported": 4902666.25,
    },
    "battery": {
        "instant_power": 1455,
        "energy_exported": 4712126,
        "energy_imported": 4803385,
    },
    "load": {
        "instant_power": 1425,
        "energy_exported": 0,
        "energy_imported": 11679089,
    },
    "solar": {
        "instant_power": 0,
        "energy_exported": 8337073,
        "energy_imported": 0,
    },
}


class TestNativeEnergyMerge:
    """PyPowerwallTEDAPI.get_api_meters_aggregates() merge behavior."""

    def _make_backend(self):
        with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI') as mock_tedapi_class:
            backend = PyPowerwallTEDAPI(gw_pwd='password')
        backend.tedapi.pw3 = False
        backend.tedapi.current_power.return_value = 0
        backend.tedapi.get_config.return_value = {'vin': 'GW--123'}
        backend.tedapi.get_status.return_value = {
            'system': {'time': '2026-08-16T04:00:00Z'},
            'esCan': {'bus': {}},
        }
        return backend

    def test_merge_success_values_and_disclaimer(self):
        backend = self._make_backend()
        backend.tedapi.get_native_meters_aggregates.return_value = VALID_NATIVE

        data = backend.get_api_meters_aggregates()

        # Lifetime accumulators overlaid on every section
        assert data['site']['energy_imported'] == 4902666.25
        assert data['site']['energy_exported'] == 1469391
        assert data['load']['energy_imported'] == 11679089
        assert data['solar']['energy_exported'] == 8337073
        assert data['battery']['energy_exported'] == 4712126
        # Provenance note appended after the existing synthesized disclaimer
        assert data['site']['disclaimer'] == \
            "site: voltage/current from unknown; energy from gateway local API"
        assert data['load']['disclaimer'].endswith("; energy from gateway local API")
        assert data['solar']['disclaimer'].endswith("; energy from gateway local API")
        assert data['battery']['disclaimer'].endswith("; energy from gateway local API")

    def test_merge_partial_native_payload_untouched_sections(self):
        # Native payload only carrying some sections (e.g. gateway meter set)
        backend = self._make_backend()
        backend.tedapi.get_native_meters_aggregates.return_value = {
            "site": VALID_NATIVE["site"],
        }

        data = backend.get_api_meters_aggregates()

        assert data['site']['energy_imported'] == 4902666.25
        assert data['site']['disclaimer'].endswith("; energy from gateway local API")
        # Sections absent from the native payload keep synthesized 0s and
        # their original disclaimer - no provenance note added
        for section in ("battery", "load", "solar"):
            assert data[section]['energy_imported'] == 0
            assert data[section]['energy_exported'] == 0
            assert "energy from gateway local API" not in data[section]['disclaimer']

    def test_merge_ignores_non_numeric_energy_values(self):
        backend = self._make_backend()
        backend.tedapi.get_native_meters_aggregates.return_value = {
            "site": {
                "instant_power": -51,
                "energy_exported": None,
                "energy_imported": "n/a",
            },
        }

        data = backend.get_api_meters_aggregates()

        assert data['site']['energy_imported'] == 0
        assert data['site']['energy_exported'] == 0
        assert "energy from gateway local API" not in data['site']['disclaimer']

    def test_endpoint_unavailable_keeps_zeros(self):
        backend = self._make_backend()
        backend.tedapi.get_native_meters_aggregates.return_value = None

        data = backend.get_api_meters_aggregates()

        # Gateway without the native endpoint: values stay 0 exactly as before
        for section in ("site", "battery", "load", "solar"):
            assert data[section]['energy_imported'] == 0
            assert data[section]['energy_exported'] == 0
            assert "energy from gateway local API" not in data[section]['disclaimer']


class TestNativeMetersAggregatesBackoff:
    """TEDAPI.get_native_meters_aggregates() caching and backoff."""

    def _make_tedapi(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            ted = TEDAPI(gw_pwd='gateway-password')
        return ted

    def test_unavailable_endpoint_backs_off(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value=None) as mock_get:
            assert ted.get_native_meters_aggregates() is None
            assert mock_get.call_count == 1
            # Backoff window armed
            assert ted._native_fail_until > time.time()

            # Retries within the backoff window are suppressed entirely -
            # the gateway is not hammered on every poll
            assert ted.get_native_meters_aggregates() is None
            assert mock_get.call_count == 1

    def test_malformed_payload_triggers_backoff(self):
        ted = self._make_tedapi()
        # Missing the four required sections - treated as unavailable
        malformed = {"site": {"energy_imported": 123}}
        with patch.object(ted, 'get_native_api', return_value=malformed) as mock_get:
            assert ted.get_native_meters_aggregates() is None
            assert ted._native_fail_until > time.time()
            assert mock_get.call_count == 1

    def test_backoff_expiry_retries_endpoint(self):
        ted = self._make_tedapi()
        responses = [None, VALID_NATIVE]
        with patch.object(ted, 'get_native_api', side_effect=responses) as mock_get:
            assert ted.get_native_meters_aggregates() is None  # sets backoff
            # Simulate the NATIVE_FAIL_RETRY window elapsing
            ted._native_fail_until = time.time() - 1
            result = ted.get_native_meters_aggregates()
            assert result == VALID_NATIVE
            assert mock_get.call_count == 2

    def test_successful_fetch_is_cached(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value=VALID_NATIVE) as mock_get:
            first = ted.get_native_meters_aggregates()
            assert first == VALID_NATIVE
            assert mock_get.call_count == 1

            # Subsequent polls within the cache TTL reuse the fetch
            second = ted.get_native_meters_aggregates()
            assert second == VALID_NATIVE
            assert mock_get.call_count == 1

            # force=True bypasses the cache
            ted.get_native_meters_aggregates(force=True)
            assert mock_get.call_count == 2
