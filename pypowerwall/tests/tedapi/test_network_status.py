"""Offline tests for the gateway networking status path.

These exercise TEDAPI.get_network_status against the real generated protobufs
(no gateway): the exact request bytes that were validated on hardware, the
response parse for each transport, the output shapes, and the guarantee that the
Wi-Fi password the gateway includes in its reply never reaches a caller or a log.
"""
import json
import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.api_version import TEDAPIApiVersion
from pypowerwall.tedapi.auth_mode import AuthMode
from pypowerwall.tedapi.network_status import (NetworkInterfaceStatus, NetworkStatus,
                                               enum_name, format_ipv4, format_mac)
from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2

try:
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_transport_pb2 as _tx  # noqa
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_energy_device_pb2 as _ed  # noqa
    HAVE_V2026 = True
except Exception:
    HAVE_V2026 = False

v2026_only = pytest.mark.skipif(not HAVE_V2026, reason='V2026_06 protos require protobuf>=6.33.6')

DIN = '1538000-45-D--GF225311003KW7'
SSID = 'HomeNetwork'
PASSWORD = 'S3cretWifiPass'
WIFI_MAC = bytes.fromhex('a1b2c3d4e5f6')
WIFI_IP = 0xC0A80116        # 192.168.1.22
MASK = 0xFFFFFF00           # 255.255.255.0
ROUTER = 0xC0A80101         # 192.168.1.1
DNS = 0x09090909            # 9.9.9.9

# The local installer envelope the gateway answered over Gateway Wi-Fi basic
# auth on a Powerwall 3 (firmware 26.34.3, 2026-11-14) and a Powerwall 2
# (firmware 26.42.0): deliveryChannel LOCAL_HTTPS, sender.local INSTALLER,
# recipient.din, and an empty common.get_networking_status_request
# (CommonMessages field 22 -> tag 0xB2 0x01, length 0).
PINNED_ENVELOPE = (b'\x08\x01'
                   b'\x12\x02\x18\x01'
                   b'\x1a\x1e\x0a\x1c' + DIN.encode() +
                   b'\x22\x03\xb2\x01\x00')
# Basic (Gateway Wi-Fi) wraps the envelope in a transport Message with a tail.
PINNED_MESSAGE = b'\x0a' + bytes([len(PINNED_ENVELOPE)]) + PINNED_ENVELOPE + b'\x12\x02\x08\x01'
# The signed-command envelope the gateway answered over signed v1r on a
# Powerwall 3 (firmware 26.34.3, 2026-11-15): deliveryChannel HERMES_COMMAND,
# sender.authorizedClient CUSTOMER_MOBILE_APP, same recipient and request. A
# Powerwall 2 (firmware 26.42.0) timed out on the installer envelope over v1r.
PINNED_V1R_ENVELOPE = (b'\x08\x02'
                       b'\x12\x02\x20\x01'
                       b'\x1a\x1e\x0a\x1c' + DIN.encode() +
                       b'\x22\x03\xb2\x01\x00')


def _make_api(v1r=False, auth_mode=AuthMode.BASIC, api_version=TEDAPIApiVersion.V2024_06):
    # Patch connect() so construction doesn't reach the network (mirrors test_init).
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value='TEST_DIN'):
        api = TEDAPI('test_password', pwcacheexpire=50)
    api.din = DIN
    api.v1r = v1r
    api.auth_mode = auth_mode
    api.tedapi_api_version = api_version
    return api


