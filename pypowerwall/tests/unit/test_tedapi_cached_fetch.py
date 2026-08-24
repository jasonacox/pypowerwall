"""Unit tests for the shared getter skeleton in TEDAPI.

get_config / get_status / get_device_controller / get_firmware_version /
get_components / get_battery_block are one skeleton (``_cached_fetch``) around
different fetches: cache -> cooldown -> lock -> re-check -> reconnect -> fetch
-> cache. These tests pin that skeleton once, parametrized over every getter, so
the behaviors can't drift apart again, and then the per-getter specifics
(transports, cache shapes) and get_din's deliberately different contract.

Everything is mocked at the transport boundary (``_post_tedapi``,
``_post_tedapi_wifi``, ``session``) — nothing here touches a gateway.
"""
import gzip
import logging
import time
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import TEDAPI, tedapi_pb2, _CACHE_MISS
from pypowerwall.tedapi.system_info import SystemInfo

DIN = "1538000-45-D--TESTDIN0000000"
FOLLOWER = "1707000-11-J--FOLLOWER000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tedapi(**kwargs):
    """Basic-mode TEDAPI with connect() patched out, a MagicMock session, empty
    caches and no cooldown."""
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value=DIN):
        api = TEDAPI("testpassword", **kwargs)
    api.din = DIN
    api.session = MagicMock()
    api.pwcache = {}
    api.pwcachetime = {}
    api.pwcooldown = 0
    return api


def make_message(text="", config_text=""):
    """A full transport Message (envelope + tail), as basic mode receives."""
    msg = tedapi_pb2.Message()
    msg.message.deliveryChannel = 1
    if text:
        msg.message.payload.recv.text = text
    if config_text:
        msg.message.config.recv.file.text = config_text
    msg.tail.value = 1
    return msg.SerializeToString()


def mock_response(content=b"", status_code=HTTPStatus.OK):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


# One row per locked getter: how to call it, where it caches, which expiry it
# honors, and a transport patch that makes the fetch succeed with a known value.
class Getter:
    def __init__(self, name, key, expire_attr, call, patch_target, ok_response, ok_value,
                 seed=None, seed_result=None):
        self.name = name
        self.key = key
        self.expire_attr = expire_attr
        self.call = call                  # api -> result
        self.patch_target = patch_target  # attribute mocked at the transport boundary
        self.ok_response = ok_response    # its return value for a successful fetch
        self.ok_value = ok_value          # what the getter then returns/caches
        # a value planted in the cache, and what the getter hands back for it
        self.seed = {"seeded": True} if seed is None else seed
        self.seed_result = self.seed if seed_result is None else seed_result

    def __repr__(self):
        return self.name


SYSINFO = SystemInfo(version="25.10.1 abcd1234", din=DIN)

GETTERS = [
    Getter("get_status", "status", "pwcacheexpire",
           lambda api, **kw: api.get_status(**kw),
           "_post_tedapi", make_message(text='{"control": {"x": 1}}'), {"control": {"x": 1}}),
    Getter("get_device_controller", "controller", "pwcacheexpire",
           lambda api, **kw: api.get_device_controller(**kw),
           "_post_tedapi", make_message(text='{"components": {}}'), {"components": {}}),
    Getter("get_components", "components", "pwconfigexpire",
           lambda api, **kw: api.get_components(**kw),
           "_post_tedapi", make_message(text='{"components": {"pch": []}}'), {"components": {"pch": []}}),
    Getter("get_config", "config", "pwconfigexpire",
           lambda api, **kw: api.get_config(**kw),
           "_post_tedapi", make_message(config_text='{"vin": "GW--1", "battery_blocks": []}'),
           {"vin": "GW--1", "battery_blocks": []}),
    Getter("get_battery_block", DIN, "pwcacheexpire",
           lambda api, **kw: api.get_battery_block(din=DIN, **kw),
           "_post_tedapi", make_message(config_text='{"block": 1}'), {"block": 1}),
    # the firmware cache holds the SystemInfo; the getter derives the version
    Getter("get_firmware_version", "firmware", "pwcacheexpire",
           lambda api, **kw: api.get_firmware_version(**kw),
           "_get_system_info", SYSINFO, SYSINFO.version,
           seed=SystemInfo(version="0.0.0 seeded"), seed_result="0.0.0 seeded"),
]


