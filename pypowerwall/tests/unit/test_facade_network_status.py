"""Facade tests for Powerwall.network_status(): it delegates to the TEDAPI
backend when one is connected and degrades to None (never raises) otherwise."""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall import Powerwall

STATUS = {
    'wifi': {'enabled': True, 'signal_strength_percent': 58},
    'eth': {'enabled': True, 'signal_strength_percent': 0},
    'gsm': None,
}


@pytest.fixture(name='pw')
def fixture_powerwall():
    # Construction must not need the network: leave connect() out of it and
    # attach the backend pieces each test needs.
    with patch.object(Powerwall, 'connect', return_value=False):
        pw = Powerwall(host='', password='', email='test@example.com', cloudmode=True)
    pw.client = MagicMock()
    return pw


def _attach_tedapi(pw, mode='v1r', result=None):
    pw.tedapi = MagicMock()
    pw.tedapi.get_network_status.return_value = STATUS if result is None else result
    pw.tedapi_mode = mode
    return pw.tedapi


@pytest.mark.parametrize('mode', ['full', 'hybrid', 'v1r'])
def test_delegates_to_tedapi(pw, mode):
    tedapi = _attach_tedapi(pw, mode)
    assert pw.network_status() == STATUS
    tedapi.get_network_status.assert_called_once_with(force=False, details=False)


def test_passes_details_and_force(pw):
    tedapi = _attach_tedapi(pw)
    pw.network_status(details=True, force=True)
    tedapi.get_network_status.assert_called_once_with(force=True, details=True)


def test_jsonformat(pw):
    _attach_tedapi(pw)
    out = pw.network_status(jsonformat=True)
    assert isinstance(out, str)
    assert json.loads(out) == STATUS


def test_gateway_failure_returns_none(pw):
    tedapi = _attach_tedapi(pw)
    tedapi.get_network_status.return_value = None
    assert pw.network_status() is None
    assert pw.network_status(jsonformat=True) is None


def test_requires_tedapi(pw, caplog):
    """Cloud / FleetAPI / local-only connections have no TEDAPI (pw.tedapi is False)."""
    assert pw.tedapi is False
    with caplog.at_level(logging.ERROR, logger='pypowerwall'):
        assert pw.network_status() is None
        assert pw.network_status(details=True, jsonformat=True) is None
    assert 'network_status requires a TEDAPI connection' in caplog.text


def test_no_client_returns_none(pw):
    pw.client = None
    _attach_tedapi(pw)
    assert pw.network_status() is None
    pw.tedapi.get_network_status.assert_not_called()
