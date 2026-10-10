"""Unit tests for Tesla Remote Meter (teslaRemoteMeter) plumbing.

Wireless CT "remote meters" (config.json meter type "trm_mb" or "trm_wifi") report through the
Device Controller Full query's teslaRemoteMeter field returned by
get_device_controller() - a field that was already being fetched but never
read by anything. These tests cover config-driven CT selection/scaling,
the site/solar aggregate fallbacks, vitals() exposure, and holding solar
through a SolarMeterComms dropout in /api/meters/aggregates.

All DIN/serial values here are fabricated test fixtures, not data captured
from a real gateway.
"""
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import REMOTE_METER_TYPES, TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import SOLAR_METER_HOLD_ZERO_W, PyPowerwallTEDAPI

GATEWAY_DIN = "1707000-21-M--TESTGW00000001"
REMOTE_METER_DIN = "1234567-00-E--TESTMETER0001"
REMOTE_METER_DIN_2 = "1234567-00-E--TESTMETER0002"


def _remote_meter_config(location="solar", cts=None, factor=1, din=REMOTE_METER_DIN,
                         meter_type="trm_mb"):
    return {
        "vin": GATEWAY_DIN,
        "meters": [
            {
                "location": location,
                "type": meter_type,
                "cts": cts if cts is not None else [True, False, False, False],
                "inverted": [False, False, False, False],
                "connection": {"device_serial": din},
                "real_power_scale_factor": factor,
            }
        ],
    }


def _ct(voltage=0, power=0, reactive=0, current=0, exported=0, imported=0):
    return {
        "voltageV": voltage,
        "realPowerW": power,
        "reactivePowerVAR": reactive,
        "currentA": current,
        "energyExportedWs": exported,
        "energyImportedWs": imported,
    }


def _remote_meter_status(real_power=1000.0, reactive=5.0, voltage=121.0, current=8.3,
                          energy_exported=1000, energy_imported=2000, din=REMOTE_METER_DIN):
    return {
        "teslaRemoteMeter": {
            "meters": [
                {
                    "din": din,
                    "reading": {
                        "timestamp": "2025-01-01T00:00:00-08:00",
                        "firmwareVersion": "deadbeef0001",
                        "rssiDb": -50,
                        "ctReadings": [
                            _ct(voltage, real_power, reactive, current, energy_exported, energy_imported),
                            _ct(),
                            _ct(),
                            _ct(),
                        ],
                    },
                    "firmwareUpdate": None,
                }
            ],
            "detectedWired": [{"din": din, "serialPort": None}],
        }
    }


def _hierarchy_key(din, ct_index):
    """The hierarchy is keyed by "{din}:{ct index}", not just the CT slot, so a
    second remote meter doesn't overwrite the first."""
    return f"{din}:{ct_index}"


def _make_tedapi():
    with patch.object(TEDAPI, 'connect', return_value=True):
        return TEDAPI(gw_pwd='password')


def _make_backend():
    with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
        backend = PyPowerwallTEDAPI(gw_pwd='password')
    backend.tedapi.pw3 = False
    return backend


def _remote_ct(index, current=0, power=0, voltage=0, location=None):
    """A hand-built remote-meter hierarchy entry, as returned by
    aggregate_remote_meter_data()/get_remote_meter_readings() - includes
    "Index" since the extractors map CTs to phases by that field, not by
    iteration order."""
    return {
        "Index": index,
        "InstCurrent": current,
        "InstRealPower": power,
        "InstVoltage": voltage,
        "Location": location,
    }


class TestDeriveMeterConfig:
    """derive_meter_config() gained a `types` filter; the default must keep
    matching only Neurio meters so existing callers are unaffected."""

    def test_default_type_still_matches_neurio(self):
        ted = _make_tedapi()
        config = {"meters": [{
            "type": "neurio_w2_tcp", "location": "site",
            "cts": [True, True, False, False],
            "connection": {"device_serial": "NEURIOSN1"},
        }]}
        result = ted.derive_meter_config(config)
        assert "NEURIOSN1" in result
        assert result["NEURIOSN1"]["type"] == "neurio_w2_tcp"

    def test_default_type_ignores_remote_meter(self):
        ted = _make_tedapi()
        result = ted.derive_meter_config(_remote_meter_config())
        assert result == {}

    def test_trm_mb_type_filter(self):
        ted = _make_tedapi()
        result = ted.derive_meter_config(_remote_meter_config(location="solar", factor=2),
                                          types=("trm_mb",))
        assert REMOTE_METER_DIN in result
        entry = result[REMOTE_METER_DIN]
        assert entry["type"] == "trm_mb"
        assert entry["location"] == ["solar", "solar", "solar", "solar"]
        assert entry["cts"] == [True, False, False, False]
        assert entry["real_power_scale_factor"] == 2

    def test_trm_mb_filter_ignores_neurio(self):
        ted = _make_tedapi()
        config = {"meters": [{
            "type": "neurio_w2_tcp", "location": "site",
            "connection": {"device_serial": "NEURIOSN1"},
        }]}
        assert ted.derive_meter_config(config, types=("trm_mb",)) == {}

    def test_missing_meters_key_returns_empty(self):
        ted = _make_tedapi()
        assert ted.derive_meter_config({}, types=("trm_mb",)) == {}


