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


class TestMode4Selection:
    """Test that mode 4 (WiFi TEDAPI) selection is unchanged."""

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

    def test_hybrid_tedapi_with_both_passwords(self, mock_clients):
        """Hybrid mode when both password and gw_pwd are set (no rsa_key_path)."""
        import pypowerwall
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            password="LNDYT",
            gw_pwd="ABCDELNDYT",
        )
        assert pw.tedapi_mode in ("hybrid", "off")
        mock_clients['local'].assert_called_once()


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
