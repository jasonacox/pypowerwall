"""Unit tests for the ``failover`` option (Powerwall, PyPowerwallTEDAPI, TEDAPI).

failover=True (default, what the proxy and pypowerwall-server use) keeps every
automatic switch: Powerwall.connect() falls back across modes, and v1r with a
wifi_host moves the leader's queries to the WiFi host while the LAN is down
and back when it recovers. failover=False is strict: the configured mode and
transport only, failures return None/False — e.g. a script testing which modes
work. These tests pin both, and that the default is unchanged.

Everything is mocked at the transport boundary — nothing here touches a gateway.
"""
import inspect
from unittest.mock import MagicMock, patch

import pytest

import pypowerwall
from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI

LEADER = "1707000-11-J--TG0123456789AB"
FOLLOWER = "1707000-11-J--TG0FOLLOWER01"


def make_v1r(failover=True, din=LEADER):
    """v1r TEDAPI with a WiFi host configured and a healthy LAN."""
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value=din):
        ted = TEDAPI(gw_pwd="testpassword", failover=failover)
    ted.v1r = True
    ted.din = din
    ted.wifi_host = "192.168.91.1"
    ted.wifi_session = MagicMock()
    ted.v1r_transport = MagicMock()
    return ted


class TestDefaults:

    @pytest.mark.parametrize("cls", [pypowerwall.Powerwall, PyPowerwallTEDAPI, TEDAPI])
    def test_default_is_failover_on_and_last(self, cls):
        params = list(inspect.signature(cls.__init__).parameters.values())
        assert params[-1].name == "failover"          # appended: positional calls unchanged
        assert params[-1].default is True

    def test_wrapper_passes_failover_through(self):
        with patch("pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI") as ted_cls:
            ted_cls.return_value.connect.return_value = LEADER
            PyPowerwallTEDAPI("pwd", failover=False)
        assert ted_cls.call_args.kwargs["failover"] is False


class TestStrictTedapi:

    def test_leader_never_routes_via_wifi(self):
        ted = make_v1r(failover=False)
        ted.v1r_transport.post_v1r.return_value = None
        with patch.object(ted, "_post_tedapi_wifi") as wifi:
            for _ in range(5):
                assert ted._post_tedapi(b"req") is None
        assert ted.v1r_transport.post_v1r.call_count == 5   # every request tried the LAN
        wifi.assert_not_called()
        assert ted.lan_failed is False

    def test_default_trips_after_three(self):
        ted = make_v1r(failover=True)
        ted.v1r_transport.post_v1r.return_value = None
        with patch.object(ted, "_post_tedapi_wifi", return_value=None) as wifi:
            for _ in range(5):
                ted._post_tedapi(b"req")
        assert ted.v1r_transport.post_v1r.call_count == 3
        assert wifi.call_count == 2
        assert ted.lan_failed is True

    def test_first_connect_lan_down_does_not_use_wifi(self):
        ted = make_v1r(failover=False, din=None)
        ted.v1r_transport.login.return_value = False
        assert ted._connect_v1r() is None
        ted.wifi_session.get.assert_not_called()
        assert ted.lan_failed is False and ted.din is None

    def test_followers_still_use_wifi_host(self):
        """Follower routing isn't failover: v1r can only reach followers via
        the WiFi host, strict or not."""
        ted = make_v1r(failover=False)
        ted._cache_put("config", {"battery_blocks": [
            {"vin": LEADER, "type": "Powerwall3"}, {"vin": FOLLOWER, "type": "Powerwall3"}]})
        ted._cache_put("components", {"components": {}})
        with patch.object(ted, "_post_tedapi", return_value=None) as lan, \
                patch.object(ted, "_post_tedapi_wifi", return_value=None) as wifi:
            ted.get_pw3_vitals()
        assert lan.call_args.kwargs["din"] == LEADER
        assert FOLLOWER in wifi.call_args.kwargs["url_suffix"]

    @pytest.mark.parametrize("failover, hosts", [
        (True, ["10.42.1.40", "192.168.91.1"]),
        (False, ["10.42.1.40"]),
    ])
    def test_native_api_hosts(self, failover, hosts):
        ted = make_v1r(failover=failover)
        ted.gw_ip = "10.42.1.40"
        tried = []
        with patch.object(ted, "_customer_password", return_value="pw"), \
                patch.object(ted, "_native_get", side_effect=lambda host, path: tried.append(host)):
            assert ted.get_native_api("/api/meters/aggregates") is None
        assert tried == hosts


class TestStrictPowerwallConnect:

    @pytest.fixture
    def clients(self):
        with patch("pypowerwall.PyPowerwallTEDAPI") as ted, \
                patch("pypowerwall.PyPowerwallLocal") as local, \
                patch("pypowerwall.PyPowerwallFleetAPI") as fleet, \
                patch("pypowerwall.PyPowerwallCloud") as cloud:
            for cls in (ted, local, fleet, cloud):
                cls.return_value = MagicMock()
            # A v1r connect failure raises from the constructor (ConnectionError)
            ted.side_effect = ConnectionError("LAN down")
            yield {"tedapi": ted, "fleet": fleet, "cloud": cloud}

    def _v1r(self, **kwargs):
        return pypowerwall.Powerwall(host="10.42.1.40", gw_pwd="ABCDELNDYT",
                                     rsa_key_path="/tmp/fake_key.pem", **kwargs)

    def test_strict_tries_only_configured_mode(self, clients):
        pw = self._v1r(failover=False)
        assert pw.client is None
        clients["tedapi"].assert_called_once()
        assert clients["tedapi"].call_args.kwargs["failover"] is False
        clients["fleet"].assert_not_called()
        clients["cloud"].assert_not_called()
        assert pw.mode == "local"

    def test_full_tedapi_mode_forwards_failover(self, clients):
        clients["tedapi"].side_effect = None
        pypowerwall.Powerwall(host="192.168.91.1", gw_pwd="ABCDELNDYT", failover=False)
        assert clients["tedapi"].call_args.kwargs["failover"] is False

    def test_default_still_falls_back_to_other_modes(self, clients):
        pw = self._v1r()
        assert clients["tedapi"].call_args.kwargs["failover"] is True
        clients["fleet"].assert_called()
        assert pw.mode == "fleetapi" and pw.client is clients["fleet"].return_value

    def test_strict_retry_retries_configured_mode_only(self, clients):
        connected = MagicMock()
        clients["tedapi"].side_effect = [ConnectionError("down"), connected]
        with patch("pypowerwall.time.sleep") as sleep:
            pw = self._v1r(failover=False, retry_modes=True)
        sleep.assert_called_once_with(30)
        assert clients["tedapi"].call_count == 2
        clients["fleet"].assert_not_called()
        assert pw.tedapi_mode == "v1r" and pw.client is connected
