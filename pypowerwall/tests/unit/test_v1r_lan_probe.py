"""Unit tests for the v1r LAN recovery probe and failover accounting under concurrency.

The proxy is a ThreadingHTTPServer and the TEDAPI getters each hold their own
per-method API lock, so several threads can be inside TEDAPI._post_tedapi at
once. These tests pin that:
  1. exactly one thread claims each LAN recovery probe (_connect_v1r runs
     once) while the others keep routing via the WiFi fallback;
  2. _connect_v1r keeps the known DIN visible while it reconnects, and still
     clears it (returning None) when the reconnect fails;
  3. concurrent LAN failures trip the failover exactly once, on the regular
     backoff schedule, and requests already in flight when it tripped don't
     escalate it.

Everything is mocked at the transport boundary — nothing here touches a gateway.
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import TEDAPI

LEADER_DIN = "1707000-11-J--TG0123456789AB"
THREADS = 6
WAIT = 5  # seconds; generous upper bound so a slow CI box can't flake


def _make_v1r_tedapi():
    """A TEDAPI in v1r mode with the LAN marked failed and the recovery window open."""
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value=LEADER_DIN):
        ted = TEDAPI(gw_pwd="testpassword")
    ted.v1r = True
    ted.din = LEADER_DIN
    ted.v1r_transport = MagicMock()
    ted.wifi_session = MagicMock()   # truthy: WiFi fallback configured
    ted.wifi_session.get.return_value.status_code = 503   # WiFi /tedapi/din down unless a test says otherwise
    ted.lan_failed = True
    ted.lan_fail_count = 3
    ted.lan_recover_after = 0        # window open
    return ted


def _run_threads(target, n=THREADS):
    """Start n threads into target() together; return (threads, errors)."""
    barrier = threading.Barrier(n)
    errors = []

    def worker():
        try:
            barrier.wait(WAIT)
            target()
        except Exception as e:  # surfaced by the caller's assert
            errors.append(e)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(n)]
    for t in threads:
        t.start()
    return threads, errors


class TestLanRecoveryProbeClaim:
    """Only one thread reconnects when the recovery window opens."""

    def _probe_race(self, ted, connect_result):
        """Race THREADS callers into _post_tedapi with a slow _connect_v1r that
        blocks until every other caller has been served via WiFi."""
        release = threading.Event()
        wifi_done = threading.Semaphore(0)
        connect_calls = []

        def slow_connect(keep_din=False):
            connect_calls.append(threading.current_thread().name)
            # Held here, mid-reconnect, until the other THREADS-1 callers have
            # been routed via WiFi (bounded so a regression fails, not hangs).
            release.wait(WAIT)
            if connect_result:
                ted.lan_failed = False   # what a successful _connect_v1r does
                ted.lan_fail_count = 0
                ted.lan_recover_after = 0
            return connect_result

        def wifi(pb_bytes, url_suffix):
            wifi_done.release()
            return None

        with patch.object(ted, "_connect_v1r", side_effect=slow_connect), \
                patch.object(ted, "_post_tedapi_wifi", side_effect=wifi) as wifi_post:
            threads, errors = _run_threads(lambda: ted._post_tedapi(b"req"))
            for _ in range(THREADS - 1):
                assert wifi_done.acquire(timeout=WAIT), \
                    "other callers must route via WiFi while the probe reconnects"
            release.set()
            for t in threads:
                t.join(WAIT)
        assert not errors, errors
        return connect_calls, wifi_post

    def test_probe_claimed_exactly_once_on_failure(self):
        ted = _make_v1r_tedapi()
        before = time.time()
        connect_calls, wifi_post = self._probe_race(ted, connect_result=None)

        assert len(connect_calls) == 1, f"_connect_v1r ran {len(connect_calls)} times"
        # Every caller was served via WiFi, the probe winner after its failed reconnect
        assert wifi_post.call_count == THREADS
        # One failed probe = one backoff step: 3 -> 4 failures, next probe in 60 * 2**4 s
        assert ted.lan_failed is True
        assert ted.lan_fail_count == 4
        assert before + 960 <= ted.lan_recover_after <= time.time() + 960

    def test_probe_claimed_exactly_once_on_success(self):
        ted = _make_v1r_tedapi()
        ted.v1r_transport.post_v1r.return_value = b"envelope"
        connect_calls, wifi_post = self._probe_race(ted, connect_result=LEADER_DIN)

        assert len(connect_calls) == 1, f"_connect_v1r ran {len(connect_calls)} times"
        # The losers went WiFi while the probe ran; the winner resumed on LAN,
        # signing with the leader DIN
        assert wifi_post.call_count == THREADS - 1
        ted.v1r_transport.post_v1r.assert_called_once()
        assert ted.v1r_transport.post_v1r.call_args.args[1] == LEADER_DIN
        assert ted.lan_failed is False
        assert ted.lan_fail_count == 0

    def test_no_probe_before_window(self):
        ted = _make_v1r_tedapi()
        ted.lan_recover_after = time.time() + 300
        with patch.object(ted, "_connect_v1r") as connect, \
                patch.object(ted, "_post_tedapi_wifi", return_value=None):
            ted._post_tedapi(b"req")
        connect.assert_not_called()
        assert ted.lan_fail_count == 3

    def test_claim_is_single_use_per_window(self):
        ted = _make_v1r_tedapi()
        assert ted._claim_lan_probe() is True
        assert ted._claim_lan_probe() is False
        # The claim pushes the window to where a failed probe would put it
        assert ted.lan_recover_after > time.time() + 900

    def test_no_claim_when_lan_healthy(self):
        ted = _make_v1r_tedapi()
        ted.lan_failed = False
        assert ted._claim_lan_probe() is False

    def test_backoff_schedule_unchanged(self):
        assert [TEDAPI._lan_backoff(n) for n in range(3, 10)] == \
            [480, 960, 1920, 3840, 7680, 7680, 7680]


class TestConnectV1rKeepsDin:
    """_connect_v1r doesn't expose DIN None to other threads mid-reconnect."""

    def test_din_visible_during_reconnect(self):
        ted = _make_v1r_tedapi()
        seen = []

        def login():
            seen.append(ted.din)   # what a concurrent getter would see now
            return True

        ted.v1r_transport.login.side_effect = login
        ted.v1r_transport.get_din.side_effect = lambda: seen.append(ted.din) or LEADER_DIN
        ted.v1r_transport.get_config_v1r.return_value = {"vin": "GW"}
        ted.wifi_session = None

        assert ted._connect_v1r() == LEADER_DIN
        assert seen == [LEADER_DIN, LEADER_DIN]
        assert ted.din == LEADER_DIN
        assert ted.lan_failed is False and ted.lan_fail_count == 0 and ted.lan_recover_after == 0

    @pytest.mark.parametrize("failure", ["login", "din", "exception"])
    def test_failed_reconnect_still_clears_din(self, failure):
        """connect() contract: DIN or None — a failed reconnect returns None and
        leaves no stale DIN behind, exactly as before."""
        ted = _make_v1r_tedapi()
        if failure == "login":
            ted.v1r_transport.login.return_value = False
        elif failure == "din":
            ted.v1r_transport.login.return_value = True
            ted.v1r_transport.get_din.return_value = None
        else:
            ted.v1r_transport.login.side_effect = OSError("No route to host")

        assert ted._connect_v1r() is None
        assert ted.din is None
        assert ted.lan_failed is True   # failover state untouched by a failed connect

    @pytest.mark.parametrize("failure", ["login", "din", "exception"])
    def test_keep_din_on_failed_reconnect(self, failure):
        """keep_din (probe with WiFi fallback): the failure still returns None,
        but the known DIN stays for the WiFi path."""
        ted = _make_v1r_tedapi()
        if failure == "login":
            ted.v1r_transport.login.return_value = False
        elif failure == "din":
            ted.v1r_transport.login.return_value = True
            ted.v1r_transport.get_din.return_value = None
        else:
            ted.v1r_transport.login.side_effect = OSError("No route to host")

        assert ted._connect_v1r(keep_din=True) is None
        assert ted.din == LEADER_DIN
        assert ted.lan_failed is True

    def test_initial_connect_sets_din(self):
        ted = _make_v1r_tedapi()
        ted.din = None
        ted.v1r_transport.login.return_value = True
        ted.v1r_transport.get_din.return_value = LEADER_DIN
        ted.v1r_transport.get_config_v1r.return_value = None
        ted.v1r_transport.pending_verification = False
        ted.v1r_transport.key_unknown = False
        ted.wifi_session = None
        assert ted._connect_v1r() == LEADER_DIN
        assert ted.din == LEADER_DIN

    def test_error_after_din_known_keeps_din(self):
        """Unchanged: an error after the DIN is known (e.g. in the key probe)
        is logged and the connect still succeeds."""
        ted = _make_v1r_tedapi()
        ted.v1r_transport.login.return_value = True
        ted.v1r_transport.get_din.return_value = LEADER_DIN
        ted.v1r_transport.get_config_v1r.side_effect = OSError("timeout")
        assert ted._connect_v1r() == LEADER_DIN
        assert ted.din == LEADER_DIN


