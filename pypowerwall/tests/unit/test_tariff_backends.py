"""Tests for tariff endpoint parity across non-local backends and the facade."""
from unittest.mock import MagicMock

from pypowerwall import Powerwall
from pypowerwall.fleetapi.pypowerwall_fleetapi import PyPowerwallFleetAPI
from pypowerwall.pypowerwall_base import PyPowerwallBase
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI


def _bare_backend(cls):
    backend = object.__new__(cls)
    PyPowerwallBase.__init__(backend, 'test@example.com')
    backend.poll_api_map = backend.init_poll_api_map()
    backend.post_api_map = backend.init_post_api_map()
    return backend


def test_fleetapi_tariff_read_uses_site_info():
    backend = _bare_backend(PyPowerwallFleetAPI)
    backend.fleet = MagicMock()
    tariff = {'code': 'FLEET', 'currency': 'EUR'}
    backend.fleet.get_tariff.return_value = tariff

    assert backend.poll('/api/tesla/tariff_rate', force=True) == tariff
    backend.fleet.get_tariff.assert_called_once_with(force=True)


def test_fleetapi_tou_write_is_normalized():
    backend = _bare_backend(PyPowerwallFleetAPI)
    backend.fleet = MagicMock()
    backend.fleet.set_time_of_use_settings.return_value = {
        'response': {'Message': 'Updated', 'Code': 201}
    }
    payload = {'tou_settings': {'optimization_strategy': 'economics'}}

    assert backend.post('/api/tesla/time_of_use_settings', payload, None) == {
        'Message': 'Updated',
        'Code': 201,
    }
    backend.fleet.set_time_of_use_settings.assert_called_once_with(payload)


def test_tedapi_tariff_endpoints_return_mock_shapes():
    backend = _bare_backend(PyPowerwallTEDAPI)

    assert backend.poll('/api/tesla/tariff_rate') == {}
    assert backend.post(
        '/api/tesla/time_of_use_settings',
        {'tou_settings': {}},
        None,
    ) == {'Message': 'Not implemented', 'Code': 501}


def test_powerwall_tariff_facade_wraps_tou_settings():
    pw = object.__new__(Powerwall)
    pw.client = MagicMock()
    pw.client.poll.return_value = {'code': 'TEST'}
    pw.client.post.return_value = {'Message': 'Updated', 'Code': 201}

    assert pw.get_tariff(force=True) == {'code': 'TEST'}
    pw.client.poll.assert_called_once_with('/api/tesla/tariff_rate', True, False, False)

    tou_settings = {'optimization_strategy': 'economics'}
    assert pw.set_tariff(tou_settings) == {'Message': 'Updated', 'Code': 201}
    pw.client.post.assert_called_once_with(
        '/api/tesla/time_of_use_settings',
        {'tou_settings': tou_settings},
        None,
        False,
        False,
    )
