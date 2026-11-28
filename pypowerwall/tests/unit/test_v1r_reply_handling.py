"""Unit tests for how TEDAPIv1r.post_v1r() reads a gateway reply, and how the
LAN failover counts it (review of #477).

1. The plain-text "authorization not verified" error is recognised only where
   the gateway sends it: as the whole inner payload, or in the envelope outside
   the payload. A valid reply whose data merely contains the phrase (a Wi-Fi
   SSID in the network status, a key description) is returned as data, and no
   warning or log ever shows an inner payload, which can hold the Wi-Fi
   password.
2. A request-level fault (the gateway answered but refused or couldn't complete
   that one request, e.g. a Powerwall 2 timing out on the network status) is
   not a LAN failure: it neither counts toward the LAN->WiFi failover nor
   resets the count. Key, signature and clock faults still count, as before.
3. The network status logs its Powerwall 2 hint only for such a refusal, not
   for a LAN outage or a key problem.

Everything is mocked at the HTTP session / transport boundary.
"""
import logging
import threading
import warnings
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2
from pypowerwall.tedapi.tedapi_v1r import REQUEST_FAULTS, TEDAPIv1r, _plain_text

LEADER = "1707000-11-J--TG0123456789AB"
PHRASE = "authorization not verified"
PASSWORD = "S3cretWifiPass"
PLAIN_ERROR = b"v1r: client authorization not verified"


def _network_reply(ssid: str) -> bytes:
    """A network status reply (bare MessageEnvelope, as v1r returns it) whose
    Wi-Fi SSID is ``ssid``, with the Wi-Fi password as raw wire bytes (field 2,
    which the legacy proto doesn't model) -- as a real gateway sends it."""
    envelope = combined_pb2.MessageEnvelope()
    response = envelope.common.get_networking_status_response
    response.wifi_config.ssid = ssid
    password = PASSWORD.encode()
    response.wifi_config.MergeFromString(
        b"\x12" + bytes([len(password) + 2]) + b"\x0a" + bytes([len(password)]) + password)
    response.wifi.enabled = True
    return envelope.SerializeToString()


def _routable(inner: bytes = b"", fault=combined_pb2.MESSAGEFAULT_ERROR_NONE, outside: bytes = b"") -> bytes:
    msg = combined_pb2.RoutableMessage()
    msg.signed_message_status.message_fault = fault
    if inner:
        msg.protobuf_message_as_bytes = inner
    if outside:
        # Text in the envelope itself, outside the inner payload.
        msg.from_destination.routing_address = outside
    return msg.SerializeToString()


def _transport() -> TEDAPIv1r:
    """A TEDAPIv1r with no real key or socket (built without __init__, as the
    other v1r unit tests do)."""
    with patch.object(TEDAPIv1r, "__init__", lambda self, *a, **kw: None):
        transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.pending_verification = False
    transport.key_unknown = False
    transport._flag_lock = threading.Lock()
    transport.host = "10.42.1.1"
    transport.timeout = 5
    transport.din = LEADER
    transport.key_fingerprint = "f" * 64
    transport._private_key = MagicMock()
    transport._private_key.sign.return_value = b"\x00" * 64
    transport._public_key_der = b"\x00" * 32
    transport.session = MagicMock()
    return transport


def _reply(transport: TEDAPIv1r, content: bytes) -> None:
    response = MagicMock()
    response.status_code = 200
    response.content = content
    transport.session.post.return_value = response


def _post(transport: TEDAPIv1r, caplog):
    """post_v1r() once; returns (result, warnings, log text)."""
    with warnings.catch_warnings(record=True) as caught, caplog.at_level(logging.DEBUG):
        warnings.simplefilter("always")
        result = transport.post_v1r(b"envelope", LEADER)
    messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
    return result, messages, caplog.text


# ---------------------------------------------------------------------------
# 1. The plain-text auth error, and what diagnostics may show
# ---------------------------------------------------------------------------

