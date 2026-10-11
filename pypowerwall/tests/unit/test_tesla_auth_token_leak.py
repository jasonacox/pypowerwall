"""Interactive Tesla login must not leak tokens to stdout (#415).

`login()` (the `setup` path, show_token_page=False) saves tokens itself, so
printing them to the console only hands working Tesla credentials to anything
that captures stdout — terminal scrollback, shell logs, CI logs, screen
shares, pasted bug reports. The `authtoken` command (show_token_page=True) is
the one flow where showing the tokens is the point; that stays.

All tests are mocked — no sockets (blocked by conftest), fake token strings
only, and the pywebview backend is driven through a stubbed `webview` module.
"""
import json
import re
import sys
import threading
import time
from unittest.mock import patch

import pytest

from pypowerwall import tesla_auth as ta
from pypowerwall import v1r_register as reg

# Clearly fake tokens — never real credential material.
FAKE_RT = "FAKE-REFRESH-" + "r" * 40
FAKE_AT = "FAKE-ACCESS-" + "a" * 40
FAKE_TOKEN_DATA = {
    "refresh_token": FAKE_RT,
    "access_token": FAKE_AT,
    "token_type": "Bearer",
    "expires_in": 28800,
}


def _assert_no_secret_slice(text, token, min_len=8):
    """Assert no substring of `token` with >= min_len chars appears in text."""
    for i in range(len(token) - min_len + 1):
        assert token[i:i + min_len] not in text, (
            f"stdout leaks >= {min_len}-char slice of token at offset {i}"
        )


class _FakeWindow:
    def __init__(self):
        self.loaded = []
        self.destroyed = False

    def load_html(self, html):
        self.loaded.append(html)

    def destroy(self):
        self.destroyed = True


class _FakeWebview:
    """Stands in for the `webview` module inside _local_login_pywebview."""

    def __init__(self):
        self.window = _FakeWindow()

    def create_window(self, *args, **kwargs):
        return self.window

    def start(self):
        # Give the poll_token thread time to run the (mocked) exchange
        time.sleep(0.5)


def _drive_pywebview_login(show_token_page, monkeypatch, capsys):
    """Drive _local_login_pywebview to completion with everything mocked.

    Sets the auth code synchronously (as the navigation monkey-patch would),
    mocks the exchange, and stubs the webview module. Returns
    (return_value, captured_stdout).
    """
    fake_webview = _FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr(ta, "_build_auth_url",
                        lambda region: ("https://auth.example/login", "verifier", "state123"))
    monkeypatch.setattr(ta, "_patch_pywebview_navigation",
                        lambda result, state: result.__setitem__("code", "fake-auth-code"))
    monkeypatch.setattr(ta, "_exchange_code",
                        lambda code, verifier, region: dict(FAKE_TOKEN_DATA))

    result = ta._local_login_pywebview(region="us",
                                       show_token_page=show_token_page)
    captured = capsys.readouterr()
    return result, captured.out


class TestLoginPathNeverPrintsTokens:
    """login() / setup path (show_token_page=False) — the security fix."""

    def test_pywebview_login_prints_no_token_slices(self, monkeypatch, capsys):
        # FAILS on pre-fix code: the pywebview backend printed the full RT/AT
        # unconditionally after the exchange.
        _, out = _drive_pywebview_login(False, monkeypatch, capsys)
        _assert_no_secret_slice(out, FAKE_RT)
        _assert_no_secret_slice(out, FAKE_AT)
        # A non-secret confirmation is fine (and expected)
        assert "Token captured" in out

    def test_pywebview_login_returns_populated_token_data(self, monkeypatch, capsys):
        # FAILS on pre-fix code: the pywebview backend always returned {} as
        # token_data — the empty-token-dict bug reported on Windows (#409).
        result, _ = _drive_pywebview_login(False, monkeypatch, capsys)
        rt, email, token_data = result
        assert rt == FAKE_RT
        assert token_data.get("access_token") == FAKE_AT
        assert token_data.get("refresh_token") == FAKE_RT

    def test_macos_backend_token_prints_are_guarded(self):
        # FAILS on pre-fix code: the macOS WKWebView backend printed the full
        # RT/AT unconditionally (no show_token_page guard).
        # The macOS backend can't be driven with mocks here (needs PyObjC +
        # a real AppKit event loop), so this is a source-level tripwire: the
        # token-printing helper must only ever be called under
        # `if show_token_page:`.
        src = open(ta.__file__, encoding="utf-8").read()
        lines = src.splitlines()
        call_sites = [i for i, ln in enumerate(lines)
                      if "_print_tokens_for_copy(token" in ln
                      and not ln.strip().startswith("def ")]
        assert call_sites, "no guarded token-print call sites found"
        for i in call_sites:
            # Walk back to the nearest non-comment, non-blank line: it must be
            # the show_token_page guard.
            j = i - 1
            while j >= 0 and (not lines[j].strip()
                              or lines[j].strip().startswith("#")):
                j -= 1
            assert re.match(r"^\s*if show_token_page:", lines[j]), (
                f"token print at line {i + 1} is not guarded by show_token_page"
            )
        # And the raw token must never be printed anywhere except the helper
        in_helper = False
        helper_depth = None
        for ln in lines:
            if ln.startswith("def _print_tokens_for_copy"):
                in_helper = True
                continue
            if in_helper and ln and not ln[0].isspace():
                in_helper = False
            if not in_helper and "print(token)" in ln:
                pytest.fail(f"unguarded `print(token)` outside helper: {ln.strip()}")


class TestAuthtokenPathStillPrintsTokens:
    """authtoken command (show_token_page=True) — behavior unchanged."""

    def test_pywebview_authtoken_prints_both_tokens(self, monkeypatch, capsys):
        out = None
        _, out = _drive_pywebview_login(True, monkeypatch, capsys)
        assert FAKE_RT in out
        assert FAKE_AT in out


class TestV1rRegisterExchange:
    """v1r_register step2 must print no part of either token."""

    def _run_exchange(self, tmp_path, monkeypatch, capsys):
        tokens_file = str(tmp_path / "fleet_tokens.json")

        class FakeResponse:
            def read(self):
                return json.dumps(FAKE_TOKEN_DATA).encode()

        monkeypatch.setattr(reg.urllib.request, "urlopen",
                            lambda req, context=None, timeout=None: FakeResponse())
        access = reg.step2_exchange_token(
            "fake-code", "cid", "csecret", "https://redirect.example",
            "https://fleet-api.example", tokens_file=tokens_file)
        return access, tokens_file, capsys.readouterr().out

    def test_exchange_prints_no_token_characters(self, tmp_path, monkeypatch, capsys):
        # FAILS on pre-fix code: step2 printed the first 30 chars of the
        # access and refresh tokens.
        access, tokens_file, out = self._run_exchange(tmp_path, monkeypatch, capsys)
        assert access == FAKE_AT
        _assert_no_secret_slice(out, FAKE_RT)
        _assert_no_secret_slice(out, FAKE_AT)
        # Confirmation mentions expiry and the save location instead
        assert "expires in 28800s" in out
        assert tokens_file in out
        # File still written with the full tokens, same return value
        saved = json.load(open(tokens_file))
        assert saved["refresh_token"] == FAKE_RT
        assert "obtained_at" in saved
