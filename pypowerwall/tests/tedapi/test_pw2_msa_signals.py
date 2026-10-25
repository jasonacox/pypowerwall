"""PW2 per-Powerwall signals: requested via the unsigned msaSignals variable of the
V2024_06 DeviceControllerQuery and surfaced on the PW2 TEPINV / TETHC / TESYNC
vitals blocks, filling keys that were placeholders (None). A second, later change
appends TEPOD to the unsigned msaComp.types and the POD_available_* names to
msaSignals, filling the TEPOD blocks' POD_available_* placeholders from the msa
TEPOD components (see the POD sections below; that hardware basis is in
queries/__init__.py).

Hardware basis (2026-10-09/11, 4x Powerwall 2 behind a Backup Gateway 1, firmware
26.34.0, v1r LAN): the gateway honors the extra names with the capture's signature
and type order intact. fixtures/pw2_device_controller_full.json is a raw response
to the #416 request from that gateway (before TEPOD was added), with identifiers
replaced: PACKAGE_SERIAL_n is the n-th package in esCan.bus.THC order and
MODULE_SERIAL_n is the msa TEPINV component that follows that package's TETHC, so
the expected pairing is visible.
"""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pypowerwall.tedapi import TEDAPI, _signal_value, _pw2_msa_module_pairing
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.queries import QueryRole
from pypowerwall.tests.unit.test_tedapi_cached_fetch import make_tedapi

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "pw2_device_controller_full.json")
                     .read_text(encoding="utf-8"))
CONFIG = {"vin": "1118431-00-L--GATEWAY_SERIAL"}
PACKAGES = [f"PACKAGE_SERIAL_{n}" for n in range(1, 5)]
PART = {1: "1092170-05-J", 2: "1092170-05-J", 3: "1092170-05-J", 4: "1092170-13-J"}

PW2_NAMES = [
    "PINV_EnergyCharged", "PINV_EnergyDischarged",
    "PINV_LifetimeEnergyCharged", "PINV_LifetimeEnergyDischarged",
    "PINV_HeatsinkTemp", "PINV_PllFrequency", "PINV_PllLocked", "PINV_Qout",
    "PINV_ReadyForGridForming", "PINV_HardwareEnableLine", "PINV_PowerLimiter",
    "THC_State", "SYNC_ExternallyPowered", "SYNC_SiteSwitchEnabled",
]

# requested together with the PW2 names (the TEPOD components carry them)
POD_POWER_NAMES = ["POD_available_charge_power", "POD_available_dischg_power"]

# TEPINV keys vitals() now fills from the msa module (placeholders + new keys)
PINV_MSA_KEYS = [n for n in PW2_NAMES if n.startswith("PINV_")]


def _msa_component(serial):
    return next(c for c in FIXTURE["components"]["msa"] if c["serialNumber"] == serial)


def _msa_value(serial, name):
    sig = next(s for s in _msa_component(serial)["signals"] if s["name"] == name)
    return _signal_value(sig)


def _vitals(status):
    api = make_tedapi()
    with patch.object(TEDAPI, "get_config", return_value=copy.deepcopy(CONFIG)), \
            patch.object(TEDAPI, "get_device_controller", return_value=status):
        return api.vitals()


def _tepinv(vitals, n):
    return vitals[f"TEPINV--{PART[n]}--PACKAGE_SERIAL_{n}"]


# --- query layer ---------------------------------------------------------------

