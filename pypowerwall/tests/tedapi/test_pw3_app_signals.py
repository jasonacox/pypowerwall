"""PW3 signals the V2026_06 queries request (PW3Query/ComplianceQuery),
requested here as V2024_06 ComponentsQuery extras (PW3_APP_SIGNAL_NAMES).

bms/hvp extras land on each battery's TEPOD block, pch/pws/baggr on the
Powerwall's TEPINV block. Values come from value, boolValue or textValue as the
gateway sends them. Fixture values are shaped like the 2026-10-11 hardware read;
the phantom slot carries the placeholder values real empty slots report.
"""
import json

import pytest

from pypowerwall.tedapi import _component_signal_value
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.queries import QueryRole

from .test_pw3_temperatures import (EXPANSION_DIN, FOLLOWER_DIN, LEADER_DIN,  # noqa: F401
                                    _vitals_for, fixture_api)


def _num(name, value):
    return {"name": name, "value": value, "textValue": None, "boolValue": None, "timestamp": 0}


def _text(name, value):
    return {"name": name, "value": None, "textValue": value, "boolValue": None, "timestamp": 0}


def _bool(name, value):
    return {"name": name, "value": None, "textValue": None, "boolValue": value, "timestamp": 0}


def _pack(kwh_discharged, cac, serial, bi_state="BI_DISCONNECT_HW_OPENED", lockout=False):
    bms = {"signals": [
        _num("BMS_nominalEnergyRemaining", 7.0), _num("BMS_nominalFullPackEnergy", 13.5),
        _num("BMS_kwhDischargeTotal", kwh_discharged), _num("BMS_LOG_ahDischargeTotal", kwh_discharged * 11.7),
        _num("BMS_LOG_cacAvg", cac), _num("BMS_LOG_numFullBattCycles", 0),
        _num("BMS_LOG_overDischargeCounter", 0), _num("BMS_LOG_selfDischargeRate", 0.392),
    ], "activeAlerts": []}
    hvp = {"partNumber": "1707000-11-J", "serialNumber": serial, "signals": [
        _text("HVP_SafetyBiDisconnectState", bi_state), _bool("HVP_a061_LockoutOnIsoFaultRetry", lockout),
    ], "activeAlerts": []}
    return bms, hvp


def _payload(packs, ac_power):
    return json.dumps({"components": {
        "pws": [{"signals": [
            _text("PWS_RSD_State", "RSD_State_Armed"), _text("PWS_ExtSwitch_State", "PWS_SWITCH_STATE_CLOSED"),
            _text("PWS_RSDSelfTest_Result", "RSD_TEST_PASS"), _num("PWS_reversePolarityStrings", 0),
        ], "activeAlerts": []}],
        "pch": [{"signals": [
            _num("PCH_AcFrequency", 60.0), _num("PCH_AcRealPowerSum", ac_power),
            _num("PCH_AcVoltageLL", 240.6), _num("PCH_AcVoltageCN", None),
        ], "activeAlerts": []}],
        "bms": [bms for bms, _ in packs],
        "hvp": [hvp for _, hvp in packs],
        "baggr": [{"signals": [
            _num("BAGGR_ExpectedEnergyRemaining", 12.5), _num("BAGGR_ExpectedFullPackEnergy", 14.05),
            _text("BAGGR_OperationType", "BAGGR_OP_TYPE_NONE"),
        ], "activeAlerts": []}],
    }})


# Leader: its own pack, a real expansion pack, and an empty slot that reports
# placeholder values (cacAvg 173.3) under no known serial
LEADER = _payload([_pack(2969.767, 171.2, "TG12000000001Z"), _pack(812.5, 172.0, "TG12000000004Z"),
                   _pack(0, 173.3, "", bi_state=None, lockout=None)], 1690)
FOLLOWER = _payload([_pack(2867.266, 171.2, "TG12000000002Z")], -370)