def _fill(envelope):
    """Populate a networking status reply shaped like the one seen on hardware:
    Wi-Fi active with a percentage but no dBm/SNR, Ethernet idle, cellular up."""
    response = envelope.common.get_networking_status_response
    response.wifi_config.ssid = SSID
    response.wifi_config.security_type = combined_pb2.WIFI_NETWORK_SECURITY_TYPE_WPA2_PERSONAL
    # The password is field 2 (WifiPassword{value = 1}) in Tesla's schema. The
    # legacy proto reserves it, so the only way to put it in a test reply is as
    # raw wire bytes -- exactly how it arrives from a real gateway.
    password = PASSWORD.encode()
    response.wifi_config.MergeFromString(
        b'\x12' + bytes([len(password) + 2]) + b'\x0a' + bytes([len(password)]) + password)

    wifi = response.wifi
    wifi.mac_address = WIFI_MAC
    wifi.enabled = True
    wifi.active_route = True
    wifi.ipv4_config.dhcp_enabled = True
    wifi.ipv4_config.address = WIFI_IP
    wifi.ipv4_config.subnet_mask = MASK
    wifi.ipv4_config.gateway = ROUTER
    wifi.ipv4_config.dns.append(DNS)
    wifi.connectivity_status.connected_physical = True
    wifi.connectivity_status.connected_internet = True
    wifi.connectivity_status.connected_tesla = True
    wifi.connectivity_status.rssi.signal_strength_percent.value = 58
    wifi.device_state = combined_pb2.NETWORK_DEVICE_STATE_READY
    wifi.device_state_reason = combined_pb2.NETWORK_DEVICE_STATE_REASON_NONE

    eth = response.eth
    eth.mac_address = bytes.fromhex('a1b2c3d4e5f7')
    eth.enabled = True
    eth.connectivity_status.rssi.signal_strength_percent.value = 0

    gsm = response.gsm
    gsm.enabled = True
    gsm.connectivity_status.connected_physical = True
    gsm.connectivity_status.connected_internet = True
    gsm.connectivity_status.connected_tesla = True
    gsm.connectivity_status.rssi.signal_strength_percent.value = 60
    return envelope


def _wrap(envelope, bare):
    """Serialize in the shape the transport hands back: bare MessageEnvelope for
    v1r / bearer, full transport Message (with tail) for basic."""
    if bare:
        return envelope.SerializeToString()
    message = combined_pb2.Message()
    message.message.CopyFrom(envelope)
    message.tail.value = 1
    return message.SerializeToString()


def _response(bare):
    return _wrap(_fill(combined_pb2.MessageEnvelope()), bare)


EXPECTED_WIFI = {
    'enabled': True,
    'active_route': True,
    'connected_physical': True,
    'connected_internet': True,
    'connected_tesla': True,
    'signal_strength_percent': 58,
    'rssi': None,
    'snr': None,
    'device_state': 'NETWORK_DEVICE_STATE_READY',
    'device_state_reason': 'NETWORK_DEVICE_STATE_REASON_NONE',
}

TRANSPORTS = [
    pytest.param(False, AuthMode.BASIC, id='basic'),
    pytest.param(False, AuthMode.BEARER, id='bearer'),
    pytest.param(True, AuthMode.BASIC, id='v1r'),
]


# ── Request ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('auth_mode', [AuthMode.BASIC, AuthMode.BEARER])
def test_request_bytes_are_pinned(auth_mode):
    """The request must stay byte-identical to the hardware-validated one."""
    api = _make_api(auth_mode=auth_mode)
    with patch.object(api, '_post_tedapi', return_value=None) as post:
        assert api.get_network_status() is None
    post.assert_called_once_with(PINNED_MESSAGE, v1r_envelope=None)


def test_v1r_request_adds_the_pinned_signed_command_envelope():
    """v1r hands the transport both forms: the signed-command envelope for the
    signed transports, the installer Message for the legacy Wi-Fi fallback."""
    api = _make_api(v1r=True)
    with patch.object(api, '_post_tedapi', return_value=None) as post:
        assert api.get_network_status() is None
    post.assert_called_once_with(PINNED_MESSAGE, v1r_envelope=PINNED_V1R_ENVELOPE)


def _v1r_api_with_transports():
    api = _make_api(v1r=True)
    api.v1r_transport = MagicMock()
    api.v1r_transport.post_v1r.return_value = _response(bare=True)
    api.wifi_v1r_transport = MagicMock()
    api.wifi_v1r_transport.post_v1r.return_value = _response(bare=True)
    return api


def _fail_lan(api):
    api.lan_failed = True
    api.lan_recover_after = time.time() + 3600


def test_v1r_lan_sends_the_signed_command_envelope():
    api = _v1r_api_with_transports()
    assert api.get_network_status()['wifi'] == EXPECTED_WIFI
    api.v1r_transport.post_v1r.assert_called_once_with(PINNED_V1R_ENVELOPE, DIN)


def test_signed_wifi_v1r_fallback_sends_the_signed_command_envelope():
    api = _v1r_api_with_transports()
    api.wifi_v1r_fallback = True
    _fail_lan(api)
    assert api.get_network_status()['wifi'] == EXPECTED_WIFI
    api.wifi_v1r_transport.post_v1r.assert_called_once_with(PINNED_V1R_ENVELOPE, DIN)
    api.v1r_transport.post_v1r.assert_not_called()


