"""TEDAPI.extract_fan_speeds() / get_fan_speeds().

The PVAC fan RPMs arrive in one of two places depending on the query set:
``components.msa[].signals[]`` for the V2024_06 ``msaSignals`` request, and
``esCan.bus.PVAC[].PVAC_Logging`` for the Tesla-signed V2026_06
DeviceControllerQuery (whose TEMSA signals filter no longer names the fan
speeds — reading only ``msa`` made /fans empty on that query set).
"""
from unittest.mock import patch

from pypowerwall.tedapi import TEDAPI

from .test_tedapi_cached_fetch import make_tedapi

ACTUAL = "PVAC_Fan_Speed_Actual_RPM"
TARGET = "PVAC_Fan_Speed_Target_RPM"


def _msa(part, serial, actual, target, extra=()):
    signals = [{"name": ACTUAL, "value": actual}, {"name": TARGET, "value": target}]
    signals += [{"name": n, "value": v} for n, v in extra]
    return {"partNumber": part, "serialNumber": serial, "signals": signals}


def _pvac(part, serial, actual, target, mia=False):
    return {
        "packagePartNumber": part,
        "packageSerialNumber": serial,
        "PVAC_Status": {"PVAC_Pout": 1000},
        "PVAC_Logging": {"isMIA": mia, ACTUAL: actual, TARGET: target,
                         "PVAC_VL1Ground": 120.0},
    }


class TestExtractFanSpeeds:

    def test_msa_signals_v2024_shape(self):
        data = {"components": {"msa": [
            _msa("1538100-00-F", "SN1", 1200, 1250, extra=[("MSA_pcbaId", "x")]),
        ]}}
        assert make_tedapi().extract_fan_speeds(data) == {
            "PVAC--1538100-00-F--SN1": {ACTUAL: 1200, TARGET: 1250},
        }

    def test_pvac_logging_v2026_shape(self):
        data = {"esCan": {"bus": {"PVAC": [
            _pvac("1538100-00-F", "SN1", 1300, 1350),
            _pvac("1538100-00-F", "SN2", 0, 0),
        ]}}}
        assert make_tedapi().extract_fan_speeds(data) == {
            "PVAC--1538100-00-F--SN1": {ACTUAL: 1300, TARGET: 1350},
            "PVAC--1538100-00-F--SN2": {ACTUAL: 0, TARGET: 0},
        }

    def test_both_sources_merge_with_pvac_logging_winning(self):
        data = {
            "esCan": {"bus": {"PVAC": [_pvac("P", "SN1", 1300, 1350)]}},
            "components": {"msa": [_msa("P", "SN1", 999, 999), _msa("P", "SN2", 800, 850)]},
        }
        assert make_tedapi().extract_fan_speeds(data) == {
            "PVAC--P--SN1": {ACTUAL: 1300, TARGET: 1350},
            "PVAC--P--SN2": {ACTUAL: 800, TARGET: 850},
        }

    def test_mia_and_missing_values_are_skipped(self):
        data = {
            "esCan": {"bus": {"PVAC": [
                _pvac("P", "MIA", 1300, 1350, mia=True),
                {"packagePartNumber": "P", "packageSerialNumber": "NOLOG"},
                {"packagePartNumber": "P", "packageSerialNumber": "NONE",
                 "PVAC_Logging": {ACTUAL: None, TARGET: None}},
                {"packagePartNumber": "P", "packageSerialNumber": "HALF",
                 "PVAC_Logging": {ACTUAL: 700, TARGET: None}},
            ]}},
            "components": {"msa": [
                {"partNumber": "P", "serialNumber": "MSANONE",
                 "signals": [{"name": ACTUAL, "value": None}]},
                {"partNumber": "P", "serialNumber": "MSAOTHER",
                 "signals": [{"name": "THC_AmbientTemp", "value": 30}]},
            ]},
        }
        assert make_tedapi().extract_fan_speeds(data) == {
            "PVAC--P--HALF": {ACTUAL: 700},
        }

    def test_malformed_payloads_yield_empty(self):
        api = make_tedapi()
        assert api.extract_fan_speeds(None) == {}
        assert api.extract_fan_speeds([]) == {}
        assert api.extract_fan_speeds({}) == {}
        assert api.extract_fan_speeds({"esCan": {"bus": {"PVAC": None}}}) == {}
        assert api.extract_fan_speeds({"esCan": {"bus": {"PVAC": ["junk", 3]}}}) == {}
        assert api.extract_fan_speeds({"components": {"msa": None}}) == {}
        assert api.extract_fan_speeds({"components": {"msa": ["junk"]}}) == {}
        assert api.extract_fan_speeds({"components": "junk"}) == {}

    def test_get_fan_speeds_reads_device_controller(self):
        api = make_tedapi()
        payload = {"esCan": {"bus": {"PVAC": [_pvac("P", "SN1", 1300, 1350)]}}}
        with patch.object(TEDAPI, "get_device_controller", return_value=payload) as gdc:
            assert api.get_fan_speeds(force=True) == {
                "PVAC--P--SN1": {ACTUAL: 1300, TARGET: 1350},
            }
        gdc.assert_called_once_with(force=True)