class TestDeviceControllerRequestQuery:

    def test_capture_is_pristine(self):
        raw = json.loads((q._DIR / "V2024_06.json").read_text(encoding="utf-8"))
        assert q.V2024_06_QUERIES["device_controller_full"].b_value == raw["device_controller_full"]["b_value"]

    def test_signature_and_text_unchanged(self):
        captured = q.V2024_06_QUERIES["device_controller_full"]
        request = q.get_query(QueryRole.DEVICE_CONTROLLER_FULL)
        assert (request.text, request.code) == (captured.text, captured.code)

    def test_only_signal_names_are_appended(self):
        captured = json.loads(q.V2024_06_QUERIES["device_controller_full"].b_value)
        request = json.loads(q.get_query(QueryRole.DEVICE_CONTROLLER_FULL).b_value)
        # the capture's type list stays; TEPOD (validated 2026-10-18) is appended
        # after it, so TEPINV keeps its two captured positions
        captured_types = captured["msaComp"]["types"]
        assert request["msaComp"]["types"][:len(captured_types)] == captured_types
        assert request["msaComp"]["types"][len(captured_types):] == list(q.PW2_MSA_COMPONENT_TYPES)
        # #419's SYNC_Uptime goes first, then the PW2 names, then the POD names
        assert request["msaSignals"] == captured["msaSignals"] + list(q.GATEWAY_MSA_SIGNAL_NAMES) \
            + PW2_NAMES + POD_POWER_NAMES
        assert set(request) == set(captured)

    def test_single_source_of_truth(self):
        assert list(q.PW2_MSA_SIGNAL_NAMES) == PW2_NAMES
        assert list(q.PW2_POD_POWER_SIGNAL_NAMES) == POD_POWER_NAMES
        assert q.EXTRA_SIGNAL_NAMES[QueryRole.DEVICE_CONTROLLER_FULL]["msaSignals"] == (
            q.GATEWAY_MSA_SIGNAL_NAMES + q.PW2_MSA_SIGNAL_NAMES + q.PW2_POD_POWER_SIGNAL_NAMES)
        assert q.EXTRA_COMPONENT_TYPES[QueryRole.DEVICE_CONTROLLER_FULL] == {
            "msaComp": q.PW2_MSA_COMPONENT_TYPES}

    def test_basic_query_and_v2026_06_untouched(self):
        assert q.get_query(QueryRole.DEVICE_CONTROLLER_BASIC) is q.V2024_06_QUERIES["device_controller_basic"]
        assert q.get_query(QueryRole.DEVICE_CONTROLLER_FULL, "V2026_06") is q.V2026_06_QUERIES["DeviceControllerQuery"]

    def test_v2026_06_cannot_carry_tepod(self):
        # Tesla's signed DeviceControllerQuery lists its component types inline
        assert "TEPOD" not in q.get_query(QueryRole.DEVICE_CONTROLLER_FULL, "V2026_06").text

    def test_fixture_was_made_with_this_request(self):
        # every requested PW2 name is echoed on the populated components that own it
        echoed = {s["name"] for c in FIXTURE["components"]["msa"] if c["serialNumber"]
                  for s in c["signals"]}
        assert set(PW2_NAMES) <= echoed


# --- signal values -------------------------------------------------------------

class TestMsaSignalValue:

    @pytest.mark.parametrize("signal, expected", [
        ({"name": "x", "value": 9140978, "boolValue": None, "textValue": None}, 9140978),
        ({"name": "x", "value": 0, "boolValue": None, "textValue": None}, 0),
        ({"name": "x", "value": None, "boolValue": False, "textValue": None}, False),
        ({"name": "x", "value": None, "boolValue": None, "textValue": "THC_STATE_AUTONOMOUSCONTROL"},
         "THC_STATE_AUTONOMOUSCONTROL"),
        ({"name": "x", "value": None, "boolValue": None, "textValue": ""}, ""),   # as delivered
        ({"name": "x", "value": None, "boolValue": None, "textValue": None}, None),
        ({"name": "x"}, None),
        (None, None),
        ("junk", None),
    ])
    def test_first_delivered_field(self, signal, expected):
        assert _signal_value(signal) == expected


# --- module -> package pairing ---------------------------------------------------

def _thc(serial):
    return {"partNumber": "1092170-05-J", "serialNumber": serial,
            "signals": [{"name": "THC_AmbientTemp", "value": 30.0}]}


def _pinv(serial):
    return {"partNumber": "1081100-10-Q", "serialNumber": serial,
            "signals": [{"name": "PINV_EnergyCharged", "value": 1}]}


def _tepod(serial):
    return {"partNumber": "1081100-10-Q", "serialNumber": serial,
            "signals": [{"name": "POD_available_charge_power", "value": 7000},
                        {"name": "POD_available_dischg_power", "value": 8570}]}


def _family_names(component):
    return {s["name"].split("_", 1)[0] for s in component["signals"]}


def _empty(*names):
    return {"partNumber": "", "serialNumber": "",
            "signals": [{"name": n, "value": None} for n in names]}


