"""Regression tests: a failed re-login inside poll()/post() must not raise.

When a cached local session expires (HTTP 401/403), poll() and post() call
_get_session() to log in again. _get_session() raises LoginError (wrong or
changed gateway password) or ConnectionError (gateway unreachable) - correct
for authenticate(), which drives mode fallback in connect(), but those
exceptions escaped poll()/post() and every facade read built on them
(level(), power(), ...), breaking the "read methods return None" contract.
"""
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.local.exceptions import LoginError
from pypowerwall.local.pypowerwall_local import PyPowerwallLocal


def _make_client():
    client = PyPowerwallLocal(host='127.0.0.1', password='password', email='test@example.com',
                              timezone='UTC', timeout=5, pwcacheexpire=5, poolmaxsize=0,
                              authmode='cookie', cachefile='unused', gw_pw=None)
    client.session = MagicMock()
    client.auth = {'AuthCookie': 'cookie', 'UserRecord': 'record'}
    return client


def _status(code):
    response = MagicMock()
    response.status_code = code
    return response


def _login_rejected():
    """The gateway's answer to a login with a wrong password: 401, no cookies."""
    response = _status(401)
    response.cookies = {}
    response.json.side_effect = ValueError('no json')
    return response


@pytest.mark.parametrize('code', [401, 403])
def test_poll_relogin_bad_password_returns_none(code):
    client = _make_client()
    client.session.get.return_value = _status(code)
    client.session.post.return_value = _login_rejected()

    assert client.poll('/api/status') is None  # used to raise LoginError


def test_poll_relogin_gateway_unreachable_returns_none():
    client = _make_client()
    client.session.get.return_value = _status(401)
    client.session.post.side_effect = OSError('No route to host')

    assert client.poll('/api/status') is None  # used to raise ConnectionError


def test_post_relogin_bad_password_returns_none():
    client = _make_client()
    client.session.post.side_effect = [_status(401), _login_rejected()]

    assert client.post('/api/operation', {'real_mode': 'self_consumption'}, None) is None


def test_poll_relogin_success_still_retries(tmp_path):
    """Sanity check: a successful re-login still retries the read once."""
    client = _make_client()
    client.cachefile = str(tmp_path / '.powerwall')
    ok = _status(200)
    ok.text = '{"percentage": 50}'
    ok.headers = {'Content-Type': 'application/json'}
    client.session.get.side_effect = [_status(401), ok]
    login = _status(200)
    login.cookies = {'AuthCookie': 'new', 'UserRecord': 'new'}
    client.session.post.return_value = login

    assert client.poll('/api/system_status/soe') == {'percentage': 50}
    assert client.auth == {'AuthCookie': 'new', 'UserRecord': 'new'}


def test_authenticate_still_raises_login_error():
    """authenticate() must keep raising - connect() relies on it for failover."""
    client = _make_client()
    client.cachefile = '/nonexistent/dir/.powerwall'
    client.poolmaxsize = 0
    client.auth = {}
    with patch('pypowerwall.local.pypowerwall_local.requests.post', return_value=_login_rejected()):
        with pytest.raises(LoginError):
            client.authenticate()