@pytest.fixture(params=GETTERS, ids=repr)
def getter(request):
    return request.param


# ---------------------------------------------------------------------------
# The shared skeleton — every getter must behave identically
# ---------------------------------------------------------------------------

class TestCachedFetchSkeleton:

    def test_fresh_cache_short_circuits_without_transport(self, getter):
        api = make_tedapi()
        api.pwcache[getter.key] = getter.seed
        api.pwcachetime[getter.key] = time.time()
        with patch.object(api, getter.patch_target) as transport:
            assert getter.call(api) == getter.seed_result
        transport.assert_not_called()

    def test_expired_cache_refetches(self, getter):
        api = make_tedapi()
        api.pwcache[getter.key] = getter.seed
        api.pwcachetime[getter.key] = time.time() - getattr(api, getter.expire_attr) - 1
        with patch.object(api, getter.patch_target, return_value=getter.ok_response) as transport:
            assert getter.call(api) == getter.ok_value
        transport.assert_called_once()

    def test_force_bypasses_fresh_cache(self, getter):
        api = make_tedapi()
        api.pwcache[getter.key] = getter.seed
        api.pwcachetime[getter.key] = time.time()
        with patch.object(api, getter.patch_target, return_value=getter.ok_response) as transport:
            assert getter.call(api, force=True) == getter.ok_value
        transport.assert_called_once()

    def test_cooldown_returns_none_without_transport(self, getter):
        api = make_tedapi()
        api.pwcooldown = time.perf_counter() + 300
        with patch.object(api, getter.patch_target) as transport:
            assert getter.call(api) is None
        transport.assert_not_called()

    def test_force_bypasses_cooldown(self, getter):
        api = make_tedapi()
        api.pwcooldown = time.perf_counter() + 300
        with patch.object(api, getter.patch_target, return_value=getter.ok_response):
            assert getter.call(api, force=True) == getter.ok_value

    def test_success_is_cached_with_timestamp(self, getter):
        api = make_tedapi()
        before = time.time()
        with patch.object(api, getter.patch_target, return_value=getter.ok_response):
            getter.call(api)
        assert getter.key in api.pwcache
        assert api.pwcachetime[getter.key] >= before

    def test_transport_none_returns_none_and_leaves_cache_alone(self, getter):
        """A silent transport (busy, 401, malformed) must not poison the cache:
        the next poll must retry rather than serve None for the expiry window."""
        api = make_tedapi()
        with patch.object(api, getter.patch_target, return_value=None):
            assert getter.call(api) is None
        assert getter.key not in api.pwcache
        assert getter.key not in api.pwcachetime

    def test_fetch_exception_is_logged_not_raised(self, getter, caplog):
        api = make_tedapi()
        with patch.object(api, getter.patch_target, side_effect=OSError("boom")), \
                caplog.at_level(logging.ERROR):
            assert getter.call(api) is None
        assert "Error fetching" in caplog.text and "boom" in caplog.text
        assert getter.key not in api.pwcache

    def test_lock_timeout_serves_stale_cache(self, getter):
        """Bounded lock wait: on timeout hand back whatever is cached (even if
        expired) rather than raising into a poller."""
        api = make_tedapi()
        api.pwcache[getter.key] = getter.seed
        api.pwcachetime[getter.key] = 0
        with patch("pypowerwall.api_lock.acquire_with_exponential_backoff", return_value=False), \
                patch.object(api, getter.patch_target) as transport:
            assert getter.call(api) == getter.seed_result
        transport.assert_not_called()

    def test_lock_timeout_without_cache_returns_none(self, getter):
        api = make_tedapi()
        with patch("pypowerwall.api_lock.acquire_with_exponential_backoff", return_value=False):
            assert getter.call(api) is None

    def test_reconnects_when_din_unknown(self, getter):
        """A getter on a not-yet-connected object must attempt connect() first —
        the documented failure shape after a failed startup is din=None."""
        api = make_tedapi()
        api.din = None

        def fake_connect(force=False):
            api.din = DIN
            return DIN

        with patch.object(api, "connect", side_effect=fake_connect) as connect, \
                patch.object(api, getter.patch_target, return_value=getter.ok_response):
            assert getter.call(api) == getter.ok_value
        connect.assert_called_once()

    def test_failed_reconnect_returns_none(self, getter, caplog):
        api = make_tedapi()
        api.din = None
        with patch.object(api, "connect", return_value=None), \
                patch.object(api, getter.patch_target) as transport, \
                caplog.at_level(logging.ERROR):
            assert getter.call(api) is None
        transport.assert_not_called()
        assert "Not Connected" in caplog.text


