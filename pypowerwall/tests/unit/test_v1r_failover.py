"""Unit tests for v1r LAN-down failover behavior.

Covers the fail-fast / failover paths for TEDAPI v1r mode with a WiFi
fallback host configured:

  1. Session retry policy: v1r, primary TEDAPI and WiFi sessions mount
     fail-fast adapters (total=1) so a dead host fails in ~2x timeout
     instead of wedging API-lock holders for 4-6x timeout.
  2. Cold-start failover: TEDAPI._connect_v1r() falls back to WiFi TEDAPI
     when the LAN login fails at connect time (DIN adopted over WiFi,
     lan_failed entered immediately) instead of returning None.
  3. Recovery probe: _post_tedapi() keeps routing via WiFi (not 'resumed')
     when the recovery reconnect comes back over the fallback path.
"""
import logging
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from pypowerwall.tedapi import TEDAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tedapi():
    """Build a TEDAPI instance with all network I/O mocked out."""
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value='TEST_DIN'):
        ted = TEDAPI(gw_pwd='testpassword')
    ted.gw_ip = '10.42.1.1'
    ted.v1r = True
    return ted


def _din_response(din='WIFI_DIN'):
    """Fake requests.Response for GET /tedapi/din."""
    resp = MagicMock()
    resp.status_code = HTTPStatus.OK
    resp.content = din.encode('utf-8')
    return resp


# ---------------------------------------------------------------------------
# Tests: fail-fast session retry policy
# ---------------------------------------------------------------------------

class TestFailfastRetryPolicy:
    """Dead hosts must fail fast so API-lock holders are released quickly."""

    def test_v1r_session_uses_single_retry(self):
        from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r
        transport = TEDAPIv1r.__new__(TEDAPIv1r)
        transport.poolmaxsize = 10
        session = transport._init_session()
        adapter = session.get_adapter('https://example.com')
        assert adapter.max_retries.total == 1

    def test_primary_session_uses_single_retry(self):
        ted = _make_tedapi()
        session = ted._init_session()
        adapter = session.get_adapter('https://example.com')
        assert adapter.max_retries.total == 1

    def test_wifi_session_uses_single_retry(self):
        ted = _make_tedapi()
        ted.wifi_host = '192.168.1.39'
        ted._init_wifi_session('testpassword')
        adapter = ted.wifi_session.get_adapter('https://example.com')
        assert adapter.max_retries.total == 1


# ---------------------------------------------------------------------------
# Tests: TEDAPI._connect_v1r() — cold-start failover
# ---------------------------------------------------------------------------

