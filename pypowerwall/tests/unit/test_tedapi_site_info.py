"""TEDAPI /api/site_info reads config.json's "site_info" section.

It read the top level of config.json, where none of these keys exist, so every
field was None. Values below are shaped like a live 2026-10-11 Powerwall 3 config.
"""
import json
from unittest.mock import patch

from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI

SITE_INFO = {
    "site_name": "Test Site", "timezone": "America/Los_Angeles",
    "nominal_system_energy_ac": 27, "nominal_system_power_ac": 13.44,
    "max_site_meter_power_ac": 1000000000, "min_site_meter_power_ac": -1000000000,
    "panel_max_current": 100, "grid_code": "60Hz_240V_s_SMC_IEEE1547-2018_UL1741SB-CA-Rule21_2023",
    "country": "United States", "state": "California", "utility": "Southern California Edison",
    "battery_commission_date": "2025-12-15T15:48:57-08:00",
}

# A real gateway's /api/site_info (pwsimulator/stub.py)
GATEWAY_SITE_INFO = json.loads(
    '{"max_system_energy_kWh":27,"max_system_power_kW":10.8,"site_name":"Tesla Energy Gateway",'
    '"timezone":"America/Los_Angeles","max_site_meter_power_kW":1000000000,"min_site_meter_power_kW":-1000000000,'
    '"nominal_system_energy_kWh":27,"nominal_system_power_kW":10.8,"panel_max_current":100,'
    '"grid_code":{"grid_code":"60Hz_240V_s_UL1741SA:2019_California","grid_voltage_setting":240,'
    '"grid_freq_setting":60,"grid_phase_setting":"Split","country":"United States","state":"California",'
    '"utility":"Southern California Edison"}}')


def _site_info(config):
    with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
        backend = PyPowerwallTEDAPI(gw_pwd='password')
    backend.tedapi.get_config.return_value = config
    return backend.get_api_site_info()


def test_fields_come_from_site_info():
    data = _site_info({"vin": "X", "site_info": SITE_INFO})
    assert data["site_name"] == "Test Site"
    assert data["timezone"] == "America/Los_Angeles"
    assert data["max_system_energy_kWh"] == data["nominal_system_energy_kWh"] == 27
    assert data["max_system_power_kW"] == data["nominal_system_power_kW"] == 13.44
    assert data["max_site_meter_power_kW"] == 1000000000
    assert data["min_site_meter_power_kW"] == -1000000000
    assert data["panel_max_current"] == 100
    assert data["grid_code"] == {
        "grid_code": "60Hz_240V_s_SMC_IEEE1547-2018_UL1741SB-CA-Rule21_2023",
        "grid_voltage_setting": None, "grid_freq_setting": None, "grid_phase_setting": None,
        "country": "United States", "state": "California", "utility": "Southern California Edison",
    }


def test_same_shape_as_a_gateway():
    data = _site_info({"site_info": SITE_INFO})
    assert set(data) == set(GATEWAY_SITE_INFO)
    assert set(data["grid_code"]) == set(GATEWAY_SITE_INFO["grid_code"])


def test_missing_site_info_keeps_shape():
    for config in ({}, {"site_info": None}, {"site_info": {}}, {"site_info": "x"}, {"site_info": [1]}):
        data = _site_info(config)
        assert set(data) == set(GATEWAY_SITE_INFO)
        assert data["site_name"] is None and data["grid_code"]["grid_code"] is None


def test_no_config_returns_none():
    assert _site_info(None) is None
