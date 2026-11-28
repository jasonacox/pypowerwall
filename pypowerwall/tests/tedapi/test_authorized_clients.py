"""Offline tests for the authorized clients (paired keys) path.

These exercise TEDAPI.get_authorized_clients / add_authorized_client /
remove_authorized_client against the real generated protobufs (no gateway): the
list, add and remove request bytes validated on hardware, the
response parse for each transport, key normalization, the guard against removing
the key a connection signs with, and that descriptions stay out of default
output and logs.
"""
import base64
import hashlib
import logging
import threading
import warnings
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.auth_mode import AuthMode
from pypowerwall.tedapi.authorized_clients import (AuthorizedClient, AuthorizedClients, enum_label,
                                                   fingerprint, public_key_bytes, rsa_public_key_der)
from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2
from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r

try:
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_transport_pb2 as _tx  # noqa
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_energy_device_pb2 as _ed  # noqa
    HAVE_V2026 = True
except Exception:
    HAVE_V2026 = False

v2026_only = pytest.mark.skipif(not HAVE_V2026, reason='V2026_06 protos require protobuf>=6.33.6')

DIN = '1538000-45-D--GF225311003KW7'
DESCRIPTION = "Alice's iPhone"
IDENTIFIER = 'alice@example.com'

_OWN = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OWN_DER = _OWN.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)
OTHER_DER = _OTHER.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)
OTHER_SPKI = _OTHER.public_key().public_bytes(serialization.Encoding.DER,
                                              serialization.PublicFormat.SubjectPublicKeyInfo)
OTHER_PEM = _OTHER.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)
OTHER_PRIVATE_PEM = _OTHER.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption())
EC_PEM = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

# The bare MessageEnvelope that listed the clients on a Powerwall 3 (firmware
# 26.34.3, signed v1r and Gateway Wi-Fi basic, 2026-11-14): deliveryChannel
# LOCAL_HTTPS, sender.local INSTALLER, recipient.din, and an empty
# authorization.list_authorized_clients_request (envelope field 12 -> tag 0x62;
# AuthorizationMessages field 5 -> tag 0x2a, length 0).
PINNED_LIST_ENVELOPE = (b'\x08\x01'
                        b'\x12\x02\x18\x01'
                        b'\x1a\x1e\x0a\x1c' + DIN.encode() +
                        b'\x62\x02\x2a\x00')
PINNED_LIST_MESSAGE = (b'\x0a' + bytes([len(PINNED_LIST_ENVELOPE)]) + PINNED_LIST_ENVELOPE
                       + b'\x12\x02\x08\x01')
# Signed command envelope (as the TEG writes): deliveryChannel HERMES_COMMAND,
# sender.authorizedClient CUSTOMER_MOBILE_APP, recipient.din. Add and remove in
# this shape were accepted by a Powerwall 3 (firmware 26.34.3, signed v1r,
# 2026-11-14); only the key bytes differ from the pinned tests below.
COMMAND_HEADER = (b'\x08\x02'
                  b'\x12\x02\x20\x01'
                  b'\x1a\x1e\x0a\x1c' + DIN.encode())


def _make_api(v1r=False, auth_mode=AuthMode.BASIC, key=OWN_DER):
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value='TEST_DIN'):
        api = TEDAPI('test_password', pwcacheexpire=50)
    api.din = DIN
    api.v1r = v1r
    api.auth_mode = auth_mode
    if v1r:
        transport = TEDAPIv1r.__new__(TEDAPIv1r)
        transport._public_key_der = key
        transport.post_v1r = MagicMock()
        api.v1r_transport = transport
    return api


def _record(record, key, state=combined_pb2.AUTHORIZED_STATE_VERIFIED, added=1730000000, by=b''):
    record.type = combined_pb2.AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP
    record.description = DESCRIPTION
    record.key_type = combined_pb2.AUTHORIZED_KEY_TYPE_RSA
    record.public_key = key
    record.roles.append(combined_pb2.AUTHORIZATION_ROLE_CUSTOMER)
    record.state = state
    record.verification = combined_pb2.AUTHORIZED_VERIFICATION_TYPE_PRESENCE_PROOF
    if added:
        record.added_time.seconds = added
    record.identifier = IDENTIFIER
    record.authorized_by_public_key = by
    return record


