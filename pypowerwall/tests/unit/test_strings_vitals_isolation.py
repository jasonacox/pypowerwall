"""strings() must not modify the dict returned by vitals().

strings() used to copy each PVS block's string keys (PVS_StringA_Connected,
...) into the matching PVAC block of the vitals() dict it was given. That
dict can share its device blocks with a backend cache: TEDAPI's vitals()
builds a new top-level dict per call but merges the Powerwall 3 blocks in
from the "pw3_vitals" cache entry by reference. So on a Powerwall 3, every
vitals() call until that entry expired - including the proxy's /vitals -
showed PVS_String*_Connected on the PVAC blocks, but only when /strings had
run first (seen on a long-running proxy polled by Powerwall-Dashboard while
validating v0.19.0).

The strings() output itself is pinned byte-for-byte below: the fix must not
change the /strings shape (AGENTS.md Prime Directive). The expected values
were captured from strings() before the fix.

All DIN/serial values here are fabricated test fixtures.
"""
import copy
import json
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall import Powerwall
from pypowerwall.tedapi import TEDAPI

PW3_PVAC = "PVAC--1707000-11-L--TG0002"

VITALS = {
    "STSTSM--1232100-00-E--TG0001": {"partNumber": "1232100-00-E"},
    # Powerwall 2 style: PVAC/PVS pair with 4 strings
    "PVAC--1538100-00-F--CN1": {
        "PVAC_Pout": 1500.0, "PVAC_State": "PVAC_Active",
        "PVAC_PVCurrent_A": 1.5, "PVAC_PVCurrent_B": 0.0,
        "PVAC_PVCurrent_C": 2.0, "PVAC_PVCurrent_D": 1.0,
        "PVAC_PVMeasuredPower_A": 450.0, "PVAC_PVMeasuredPower_B": 0.0,
        "PVAC_PVMeasuredPower_C": 600.0, "PVAC_PVMeasuredPower_D": 300.0,
        "PVAC_PVMeasuredVoltage_A": 300.0, "PVAC_PVMeasuredVoltage_B": 0.0,
        "PVAC_PVMeasuredVoltage_C": 300.0, "PVAC_PVMeasuredVoltage_D": 300.0,
        "PVAC_PvState_A": "PV_Active", "PVAC_PvState_B": "PV_Disabled",
        "PVAC_PvState_C": "PV_Active", "PVAC_PvState_D": "PV_Active",
    },
    "PVS--1538100-00-F--CN1": {
        "PVS_State": "PVS_Active", "PVS_vLL": 240.0,
        "PVS_StringA_Connected": True, "PVS_StringB_Connected": False,
        "PVS_StringC_Connected": True, "PVS_StringD_Connected": True,
    },
    # Powerwall 3 style: PVAC/PVS pair with strings A-F
    PW3_PVAC: {
        "PVAC_Pout": 2500,
        "PVAC_PVCurrent_E": 3.1, "PVAC_PVMeasuredVoltage_E": 350.0, "PVAC_PVMeasuredPower_E": 1085.0,
        "PVAC_PVCurrent_F": 2.9, "PVAC_PVMeasuredVoltage_F": 351.0, "PVAC_PVMeasuredPower_F": 1017.9,
    },
    "PVS--1707000-11-L--TG0002": {
        "PVS_StringA_Connected": True, "PVS_StringB_Connected": True,
        "PVS_StringC_Connected": False, "PVS_StringD_Connected": False,
        "PVS_StringE_Connected": True, "PVS_StringF_Connected": True,
    },
    # PVAC without a PVS partner
    "PVAC--1538100-00-F--CN3": {"PVAC_PVCurrent_A": 0.5, "PVAC_PVMeasuredVoltage_A": 200.0},
}

