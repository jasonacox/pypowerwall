"""Tests for PW_TEDAPI_AUTH_MODE wiring through the proxy.

The env var selects the TEDAPI transport (basic HTTP Basic Auth vs. bearer
AuthEnvelope), so the failure this guards is silent: an unwired or dropped
setting leaves the proxy talking basic to a gateway that only answers bearer,
which looks like a dead gateway rather than a config problem.

Covers:
- the env value being coerced leniently (AuthMode.coerce with default=BASIC;
  the fallback behavior itself is tested with the enum in
  pypowerwall/tests/unit/test_bearer_auth.py)
- the value actually reaching pypowerwall.Powerwall(tedapi_auth_mode=...)
- /stats config + status reporting
- /health reporting the auth mode of the live TEDAPI transport
"""
import ast
import unittest
from unittest.mock import Mock

import proxy.server as server
from pypowerwall.tedapi.auth_mode import AuthMode


class TestEnvAuthModeCoercion(unittest.TestCase):
    """A bad container env var must not be fatal — the module-level coercion
    must go through AuthMode.coerce with a default, or a typo becomes a fatal
    "Powerwall Connection Error" and a restart loop."""

    def test_module_value_is_an_auth_mode(self):
        """The value loaded by the running process is coerced, not a raw string."""
        self.assertIsInstance(server.tedapi_auth_mode, AuthMode)

    def test_coercion_call_passes_a_default(self):
        """The call already ran at import, so read the source: the assignment to
        tedapi_auth_mode must call AuthMode.coerce(<PW_TEDAPI_AUTH_MODE env>,
        default=...) — without default= an unknown value raises at startup."""
        src = open(server.__file__, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "coerce"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "AuthMode"):
                self.assertIn("PW_TEDAPI_AUTH_MODE", ast.dump(node),
                              "coerce must read the PW_TEDAPI_AUTH_MODE env var")
                self.assertIn("default", [k.arg for k in node.keywords],
                              "coerce must pass default= so a typo is not fatal")
                return
        self.fail("AuthMode.coerce(...) call not found in proxy/server.py")


class TestPowerwallWiring(unittest.TestCase):
    """The coerced value must reach the Powerwall constructor.

    The call is module-level and already ran at import, so this reads the source
    rather than re-importing (a reload would swap module globals other proxy
    tests hold by reference).
    """

    @staticmethod
    def _powerwall_call_kwargs():
        src = open(server.__file__, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Powerwall"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "pypowerwall"
                    and any(k.arg == "host" for k in node.keywords)):
                return {k.arg: k.value for k in node.keywords}
        return None

    def test_tedapi_auth_mode_is_passed(self):
        kwargs = self._powerwall_call_kwargs()
        self.assertIsNotNone(kwargs, "pypowerwall.Powerwall(host=...) call not found")
        self.assertIn("tedapi_auth_mode", kwargs)
        value = kwargs["tedapi_auth_mode"]
        self.assertIsInstance(value, ast.Name)
        self.assertEqual(value.id, "tedapi_auth_mode",
                         "must pass the coerced module global, not a literal")


class TestStatsReporting(unittest.TestCase):
    """/stats must show both the requested setting and the active mode."""

    def test_config_reports_env_setting(self):
        cfg = server.proxystats["config"]
        self.assertEqual(cfg["PW_TEDAPI_AUTH_MODE"], str(server.tedapi_auth_mode))
        self.assertEqual(cfg["PW_TEDAPI_API_VERSION"], server.tedapi_api_version)

    def test_auth_mode_key_present_and_rendered_as_string(self):
        """JSON-serializable: the enum's value, not "AuthMode.BASIC"."""
        value = server.proxystats["tedapi_auth_mode"]
        self.assertIn(value, [m.value for m in AuthMode])


class TestHealthTransportAuthMode(unittest.TestCase):
    """/health transport detail must name the auth mode of the live TEDAPI."""

    def _transports(self, tedapi):
        pw = Mock()
        pw.cloudmode = False
        pw.fleetapi = False
        pw.tedapi = tedapi
        with unittest.mock.patch.object(server, "pw", pw), \
             unittest.mock.patch.object(server, "pw_control", None), \
             unittest.mock.patch.object(server, "control_secret", ""):
            return server.get_transport_health()

    def test_reports_bearer(self):
        tedapi = Mock(v1r=False, din="DIN1", gw_ip="10.0.0.5",
                      auth_mode=AuthMode.BEARER)
        wifi = self._transports(tedapi)["wifi_tedapi"]
        self.assertTrue(wifi["active"])
        self.assertEqual(wifi["auth_mode"], "bearer")
        self.assertEqual(wifi["host"], "10.0.0.5")

    def test_reports_basic(self):
        tedapi = Mock(v1r=False, din="DIN1", gw_ip="192.168.91.1",
                      auth_mode=AuthMode.BASIC)
        self.assertEqual(self._transports(tedapi)["wifi_tedapi"]["auth_mode"], "basic")


if __name__ == "__main__":
    unittest.main()