def test_legacy_wifi_fallback_keeps_the_installer_envelope():
    """With the LAN down and no signed Wi-Fi route, v1r falls back to Gateway
    Wi-Fi basic auth, which was validated with the installer envelope."""
    api = _v1r_api_with_transports()
    api.wifi_session = MagicMock()
    _fail_lan(api)
    with patch.object(api, '_post_tedapi_wifi', return_value=_response(bare=False)) as wifi:
        assert api.get_network_status()['wifi'] == EXPECTED_WIFI
    wifi.assert_called_once_with(PINNED_MESSAGE, '/tedapi/v1')
    api.v1r_transport.post_v1r.assert_not_called()


def test_other_requests_are_unchanged_on_v1r():
    """Without v1r_envelope the transport still strips the Message wrapper."""
    api = _v1r_api_with_transports()
    api._post_tedapi(PINNED_MESSAGE)
    api.v1r_transport.post_v1r.assert_called_once_with(PINNED_ENVELOPE, DIN)


@pytest.mark.parametrize('api_version', [
    TEDAPIApiVersion.V2024_06,
    pytest.param(TEDAPIApiVersion.V2026_06, marks=v2026_only),
])
def test_envelope_survives_transport_unwrap(api_version):
    """v1r and bearer strip the Message/Tail wrapper by re-parsing with the
    transport proto of the configured api version. Neither may drop the request
    (the legacy proto does not know CommonMessages field 22)."""
    api = _make_api(v1r=True, api_version=api_version)
    assert api._envelope_bytes(PINNED_MESSAGE) == PINNED_ENVELOPE


# ── Response parse, per transport ────────────────────────────────────────────

@pytest.mark.parametrize('v1r, auth_mode', TRANSPORTS)
def test_get_network_status_per_transport(v1r, auth_mode):
    api = _make_api(v1r=v1r, auth_mode=auth_mode)
    bare = v1r or auth_mode == AuthMode.BEARER
    with patch.object(api, '_post_tedapi', return_value=_response(bare)):
        status = api.get_network_status()

    assert list(status) == ['wifi', 'eth', 'gsm']
    assert status['wifi'] == EXPECTED_WIFI
    assert status['eth'] == {
        'enabled': True, 'active_route': False, 'connected_physical': False,
        'connected_internet': False, 'connected_tesla': False,
        'signal_strength_percent': 0, 'rssi': None, 'snr': None,
        'device_state': 'NETWORK_DEVICE_STATE_INVALID',
        'device_state_reason': 'NETWORK_DEVICE_STATE_REASON_INVALID',
    }
    assert status['gsm']['connected_tesla'] is True
    assert status['gsm']['signal_strength_percent'] == 60


def test_details_adds_identifying_fields():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=_response(bare=False)):
        status = api.get_network_status(details=True)

    assert status['wifi'] == {
        **EXPECTED_WIFI,
        'mac_address': 'a1:b2:c3:d4:e5:f6',
        'ipv4': {'dhcp_enabled': True, 'address': '192.168.1.22',
                 'subnet_mask': '255.255.255.0', 'gateway': '192.168.1.1',
                 'dns': ['9.9.9.9']},
    }
    # No IPv4 config and no MAC on the wire -> None, not empty placeholders.
    assert status['gsm']['mac_address'] is None
    assert status['gsm']['ipv4'] is None
    assert status['wifi_config'] == {
        'ssid': SSID, 'security_type': 'WIFI_NETWORK_SECURITY_TYPE_WPA2_PERSONAL'}
    json.dumps(status)  # JSON-safe