# json.dumps(strings()) - key order included - captured before the fix
EXPECTED_SIMPLE = (
    '{"A": {"Current": 1.5, "Power": 450.0, "Voltage": 300.0, "State": "PV_Active", "Connected": true}, '
    '"B": {"Current": 0.0, "Power": 0.0, "Voltage": 0.0, "State": "PV_Disabled", "Connected": false}, '
    '"C": {"Current": 2.0, "Power": 600.0, "Voltage": 300.0, "State": "PV_Active", "Connected": true}, '
    '"D": {"Current": 1.0, "Power": 300.0, "Voltage": 300.0, "State": "PV_Active", "Connected": true}, '
    '"E1": {"Current": 3.1, "Voltage": 350.0, "Power": 1085.0, "Connected": true}, '
    '"F1": {"Current": 2.9, "Voltage": 351.0, "Power": 1017.9, "Connected": true}, '
    '"A1": {"Connected": true}, "B1": {"Connected": true}, "C1": {"Connected": false}, '
    '"D1": {"Connected": false}, "A2": {"Current": 0.5, "Voltage": 200.0}}'
)
EXPECTED_VERBOSE = (
    '{"PVAC--1538100-00-F--CN1": {"PVAC_Pout": 1500.0, "PVAC_PVCurrent_A": 1.5, "PVAC_PVCurrent_B": 0.0, '
    '"PVAC_PVCurrent_C": 2.0, "PVAC_PVCurrent_D": 1.0, "PVAC_PVMeasuredPower_A": 450.0, '
    '"PVAC_PVMeasuredPower_B": 0.0, "PVAC_PVMeasuredPower_C": 600.0, "PVAC_PVMeasuredPower_D": 300.0, '
    '"PVAC_PVMeasuredVoltage_A": 300.0, "PVAC_PVMeasuredVoltage_B": 0.0, "PVAC_PVMeasuredVoltage_C": 300.0, '
    '"PVAC_PVMeasuredVoltage_D": 300.0, "PVAC_PvState_A": "PV_Active", "PVAC_PvState_B": "PV_Disabled", '
    '"PVAC_PvState_C": "PV_Active", "PVAC_PvState_D": "PV_Active", "PVS_StringA_Connected": true, '
    '"PVS_StringB_Connected": false, "PVS_StringC_Connected": true, "PVS_StringD_Connected": true}, '
    '"PVAC--1707000-11-L--TG0002": {"PVAC_Pout": 2500, "PVAC_PVCurrent_E": 3.1, "PVAC_PVMeasuredVoltage_E": 350.0, '
    '"PVAC_PVMeasuredPower_E": 1085.0, "PVAC_PVCurrent_F": 2.9, "PVAC_PVMeasuredVoltage_F": 351.0, '
    '"PVAC_PVMeasuredPower_F": 1017.9, "PVS_StringA_Connected": true, "PVS_StringB_Connected": true, '
    '"PVS_StringC_Connected": false, "PVS_StringD_Connected": false, "PVS_StringE_Connected": true, '
    '"PVS_StringF_Connected": true}, '
    '"PVAC--1538100-00-F--CN3": {"PVAC_Pout": null, "PVAC_PVCurrent_A": 0.5, "PVAC_PVMeasuredVoltage_A": 200.0}}'
)


def _powerwall(vitals_fn):
    """Facade whose client.vitals() is vitals_fn (cloud backend patched out)."""
    with patch('pypowerwall.PyPowerwallCloud'):
        pw = Powerwall(host='', password='', email='test@example.com', cloudmode=True, siteid=None)
    pw.client = MagicMock()
    pw.client.vitals.side_effect = vitals_fn
    return pw


class TestStringsLeavesVitalsUnchanged:

    @pytest.mark.parametrize("verbose", [False, True])
    def test_cached_vitals_dict_not_modified(self, verbose):
        # A backend that hands out the same cached dict on every call
        cached = copy.deepcopy(VITALS)
        pw = _powerwall(lambda: cached)
        before = copy.deepcopy(pw.vitals())
        pw.strings(verbose=verbose)
        pw.strings(jsonformat=True, verbose=verbose)
        assert pw.vitals() == before
        assert not any(k.startswith('PVS_String') for k in pw.vitals()[PW3_PVAC])

    def test_tedapi_pw3_cache_not_modified(self):
        # The real TEDAPI.vitals() path: a new top-level dict per call, with the
        # Powerwall 3 device blocks merged in by reference from "pw3_vitals"
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        api.din = "1707000-11-L--TG0002"
        api.pw3 = True
        api.pwcooldown = 0
        pw3_blocks = {k: v for k, v in copy.deepcopy(VITALS).items() if k.endswith("TG0002")}
        api._cache_put("pw3_vitals", pw3_blocks)
        with patch.object(TEDAPI, 'get_config', return_value={"vin": api.din}), \
                patch.object(TEDAPI, 'get_device_controller', return_value={}):
            pw = _powerwall(api.vitals)
            before = pw.vitals()
            # Confirms the sharing this test relies on
            assert before[PW3_PVAC] is api.pwcache["pw3_vitals"][PW3_PVAC]
            before = copy.deepcopy(before)
            strings = pw.strings()
            after = pw.vitals()
        assert strings["E"]["Connected"] is True  # the PVS data still reaches strings()
        before.pop("VITALS")  # header carries a per-call timestamp
        after.pop("VITALS")
        assert after == before
        assert not any(k.startswith('PVS_String') for k in after[PW3_PVAC])


class TestStringsOutputUnchanged:

    @pytest.mark.parametrize("verbose,expected", [(False, EXPECTED_SIMPLE), (True, EXPECTED_VERBOSE)])
    def test_output_pinned(self, verbose, expected):
        pw = _powerwall(lambda: copy.deepcopy(VITALS))
        result = pw.strings(verbose=verbose)
        assert json.dumps(result) == expected
        assert pw.strings(jsonformat=True, verbose=verbose) == json.dumps(result, indent=4, sort_keys=True)

    @pytest.mark.parametrize("verbose,expected", [(False, EXPECTED_SIMPLE), (True, EXPECTED_VERBOSE)])
    def test_output_same_on_repeat_calls(self, verbose, expected):
        # Before the fix the first call mutated the shared dict; repeat calls
        # against the same cached dict must still give the same answer
        cached = copy.deepcopy(VITALS)
        pw = _powerwall(lambda: cached)
        assert json.dumps(pw.strings(verbose=verbose)) == expected
        assert json.dumps(pw.strings(verbose=verbose)) == expected
