"""Unit tests for firmware change tracking in proxy/server.py.

Covers the state machine of track_firmware_version():
- first non-None version logs exactly once
- identical subsequent versions are silent
- a change logs old -> new
- control characters (log forging) and DEL are stripped
- whitespace is collapsed
- non-str values (int/bytes) are coerced instead of silently ignored
- empty/None values are skipped
"""
import unittest
from unittest.mock import patch

import proxy.server as server


def _reset_state():
    server._firmware_state["version"] = None


class TestTrackFirmwareVersion(unittest.TestCase):
    def setUp(self):
        _reset_state()
        self.log_messages = []
        patcher = patch(
            "proxy.server.log", wraps=None
        )
        self.mock_log = patcher.start()
        self.mock_log.info.side_effect = lambda msg: self.log_messages.append(msg)
        self.addCleanup(patcher.stop)

    def test_first_sighting_logs_once(self):
        server.track_firmware_version("26.18.1 fabf8f5a")
        self.assertEqual(len(self.log_messages), 1)
        self.assertIn("26.18.1 fabf8f5a", self.log_messages[0])

    def test_identical_version_silent(self):
        server.track_firmware_version("26.18.1")
        server.track_firmware_version("26.18.1")
        self.assertEqual(len(self.log_messages), 1)

    def test_change_logs_old_to_new(self):
        server.track_firmware_version("26.18.1")
        server.track_firmware_version("26.18.3-c-2")
        self.assertEqual(len(self.log_messages), 2)
        self.assertIn("26.18.1 -> 26.18.3-c-2", self.log_messages[1])

    def test_none_and_empty_skipped(self):
        server.track_firmware_version(None)
        server.track_firmware_version("")
        server.track_firmware_version("   ")
        self.assertEqual(self.log_messages, [])
        self.assertIsNone(server._firmware_state["version"])

    def test_control_chars_stripped(self):
        server.track_firmware_version("26.18.1\x1b[2J\r\nFAKE-LOG-LINE")
        self.assertEqual(len(self.log_messages), 1)
        # No newlines or ESC survive — a forged line cannot be injected
        for ch in self.log_messages[0]:
            self.assertTrue(ch >= " " and ch != "\x7f")
        self.assertTrue(self.log_messages[0].startswith("Gateway firmware: 26.18.1"))

    def test_del_char_stripped(self):
        server.track_firmware_version("26.18.1\x7f")
        self.assertEqual(self.log_messages[0], "Gateway firmware: 26.18.1")

    def test_whitespace_collapsed(self):
        server.track_firmware_version("26.18.1\t fabf8f5a")
        self.assertEqual(self.log_messages[0], "Gateway firmware: 26.18.1 fabf8f5a")

    def test_non_str_coerced(self):
        server.track_firmware_version(26181)
        self.assertEqual(self.log_messages, ["Gateway firmware: 26181"])

    def test_firmware_check_interval_in_stats_config(self):
        self.assertIn(
            "PW_FIRMWARE_CHECK_INTERVAL", server.proxystats["config"]
        )


if __name__ == "__main__":
    unittest.main()