@v2026_only
@pytest.mark.parametrize('bare', [True, False])
def test_parses_reply_built_from_tesla_schema(bare):
    """A reply serialized with the generated V2026_06 schema (Tesla's own field
    layout, including the password message) parses through the legacy proto --
    the two definitions agree on the wire."""
    envelope = _ed.MessageEnvelope()
    response = envelope.common.getNetworkingStatusResponse
    response.wifiConfig.ssid = SSID
    response.wifiConfig.password.value = PASSWORD
    response.wifiConfig.securityType = 3
    response.wifi.macAddress = WIFI_MAC
    response.wifi.enabled = True
    response.wifi.activeRoute = True
    response.wifi.ipv4Config.dhcpEnabled = True
    response.wifi.ipv4Config.address = WIFI_IP
    response.wifi.ipv4Config.subnetMask = MASK
    response.wifi.ipv4Config.gateway = ROUTER
    response.wifi.ipv4Config.dns.append(DNS)
    response.wifi.connectivityStatus.connectedPhysical = True
    response.wifi.connectivityStatus.connectedInternet = True
    response.wifi.connectivityStatus.connectedTesla = True
    response.wifi.connectivityStatus.rssi.value = -61
    response.wifi.connectivityStatus.rssi.signalStrengthPercent.value = 58
    response.wifi.connectivityStatus.snr.value = 27
    response.wifi.deviceState = 6
    response.wifi.deviceStateReason = 1
    if bare:
        raw = envelope.SerializeToString()
    else:
        message = _tx.Message()
        message.message.CopyFrom(envelope)
        message.tail.value = 1
        raw = message.SerializeToString()

    api = _make_api(v1r=bare, api_version=TEDAPIApiVersion.V2026_06)
    with patch.object(api, '_post_tedapi', return_value=raw):
        status = api.get_network_status(details=True)

    assert status['wifi'] == {
        **EXPECTED_WIFI, 'rssi': -61, 'snr': 27,
        'mac_address': 'a1:b2:c3:d4:e5:f6',
        'ipv4': {'dhcp_enabled': True, 'address': '192.168.1.22',
                 'subnet_mask': '255.255.255.0', 'gateway': '192.168.1.1',
                 'dns': ['9.9.9.9']},
    }
    assert status['eth'] is None and status['gsm'] is None
    assert PASSWORD not in json.dumps(status)


# ── Privacy ──────────────────────────────────────────────────────────────────

def test_wifi_password_never_surfaces(caplog):
    """The reply carries the Wi-Fi password; it must not appear in any output
    shape, in the cached model, or in the logs (DEBUG included)."""
    raw = _response(bare=False)
    assert PASSWORD.encode() in raw  # the test reply really does contain it
    api = _make_api()
    with caplog.at_level(logging.DEBUG, logger='pypowerwall'), \
         patch.object(api, '_post_tedapi', return_value=raw):
        default = api.get_network_status()
        details = api.get_network_status(details=True)

    model = api._cache_get('network_status', 50, False)
    assert isinstance(model, NetworkStatus)
    for text in (json.dumps(default), json.dumps(details), repr(model), str(vars(model)),
                 caplog.text):
        assert PASSWORD not in text
    assert not hasattr(combined_pb2.WifiConfig(), 'password')


def test_identifying_fields_stay_out_of_default_output_and_logs(caplog):
    api = _make_api()
    with caplog.at_level(logging.DEBUG, logger='pypowerwall'), \
         patch.object(api, '_post_tedapi', return_value=_response(bare=False)):
        default = api.get_network_status()

    assert 'network status' in caplog.text  # the debug line was emitted
    for text in (json.dumps(default), caplog.text):
        for private in (SSID, 'a1:b2:c3:d4:e5:f6', '192.168.1.22', '192.168.1.1'):
            assert private not in text
    assert 'wifi_config' not in default


# ── Failure handling: log and return None, never raise ───────────────────────

@pytest.mark.parametrize('v1r, auth_mode', TRANSPORTS)
def test_error_response_returns_none(v1r, auth_mode, caplog):
    """Firmware without the request answers common.error_response."""
    bare = v1r or auth_mode == AuthMode.BEARER
    envelope = combined_pb2.MessageEnvelope()
    envelope.common.error_response.status.code = 12
    envelope.common.error_response.status.message = 'not implemented'
    api = _make_api(v1r=v1r, auth_mode=auth_mode)
    with caplog.at_level(logging.ERROR, logger='pypowerwall'), \
         patch.object(api, '_post_tedapi', return_value=_wrap(envelope, bare)):
        assert api.get_network_status() is None
    assert 'gateway returned error 12: not implemented' in caplog.text


def test_unexpected_payloads_return_none(caplog):
    api = _make_api(v1r=True)
    other = combined_pb2.MessageEnvelope()
    other.teg.get_backup_events_response.SetInParent()
    empty_common = combined_pb2.MessageEnvelope()
    empty_common.common.SetInParent()
    with caplog.at_level(logging.ERROR, logger='pypowerwall'):
        for raw in (other.SerializeToString(), empty_common.SerializeToString(), b''):
            with patch.object(api, '_post_tedapi', return_value=raw):
                assert api.get_network_status(force=True) is None
    assert caplog.text.count('unexpected response from gateway') == 3


def test_undecodable_response_returns_none(caplog):
    api = _make_api(v1r=True)
    with caplog.at_level(logging.ERROR, logger='pypowerwall'), \
         patch.object(api, '_post_tedapi', return_value=b'\xff\xff\xff'):
        assert api.get_network_status() is None
    assert 'Error fetching network status' in caplog.text


