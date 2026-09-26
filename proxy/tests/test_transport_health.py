"""Tests for get_transport_health()'s v1r LAN block (/health "transports").

A known leader DIN no longer means the wired LAN is up: the library keeps the
DIN through a failed reconnect, and reads it from the WiFi host when the LAN
is down at startup. The v1r_lan status therefore also checks lan_failed, and
the block reports the failover setting, whether traffic has failed over, and
when the LAN is retried.
"""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import proxy.server as server

DIN = "1707000-11-J--TG0123456789AB"


def v1r_tedapi(**overrides):
    fields = dict(v1r=True, din=DIN, gw_ip="10.42.1.40", lan_failed=False, lan_recover_after=0,
                  lan_last_success=0, failover=True, wifi_session=None)
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestV1rLanHealth(unittest.TestCase):

    def _v1r_lan(self, tedapi):
        with patch.object(server, "pw", SimpleNamespace(tedapi=tedapi)), \
                patch.object(server, "pw_control", None):
            return server.get_transport_health()["v1r_lan"]

    def test_healthy_lan(self):
        info = self._v1r_lan(v1r_tedapi())
        self.assertEqual(info["status"], "ok")
        self.assertIs(info["failover"], True)
        self.assertIs(info["failed_over"], False)
        self.assertNotIn("lan_retry_in_seconds", info)

    def test_failed_over_is_unavailable_despite_din(self):
        info = self._v1r_lan(v1r_tedapi(lan_failed=True, lan_recover_after=time.time() + 480))
        self.assertEqual(info["status"], "unavailable")
        self.assertEqual(info["leader_din"], DIN)
        self.assertIs(info["failed_over"], True)
        self.assertTrue(470 <= info["lan_retry_in_seconds"] <= 480)

    def test_no_din_is_unavailable(self):
        self.assertEqual(self._v1r_lan(v1r_tedapi(din=None))["status"], "unavailable")

    def test_strict_mode_reported(self):
        self.assertIs(self._v1r_lan(v1r_tedapi(failover=False))["failover"], False)

    def test_older_library_without_failover_attribute(self):
        tedapi = v1r_tedapi()
        del tedapi.failover
        self.assertIs(self._v1r_lan(tedapi)["failover"], True)


if __name__ == "__main__":
    unittest.main()
