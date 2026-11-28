"""Facade tests for Powerwall.authorized_clients / add_authorized_client /
remove_authorized_client: they delegate to the TEDAPI backend and degrade to
None / False (never raise) without one; the writes need v1r."""
import json
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall import Powerwall

CLIENTS = {'clients': [{'fingerprint': 'ab' * 32, 'state': 'VERIFIED'}], 'enable_line_switch_off': False}


@pytest.fixture(name='pw')
def fixture_powerwall():
    with patch.object(Powerwall, 'connect', return_value=False):
        pw = Powerwall(host='', password='', email='test@example.com', cloudmode=True)
    pw.client = MagicMock()
    return pw


def _attach_tedapi(pw, mode='v1r'):
    pw.tedapi = MagicMock()
    pw.tedapi.get_authorized_clients.return_value = CLIENTS
    pw.tedapi.add_authorized_client.return_value = {'state': 'PENDING_VERIFICATION'}
    pw.tedapi.remove_authorized_client.return_value = True
    pw.tedapi_mode = mode
    return pw.tedapi


@pytest.mark.parametrize('mode', ['full', 'hybrid', 'v1r'])
def test_list_delegates_in_any_tedapi_mode(pw, mode):
    tedapi = _attach_tedapi(pw, mode)
    assert pw.authorized_clients() == CLIENTS
    tedapi.get_authorized_clients.assert_called_once_with(force=False, details=False)


def test_list_details_force_and_json(pw):
    tedapi = _attach_tedapi(pw)
    out = pw.authorized_clients(details=True, force=True, jsonformat=True)
    tedapi.get_authorized_clients.assert_called_once_with(force=True, details=True)
    assert json.loads(out) == CLIENTS


def test_positional_order_matches_the_other_getters(pw):
    """jsonformat comes first, as in vitals(jsonformat), alerts(jsonformat, ...)
    and network_status(jsonformat, ...): authorized_clients(True) means JSON."""
    tedapi = _attach_tedapi(pw)
    assert json.loads(pw.authorized_clients(True)) == CLIENTS
    tedapi.get_authorized_clients.assert_called_once_with(force=False, details=False)
    tedapi.get_authorized_clients.reset_mock()
    assert pw.authorized_clients(False, True, True) == CLIENTS
    tedapi.get_authorized_clients.assert_called_once_with(force=True, details=True)


def test_bad_keys_raise_like_the_other_setters(pw):
    """An invalid argument raises ValueError (as set_grid_export('bad') does)."""
    tedapi = _attach_tedapi(pw)
    tedapi.add_authorized_client.side_effect = ValueError('only RSA keys can be added')
    tedapi.remove_authorized_client.side_effect = ValueError('public key is empty')
    with pytest.raises(ValueError):
        pw.add_authorized_client('KEY')
    with pytest.raises(ValueError):
        pw.remove_authorized_client('')


def test_list_failure_returns_none(pw):
    tedapi = _attach_tedapi(pw)
    tedapi.get_authorized_clients.return_value = None
    assert pw.authorized_clients(jsonformat=True) is None


def test_list_without_tedapi(pw, caplog):
    pw.tedapi = False
    pw.tedapi_mode = None
    assert pw.authorized_clients() is None
    assert 'get_authorized_clients requires a TEDAPI connection' in caplog.text


def test_add_and_remove_delegate_on_v1r(pw):
    tedapi = _attach_tedapi(pw)
    assert pw.add_authorized_client('KEY', description='HA') == {'state': 'PENDING_VERIFICATION'}
    tedapi.add_authorized_client.assert_called_once_with('KEY', description='HA')
    assert pw.remove_authorized_client('abcdef12') is True
    tedapi.remove_authorized_client.assert_called_once_with('abcdef12', allow_current_key=False)
    tedapi.remove_authorized_client.return_value = None
    assert pw.remove_authorized_client('abcdef12', allow_current_key=True) is False


@pytest.mark.parametrize('mode', ['full', 'hybrid'])
def test_writes_need_v1r(pw, mode, caplog):
    tedapi = _attach_tedapi(pw, mode)
    assert pw.add_authorized_client('KEY') is None
    assert pw.remove_authorized_client('KEY') is False
    tedapi.add_authorized_client.assert_not_called()
    tedapi.remove_authorized_client.assert_not_called()
    assert 'add_authorized_client requires v1r LAN mode' in caplog.text


def test_no_client(pw):
    pw.client = None
    assert pw.authorized_clients() is None
    assert pw.add_authorized_client('KEY') is None
    assert pw.remove_authorized_client('KEY') is False
