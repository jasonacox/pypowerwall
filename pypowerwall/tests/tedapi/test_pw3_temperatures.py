"""PW3 temperatures: requested via unsigned ComponentsQuery variables and surfaced
in get_pw3_vitals() (TEPOD pack temps, TEPINV inverter ambient) and temps().

Hardware basis (2026-09-24, PW3 leader + follower, WiFi TEDAPI and v1r LAN): the
V2024_06 ComponentsQuery signature covers only the query text; the gateway honors
extra *SignalNames and returns HVP_PackTempMax/Min, HVP_ShuntTemperature per
battery and PCH_AmbientTemp per inverter.
"""
import json
import time
from unittest.mock import patch

import pytest

from pypowerwall import Powerwall
from pypowerwall.tedapi import TEDAPI, tedapi_pb2, _component_signal_value
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.queries import QueryRole

LEADER_DIN = "1707000-11-J--TG12000000001Z"
FOLLOWER_DIN = "1707000-11-J--TG12000000002Z"
EXPANSION_DIN = "2707000-11-J--TG12000000004Z"

TEMP_EXTRAS = {
    "pchSignalNames": ["PCH_AmbientTemp", "PCH_heatsinkTemp"],
    "bmsSignalNames": ["BMS_LOG_tempOutOfBounds", "BMS_LOG_tempOutOfBoundsCharge"],
    "hvpSignalNames": ["HVP_PackTempMax", "HVP_PackTempMin", "HVP_ShuntTemperature"],
}


def _sig(name, value):
    return {"name": name, "value": value, "textValue": "", "boolValue": False, "timestamp": 0}


HEATSINK = 45.450980392156865   # the constant both PW3s delivered at validation


def _payload(ambient, packs, hvp_serials):
    """Components payload for one PW3: ``packs`` is a list of
    (energy_remaining_kwh, (pack_max, pack_min, shunt), (oob, oob_charge))
    per BMS/HVP index."""
    return json.dumps({"components": {
        "pws": [{"signals": [], "activeAlerts": []}],
        "pch": [{"signals": [
            _sig("PCH_AcFrequency", 60.0),
            _sig("PCH_AmbientTemp", ambient),
            _sig("PCH_heatsinkTemp", HEATSINK),
        ], "activeAlerts": []}],
        "bms": [{"signals": [
            _sig("BMS_nominalEnergyRemaining", energy),
            _sig("BMS_nominalFullPackEnergy", 13.5),
            _sig("BMS_LOG_tempOutOfBounds", counters[0]),
            _sig("BMS_LOG_tempOutOfBoundsCharge", counters[1]),
        ], "activeAlerts": []} for energy, _, counters in packs],
        "hvp": [{"partNumber": "1707000-11-J", "serialNumber": serial, "signals": [
            _sig("HVP_State", None),
            _sig("HVP_PackTempMax", temps[0]),
            _sig("HVP_PackTempMin", temps[1]),
            _sig("HVP_ShuntTemperature", temps[2]),
        ], "activeAlerts": []} for serial, (_, temps, _) in zip(hvp_serials, packs)],
        "baggr": [{"signals": [], "activeAlerts": []}],
    }})


# Distinct per-battery values so a wrong BMS/HVP index pairing can't pass
LEADER_PAYLOAD = _payload(45.4, [(7.0, (39.7, 35.1, 40.2), (1, 2)),
                                (6.0, (38.0, 34.0, 39.0), (3, 4))],
                          ["TG12000000001Z", "TG12000000004Z"])
FOLLOWER_PAYLOAD = _payload(44.7, [(6.9, (39.5, 34.8, 39.9), (0, 0))], ["TG12000000002Z"])

BATTERY_BLOCKS = [
    {"vin": LEADER_DIN, "type": "Powerwall3", "battery_expansions": [{"din": EXPANSION_DIN}]},
    {"vin": FOLLOWER_DIN, "type": "Powerwall3Follower", "battery_expansions": []},
]


@pytest.fixture(name="api")
def fixture_api():
    """WiFi-mode TEDAPI with config/components caches seeded (leader + follower)."""
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value=LEADER_DIN):
        api = TEDAPI("test_password", pwcacheexpire=300, pwconfigexpire=300)
    api.din = LEADER_DIN
    api.pwcache["config"] = {"battery_blocks": BATTERY_BLOCKS}
    api.pwcachetime["config"] = time.time()
    api.pwcache["components"] = {"components": {}}
    api.pwcachetime["components"] = time.time()
    return api