class TestModulePairing:

    def test_fixture_pairs_each_package_with_the_following_module(self):
        pairs = _pw2_msa_module_pairing(FIXTURE["components"]["msa"], PACKAGES)
        assert {pkg: c["serialNumber"] for pkg, c in pairs.items()} == {
            f"PACKAGE_SERIAL_{n}": f"MODULE_SERIAL_{n}" for n in range(1, 5)}

    def test_fixture_empty_slots_are_serial_less(self):
        # 6 empty battery slots after the 4 real ones, all without a serial
        msa = FIXTURE["components"]["msa"]
        assert len(msa) == 40
        assert sum(1 for c in msa if not c["serialNumber"] and _family_names(c) == {"THC"}) == 6

    def test_serial_less_slots_are_skipped_even_when_live(self):
        # On the validation gateway two serial-less msa components returned a LIVE
        # ISLAND_GridConnected (when that name was requested), so the filter must be the
        # serial, not "has a live signal" (cf. the PW3 phantom device in #406)
        live = _empty()
        live["signals"] = [{"name": "PINV_EnergyCharged", "value": 5},
                           {"name": "ISLAND_GridConnected", "value": None, "boolValue": None,
                            "textValue": "ISLAND_GridConnected_Connected"}]
        msa = [_thc("P1"), live, _pinv("M1"), _empty("THC_State"),
               _thc("P2"), _pinv("M2"), _empty("PINV_EnergyCharged")]
        pairs = _pw2_msa_module_pairing(msa, ["P1", "P2"])
        assert {k: v["serialNumber"] for k, v in pairs.items()} == {"P1": "M1", "P2": "M2"}

    def test_tepod_components_after_their_module_are_passed_over(self):
        # the TEPOD components (requested for the POD_* placeholders) each follow
        # their module's TEPINV and repeat its serial: family POD with the slot
        # already closed -> passed over without breaking the walk
        msa = [_thc("P1"), _pinv("M1"), _tepod("M1"), _thc("P2"), _pinv("M2"), _tepod("M2")]
        pairs = _pw2_msa_module_pairing(msa, ["P1", "P2"])
        assert {k: v["serialNumber"] for k, v in pairs.items()} == {"P1": "M1", "P2": "M2"}

    def test_tepod_before_its_module_is_irregular(self):
        # the validated layout puts each TEPOD after its TEPINV; anything else is
        # a stray serial-bearing component and voids the pairing, strict on purpose
        msa = [_thc("P1"), _tepod("M1"), _pinv("M1")]
        assert _pw2_msa_module_pairing(msa, ["P1"]) == {}

    @pytest.mark.parametrize("msa, packages", [
        ([_pinv("M1"), _thc("P1")], ["P1"]),                                    # module before its package
        ([_thc("P1"), _thc("P2"), _pinv("M1"), _pinv("M2")], ["P1", "P2"]),    # two packages in a row
        ([_thc("P1"), _pinv("M1"), _pinv("M2")], ["P1"]),                       # two modules for one package
        ([_thc("P1"), _pinv("M1"), _thc("P2")], ["P1", "P2"]),                  # last package unpaired
        ([_thc("PX"), _pinv("M1")], ["P1"]),                                    # TETHC not in esCan.bus.THC
        ([_thc("P1"), _pinv("M1")], ["P1", "P2"]),                              # fewer pairs than packages
        ([_thc("P1"), _pinv("M1"), _thc("P1"), _pinv("M2")], ["P1"]),           # repeated package serial
        ([_thc("P1"), _pinv("M1"), _thc("P2"), _pinv("M1")], ["P1", "P2"]),    # repeated module serial
        ([_thc("P1"), {"serialNumber": "GW", "signals": []}, _pinv("M1")], ["P1"]),  # other device in between
    ])
    def test_irregular_layouts_pair_nothing(self, msa, packages):
        assert _pw2_msa_module_pairing(msa, packages) == {}

    @pytest.mark.parametrize("msa", [None, [], ["junk", None, 3]])
    def test_missing_or_malformed_msa(self, msa):
        assert _pw2_msa_module_pairing(msa, ["P1"]) == {}


# --- vitals ----------------------------------------------------------------------