class TestFailedProbeDin:
    """What a failed recovery probe leaves behind for the getters."""

    def _fail_probe(self, ted):
        ted.v1r_transport.login.return_value = False
        with patch.object(ted, "_post_tedapi_wifi", return_value=None):
            ted._post_tedapi(b"req")

    def test_wifi_fallback_keeps_din_and_backoff(self):
        """With a WiFi fallback, the failed probe keeps the DIN, so the next
        getter serves via WiFi instead of reconnecting LAN (and bailing with
        "Not Connected") on every poll."""
        ted = _make_v1r_tedapi()
        self._fail_probe(ted)
        assert ted.din == LEADER_DIN
        assert ted.lan_fail_count == 4 and ted.lan_recover_after > time.time() + 900

        ted.pwcache.clear()
        with patch.object(ted, "connect") as connect, \
                patch.object(ted, "_post_tedapi_wifi", return_value=None) as wifi:
            ted.get_status(force=True)
        connect.assert_not_called()
        wifi.assert_called_once()
        assert ted.v1r_transport.login.call_count == 1   # only the probe

    def test_no_wifi_fallback_clears_din(self):
        """Without a WiFi fallback, unchanged: the DIN is cleared so the next
        getter's connect() retries LAN — the only way data comes back sooner."""
        ted = _make_v1r_tedapi()
        ted.wifi_session = None
        self._fail_probe(ted)
        assert ted.din is None


