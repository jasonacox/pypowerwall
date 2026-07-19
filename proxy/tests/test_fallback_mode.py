"""Tests for SolarOnly fallback mode tracking and auto-recovery (PR #361).

Covers:
- enter_fallback_mode() / exit_fallback_mode() lifecycle
- /health fallback_mode payload (in/out of fallback)
- /stats fallback_mode payload (in/out of fallback)
- /health/reset clears fallback state
- PW_TEDAPI_PROBE_INTERVAL env var parsing (non-integer → 30, < 5 → clamped to 5)
"""
import json
import os
import time
import unittest
from http import HTTPStatus
from unittest.mock import Mock, patch

import proxy.server as server
from proxy.server import (
    _fallback_mode,
    _fallback_mode_lock,
    enter_fallback_mode,
    exit_fallback_mode,
)
from proxy.tests.test_csv_endpoints import BaseDoGetTest, standard_test_patches


def _reset_fallback_state():
    """Reset _fallback_mode to its initial (non-fallback) state."""
    with _fallback_mode_lock:
        _fallback_mode["is_fallback_mode"] = False
        _fallback_mode["fallback_since"] = None
        _fallback_mode["recovery_attempts"] = 0
        _fallback_mode["last_recovery_attempt"] = None


class TestFallbackModeLifecycle(unittest.TestCase):
    """enter_fallback_mode() / exit_fallback_mode() contract tests."""

    def setUp(self):
        _reset_fallback_state()

    def tearDown(self):
        _reset_fallback_state()

    def test_enter_sets_state(self):
        """enter_fallback_mode() sets is_fallback_mode, records fallback_since, zeroes counters."""
        before = time.time()
        enter_fallback_mode("test reason")

        with _fallback_mode_lock:
            self.assertTrue(_fallback_mode["is_fallback_mode"])
            self.assertIsNotNone(_fallback_mode["fallback_since"])
            self.assertGreaterEqual(_fallback_mode["fallback_since"], before)
            self.assertEqual(_fallback_mode["recovery_attempts"], 0)
            self.assertIsNone(_fallback_mode["last_recovery_attempt"])

    def test_enter_is_idempotent(self):
        """Double enter_fallback_mode() is a no-op — fallback_since is not reset on second call."""
        enter_fallback_mode("first")
        with _fallback_mode_lock:
            first_since = _fallback_mode["fallback_since"]

        time.sleep(0.02)
        enter_fallback_mode("second")  # should not overwrite fallback_since

        with _fallback_mode_lock:
            self.assertEqual(_fallback_mode["fallback_since"], first_since)

    def test_enter_resets_recovery_attempts_to_zero(self):
        """recovery_attempts is reset to zero on enter even if non-zero before."""
        # Simulate a previous partial state (shouldn't happen normally, but guard it anyway)
        with _fallback_mode_lock:
            _fallback_mode["recovery_attempts"] = 99

        enter_fallback_mode("reset check")

        with _fallback_mode_lock:
            self.assertEqual(_fallback_mode["recovery_attempts"], 0)

    def test_exit_clears_all_fields(self):
        """exit_fallback_mode() clears is_fallback_mode, fallback_since, recovery_attempts, last_recovery_attempt."""
        enter_fallback_mode("test")
        with _fallback_mode_lock:
            _fallback_mode["recovery_attempts"] = 5
            _fallback_mode["last_recovery_attempt"] = time.time()

        exit_fallback_mode()

        with _fallback_mode_lock:
            self.assertFalse(_fallback_mode["is_fallback_mode"])
            self.assertIsNone(_fallback_mode["fallback_since"])
            self.assertEqual(_fallback_mode["recovery_attempts"], 0)
            self.assertIsNone(_fallback_mode["last_recovery_attempt"])

    def test_exit_is_idempotent(self):
        """Double exit_fallback_mode() is a no-op — no error when called outside fallback."""
        # Call from non-fallback state — must not raise
        exit_fallback_mode()

        with _fallback_mode_lock:
            self.assertFalse(_fallback_mode["is_fallback_mode"])

    def test_full_lifecycle(self):
        """Full enter → accumulate attempts → exit cycle resets everything."""
        enter_fallback_mode("probe timeout")
        with _fallback_mode_lock:
            _fallback_mode["recovery_attempts"] = 3
            _fallback_mode["last_recovery_attempt"] = time.time()

        exit_fallback_mode()

        with _fallback_mode_lock:
            self.assertFalse(_fallback_mode["is_fallback_mode"])
            self.assertEqual(_fallback_mode["recovery_attempts"], 0)
            self.assertIsNone(_fallback_mode["last_recovery_attempt"])


