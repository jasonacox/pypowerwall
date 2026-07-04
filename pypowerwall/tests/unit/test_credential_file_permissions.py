"""Credential files must be created with 0o600 (owner-only) permissions.

Covers the P1 fix replacing plain open() (default umask, world-readable) and
chmod-after-write (race window) with os.open(..., 0o600) at creation time for
files that hold tokens/secrets: .pypowerwall.fleetapi and the .powerwall
local auth cache.
"""
import os
from unittest.mock import MagicMock

from pypowerwall.fleetapi.fleetapi import FleetAPI
from pypowerwall.local.pypowerwall_local import PyPowerwallLocal


def _mode(path):
    return os.stat(path).st_mode & 0o777


def test_fleetapi_save_config_creates_0600(tmp_path):
    configfile = tmp_path / '.pypowerwall.fleetapi'
    # Nonexistent config file - load_config() is a no-op, no network involved
    fleet = FleetAPI(configfile=str(configfile))
    fleet.CLIENT_ID = 'client-id'
    fleet.CLIENT_SECRET = 'client-secret'
    fleet.access_token = 'access'
    fleet.refresh_token = 'refresh'
    fleet.site_id = '1234'

    fleet.save_config()

    assert configfile.exists()
    assert _mode(configfile) == 0o600


def test_local_auth_cache_creates_0600(tmp_path):
    cachefile = tmp_path / '.powerwall'
    pw = PyPowerwallLocal(host='127.0.0.1', password='password', email='me@example.com',
                          timezone='UTC', timeout=5, pwcacheexpire=5, poolmaxsize=0,
                          authmode='cookie', cachefile=str(cachefile))
    # Mock the login response so _get_session() writes the auth cache
    # without any network access
    response = MagicMock()
    response.status_code = 200
    response.cookies = {'AuthCookie': 'auth-cookie', 'UserRecord': 'user-record'}
    pw.session = MagicMock()
    pw.session.post.return_value = response

    pw._get_session()  # pylint: disable=protected-access

    assert cachefile.exists()
    assert _mode(cachefile) == 0o600
