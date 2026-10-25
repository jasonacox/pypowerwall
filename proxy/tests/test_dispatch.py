"""Authenticated, non-actuating tests for local battery dispatch routes."""
import json
from io import BytesIO
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest

from proxy import server
from proxy.tests.test_csv_endpoints import UnittestHandler


@pytest.fixture
def controls(monkeypatch):
    pw = Mock()
    pw.tedapi.v1r = True
    pw.dispatch_battery_power.return_value = {'power_watts': -500.0, 'duration_seconds': 30}
    pw.resume_battery_operation.return_value = {'resume_battery_operation': True}
    cloud = Mock()
    cloud.client = None  # These commands do not require cloud credentials.
    monkeypatch.setattr(server, 'pw', pw)
    monkeypatch.setattr(server, 'pw_control', cloud)
    monkeypatch.setattr(server, 'control_secret', 'secret')
    monkeypatch.setattr(server, 'api_base_url', '')
    return pw, cloud


def post(action, **fields):
    handler = UnittestHandler()
    body = urlencode(fields).encode()
    handler.path = '/control/' + action
    handler.rfile = BytesIO(body)
    handler.headers = {'Content-Length': str(len(body))}
    handler.do_POST()
    return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())


def test_dispatch_and_resume_use_local_facade(controls):
    pw, cloud = controls
    assert post('dispatch', power_watts=-500, duration_seconds=30, token='secret') == (
        200, {'power_watts': -500.0, 'duration_seconds': 30},
    )
    pw.dispatch_battery_power.assert_called_once_with(-500.0, 30)
    assert post('resume', token='secret') == (200, {'resume_battery_operation': True})
    pw.resume_battery_operation.assert_called_once_with()
    assert not cloud.method_calls


@pytest.mark.parametrize('watts,seconds', [('nan', '30'), ('inf', '30'), ('', '30'),
    ('500', ''), ('500', '0'), ('500', '-1'), ('500', '86401'), ('500', '1.5'), ('500', 'true')])
def test_invalid_parameters_never_send(controls, watts, seconds):
    pw, _ = controls
    assert post('dispatch', power_watts=watts, duration_seconds=seconds, token='secret')[0] == 400
    pw.dispatch_battery_power.assert_not_called()


@pytest.mark.parametrize('action', ['dispatch', 'resume'])
@pytest.mark.parametrize('token', ['', 'wrong'])
def test_token_required(controls, action, token):
    pw, _ = controls
    assert post(action, power_watts=-500, duration_seconds=30, token=token)[0] == 401
    pw.dispatch_battery_power.assert_not_called()
    pw.resume_battery_operation.assert_not_called()


@pytest.mark.parametrize('action', ['dispatch', 'resume'])
def test_controls_disabled(controls, monkeypatch, action):
    pw, _ = controls
    monkeypatch.setattr(server, 'control_secret', '')
    assert post(action, power_watts=-500, duration_seconds=30, token='secret')[0] == 400
    pw.dispatch_battery_power.assert_not_called()
    pw.resume_battery_operation.assert_not_called()


@pytest.mark.parametrize('action', ['dispatch', 'resume'])
def test_requires_v1r_without_cloud_fallback(controls, action):
    pw, cloud = controls
    pw.tedapi = None
    cloud.client = Mock()
    status, body = post(action, power_watts=-500, duration_seconds=30, token='secret')
    assert status == 400
    assert 'v1r' in body['error']
    pw.dispatch_battery_power.assert_not_called()
    pw.resume_battery_operation.assert_not_called()
    assert not cloud.method_calls


@pytest.mark.parametrize('action,method', [('dispatch', 'dispatch_battery_power'),
                                          ('resume', 'resume_battery_operation')])
@pytest.mark.parametrize('failure', [None, False, {'ERROR': 'unsupported'}, OSError('offline')])
def test_failed_ack_is_an_error(controls, action, method, failure):
    pw, _ = controls
    if isinstance(failure, Exception):
        getattr(pw, method).side_effect = failure
    else:
        getattr(pw, method).return_value = failure
    assert post(action, power_watts=500, duration_seconds=30, token='secret')[0] == 400