class TestProbeWithColdFailover:
    """The probe's reconnect runs the real _connect_v1r, including the WiFi cold
    failover (#394): when the LAN is down but the WiFi host answers /tedapi/din."""

    def _wifi_din(self, ted, din=LEADER_DIN):
        r = MagicMock()
        r.status_code = 200
        r.content = din.encode()
        ted.wifi_session.get.return_value = r

    def test_concurrent_probe_via_cold_failover_runs_once(self):
        ted = _make_v1r_tedapi()
        self._wifi_din(ted)
        release = threading.Event()
        wifi_done = threading.Semaphore(0)

        def login():
            release.wait(WAIT)   # LAN login hangs until the others went WiFi
            return False

        def wifi(pb_bytes, url_suffix):
            wifi_done.release()
            return None

        ted.v1r_transport.login.side_effect = login
        before = time.time()
        with patch.object(ted, "_post_tedapi_wifi", side_effect=wifi):
            threads, errors = _run_threads(lambda: ted._post_tedapi(b"req"))
            for _ in range(THREADS - 1):
                assert wifi_done.acquire(timeout=WAIT)
            release.set()
            for t in threads:
                t.join(WAIT)
        assert not errors, errors
        assert ted.v1r_transport.login.call_count == 1
        assert ted.wifi_session.get.call_count == 1   # one WiFi DIN fetch
        # One failed probe = one backoff step, set by the cold failover
        assert ted.din == LEADER_DIN and ted.lan_failed is True
        assert ted.lan_fail_count == 4
        assert before + 960 <= ted.lan_recover_after <= time.time() + 960

    def test_both_down_keeps_din_with_wifi_configured(self):
        ted = _make_v1r_tedapi()   # WiFi /tedapi/din answers 503
        ted.v1r_transport.login.return_value = False
        with patch.object(ted, "_post_tedapi_wifi", return_value=None):
            ted._post_tedapi(b"req")
        assert ted.din == LEADER_DIN
        assert ted.lan_fail_count == 4 and ted.lan_recover_after > time.time() + 900

    def test_initial_connect_cold_failover_unchanged(self):
        ted = _make_v1r_tedapi()
        ted.din = None
        ted.lan_failed = False
        ted.lan_fail_count = 0
        self._wifi_din(ted)
        ted.v1r_transport.login.return_value = False
        assert ted._connect_v1r() == LEADER_DIN
        assert ted.lan_failed is True and ted.lan_fail_count == 3
        assert ted.lan_recover_after == pytest.approx(time.time() + 480, abs=5)