class TestAggregateRemoteMeterData:
    def test_ct_scaling_location_and_filtering(self):
        ted = _make_tedapi()
        config = _remote_meter_config(location="solar", factor=2)
        status = _remote_meter_status(real_power=500.0, current=4.0)
        meter_config = ted.derive_meter_config(config, types=("trm_mb",))

        flat, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)

        key = _hierarchy_key(REMOTE_METER_DIN, 0)
        assert hierarchy[key]["InstRealPower"] == 1000.0  # scaled by factor 2
        assert hierarchy[key]["Location"] == "solar"
        assert hierarchy[key]["InstCurrent"] == 4.0
        assert hierarchy[key]["Index"] == 0
        assert _hierarchy_key(REMOTE_METER_DIN, 1) not in hierarchy  # cts[1] is False - filtered out

        flat_key = f"TRM--{REMOTE_METER_DIN}"
        assert flat_key in flat
        assert flat[flat_key]["TRM_CT0_InstRealPower"] == 1000.0
        assert flat[flat_key]["serialNumber"] == REMOTE_METER_DIN
        assert flat[flat_key]["componentParentDin"] == GATEWAY_DIN
        assert flat[flat_key]["manufacturer"] == "TESLA"

    def test_energy_accumulators_pass_through(self):
        ted = _make_tedapi()
        config = _remote_meter_config()
        status = _remote_meter_status(energy_exported=12345, energy_imported=67890)
        meter_config = ted.derive_meter_config(config, types=("trm_mb",))

        _, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)
        key = _hierarchy_key(REMOTE_METER_DIN, 0)
        assert hierarchy[key]["EnergyExportedWs"] == 12345
        assert hierarchy[key]["EnergyImportedWs"] == 67890

    def test_explicit_null_real_power_does_not_raise(self):
        """realPowerW present but explicitly null (not just absent) must not
        raise TypeError from `None * factor` - .get(key, 0) only substitutes
        the default when the key is *missing*, not when its value is None."""
        ted = _make_tedapi()
        config = _remote_meter_config(factor=3)
        status = _remote_meter_status()
        status["teslaRemoteMeter"]["meters"][0]["reading"]["ctReadings"][0]["realPowerW"] = None
        meter_config = ted.derive_meter_config(config, types=("trm_mb",))

        _, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["InstRealPower"] == 0

    def test_no_meter_config_includes_unfiltered_cts(self):
        """No config.json entry for this din: derive_meter_config() would
        return {}, and with no cts list to check against, every CT the
        gateway reports is passed through as-is (mirrors aggregate_neurio_data)."""
        ted = _make_tedapi()
        config = {"vin": GATEWAY_DIN}  # no "meters" key at all
        status = _remote_meter_status()

        flat, hierarchy = ted.aggregate_remote_meter_data(config, status, {})
        assert len(hierarchy) == 4  # all 4 CTs included, unfiltered
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["Location"] is None
        assert flat[f"TRM--{REMOTE_METER_DIN}"]["manufacturer"] is None

    def test_no_remote_meters_in_status(self):
        ted = _make_tedapi()
        flat, hierarchy = ted.aggregate_remote_meter_data({"vin": GATEWAY_DIN}, {}, {})
        assert flat == {}
        assert hierarchy == {}

    def test_meter_entry_without_din_is_skipped(self):
        ted = _make_tedapi()
        status = {"teslaRemoteMeter": {"meters": [{"reading": {"ctReadings": []}}]}}
        flat, hierarchy = ted.aggregate_remote_meter_data({"vin": GATEWAY_DIN}, status, {})
        assert flat == {}
        assert hierarchy == {}

    def test_multiple_meters_do_not_collide_in_hierarchy(self):
        """Regression: the hierarchy used to be keyed by CT slot alone
        ("CT0"), so a second remote meter's CT0 silently overwrote the
        first's. Both meters' CT0 must be independently addressable."""
        ted = _make_tedapi()
        config = _remote_meter_config(location="solar")
        config["meters"].append({
            "location": "site",
            "type": "trm_mb",
            "cts": [True, False, False, False],
            "inverted": [False, False, False, False],
            "connection": {"device_serial": REMOTE_METER_DIN_2},
            "real_power_scale_factor": 1,
        })
        status = _remote_meter_status(real_power=100.0, din=REMOTE_METER_DIN)
        status["teslaRemoteMeter"]["meters"].append(
            _remote_meter_status(real_power=200.0, din=REMOTE_METER_DIN_2)
            ["teslaRemoteMeter"]["meters"][0]
        )
        meter_config = ted.derive_meter_config(config, types=("trm_mb",))

        _, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)

        assert len(hierarchy) == 2
        first = hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]
        second = hierarchy[_hierarchy_key(REMOTE_METER_DIN_2, 0)]
        assert first["InstRealPower"] == 100.0
        assert first["Location"] == "solar"
        assert second["InstRealPower"] == 200.0
        assert second["Location"] == "site"

    def test_skipped_ct_slot_preserves_index_for_phase_mapping(self):
        """cts=[True, False, True, False]: CT1 is filtered out, but CT2 must
        keep Index=2 (not collapse to the 2nd surviving position) so a
        consumer mapping Index->phase doesn't misassign it to phase B."""
        ted = _make_tedapi()
        config = _remote_meter_config(cts=[True, False, True, False])
        status = _remote_meter_status()
        status["teslaRemoteMeter"]["meters"][0]["reading"]["ctReadings"][2] = _ct(
            voltage=119.0, power=300.0, current=2.5)
        meter_config = ted.derive_meter_config(config, types=("trm_mb",))

        _, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)

        assert len(hierarchy) == 2
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["Index"] == 0
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 2)]["Index"] == 2
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 2)]["InstRealPower"] == 300.0


