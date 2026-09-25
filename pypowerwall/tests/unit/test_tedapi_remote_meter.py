"""Unit tests for Tesla Remote Meter (teslaRemoteMeter) plumbing.

Wireless CT "remote meters" (config.json meter type "trm_mb") report through the
Device Controller Full query's teslaRemoteMeter field returned by
get_device_controller() - a field that was already being fetched but never
read by anything. These tests cover config-driven CT selection/scaling,
the site/solar aggregate fallbacks, and vitals() exposure.

All DIN/serial values here are fabricated test fixtures, not data captured
from a real gateway.
"""
from unittest.mock import MagicMock, patch

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI

GATEWAY_DIN = "1707000-21-M--TESTGW00000001"
REMOTE_METER_DIN = "1234567-00-E--TESTMETER0001"
REMOTE_METER_DIN_2 = "1234567-00-E--TESTMETER0002"


def _remote_meter_config(location="solar", cts=None, factor=1, din=REMOTE_METER_DIN):
    return {
        "vin": GATEWAY_DIN,
        "meters": [
            {
                "location": location,
                "type": "trm_mb",
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
