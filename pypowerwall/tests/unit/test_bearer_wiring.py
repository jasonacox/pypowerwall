"""Unit tests for the bearer wiring above the TEDAPI transport.

The transport itself is covered in test_bearer_auth.py; this file covers the
layers a user actually configures:

  1. PyPowerwallTEDAPI — forwards auth_mode/timezone to TEDAPI, and
     api_logout()/api_login_basic(), which stopped being mock-data stubs and
     now drive real session teardown/login.
  2. Powerwall — the tedapi_auth_mode kwarg and its coercion.
  3. The CLI --auth-mode flag.
"""
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi.auth_mode import AuthMode
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI


# ---------------------------------------------------------------------------
# PyPowerwallTEDAPI backend
# ---------------------------------------------------------------------------

def make_backend(auth_mode="bearer", **kwargs):
    """Build the TEDAPI backend with the transport class mocked out."""
    with patch("pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI") as mock_cls:
        backend = PyPowerwallTEDAPI(gw_pwd="password", auth_mode=auth_mode, **kwargs)
    backend._mock_tedapi_class = mock_cls
    return backend


class TestBackendConstruction:

    @pytest.mark.parametrize("mode", ["basic", "bearer"])
    def test_auth_mode_forwarded_to_transport(self, mode):
        backend = make_backend(mode, timezone="Europe/Berlin")
        kwargs = backend._mock_tedapi_class.call_args[1]
        assert kwargs["auth_mode"] == mode
        assert kwargs["timezone"] == "Europe/Berlin"

    def test_auth_mode_is_coerced(self):
        backend = make_backend("BEARER")
        assert backend.auth_mode is AuthMode.BEARER

    def test_invalid_auth_mode_raises(self):
        with patch("pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI"):
            with pytest.raises(ValueError, match="Invalid auth_mode"):
                PyPowerwallTEDAPI(gw_pwd="password", auth_mode="nope")

    def test_presence_is_rejected(self):
        """presence mode was removed; it must not silently degrade to another
        transport at the facade layer either."""
        with patch("pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI"):
            with pytest.raises(ValueError, match="Invalid auth_mode"):
                PyPowerwallTEDAPI(gw_pwd="password", auth_mode="presence")

    def test_defaults_to_basic(self):
        with patch("pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI"):
            backend = PyPowerwallTEDAPI(gw_pwd="password")
        assert backend.auth_mode is AuthMode.BASIC


class TestBackendLogout:
    """api_logout() was a mock-data stub; it now tears down the real session."""

    def test_bearer_logout_invalidates_token(self):
        backend = make_backend("bearer")
        assert backend.api_logout() == {"status": "ok"}
        backend.tedapi._bearer_logout.assert_called_once()

    def test_basic_logout_is_noop(self):
        """Basic auth has no server-side session — logging out must not call
        the bearer teardown, and must keep returning the documented shape."""
        backend = make_backend("basic")
        assert backend.api_logout() == {"status": "ok"}
        backend.tedapi._bearer_logout.assert_not_called()

    def test_logout_without_transport_is_safe(self):
        backend = make_backend("bearer")
        backend.tedapi = None
        assert backend.api_logout() == {"status": "ok"}


class TestBackendLoginBasic:
    """api_login_basic() delegates to the bearer login in bearer mode only."""

    def test_bearer_login_performs_login_without_echoing_token(self):
        """The login runs, but the token must never appear in the response.

        This endpoint is served by the proxy, which is routinely exposed on the
        LAN, so echoing the installer bearer token would hand a credential to
        anything that can reach it. The token's only home is the TEDAPI session.
        The shape also matches the cloud and fleetapi backends, which both
        return a bare {"status": "ok"}.
        """
        backend = make_backend("bearer")
        backend.tedapi.token = "TOKEN123"

        result = backend.api_login_basic()

        backend.tedapi._bearer_login.assert_called_once()
        assert result == {"status": "ok"}
        assert "TOKEN123" not in str(result), "bearer token must not leak to callers"

    def test_bearer_login_failure_returns_error_shape(self):
        """Failure must return a dict, not raise — the proxy maps these to HTTP."""
        backend = make_backend("bearer")
        backend.tedapi._bearer_login.side_effect = ValueError("bad password")

        result = backend.api_login_basic()

        assert result["status"] == "error"
        assert "bad password" in result["message"]

    def test_basic_login_is_noop(self):
        backend = make_backend("basic")
        assert backend.api_login_basic() == {"status": "ok"}
        backend.tedapi._bearer_login.assert_not_called()


# ---------------------------------------------------------------------------
# Powerwall facade
# ---------------------------------------------------------------------------