def test_failures_are_not_cached():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=None) as post:
        assert api.get_network_status() is None
        assert api.get_network_status() is None
    assert post.call_count == 2


def test_not_connected_returns_none():
    api = _make_api()
    api.din = None
    with patch.object(api, 'connect', return_value=None), \
         patch.object(api, '_post_tedapi') as post:
        assert api.get_network_status() is None
    post.assert_not_called()


# ── Cache ────────────────────────────────────────────────────────────────────

def test_cache_serves_both_shapes_and_force_refetches():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=_response(bare=False)) as post:
        first = api.get_network_status()
        assert api.get_network_status() == first
        assert 'wifi_config' in api.get_network_status(details=True)
        assert post.call_count == 1
        api.get_network_status(force=True)
        assert post.call_count == 2


def test_caller_cannot_mutate_cached_status():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=_response(bare=False)):
        details = api.get_network_status(details=True)
        details['wifi']['enabled'] = False
        details['wifi']['ipv4']['dns'].append('1.1.1.1')
        details['wifi']['ipv4']['address'] = 'changed'
        again = api.get_network_status(details=True)
    assert again['wifi']['enabled'] is True
    assert again['wifi']['ipv4'] == {'dhcp_enabled': True, 'address': '192.168.1.22',
                                     'subnet_mask': '255.255.255.0', 'gateway': '192.168.1.1',
                                     'dns': ['9.9.9.9']}


# ── Model ────────────────────────────────────────────────────────────────────

def test_missing_interfaces_and_config_are_none():
    response = combined_pb2.CommonAPIGetNetworkingStatusResponse()
    response.wifi.enabled = True
    status = NetworkStatus.from_proto(response)
    assert status.interfaces == ['wifi']
    assert status.to_dict(details=True) == {
        'wifi': {'enabled': True, 'active_route': False, 'connected_physical': False,
                 'connected_internet': False, 'connected_tesla': False,
                 'signal_strength_percent': None, 'rssi': None, 'snr': None,
                 'device_state': 'NETWORK_DEVICE_STATE_INVALID',
                 'device_state_reason': 'NETWORK_DEVICE_STATE_REASON_INVALID',
                 'mac_address': None, 'ipv4': None},
        'eth': None,
        'gsm': None,
        'wifi_config': None,
    }


def test_signal_values_reported_when_present():
    interface = combined_pb2.NetworkInterface()
    interface.connectivity_status.rssi.value = -72
    interface.connectivity_status.rssi.signal_strength_percent.value = 41
    interface.connectivity_status.snr.value = 0   # wrapper: an explicit 0 is kept
    status = NetworkInterfaceStatus.from_proto(interface)
    assert (status.rssi, status.signal_strength_percent, status.snr) == (-72, 41, 0)


def test_unknown_enum_values_do_not_break_output():
    """Newer firmware may send enum values this schema does not define."""
    response = combined_pb2.CommonAPIGetNetworkingStatusResponse()
    response.wifi_config.security_type = 42
    response.wifi.device_state = 99
    response.wifi.device_state_reason = 77
    data = NetworkStatus.from_proto(response).to_dict(details=True)
    assert data['wifi']['device_state'] == 'UNKNOWN (99)'
    assert data['wifi']['device_state_reason'] == 'UNKNOWN (77)'
    assert data['wifi_config'] == {'ssid': None, 'security_type': 'UNKNOWN (42)'}


def test_formatters():
    assert format_ipv4(0xC0A80102) == '192.168.1.2'
    assert format_ipv4(0) is None
    assert format_mac(bytes.fromhex('0a1b2c3d4e5f')) == '0a:1b:2c:3d:4e:5f'
    assert format_mac(b'') is None
    assert enum_name(combined_pb2.NetworkDeviceState, 6) == 'NETWORK_DEVICE_STATE_READY'
    assert enum_name(combined_pb2.NetworkDeviceState, 1234) == 'UNKNOWN (1234)'


def test_common_messages_is_a_oneof():
    """error_response and the networking messages share Tesla's `message` oneof;
    the existing HasField('error_response') callers keep working."""
    common = combined_pb2.CommonMessages()
    assert common.WhichOneof('message') is None
    common.error_response.status.code = 3
    assert common.HasField('error_response') and common.WhichOneof('message') == 'error_response'
    common.get_networking_status_request.SetInParent()
    assert not common.HasField('error_response')
    assert common.SerializeToString() == b'\xb2\x01\x00'
