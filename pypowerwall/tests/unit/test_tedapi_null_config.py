"""Unit tests for null config fields crashing vitals()/aggregates (#407).

A gateway restarted mid re-commissioning can return config.json with
'meters': null and/or 'vin': null. The #407 reporter saw
"TypeError: 'NoneType' object is not iterable" but could not capture the
failing line; replaying captured payloads with each section nulled
reproduces the reported message from derive_meter_config(). These tests
replay those payloads against derive_meter_config() and vitals().

All DIN/serial values here are fabricated test fixtures built from the
captured payload shape, not data captured from a real gateway.
"""
from unittest.mock import patch

from pypowerwall.tedapi import TEDAPI

GATEWAY_DIN = "1707000-21-M--TESTGW00000001"


def _make_tedapi():
    with patch.object(TEDAPI, 'connect', return_value=True):
        return TEDAPI(gw_pwd='password')


def _good_config():
    return {
        "vin": GATEWAY_DIN,
        "meters": [{
            "type": "neurio_w2_tcp",
            "location": "site",
            "cts": [True, False, False, False],
            "connection": {"device_serial": "NEURIOSN1"},
        }],
    }


class TestDeriveMeterConfigNulls:
    """config 'meters': null (or a null config) must yield {}, not TypeError."""

    def test_meters_null_returns_empty(self):
        ted = _make_tedapi()
        assert ted.derive_meter_config({"vin": GATEWAY_DIN, "meters": None}) == {}

    def test_config_null_returns_empty(self):
        ted = _make_tedapi()
        assert ted.derive_meter_config(None) == {}

    def test_meters_missing_returns_empty(self):
        ted = _make_tedapi()
        assert ted.derive_meter_config({"vin": GATEWAY_DIN}) == {}

    def test_null_meter_entry_skipped(self):
        ted = _make_tedapi()
        config = _good_config()
        config["meters"].insert(0, None)
        result = ted.derive_meter_config(config)
        assert "NEURIOSN1" in result
        assert result["NEURIOSN1"]["location"] == ["site"] * 4

    def test_good_config_unchanged(self):
        ted = _make_tedapi()
        result = ted.derive_meter_config(_good_config())
        assert "NEURIOSN1" in result
        assert result["NEURIOSN1"]["type"] == "neurio_w2_tcp"


class TestVitalsNormalVinParity:
    """With a normal VIN, vitals() must keep the gateway block's identity:
    STSTSM--{partNumber}--{serialNumber} with both fields parsed."""

    def test_vitals_keeps_gateway_identity(self):
        ted = _make_tedapi()
        config = _good_config()
        status = {
            "control": None,
            "system": {"sitemanagerStatus": {"isRunning": True}},
            "components": None,
            "esCan": None,
        }
        with patch.object(TEDAPI, 'get_config', return_value=config), \
             patch.object(TEDAPI, 'get_device_controller', return_value=status), \
             patch.object(TEDAPI, 'get_firmware_version', return_value="26.26.11 test"):
            result = ted.vitals(force=True)
        assert isinstance(result, dict)
        assert "STSTSM--1707000-21-M--TESTGW00000001" in result
        block = result["STSTSM--1707000-21-M--TESTGW00000001"]
        assert block["partNumber"] == "1707000-21-M"
        assert block["serialNumber"] == "TESTGW00000001"


class TestVitalsNullConfig:
    """End-to-end: vitals() with the #407 post-restart config shape must return
    a dict instead of raising, with the STSTSM block degraded to null identity."""

    def test_vitals_with_null_meters_and_vin(self):
        ted = _make_tedapi()
        config = {"vin": None, "meters": None, "site_info": None, "battery_blocks": None}
        status = {
            "control": None,
            "system": {"sitemanagerStatus": {"isRunning": False}},
            "components": None,
            "esCan": None,
        }
        with patch.object(TEDAPI, 'get_config', return_value=config), \
             patch.object(TEDAPI, 'get_device_controller', return_value=status), \
             patch.object(TEDAPI, 'get_firmware_version', return_value="26.26.11 test"):
            result = ted.vitals(force=True)
        assert isinstance(result, dict)
        ststsm_key = "STSTSM--None"
        assert ststsm_key in result
        assert result[ststsm_key]["partNumber"] is None