class TestAuthNotVerifiedText:

    @pytest.mark.parametrize("ssid", [PHRASE, f"Home {PHRASE.upper()} 5G"])
    def test_reply_containing_the_phrase_is_data(self, ssid, caplog):
        """The case from the review: a network status reply whose SSID holds
        the phrase is a valid reply, not an auth error."""
        transport = _transport()
        reply = _network_reply(ssid)
        _reply(transport, _routable(reply))
        result, messages, logs = _post(transport, caplog)
        assert result == reply
        assert messages == []
        assert transport.pending_verification is False
        assert PASSWORD not in logs and ssid not in logs

    @pytest.mark.parametrize("text", [PLAIN_ERROR, b"authorization not verified", b"  v1r: Client Authorization Not Verified\n"])
    def test_plain_text_error_still_detected(self, text, caplog):
        transport = _transport()
        _reply(transport, _routable(text))
        result, messages, _ = _post(transport, caplog)
        assert result is None
        assert transport.pending_verification is True
        assert len(messages) == 1 and "PENDING_VERIFICATION" in messages[0]
        assert repr(text.decode().strip()) in messages[0]  # the gateway's own words

    def test_phrase_outside_the_payload_still_detected_without_showing_the_payload(self, caplog):
        """The envelope check is kept (the text may land outside the payload),
        but the warning shows the envelope without the payload."""
        transport = _transport()
        _reply(transport, _routable(_network_reply("Home"), outside=PLAIN_ERROR))
        result, messages, logs = _post(transport, caplog)
        assert result is None
        assert transport.pending_verification is True
        assert len(messages) == 1
        assert "inner payload:" in messages[0] and "not shown" in messages[0]
        assert PASSWORD not in messages[0] and PASSWORD not in logs

    def test_unknown_key_preview_leaves_out_the_payload(self, caplog):
        transport = _transport()
        _reply(transport, _routable(_network_reply("Home"), fault=combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID))
        result, messages, logs = _post(transport, caplog)
        assert result is None
        assert len(messages) == 1 and "UNKNOWN_KEY_ID" in messages[0]
        assert PASSWORD not in messages[0] and PASSWORD not in logs

    def test_plain_text_helper(self):
        assert _plain_text(PLAIN_ERROR) == PLAIN_ERROR.decode()
        assert _plain_text(_network_reply(PHRASE)) is None   # protobuf, even with the phrase in it
        assert _plain_text(b"") is None
        assert _plain_text(b"a" * 513) is None               # too long for a gateway error
        assert _plain_text(b"bad \xff byte") is None


# ---------------------------------------------------------------------------
# 2. Request-level faults and the LAN failover
# ---------------------------------------------------------------------------

class TestRequestFault:

    def test_request_fault_is_reported_and_reset(self, caplog):
        transport = _transport()
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT))
        assert _post(transport, caplog)[0] is None
        assert transport.request_fault() == combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT
        # The next call starts clean, whatever happens to it.
        transport.session.post.side_effect = OSError("no route")
        assert _post(transport, caplog)[0] is None
        assert transport.request_fault() is None
        transport.session.post.side_effect = None
        assert transport.post_v1r(b"envelope", "") is None   # no DIN: returns before the request
        assert transport.request_fault() is None

    @pytest.mark.parametrize("fault", [
        combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID,
        combined_pb2.MESSAGEFAULT_ERROR_INVALID_SIGNATURE,
        combined_pb2.MESSAGEFAULT_ERROR_TIME_EXPIRED,
    ])
    def test_key_and_signature_faults_are_not_request_faults(self, fault, caplog):
        transport = _transport()
        _reply(transport, _routable(fault=fault))
        assert _post(transport, caplog)[0] is None
        assert transport.request_fault() is None
        assert fault not in REQUEST_FAULTS

    def test_request_fault_is_per_thread(self, caplog):
        transport = _transport()
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT))
        _post(transport, caplog)
        seen = []
        other = threading.Thread(target=lambda: seen.append(transport.request_fault()))
        other.start()
        other.join()
        assert seen == [None]
        assert transport.request_fault() == combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT


def _tedapi(transport) -> TEDAPI:
    """v1r TEDAPI with a WiFi host, failover on and a healthy LAN."""
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value=LEADER):
        ted = TEDAPI(gw_pwd="testpassword")
    ted.v1r = True
    ted.din = LEADER
    ted.wifi_host = "192.168.91.1"
    ted.wifi_session = MagicMock()
    ted.v1r_transport = transport
    return ted