def _list_envelope():
    env = combined_pb2.MessageEnvelope()
    reply = env.authorization.list_authorized_clients_response
    _record(reply.clients.add(), OWN_DER)
    _record(reply.clients.add(), OTHER_DER, state=combined_pb2.AUTHORIZED_STATE_PENDING_VERIFICATION_TIMEOUT,
            added=0, by=OWN_DER)
    return env


def _wrap(envelope, bare):
    if bare:
        return envelope.SerializeToString()
    message = combined_pb2.Message()
    message.message.CopyFrom(envelope)
    message.tail.value = 1
    return message.SerializeToString()


def _error_envelope(code=12, message='Not implemented'):
    env = combined_pb2.MessageEnvelope()
    env.common.error_response.status.code = code
    env.common.error_response.status.message = message
    return env


# ── list request ────────────────────────────────────────────────────────────

def test_list_request_bytes_are_pinned():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=None) as post:
        assert api.get_authorized_clients() is None
    assert post.call_args[0][0] == PINNED_LIST_MESSAGE
    assert api._envelope_bytes(PINNED_LIST_MESSAGE) == PINNED_LIST_ENVELOPE


@v2026_only
def test_list_request_matches_the_v2026_schema():
    pb = _tx.Message()
    pb.message.deliveryChannel = _ed.DELIVERY_CHANNEL_LOCAL_HTTPS
    pb.message.sender.local = _ed.LOCAL_PARTICIPANT_INSTALLER
    pb.message.recipient.din = DIN
    pb.message.authorization.listAuthorizedClientsRequest.SetInParent()
    pb.tail.value = 1
    assert pb.SerializeToString() == PINNED_LIST_MESSAGE


@pytest.mark.parametrize('v1r,auth_mode,bare', [
    (False, AuthMode.BASIC, False),
    (False, AuthMode.BEARER, True),
    (True, AuthMode.BASIC, True),
])
def test_list_parses_each_transport(v1r, auth_mode, bare):
    api = _make_api(v1r=v1r, auth_mode=auth_mode)
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), bare)):
        result = api.get_authorized_clients()
    assert result['enable_line_switch_off'] is False
    own, other = result['clients']
    assert own == {
        'fingerprint': hashlib.sha256(OWN_DER).hexdigest(),
        'type': 'CUSTOMER_MOBILE_APP',
        'key_type': 'RSA',
        'roles': ['CUSTOMER'],
        'state': 'VERIFIED',
        'verification': 'PRESENCE_PROOF',
        'added_time': '2024-10-27T03:33:20+00:00',
        'authorized_by': None,
        'current_key': True if v1r else None,
    }
    assert other['state'] == 'PENDING_VERIFICATION_TIMEOUT'
    assert other['added_time'] is None
    assert other['authorized_by'] == fingerprint(OWN_DER)
    assert other['current_key'] is (False if v1r else None)


def test_default_output_has_no_descriptions_identifiers_or_keys():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), False)):
        result = api.get_authorized_clients()
    text = repr(result)
    assert DESCRIPTION not in text and IDENTIFIER not in text
    assert all('public_key' not in c and 'description' not in c for c in result['clients'])


def test_details_add_description_identifier_and_key():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), False)):
        result = api.get_authorized_clients(details=True)
    own = result['clients'][0]
    assert own['description'] == DESCRIPTION
    assert own['identifier'] == IDENTIFIER
    assert base64.b64decode(own['public_key']) == OWN_DER


def test_descriptions_never_reach_debug_logs(caplog):
    api = _make_api()
    caplog.set_level(logging.DEBUG)
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), False)):
        api.get_authorized_clients(details=True)
    assert DESCRIPTION not in caplog.text and IDENTIFIER not in caplog.text
    assert base64.b64encode(OWN_DER).decode() not in caplog.text


