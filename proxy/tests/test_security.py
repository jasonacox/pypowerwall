"""Security regression tests for proxy/server.py.

Covers the P1 hardening fixes:
- DISABLED/ALLOWLIST matching ignores query strings (no ?x=1 bypass)
- Unallowlisted /api/ paths are never proxied to the gateway with auth
- /help escapes attacker-controlled request paths (stored XSS)
- /control POST body size is capped
- GET /control/max_backup auto-cancel (a write) requires a valid token
- Control token compare (now constant-time) accepts/rejects correctly
"""
import json
import unittest
from http import HTTPStatus
from io import BytesIO
from unittest.mock import Mock, patch

from proxy.tests.test_csv_endpoints import BaseDoGetTest, UnittestHandler, common_patches


SECRET = "test-secret"


def _passthrough_safe_pw_call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class TestQueryStringBypass(BaseDoGetTest):
    """DISABLED and ALLOWLIST must match on the path only, not path+query."""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_disabled_path_blocked(self, _proxystats_lock, mock_safe_pw_call, mock_pw):
        """Baseline: a DISABLED path without query string is blocked."""
        self.handler.path = "/api/customer/registration"
        self.handler.do_GET()
        self.assertIn("API Disabled", self.get_written_text())
        mock_safe_pw_call.assert_not_called()

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_disabled_path_with_query_string_blocked(self, _proxystats_lock, mock_safe_pw_call, mock_pw):
        """Regression: appending ?x=1 must not bypass the DISABLED list."""
        self.handler.path = "/api/customer/registration?x=1"
        self.handler.do_GET()
        self.assertIn("API Disabled", self.get_written_text())
        mock_safe_pw_call.assert_not_called()

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_allowlist_path_with_query_string_polls_path_only(self, _proxystats_lock, mock_safe_pw_call, mock_pw):
        """An allowlisted path with a query string polls the bare path."""
        mock_safe_pw_call.return_value = '{"din": "123"}'
        self.handler.path = "/api/status?x=1"
        self.handler.do_GET()
        mock_safe_pw_call.assert_called_once_with(mock_pw.poll, "/api/status", jsonformat=True)
        self.assertEqual(self.get_written_json(), {"din": "123"})


class TestGatewayPassthroughBlocked(BaseDoGetTest):
    """Unmatched /api/ paths must never be proxied to the gateway with auth."""

    @common_patches
    @patch('proxy.server.pw')
    def test_unallowlisted_api_path_not_proxied(self, _proxystats_lock, mock_pw):
        """An /api/ path not in ALLOWLIST returns Not Found, no gateway call."""
        mock_pw.cloudmode = False
        mock_pw.fleetapi = False
        mock_pw.authmode = "token"
        self.handler.path = "/api/config"
        self.handler.do_GET()
        written = self.get_written_text()
        self.assertIn("Not Found", written)
        mock_pw.client.session.get.assert_not_called()

    @common_patches
    @patch('proxy.server.pw')
    def test_unallowlisted_api_path_with_query_not_proxied(self, _proxystats_lock, mock_pw):
        """Query strings do not smuggle /api/ paths past the block."""
        mock_pw.cloudmode = False
        mock_pw.fleetapi = False
        mock_pw.authmode = "token"
        self.handler.path = "/api/config?x=1"
        self.handler.do_GET()
        self.assertIn("Not Found", self.get_written_text())
        mock_pw.client.session.get.assert_not_called()

    @common_patches
    @patch('proxy.server.pw')
    def test_non_api_path_still_passes_through(self, _proxystats_lock, mock_pw):
        """Web app assets (non-/api/ paths) keep the gateway passthrough."""
        mock_pw.cloudmode = False
        mock_pw.fleetapi = False
        mock_pw.authmode = "token"
        response = Mock()
        response.content = b"asset-bytes"
        response.headers = {"content-type": "application/javascript"}
        mock_pw.client.session.get.return_value = response
        self.handler.path = "/some_web_asset.js"
        self.handler.do_GET()
        mock_pw.client.session.get.assert_called_once()
        self.assertIn("asset-bytes", self.get_written_text())


class TestHelpEscaping(BaseDoGetTest):
    """/help must html-escape attacker-controlled URI stats (stored XSS)."""

    @patch('proxy.server.api_base_url', '')
    @patch('proxy.server.proxystats', {
        'gets': 0, 'posts': 0, 'errors': 0, 'timeout': 0, 'start': 1000,
        'clear': 0, 'uri': {'/api/status?<script>alert(1)</script>': 1},
        'config': {'PW_HOST': '<img src=x onerror=alert(2)>'},
    })
    @patch('proxy.server.proxystats_lock')
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call', return_value=None)
    def test_help_escapes_malicious_uri(self, _mock_safe, mock_pw, _lock):
        mock_pw.cloudmode = False
        mock_pw.fleetapi = False
        mock_pw.authmode = "cookie"
        self.handler.path = "/help"
        self.handler.do_GET()
        written = self.get_written_text()
        self.assertNotIn("<script>alert(1)</script>", written)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", written)
        self.assertNotIn("<img src=x onerror=alert(2)>", written)


