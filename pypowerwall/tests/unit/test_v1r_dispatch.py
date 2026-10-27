"""Non-actuating battery dispatch regression tests.

Author: Jason A. Cox
https://github.com/jasonacox/pypowerwall

Pin the tesla-protocol field numbers and exercise real envelope parsing at
the post_v1r boundary. No test loads a key or contacts a Powerwall.
"""
import time
from unittest.mock import Mock

import pytest

from pypowerwall import Powerwall
from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as pb
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI
from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r


ACK = bytes.fromhex('2a03b20200')  # envelope.teg.dispatch_battery_power_response


def transport_for(reply=ACK):
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.post_v1r = Mock(return_value=reply)
    return transport


def core_for(transport):
    core = TEDAPI.__new__(TEDAPI)
    core.v1r, core.v1r_transport, core.din = True, transport, 'TEST_DIN'
    core.failover = True
    core.lan_failed = False
    core.wifi_v1r_fallback = False
    core.wifi_v1r_transport = None
    core._wifi_v1r_ready_until = 0.0
    core.wifi_session = None
    core.connect = Mock(return_value=False)
    core.pwcache = {'status': {}, 'controller': {}, 'pw3_vitals': {}, 'config': {'keep': True}}
    core.pwcachetime = dict.fromkeys(core.pwcache, 123)
    return core


@pytest.mark.parametrize('watts', [-500, 500, 5000, 0, 12.5])
def test_dispatch_wire_format(watts):
    transport = transport_for()
    assert transport.dispatch_battery_power('TEST_DIN', watts, 30) == {
        'power_watts': watts, 'duration_seconds': 30,
    }
    payload, din = transport.post_v1r.call_args.args
    assert din == 'TEST_DIN'
    envelope = pb.MessageEnvelope.FromString(payload)
    request = envelope.teg.dispatch_battery_power_request
    assert envelope.deliveryChannel == pb.DELIVERY_CHANNEL_HERMES_COMMAND
    assert envelope.sender.authorizedClient == 1
    assert envelope.recipient.din == 'TEST_DIN'
    assert envelope.teg.WhichOneof('message') == 'dispatch_battery_power_request'
    assert request.HasField('real_power')
    assert not request.HasField('resume_device_mode')
    assert request.real_power.power_watts == watts
    assert request.real_power.duration_seconds == 30
    if watts == -500:
        assert payload.hex() == (
            '0802120220011a0a0a08544553545f44494e'
            '2a10aa020d120b090000000000407fc0101e'
        )
    if watts == 5000:
        # Pin the 5000 W / 30 s command with a normalized TEST_DIN recipient.
        assert payload.hex() == (
            '0802120220011a0a0a08544553545f44494e'
            '2a10aa020d120b09000000000088b340101e'
        )


def test_dispatch_routes_through_strict_wifi_v1r_after_failover():
    lan = transport_for()
    wifi = transport_for()
    core = core_for(lan)
    core.wifi_v1r_transport = wifi
    core.wifi_v1r_fallback = True
    core.lan_failed = True
    core._wifi_v1r_ready_until = time.monotonic() + 60.0
    assert core.dispatch_battery_power(-500, 30) == {
        'power_watts': -500, 'duration_seconds': 30,
    }
    wifi.post_v1r.assert_called_once()
    lan.post_v1r.assert_not_called()


def test_dispatch_probe_false_does_not_fall_back_to_lan():
    lan = transport_for()
    core = core_for(lan)
    core.wifi_v1r_transport = transport_for()
    core.wifi_v1r_fallback = True
    core.lan_failed = True
    core._wifi_v1r_ready_until = 0.0
    core.wifi_v1r_ready = Mock(return_value=False)
    assert core.dispatch_battery_power(-500, 30) is None
    lan.post_v1r.assert_not_called()
    core.wifi_v1r_transport.post_v1r.assert_not_called()


def test_resume_wire_format():
    transport = transport_for()
    assert transport.resume_battery_operation('TEST_DIN') == {'resume_battery_operation': True}
    payload, _ = transport.post_v1r.call_args.args
    assert payload.hex() == '0802120220011a0a0a08544553545f44494e2a05aa02020a00'
    request = pb.MessageEnvelope.FromString(payload).teg.dispatch_battery_power_request
    assert request.HasField('resume_device_mode')
    assert not request.HasField('real_power')


@pytest.mark.parametrize('watts,seconds', [
    (True, 30), (None, 30), ('500', 30), (float('nan'), 30),
    (float('inf'), 30), (-float('inf'), 30), (10**1000, 30),
    (500, 0), (500, -1), (500, 86401), (500, 2**32),
    (500, 1.5), (500, True), (500, '30'), (500, None),
])
def test_invalid_inputs_fail_before_any_io(watts, seconds):
    transport = transport_for()
    core = core_for(transport)
    core.din = None
    facade = Powerwall.__new__(Powerwall)
    facade.client = Mock()
    for method in (facade.dispatch_battery_power, core.dispatch_battery_power):
        with pytest.raises(ValueError):
            method(watts, seconds)
    with pytest.raises(ValueError):
        transport.dispatch_battery_power('TEST_DIN', watts, seconds)
    core.connect.assert_not_called()
    transport.post_v1r.assert_not_called()
    facade.client.dispatch_battery_power.assert_not_called()


