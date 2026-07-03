"""Regression tests: when connect() fails for all modes, self.client stays None
and every facade method must degrade to None (or False) instead of raising a
raw AttributeError on every call.
"""
from unittest.mock import patch

import pytest

from pypowerwall import Powerwall


@pytest.fixture(name="pw")
def fixture_disconnected_powerwall():
    # Simulate connect() failing for all modes - client remains None
    with patch.object(Powerwall, 'connect', return_value=False):
        pw = Powerwall(host='', password='', email='test@example.com', cloudmode=True)
    assert pw.client is None
    return pw


def test_poll_returns_none(pw):
    assert pw.poll('/api/status') is None
    assert pw.poll('/api/status', jsonformat=True) is None


def test_post_returns_none(pw):
    assert pw.post('/api/operation', payload={'backup_reserve_percent': 20}) is None


def test_vitals_returns_none(pw):
    assert pw.vitals() is None
    assert pw.vitals(jsonformat=True) is None


def test_get_time_remaining_returns_none(pw):
    assert pw.get_time_remaining() is None


def test_power_and_sensors_return_none(pw):
    assert pw.power() is None
    assert pw.site() is None
    assert pw.solar() is None
    assert pw.battery() is None
    assert pw.load() is None


def test_status_shortcuts_return_none(pw):
    assert pw.status() is None
    assert pw.version() is None
    assert pw.din() is None
    assert pw.uptime() is None
    assert pw.level() is None
    assert pw.site_name() is None


def test_grid_charging_export_return_none(pw):
    assert pw.get_grid_charging() is None
    assert pw.get_grid_export() is None
    assert pw.set_grid_charging(True) is None
    assert pw.set_grid_export('battery_ok') is None


def test_is_connected_returns_false(pw):
    assert pw.is_connected() is False
