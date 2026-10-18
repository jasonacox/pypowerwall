"""Tests for PW_FAILOVER wiring through the proxy (#402).

PW_FAILOVER=no pins the configured transports (pypowerwall's failover=False):
the v1r leader stays on the wired LAN and the proxy never falls back from local
to FleetAPI or Cloud mode. An unwired setting fails silently - the proxy keeps
rerouting writes and reads the user asked it not to - so these tests check that
the value reaches every pypowerwall.Powerwall() call and /stats.

The calls are module-level and already ran at import, so the wiring checks read
the source rather than re-importing (a reload would swap module globals other
proxy tests hold by reference).
"""
import ast
import unittest

import proxy.server as server


def _powerwall_calls():
    """keyword-argument maps of every pypowerwall.Powerwall(...) call in server.py"""
    src = open(server.__file__, encoding="utf-8").read()
    calls = []
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Powerwall"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pypowerwall"):
            calls.append({k.arg: k.value for k in node.keywords})
    return calls


class TestFailoverEnv(unittest.TestCase):

    def test_default_is_on(self):
        """Unset in the test environment: failover stays on, as in the library."""
        self.assertIs(server.failover, True)

    def test_only_no_turns_it_off(self):
        """The module-level assignment compares with "no" (!=), so a typo such as
        "false" or "off" keeps the library default instead of disabling failover."""
        src = open(server.__file__, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "failover"):
                dump = ast.dump(node.value)
                self.assertIn("PW_FAILOVER", dump)
                self.assertIsInstance(node.value, ast.Compare)
                self.assertIsInstance(node.value.ops[0], ast.NotEq)
                self.assertEqual(node.value.comparators[0].value, "no")
                return
        self.fail("failover = ... assignment not found in proxy/server.py")

    def test_every_powerwall_call_passes_failover(self):
        """The data connection and the cloud control connection both get it."""
        calls = _powerwall_calls()
        self.assertGreaterEqual(len(calls), 2)
        for kwargs in calls:
            self.assertIn("failover", kwargs)
            value = kwargs["failover"]
            self.assertIsInstance(value, ast.Name)
            self.assertEqual(value.id, "failover",
                             "must pass the module global, not a literal")

    def test_stats_config_reports_setting(self):
        self.assertIs(server.proxystats["config"]["PW_FAILOVER"], server.failover)


if __name__ == "__main__":
    unittest.main()
