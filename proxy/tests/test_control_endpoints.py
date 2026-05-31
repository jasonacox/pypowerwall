"""Tests for /control/reserve and /control/mode POST handlers.

Covers the single-value (legacy) form and the optional companion-parameter
form (mode= on /control/reserve, level= on /control/mode) added to let a
caller update both reserve and mode in a single set_operation() invocation.
"""
import json
import unittest
from http import HTTPStatus
from io import BytesIO
from unittest.mock import Mock, patch

from proxy.tests.test_csv_endpoints import UnittestHandler, common_patches


SECRET = "test-secret"


def _encode(params):
    return "&".join(f"{k}={v}" for k, v in params.items()).encode("utf-8")


def _passthrough_safe_pw_call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class BaseDoPostTest(unittest.TestCase):
    def setUp(self):
        self.handler = UnittestHandler()
        self.handler.command = "POST"

    def _post(self, path, params):
        body = _encode(params)
        self.handler.path = path
        self.handler.rfile = BytesIO(body)
        self.handler.headers = {"Content-Length": str(len(body))}
        self.handler.do_POST()

    def _response_body(self):
        return self.handler.wfile.getvalue().decode("utf-8")

    def _make_pw_control(self, set_reserve=None, set_mode=None, set_operation=None):
        pw_control = Mock()
        pw_control.client = Mock()  # not None -> passes cloud-mode connectivity check
        pw_control.set_reserve.return_value = set_reserve if set_reserve is not None else {"set_reserve": "ok"}
        pw_control.set_mode.return_value = set_mode if set_mode is not None else {"set_mode": "ok"}
        pw_control.set_operation.return_value = set_operation if set_operation is not None else {"set_operation": "ok"}
        return pw_control


class TestControlReserve(BaseDoPostTest):
    """POST /control/reserve — single-value and combined-with-mode forms."""

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_value_only_calls_set_reserve(self, _proxystats_lock, mock_safe, mock_pw_control, mock_pw):
        """value= alone -> set_reserve(level), set_operation not called (legacy behaviour)."""
        pw_control = self._make_pw_control()
        mock_pw_control.client = pw_control.client
        mock_pw_control.set_reserve = pw_control.set_reserve
        mock_pw_control.set_operation = pw_control.set_operation
        mock_pw.tedapi = None

        self._post("/control/reserve", {"value": "50", "token": SECRET})

        pw_control.set_reserve.assert_called_once_with(50)
        pw_control.set_operation.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        self.assertEqual(json.loads(self._response_body()), {"set_reserve": "ok"})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_value_with_valid_mode_calls_set_operation(self, _proxystats_lock, mock_safe, mock_pw_control, mock_pw):
        """value= + valid mode= -> set_operation(level, mode), neither set_reserve nor set_mode."""
        pw_control = self._make_pw_control()
        mock_pw_control.client = pw_control.client
        mock_pw_control.set_reserve = pw_control.set_reserve
        mock_pw_control.set_mode = pw_control.set_mode
        mock_pw_control.set_operation = pw_control.set_operation
        mock_pw.tedapi = None

        self._post(
            "/control/reserve",
            {"value": "5", "mode": "self_consumption", "token": SECRET},
        )

        pw_control.set_operation.assert_called_once_with(5, "self_consumption")
        pw_control.set_reserve.assert_not_called()
        pw_control.set_mode.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        self.assertEqual(json.loads(self._response_body()), {"set_operation": "ok"})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_value_with_invalid_mode_returns_error(self, _proxystats_lock, mock_safe, mock_pw_control, mock_pw):
        """value= + invalid mode= -> 400 error, no Powerwall call (no silent fallback to set_reserve)."""
        pw_control = self._make_pw_control()
        mock_pw_control.client = pw_control.client
        mock_pw_control.set_reserve = pw_control.set_reserve
        mock_pw_control.set_operation = pw_control.set_operation
        mock_pw.tedapi = None

        self._post(
            "/control/reserve",
            {"value": "5", "mode": "garbage", "token": SECRET},
        )

        pw_control.set_reserve.assert_not_called()
        pw_control.set_operation.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.BAD_REQUEST)
        self.assertIn("error", json.loads(self._response_body()))


class TestControlMode(BaseDoPostTest):
    """POST /control/mode — single-value and combined-with-level forms."""

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_value_only_calls_set_mode(self, _proxystats_lock, mock_safe, mock_pw_control, mock_pw):
        """value= alone -> set_mode(mode), set_operation not called (legacy behaviour)."""
        pw_control = self._make_pw_control()
        mock_pw_control.client = pw_control.client
        mock_pw_control.set_mode = pw_control.set_mode
        mock_pw_control.set_operation = pw_control.set_operation
        mock_pw.tedapi = None

        self._post("/control/mode", {"value": "backup", "token": SECRET})

        pw_control.set_mode.assert_called_once_with("backup")
        pw_control.set_operation.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        self.assertEqual(json.loads(self._response_body()), {"set_mode": "ok"})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_value_with_valid_level_calls_set_operation(self, _proxystats_lock, mock_safe, mock_pw_control, mock_pw):
        """value= + valid level= -> set_operation(level, mode), neither set_mode nor set_reserve."""
        pw_control = self._make_pw_control()
        mock_pw_control.client = pw_control.client
        mock_pw_control.set_mode = pw_control.set_mode
        mock_pw_control.set_reserve = pw_control.set_reserve
        mock_pw_control.set_operation = pw_control.set_operation
        mock_pw.tedapi = None

        self._post(
            "/control/mode",
            {"value": "backup", "level": "80", "token": SECRET},
        )

        pw_control.set_operation.assert_called_once_with(80, "backup")
        pw_control.set_mode.assert_not_called()
        pw_control.set_reserve.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        self.assertEqual(json.loads(self._response_body()), {"set_operation": "ok"})

    @common_patches
    @patch("proxy.server.control_secret", SECRET)
    @patch("proxy.server.pw")
    @patch("proxy.server.pw_control")
    @patch("proxy.server.safe_pw_call", side_effect=_passthrough_safe_pw_call)
    def test_value_with_invalid_level_returns_error(self, _proxystats_lock, mock_safe, mock_pw_control, mock_pw):
        """value= + non-numeric level= -> 400 error, no Powerwall call (no silent fallback to set_mode)."""
        pw_control = self._make_pw_control()
        mock_pw_control.client = pw_control.client
        mock_pw_control.set_mode = pw_control.set_mode
        mock_pw_control.set_operation = pw_control.set_operation
        mock_pw.tedapi = None

        self._post(
            "/control/mode",
            {"value": "backup", "level": "not-a-number", "token": SECRET},
        )

        pw_control.set_mode.assert_not_called()
        pw_control.set_operation.assert_not_called()
        self.handler.send_response.assert_called_with(HTTPStatus.BAD_REQUEST)
        self.assertIn("error", json.loads(self._response_body()))


if __name__ == "__main__":
    unittest.main()