# ---------------------------------------------------------------------------
# _cache_get / _fetch_query / _decode_json
# ---------------------------------------------------------------------------

class TestCacheGet:

    def test_missing_timestamp_is_a_miss(self):
        api = make_tedapi()
        api.pwcache["status"] = {"x": 1}
        assert api._cache_get("status", 5) is _CACHE_MISS

    def test_missing_value_is_a_miss(self):
        """A key whose value was popped (cache invalidation) must not KeyError."""
        api = make_tedapi()
        api.pwcachetime["status"] = time.time()
        assert api._cache_get("status", 5) is _CACHE_MISS

    def test_fresh_and_expired(self):
        api = make_tedapi()
        api.pwcache["status"] = {"x": 1}
        api.pwcachetime["status"] = time.time()
        assert api._cache_get("status", 5) == {"x": 1}
        api.pwcachetime["status"] = time.time() - 6
        assert api._cache_get("status", 5) is _CACHE_MISS


class TestFetchQuery:

    def test_none_response_is_none(self):
        api = make_tedapi()
        with patch.object(api, "_post_tedapi", return_value=None):
            assert api._fetch_query("device_controller_basic") is None

    def test_malformed_payload_is_none(self, caplog):
        """A malformed payload decodes to None so the caller leaves its cache alone."""
        api = make_tedapi()
        with patch.object(api, "_post_tedapi", return_value=make_message(text="{not json")), \
                caplog.at_level(logging.ERROR):
            assert api._fetch_query("device_controller_basic") is None
        assert "Error Decoding JSON" in caplog.text

    def test_routes_din_and_url_suffix_to_transport(self):
        api = make_tedapi()
        with patch.object(api, "_post_tedapi", return_value=make_message(text="{}")) as post:
            api._fetch_query("components", recipient_din=FOLLOWER, sender_din=DIN, tail=2,
                             din=FOLLOWER, url_suffix=f"/tedapi/device/{FOLLOWER}/v1")
        assert post.call_args.kwargs == {"din": FOLLOWER,
                                         "url_suffix": f"/tedapi/device/{FOLLOWER}/v1"}
        sent = tedapi_pb2.Message.FromString(post.call_args.args[0])
        assert sent.message.recipient.din == FOLLOWER
        assert sent.message.sender.din == DIN
        assert sent.tail.value == 2

    def test_wifi_route_parses_full_message(self):
        """A v1r follower query goes out on _post_tedapi_wifi and its full-Message
        answer must be parsed as such (from_wifi), even with v1r set."""
        api = make_tedapi()
        api.v1r = True
        with patch.object(api, "_post_tedapi_wifi",
                          return_value=make_message(text='{"w": 1}')) as wifi, \
                patch.object(api, "_post_tedapi") as lan:
            assert api._fetch_query("components", use_wifi=True,
                                    url_suffix="/tedapi/device/X/v1") == {"w": 1}
        wifi.assert_called_once()
        lan.assert_not_called()


class TestDecodeJson:

    @pytest.mark.parametrize("payload", ["", "{bad", "[1,"])
    def test_malformed_payloads_log_and_return_none(self, payload, caplog):
        with caplog.at_level(logging.ERROR):
            assert TEDAPI._decode_json(payload) is None
        assert "Error Decoding JSON" in caplog.text

    def test_missing_payload_is_none_without_logging(self, caplog):
        with caplog.at_level(logging.ERROR):
            assert TEDAPI._decode_json(None) is None
        assert caplog.text == ""

    def test_empty_object_is_preserved(self):
        """A well-formed empty JSON object stays {} — distinct from None."""
        assert TEDAPI._decode_json("{}") == {}

    def test_good_payload(self):
        assert TEDAPI._decode_json('{"a": [1, 2]}') == {"a": [1, 2]}


