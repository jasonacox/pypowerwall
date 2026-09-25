"""v1r key registration: state handling, post-proof polling window, and
re-registering the same key (#354, PR #383 review)."""
import os
from unittest.mock import patch

import pytest

from pypowerwall import v1r_register as reg
from pypowerwall.tedapi.tedapi_v1r import REGISTER_KEY_FILENAME, reregister_hint


class FakeClock:
    """Stands in for the ``time`` module inside v1r_register: sleep advances now."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _poll(states, **kwargs):
    """Run _poll_key_state against a scripted sequence of key states.
    Returns (result, number_of_polls, elapsed_seconds)."""
    clock = FakeClock()
    start = clock.now
    seq = iter(states)
    with patch.object(reg, 'time', clock), \
         patch.object(reg, 'api_call', return_value=(200, {})) as api, \
         patch.object(reg, '_check_key_state', side_effect=lambda resp, pubkey_der=None: next(seq)):
        result = reg._poll_key_state("tok", 1, "https://x", **kwargs)
    return result, api.call_count, clock.now - start


# --- _poll_key_state -------------------------------------------------------------

class TestPollKeyState:

    def test_deadline_poll_catches_the_documented_62s_transition(self):
        # VERIFIED arrives on the 8th poll (70 s in) - the old 6-attempt, ~25 s
        # post-proof poll would have reported failure
        states = [1] * 7 + [3]
        result, polls, elapsed = _poll(states, delay=10, timeout=reg.POST_PROOF_POLL_SECONDS)
        assert (result, polls, elapsed) == (3, 8, 70)

    def test_deadline_poll_stops_at_the_deadline(self):
        result, polls, elapsed = _poll([1] * 50, delay=10, timeout=120)
        assert result == 1
        assert elapsed <= 120
        assert polls == 13   # t = 0, 10, ..., 120

    def test_timeout_state_is_terminal(self):
        result, polls, _ = _poll([1, 2, 3], delay=10, timeout=120)
        assert (result, polls) == (2, 2)

    def test_attempt_mode_unchanged(self):
        result, polls, elapsed = _poll([1, 1, 1, 1], attempts=3, delay=5)
        assert (result, polls, elapsed) == (1, 3, 10)

    def test_unparseable_response_is_not_terminal(self):
        result, polls, _ = _poll([None, None, 3], attempts=3, delay=5)
        assert (result, polls) == (3, 3)


# --- step4_register_key -------------------------------------------------------------

class TestStep4:

    def _run(self, poll_results, reg_state=1):
        polls = iter(poll_results)
        with patch.object(reg, 'api_call', return_value=(200, {})), \
             patch.object(reg, '_check_key_state', return_value=reg_state), \
             patch.object(reg, '_poll_key_state', side_effect=lambda *a, **k: next(polls)) as poll, \
             patch('builtins.input') as prompt:
            reg.step4_register_key("tok", 1, b"der", "https://x", private_key_file="/keys/tedapi_rsa_private.pem")
        return poll, prompt

    def test_timed_out_key_skips_the_physical_proof_prompt(self, capsys):
        poll, prompt = self._run([2])
        prompt.assert_not_called()
        assert poll.call_count == 1
        out = capsys.readouterr().out
        assert "STEP 5" not in out
        assert "python -m pypowerwall register -authpath /keys" in out

    def test_pending_key_prompts_then_polls_with_the_deadline(self):
        poll, prompt = self._run([1, 3])
        prompt.assert_called_once()
        _, post_proof_kwargs = poll.call_args_list[1]
        assert post_proof_kwargs["timeout"] == reg.POST_PROOF_POLL_SECONDS
        assert post_proof_kwargs["delay"] == reg.POST_PROOF_POLL_DELAY

    def test_cloud_auto_verification_needs_no_prompt(self):
        poll, prompt = self._run([], reg_state=3)
        prompt.assert_not_called()
        poll.assert_not_called()


# --- re-registering the same key -------------------------------------------------------

class TestReregisterHint:

    def test_points_register_at_the_configured_key_directory(self, tmp_path):
        key = tmp_path / REGISTER_KEY_FILENAME
        assert reregister_hint(str(key)) == f"python -m pypowerwall register -authpath {tmp_path}"

    def test_relative_key_path_becomes_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert reregister_hint(REGISTER_KEY_FILENAME).endswith(f"-authpath {os.getcwd()}")

    def test_directory_with_spaces_is_quoted(self):
        assert "-authpath '/my keys'" in reregister_hint(f"/my keys/{REGISTER_KEY_FILENAME}")

    def test_non_default_filename_says_to_rename(self):
        hint = reregister_hint("/keys/custom.pem")
        assert hint.startswith("python -m pypowerwall register -authpath /keys")
        assert "rename custom.pem" in hint

    @pytest.mark.parametrize("path", [None, "", 123])
    def test_unknown_path_gives_the_bare_command(self, path):
        assert reregister_hint(path) == "python -m pypowerwall register"


def test_cli_register_honors_authpath(tmp_path):
    from pypowerwall.__main__ import main

    with patch('sys.argv', ['pypowerwall', 'register', '-authpath', str(tmp_path)]), \
         patch('pypowerwall.v1r_register.main') as register_main:
        main()
    register_main.assert_called_once_with(authpath=str(tmp_path))