class TestConnectV1rColdFailover:
    """_connect_v1r() serves WiFi immediately when LAN is down at connect."""

    def test_cold_failover_adopts_wifi_din(self, caplog):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        ted.wifi_session.get.return_value = _din_response()
        ted.wifi_host = '192.168.1.39'

        with caplog.at_level(logging.WARNING):
            result = ted._connect_v1r()

        assert result == 'WIFI_DIN'
        assert ted.din == 'WIFI_DIN'
        assert ted.lan_failed is True
        assert ted.lan_fail_count == 3
        assert ted.lan_recover_after > 0
        assert ted.wifi_available is True
        assert any('fallback' in r.message for r in caplog.records)

    def test_no_wifi_session_returns_none(self):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = None

        assert ted._connect_v1r() is None
        assert ted.lan_failed is False

    def test_dead_wifi_returns_none(self):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        ted.wifi_session.get.side_effect = TimeoutError('timed out')
        ted.wifi_host = '192.168.1.39'

        assert ted._connect_v1r() is None
        assert ted.lan_failed is False

    def test_cold_failover_on_din_failure(self):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = True
        mock_transport.get_din.return_value = None
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        ted.wifi_session.get.return_value = _din_response()
        ted.wifi_host = '192.168.1.39'

        assert ted._connect_v1r() == 'WIFI_DIN'
        assert ted.lan_failed is True

    def test_cold_failover_on_exception(self, caplog):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.side_effect = ConnectionError('gone')
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        ted.wifi_session.get.return_value = _din_response()
        ted.wifi_host = '192.168.1.39'

        import logging
        with caplog.at_level(logging.ERROR):
            assert ted._connect_v1r() == 'WIFI_DIN'
        assert ted.lan_failed is True

    def test_cold_failover_non_ok_status_returns_none(self):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        resp = MagicMock()
        resp.status_code = HTTPStatus.FORBIDDEN
        ted.wifi_session.get.return_value = resp
        ted.wifi_host = '192.168.1.39'

        assert ted._connect_v1r() is None
        assert ted.lan_failed is False

    def test_cold_failover_decode_error_returns_none(self):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        resp = MagicMock()
        resp.status_code = HTTPStatus.OK
        resp.content = b'\xff\xfe\x00bad'
        ted.wifi_session.get.return_value = resp
        ted.wifi_host = '192.168.1.39'

        assert ted._connect_v1r() is None
        assert ted.lan_failed is False

    def test_cold_failover_empty_din_returns_none(self):
        ted = _make_tedapi()
        mock_transport = MagicMock()
        mock_transport.login.return_value = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = MagicMock()
        ted.wifi_session.get.return_value = _din_response('   ')
        ted.wifi_host = '192.168.1.39'

        assert ted._connect_v1r() is None
        assert ted.lan_failed is False

    def test_lan_success_still_clears_state(self):
        ted = _make_tedapi()
        ted.lan_failed = True
        ted.lan_fail_count = 3
        mock_transport = MagicMock()
        mock_transport.login.return_value = True
        mock_transport.get_din.return_value = 'LAN_DIN'
        mock_transport.get_config_v1r.return_value = {'vin': 'GW--123'}
        mock_transport.pending_verification = False
        ted.v1r_transport = mock_transport
        ted.wifi_session = None

        assert ted._connect_v1r() == 'LAN_DIN'
        assert ted.lan_failed is False
        assert ted.lan_fail_count == 0


# ---------------------------------------------------------------------------
# Tests: _post_tedapi() recovery probe over fallback
# ---------------------------------------------------------------------------

class TestRecoveryProbeOverFallback:
    """A recovery reconnect served over WiFi must not claim LAN 'resumed'."""

    def test_recovery_over_wifi_routes_via_wifi(self, caplog):
        ted = _make_tedapi()
        ted.lan_failed = True
        ted.lan_recover_after = 0  # recovery window reached
        ted.wifi_session = MagicMock()
        ted.wifi_host = '192.168.1.39'
        with patch.object(
            TEDAPI, '_connect_v1r', return_value='WIFI_DIN',
        ), patch.object(
            TEDAPI, '_post_tedapi_wifi', return_value=None,
        ) as mock_wifi:
            # _connect_v1r mock leaves lan_failed set (cold-failover shape)
            with caplog.at_level(logging.INFO):
                assert ted._post_tedapi(b'pb', din='D') is None
        mock_wifi.assert_called_once()
        assert any(
            'continuing on WiFi' in r.message for r in caplog.records
        )
        assert not any(
            'resuming wired' in r.message for r in caplog.records
        )

    def test_recovery_lan_resumed_routes_via_lan(self, caplog):
        ted = _make_tedapi()
        ted.lan_failed = True
        ted.lan_recover_after = 0  # recovery window reached
        ted.din = 'LAN_DIN'
        mock_transport = MagicMock()
        mock_transport.post_v1r.return_value = b'envelope'
        ted.v1r_transport = mock_transport

        def fake_reconnect():
            ted.lan_failed = False
            ted.lan_fail_count = 0
            return 'LAN_DIN'

        with patch.object(
            TEDAPI, '_connect_v1r', side_effect=fake_reconnect,
        ), patch.object(
            TEDAPI, '_envelope_bytes', return_value=b'env',
        ), patch.object(
            TEDAPI, '_post_tedapi_wifi',
        ) as mock_wifi:
            with caplog.at_level(logging.INFO):
                assert ted._post_tedapi(b'pb', din='D') == b'envelope'
        mock_wifi.assert_not_called()
        mock_transport.post_v1r.assert_called_once_with(b'env', 'LAN_DIN')
        assert any(
            'resuming wired' in r.message for r in caplog.records
        )