# ---------------------------------------------------------------------------
# Per-getter specifics
# ---------------------------------------------------------------------------

class TestFirmwareVersion:

    def test_cache_holds_system_info_and_serves_both_shapes(self):
        """The cache holds the SystemInfo, so details=True on a cache hit gets the
        details dict — it used to hand back the cached version *string*."""
        api = make_tedapi()
        with patch.object(api, "_get_system_info", return_value=SYSINFO) as fetch:
            assert api.get_firmware_version() == SYSINFO.version
            details = api.get_firmware_version(details=True)
        fetch.assert_called_once()
        assert api.pwcache["firmware"] is SYSINFO
        assert details == SYSINFO.to_details_dict()
        assert details["system"]["version"]["text"] == SYSINFO.version


class TestConfigFetch:

    def test_battery_blocks_defaulted(self):
        api = make_tedapi()
        with patch.object(api, "_post_tedapi", return_value=make_message(config_text='{"vin": "GW"}')):
            assert api.get_config() == {"vin": "GW", "battery_blocks": []}

    def test_malformed_json_is_none(self):
        """A malformed config payload returns None so the cache is left alone."""
        api = make_tedapi()
        with patch.object(api, "_post_tedapi", return_value=make_message(config_text="{nope")):
            assert api.get_config() is None

    def test_v1r_lan_reads_filestore(self):
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = False
        api.v1r_transport = MagicMock()
        api.v1r_transport.get_config_v1r.return_value = {"vin": "PW3", "battery_blocks": [1]}
        with patch.object(api, "_post_tedapi") as lan, patch.object(api, "_post_tedapi_wifi") as wifi:
            assert api.get_config() == {"vin": "PW3", "battery_blocks": [1]}
        api.v1r_transport.get_config_v1r.assert_called_once_with(DIN)
        lan.assert_not_called()
        wifi.assert_not_called()

    def test_v1r_lan_down_with_wifi_uses_wifi_fallback(self):
        """LAN down + WiFi session: the legacy config.send request goes straight
        to _post_tedapi_wifi (never _post_tedapi's LAN route) and its full
        Message answer is parsed as such."""
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = True
        api.wifi_session = object()
        api.v1r_transport = MagicMock()
        with patch.object(api, "_post_tedapi_wifi",
                          return_value=make_message(config_text='{"vin": "WIFI"}')) as wifi, \
                patch.object(api, "_post_tedapi") as lan:
            assert api.get_config() == {"vin": "WIFI", "battery_blocks": []}
        sent = tedapi_pb2.Message.FromString(wifi.call_args.args[0])
        assert sent.message.config.send.file == "config.json"
        lan.assert_not_called()
        api.v1r_transport.get_config_v1r.assert_not_called()

    def test_v1r_lan_down_without_wifi_still_tries_filestore(self):
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = True
        api.wifi_session = None
        api.v1r_transport = MagicMock()
        api.v1r_transport.get_config_v1r.return_value = None
        assert api.get_config() is None
        api.v1r_transport.get_config_v1r.assert_called_once_with(DIN)


class TestBatteryBlock:

    def test_requires_din(self, caplog):
        api = make_tedapi()
        with caplog.at_level(logging.ERROR):
            assert api.get_battery_block() is None
        assert "No DIN specified" in caplog.text

    def test_cache_is_keyed_by_din(self):
        api = make_tedapi()
        with patch.object(api, "_post_tedapi", return_value=make_message(config_text='{"b": 1}')):
            api.get_battery_block(din=FOLLOWER)
        assert api.pwcache[FOLLOWER] == {"b": 1}

    def test_v1r_follower_without_wifi_returns_none(self):
        api = make_tedapi()
        api.v1r = True
        api.wifi_session = None
        with patch.object(api, "_post_tedapi") as lan:
            assert api.get_battery_block(din=FOLLOWER) is None
        lan.assert_not_called()

    def test_v1r_follower_with_wifi_routes_per_device(self):
        api = make_tedapi()
        api.v1r = True
        api.wifi_session = object()
        with patch.object(api, "_post_tedapi_wifi",
                          return_value=make_message(config_text='{"b": 2}')) as wifi:
            assert api.get_battery_block(din=FOLLOWER) == {"b": 2}
        assert wifi.call_args.kwargs["url_suffix"] == f"/tedapi/device/{FOLLOWER}/v1"
        sent = tedapi_pb2.Message.FromString(wifi.call_args.args[0])
        assert sent.message.recipient.din == FOLLOWER
        assert sent.message.sender.din == DIN
        assert sent.tail.value == 2


