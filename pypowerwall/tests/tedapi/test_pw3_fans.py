"""PW3 fans: requested via unsigned ComponentsQuery variables, surfaced on each
inverter's TEPINV vitals block and by TEDAPI.get_fan_speeds().

Hardware basis (2026-09-26, PW3 leader + follower, firmware 26.18.1, no DC
expansions): each PW3 inverter (pch) reports PCH_FanSpeed_A/B (measured RPM) and
PCH_FanDuty_A/B (duty cycle, %). The PW2 PVAC_Fan_Speed_* names are echoed by the
device controller's msa components on PW3 but always None.
"""
import json
import time
from unittest.mock import patch

import pytest

from pypowerwall.tedapi import TEDAPI, tedapi_pb2
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.queries import QueryRole

LEADER_DIN = "1707000-11-M--TG1253370033TB"
FOLLOWER_DIN = "1707000-11-M--TG125337002LNY"   # sorts before the leader
FAN_NAMES = ["PCH_FanSpeed_A", "PCH_FanSpeed_B", "PCH_FanDuty_A", "PCH_FanDuty_B"]


def _sig(name, value):
    return {"name": name, "value": value, "textValue": None, "boolValue": None, "timestamp": None}


def _payload(fans):
    """Components payload for one PW3 whose pch carries ``fans`` {name: value}."""
    return json.dumps({"components": {
        "pws": [{"signals": [], "activeAlerts": []}],
        "pch": [{"signals": [_sig("PCH_AcFrequency", 60.0), _sig("PCH_AmbientTemp", 55.2)]
                 + [_sig(name, value) for name, value in fans.items()], "activeAlerts": []}],
        "bms": [{"signals": [_sig("BMS_nominalEnergyRemaining", 7.0),
                             _sig("BMS_nominalFullPackEnergy", 13.5)], "activeAlerts": []}],
        "hvp": [{"partNumber": "1707000-11-M", "serialNumber": "x", "signals": [], "activeAlerts": []}],
        "baggr": [{"signals": [], "activeAlerts": []}],
    }})


LEADER_FANS = {"PCH_FanSpeed_A": 1395, "PCH_FanSpeed_B": 1397, "PCH_FanDuty_A": 19.1, "PCH_FanDuty_B": 19.1}
FOLLOWER_FANS = {"PCH_FanSpeed_A": 1000, "PCH_FanSpeed_B": 991, "PCH_FanDuty_A": 5.1, "PCH_FanDuty_B": 6.6}

BATTERY_BLOCKS = [
    {"vin": LEADER_DIN, "type": "Powerwall3", "battery_expansions": []},
    {"vin": FOLLOWER_DIN, "type": "Powerwall3Follower", "battery_expansions": []},
]

# Device controller answer on PW3: the PVAC fan names echo on msa components, value None
PW3_CONTROLLER = {"components": {"msa": [
    {"partNumber": "1707000-11-M", "serialNumber": "TG1253370033TB", "signals": [], "activeAlerts": []},
    {"partNumber": "", "serialNumber": "", "activeAlerts": [], "signals": [
        _sig("PVAC_Fan_Speed_Actual_RPM", None), _sig("PVAC_Fan_Speed_Target_RPM", None)]},
]}}

PW2_CONTROLLER = {"components": {"msa": [
    {"partNumber": "1538000-45-C", "serialNumber": "TG1", "activeAlerts": [], "signals": [
        _sig("PVAC_Fan_Speed_Actual_RPM", 1180), _sig("PVAC_Fan_Speed_Target_RPM", 1200)]},
    {"partNumber": "1092170-03-E", "serialNumber": "TG9", "activeAlerts": [], "signals": [
        _sig("THC_AmbientTemp", 22.5)]},
]}}
PW2_FANS = {"PVAC--1538000-45-C--TG1": {"PVAC_Fan_Speed_Actual_RPM": 1180, "PVAC_Fan_Speed_Target_RPM": 1200}}