class TestHealthEndpointFallbackMode(BaseDoGetTest):
    """/health endpoint includes correct fallback_mode payload."""

    def setUp(self):
        super().setUp()
        _reset_fallback_state()

    def tearDown(self):
        super().tearDown()
        _reset_fallback_state()

    def _do_health(self):
        """Hit /health with minimal patches required for the endpoint to render."""
        with standard_test_patches(), \
             patch('proxy.server.pw') as mock_pw, \
             patch('proxy.server.health_check_enabled', False), \
             patch('proxy.server.graceful_degradation', False), \
             patch('proxy.server.get_transport_health', return_value={}), \
             patch('proxy.server._endpoint_stats', {}), \
             patch('proxy.server._endpoint_stats_lock'), \
             patch('proxy.server.time') as mock_time:
            mock_time.time.return_value = 2000.0
            mock_pw.tedapi = None
            self.handler.path = "/health"
            self.handler.do_GET()

    def test_health_not_in_fallback(self):
        """/health fallback_mode is_fallback_mode=False when proxy is healthy."""
        self._do_health()

        self.handler.send_response.assert_called_with(HTTPStatus.OK)
        data = self.get_written_json()

        self.assertIn("fallback_mode", data)
        fm = data["fallback_mode"]
        self.assertFalse(fm["is_fallback_mode"])
        self.assertIsNone(fm["fallback_since"])
        self.assertIsNone(fm["fallback_duration_seconds"])
        self.assertEqual(fm["recovery_attempts"], 0)

    def test_health_in_fallback(self):
        """/health fallback_mode reflects active fallback state."""
        enter_fallback_mode("test probe failure")
        # Align fallback_since with the mocked time.time() = 2000.0 used in _do_health()
        # so that fallback_duration_seconds = round(2000.0 - 1900.0, 1) = 100.0
        with _fallback_mode_lock:
            _fallback_mode["fallback_since"] = 1900.0
            _fallback_mode["recovery_attempts"] = 2

        self._do_health()

        data = self.get_written_json()
        fm = data["fallback_mode"]

        self.assertTrue(fm["is_fallback_mode"])
        self.assertIsNotNone(fm["fallback_since"])
        self.assertIsNotNone(fm["fallback_duration_seconds"])
        self.assertGreaterEqual(fm["fallback_duration_seconds"], 0)
        self.assertEqual(fm["recovery_attempts"], 2)


class TestHealthResetClearsFallback(BaseDoGetTest):
    """/health/reset clears fallback state."""

    def setUp(self):
        super().setUp()
        _reset_fallback_state()

    def tearDown(self):
        super().tearDown()
        _reset_fallback_state()

    def test_health_reset_clears_fallback(self):
        """/health/reset resets is_fallback_mode and all associated fields."""
        enter_fallback_mode("before reset")
        with _fallback_mode_lock:
            _fallback_mode["recovery_attempts"] = 3
            _fallback_mode["last_recovery_attempt"] = time.time()

        with standard_test_patches(), \
             patch('proxy.server.health_check_enabled', False), \
             patch('proxy.server.graceful_degradation', False), \
             patch('proxy.server._endpoint_stats', {}), \
             patch('proxy.server._endpoint_stats_lock'), \
             patch('proxy.server.time') as mock_time:
            mock_time.time.return_value = 3000.0
            self.handler.path = "/health/reset"
            self.handler.do_GET()

        self.handler.send_response.assert_called_with(HTTPStatus.OK)

        with _fallback_mode_lock:
            self.assertFalse(_fallback_mode["is_fallback_mode"])
            self.assertIsNone(_fallback_mode["fallback_since"])
            self.assertEqual(_fallback_mode["recovery_attempts"], 0)
            self.assertIsNone(_fallback_mode["last_recovery_attempt"])

    def test_health_reset_idempotent_when_not_in_fallback(self):
        """/health/reset does not error when proxy is not in fallback mode."""
        with standard_test_patches(), \
             patch('proxy.server.health_check_enabled', False), \
             patch('proxy.server.graceful_degradation', False), \
             patch('proxy.server._endpoint_stats', {}), \
             patch('proxy.server._endpoint_stats_lock'), \
             patch('proxy.server.time') as mock_time:
            mock_time.time.return_value = 3000.0
            self.handler.path = "/health/reset"
            self.handler.do_GET()

        self.handler.send_response.assert_called_with(HTTPStatus.OK)

        with _fallback_mode_lock:
            self.assertFalse(_fallback_mode["is_fallback_mode"])