def _vitals_for(api, payloads):
    """Run get_pw3_vitals with each device URL answering its payload."""
    def fake_post(data, din=None, url_suffix=None):
        resp = tedapi_pb2.Message()
        resp.message.payload.recv.text = payloads[din]
        return resp.SerializeToString()
    # Unforced: config/components come from the fixture's seeded caches
    with patch.object(api, '_post_tedapi', side_effect=fake_post):
        return api.get_pw3_vitals()


# --- query layer ---------------------------------------------------------------

class TestComponentsRequestQuery:

    def test_capture_is_pristine(self):
        raw = json.loads((q._DIR / "V2024_06.json").read_text(encoding="utf-8"))
        assert q.V2024_06_QUERIES["components"].b_value == raw["components"]["b_value"]

    def test_signature_and_text_unchanged(self):
        captured = q.V2024_06_QUERIES["components"]
        request = q.get_query(QueryRole.COMPONENTS)
        assert request.text == captured.text
        assert request.code == captured.code

    def test_extras_appended_after_captured_names(self):
        captured = json.loads(q.V2024_06_QUERIES["components"].b_value)
        request = json.loads(q.get_query(QueryRole.COMPONENTS).b_value)
        for key, extras in TEMP_EXTRAS.items():
            assert request[key] == captured[key] + extras
        for key in captured:
            if key not in TEMP_EXTRAS:
                assert request[key] == captured[key]

    def test_only_difference_on_wire_is_appended_names(self):
        # Removing the extras reproduces the capture byte-for-byte
        request = json.loads(q.get_query(QueryRole.COMPONENTS).b_value)
        for key, extras in TEMP_EXTRAS.items():
            request[key] = request[key][:-len(extras)]
        assert json.dumps(request, separators=(",", ":")) == q.V2024_06_QUERIES["components"].b_value

    def test_roles_without_extras_are_the_capture_object(self):
        for role in (QueryRole.DEVICE_CONTROLLER_BASIC, QueryRole.DEVICE_CONTROLLER_FULL):
            assert q.get_query(role) is q.V2024_06_QUERIES[role]

    def test_v2026_06_is_untouched(self):
        assert q.get_query(QueryRole.COMPONENTS, "V2026_06") is q.V2026_06_QUERIES["PW3Query"]

    def test_extras_are_idempotent(self):
        once = q.get_query(QueryRole.COMPONENTS)
        twice = q._with_extra_signals(once, q.EXTRA_SIGNAL_NAMES[QueryRole.COMPONENTS])
        assert twice.b_value == once.b_value

    def test_built_request_carries_extras(self, api):
        msg = tedapi_pb2.Message()
        msg.ParseFromString(api._build_request(QueryRole.COMPONENTS))
        variables = json.loads(msg.message.payload.send.b.value)
        assert variables["hvpSignalNames"][-3:] == TEMP_EXTRAS["hvpSignalNames"]
        assert msg.message.payload.send.code == q.V2024_06_QUERIES["components"].code


# --- get_pw3_vitals --------------------------------------------------------------

