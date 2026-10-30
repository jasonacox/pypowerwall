"""The final "Unable to connect" error names why the configured mode failed (#373).

With failover on, connect() goes on to FleetAPI and Cloud, which fail for their own
unrelated reasons; the configured mode's reason (a missing RSA key, the v1r password
check) used to be visible only in an earlier fallback warning."""
import logging
from unittest.mock import MagicMock, patch

import pytest

import pypowerwall

KEY_MISSING = FileNotFoundError("RSA private key not found at /config/missing.pem.")


@pytest.fixture
def clients():
    with patch("pypowerwall.PyPowerwallTEDAPI") as ted, \
            patch("pypowerwall.PyPowerwallLocal") as local, \
            patch("pypowerwall.PyPowerwallFleetAPI") as fleet, \
            patch("pypowerwall.PyPowerwallCloud") as cloud:
        for cls in (ted, local, fleet, cloud):
            cls.return_value = MagicMock()
        ted.side_effect = KEY_MISSING
        fleet.side_effect = RuntimeError("No sites found for nobody@nowhere.com")
        cloud.side_effect = RuntimeError("Missing auth file .pypowerwall.auth")
        yield {"tedapi": ted, "fleet": fleet, "cloud": cloud}


def _v1r(**kwargs):
    return pypowerwall.Powerwall(host="10.42.1.40", gw_pwd="ABCDELNDYT",
                                 rsa_key_path="/config/missing.pem", **kwargs)


def _final_error(caplog):
    (record,) = [r for r in caplog.records
                 if r.levelno == logging.ERROR and r.getMessage().startswith("Unable to connect to Powerwall")]
    return record.getMessage()


@pytest.mark.parametrize("failover", [True, False])
def test_final_error_names_the_configured_mode_failure(clients, caplog, failover):
    with caplog.at_level(logging.WARNING, logger="pypowerwall"):
        pw = _v1r(failover=failover)
    assert pw.client is None
    message = _final_error(caplog)
    assert "(local mode: RSA private key not found at /config/missing.pem.)" in message
    assert "nobody@nowhere.com" not in message
    assert "auth file" not in message


def test_v1r_without_password_is_named(clients, caplog):
    with caplog.at_level(logging.WARNING, logger="pypowerwall"):
        pypowerwall.Powerwall(host="10.42.1.40", rsa_key_path="/config/key.pem", cloudmode=False)
    assert "(local mode: v1r mode requires password or gw_pwd)" in _final_error(caplog)
    clients["tedapi"].assert_not_called()


def test_reconnect_reports_its_own_failure(clients, caplog):
    pw = _v1r(failover=False)
    clients["tedapi"].side_effect = ConnectionError("LAN down")
    assert pw.connect() is False
    assert pw._connect_error == "local mode: LAN down"


def test_no_error_after_a_successful_connect(clients, caplog):
    clients["tedapi"].side_effect = None
    with caplog.at_level(logging.WARNING, logger="pypowerwall"):
        pw = _v1r()
    assert pw.client is clients["tedapi"].return_value
    assert pw._connect_error is None
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]