class TestGetRemoteMeterReadings:
    def test_combines_controller_and_config(self):
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status())
        ted.get_config = MagicMock(return_value=_remote_meter_config(location="solar"))

        hierarchy = ted.get_remote_meter_readings()
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["Location"] == "solar"

    def test_none_controller_returns_empty(self):
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=None)
        ted.get_config = MagicMock(return_value=_remote_meter_config())
        assert ted.get_remote_meter_readings() == {}

    def test_none_config_returns_empty(self):
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status())
        ted.get_config = MagicMock(return_value=None)
        assert ted.get_remote_meter_readings() == {}

    def test_forwards_force_flag(self):
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status())
        ted.get_config = MagicMock(return_value=_remote_meter_config())

        ted.get_remote_meter_readings(force=True)
        ted.get_device_controller.assert_called_once_with(force=True)
        ted.get_config.assert_called_once_with(force=True)

    def test_skips_device_controller_fetch_when_no_remote_meter_configured(self):
        """Most installs have no remote meter - this must not cost them an
        extra Device Controller Full query fetch on every poll."""
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status())
        assert ted.get_remote_meter_readings(config={"vin": GATEWAY_DIN}) == {}
        ted.get_device_controller.assert_not_called()

    def test_uses_passed_in_config_without_refetching(self):
        """Callers that already fetched config.json (the site/solar aggregate
        extractors) should not trigger a second get_config() call."""
        ted = _make_tedapi()
        ted.get_config = MagicMock(return_value={"vin": GATEWAY_DIN})
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status())

        hierarchy = ted.get_remote_meter_readings(config=_remote_meter_config(location="solar"))
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["Location"] == "solar"
        ted.get_config.assert_not_called()


class TestVitalsRemoteMeter:
    def test_vitals_includes_trm_block(self):
        ted = _make_tedapi()
        ted.pw3 = False
        status = {
            **_remote_meter_status(),
            'control': {'alerts': {'active': []}},
            'components': {'msa': []},
            'esCan': {
                'bus': {
                    'PVAC': [], 'PVS': [], 'THC': [], 'POD': [], 'PINV': [],
                    'SYNC': {}, 'ISLANDER': {}, 'MSA': {},
                },
            },
        }
        ted.get_config = MagicMock(return_value=_remote_meter_config(location="solar"))
        ted.get_device_controller = MagicMock(return_value=status)

        vitals = ted.vitals()
        key = f"TRM--{REMOTE_METER_DIN}"
        assert key in vitals
        assert vitals[key]["TRM_CT0_Location"] == "solar"