def test_list_is_cached_and_failures_are_not():
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=None) as post:
        assert api.get_authorized_clients() is None
        assert api.get_authorized_clients() is None
    assert post.call_count == 2
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), False)) as post:
        first = api.get_authorized_clients()
        second = api.get_authorized_clients()
        api.get_authorized_clients(force=True)
    assert first == second
    assert post.call_count == 2


def test_list_error_response_is_logged(caplog):
    api = _make_api()
    with patch.object(api, '_post_tedapi', return_value=_wrap(_error_envelope(), False)):
        assert api.get_authorized_clients() is None
    assert 'gateway returned error 12: Not implemented' in caplog.text


def test_list_unexpected_and_undecodable_replies(caplog):
    api = _make_api()
    env = combined_pb2.MessageEnvelope()
    env.common.SetInParent()
    with patch.object(api, '_post_tedapi', return_value=_wrap(env, False)):
        assert api.get_authorized_clients() is None
    assert 'unexpected response' in caplog.text
    with patch.object(api, '_post_tedapi', return_value=b'\xff\xff\xff'):
        assert api.get_authorized_clients(force=True) is None
    assert 'undecodable response' in caplog.text


def test_list_not_connected():
    api = _make_api()
    api.din = None
    with patch.object(api, 'connect', return_value=None):
        assert api.get_authorized_clients() is None


@v2026_only
def test_list_reply_built_with_the_v2026_schema_parses():
    env = _ed.MessageEnvelope()
    rec = env.authorization.listAuthorizedClientsResponse.clients.add()
    rec.type = 1
    rec.keyType = 1
    rec.publicKey = OTHER_DER
    rec.roles.append(1)
    rec.state = 3
    rec.verification = 4
    rec.addedTime.seconds = 1730000000
    rec.authorizedByPublicKey = OWN_DER
    env.authorization.listAuthorizedClientsResponse.enableLineSwitchOff = True
    api = _make_api(v1r=True)
    with patch.object(api, '_post_tedapi', return_value=env.SerializeToString()):
        result = api.get_authorized_clients()
    client = result['clients'][0]
    assert result['enable_line_switch_off'] is True
    assert (client['state'], client['verification']) == ('VERIFIED', 'HERMES_COMMAND')
    assert client['authorized_by'] == fingerprint(OWN_DER)
    assert client['current_key'] is False


# ── add ─────────────────────────────────────────────────────────────────────

def _add_reply(key=OTHER_DER):
    env = combined_pb2.MessageEnvelope()
    _record(env.authorization.add_authorized_client_response.client, key,
            state=combined_pb2.AUTHORIZED_STATE_PENDING_VERIFICATION)
    return env.SerializeToString()


@pytest.mark.parametrize('key', [OTHER_DER, OTHER_SPKI, OTHER_PEM, OTHER_PEM.decode(), OTHER_PRIVATE_PEM,
                                 base64.b64encode(OTHER_DER).decode(), base64.b64encode(OTHER_SPKI).decode()])
def test_add_sends_pkcs1_der_for_any_key_form(key):
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _add_reply()
    result = api.add_authorized_client(key, description='HA test')
    sent = combined_pb2.MessageEnvelope()
    sent.ParseFromString(api.v1r_transport.post_v1r.call_args[0][0])
    req = sent.authorization.add_authorized_client_request
    assert req.public_key == OTHER_DER
    assert req.description == 'HA test'
    assert req.type == combined_pb2.AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP
    assert req.key_type == combined_pb2.AUTHORIZED_KEY_TYPE_RSA
    assert result['state'] == 'PENDING_VERIFICATION'
    assert result['fingerprint'] == fingerprint(OTHER_DER)
    assert result['current_key'] is False
    assert result['description'] == DESCRIPTION


def test_add_command_envelope_bytes():
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _add_reply()
    api.add_authorized_client(OTHER_DER, description='x')
    payload, din = api.v1r_transport.post_v1r.call_args[0]
    assert din == DIN
    assert payload.startswith(COMMAND_HEADER + b'\x62')


