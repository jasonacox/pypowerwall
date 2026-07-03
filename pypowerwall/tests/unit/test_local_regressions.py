"""Regression tests for local backend robustness:
- poll() 404 handler compared `version >= 23440` which raised TypeError when
  the firmware version could not be determined (version() returned None)
"""
from unittest.mock import MagicMock, patch

from pypowerwall.local.pypowerwall_local import PyPowerwallLocal


def _make_client():
    client = PyPowerwallLocal(host='127.0.0.1', password='password', email='test@example.com',
                              timezone='UTC', timeout=5, pwcacheexpire=5, poolmaxsize=0,
                              authmode='cookie', cachefile='unused', gw_pw=None)
    client.session = MagicMock()
    client.auth = {'AuthCookie': 'cookie', 'UserRecord': 'record'}
    return client


def test_vitals_404_with_unknown_version():
    """404 on /api/devices/vitals must not TypeError when version() is None."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 404
    client.session.get.return_value = response

    with patch.object(client, 'version', return_value=None):
        result = client.poll('/api/devices/vitals')  # used to raise TypeError

    assert result is None
    # Firmware version unknown - vitals API must not be permanently disabled
    assert client.vitals_api is True


def test_vitals_404_with_new_firmware_disables_vitals():
    """Sanity check: the >= 23440 gate still works when a version is known."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 404
    client.session.get.return_value = response

    with patch.object(client, 'version', return_value=23440):
        result = client.poll('/api/devices/vitals')

    assert result is None
    assert client.vitals_api is False