class TestPw2Vitals:

    def test_tepinv_placeholders_filled_from_its_own_module(self):
        vitals = _vitals(copy.deepcopy(FIXTURE))
        for n in range(1, 5):
            block = _tepinv(vitals, n)
            for key in PINV_MSA_KEYS:
                assert block[key] == _msa_value(f"MODULE_SERIAL_{n}", key), (n, key)

    def test_values_as_delivered(self):
        block = _tepinv(_vitals(copy.deepcopy(FIXTURE)), 1)
        assert isinstance(block["PINV_EnergyCharged"], (int, float)) and block["PINV_EnergyCharged"] > 0
        assert block["PINV_PllLocked"] is True              # boolValue, not value
        assert block["PINV_ReadyForGridForming"] is True
        assert block["PINV_PowerLimiter"] is None           # echoed with no value on this firmware

    def test_modules_are_not_interchangeable(self):
        # distinct per-module counters, so a wrong pairing could not pass the test above
        values = [_msa_value(f"MODULE_SERIAL_{n}", "PINV_EnergyCharged") for n in range(1, 5)]
        assert len(set(values)) == 4

    def test_thc_state_and_sync_signals(self):
        vitals = _vitals(copy.deepcopy(FIXTURE))
        for n in range(1, 5):
            assert vitals[f"TETHC--{PART[n]}--PACKAGE_SERIAL_{n}"]["THC_State"] == \
                _msa_value(f"PACKAGE_SERIAL_{n}", "THC_State")
        sync = vitals["TESYNC--1118431-00-L--GATEWAY_SERIAL"]
        assert sync["SYNC_ExternallyPowered"] is False      # boolValue False must not become None
        assert sync["SYNC_SiteSwitchEnabled"] is False

    def test_no_phantom_blocks_from_serial_less_slots(self):
        vitals = _vitals(copy.deepcopy(FIXTURE))
        tepinv = sorted(k for k in vitals if k.startswith("TEPINV--"))
        assert tepinv == sorted(f"TEPINV--{PART[n]}--PACKAGE_SERIAL_{n}" for n in range(1, 5))

    def test_tepod_placeholders_without_tepod_components_stay_none(self):
        # this fixture predates the TEPOD request: no TEPOD components arrive, so
        # the POD_* keys keep their placeholder None (the unswept ones always do)
        pod = _vitals(copy.deepcopy(FIXTURE))[f"TEPOD--{PART[1]}--PACKAGE_SERIAL_1"]
        assert pod["POD_ActiveHeating"] is None and pod["POD_state"] is None
        assert pod["POD_available_charge_power"] is None and pod["POD_available_dischg_power"] is None

    def test_tepod_available_power_filled_from_its_module(self):
        # a TEPOD carries the serial of its TEPINV module: the package's POD block
        # takes POD_available_charge_power/dischg_power from it, other packages
        # keep None
        status = copy.deepcopy(FIXTURE)
        msa = status["components"]["msa"]
        i = next(i for i, c in enumerate(msa) if c["serialNumber"] == "MODULE_SERIAL_2")
        msa.insert(i + 1, _tepod("MODULE_SERIAL_2"))
        vitals = _vitals(status)
        pod1 = vitals[f"TEPOD--{PART[1]}--PACKAGE_SERIAL_1"]
        assert pod1["POD_available_charge_power"] is None and pod1["POD_available_dischg_power"] is None
        pod2 = vitals[f"TEPOD--{PART[2]}--PACKAGE_SERIAL_2"]
        assert pod2["POD_available_charge_power"] == 7000
        assert pod2["POD_available_dischg_power"] == 8570

    def test_tepod_without_a_paired_module_stays_none(self):
        status = copy.deepcopy(FIXTURE)
        status["components"]["msa"].append(_tepod("UNKNOWN_MODULE"))
        pod = _vitals(status)[f"TEPOD--{PART[1]}--PACKAGE_SERIAL_1"]
        assert pod["POD_available_charge_power"] is None

    def test_tepod_signals_stay_off_the_pinv_block(self):
        status = copy.deepcopy(FIXTURE)
        msa = status["components"]["msa"]
        i = next(i for i, c in enumerate(msa) if c["serialNumber"] == "MODULE_SERIAL_1")
        msa.insert(i + 1, _tepod("MODULE_SERIAL_1"))
        block = _tepinv(_vitals(status), 1)
        assert block["PINV_EnergyCharged"] == _msa_value("MODULE_SERIAL_1", "PINV_EnergyCharged")
        assert all(not key.startswith("POD_") for key in block)

    def test_ambiguous_pairing_leaves_every_module_value_none(self):
        status = copy.deepcopy(FIXTURE)
        msa = status["components"]["msa"]
        i = next(i for i, c in enumerate(msa) if c["serialNumber"] == "MODULE_SERIAL_2")
        msa[i], msa[i - 1] = msa[i - 1], msa[i]            # module 2 now precedes package 2
        vitals = _vitals(status)
        for n in range(1, 5):
            block = _tepinv(vitals, n)
            assert all(block[key] is None for key in PINV_MSA_KEYS), n
        # serial-joined signals don't depend on order and still fill
        assert vitals[f"TETHC--{PART[1]}--PACKAGE_SERIAL_1"]["THC_State"] is not None

    def test_every_other_key_unchanged(self):
        # Strip the PW2 extras from the response: every key outside them must be identical,
        # and the extras fall back to the old placeholder None
        stripped = copy.deepcopy(FIXTURE)
        for c in stripped["components"]["msa"]:
            c["signals"] = [s for s in c["signals"] if s["name"] not in PW2_NAMES]
        with_extras, without = _vitals(copy.deepcopy(FIXTURE)), _vitals(stripped)
        assert with_extras.keys() == without.keys()
        for name, block in without.items():
            if not isinstance(block, dict) or name == "VITALS":
                continue
            for key, value in block.items():
                if key in PW2_NAMES:
                    assert value is None, (name, key)
                else:
                    assert with_extras[name][key] == value, (name, key)

    def test_sync_value_is_not_overwritten_by_a_null_echo(self):
        # the gateway serial is on two msa components; a None on one must not mask the other
        status = copy.deepcopy(FIXTURE)
        gw = next(c for c in status["components"]["msa"] if c["serialNumber"] == "GATEWAY_SERIAL")
        gw["signals"] = [{"name": "SYNC_ExternallyPowered", "value": None, "boolValue": None, "textValue": None}]
        sync = _vitals(status)["TESYNC--1118431-00-L--GATEWAY_SERIAL"]
        assert sync["SYNC_ExternallyPowered"] is False

    def test_withheld_pairing_is_logged(self, caplog):
        status = copy.deepcopy(FIXTURE)
        msa = status["components"]["msa"]
        i = next(i for i, c in enumerate(msa) if c["serialNumber"] == "MODULE_SERIAL_1")
        msa[i], msa[i - 1] = msa[i - 1], msa[i]
        with caplog.at_level("DEBUG", logger="pypowerwall.tedapi"):
            _vitals(status)
        assert "could not be paired" in caplog.text

    def test_sync_fills_on_a_site_without_powerwall_2(self):
        # PW3 behind a Backup Gateway 2: esCan.bus.SYNC has a serial, there are no THC
        # packages, and the gateway's own msa component carries the SYNC signals
        status = {
            "esCan": {"bus": {"SYNC": {"packagePartNumber": "1232100-00-E",
                                       "packageSerialNumber": "GW2_SERIAL"}}},
            "components": {"msa": [
                {"partNumber": "1232100-00-E", "serialNumber": "GW2_SERIAL", "signals": [
                    {"name": "SYNC_ExternallyPowered", "value": None, "boolValue": False, "textValue": None},
                    {"name": "SYNC_SiteSwitchEnabled", "value": None, "boolValue": False, "textValue": None},
                    {"name": "PINV_EnergyCharged", "value": None, "boolValue": None, "textValue": None}]},
                {"partNumber": "", "serialNumber": "", "signals": [
                    {"name": "THC_State", "value": None, "boolValue": None, "textValue": None}]},
            ]},
        }
        vitals = _vitals(status)
        sync = vitals["TESYNC--1232100-00-E--GW2_SERIAL"]
        assert sync["SYNC_ExternallyPowered"] is False and sync["SYNC_SiteSwitchEnabled"] is False
        assert not [k for k in vitals if k.startswith(("TEPINV--", "TETHC--"))]

    def test_no_msa_at_all(self):
        status = copy.deepcopy(FIXTURE)
        status["components"] = None
        block = _tepinv(_vitals(status), 1)
        assert all(block[key] is None for key in PINV_MSA_KEYS)