@pytest.fixture(name="api")
def fixture_api():
    """WiFi-mode TEDAPI with config/components/controller caches seeded."""
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value=LEADER_DIN):
        api = TEDAPI("test_password", pwcacheexpire=300, pwconfigexpire=300)
    api.din = LEADER_DIN
    now = time.time()
    api.pwcache.update({"config": {"battery_blocks": BATTERY_BLOCKS}, "components": {"components": {}},
                        "controller": PW3_CONTROLLER})
    api.pwcachetime.update({"config": now, "components": now, "controller": now})
    return api


def _post_answering(payloads):
    def fake_post(data, din=None, url_suffix=None):
        resp = tedapi_pb2.Message()
        resp.message.payload.recv.text = payloads[din]
        return resp.SerializeToString()
    return fake_post


def _vitals_for(api, payloads):
    with patch.object(api, '_post_tedapi', side_effect=_post_answering(payloads)):
        return api.get_pw3_vitals()


# --- query layer ---------------------------------------------------------------

class TestFanSignalRequest:

    def test_fan_names_appended_after_temperature_extras(self):
        captured = json.loads(q.V2024_06_QUERIES["components"].b_value)["pchSignalNames"]
        request = json.loads(q.get_query(QueryRole.COMPONENTS).b_value)["pchSignalNames"]
        # every earlier name (capture + temperature extras) keeps its position
        assert request == captured + ["PCH_AmbientTemp", "PCH_heatsinkTemp"] + FAN_NAMES

    def test_single_source_of_truth(self):
        assert list(q.PW3_FAN_SIGNAL_NAMES) == FAN_NAMES
        pch = q.EXTRA_SIGNAL_NAMES[QueryRole.COMPONENTS]["pchSignalNames"]
        assert pch[-len(FAN_NAMES):] == q.PW3_FAN_SIGNAL_NAMES

    def test_signature_unchanged(self):
        assert q.get_query(QueryRole.COMPONENTS).code == q.V2024_06_QUERIES["components"].code

    def test_device_controller_query_untouched(self):
        # PW2 fans keep coming from the pristine device-controller capture
        assert q.get_query(QueryRole.DEVICE_CONTROLLER_FULL) is q.V2024_06_QUERIES["device_controller_full"]


# --- vitals passthrough -----------------------------------------------------------

class TestPw3VitalsFans:

    def test_each_inverter_reports_its_own_fans(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: _payload(LEADER_FANS), FOLLOWER_DIN: _payload(FOLLOWER_FANS)})
        for din, fans in ((LEADER_DIN, LEADER_FANS), (FOLLOWER_DIN, FOLLOWER_FANS)):
            block = vitals[f"TEPINV--{din}"]
            assert {name: block[name] for name in FAN_NAMES} == fans

    def test_missing_fan_signals_are_none_keys(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: _payload({}), FOLLOWER_DIN: _payload({"PCH_FanSpeed_A": None})})
        for din in (LEADER_DIN, FOLLOWER_DIN):
            block = vitals[f"TEPINV--{din}"]
            assert all(name in block and block[name] is None for name in FAN_NAMES)
            assert block["PINV_Fout"] == 60.0   # existing keys unaffected

    def test_fans_not_mapped_onto_pvac_names(self, api):
        # PW3 has no target RPM: the PW2 PVAC fan keys are not synthesized
        vitals = _vitals_for(api, {LEADER_DIN: _payload(LEADER_FANS), FOLLOWER_DIN: _payload(FOLLOWER_FANS)})
        for block in vitals.values():
            assert "PVAC_Fan_Speed_Actual_RPM" not in block
            assert "PVAC_Fan_Speed_Target_RPM" not in block


# --- extract_pw3_fan_speeds ----------------------------------------------------------