class TestLanFailureAccounting:
    """Concurrent LAN failures trip the failover once, on the regular schedule."""

    def test_concurrent_failures_trip_failover_once(self):
        ted = _make_v1r_tedapi()
        ted.lan_failed = False
        ted.lan_fail_count = 0
        in_flight = threading.Barrier(THREADS)

        def post_v1r(envelope, din):
            in_flight.wait(WAIT)   # all THREADS requests are on the wire at once
            return None

        ted.v1r_transport.post_v1r.side_effect = post_v1r
        before = time.time()
        threads, errors = _run_threads(lambda: ted._post_tedapi(b"req"))
        for t in threads:
            t.join(WAIT)
        assert not errors, errors
        # 3 failures trip the failover; the in-flight stragglers don't push the
        # first probe out further (was 60 * 2**THREADS s with THREADS stragglers)
        assert ted.lan_failed is True
        assert ted.lan_fail_count == 3
        assert before + 480 <= ted.lan_recover_after <= time.time() + 480

    def test_straggler_success_leaves_failover_counter(self):
        ted = _make_v1r_tedapi()
        ted.lan_failed = False
        ted.lan_fail_count = 2

        def post_v1r(envelope, din):
            # Another thread trips the failover while this request is in flight
            ted.lan_failed = True
            ted.lan_fail_count = 3
            return b"envelope"

        ted.v1r_transport.post_v1r.side_effect = post_v1r
        assert ted._post_tedapi(b"req") == b"envelope"
        assert ted.lan_fail_count == 3
        assert ted.lan_last_success > 0

    def test_sequential_failures_unchanged(self):
        """Single-threaded behavior is unchanged: 3 consecutive failures trip the
        failover with a 480s window; a success before that resets the count."""
        ted = _make_v1r_tedapi()
        ted.lan_failed = False
        ted.lan_fail_count = 0
        ted.v1r_transport.post_v1r.return_value = None
        ted._post_tedapi(b"req")
        ted._post_tedapi(b"req")
        assert ted.lan_fail_count == 2 and ted.lan_failed is False
        ted.v1r_transport.post_v1r.return_value = b"envelope"
        ted._post_tedapi(b"req")
        assert ted.lan_fail_count == 0
        ted.v1r_transport.post_v1r.return_value = None
        for _ in range(3):
            ted._post_tedapi(b"req")
        assert ted.lan_failed is True and ted.lan_fail_count == 3
        assert ted.lan_recover_after == pytest.approx(time.time() + 480, abs=5)