class BaseDoPostTest(unittest.TestCase):
    def setUp(self):
        self.handler = UnittestHandler()
        self.handler.command = "POST"

    def _post(self, path, body, content_length=None):
        self.handler.path = path
        self.handler.rfile = BytesIO(body)
        length = content_length if content_length is not None else len(body)
        self.handler.headers = {"Content-Length": str(length)}
        self.handler.do_POST()

    def _response_body(self):
        return self.handler.wfile.getvalue().decode("utf-8")


class TestPostBodyCap(BaseDoPostTest):
    """POST bodies over MAX_POST_BODY bytes are rejected with a 400 error."""

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_oversized_body_rejected(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        mock_pw.tedapi = None
        body = b"value=50&token=" + SECRET.encode() + b"&pad=" + b"A" * 8192
        self._post("/control/reserve", body)
        self.handler.send_response.assert_called_with(HTTPStatus.BAD_REQUEST)
        self.assertIn("error", json.loads(self._response_body()))
        mock_pw_control.set_reserve.assert_not_called()

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_normal_body_accepted(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        mock_pw.tedapi = None
        mock_pw_control.client = Mock()
        mock_pw_control.set_reserve.return_value = {"set_reserve": "ok"}
        self._post("/control/reserve", f"value=50&token={SECRET}".encode())
        mock_pw_control.set_reserve.assert_called_once_with(50)
        self.handler.send_response.assert_called_with(HTTPStatus.OK)


class TestControlTokenCompare(BaseDoPostTest):
    """Constant-time token compare still accepts the correct token only."""

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_correct_token_accepted(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        mock_pw.tedapi = None
        mock_pw_control.client = Mock()
        mock_pw_control.set_mode.return_value = {"set_mode": "ok"}
        self._post("/control/mode", f"value=backup&token={SECRET}".encode())
        mock_pw_control.set_mode.assert_called_once_with("backup")
        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        self.assertEqual(json.loads(self._response_body()), {"set_mode": "ok"})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_wrong_token_rejected(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        mock_pw.tedapi = None
        mock_pw_control.client = Mock()
        self._post("/control/mode", b"value=backup&token=wrong-secret")
        mock_pw_control.set_mode.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.UNAUTHORIZED)
        self.assertIn("unauthorized", json.loads(self._response_body()))

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_missing_token_rejected(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        mock_pw.tedapi = None
        mock_pw_control.client = Mock()
        self._post("/control/mode", b"value=backup")
        mock_pw_control.set_mode.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.UNAUTHORIZED)


class TestMaxBackupGetAutoCancel(BaseDoGetTest):
    """GET /control/max_backup: auto-cancel (a write) needs a valid token."""

    def _setup_backup_events(self, mock_pw):
        mock_pw.tedapi = Mock()
        mock_pw.tedapi.v1r = True
        # Expired (inactive) event lingering on the gateway
        mock_pw.tedapi.get_backup_events.return_value = {
            "manual_backup": {"active": False, "duration": 3600}
        }

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_get_without_token_does_not_cancel(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        """Tokenless GET stays read-only: expired event reported, not cancelled."""
        self._setup_backup_events(mock_pw)
        self.handler.path = "/control/max_backup"
        self.handler.do_GET()
        mock_pw.tedapi.cancel_max_backup.assert_not_called()
        result = self.get_written_json()
        self.assertEqual(result["manual_backup"], {"active": False, "duration": 3600})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_get_with_invalid_token_does_not_cancel(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        self._setup_backup_events(mock_pw)
        self.handler.path = "/control/max_backup?token=wrong-secret"
        self.handler.do_GET()
        mock_pw.tedapi.cancel_max_backup.assert_not_called()
        result = self.get_written_json()
        self.assertEqual(result["manual_backup"], {"active": False, "duration": 3600})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_get_with_valid_token_cancels(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        """Valid ?token= cancels the expired event and nulls it in the output."""
        self._setup_backup_events(mock_pw)
        self.handler.path = f"/control/max_backup?token={SECRET}"
        self.handler.do_GET()
        mock_pw.tedapi.cancel_max_backup.assert_called_once()
        result = self.get_written_json()
        self.assertIsNone(result["manual_backup"])

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_get_active_event_not_cancelled(self, _proxystats_lock, _mock_safe, mock_pw_control, mock_pw):
        """An active event is never auto-cancelled, token or not."""
        mock_pw.tedapi = Mock()
        mock_pw.tedapi.v1r = True
        mock_pw.tedapi.get_backup_events.return_value = {
            "manual_backup": {"active": True, "duration": 3600}
        }
        self.handler.path = f"/control/max_backup?token={SECRET}"
        self.handler.do_GET()
        mock_pw.tedapi.cancel_max_backup.assert_not_called()
        result = self.get_written_json()
        self.assertEqual(result["manual_backup"], {"active": True, "duration": 3600})


if __name__ == "__main__":
    unittest.main()
