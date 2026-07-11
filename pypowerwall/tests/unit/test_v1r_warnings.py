"""Unit tests for v1r key-auth warning behavior.

Covers two new code paths added in fix/v1r-pending-verification-warning:
  1. TEDAPI._connect_v1r() probes key state at init and logs an error if
     PENDING_VERIFICATION is detected.
  2. TEDAPIv1r.post_v1r() emits a warnings.warn() exactly once when the
     gateway returns an "authorization not verified" inner payload.
"""
import logging
import warnings
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_routable_message(
    fault=combined_pb2.MESSAGEFAULT_ERROR_NONE,
    inner_bytes: bytes = b"",
) -> bytes:
    """Return serialized RoutableMessage bytes for use as a mock HTTP response."""
    msg = combined_pb2.RoutableMessage()
    msg.signed_message_status.message_fault = fault
    msg.protobuf_message_as_bytes = inner_bytes
    return msg.SerializeToString()


# ---------------------------------------------------------------------------
# Tests: TEDAPI._connect_v1r() — connect-time probe
# ---------------------------------------------------------------------------

class TestConnectV1rProbe:
    """TEDAPI._connect_v1r() probes key state and logs an error on PENDING_VERIFICATION."""

    def _make_tedapi(self):
        """Build a TEDAPI instance with all network I/O mocked out."""
        with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
            from pypowerwall.tedapi import TEDAPI
            ted = TEDAPI(gw_pwd="testpassword")
        ted.gw_ip = "10.42.1.1"
        ted.v1r = True
        ted.wifi_session = None
        return ted

    def test_connect_v1r_logs_error_when_pending_verification(self, caplog):
        """When probe returns None and pending_verification is True, an error is logged."""
        ted = self._make_tedapi()

        mock_transport = MagicMock()
        mock_transport.login.return_value = True
        mock_transport.get_din.return_value = "TEST_DIN"
        mock_transport.get_config_v1r.return_value = None
        mock_transport.pending_verification = True
        ted.v1r_transport = mock_transport

        with caplog.at_level(logging.ERROR):
            result = ted._connect_v1r()

        assert result == "TEST_DIN", "_connect_v1r() must still return the DIN"
        assert any(
            "PENDING_VERIFICATION" in record.message for record in caplog.records
        ), "Expected PENDING_VERIFICATION error to be logged"

    def test_connect_v1r_no_log_when_probe_succeeds(self, caplog):
        """When the probe returns data, no PENDING_VERIFICATION error is logged."""
        ted = self._make_tedapi()

        mock_transport = MagicMock()
        mock_transport.login.return_value = True
        mock_transport.get_din.return_value = "TEST_DIN"
        mock_transport.get_config_v1r.return_value = {"vin": "GW--123"}
        mock_transport.pending_verification = False
        ted.v1r_transport = mock_transport

        with caplog.at_level(logging.ERROR):
            result = ted._connect_v1r()

        assert result == "TEST_DIN"
        assert not any(
            "PENDING_VERIFICATION" in record.message for record in caplog.records
        )

    def test_connect_v1r_logs_error_when_key_unknown(self, caplog):
        """When probe returns None and key_unknown is True, an error is logged."""
        ted = self._make_tedapi()

        mock_transport = MagicMock()
        mock_transport.login.return_value = True
        mock_transport.get_din.return_value = "TEST_DIN"
        mock_transport.get_config_v1r.return_value = None
        mock_transport.pending_verification = False
        mock_transport.key_unknown = True
        ted.v1r_transport = mock_transport

        with caplog.at_level(logging.ERROR):
            result = ted._connect_v1r()

        assert result == "TEST_DIN"
        assert any(
            "key" in record.message.lower() and "not recognized" in record.message.lower()
            for record in caplog.records
        ), "Expected UNKNOWN_KEY_ID error to be logged"

    def test_connect_v1r_no_log_when_probe_none_but_not_pending(self, caplog):
        """When probe returns None but both flags are False, no error is logged."""
        ted = self._make_tedapi()

        mock_transport = MagicMock()
        mock_transport.login.return_value = True
        mock_transport.get_din.return_value = "TEST_DIN"
        mock_transport.get_config_v1r.return_value = None
        mock_transport.pending_verification = False
        mock_transport.key_unknown = False
        ted.v1r_transport = mock_transport

        with caplog.at_level(logging.ERROR):
            result = ted._connect_v1r()

        assert result == "TEST_DIN"
        assert not any(
            "PENDING_VERIFICATION" in record.message or "not recognized" in record.message
            for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Tests: TEDAPIv1r.post_v1r() — warning-once behavior
# ---------------------------------------------------------------------------

class TestPostV1rWarnings:
    """TEDAPIv1r.post_v1r() emits a UserWarning exactly once per 'authorization not verified' error."""

    def _make_transport(self):
        """Build a TEDAPIv1r with all I/O mocked (no real socket, no real RSA key)."""
        from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r

        with patch.object(TEDAPIv1r, "__init__", lambda self, *a, **kw: None):
            transport = TEDAPIv1r.__new__(TEDAPIv1r)
        # Minimal attribute setup matching the real __init__
        transport.pending_verification = False
        transport.key_unknown = False
        transport.host = "10.42.1.1"
        transport.timeout = 5
        transport.token = "fake-token"
        transport.din = "TEST_DIN"
        # Stub out RSA signing so we don't need a real key
        transport._private_key = MagicMock()
        transport._private_key.sign.return_value = b"\x00" * 64
        transport._public_key_der = b"\x00" * 32

        # Mock the session so we can control the HTTP response
        transport.session = MagicMock()
        return transport

    def _mock_response(self, payload_bytes: bytes, status_code: int = 200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.content = _make_routable_message(inner_bytes=payload_bytes)
        return resp

    def test_pending_verification_emits_warning_once(self):
        """First 'authorization not verified' call emits UserWarning; second does not."""
        transport = self._make_transport()
        inner = b"v1r: client authorization not verified"
        transport.session.post.return_value = self._mock_response(inner)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result1 = transport.post_v1r(b"fake-payload", "TEST_DIN")
            result2 = transport.post_v1r(b"fake-payload", "TEST_DIN")

        assert result1 is None, "post_v1r must return None on auth failure"
        assert result2 is None

        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 1, (
            f"Expected exactly one UserWarning across two calls, got {len(user_warnings)}"
        )
        assert "PENDING_VERIFICATION" in str(user_warnings[0].message)

    def test_pending_verification_flag_is_set(self):
        """pending_verification flag must be True after the first auth failure."""
        transport = self._make_transport()
        inner = b"authorization not verified"
        transport.session.post.return_value = self._mock_response(inner)

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            transport.post_v1r(b"fake-payload", "TEST_DIN")

        assert transport.pending_verification is True

    def test_unknown_key_emits_warning_once(self):
        """UNKNOWN_KEY_ID fault emits UserWarning exactly once across repeated calls."""
        transport = self._make_transport()
        bad_resp = MagicMock()
        bad_resp.status_code = 200
        msg = combined_pb2.RoutableMessage()
        msg.signed_message_status.message_fault = combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID
        bad_resp.content = msg.SerializeToString()
        transport.session.post.return_value = bad_resp

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result1 = transport.post_v1r(b"fake-payload", "TEST_DIN")
            result2 = transport.post_v1r(b"fake-payload", "TEST_DIN")

        assert result1 is None
        assert result2 is None
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 1, (
            f"Expected exactly one UserWarning across two calls, got {len(user_warnings)}"
        )
        assert "UNKNOWN_KEY_ID" in str(user_warnings[0].message)
        assert transport.key_unknown is True

    def test_valid_response_returns_inner_bytes(self):
        """A well-formed response returns the inner bytes without a warning."""
        transport = self._make_transport()
        inner = b"\x08\x01\x12\x03abc"  # fake valid protobuf
        transport.session.post.return_value = self._mock_response(inner)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = transport.post_v1r(b"fake-payload", "TEST_DIN")

        assert result == inner
        assert not any(issubclass(w.category, UserWarning) for w in caught)
        assert transport.pending_verification is False
        assert transport.key_unknown is False