class TestStatsEndpointFallbackMode(BaseDoGetTest):
    """/stats includes correct fallback_mode payload."""

    def setUp(self):
        super().setUp()
        _reset_fallback_state()

    def tearDown(self):
        super().tearDown()
        _reset_fallback_state()

    def _do_stats(self):
        with standard_test_patches(), \
             patch('proxy.server.pw') as mock_pw, \
             patch('proxy.server.health_check_enabled', False), \
             patch('proxy.server.graceful_degradation', False), \
             patch('proxy.server.safe_pw_call', return_value="Test Site"), \
             patch('proxy.server.resource') as mock_resource, \
             patch('proxy.server.time') as mock_time, \
             patch('proxy.server._endpoint_stats', {}), \
             patch('proxy.server._endpoint_stats_lock'), \
             patch('proxy.server._error_counts', {}), \
             patch('proxy.server._error_counts_lock'):
            mock_time.time.return_value = 2000.0
            mock_resource.getrusage.return_value = Mock(ru_maxrss=1024)
            mock_pw.cloudmode = False
            mock_pw.fleetapi = False
            self.handler.path = "/stats"
            self.handler.do_GET()

    def test_stats_fallback_mode_not_active(self):
        """/stats includes fallback_mode with is_fallback_mode=False when healthy."""
        self._do_stats()

        data = self.get_written_json()
        self.assertIn("fallback_mode", data)
        fm = data["fallback_mode"]
        self.assertFalse(fm["is_fallback_mode"])
        self.assertIsNone(fm["fallback_duration_seconds"])

    def test_stats_fallback_mode_active(self):
        """/stats fallback_mode reflects active fallback including duration and attempt count."""
        enter_fallback_mode("probe timeout")
        # Align fallback_since with the mocked time.time() = 2000.0 in _do_stats()
        with _fallback_mode_lock:
            _fallback_mode["fallback_since"] = 1900.0
            _fallback_mode["recovery_attempts"] = 1

        self._do_stats()

        data = self.get_written_json()
        fm = data["fallback_mode"]

        self.assertTrue(fm["is_fallback_mode"])
        self.assertIsNotNone(fm["fallback_since"])
        self.assertIsNotNone(fm["fallback_duration_seconds"])
        self.assertGreaterEqual(fm["fallback_duration_seconds"], 0)
        self.assertEqual(fm["recovery_attempts"], 1)


class TestProbeIntervalEnvParsing(unittest.TestCase):
    """PW_TEDAPI_PROBE_INTERVAL env var parsing — non-integer → 30, < 5 → clamp to 5."""

    @staticmethod
    def _parse(raw):
        """Replicate the module-level parsing expression."""
        try:
            return max(5, int(raw))
        except (ValueError, TypeError):
            return 30

    def test_default_is_30(self):
        self.assertEqual(self._parse("30"), 30)

    def test_valid_integer_used(self):
        self.assertEqual(self._parse("60"), 60)

    def test_non_integer_string_falls_back_to_30(self):
        self.assertEqual(self._parse("bad_value"), 30)

    def test_empty_string_falls_back_to_30(self):
        self.assertEqual(self._parse(""), 30)

    def test_none_falls_back_to_30(self):
        """None (env var missing) raises TypeError → falls back to 30."""
        self.assertEqual(self._parse(None), 30)

    def test_value_below_5_clamped_to_5(self):
        self.assertEqual(self._parse("2"), 5)
        self.assertEqual(self._parse("1"), 5)
        self.assertEqual(self._parse("0"), 5)

    def test_exactly_5_accepted(self):
        self.assertEqual(self._parse("5"), 5)

    def test_module_constant_is_at_least_5(self):
        """TEDAPI_PROBE_INTERVAL loaded by the running process must respect the clamp."""
        self.assertGreaterEqual(server.TEDAPI_PROBE_INTERVAL, 5)


if __name__ == "__main__":
    unittest.main()
