"""Regression tests for FleetAPI.new_token() - the token refresh must never
wedge permanently when the refresh request fails (see fleetapi.py new_token).
"""
import threading
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.fleetapi.fleetapi import FleetAPI


@pytest.fixture(name="fleet")
def fixture_fleetapi(tmp_path):
    # Nonexistent config file - load_config() is a no-op, no network involved
    fleet = FleetAPI(configfile=str(tmp_path / 'nonexistent.fleetapi'))
    fleet.CLIENT_ID = 'client-id'
    fleet.access_token = 'old-access'
    fleet.refresh_token = 'old-refresh'
    return fleet


def _response(status_code=200, json_body=None, json_exc=None):
    response = MagicMock()
    response.status_code = status_code
    if json_exc:
        response.json.side_effect = json_exc
    else:
        response.json.return_value = json_body or {}
    return response


def test_new_token_success_updates_tokens(fleet):
    resp = _response(200, {'access_token': 'new-access', 'refresh_token': 'new-refresh'})
    with patch('pypowerwall.fleetapi.fleetapi._http2_request', return_value=resp), \
         patch.object(fleet, 'save_config') as mock_save:
        fleet.new_token()
    assert fleet.access_token == 'new-access'
    assert fleet.refresh_token == 'new-refresh'
    mock_save.assert_called_once()
    assert not fleet.refresh_lock.locked()


def test_new_token_http_error_does_not_wedge(fleet):
    # Non-200 response: tokens unchanged, lock released for the next attempt
    resp = _response(500, json_exc=ValueError('not json'))
    with patch('pypowerwall.fleetapi.fleetapi._http2_request', return_value=resp):
        fleet.new_token()
    assert fleet.access_token == 'old-access'
    assert not fleet.refresh_lock.locked()


def test_new_token_invalid_json_does_not_wedge(fleet):
    # 200 with an unparseable body must not raise or hold the lock
    resp = _response(200, json_exc=ValueError('invalid json'))
    with patch('pypowerwall.fleetapi.fleetapi._http2_request', return_value=resp):
        fleet.new_token()
    assert fleet.access_token == 'old-access'
    assert not fleet.refresh_lock.locked()


def test_new_token_exception_releases_lock(fleet):
    # Request exception propagates but must release the lock (was: refreshing=True forever)
    with patch('pypowerwall.fleetapi.fleetapi._http2_request',
               side_effect=ConnectionError('network down')):
        with pytest.raises(ConnectionError):
            fleet.new_token()
    assert not fleet.refresh_lock.locked()
    # A subsequent refresh must still work
    resp = _response(200, {'access_token': 'new-access', 'refresh_token': 'new-refresh'})
    with patch('pypowerwall.fleetapi.fleetapi._http2_request', return_value=resp), \
         patch.object(fleet, 'save_config'):
        fleet.new_token()
    assert fleet.access_token == 'new-access'


def test_new_token_concurrent_refresh_skipped(fleet):
    # While another thread holds the lock, new_token() returns without a request
    assert isinstance(fleet.refresh_lock, type(threading.Lock()))
    fleet.refresh_lock.acquire()
    try:
        with patch('pypowerwall.fleetapi.fleetapi._http2_request') as mock_req:
            fleet.new_token()
        mock_req.assert_not_called()
    finally:
        fleet.refresh_lock.release()
    assert fleet.access_token == 'old-access'