@v2026_only
def test_add_command_matches_the_v2026_schema():
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _add_reply()
    api.add_authorized_client(OTHER_DER, description='HA test')
    env = _ed.MessageEnvelope()
    env.deliveryChannel = _ed.DELIVERY_CHANNEL_HERMES_COMMAND
    env.sender.authorizedClient = _ed.AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP
    env.recipient.din = DIN
    req = env.authorization.addAuthorizedClientRequest
    req.type = _ed.AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP
    req.description = 'HA test'
    req.keyType = _ed.AUTHORIZED_KEY_TYPE_RSA
    req.publicKey = OTHER_DER
    assert api.v1r_transport.post_v1r.call_args[0][0] == env.SerializeToString()


@pytest.mark.parametrize('key', [EC_PEM, b'', '', 'not a key!', b'\x00\x01garbage', 42])
def test_add_rejects_bad_keys_without_sending(key):
    """An invalid argument raises ValueError, as the other setters do."""
    api = _make_api(v1r=True)
    with pytest.raises(ValueError):
        api.add_authorized_client(key)
    api.v1r_transport.post_v1r.assert_not_called()


def test_add_needs_v1r(caplog):
    api = _make_api()
    with patch.object(api, '_post_tedapi') as post:
        assert api.add_authorized_client(OTHER_DER) is None
    post.assert_not_called()
    assert 'add_authorized_client requires v1r transport' in caplog.text


def test_add_gateway_error_and_no_reply(caplog):
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _error_envelope(7, 'Permission denied').SerializeToString()
    assert api.add_authorized_client(OTHER_DER) is None
    assert 'gateway returned error 7: Permission denied' in caplog.text
    api.v1r_transport.post_v1r.return_value = None
    assert api.add_authorized_client(OTHER_DER) is None
    assert 'add_authorized_client: the gateway did not confirm the request' in caplog.text
    assert 'refused' not in caplog.text


def test_add_transport_exception_is_logged(caplog):
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.side_effect = RuntimeError('boom')
    assert api.add_authorized_client(OTHER_DER) is None
    assert 'add_authorized_client failed: boom' in caplog.text


def test_add_without_write_transport_or_connection(caplog):
    api = _make_api(v1r=True)
    with patch.object(api, '_v1r_write_transport', return_value=None):
        assert api.add_authorized_client(OTHER_DER) is None
    assert 'requires an available signed-v1r transport' in caplog.text
    api.din = None
    with patch.object(api, 'connect', return_value=None):
        assert api.add_authorized_client(OTHER_DER) is None
    assert 'Not connected - unable to add_authorized_client' in caplog.text


def test_add_and_remove_drop_the_cached_list():
    api = _make_api(v1r=True)
    api._cache_put('authorized_clients', AuthorizedClients())
    api.v1r_transport.post_v1r.return_value = _add_reply()
    api.add_authorized_client(OTHER_DER)
    assert 'authorized_clients' not in api.pwcache
    api._cache_put('authorized_clients', AuthorizedClients())
    api.v1r_transport.post_v1r.return_value = None
    assert api.remove_authorized_client(OTHER_DER) is False
    assert 'authorized_clients' not in api.pwcache


# ── remove ──────────────────────────────────────────────────────────────────

def _remove_reply():
    env = combined_pb2.MessageEnvelope()
    env.authorization.remove_authorized_client_response.SetInParent()
    return env.SerializeToString()


def test_remove_command_bytes_are_pinned():
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _remove_reply()
    assert api.remove_authorized_client(b'\x01\x02\x03') is True
    # AuthorizationMessages field 3 (tag 0x1a) carrying public_key (tag 0x0a).
    assert api.v1r_transport.post_v1r.call_args[0][0] == COMMAND_HEADER + b'\x62\x07\x1a\x05\x0a\x03\x01\x02\x03'