# ---------------------------------------------------------------------------
# get_din — same cache/cooldown, but unlocked, no reconnect, exceptions propagate
# ---------------------------------------------------------------------------

class TestGetDin:

    def test_fresh_cache(self):
        api = make_tedapi()
        api.pwcache["din"] = "CACHED"
        api.pwcachetime["din"] = time.time()
        assert api.get_din() == "CACHED"
        api.session.get.assert_not_called()

    def test_cooldown(self):
        api = make_tedapi()
        api.pwcooldown = time.perf_counter() + 300
        assert api.get_din() is None
        api.session.get.assert_not_called()

    def test_http_ok_is_cached(self):
        api = make_tedapi()
        api.session.get.return_value = mock_response(b"  1538000-45-D--X \n")
        assert api.get_din() == "1538000-45-D--X"
        assert api.pwcache["din"] == "1538000-45-D--X"

    def test_http_gzip(self):
        api = make_tedapi()
        api.session.get.return_value = mock_response(gzip.compress(b"GZ--DIN"))
        assert api.get_din() == "GZ--DIN"

    def test_http_busy_activates_cooldown(self):
        api = make_tedapi()
        api.session.get.return_value = mock_response(b"", HTTPStatus.TOO_MANY_REQUESTS)
        assert api.get_din() is None
        assert api.pwcooldown > time.perf_counter()

    def test_http_forbidden_advises_password(self, caplog):
        api = make_tedapi()
        api.session.get.return_value = mock_response(b"", HTTPStatus.FORBIDDEN)
        with caplog.at_level(logging.ERROR):
            assert api.get_din() is None
        assert "Gateway Password" in caplog.text

    def test_http_error_returns_none(self):
        api = make_tedapi()
        api.session.get.return_value = mock_response(b"", HTTPStatus.INTERNAL_SERVER_ERROR)
        assert api.get_din() is None
        assert "din" not in api.pwcache

    def test_transport_exception_propagates_to_connect(self):
        """connect() relies on the exception to log its routing advice — get_din
        must not swallow it like the locked getters do."""
        api = make_tedapi()
        api.session.get.side_effect = OSError("no route")
        with pytest.raises(OSError):
            api.get_din()

    def test_v1r_lan(self):
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = False
        api.v1r_transport = MagicMock()
        api.v1r_transport.get_din.return_value = "V1R--DIN"
        assert api.get_din() == "V1R--DIN"
        assert api.pwcache["din"] == "V1R--DIN"
        api.session.get.assert_not_called()

    def test_v1r_lan_down_uses_wifi_host(self):
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = True
        api.wifi_host = "10.0.0.9"
        api.wifi_session = MagicMock()
        api.wifi_session.get.return_value = mock_response(b"WIFI--DIN")
        api.v1r_transport = MagicMock()
        assert api.get_din() == "WIFI--DIN"
        assert api.wifi_session.get.call_args.args[0] == "https://10.0.0.9/tedapi/din"
        api.v1r_transport.get_din.assert_not_called()

    def test_v1r_lan_down_without_wifi_returns_none(self):
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = True
        api.wifi_session = None
        assert api.get_din() is None

    def test_v1r_wifi_error_is_swallowed(self, caplog):
        """The WiFi fallback is best-effort (unlike the primary GET)."""
        api = make_tedapi()
        api.v1r = True
        api.lan_failed = True
        api.wifi_session = MagicMock()
        api.wifi_session.get.side_effect = OSError("wifi down")
        with caplog.at_level(logging.ERROR):
            assert api.get_din() is None
        assert "WiFi fallback failed" in caplog.text