class TestExtractSiteSectionRemoteMeterFallback:
    """_extract_site_section() tries Meter X, then Meter Z, then Neurio,
    then a Tesla Remote Meter configured for the "site" location."""

    def _status(self):
        return {
            "esCan": {"bus": {"SYNC": {}, "MSA": {}, "ISLANDER": {}}},
            "neurio": {"readings": []},
        }

    def test_falls_back_to_remote_meter_when_nothing_else_available(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 1500.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=6.25, power=1500.0, voltage=123.5, location="site"),
        }

        result = backend._extract_site_section(self._status(), {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 6.25
        assert result["disclaimer"] == "site: voltage/current from Remote Meter"

    def test_meter_x_takes_precedence_over_remote_meter(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 1000.0
        status = self._status()
        status["esCan"]["bus"]["SYNC"] = {
            "METER_X_AcMeasurements": {
                "isMIA": False, "METER_X_CTA_I": 4.2, "METER_X_CTB_I": 0, "METER_X_CTC_I": 0,
            },
        }
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=99, power=99, voltage=99, location="site"),
        }

        result = backend._extract_site_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["disclaimer"] == "site: voltage/current from Meter X"
        backend.tedapi.get_remote_meter_readings.assert_not_called()

    def test_remote_meter_for_a_different_location_is_ignored(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 500.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=6.25, power=1500.0, voltage=123.5, location="solar"),
        }

        result = backend._extract_site_section(self._status(), {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 0
        assert result["disclaimer"] == "site: voltage/current from unknown"

    def test_falls_through_to_remote_meter_when_neurio_has_no_site_ct(self):
        """Regression: a Neurio device with every CT assigned to solar/load
        (none to "site") used to be mistaken for "handled" (used_meter was
        set unconditionally whenever any Neurio reading existed), permanently
        blocking the remote-meter fallback for the site section."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 750.0
        backend.tedapi.aggregate_neurio_data.return_value = (
            {},
            {"CT0": {"Index": 0, "InstCurrent": 5.0, "InstRealPower": 500.0,
                     "InstVoltage": 120.0, "Location": "solar"}},
        )
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=3.1, power=750.0, voltage=124.0, location="site"),
        }
        status = self._status()
        status["neurio"] = {"readings": [{"serial": "NEURIOSN1"}]}

        result = backend._extract_site_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["disclaimer"] == "site: voltage/current from Remote Meter"
        assert result["i_a_current"] == 3.1

    def test_reuses_shared_remote_hierarchy_without_refetching(self):
        """When the aggregates entry point already fetched the hierarchy, the
        extractor must use it instead of calling get_remote_meter_readings again."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 1500.0
        shared_hierarchy = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=6.25, power=1500.0, voltage=123.5, location="site"),
        }

        result = backend._extract_site_section(self._status(), {"vin": GATEWAY_DIN}, False,
                                                 remote_hierarchy=shared_hierarchy)
        assert result["i_a_current"] == 6.25
        backend.tedapi.get_remote_meter_readings.assert_not_called()

    def test_neurio_provides_site_current_when_available(self):
        """The successful (non-fallthrough) Neurio path: CTs actually
        assigned to "site" are used directly (all three phases), and the
        remote-meter tier is never reached."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 600.0
        backend.tedapi.aggregate_neurio_data.return_value = (
            {},
            {
                "CT0": {"Index": 0, "InstCurrent": 5.0, "InstRealPower": 600.0,
                        "InstVoltage": 120.0, "Location": "site"},
                "CT1": {"Index": 1, "InstCurrent": 6.0, "InstRealPower": 700.0,
                        "InstVoltage": 121.0, "Location": "site"},
                "CT2": {"Index": 2, "InstCurrent": 7.0, "InstRealPower": 800.0,
                        "InstVoltage": 122.0, "Location": "site"},
            },
        )
        status = self._status()
        status["neurio"] = {"readings": [{"serial": "NEURIOSN1"}]}

        result = backend._extract_site_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["disclaimer"] == "site: voltage/current from Neurio"
        assert result["i_a_current"] == 5.0
        assert result["i_b_current"] == 6.0
        assert result["i_c_current"] == 7.0
        backend.tedapi.get_remote_meter_readings.assert_not_called()
        backend.tedapi.get_remote_meter_readings.assert_not_called()

    def test_skipped_ct_slot_maps_to_correct_phase(self):
        """Regression: two remote CTs at Index 0 and Index 2 (Index 1 not
        configured) used to be reassigned to the first two iteration slots
        (i_a, i_b) instead of their real phases (i_a, i_c)."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 900.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=4.0, power=400.0, voltage=120.0, location="site"),
            _hierarchy_key(REMOTE_METER_DIN, 2): _remote_ct(2, current=5.0, power=500.0, voltage=121.0, location="site"),
        }

        result = backend._extract_site_section(self._status(), {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 4.0
        assert result["i_b_current"] == 0
        assert result["i_c_current"] == 5.0

    def test_three_phase_mapping_and_invalid_index_is_skipped(self):
        """All three phases (Index 0/1/2) map correctly, and a CT with no
        usable Index (e.g. missing/out of range) is skipped rather than
        raising or corrupting a phase."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 1200.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=4.0, power=400.0, voltage=120.0, location="site"),
            _hierarchy_key(REMOTE_METER_DIN, 1): _remote_ct(1, current=5.0, power=500.0, voltage=121.0, location="site"),
            _hierarchy_key(REMOTE_METER_DIN, 2): _remote_ct(2, current=6.0, power=600.0, voltage=122.0, location="site"),
            f"{REMOTE_METER_DIN}:3": _remote_ct(3, current=99, power=99, voltage=99, location="site"),
        }

        result = backend._extract_site_section(self._status(), {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 4.0
        assert result["i_b_current"] == 5.0
        assert result["i_c_current"] == 6.0


class TestExtractSolarSectionRemoteMeter:
    def _pvac_status(self, voltage=245.0):
        return {"esCan": {"bus": {
            "PVAC": [{"packageSerialNumber": "PVACSN1", "PVAC_Status": {"PVAC_Vout": voltage}}],
            "SYNC": {},
        }}}

    def test_pvac_voltage_with_remote_meter_current(self):
        """Regression: a remote-metered solar circuit has no Meter Y, so
        i_a/b/c used to stay 0 even with PVAC voltage and a working remote CT
        both available - voltage and current sources must be independent."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 3000.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=12.5, power=3000.0, voltage=121.0, location="solar"),
        }

        result = backend._extract_solar_section(self._pvac_status(), {"vin": GATEWAY_DIN}, False)
        assert result["instant_average_voltage"] == 245.0  # still from PVAC
        assert result["i_a_current"] == 12.5  # now from Remote Meter, was 0 before this fix
        assert result["disclaimer"] == "solar: voltage from PVAC, current from Remote Meter"

    def test_no_pvac_no_meter_y_full_remote_meter_fallback(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 800.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=6.6, power=800.0, voltage=122.0, location="solar"),
        }
        status = {"esCan": {"bus": {"PVAC": [], "SYNC": {}}}}

        result = backend._extract_solar_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["instant_average_voltage"] == 122.0
        assert result["i_a_current"] == 6.6
        assert result["disclaimer"] == "solar: voltage from Remote Meter, current from Remote Meter"

    def test_meter_y_current_takes_precedence_over_remote_meter(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 3000.0
        status = self._pvac_status()
        status["esCan"]["bus"]["SYNC"] = {
            "METER_Y_AcMeasurements": {"METER_Y_CTA_I": 10.0, "METER_Y_CTB_I": 0, "METER_Y_CTC_I": 0},
        }

        result = backend._extract_solar_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 10.0
        assert result["disclaimer"] == "solar: voltage from PVAC, current from Meter Y"
        backend.tedapi.get_remote_meter_readings.assert_not_called()

    def test_no_remote_meter_configured_keeps_zero_current(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 3000.0
        backend.tedapi.get_remote_meter_readings.return_value = {}

        result = backend._extract_solar_section(self._pvac_status(), {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 0
        # Byte-identical to the fixed string used before remote-meter support, so
        # the common PVAC-only install's /api/meters/aggregates output is unchanged
        assert result["disclaimer"] == "solar: voltage from PVAC, calculated current from power"

    def test_meter_y_voltage_used_when_pvac_reports_none(self):
        """PVAC reports no voltage at all (no entries), but Meter Y's own
        voltage signals are present - voltage_source must fall back to
        "Meter Y" independently of the current source."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 500.0
        status = {"esCan": {"bus": {
            "PVAC": [],
            "SYNC": {"METER_Y_AcMeasurements": {
                "METER_Y_CTA_I": 4.0, "METER_Y_CTB_I": 0, "METER_Y_CTC_I": 0,
                "METER_Y_VL1N": 120.0, "METER_Y_VL2N": 120.0, "METER_Y_VL3N": 0,
            }},
        }}}

        result = backend._extract_solar_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["disclaimer"] == "solar: voltage from Meter Y, current from Meter Y"
        backend.tedapi.get_remote_meter_readings.assert_not_called()

    def test_three_phase_mapping_and_invalid_index_is_skipped(self):
        """All three phases (Index 0/1/2) map correctly, and a CT with no
        usable Index (e.g. missing/out of range) is skipped rather than
        raising or corrupting a phase."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 1200.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=4.0, power=400.0, voltage=120.0, location="solar"),
            _hierarchy_key(REMOTE_METER_DIN, 1): _remote_ct(1, current=5.0, power=500.0, voltage=121.0, location="solar"),
            _hierarchy_key(REMOTE_METER_DIN, 2): _remote_ct(2, current=6.0, power=600.0, voltage=122.0, location="solar"),
            f"{REMOTE_METER_DIN}:3": _remote_ct(3, current=99, power=99, voltage=99, location="solar"),
        }
        status = {"esCan": {"bus": {"PVAC": [], "SYNC": {}}}}

        result = backend._extract_solar_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 4.0
        assert result["i_b_current"] == 5.0
        assert result["i_c_current"] == 6.0

    def test_skipped_ct_slot_maps_to_correct_phase(self):
        """Regression: two remote CTs at Index 0 and Index 2 (Index 1 not
        configured) used to be reassigned to the first two iteration slots
        (i_a, i_b) instead of their real phases (i_a, i_c)."""
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 900.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=4.0, power=400.0, voltage=120.0, location="solar"),
            _hierarchy_key(REMOTE_METER_DIN, 2): _remote_ct(2, current=5.0, power=500.0, voltage=121.0, location="solar"),
        }
        status = {"esCan": {"bus": {"PVAC": [], "SYNC": {}}}}

        result = backend._extract_solar_section(status, {"vin": GATEWAY_DIN}, False)
        assert result["i_a_current"] == 4.0
        assert result["i_b_current"] == 0
        assert result["i_c_current"] == 5.0

    def test_reuses_shared_remote_hierarchy_without_refetching(self):
        backend = _make_backend()
        backend.tedapi.current_power.return_value = 800.0
        shared_hierarchy = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=6.6, power=800.0, voltage=122.0, location="solar"),
        }
        status = {"esCan": {"bus": {"PVAC": [], "SYNC": {}}}}

        result = backend._extract_solar_section(status, {"vin": GATEWAY_DIN}, False,
                                                  remote_hierarchy=shared_hierarchy)
        assert result["i_a_current"] == 6.6
        backend.tedapi.get_remote_meter_readings.assert_not_called()