class TestLanFailover:

    def test_powerwall2_network_status_timeouts_dont_trip_the_failover(self, caplog):
        """The review's scenario, end to end through the real transport: a
        Powerwall 2 answers the network status with MESSAGEFAULT_ERROR_TIMEOUT
        over v1r. Repeated, it must not move the healthy LAN to WiFi."""
        transport = _transport()
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT))
        ted = _tedapi(transport)
        with patch.object(ted, "_post_tedapi_wifi") as wifi, caplog.at_level(logging.DEBUG):
            for _ in range(10):
                assert ted._post_tedapi(b"req") is None
        wifi.assert_not_called()
        assert ted.lan_failed is False
        assert ted.lan_fail_count == 0

    def test_request_fault_doesnt_hide_a_failing_lan(self, caplog):
        """Neutral, not a success: failures around it still add up and trip."""
        transport = _transport()
        ted = _tedapi(transport)
        timeout = _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT)

        def answer(content=None, error=None):
            response = MagicMock(status_code=200, content=content)
            transport.session.post.side_effect = error
            transport.session.post.return_value = response

        with patch.object(ted, "_post_tedapi_wifi", return_value=None), caplog.at_level(logging.DEBUG):
            answer(error=OSError("no route"))
            ted._post_tedapi(b"req")
            ted._post_tedapi(b"req")
            assert ted.lan_fail_count == 2
            answer(content=timeout)
            ted._post_tedapi(b"req")
            assert ted.lan_fail_count == 2          # unchanged
            answer(error=OSError("no route"))
            ted._post_tedapi(b"req")
        assert ted.lan_failed is True

    def test_key_faults_still_trip_the_failover(self, caplog):
        """A key the gateway doesn't know fails every signed request: the
        failover (to a WiFi path that may work) keeps counting it."""
        transport = _transport()
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID))
        ted = _tedapi(transport)
        with patch.object(ted, "_post_tedapi_wifi", return_value=None), \
                warnings.catch_warnings(), caplog.at_level(logging.DEBUG):
            warnings.simplefilter("ignore")
            for _ in range(3):
                ted._post_tedapi(b"req")
        assert ted.lan_failed is True

    def test_success_after_a_request_fault_resets_the_count(self, caplog):
        transport = _transport()
        ted = _tedapi(transport)
        ted.lan_fail_count = 2
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT))
        ted._post_tedapi(b"req")
        _reply(transport, _routable(b"\x08\x01"))
        assert ted._post_tedapi(b"req") == b"\x08\x01"
        assert ted.lan_fail_count == 0

    def test_mocked_transports_keep_the_old_accounting(self):
        """A transport without request_fault() (or a Mock standing in for one)
        counts a None as a failure, as before."""
        ted = _tedapi(MagicMock())
        ted.v1r_transport.post_v1r.return_value = None
        with patch.object(ted, "_post_tedapi_wifi", return_value=None):
            for _ in range(3):
                ted._post_tedapi(b"req")
        assert ted.lan_failed is True


# ---------------------------------------------------------------------------
# 3. The network status's Powerwall 2 hint follows the gateway's refusal
# ---------------------------------------------------------------------------

class TestNetworkStatusHint:
    """get_network_status() over the real transport: the Powerwall 2 hint is
    logged only when the gateway refused the request, not for a LAN outage or a
    key problem, which the transport logs itself."""

    HINT = "a Powerwall 2 does not answer it over v1r"

    def _network_status(self, transport, caplog):
        ted = _tedapi(transport)
        with patch.object(ted, "_post_tedapi_wifi") as wifi, \
                warnings.catch_warnings(), caplog.at_level(logging.DEBUG):
            warnings.simplefilter("ignore")
            assert ted.get_network_status() is None
        wifi.assert_not_called()
        return caplog.text

    def test_powerwall2_timeout_is_explained(self, caplog):
        transport = _transport()
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT))
        assert self.HINT in self._network_status(transport, caplog)

    def test_lan_outage_gets_no_hint(self, caplog):
        transport = _transport()
        transport.session.post.side_effect = OSError("no route")
        assert self.HINT not in self._network_status(transport, caplog)

    def test_key_fault_gets_no_hint(self, caplog):
        transport = _transport()
        _reply(transport, _routable(fault=combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID))
        assert self.HINT not in self._network_status(transport, caplog)
