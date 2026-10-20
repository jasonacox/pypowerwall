"""/stats and the power-flow page are unauthenticated: they show that an
account detail, secret or filesystem path is set without showing it, as
pypowerwall-server does. Keys keep their place; unset values stay unset."""
import copy
import json
import unittest
from unittest.mock import patch

import proxy.server as server
from proxy.tests.test_csv_endpoints import BaseDoGetTest

MASK = "**********"


class TestMaskedHelper(unittest.TestCase):

    def test_set_values_are_masked(self):
        for value in ("secret", "/auth/.powerwall", 123456):
            self.assertEqual(server._masked(value), MASK)

    def test_unset_values_pass_through(self):
        for value in (None, ""):
            self.assertEqual(server._masked(value), value)


class TestStatsConfig(unittest.TestCase):

    def test_sensitive_config_values_are_masked_or_unset(self):
        config = server.proxystats["config"]
        for key in ("PW_PASSWORD", "PW_EMAIL", "PW_SITEID", "PW_AUTH_PATH",
                    "PW_CACHE_FILE", "PW_CONTROL_SECRET", "PW_GW_PWD",
                    "PW_RSA_KEY_PATH"):
            self.assertIn(key, config)
            self.assertIn(config[key], (MASK, None, ""), key)

    def test_unset_secrets_stay_null(self):
        """Unset secrets keep reporting null, as before (none are set in tests)."""
        self.assertFalse(server.password or server.control_secret or server.gw_pwd)
        for key in ("PW_PASSWORD", "PW_CONTROL_SECRET", "PW_GW_PWD"):
            self.assertIsNone(server.proxystats["config"][key], key)

    def test_raw_values_never_appear(self):
        stats = json.dumps(server.proxystats)
        self.assertEqual(server.proxystats["cf"], MASK)
        for raw in (server.email, server.cachefile):
            self.assertNotIn(f'"{raw}"', stats)


class TestStatsSiteId(BaseDoGetTest):

    def test_cloud_siteid_is_masked(self):
        stats = copy.deepcopy(server.proxystats)
        with patch.object(server, "proxystats", stats), \
                patch.object(server, "proxystats_lock"), \
                patch.object(server, "safe_pw_call", return_value="My Home"), \
                patch.object(server, "pw") as pw:
            pw.cloudmode = True
            pw.fleetapi = False
            pw.client.siteid = 1234567890
            pw.client.counter = 3
            self.handler.path = "/stats"
            self.handler.do_GET()
        written = self.get_written_text()
        self.assertEqual(json.loads(written)["siteid"], MASK)
        self.assertNotIn("1234567890", written)


class TestHelpSiteId(BaseDoGetTest):

    def test_help_page_shows_masked_siteid(self):
        stats = copy.deepcopy(server.proxystats)
        with patch.object(server, "proxystats", stats), \
                patch.object(server, "proxystats_lock"), \
                patch.object(server, "api_base_url", ""), \
                patch.object(server, "safe_pw_call", return_value="My Home"), \
                patch.object(server, "pw") as pw:
            pw.cloudmode = False
            pw.fleetapi = True
            pw.client.siteid = 1234567890
            pw.client.counter = 3
            pw.authmode = "cookie"
            self.handler.path = "/help"
            self.handler.do_GET()
        written = self.get_written_text()
        self.assertIn(MASK, written)
        self.assertNotIn("1234567890", written)


class TestPowerFlowPage(BaseDoGetTest):

    def test_email_is_not_in_the_page(self):
        with patch.object(server, "email", "owner@example.com"), \
                patch.object(server, "api_base_url", ""), \
                patch.object(server, "safe_pw_call", return_value={}), \
                patch.object(server, "proxystats_lock"), \
                patch.object(server, "proxystats", copy.deepcopy(server.proxystats)), \
                patch.object(server, "pw"):
            self.handler.path = "/"
            self.handler.do_GET()
        page = b"".join(c.args[0] for c in self.handler.wfile.write.call_args_list)
        self.assertIn(b'"username": ""', page)
        self.assertNotIn(b"owner@example.com", page)


if __name__ == "__main__":
    unittest.main()