class TestRequest:
    def test_names_appended_to_their_component_groups(self):
        request = json.loads(q.get_query(QueryRole.COMPONENTS).b_value)
        for key, names in q.PW3_APP_SIGNAL_NAMES.items():
            assert request[key][-len(names):] == list(names)

    def test_group_matches_signal_prefix(self):
        prefix = {"pchSignalNames": "PCH_", "bmsSignalNames": "BMS_", "hvpSignalNames": "HVP_",
                  "pwsSignalNames": "PWS_", "baggrSignalNames": "BAGGR_"}
        for key, names in q.PW3_APP_SIGNAL_NAMES.items():
            assert all(n.startswith(prefix[key]) for n in names)


class TestVitals:
    def test_battery_health_on_each_tepod(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER, FOLLOWER_DIN: FOLLOWER})
        leader, expansion, follower = (vitals[f"TEPOD--{d}"] for d in (LEADER_DIN, EXPANSION_DIN, FOLLOWER_DIN))
        assert leader["BMS_kwhDischargeTotal"] == 2969.767
        assert leader["BMS_LOG_cacAvg"] == 171.2
        assert leader["BMS_LOG_numFullBattCycles"] == 0
        assert expansion["BMS_kwhDischargeTotal"] == 812.5
        assert follower["BMS_kwhDischargeTotal"] == 2867.266
        # enum and boolean signals come through, not as None
        assert leader["HVP_SafetyBiDisconnectState"] == "BI_DISCONNECT_HW_OPENED"
        assert leader["HVP_a061_LockoutOnIsoFaultRetry"] is False

    def test_empty_slot_placeholders_never_reach_vitals(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER, FOLLOWER_DIN: FOLLOWER})
        tepods = [k for k in vitals if k.startswith("TEPOD--")]
        assert len(tepods) == 3
        assert all(vitals[k]["BMS_LOG_cacAvg"] != 173.3 for k in tepods)

    def test_inverter_pws_and_baggr_on_tepinv(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER, FOLLOWER_DIN: FOLLOWER})
        leader = vitals[f"TEPINV--{LEADER_DIN}"]
        assert leader["PCH_AcRealPowerSum"] == 1690
        assert leader["PCH_AcVoltageLL"] == 240.6
        assert leader["PCH_AcVoltageCN"] is None
        assert leader["PWS_RSD_State"] == "RSD_State_Armed"
        assert leader["BAGGR_ExpectedFullPackEnergy"] == 14.05
        assert leader["BAGGR_OperationType"] == "BAGGR_OP_TYPE_NONE"
        assert vitals[f"TEPINV--{FOLLOWER_DIN}"]["PCH_AcRealPowerSum"] == -370

    def test_every_name_present_even_when_not_delivered(self, api):
        # stable block shape: a signal the gateway doesn't send is None
        vitals = _vitals_for(api, {LEADER_DIN: LEADER, FOLLOWER_DIN: FOLLOWER})
        tepinv = vitals[f"TEPINV--{LEADER_DIN}"]
        for key in ("pchSignalNames", "pwsSignalNames", "baggrSignalNames"):
            for name in q.PW3_APP_SIGNAL_NAMES[key]:
                assert name in tepinv
        assert tepinv["PWS_pcbaId"] is None
        tepod = vitals[f"TEPOD--{LEADER_DIN}"]
        for key in ("bmsSignalNames", "hvpSignalNames"):
            for name in q.PW3_APP_SIGNAL_NAMES[key]:
                assert name in tepod


class TestComponentSignalValue:
    @pytest.mark.parametrize("signal, expected", [
        (_num("X", 1.5), 1.5), (_num("X", 0), 0), (_text("X", "RSD_State_Armed"), "RSD_State_Armed"),
        (_bool("X", False), False), (_num("X", None), None),
    ])
    def test_value_bool_or_text(self, signal, expected):
        assert _component_signal_value([{"signals": [signal]}], "X") == expected
