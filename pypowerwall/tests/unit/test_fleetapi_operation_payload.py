"""Regression tests for fleetapi post_api_operation partial-payload handling.

A reserve-only payload of 0 used to be rejected by the truthiness-based
"missing parameters" guard ('not 0' is True). See PW3 mode-persistence race
reported in pypowerwall-server PR #85.
"""
from unittest.mock import MagicMock

import pytest

from pypowerwall.fleetapi.pypowerwall_fleetapi import (
    PyPowerwallFleetAPI,
    PyPowerwallFleetAPIInvalidPayload,
)


def _make_fleetapi():
    # Construct via __new__ to skip __init__ network/token-file side effects.
    fleet = PyPowerwallFleetAPI.__new__(PyPowerwallFleetAPI)
    fleet.fleet = MagicMock()
    fleet.fleet.set_battery_reserve.return_value = 200
    fleet.fleet.set_operating_mode.return_value = 200
    return fleet


def test_reserve_zero_only_not_rejected_as_empty(tmp_path):
    fleet = _make_fleetapi()

    resp = fleet.post_api_operation(payload={'backup_reserve_percent': 0})
    assert 'error' not in resp
    assert resp['set_backup_reserve_percent']['backup_reserve_percent'] == 0
    fleet.fleet.set_battery_reserve.assert_called_once_with(0)
    fleet.fleet.set_operating_mode.assert_not_called()


def test_mode_only_payload_single_command(tmp_path):
    fleet = PyPowerwallFleetAPI.__new__(PyPowerwallFleetAPI)
    fleet.fleet = MagicMock()
    fleet.fleet.set_battery_reserve.return_value = 200
    fleet.fleet.set_operating_mode.return_value = 200

    resp = fleet.post_api_operation(payload={'real_mode': 'autonomous'})
    assert 'error' not in resp
    assert resp['set_operation']['real_mode'] == 'autonomous'
    fleet.fleet.set_operating_mode.assert_called_once_with('autonomous')
    fleet.fleet.set_battery_reserve.assert_not_called()


def test_empty_payload_still_rejected(tmp_path):
    fleet = PyPowerwallFleetAPI.__new__(PyPowerwallFleetAPI)
    fleet.fleet = MagicMock()
    with pytest.raises(PyPowerwallFleetAPIInvalidPayload):
        fleet.post_api_operation(payload={})