class TestPw3VitalsTemperatures:

    def test_leader_and_follower_each_report_their_own_temps(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: FOLLOWER_PAYLOAD})
        leader, follower = vitals[f"TEPOD--{LEADER_DIN}"], vitals[f"TEPOD--{FOLLOWER_DIN}"]
        assert (leader["HVP_PackTempMax"], leader["HVP_PackTempMin"], leader["HVP_ShuntTemperature"]) \
            == (39.7, 35.1, 40.2)
        assert (follower["HVP_PackTempMax"], follower["HVP_PackTempMin"], follower["HVP_ShuntTemperature"]) \
            == (39.5, 34.8, 39.9)
        assert vitals[f"TEPINV--{LEADER_DIN}"]["PCH_AmbientTemp"] == 45.4
        assert vitals[f"TEPINV--{FOLLOWER_DIN}"]["PCH_AmbientTemp"] == 44.7

    def test_heatsink_passed_through_as_delivered(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: FOLLOWER_PAYLOAD})
        assert vitals[f"TEPINV--{LEADER_DIN}"]["PCH_heatsinkTemp"] == HEATSINK
        assert vitals[f"TEPINV--{FOLLOWER_DIN}"]["PCH_heatsinkTemp"] == HEATSINK

    def test_expansion_pack_gets_its_own_hvp_temps(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: FOLLOWER_PAYLOAD})
        expansion = vitals[f"TEPOD--{EXPANSION_DIN}"]
        assert (expansion["HVP_PackTempMax"], expansion["HVP_PackTempMin"]) == (38.0, 34.0)

    def test_bms_counters_follow_their_battery(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: FOLLOWER_PAYLOAD})
        expected = {LEADER_DIN: (1, 2), EXPANSION_DIN: (3, 4), FOLLOWER_DIN: (0, 0)}
        for din, counters in expected.items():
            pod = vitals[f"TEPOD--{din}"]
            assert (pod["BMS_LOG_tempOutOfBounds"], pod["BMS_LOG_tempOutOfBoundsCharge"]) == counters

    def test_any_requested_extra_is_surfaced(self, api):
        # Single source of truth: adding a name to EXTRA_SIGNAL_NAMES is the whole change
        future = json.loads(FOLLOWER_PAYLOAD)
        future["components"]["hvp"][0]["signals"].append(_sig("HVP_FutureSignal", 7))
        extras = q.EXTRA_SIGNAL_NAMES[QueryRole.COMPONENTS]
        grown = {"hvpSignalNames": extras["hvpSignalNames"] + ("HVP_FutureSignal",)}
        payloads = {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: json.dumps(future)}
        with patch.dict(extras, grown):
            vitals = _vitals_for(api, payloads)
        assert vitals[f"TEPOD--{FOLLOWER_DIN}"]["HVP_FutureSignal"] == 7
        assert vitals[f"TEPOD--{LEADER_DIN}"]["HVP_FutureSignal"] is None

    def test_malformed_hvp_entry_does_not_raise(self, api):
        # A None component entry used to crash the alert collection before any
        # vitals were built; now the battery still reports energy and None temps
        bad = json.loads(FOLLOWER_PAYLOAD)
        bad["components"]["hvp"][0] = None
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: json.dumps(bad)})
        assert vitals[f"TEPOD--{FOLLOWER_DIN}"]["HVP_PackTempMax"] is None
        assert vitals[f"TEPOD--{FOLLOWER_DIN}"]["POD_nom_energy_remaining"] == 6900

    def test_alerts_still_collected(self, api):
        alerting = json.loads(FOLLOWER_PAYLOAD)
        alerting["components"]["pch"][0]["activeAlerts"] = [{"name": "PCH_a054_test"}, {"bogus": 1}]
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: json.dumps(alerting)})
        assert vitals[f"TEPOD--{FOLLOWER_DIN}"]["alerts"] == ["PCH_a054_test"]

    def test_existing_pod_fields_unchanged(self, api):
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: FOLLOWER_PAYLOAD})
        pod = vitals[f"TEPOD--{LEADER_DIN}"]
        assert pod["POD_nom_energy_remaining"] == 7000
        assert pod["POD_nom_full_pack_energy"] == 13500
        assert pod["POD_nom_energy_to_be_charged"] == 6500
        assert vitals[f"TEPINV--{LEADER_DIN}"]["PINV_Fout"] == 60.0

    def test_missing_signals_yield_none_keys(self, api):
        bare = json.loads(FOLLOWER_PAYLOAD)
        bare["components"]["pch"][0]["signals"] = [_sig("PCH_AcFrequency", 60.0)]
        bare["components"]["bms"][0]["signals"] = bare["components"]["bms"][0]["signals"][:2]
        bare["components"]["hvp"][0]["signals"] = []
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: json.dumps(bare)})
        pod = vitals[f"TEPOD--{FOLLOWER_DIN}"]
        assert pod["HVP_PackTempMax"] is None and pod["HVP_ShuntTemperature"] is None
        assert pod["BMS_LOG_tempOutOfBounds"] is None
        assert pod["POD_nom_energy_remaining"] == 6900   # energy still parsed
        assert vitals[f"TEPINV--{FOLLOWER_DIN}"]["PCH_AmbientTemp"] is None
        assert vitals[f"TEPINV--{FOLLOWER_DIN}"]["PCH_heatsinkTemp"] is None

    def test_malformed_signal_lists_do_not_raise(self, api):
        bad = json.loads(FOLLOWER_PAYLOAD)
        bad["components"]["hvp"][0]["signals"] = None
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: json.dumps(bad)})
        assert vitals[f"TEPOD--{FOLLOWER_DIN}"]["HVP_PackTempMax"] is None

    def test_phantom_bms_slot_creates_no_entry(self, api):
        # A third BMS/HVP pair with no matching expansion DIN is skipped, temps or not
        phantom = json.loads(FOLLOWER_PAYLOAD)
        phantom["components"]["bms"].append(phantom["components"]["bms"][0])
        phantom["components"]["hvp"].append(dict(phantom["components"]["hvp"][0], serialNumber=""))
        vitals = _vitals_for(api, {LEADER_DIN: LEADER_PAYLOAD, FOLLOWER_DIN: json.dumps(phantom)})
        assert len([k for k in vitals if k.startswith("TEPOD--")]) == 3


