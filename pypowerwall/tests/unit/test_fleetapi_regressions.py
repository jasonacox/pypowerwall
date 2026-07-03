"""Regression tests for FleetAPI robustness:
- PyPowerwallFleetAPI.getsites() returned None whenever siteid was unset,
  which defeated connect()'s auto-default-to-first-site logic
- FleetAPI.load_config() site auto-discovery crashed when getsites() returned
  None and could pick a vehicle (no energy_site_id) from the products list
"""
import json
from unittest.mock import MagicMock, patch

from pypowerwall.fleetapi.fleetapi import FleetAPI
from pypowerwall.fleetapi.pypowerwall_fleetapi import PyPowerwallFleetAPI


def test_getsites_without_siteid(tmp_path):
    """getsites() must return the site list even when siteid is None."""
    backend = PyPowerwallFleetAPI(email='test@example.com', authpath=str(tmp_path))
    backend.siteid = None
    backend.fleet = MagicMock()
    sites = [{'energy_site_id': 1234, 'site_name': 'Home'}]
    backend.fleet.getsites.return_value = sites
    # Used to return None because of the `if self.siteid is None` guard
    assert backend.getsites() == sites


def test_getsites_error_returns_none(tmp_path):
    backend = PyPowerwallFleetAPI(email='test@example.com', authpath=str(tmp_path))
    backend.fleet = MagicMock()
    backend.fleet.getsites.side_effect = RuntimeError('api down')
    assert backend.getsites() is None


def _write_config(tmp_path, site_id=None):
    configfile = tmp_path / 'config.fleetapi'
    configfile.write_text(json.dumps({
        'CLIENT_ID': 'cid', 'CLIENT_SECRET': 'secret', 'DOMAIN': 'example.com',
        'REDIRECT_URI': 'https://example.com', 'AUDIENCE': 'aud',
        'partner_token': 'pt', 'partner_account': {}, 'access_token': 'at',
        'refresh_token': 'rt', 'site_id': site_id,
    }))
    return str(configfile)


def test_load_config_sites_none_does_not_crash(tmp_path):
    """getsites() returning None (API error) must not TypeError in load_config()."""
    configfile = _write_config(tmp_path)
    with patch.object(FleetAPI, 'getsites', return_value=None):
        fleet = FleetAPI(configfile=configfile)  # used to raise TypeError
    assert not fleet.site_id


def test_load_config_skips_vehicles(tmp_path):
    """Products list can mix in vehicles - pick the first energy site."""
    configfile = _write_config(tmp_path)
    products = [
        {'vin': '5YJ3E1EA0000000', 'display_name': 'Car'},  # vehicle - no energy_site_id
        {'energy_site_id': 9999, 'site_name': 'Home'},
    ]
    with patch.object(FleetAPI, 'getsites', return_value=products):
        fleet = FleetAPI(configfile=configfile)
    assert fleet.site_id == 9999