class TestPowerwallFacade:

    @pytest.fixture
    def mock_backends(self):
        with patch("pypowerwall.PyPowerwallTEDAPI") as tedapi, \
                patch("pypowerwall.PyPowerwallLocal"), \
                patch("pypowerwall.PyPowerwallFleetAPI") as fleet, \
                patch("pypowerwall.PyPowerwallCloud") as cloud:
            for cls in (tedapi, fleet, cloud):
                inst = MagicMock()
                inst.authenticate.return_value = True
                inst.tedapi = MagicMock()
                cls.return_value = inst
            yield {"tedapi": tedapi, "fleet": fleet, "cloud": cloud}

    def test_auth_mode_forwarded_to_backend(self, mock_backends):
        import pypowerwall
        pypowerwall.Powerwall(host="10.0.0.1", gw_pwd="ABCDE12345",
                              tedapi_auth_mode="bearer", timezone="Europe/Berlin")

        kwargs = mock_backends["tedapi"].call_args[1]
        assert kwargs["auth_mode"] is AuthMode.BEARER
        assert kwargs["timezone"] == "Europe/Berlin"

    def test_auth_mode_is_coerced_on_the_facade(self, mock_backends):
        import pypowerwall
        pw = pypowerwall.Powerwall(host="10.0.0.1", gw_pwd="ABCDE12345",
                                   tedapi_auth_mode="BEARER")
        assert pw.tedapi_auth_mode is AuthMode.BEARER

    def test_invalid_auth_mode_raises(self, mock_backends):
        import pypowerwall
        with pytest.raises(ValueError, match="Invalid auth_mode"):
            pypowerwall.Powerwall(host="10.0.0.1", gw_pwd="ABCDE12345",
                                  tedapi_auth_mode="bogus")

    def test_presence_is_rejected(self, mock_backends):
        import pypowerwall
        with pytest.raises(ValueError, match="Invalid auth_mode"):
            pypowerwall.Powerwall(host="10.0.0.1", gw_pwd="ABCDE12345",
                                  tedapi_auth_mode="presence")

    def test_defaults_to_basic(self, mock_backends):
        import pypowerwall
        pw = pypowerwall.Powerwall(host="10.0.0.1", gw_pwd="ABCDE12345")
        assert pw.tedapi_auth_mode is AuthMode.BASIC

    def test_local_errors_still_fall_back(self, mock_backends):
        """Local-mode failures must still try the next mode."""
        import pypowerwall
        mock_backends["tedapi"].side_effect = ConnectionError("no route")

        pypowerwall.Powerwall(host="10.0.0.1", gw_pwd="ABCDE12345")

        assert mock_backends["fleet"].called or mock_backends["cloud"].called, \
            "ordinary local failures must still try the next mode"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCliAuthMode:

    def _run(self, argv, mock_ted, tmp_path, monkeypatch):
        from pypowerwall.tedapi.__main__ import run_tedapi_test
        monkeypatch.chdir(tmp_path)
        with patch("requests.get") as mock_get, \
                patch("pypowerwall.tedapi.TEDAPI", return_value=mock_ted) as cls:
            mock_get.return_value.status_code = 200
            run_tedapi_test(argv)
        return cls

    @pytest.fixture
    def mock_ted(self):
        ted = MagicMock()
        ted.din = "DIN123"
        ted.get_config.return_value = {}
        ted.get_status.return_value = {}
        return ted

    def test_auth_mode_forwarded(self, mock_ted, tmp_path, monkeypatch):
        cls = self._run(["-gw_pwd", "ABCDE12345", "--auth-mode", "bearer"],
                        mock_ted, tmp_path, monkeypatch)
        assert cls.call_args[1]["auth_mode"] == "bearer"

    def test_default_auth_mode_is_basic(self, mock_ted, tmp_path, monkeypatch):
        cls = self._run(["-gw_pwd", "ABCDE12345"], mock_ted, tmp_path, monkeypatch)
        assert cls.call_args[1]["auth_mode"] == "basic"

    def test_invalid_auth_mode_rejected_by_argparse(self, mock_ted, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            self._run(["-gw_pwd", "ABCDE12345", "--auth-mode", "bogus"],
                      mock_ted, tmp_path, monkeypatch)

    def test_presence_rejected_by_argparse(self, mock_ted, tmp_path, monkeypatch):
        """--auth-mode presence must no longer be an accepted choice."""
        with pytest.raises(SystemExit):
            self._run(["-gw_pwd", "ABCDE12345", "--auth-mode", "presence"],
                      mock_ted, tmp_path, monkeypatch)

    def test_register_presence_flag_is_gone(self, mock_ted, tmp_path, monkeypatch):
        with pytest.raises(SystemExit):
            self._run(["-gw_pwd", "ABCDE12345", "--register-presence"],
                      mock_ted, tmp_path, monkeypatch)