class TestGetApiMetersAggregatesSharedRemoteMeterFetch:
    """get_api_meters_aggregates() fetches the remote-meter hierarchy once and
    shares it with both the site and solar extractors, rather than each
    independently calling get_remote_meter_readings (which, with force=True,
    used to mean two identical Full-query fetches per aggregates call)."""

    def test_fetches_remote_meter_hierarchy_once_for_both_extractors(self):
        backend = _make_backend()
        backend.tedapi.get_config.return_value = {"vin": GATEWAY_DIN}
        backend.tedapi.get_status.return_value = {
            "system": {"time": "2025-01-01T00:00:00-08:00"},
            "esCan": {"bus": {"SYNC": {}, "MSA": {}, "ISLANDER": {}, "PVAC": [], "PINV": []}},
            "neurio": {"readings": []},
        }
        backend.tedapi.current_power.return_value = 100.0
        backend.tedapi.get_remote_meter_readings.return_value = {
            _hierarchy_key(REMOTE_METER_DIN, 0): _remote_ct(0, current=1.0, power=100.0, voltage=120.0, location="site"),
        }
        backend.tedapi.get_native_meters_aggregates.return_value = None

        backend.get_api_meters_aggregates(force=True)

        backend.tedapi.get_remote_meter_readings.assert_called_once_with(
            config={"vin": GATEWAY_DIN}, force=True)


