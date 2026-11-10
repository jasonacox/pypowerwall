"""Native /api/status fallback for TEDAPI /api/status start_time / up_time_seconds (#418):

- SYNC_Uptime usable: values come from it, the native endpoint is not asked
- No usable SYNC_Uptime (a Backup Gateway 2 lists the signal with value None):
  both values are taken verbatim from the gateway's native /api/status
- Native endpoint unavailable or malformed: both stay None, as before
- TEDAPI.get_native_status() caches, backs off when unavailable, and serves the
  last good payload after a failed fetch
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI

# Shape observed on a Backup Gateway 2 (1118431-00-G), firmware 26.34.2
NATIVE_STATUS = {
    "din": "1118431-00-G--T17I0000000",
    "start_time": "2026-10-29 01:50:22 +0800",
    "up_time_seconds": "279h50m53.630302849s",
    "is_new": False,
    "version": "26.34.2 56d7ba06",
    "device_type": "hec",
    "sync_type": "v1",
}


def _make_backend(uptime=None, native=None):
    with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
        backend = PyPowerwallTEDAPI(gw_pwd='password')
    backend.tedapi.get_config.return_value = {'vin': 'GW--123', 'site_info': {}}
    backend.tedapi.get_firmware_version.return_value = {
        'system': {'version': {'text': '26.34.2 56d7ba06', 'githash': 'abc'}}}
    backend.tedapi.get_gateway_uptime.return_value = uptime
    backend.tedapi.get_native_status.return_value = native
    return backend


class TestApiStatusNativeFallback:

    def test_sync_uptime_used_when_available(self):
        start = datetime(2026, 10, 11, 11, 58, 1, tzinfo=timezone(timedelta(hours=-7)))
        backend = _make_backend(uptime={'uptime_ms': 1434584192, 'start_time': start,
                                        'gateway_time': start}, native=NATIVE_STATUS)
        data = backend.get_api_status()
        assert data['start_time'] == '2026-10-11 11:58:01 -0700'
        assert data['up_time_seconds'] == '398h29m44.192s'
        backend.tedapi.get_native_status.assert_not_called()

    def test_native_values_used_without_sync_uptime(self):
        backend = _make_backend(uptime=None, native=NATIVE_STATUS)
        data = backend.get_api_status()
        assert data['start_time'] == '2026-10-29 01:50:22 +0800'
        assert data['up_time_seconds'] == '279h50m53.630302849s'
        # Nothing else changes shape or value
        assert data['device_type'] is None
        assert data['sync_type'] == 'unknown'
        assert data['din'] == 'GW--123'

    def test_none_when_native_unavailable(self):
        backend = _make_backend(uptime=None, native=None)
        data = backend.get_api_status()
        assert data['start_time'] is None
        assert data['up_time_seconds'] is None


class TestGetNativeStatus:

    def _make_tedapi(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            return TEDAPI(gw_pwd='gateway-password')

    def test_caches_success(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value=NATIVE_STATUS) as mock_get:
            assert ted.get_native_status() == NATIVE_STATUS
            assert ted.get_native_status() == NATIVE_STATUS
            assert mock_get.call_count == 1
            mock_get.assert_called_with('/api/status')

    def test_unavailable_backs_off(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value=None) as mock_get:
            assert ted.get_native_status() is None
            assert ted._native_status_fail_until > time.time()
            assert ted.get_native_status() is None
            assert mock_get.call_count == 1

    def test_payload_without_uptime_is_unavailable(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value={'din': 'x', 'start_time': None}):
            assert ted.get_native_status() is None
            assert ted._native_status_fail_until > time.time()

    def test_non_string_values_are_unavailable(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value={'start_time': 12345, 'up_time_seconds': '1h0m0s'}):
            assert ted.get_native_status() is None
            assert ted._native_status_fail_until > time.time()

    def test_lock_contention_serves_cache_without_backoff(self):
        # A busy customer lock (e.g. an aggregates fetch in flight) is not an
        # unavailable endpoint: serve the cache and don't start the 300s backoff.
        ted = self._make_tedapi()
        ted.timeout = 0.01
        ted.pwcache['native_status'] = NATIVE_STATUS
        ted.pwcachetime['native_status'] = 0   # cache TTL elapsed
        holder = threading.Thread(target=ted._customer_lock.acquire)
        holder.start()
        holder.join()
        try:
            with patch.object(ted, 'get_native_api') as mock_get:
                assert ted.get_native_status() == NATIVE_STATUS
                mock_get.assert_not_called()
            assert ted._native_status_fail_until == 0.0
        finally:
            ted._customer_lock = threading.RLock()   # the holder thread exited holding the old one

    def test_refreshed_while_waiting_is_not_fetched_again(self):
        # Double-check after taking the lock: a thread that waited behind another
        # thread's refresh uses that result instead of fetching again.
        ted = self._make_tedapi()
        ted.pwcachetime['native_status'] = 0   # cache TTL elapsed

        def other_thread_refreshed(*args, **kwargs):
            ted.pwcache['native_status'] = NATIVE_STATUS
            ted.pwcachetime['native_status'] = time.time()
            return True

        with patch.object(ted, '_customer_lock') as lock, \
                patch.object(ted, 'get_native_api') as mock_get:
            lock.acquire.side_effect = other_thread_refreshed
            assert ted.get_native_status() == NATIVE_STATUS
            mock_get.assert_not_called()
            lock.release.assert_called_once()

    def test_backoff_separate_from_meters_aggregates(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_native_api', return_value=None):
            ted.get_native_status()
        assert ted._native_fail_until == 0.0
