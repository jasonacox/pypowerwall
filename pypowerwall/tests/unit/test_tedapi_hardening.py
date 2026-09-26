"""Unit tests for TEDAPI thread-safety and failure-shape hardening.

Covers:
  1. connect() is single-flight: getters under different per-method locks that
     all find no DIN start one connect, not N (which cleared the DIN and closed
     the session other threads were using, or ran N parallel v1r logins);
  2. _cache_get tolerates a concurrent pop (KeyError) and a wall-clock step back;
  3. @uses_api_lock getters accept positional arguments after self;
  4. get_pw3_vitals() never raises, skips only the Powerwall whose query failed,
     and caches its result;
  5. a WiFi success clears a cooldown set while it was in flight.

Everything is mocked at the transport boundary — nothing here touches a gateway.
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from pypowerwall.tedapi import TEDAPI, tedapi_pb2, _CACHE_MISS

DIN = "1707000-11-J--TG0123456789AB"
FOLLOWER = "1707000-11-J--TG0FOLLOWER01"
WAIT = 5


def make_tedapi():
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value=DIN):
        api = TEDAPI("testpassword")
    api.din = DIN
    api.session = MagicMock()
    api.pwcache = {}
    api.pwcachetime = {}
    api.pwcooldown = 0
    return api


class TestConnectSingleFlight:

    def test_concurrent_connects_run_once(self):
        api = make_tedapi()
        api.din = None
        release = threading.Event()
        started = threading.Event()
        calls = []

        def slow_connect():
            calls.append(1)
            started.set()
            release.wait(WAIT)
            api.din = DIN
            return DIN

        results = []
        with patch.object(api, "_connect", side_effect=slow_connect):
            leader = threading.Thread(target=lambda: results.append(api.connect()))
            leader.start()
            assert started.wait(WAIT)
            # While the leader connects, others return at once with the current DIN
            others = [api.connect() for _ in range(5)]
            release.set()
            leader.join(WAIT)
        assert len(calls) == 1
        assert others == [None] * 5    # connect() contract: DIN or None
        assert results == [DIN]
        assert api._connecting is False

    def test_claim_released_after_failure(self):
        api = make_tedapi()
        api.din = None
        with patch.object(api, "_connect", side_effect=[RuntimeError("boom"), DIN]):
            with pytest.raises(RuntimeError):
                api.connect()
            assert api._connecting is False
            assert api.connect() == DIN

    def test_connected_short_circuit_unchanged(self):
        api = make_tedapi()
        with patch.object(api, "_connect") as body:
            assert api.connect() == DIN
        body.assert_not_called()


class TestCacheGet:

    def test_concurrent_pop_is_a_miss_not_keyerror(self):
        api = make_tedapi()
        api.pwcachetime["config"] = time.time()
        # A writer popped the value between the membership check and the read
        assert api._cache_get("config", 5) is _CACHE_MISS

    def test_clock_step_back_is_expired(self):
        api = make_tedapi()
        api._cache_put("config", {"a": 1})
        api.pwcachetime["config"] = time.time() + 3600   # clock since stepped back
        assert api._cache_get("config", 5) is _CACHE_MISS

    def test_fresh_entry_served(self):
        api = make_tedapi()
        api._cache_put("config", {"a": 1})
        assert api._cache_get("config", 5) == {"a": 1}
        assert api._cache_get("config", 5, force=True) is _CACHE_MISS


class TestUsesApiLockPositional:

    def test_positional_args_map_past_self_function(self):
        api = make_tedapi()
        api.pwcache[FOLLOWER] = {"block": 1}
        api.pwcachetime[FOLLOWER] = time.time()
        # Documented as get_battery_block(din); raised TypeError before
        assert api.get_battery_block(FOLLOWER) == {"block": 1}
        assert api.get_battery_block(din=FOLLOWER) == {"block": 1}

    def test_keyword_calls_unchanged(self):
        api = make_tedapi()
        api.pwcache["config"] = {"vin": "GW"}
        api.pwcachetime["config"] = time.time()
        assert api.get_config() == {"vin": "GW"}
        assert api.get_config(force=False) == {"vin": "GW"}


def _components(pw_din):
    return ('{"components": {"pch": [{"signals": [{"name": "PCH_AcVoltageAB", "value": 240}]}],'
            ' "bms": [{"signals": [{"name": "BMS_nominalEnergyRemaining", "value": 5},'
            ' {"name": "BMS_nominalFullPackEnergy", "value": 13}]}],'
            f' "hvp": [{{"serialNumber": "{pw_din}"}}]}}}}')


def _message(text):
    msg = tedapi_pb2.Message()
    msg.message.payload.recv.text = text
    return msg.SerializeToString()


class TestPw3Vitals:

    def _api(self):
        api = make_tedapi()
        api._cache_put("config", {"battery_blocks": [
            {"vin": DIN, "type": "Powerwall3"},
            {"vin": FOLLOWER, "type": "Powerwall3"},
        ]})
        api._cache_put("components", {"components": {}})
        return api

    def test_transport_error_skips_only_that_powerwall(self):
        api = self._api()

        def post(data, din=None, url_suffix=None):
            if din == FOLLOWER:
                raise requests.exceptions.ReadTimeout("timed out")
            return _message(_components(din))

        with patch.object(api, "_post_tedapi", side_effect=post):
            vitals = api.get_pw3_vitals()
        assert f"TEPINV--{DIN}" in vitals
        assert f"TEPINV--{FOLLOWER}" not in vitals

    def test_never_raises(self):
        api = self._api()
        api.pwcache["config"] = {"battery_blocks": [{"type": "Powerwall3"}]}  # no 'vin'
        assert api.get_pw3_vitals() is None

    def test_result_is_cached(self):
        api = self._api()
        with patch.object(api, "_post_tedapi",
                          side_effect=lambda data, din=None, url_suffix=None:
                          _message(_components(din))) as post:
            first = api.get_pw3_vitals()
            second = api.get_pw3_vitals()
            assert post.call_count == 2          # one per Powerwall, first call only
            api.get_pw3_vitals(force=True)
            assert post.call_count == 4
        assert first and second is first

    def test_cached_for_data_expiry_not_config_expiry(self):
        api = self._api()
        api.pwcacheexpire, api.pwconfigexpire = 5, 300
        api._cache_put("pw3_vitals", {"TEPINV--x": {}})
        api.pwcachetime["pw3_vitals"] -= 10       # older than the data expiry
        with patch.object(api, "_post_tedapi", return_value=None) as post:
            api.get_pw3_vitals()
        assert post.call_count == 2               # refetched, not served for 300s

    def test_empty_result_not_cached(self):
        api = self._api()
        with patch.object(api, "_post_tedapi", return_value=None) as post:
            assert api.get_pw3_vitals() == {}
            api.get_pw3_vitals()
        assert post.call_count == 4


class TestWifiCooldownReset:

    def test_success_clears_cooldown_set_in_flight(self):
        api = make_tedapi()
        api.wifi_host = "192.168.91.1"
        api.wifi_session = MagicMock()
        api.wifi_available = True

        def post(url, data=None, timeout=None):
            # Another thread's failure set a cooldown while this was in flight
            api.wifi_cooldown = time.time() + 120
            resp = MagicMock()
            resp.status_code = 200
            resp.content = b"ok"
            return resp

        api.wifi_session.post.side_effect = post
        assert api._post_tedapi_wifi(b"req") == b"ok"
        assert api.wifi_cooldown == 0
        assert api.wifi_fail_count == 0