class TestTrmWifiRecognition:
    """config.json meter type "trm_wifi" (the Wi-Fi Tesla Remote Meter) reports
    through teslaRemoteMeter exactly like "trm_mb"; it used to be ignored, so a
    trm_wifi site got no remote-meter data at all."""

    def test_remote_meter_types_constant(self):
        assert REMOTE_METER_TYPES == ("trm_mb", "trm_wifi")

    def test_derive_meter_config_picks_up_trm_wifi(self):
        ted = _make_tedapi()
        config = _remote_meter_config(location="solar", factor=2, meter_type="trm_wifi")
        result = ted.derive_meter_config(config, types=REMOTE_METER_TYPES)
        assert REMOTE_METER_DIN in result
        entry = result[REMOTE_METER_DIN]
        assert entry["type"] == "trm_wifi"
        assert entry["location"] == ["solar", "solar", "solar", "solar"]
        assert entry["cts"] == [True, False, False, False]
        assert entry["real_power_scale_factor"] == 2

    def test_derive_meter_config_default_still_neurio_only(self):
        ted = _make_tedapi()
        config = _remote_meter_config(meter_type="trm_wifi")
        assert ted.derive_meter_config(config) == {}

    def test_get_remote_meter_readings_fetches_for_trm_wifi_only_config(self):
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status(real_power=1517.0))
        config = _remote_meter_config(location="solar", factor=2, meter_type="trm_wifi")

        hierarchy = ted.get_remote_meter_readings(config=config)

        ted.get_device_controller.assert_called_once()
        entry = hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]
        assert entry["Location"] == "solar"
        assert entry["InstRealPower"] == 3034.0  # scaled by factor 2

    def test_get_remote_meter_readings_still_skips_without_remote_meter(self):
        ted = _make_tedapi()
        ted.get_device_controller = MagicMock(return_value=_remote_meter_status())
        config = {"vin": GATEWAY_DIN, "meters": [{
            "type": "neurio_w2_tcp", "location": "site",
            "connection": {"device_serial": "NEURIOSN1"},
        }]}
        assert ted.get_remote_meter_readings(config=config) == {}
        ted.get_device_controller.assert_not_called()

    def test_vitals_trm_block_for_trm_wifi_has_location_and_scaling(self):
        ted = _make_tedapi()
        ted.pw3 = False
        status = {
            **_remote_meter_status(real_power=1517.0),
            'control': {'alerts': {'active': []}},
            'components': {'msa': []},
            'esCan': {
                'bus': {
                    'PVAC': [], 'PVS': [], 'THC': [], 'POD': [], 'PINV': [],
                    'SYNC': {}, 'ISLANDER': {}, 'MSA': {},
                },
            },
        }
        ted.get_config = MagicMock(return_value=_remote_meter_config(
            location="solar", factor=2, meter_type="trm_wifi"))
        ted.get_device_controller = MagicMock(return_value=status)

        vitals = ted.vitals()
        block = vitals[f"TRM--{REMOTE_METER_DIN}"]
        assert block["TRM_CT0_Location"] == "solar"
        assert block["TRM_CT0_InstRealPower"] == 3034.0
        assert block["manufacturer"] == "TESLA"


class TestRemoteMeterHierarchyTimestamp:
    def test_hierarchy_entries_carry_reading_timestamp(self):
        ted = _make_tedapi()
        config = _remote_meter_config(cts=[True, False, True, False])
        status = _remote_meter_status()
        meter_config = ted.derive_meter_config(config, types=REMOTE_METER_TYPES)

        _, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)

        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["Timestamp"] == "2025-01-01T00:00:00-08:00"
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 2)]["Timestamp"] == "2025-01-01T00:00:00-08:00"

    def test_flat_block_does_not_gain_timestamp_keys(self):
        """The flat TRM--<din> block already carries the reading time once as
        lastCommunicationTime; no per-CT TRM_CT*_Timestamp keys."""
        ted = _make_tedapi()
        config = _remote_meter_config()
        status = _remote_meter_status()
        meter_config = ted.derive_meter_config(config, types=REMOTE_METER_TYPES)

        flat, _ = ted.aggregate_remote_meter_data(config, status, meter_config)

        block = flat[f"TRM--{REMOTE_METER_DIN}"]
        assert not any(k.endswith("_Timestamp") for k in block)
        assert block["lastCommunicationTime"] == "2025-01-01T00:00:00-08:00"

    def test_missing_reading_timestamp_is_none(self):
        ted = _make_tedapi()
        config = _remote_meter_config()
        status = _remote_meter_status()
        del status["teslaRemoteMeter"]["meters"][0]["reading"]["timestamp"]
        meter_config = ted.derive_meter_config(config, types=REMOTE_METER_TYPES)

        _, hierarchy = ted.aggregate_remote_meter_data(config, status, meter_config)
        assert hierarchy[_hierarchy_key(REMOTE_METER_DIN, 0)]["Timestamp"] is None


# Values below reproduce a SolarMeterComms dropout observed on 2x Powerwall 3
# (firmware 26.34.0, trm_wifi solar meter, real_power_scale_factor 2): the gateway
# reports SOLAR 0 and LOAD -1752.0 while the remote meter keeps its last good
# reading (CT0 1426.3 W, timestamp 4 s older than the gateway clock).
DROPOUT_SYSTEM_TIME = "2026-09-27T12:14:52-04:00"
DROPOUT_READING_TIME = "2026-09-27T12:14:48-04:00"