class TestExtractPw3FanSpeeds:

    def test_keeps_vitals_order_and_only_fan_signals(self, api):
        vitals = {
            f"TEPOD--{LEADER_DIN}": {"HVP_PackTempMax": 40.8},
            f"TEPINV--{LEADER_DIN}": {"PCH_AmbientTemp": 55.2, **LEADER_FANS},
            f"PVAC--{LEADER_DIN}": {"PVAC_Fout": 60.0},
            f"TEPINV--{FOLLOWER_DIN}": {"PCH_AmbientTemp": 44.5, **FOLLOWER_FANS},
        }
        fans = api.extract_pw3_fan_speeds(vitals)
        assert list(fans.items()) == [(f"TEPINV--{LEADER_DIN}", LEADER_FANS),
                                      (f"TEPINV--{FOLLOWER_DIN}", FOLLOWER_FANS)]

    def test_partial_fans_keep_none(self, api):
        vitals = {f"TEPINV--{LEADER_DIN}": {"PCH_FanSpeed_B": 1397}}
        assert api.extract_pw3_fan_speeds(vitals) == {f"TEPINV--{LEADER_DIN}": {
            "PCH_FanSpeed_A": None, "PCH_FanSpeed_B": 1397, "PCH_FanDuty_A": None, "PCH_FanDuty_B": None}}

    def test_inverter_without_fan_values_is_omitted(self, api):
        vitals = {f"TEPINV--{LEADER_DIN}": dict.fromkeys(FAN_NAMES),
                  f"TEPINV--{FOLLOWER_DIN}": {"PCH_AmbientTemp": 44.5}}
        assert api.extract_pw3_fan_speeds(vitals) == {}

    @pytest.mark.parametrize("vitals", [None, {}, [], "junk", {f"TEPINV--{LEADER_DIN}": None},
                                        {f"TEPINV--{LEADER_DIN}": ["junk"]}])
    def test_tolerates_malformed_input(self, api, vitals):
        assert api.extract_pw3_fan_speeds(vitals) == {}


# --- get_fan_speeds -----------------------------------------------------------------

class TestGetFanSpeeds:

    def test_pw3_reports_inverter_fans_leader_first(self, api):
        api.pw3 = True
        payloads = {LEADER_DIN: _payload(LEADER_FANS), FOLLOWER_DIN: _payload(FOLLOWER_FANS)}
        with patch.object(api, '_post_tedapi', side_effect=_post_answering(payloads)):
            fans = api.get_fan_speeds()
        assert list(fans.items()) == [(f"TEPINV--{LEADER_DIN}", LEADER_FANS),
                                      (f"TEPINV--{FOLLOWER_DIN}", FOLLOWER_FANS)]

    def test_pw3_pvac_names_with_none_values_add_nothing(self, api):
        # The device controller alone (PW3 answer) yields no fans, as before
        assert api.extract_fan_speeds(PW3_CONTROLLER) == {}

    def test_pw3_signals_missing_is_empty(self, api):
        api.pw3 = True
        payloads = {LEADER_DIN: _payload({}), FOLLOWER_DIN: _payload(dict.fromkeys(FAN_NAMES))}
        with patch.object(api, '_post_tedapi', side_effect=_post_answering(payloads)):
            assert api.get_fan_speeds() == {}

    def test_pw3_vitals_failure_is_empty(self, api):
        api.pw3 = True
        with patch.object(api, 'get_pw3_vitals', return_value=None):
            assert api.get_fan_speeds() == {}

    def test_pw3_device_controller_failure_still_reports_fans(self, api):
        api.pw3 = True
        vitals = {f"TEPINV--{LEADER_DIN}": dict(LEADER_FANS)}
        with patch.object(api, 'get_device_controller', return_value=None), \
                patch.object(api, 'get_pw3_vitals', return_value=vitals):
            assert api.get_fan_speeds() == {f"TEPINV--{LEADER_DIN}": LEADER_FANS}

    def test_force_is_passed_through(self, api):
        api.pw3 = True
        with patch.object(api, 'get_device_controller', return_value=None) as dc, \
                patch.object(api, 'get_pw3_vitals', return_value={}) as pw3:
            api.get_fan_speeds(force=True)
        dc.assert_called_once_with(force=True)
        pw3.assert_called_once_with(force=True)

    def test_pw2_unchanged_and_never_queries_components(self, api):
        api.pw3 = False
        api.pwcache["controller"] = PW2_CONTROLLER
        with patch.object(api, 'get_pw3_vitals') as pw3:
            assert api.get_fan_speeds() == PW2_FANS
        pw3.assert_not_called()

    def test_pw2_failure_unchanged(self, api):
        api.pw3 = False
        with patch.object(api, 'get_device_controller', return_value=None):
            assert api.get_fan_speeds() == {}