class TestComponentSignalValue:

    @pytest.mark.parametrize("components", [None, [], [None], [{"signals": None}], ["junk"]])
    def test_tolerates_malformed_input(self, components):
        assert _component_signal_value(components, "PCH_AmbientTemp") is None

    def test_first_non_none_wins(self):
        comps = [{"signals": [_sig("X", None)]}, {"signals": [_sig("X", 1.5)]}]
        assert _component_signal_value(comps, "X") == 1.5


# --- temps() facade ----------------------------------------------------------------

@pytest.fixture(name="pw")
def fixture_pw():
    with patch('pypowerwall.PyPowerwallCloud'):
        return Powerwall(host='', password='', email='test@example.com', cloudmode=True, siteid=None)


class TestTempsFacade:

    def test_pw3_reports_pack_max_per_battery_in_vitals_order(self, pw):
        vitals = {
            f"TEPOD--{LEADER_DIN}": {"HVP_PackTempMax": 39.7},
            f"TEPINV--{LEADER_DIN}": {"PCH_AmbientTemp": 45.4},
            f"TEPOD--{EXPANSION_DIN}": {"HVP_PackTempMax": 38.0},
            f"TEPOD--{FOLLOWER_DIN}": {"HVP_PackTempMax": 39.5},
        }
        with patch.object(pw, 'vitals', return_value=vitals):
            temps = pw.temps()
        assert list(temps.items()) == [
            (f"TEPOD--{LEADER_DIN}", 39.7),
            (f"TEPOD--{EXPANSION_DIN}", 38.0),
            (f"TEPOD--{FOLLOWER_DIN}", 39.5),
        ]

    def test_inverter_temps_never_feed_temps(self, pw):
        # temps() is a derived summary: pack temps only, never TEPINV values
        vitals = {f"TEPINV--{LEADER_DIN}": {"PCH_AmbientTemp": 45.4, "PCH_heatsinkTemp": HEATSINK}}
        with patch.object(pw, 'vitals', return_value=vitals):
            assert pw.temps() == {}

    def test_missing_reading_keeps_its_position(self, pw):
        # /temps/pw numbers entries by position and must match /pod, which lists
        # every battery - so a battery without a reading stays in place as None
        vitals = {
            f"TEPOD--{LEADER_DIN}": {"HVP_PackTempMax": None},
            f"TEPOD--{FOLLOWER_DIN}": {"HVP_PackTempMax": 39.5},
        }
        with patch.object(pw, 'vitals', return_value=vitals):
            temps = pw.temps()
        assert list(temps.items()) == [(f"TEPOD--{LEADER_DIN}", None), (f"TEPOD--{FOLLOWER_DIN}", 39.5)]

    def test_pw3_without_reading_stays_empty(self, pw):
        with patch.object(pw, 'vitals', return_value={f"TEPOD--{LEADER_DIN}": {"HVP_PackTempMax": None}}):
            assert pw.temps() == {}

    def test_pw2_behavior_unchanged(self, pw):
        # PW2: TETHC ambient (None preserved as before); PW2 TEPOD blocks carry no HVP temps
        vitals = {
            "TETHC--1092170-03-E--TG1": {"THC_AmbientTemp": 22.5},
            "TETHC--1092170-03-E--TG2": {"THC_AmbientTemp": None},
            "TEPOD--1081100-10-U--TG1": {"POD_nom_energy_remaining": 1000},
        }
        with patch.object(pw, 'vitals', return_value=vitals):
            assert pw.temps() == {"TETHC--1092170-03-E--TG1": 22.5, "TETHC--1092170-03-E--TG2": None}

    def test_jsonformat(self, pw):
        with patch.object(pw, 'vitals', return_value={f"TEPOD--{LEADER_DIN}": {"HVP_PackTempMax": 39.7}}):
            assert json.loads(pw.temps(jsonformat=True)) == {f"TEPOD--{LEADER_DIN}": 39.7}