class TestHoldSolarThroughSolarMeterComms:
    """get_api_meters_aggregates() end to end against a real TEDAPI (transport mocked)."""

    def _backend(self, alerts=("SolarMeterComms",), solar=0.0, load=-1752.0, site=-600.0,
                 ct0_power=1426.3, factor=2, reading_time=DROPOUT_READING_TIME,
                 system_time=DROPOUT_SYSTEM_TIME, location="solar"):
        ted = _make_tedapi()
        ted.pw3 = False
        meter_aggregates = [
            {"location": "SITE", "realPowerW": site},
            {"location": "BATTERY", "realPowerW": 0.0},
            {"location": "LOAD", "realPowerW": load},
            {"location": "SOLAR", "realPowerW": solar},
        ]
        status = {
            "control": {"meterAggregates": meter_aggregates,
                        "alerts": {"active": list(alerts)}},
            "esCan": {"bus": {
                "SYNC": {}, "MSA": {}, "PINV": [],
                "ISLANDER": {"ISLAND_AcMeasurements": {
                    "ISLAND_VL1N_Load": 120.0, "ISLAND_VL2N_Load": 120.0, "ISLAND_VL3N_Load": 0,
                }},
                "PVAC": [{"packageSerialNumber": "PVACSN1", "PVAC_Status": {"PVAC_Vout": 240.0}}],
            }},
            "neurio": {"readings": []},
        }
        if system_time is not None:
            status["system"] = {"time": system_time}
        controller = _remote_meter_status(real_power=ct0_power, current=11.9, voltage=121.0)
        reading = controller["teslaRemoteMeter"]["meters"][0]["reading"]
        if reading_time is None:
            del reading["timestamp"]
        else:
            reading["timestamp"] = reading_time
        ted.get_config = MagicMock(return_value=_remote_meter_config(
            location=location, factor=factor, meter_type="trm_wifi"))
        ted.get_status = MagicMock(return_value=status)
        ted.get_device_controller = MagicMock(return_value=controller)
        ted.get_native_meters_aggregates = MagicMock(return_value=None)
        backend = _make_backend()
        backend.tedapi = ted
        return backend

    def _assert_untouched(self, data, solar=0.0, load=-1752.0):
        assert data["solar"]["instant_power"] == solar
        assert data["load"]["instant_power"] == load
        assert "SolarMeterComms" not in data["solar"]["disclaimer"]

    def test_hold_applied(self):
        data = self._backend().get_api_meters_aggregates()

        assert data["solar"]["instant_power"] == pytest.approx(2852.6)
        assert data["load"]["instant_power"] == pytest.approx(1100.6)
        assert data["site"]["instant_power"] == -600.0  # untouched
        assert "solar held from remote meter reading during SolarMeterComms (age 4s)" \
            in data["solar"]["disclaimer"]
        # Currents recomputed from the held power
        assert data["solar"]["instant_average_current"] == pytest.approx(2852.6 / 240.0)
        assert data["solar"]["instant_total_current"] == pytest.approx(2852.6 / 240.0)
        assert data["load"]["instant_average_current"] == pytest.approx(1100.6 / 240.0)
        assert data["load"]["instant_total_current"] == pytest.approx(1100.6 / 240.0)

    def test_hold_applied_at_exact_max_age(self):
        backend = self._backend(reading_time="2026-09-27T12:13:52-04:00")  # 60 s
        data = backend.get_api_meters_aggregates()
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)

    def test_hold_applied_with_utc_z_timestamps(self):
        backend = self._backend(reading_time="2026-09-27T16:14:48Z",
                                system_time="2026-09-27T12:14:52-04:00")
        data = backend.get_api_meters_aggregates()
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)

    def test_not_applied_without_alert(self):
        data = self._backend(alerts=()).get_api_meters_aggregates()
        self._assert_untouched(data)

    def test_not_applied_when_solar_nonzero(self):
        data = self._backend(solar=2852.6, load=1194.1).get_api_meters_aggregates()
        self._assert_untouched(data, solar=2852.6, load=1194.1)

    def test_hold_applied_when_solar_reads_one_watt(self):
        # Observed 2026-09-30 13:38:05: SOLAR 1 W with the alert, LOAD short by the rest.
        data = self._backend(solar=1.0, load=-1751.0).get_api_meters_aggregates()
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)
        assert data["load"]["instant_power"] == pytest.approx(1100.6)
        assert "during SolarMeterComms (age 4s)" in data["solar"]["disclaimer"]

    def test_not_applied_when_solar_just_above_zero_threshold(self):
        data = self._backend(solar=SOLAR_METER_HOLD_ZERO_W + 1, load=-1741.0).get_api_meters_aggregates()
        self._assert_untouched(data, solar=SOLAR_METER_HOLD_ZERO_W + 1, load=-1741.0)

    def test_not_applied_when_solar_negative(self):
        data = self._backend(solar=-1.0, load=-1753.0).get_api_meters_aggregates()
        self._assert_untouched(data, solar=-1.0, load=-1753.0)

    def test_not_applied_when_reading_too_old(self):
        data = self._backend(reading_time="2026-09-27T12:13:22-04:00").get_api_meters_aggregates()  # 90 s
        self._assert_untouched(data)

    def test_hold_applied_when_reading_newer_than_system_time(self):
        """The Full query is fetched after the status; a first packet after the dropout can be
        stamped a second newer than the status snapshot (missed hold seen live 2026-09-28)."""
        data = self._backend(reading_time="2026-09-27T12:14:53-04:00").get_api_meters_aggregates()
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)
        assert data["load"]["instant_power"] == pytest.approx(1100.6)
        assert "during SolarMeterComms (age 0s)" in data["solar"]["disclaimer"]

    def test_hold_applied_when_reading_newer_by_exact_max_age(self):
        data = self._backend(reading_time="2026-09-27T12:15:52-04:00").get_api_meters_aggregates()  # -60 s
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)

    def test_not_applied_when_reading_too_far_in_future(self):
        data = self._backend(reading_time="2026-09-27T12:16:52-04:00").get_api_meters_aggregates()  # -120 s
        self._assert_untouched(data)

    def test_not_applied_without_reading_timestamp(self):
        data = self._backend(reading_time=None).get_api_meters_aggregates()
        self._assert_untouched(data)

    def test_not_applied_with_unparseable_reading_timestamp(self):
        data = self._backend(reading_time="not a time").get_api_meters_aggregates()
        self._assert_untouched(data)

    def test_not_applied_without_system_time(self):
        data = self._backend(system_time=None).get_api_meters_aggregates()
        self._assert_untouched(data)

    def test_not_applied_without_solar_ct(self):
        data = self._backend(location="load").get_api_meters_aggregates()
        self._assert_untouched(data)

    def test_not_applied_when_retained_zero(self):
        data = self._backend(ct0_power=0.0).get_api_meters_aggregates()
        self._assert_untouched(data)

    def _drop_aggregate(self, backend, location):
        """Remove a location from meterAggregates (current_power() -> None), leaving
        the voltage sources in place - the realistic case the extractors must survive."""
        status = backend.tedapi.get_status.return_value
        aggregates = status["control"]["meterAggregates"]
        aggregates[:] = [a for a in aggregates if a["location"] != location]

    def test_solar_none_is_held(self):
        """Gateway solar None (not 0) is held too, end to end with voltage sources
        reporting (on a remote-meter site the meter itself supplies one)."""
        backend = self._backend()
        self._drop_aggregate(backend, "SOLAR")
        data = backend.get_api_meters_aggregates()
        v_solar = data["solar"]["instant_average_voltage"]
        assert v_solar
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)
        assert data["solar"]["instant_total_current"] == pytest.approx(2852.6 / v_solar)
        assert data["load"]["instant_power"] == pytest.approx(1100.6)

    def _add_site_and_battery_voltage(self, backend):
        """Give site (Meter X + islander main) and battery (PINV) a voltage source,
        so all four sections divide power by a real voltage."""
        bus = backend.tedapi.get_status.return_value["esCan"]["bus"]
        bus["SYNC"]["METER_X_AcMeasurements"] = {
            "METER_X_CTA_I": 2.5, "METER_X_CTB_I": 2.5, "METER_X_CTC_I": 0,
            "METER_X_CTA_InstRealPower": -300.0, "METER_X_CTB_InstRealPower": -300.0}
        bus["ISLANDER"]["ISLAND_AcMeasurements"].update(
            {"ISLAND_VL1N_Main": 120.0, "ISLAND_VL2N_Main": 120.0, "ISLAND_VL3N_Main": 0})
        bus["PINV"] = [{"PINV_Status": {"PINV_Vout": 240.0}}]

    @pytest.mark.parametrize("location", ["SITE", "LOAD", "SOLAR", "BATTERY"])
    def test_missing_power_with_voltage_does_not_raise(self, location):
        """A location missing from meterAggregates while its voltage source still
        reports yields power and current None - it used to raise TypeError."""
        backend = self._backend(alerts=())
        self._add_site_and_battery_voltage(backend)
        self._drop_aggregate(backend, location)
        data = backend.get_api_meters_aggregates()
        section = {"SITE": "site", "LOAD": "load", "SOLAR": "solar", "BATTERY": "battery"}[location]
        assert data[section]["instant_power"] is None
        assert data[section]["instant_average_current"] is None

    def test_control_null_does_not_raise(self):
        """control: null (the gateway's site manager isn't running) with voltage
        sources still reporting: aggregates degrade to None instead of raising."""
        backend = self._backend(alerts=())
        self._add_site_and_battery_voltage(backend)
        backend.tedapi.get_status.return_value["control"] = None
        data = backend.get_api_meters_aggregates()
        for section in ("site", "load", "solar", "battery"):
            assert data[section]["instant_power"] is None

    def test_load_missing_holds_solar_and_leaves_load_alone(self):
        backend = self._backend()
        self._drop_aggregate(backend, "LOAD")
        data = backend.get_api_meters_aggregates()
        assert data["solar"]["instant_power"] == pytest.approx(2852.6)
        assert data["load"]["instant_power"] is None

    def test_hold_helper_with_load_none_or_absent(self):
        backend = _make_backend()
        status = {"control": {"alerts": {"active": ["SolarMeterComms"]}},
                  "system": {"time": DROPOUT_SYSTEM_TIME}}
        hierarchy = {_hierarchy_key(REMOTE_METER_DIN, 0): {
            **_remote_ct(0, power=2852.6, location="solar"), "Timestamp": DROPOUT_READING_TIME}}
        for load in ({"instant_power": None, "instant_average_voltage": 240.0}, {}):
            data = {"solar": {"instant_power": 0, "instant_average_voltage": None,
                              "instant_average_current": None, "disclaimer": "solar"},
                    "load": dict(load)}
            backend._hold_solar_through_meter_comms(data, status, hierarchy)
            assert data["solar"]["instant_power"] == pytest.approx(2852.6)
            assert data["solar"]["instant_average_current"] is None  # no voltage to divide by
            assert data["solar"]["disclaimer"] == (
                "solar; solar held from remote meter reading during SolarMeterComms (age 4s)")
            assert data["load"] == load

    def test_error_in_hold_leaves_aggregates_intact(self):
        backend = self._backend()
        with patch.object(PyPowerwallTEDAPI, "_hold_solar_through_meter_comms",
                          side_effect=RuntimeError("boom")):
            data = backend.get_api_meters_aggregates()
        self._assert_untouched(data)

    def test_no_remote_meter_site_untouched(self):
        """No remote meter in config.json: no Full-query fetch, nothing held,
        even with the alert and solar 0."""
        backend = self._backend()
        backend.tedapi.get_config.return_value = {"vin": GATEWAY_DIN}
        data = backend.get_api_meters_aggregates()
        self._assert_untouched(data)
        backend.tedapi.get_device_controller.assert_not_called()
