"""Gateway uptime for TEDAPI /api/status (#418).

start_time / up_time_seconds come from the Backup Gateway sync board's SYNC_Uptime
signal (milliseconds), requested through the unsigned msaSignals variable of the
V2024_06 device-controller query, and are formatted the way a real gateway does,
because strict clients (evcc's go-powerwall) parse exactly those formats. Sites
without a sync board get None, never a placeholder. Serials and values below are
fabricated fixtures shaped like the 2026-10-11 hardware capture.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pypowerwall.tedapi import TEDAPI, _sync_uptime_ms
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.queries import QueryRole
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI, go_duration

SYNC_SERIAL = "SYNC_SERIAL_1"
GW_TIME = "2026-10-11T11:58:01-07:00"
UPTIME_MS = 1434584192          # 16 days 14:29:44.192


def _controller(uptime=UPTIME_MS, sync_serial=SYNC_SERIAL, system_time=GW_TIME, msa=None):
    """A DeviceController payload with an esCan SYNC device and its msa components."""
    if msa is None:
        msa = [
            {"partNumber": "1707000-11-M", "serialNumber": "LEADER_SERIAL", "signals": []},
            # the same sync serial also appears on a signal-less component
            {"partNumber": "1493315-01-F", "serialNumber": sync_serial, "signals": []},
            {"partNumber": "1493315-01-F", "serialNumber": sync_serial, "signals": [
                {"name": "SYNC_ExternallyPowered", "value": None, "boolValue": False, "textValue": None},
                {"name": "SYNC_Uptime", "value": uptime, "boolValue": None, "textValue": None},
            ]},
        ]
    return {
        "esCan": {"bus": {"SYNC": {"packagePartNumber": "1493315-01-F",
                                   "packageSerialNumber": sync_serial}}},
        "components": {"msa": msa},
        "system": {"time": system_time},
    }


# --- the request --------------------------------------------------------------------

class TestRequest:
    def test_sync_uptime_appended_to_msa_signals(self):
        captured = q.V2024_06_QUERIES["device_controller_full"]
        request = q.get_query(QueryRole.DEVICE_CONTROLLER_FULL)
        captured_names = json.loads(captured.b_value)["msaSignals"]
        request_names = json.loads(request.b_value)["msaSignals"]
        # captured names keep their positions, the extra is appended after them (first
        # of the extras; the PW2 names follow, see test_pw2_msa_signals.py)
        assert request_names[:len(captured_names)] == captured_names
        assert request_names[len(captured_names)] == "SYNC_Uptime"

    def test_signed_text_component_types_and_signature_unchanged(self):
        captured = q.V2024_06_QUERIES["device_controller_full"]
        request = q.get_query(QueryRole.DEVICE_CONTROLLER_FULL)
        assert (request.text, request.code) == (captured.text, captured.code)
        assert json.loads(request.b_value)["msaComp"] == json.loads(captured.b_value)["msaComp"]

    def test_v2026_06_cannot_carry_it(self):
        # Tesla's signed DeviceControllerQuery lists its signals inline
        from pypowerwall.tedapi.api_version import TEDAPIApiVersion
        assert "SYNC_Uptime" not in q.get_query(QueryRole.DEVICE_CONTROLLER_FULL,
                                                TEDAPIApiVersion.V2026_06).text


# --- reading SYNC_Uptime ------------------------------------------------------------

class TestSyncUptimeMs:
    def test_reads_the_sync_serial_component(self):
        assert _sync_uptime_ms(_controller()) == UPTIME_MS

    def test_ignores_serial_less_and_other_components(self):
        # A live-looking value on a serial-less slot or another device must not be
        # taken (#406: serial-less slots can carry live signals)
        msa = [
            {"partNumber": "", "serialNumber": "", "signals": [{"name": "SYNC_Uptime", "value": 5}]},
            {"partNumber": "1707000-11-M", "serialNumber": "OTHER", "signals": [{"name": "SYNC_Uptime", "value": 7}]},
        ]
        assert _sync_uptime_ms(_controller(msa=msa)) is None

    @pytest.mark.parametrize("payload", [
        None, {}, {"esCan": None}, {"esCan": {"bus": {"SYNC": None}}},
        _controller(sync_serial=None), _controller(sync_serial=""),
        {"esCan": {"bus": {"SYNC": {"packageSerialNumber": SYNC_SERIAL}}}, "components": None},
        {"esCan": {"bus": {"SYNC": {"packageSerialNumber": SYNC_SERIAL}}}, "components": {"msa": None}},
    ])
    def test_no_sync_device_or_components(self, payload):
        assert _sync_uptime_ms(payload) is None

    @pytest.mark.parametrize("value", [None, True, False, "1434584192", -1, float("nan"), float("inf")])
    def test_unusable_values(self, value):
        assert _sync_uptime_ms(_controller(uptime=value)) is None

    def test_malformed_entries_tolerated(self):
        msa = [None, "x", {"serialNumber": SYNC_SERIAL, "signals": None},
               {"serialNumber": SYNC_SERIAL, "signals": [None, "y", {"name": "SYNC_Uptime", "value": 42.0}]}]
        assert _sync_uptime_ms(_controller(msa=msa)) == 42.0


class TestGetGatewayUptime:
    def _api(self, controller):
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        return api, patch.object(TEDAPI, 'get_device_controller', return_value=controller)

    def test_start_time_is_gateway_clock_minus_uptime(self):
        api, p = self._api(_controller())
        with p:
            result = api.get_gateway_uptime()
        now = datetime.fromisoformat(GW_TIME)
        assert result["uptime_ms"] == UPTIME_MS
        assert result["gateway_time"] == now
        assert result["start_time"] == now - timedelta(milliseconds=UPTIME_MS)
        # the 2026-10-11 hardware reading put the start at the 2026-09-24 21:28 PDT reboot
        assert result["start_time"].strftime("%Y-%m-%d %H:%M") == "2026-09-24 21:28"

    def test_utc_z_suffix(self):
        api, p = self._api(_controller(system_time="2026-10-11T18:58:01Z"))
        with p:
            result = api.get_gateway_uptime()
        assert result["start_time"].utcoffset() == timedelta(0)

    @pytest.mark.parametrize("system_time", [None, "", "not a time", "2026-10-11T11:58:01"])
    def test_no_usable_clock(self, system_time):
        api, p = self._api(_controller(system_time=system_time))
        with p:
            assert api.get_gateway_uptime() is None

    @pytest.mark.parametrize("controller", [None, {}, _controller(uptime=None), _controller(sync_serial=None)])
    def test_no_uptime(self, controller):
        api, p = self._api(controller)
        with p:
            assert api.get_gateway_uptime() is None

    def test_start_time_steady_across_reads_of_the_same_boot(self):
        # Measured 2026-10-11: SYNC_Uptime steps every ~2.2 s and system.time has 1 s
        # resolution, so the raw start wobbled between :15.0 and :16.4 (and :17).
        # These are consecutive (system.time, SYNC_Uptime) pairs from that capture.
        reads = [("13:07:20", 1438744448), ("13:07:23", 1438746624), ("13:07:25", 1438748800),
                 ("13:07:26", 1438750976), ("13:07:29", 1438753280), ("13:07:34", 1438757632)]
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        starts = set()
        for clock, uptime in reads:
            with patch.object(TEDAPI, 'get_device_controller',
                              return_value=_controller(uptime=uptime, system_time=f"2026-10-11T{clock}-07:00")):
                starts.add(api.get_gateway_uptime()["start_time"])
        assert len(starts) == 1
        assert next(iter(starts)).strftime("%Y-%m-%d %H:%M:%S") == "2026-09-24 21:28:15"

    def test_reboot_is_reported_at_once(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        with patch.object(TEDAPI, 'get_device_controller', return_value=_controller()):
            before = api.get_gateway_uptime()["start_time"]
        # an hour later the counter restarted 90 s ago
        with patch.object(TEDAPI, 'get_device_controller',
                          return_value=_controller(uptime=90_000, system_time="2026-10-11T12:58:01-07:00")):
            after = api.get_gateway_uptime()
        assert after["start_time"] == datetime.fromisoformat("2026-10-11T12:56:31-07:00")
        assert after["start_time"] != before

    @pytest.mark.parametrize("uptime", [1e300, 9e16])
    def test_out_of_range_uptime_is_none(self, uptime):
        # timedelta/datetime arithmetic would raise OverflowError out of a read method
        api, p = self._api(_controller(uptime=uptime))
        with p:
            assert api.get_gateway_uptime() is None

    def test_older_snapshot_never_rolls_back_a_newer_one(self):
        # A slow request holding a pre-reboot snapshot must not replace the
        # post-reboot result another request already reported
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        after_reboot = _controller(uptime=90_000, system_time="2026-10-11T12:58:01-07:00")
        with patch.object(TEDAPI, 'get_device_controller', return_value=after_reboot):
            newest = api.get_gateway_uptime()
        with patch.object(TEDAPI, 'get_device_controller', return_value=_controller()):  # 11:58, pre-reboot
            stale = api.get_gateway_uptime()
        assert stale == newest
        with patch.object(TEDAPI, 'get_device_controller', return_value=after_reboot):
            assert api.get_gateway_uptime()["start_time"] == newest["start_time"]

    def _start_after(self, api, uptime, clock="2026-10-11T11:58:01-07:00"):
        with patch.object(TEDAPI, 'get_device_controller',
                          return_value=_controller(uptime=uptime, system_time=clock)):
            return api.get_gateway_uptime()["start_time"]

    def test_slow_drift_does_not_move_start_time(self):
        # The counter drifts against the gateway clock; a fixed band would step
        # start_time (a false reboot) every few hours in a long-running proxy
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        first = self._start_after(api, UPTIME_MS)
        # 6 hours later the raw start has drifted 30 s
        later = self._start_after(api, UPTIME_MS + 6 * 3600_000 - 30_000, "2026-10-11T17:58:01-07:00")
        assert later == first

    def test_publish_jitter_is_not_a_reboot(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        first = self._start_after(api, UPTIME_MS)
        assert self._start_after(api, UPTIME_MS - 2_200, "2026-10-11T11:58:02-07:00") == first

    def test_drift_beyond_tolerance_relatches(self):
        from pypowerwall.tedapi import GATEWAY_START_TIME_TOLERANCE_S
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        first = self._start_after(api, UPTIME_MS)
        # counter moving forward (not a reset) but implying a start beyond the tolerance
        shifted = UPTIME_MS + int((GATEWAY_START_TIME_TOLERANCE_S + 1) * 1000)
        with patch.object(TEDAPI, 'get_device_controller', return_value=_controller(uptime=shifted)):
            second = api.get_gateway_uptime()["start_time"]
        assert (first - second).total_seconds() == pytest.approx(GATEWAY_START_TIME_TOLERANCE_S + 1)


# --- formatting ----------------------------------------------------------------------

class TestGoDuration:
    @pytest.mark.parametrize("ms, expected", [
        (UPTIME_MS, "398h29m44.192s"),
        (459256275, "127h34m16.275s"),     # the gateway sample in pwsimulator/stub.py, to the ms
        (3_600_000, "1h0m0s"),             # Go keeps zero units after the largest
        (3_600_500, "1h0m0.5s"),
        (61_000, "1m1s"),
        (1_500, "1.5s"),
        (999, "999ms"),
        (0, "0s"),
        (1434584192.4, "398h29m44.192s"),  # float input rounds to the ms
    ])
    def test_matches_go_duration_string(self, ms, expected):
        assert go_duration(ms) == expected


# --- /api/status ---------------------------------------------------------------------

def _backend(uptime_result, config=None, firmware_details=None):
    with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
        backend = PyPowerwallTEDAPI(gw_pwd='password')
    config = config if config is not None else {
        "vin": "1707000-11-M--LEADER_SERIAL",
        "site_info": {"battery_commission_date": "2025-12-15T15:48:57-08:00"},
    }
    backend.tedapi.get_config.return_value = config
    backend.tedapi.get_gateway_uptime.return_value = uptime_result
    backend.tedapi.get_firmware_version.side_effect = lambda *a, **k: (
        (firmware_details if firmware_details is not None else
         {"system": {"version": {"text": "26.26.11 c4db63ce",
                                 "githash": "c4db63cead7447561c1c60c34529d0f90ad2884f"}}})
        if k.get("details") else "26.26.11 c4db63ce")
    return backend


def _uptime_result():
    now = datetime.fromisoformat(GW_TIME)
    return {"uptime_ms": UPTIME_MS, "gateway_time": now,
            "start_time": now - timedelta(milliseconds=UPTIME_MS)}


class TestApiStatus:
    def test_gateway_formats(self):
        status = _backend(_uptime_result()).get_api_status()
        assert status["start_time"] == "2026-09-24 21:28:16 -0700"
        assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4}", status["start_time"])
        assert status["up_time_seconds"] == "398h29m44.192s"
        # start_time + up_time == gateway clock, as on a real gateway
        start = datetime.strptime(status["start_time"], "%Y-%m-%d %H:%M:%S %z")
        assert abs((start + timedelta(milliseconds=UPTIME_MS)) - datetime.fromisoformat(GW_TIME)) < timedelta(seconds=1)

    def test_commission_date_passed_through_under_its_own_key(self):
        status = _backend(_uptime_result()).get_api_status()
        assert status["battery_commission_date"] == "2025-12-15T15:48:57-08:00"
        status = _backend(None).get_api_status()
        assert status["battery_commission_date"] == "2025-12-15T15:48:57-08:00"

    def test_no_sync_board_gives_none_not_a_placeholder(self):
        status = _backend(None).get_api_status()
        assert status["start_time"] is None
        assert status["up_time_seconds"] is None

    def test_git_hash_from_firmware(self):
        status = _backend(_uptime_result()).get_api_status()
        assert status["git_hash"] == "c4db63cead7447561c1c60c34529d0f90ad2884f"
        assert status["version"] == "26.26.11 c4db63ce"

    @pytest.mark.parametrize("firmware", [{}, {"system": {"version": {"githash": ""}}}, {"system": None}])
    def test_git_hash_missing_is_none(self, firmware):
        assert _backend(_uptime_result(), firmware_details=firmware).get_api_status()["git_hash"] is None

    def test_one_forced_firmware_lookup_supplies_version_and_hash(self):
        backend = _backend(_uptime_result())
        backend.get_api_status(force=True)
        calls = backend.tedapi.get_firmware_version.call_args_list
        assert len(calls) == 1 and calls[0].kwargs == {"force": True, "details": True}

    def test_git_hash_survives_a_failed_firmware_lookup(self):
        # The gateway UI (proxy/web/viz-static/app.js) reloads the page when git_hash
        # changes, so a transient lookup failure must not flip it to None
        backend = _backend(_uptime_result())
        assert backend.get_api_status()["git_hash"] == "c4db63cead7447561c1c60c34529d0f90ad2884f"
        backend.tedapi.get_firmware_version.side_effect = lambda *a, **k: None
        assert backend.get_api_status()["git_hash"] == "c4db63cead7447561c1c60c34529d0f90ad2884f"

    def test_missing_commission_date(self):
        status = _backend(None, config={"vin": "X"}).get_api_status()
        assert status["battery_commission_date"] is None

    def test_existing_keys_and_failure_shape_unchanged(self):
        status = _backend(_uptime_result()).get_api_status()
        for key in ("din", "start_time", "up_time_seconds", "is_new", "version", "git_hash",
                    "commission_count", "device_type", "teg_type", "sync_type",
                    "cellular_disabled", "can_reboot"):
            assert key in status
        backend = _backend(_uptime_result())
        backend.tedapi.get_config.return_value = None
        assert backend.get_api_status() is None


# --- vitals --------------------------------------------------------------------------

class TestVitalsTesync:
    def _vitals(self, controller):
        with patch.object(TEDAPI, 'connect', return_value=True):
            api = TEDAPI(gw_pwd='password')
        with patch.object(TEDAPI, 'get_config', return_value={"vin": "1707000-11-M--LEADER_SERIAL"}), \
                patch.object(TEDAPI, 'get_device_controller', return_value=controller):
            return api.vitals()

    def test_sync_uptime_on_tesync_block(self):
        vitals = self._vitals(_controller())
        assert vitals[f"TESYNC--1493315-01-F--{SYNC_SERIAL}"]["SYNC_Uptime"] == UPTIME_MS

    def test_none_without_sync_value(self):
        vitals = self._vitals(_controller(uptime=None))
        assert vitals[f"TESYNC--1493315-01-F--{SYNC_SERIAL}"]["SYNC_Uptime"] is None


# --- cloud / FleetAPI ----------------------------------------------------------------

class TestCloudAndFleetApiStatus:
    """The Tesla site API has no gateway start time, uptime, git hash or sync type
    (checked live 2026-10-11), so those are None/"unknown" - no placeholders - and
    the installation date is passed through under its own name."""
    SITE = {"id": "1707000-11-M--LEADER_SERIAL", "installation_date": "2025-12-15T15:48:57-08:00",
            "version": "26.26.11 c4db63ce", "components": {"gateway": "teg"}}

    def _check(self, status):
        assert status["start_time"] is None
        assert status["up_time_seconds"] is None
        assert status["git_hash"] is None
        assert status["sync_type"] == "unknown"
        assert status["installation_date"] == "2025-12-15T15:48:57-08:00"
        assert status["version"] == "26.26.11 c4db63ce"
        assert status["device_type"] == "teg"

    def test_cloud(self, tmp_path):
        from pypowerwall.cloud.pypowerwall_cloud import PyPowerwallCloud
        cloud = PyPowerwallCloud(email='test@example.com', authpath=str(tmp_path))
        with patch.object(PyPowerwallCloud, 'get_site_config', return_value={"response": self.SITE}):
            self._check(cloud.get_api_status())
        with patch.object(PyPowerwallCloud, 'get_site_config', return_value=None):
            assert cloud.get_api_status() is None

    def test_fleetapi(self, tmp_path):
        from pypowerwall.fleetapi.pypowerwall_fleetapi import PyPowerwallFleetAPI
        fleet = PyPowerwallFleetAPI(email='test@example.com', authpath=str(tmp_path))
        with patch.object(fleet.fleet, 'get_site_info', return_value=self.SITE):
            self._check(fleet.get_api_status())
        with patch.object(fleet.fleet, 'get_site_info', return_value=None):
            assert fleet.get_api_status() is None