@pytest.mark.parametrize('key', [OTHER_DER, base64.b64encode(OTHER_DER).decode(), OTHER_PEM, OTHER_PRIVATE_PEM])
def test_remove_accepts_listed_base64_der_or_pem(key):
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _remove_reply()
    assert api.remove_authorized_client(key) is True
    sent = combined_pb2.MessageEnvelope()
    sent.ParseFromString(api.v1r_transport.post_v1r.call_args[0][0])
    assert sent.authorization.remove_authorized_client_request.public_key == OTHER_DER


def test_remove_by_fingerprint_prefix():
    api = _make_api(v1r=True)
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), True)):
        api.v1r_transport.post_v1r.return_value = _remove_reply()
        assert api.remove_authorized_client(fingerprint(OTHER_DER)[:8].upper()) is True
    sent = combined_pb2.MessageEnvelope()
    sent.ParseFromString(api.v1r_transport.post_v1r.call_args[0][0])
    assert sent.authorization.remove_authorized_client_request.public_key == OTHER_DER


def test_remove_by_fingerprint_needs_a_unique_match(caplog):
    api = _make_api(v1r=True)
    env = _list_envelope()
    _record(env.authorization.list_authorized_clients_response.clients.add(), OTHER_DER)
    with patch.object(api, '_post_tedapi', return_value=_wrap(env, True)):
        assert api.remove_authorized_client(fingerprint(OTHER_DER)[:8]) is False
        assert api.remove_authorized_client('00000000') is False
    api.v1r_transport.post_v1r.assert_not_called()
    assert 'matches 2 clients' in caplog.text and 'matches 0 clients' in caplog.text
    with patch.object(api, '_post_tedapi', return_value=None):
        assert api.remove_authorized_client('00000000') is False
    assert 'could not list clients' in caplog.text


def test_remove_refuses_the_current_key_unless_allowed(caplog):
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _remove_reply()
    assert api.remove_authorized_client(OWN_DER) is False
    api.v1r_transport.post_v1r.assert_not_called()
    assert 'refusing to remove the key this connection signs with' in caplog.text
    assert api.remove_authorized_client(OWN_DER, allow_current_key=True) is True


def test_remove_refuses_current_key_found_by_fingerprint():
    api = _make_api(v1r=True)
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), True)):
        assert api.remove_authorized_client(fingerprint(OWN_DER)[:12]) is False
    api.v1r_transport.post_v1r.assert_not_called()


@pytest.mark.parametrize('key', ['', b'', 'not base64!',
                                 '-----BEGIN PUBLIC KEY-----\nxx\n-----END PUBLIC KEY-----', 42])
def test_remove_rejects_bad_keys(key):
    """An invalid argument raises ValueError, as the other setters do."""
    api = _make_api(v1r=True)
    with pytest.raises(ValueError):
        api.remove_authorized_client(key)
    api.v1r_transport.post_v1r.assert_not_called()


def test_fingerprint_lookup_reads_through_the_locked_getter():
    """The lookup is a get_authorized_clients() read under its API lock, like
    the other TEDAPI reads, not an unlocked fetch."""
    api = _make_api(v1r=True)
    with patch.object(api, '_post_tedapi', return_value=_wrap(_list_envelope(), True)), \
            patch.object(api, '_api_lock', wraps=api._api_lock) as lock:
        api.v1r_transport.post_v1r.return_value = _remove_reply()
        assert api.remove_authorized_client(fingerprint(OTHER_DER)[:8]) is True
    assert [getattr(c.args[0], '__name__', None) for c in lock.call_args_list] == ['get_authorized_clients']


def test_remove_needs_v1r_and_reports_errors(caplog):
    api = _make_api()
    with patch.object(api, '_post_tedapi') as post:
        assert api.remove_authorized_client(OTHER_DER) is False
        assert api.remove_authorized_client('abcdef12') is False   # no lookup read either
    post.assert_not_called()
    assert 'remove_authorized_client requires v1r transport' in caplog.text
    api = _make_api(v1r=True)
    api.v1r_transport.post_v1r.return_value = _error_envelope(5, 'not found').SerializeToString()
    assert api.remove_authorized_client(OTHER_DER) is False
    assert 'gateway returned error 5: not found' in caplog.text
    api.v1r_transport.post_v1r.side_effect = RuntimeError('boom')
    assert api.remove_authorized_client(OTHER_DER) is False
    assert 'remove_authorized_client failed: boom' in caplog.text