@pytest.mark.parametrize('seconds', [1, 86400])
def test_duration_boundaries(seconds):
    assert transport_for().dispatch_battery_power('TEST_DIN', 0, seconds) is not None


@pytest.mark.parametrize('reply', [None, b'', b'bad protobuf', b'\x2a\x00',
    bytes.fromhex('2a022200'),  # valid but unrelated TEG response
    bytes.fromhex('22170a150a13080c120f6e6f7420696d706c656d656e746564'),
])
@pytest.mark.parametrize('resume', [False, True])
def test_missing_bad_or_error_ack_is_failure(reply, resume):
    transport = transport_for(reply)
    if resume:
        assert transport.resume_battery_operation('TEST_DIN') is None
    else:
        assert transport.dispatch_battery_power('TEST_DIN', -500, 30) is None


def test_rejection_status_is_logged(caplog):
    reply = pb.MessageEnvelope()
    reply.common.error_response.status.code = 7
    reply.common.error_response.status.message = 'permission denied'
    transport = transport_for(reply.SerializeToString())
    assert transport.dispatch_battery_power('TEST_DIN', 500, 30) is None
    assert 'permission denied (status code 7)' in caplog.text


def test_missing_din_and_transport_errors_do_not_report_success():
    transport = transport_for()
    assert transport.dispatch_battery_power('', 500, 30) is None
    transport.post_v1r.assert_not_called()
    transport.post_v1r.side_effect = OSError('offline')
    assert transport.resume_battery_operation('TEST_DIN') is None


def test_facade_backend_and_core_route_to_v1r_and_invalidate_samples():
    transport = transport_for()
    core = core_for(transport)
    backend = PyPowerwallTEDAPI.__new__(PyPowerwallTEDAPI)
    backend.tedapi = core
    facade = Powerwall.__new__(Powerwall)
    facade.client = backend
    assert facade.dispatch_battery_power(-500, 30) == {'power_watts': -500, 'duration_seconds': 30}
    assert core.pwcache == {'config': {'keep': True}}
    assert core.pwcachetime == {'config': 123}
    assert facade.resume_battery_operation() == {'resume_battery_operation': True}
    assert transport.post_v1r.call_count == 2


def test_failed_command_preserves_cache():
    core = core_for(transport_for(None))
    assert core.dispatch_battery_power(500, 30) is None
    assert {'status', 'controller', 'pw3_vitals'} <= set(core.pwcache)


@pytest.mark.parametrize('v1r,connected', [(False, True), (True, False)])
def test_unsupported_or_disconnected_core(v1r, connected):
    transport = transport_for()
    core = core_for(transport)
    core.v1r = v1r
    core.din = 'TEST_DIN' if connected else None
    assert core.dispatch_battery_power(-500, 30) is None
    assert core.resume_battery_operation() is None
    transport.post_v1r.assert_not_called()


@pytest.mark.parametrize('client', [None, object()])
def test_unsupported_or_absent_facade_client(client):
    facade = Powerwall.__new__(Powerwall)
    facade.client = client
    assert facade.dispatch_battery_power(500, 30) is None
    assert facade.resume_battery_operation() is None


def test_schema_field_contract():
    fields = pb.TEGMessages.DESCRIPTOR.fields_by_name
    assert fields['dispatch_battery_power_request'].number == 37
    assert fields['dispatch_battery_power_response'].number == 38
    request = pb.TEGAPIDispatchBatteryPowerRequest.DESCRIPTOR
    assert not request.oneofs
    assert request.fields_by_name['resume_device_mode'].number == 1
    assert request.fields_by_name['real_power'].number == 2
    real = request.fields_by_name['real_power'].message_type.fields_by_name
    assert (real['power_watts'].number, real['power_watts'].type) == (1, 1)  # double
    assert (real['duration_seconds'].number, real['duration_seconds'].type) == (2, 13)  # uint32


@pytest.mark.parametrize('watts, action', [(5000, 'discharge 5000 W'), (-2000, 'charge 2000 W'), (0, 'hold 0 W')])
def test_accepted_dispatch_logs_a_use_at_your_own_risk_warning(caplog, watts, action):
    transport = transport_for()
    with caplog.at_level('WARNING', logger='pypowerwall.tedapi.tedapi_v1r'):
        assert transport.dispatch_battery_power('TEST_DIN', watts, 30)
    [record] = [r for r in caplog.records if 'Battery dispatch accepted' in r.getMessage()]
    assert record.levelname == 'WARNING'
    assert f'{action} for 30 s' in record.getMessage()
    assert 'use at your own risk' in record.getMessage()


def test_failed_dispatch_and_resume_log_no_acceptance(caplog):
    transport = transport_for(None)
    assert transport.dispatch_battery_power('TEST_DIN', 500, 30) is None
    assert transport_for().resume_battery_operation('TEST_DIN') == {'resume_battery_operation': True}
    assert 'Battery dispatch accepted' not in caplog.text
