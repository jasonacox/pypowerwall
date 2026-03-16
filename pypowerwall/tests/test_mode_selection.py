"""Tests for mode selection and password auto-derivation logic."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_clients():
    """Mock all client classes to prevent network calls during mode selection tests."""
    with patch('pypowerwall.PyPowerwallTEDAPI') as mock_tedapi, \
         patch('pypowerwall.PyPowerwallLocal') as mock_local, \
         patch('pypowerwall.PyPowerwallFleetAPI') as mock_fleet, \
         patch('pypowerwall.PyPowerwallCloud') as mock_cloud:
        # Each mock client needs authenticate() and a tedapi attribute
        for mock_cls in (mock_tedapi, mock_local, mock_fleet, mock_cloud):
            instance = MagicMock()
            instance.authenticate.return_value = True
            instance.tedapi = MagicMock()
            mock_cls.return_value = instance
        yield {
            'tedapi': mock_tedapi,
            'local': mock_local,
            'fleet': mock_fleet,
            'cloud': mock_cloud,
        }


class TestV1rPasswordDerivation:
    """Test that v1r mode auto-derives password from gw_pwd."""

    def test_v1r_with_gw_pwd_only(self, mock_clients):
        """v1r mode should auto-derive last 5 chars from gw_pwd when password is empty."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="10.42.1.56",
            password="",
            gw_pwd="ABCDELNDYT",
            rsa_key_path="/tmp/fake_key.pem",
        )
        assert pw.tedapi_mode == "v1r"
        # Verify PyPowerwallTEDAPI was called with derived password (last 5 chars)
        mock_clients['tedapi'].assert_called_once()
        call_kwargs = mock_clients['tedapi'].call_args
        assert call_kwargs.kwargs.get('password') == "LNDYT"
        assert call_kwargs.kwargs.get('v1r') is True

    def test_v1r_with_explicit_password(self, mock_clients):
        """v1r mode should use explicit password when provided."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="10.42.1.56",
            password="MYPASS",
            rsa_key_path="/tmp/fake_key.pem",
        )
        assert pw.tedapi_mode == "v1r"
        call_kwargs = mock_clients['tedapi'].call_args
        assert call_kwargs.kwargs.get('password') == "MYPASS"

    def test_v1r_with_both_passwords(self, mock_clients):
        """v1r mode should prefer explicit password over gw_pwd derivation."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="10.42.1.56",
            password="EXPLICIT",
            gw_pwd="ABCDELNDYT",
            rsa_key_path="/tmp/fake_key.pem",
        )
        assert pw.tedapi_mode == "v1r"
        call_kwargs = mock_clients['tedapi'].call_args
        assert call_kwargs.kwargs.get('password') == "EXPLICIT"

    def test_v1r_no_password_no_gw_pwd_raises(self, mock_clients):
        """v1r mode with rsa_key_path but no passwords should raise ValueError."""
        import pypowerwall
        # The ValueError is caught by the connect() exception handler,
        # which falls through to fleetapi mode. The Powerwall object is created
        # but tedapi_mode should not be "v1r".
        pw = pypowerwall.Powerwall(
            host="10.42.1.56",
            password="",
            rsa_key_path="/tmp/fake_key.pem",
        )
        assert pw.tedapi_mode != "v1r"


class TestMode4FullTEDAPI:
    """Test mode 4 full TEDAPI selection (gw_pwd only, no customer password)."""

    def test_full_tedapi_with_gw_pwd_only(self, mock_clients):
        """Full TEDAPI mode when only gw_pwd is set (no password)."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="",
            gw_pwd="ABCDELNDYT",
        )
        assert pw.tedapi_mode == "full"
        mock_clients['tedapi'].assert_called_once()
        # First positional arg should be the full gw_pwd
        call_args = mock_clients['tedapi'].call_args
        assert call_args.args[0] == "ABCDELNDYT"

    def test_full_tedapi_does_not_use_local_client(self, mock_clients):
        """Full TEDAPI should use PyPowerwallTEDAPI, not PyPowerwallLocal."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="",
            gw_pwd="ABCDELNDYT",
        )
        mock_clients['local'].assert_not_called()
        mock_clients['tedapi'].assert_called_once()

    def test_full_tedapi_passes_gw_pwd_not_password(self, mock_clients):
        """Full TEDAPI should pass gw_pwd as first arg, not use password kwarg."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="",
            gw_pwd="FULLPWDHERE",
        )
        call_args = mock_clients['tedapi'].call_args
        # gw_pwd is first positional arg
        assert call_args.args[0] == "FULLPWDHERE"
        # v1r should NOT be set
        assert call_args.kwargs.get('v1r') is None or call_args.kwargs.get('v1r') is False

    def test_full_tedapi_with_port_443(self, mock_clients):
        """Full TEDAPI should work with explicit :443 on gateway IP."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1:443",
            password="",
            gw_pwd="ABCDELNDYT",
        )
        # Should still select full TEDAPI (not hybrid)
        assert pw.tedapi_mode == "full"


class TestMode4HybridTEDAPI:
    """Test mode 4 hybrid selection (password + gw_pwd, no rsa_key_path)."""

    def test_hybrid_with_both_passwords(self, mock_clients):
        """Hybrid mode when both password and gw_pwd are set (no rsa_key_path)."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="LNDYT",
            gw_pwd="ABCDELNDYT",
        )
        assert pw.tedapi_mode in ("hybrid", "off")
        mock_clients['local'].assert_called_once()

    def test_hybrid_uses_local_client(self, mock_clients):
        """Hybrid mode should use PyPowerwallLocal (not PyPowerwallTEDAPI directly)."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="LNDYT",
            gw_pwd="ABCDELNDYT",
        )
        mock_clients['local'].assert_called_once()
        # PyPowerwallTEDAPI should NOT be called directly (Local handles TEDAPI internally)
        mock_clients['tedapi'].assert_not_called()

    def test_hybrid_passes_both_passwords_to_local(self, mock_clients):
        """Hybrid mode should pass password and gw_pwd to PyPowerwallLocal."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="LNDYT",
            gw_pwd="ABCDELNDYT",
        )
        call_args = mock_clients['local'].call_args
        # PyPowerwallLocal(host, password, email, timezone, timeout, ...)
        assert call_args.args[0] == "192.168.91.1"  # host
        assert call_args.args[1] == "LNDYT"          # password
        # gw_pwd is last positional arg
        assert call_args.args[-1] == "ABCDELNDYT"

    def test_hybrid_without_gw_pwd_is_local_only(self, mock_clients):
        """Password only (no gw_pwd) should still use Local client but no TEDAPI."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="LNDYT",
        )
        mock_clients['local'].assert_called_once()
        call_args = mock_clients['local'].call_args
        # gw_pwd should be None
        assert call_args.args[-1] is None

    def test_rsa_key_overrides_hybrid(self, mock_clients):
        """With rsa_key_path set, v1r takes priority over hybrid even with both passwords."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="LNDYT",
            gw_pwd="ABCDELNDYT",
            rsa_key_path="/tmp/fake_key.pem",
        )
        assert pw.tedapi_mode == "v1r"
        mock_clients['tedapi'].assert_called_once()
        mock_clients['local'].assert_not_called()


class TestMode1Selection:
    """Test that mode 1 (local API only) selection is unchanged."""

    def test_local_api_password_only(self, mock_clients):
        """Local API mode when only password is set."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="10.42.1.56",
            password="LNDYT",
        )
        assert pw.tedapi_mode in ("hybrid", "off")
        mock_clients['local'].assert_called_once()