def test_current_key_comes_from_either_v1r_transport():
    api = _make_api(v1r=True)
    api.v1r_transport = None
    assert api._current_public_key() is None
    wifi = TEDAPIv1r.__new__(TEDAPIv1r)
    wifi._public_key_der = OTHER_DER
    api.wifi_v1r_transport = wifi
    assert api._current_public_key() == OTHER_DER
    assert wifi.public_key_der == OTHER_DER


# ── transport ───────────────────────────────────────────────────────────────

def test_send_authorization_message_without_din_or_with_bad_reply(caplog):
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.post_v1r = MagicMock(return_value=b'\xff\xff')
    message = combined_pb2.AuthorizationMessages()
    message.list_authorized_clients_request.SetInParent()
    assert transport.send_authorization_message('', message) is None
    assert 'send_authorization_message: no DIN' in caplog.text
    assert transport.send_authorization_message(DIN, message) is None
    assert 'send_authorization_message: failed to parse response' in caplog.text
    transport.post_v1r.return_value = None
    assert transport.send_authorization_message(DIN, message) is None


# ── model helpers ───────────────────────────────────────────────────────────

def test_unknown_enum_values_and_repr():
    client = AuthorizedClient(public_key=OTHER_DER, type=9, key_type=7, roles=[5], state=8, verification=6,
                              description=DESCRIPTION, identifier=IDENTIFIER)
    data = client.to_dict()
    assert data['type'] == 'UNKNOWN (9)' and data['state'] == 'UNKNOWN (8)'
    assert data['roles'] == ['UNKNOWN (5)']
    assert DESCRIPTION not in repr(client) and IDENTIFIER not in repr(client)
    assert enum_label(combined_pb2.AuthorizedState, 3) == 'VERIFIED'


def test_empty_added_time_is_none():
    record = combined_pb2.AuthorizationRecord()
    record.added_time.SetInParent()
    assert AuthorizedClient.from_proto(record).added_time is None


def test_key_helpers():
    assert fingerprint(b'') is None
    assert rsa_public_key_der(OTHER_PRIVATE_PEM.decode()) == OTHER_DER
    assert public_key_bytes(OTHER_SPKI) == OTHER_SPKI   # raw bytes pass through as listed
    assert public_key_bytes(bytearray(b'\x01')) == b'\x01'
    with pytest.raises(ValueError):
        public_key_bytes('====')
    with pytest.raises(ValueError):
        rsa_public_key_der(EC_PEM)


def test_details_copy_is_independent_and_timestamps_are_utc():
    env = _list_envelope()
    clients = AuthorizedClients.from_proto(env.authorization.list_authorized_clients_response)
    assert clients.clients[0].added_time == datetime(2024, 10, 27, 3, 33, 20, tzinfo=timezone.utc)
    data = clients.to_dict(details=True)
    data['clients'][0]['roles'].append('X')
    assert clients.to_dict(details=True)['clients'][0]['roles'] == ['CUSTOMER']


def test_authorization_messages_oneof():
    message = combined_pb2.AuthorizationMessages()
    message.list_authorized_clients_request.SetInParent()
    assert message.WhichOneof('message') == 'list_authorized_clients_request'
    message.remove_authorized_client_request.public_key = b'\x01'
    assert message.WhichOneof('message') == 'remove_authorized_client_request'


# ── refusals: named only when the gateway refused ──────────────────────────

TIMEOUT = combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT


def _refusing(api, fault=TIMEOUT):
    """The v1r transport's last request on this thread got ``fault`` back."""
    api.v1r_transport.post_v1r.return_value = None
    api.v1r_transport._set_request_fault(fault)
    return api


def test_refused_list_over_v1r_is_named(caplog):
    api = _refusing(_make_api(v1r=True))
    with patch.object(api, '_post_tedapi', return_value=None):
        assert api.get_authorized_clients() is None
    assert 'Authorized clients: the gateway refused the request over v1r (MESSAGEFAULT_ERROR_TIMEOUT)' in caplog.text


def test_list_failure_without_a_refusal_adds_nothing(caplog):
    """No answer without a refusal (a LAN outage, a key problem) is logged by
    the transport; with the LAN failed over, the request went over Wi-Fi and
    the LAN transport's fault is from an earlier request; outside v1r there
    is no fault to report."""
    plain = _make_api(v1r=True)
    failed_over = _refusing(_make_api(v1r=True))
    failed_over.lan_failed = True
    wifi = _make_api()
    for api in (plain, failed_over, wifi):
        with patch.object(api, '_post_tedapi', return_value=None):
            assert api.get_authorized_clients(force=True) is None
    assert 'refused' not in caplog.text


@pytest.mark.parametrize('call', [lambda api: api.add_authorized_client(OTHER_DER),
                                  lambda api: api.remove_authorized_client(OTHER_DER)],
                         ids=['add', 'remove'])
def test_refused_write_is_named(call, caplog):
    api = _refusing(_make_api(v1r=True), combined_pb2.MESSAGEFAULT_ERROR_INVALID_COMMAND)
    assert not call(api)
    assert 'the gateway refused the request (MESSAGEFAULT_ERROR_INVALID_COMMAND)' in caplog.text
    assert 'did not confirm' not in caplog.text


def _gateway(content=None, error=None) -> TEDAPIv1r:
    """A real TEDAPIv1r (no key or socket) whose gateway answers every POST
    with ``content``, or whose LAN raises ``error``."""
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.pending_verification = False
    transport.key_unknown = False
    transport._flag_lock = threading.Lock()
    transport.host = '10.42.1.1'
    transport.timeout = 5
    transport.din = DIN
    transport.key_fingerprint = 'f' * 64
    transport._private_key = MagicMock()
    transport._private_key.sign.return_value = b'\x00' * 64
    transport._public_key_der = OWN_DER
    transport.session = MagicMock()
    transport.session.post.side_effect = error
    transport.session.post.return_value = MagicMock(status_code=200, content=content)
    return transport


def _fault(fault) -> bytes:
    msg = combined_pb2.RoutableMessage()
    msg.signed_message_status.message_fault = fault
    return msg.SerializeToString()


class TestThroughTheRealTransport:
    """End to end through TEDAPIv1r.post_v1r(): a refusal is named, a LAN
    outage and a key fault (which the transport logs itself) are not."""

    def _run(self, transport, caplog):
        api = _make_api(v1r=True)
        api.v1r_transport = transport
        with warnings.catch_warnings(), caplog.at_level(logging.DEBUG):
            warnings.simplefilter('ignore')
            assert api.get_authorized_clients() is None
            assert api.add_authorized_client(OTHER_DER) is None
            assert api.remove_authorized_client(OTHER_DER) is False
        return caplog.text

    def test_timeout_fault_is_named(self, caplog):
        text = self._run(_gateway(_fault(TIMEOUT)), caplog)
        assert 'Authorized clients: the gateway refused the request over v1r (MESSAGEFAULT_ERROR_TIMEOUT)' in text
        assert 'add_authorized_client: the gateway refused the request (MESSAGEFAULT_ERROR_TIMEOUT)' in text
        assert 'remove_authorized_client: the gateway refused the request (MESSAGEFAULT_ERROR_TIMEOUT)' in text

    def test_lan_outage_is_not_a_refusal(self, caplog):
        text = self._run(_gateway(error=OSError('no route')), caplog)
        assert 'refused' not in text
        assert 'add_authorized_client: the gateway did not confirm the request' in text

    def test_key_fault_is_not_a_refusal(self, caplog):
        text = self._run(_gateway(_fault(combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID)), caplog)
        assert 'refused' not in text
        assert 'remove_authorized_client: the gateway did not confirm the request' in text
