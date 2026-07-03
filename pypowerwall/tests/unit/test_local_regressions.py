"""Regression tests for local backend robustness:
- poll() 404 handler compared `version >= 23440` which raised TypeError when
  the firmware version could not be determined (version() returned None)
- negative caching stored None, which the cache-hit check treated as a miss,
  so failing endpoints (404/403/503) were re-requested on every poll
- poll(api, raw=True) unconditionally reset raw to False, so the documented
  raw-bytes mode never worked except on the internal vitals path
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


def test_poll_raw_true_returns_bytes():
    """poll(api, raw=True) must return raw response bytes (was forced to False)."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 200
    response.raw.data = b'\x08\x01binary-payload'
    client.session.get.return_value = response

    assert client.poll('/api/status', raw=True) == b'\x08\x01binary-payload'
    # The request must be streamed for raw mode
    assert client.session.get.call_args.kwargs.get('stream') is True


def test_poll_default_still_parses_json():
    """Default (raw=False) behavior is unchanged - JSON payloads are parsed."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 200
    response.text = '{"din": "123"}'
    response.headers = {'Content-Type': 'application/json'}
    client.session.get.return_value = response

    assert client.poll('/api/status') == {'din': '123'}
    assert client.session.get.call_args.kwargs.get('stream') is False


def test_poll_vitals_internally_raw():
    """The internal vitals path must still force raw mode (protobuf stream)."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 200
    response.raw.data = b'protobuf-bytes'
    client.session.get.return_value = response

    assert client.poll('/api/devices/vitals') == b'protobuf-bytes'
    assert client.session.get.call_args.kwargs.get('stream') is True


def test_negative_cache_suppresses_refetch():
    """A 404 must be negatively cached - no re-request within the TTL."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 404
    client.session.get.return_value = response

    assert client.poll('/api/operation') is None
    assert client.session.get.call_count == 1
    # Second poll within the negative-cache TTL must not hit the gateway
    assert client.poll('/api/operation') is None
    assert client.session.get.call_count == 1


def test_cache_invalidation_after_write_forces_refetch():
    """_invalidate_cache (write path) must clear a negative entry and re-fetch."""
    client = _make_client()
    response = MagicMock()
    response.status_code = 404
    client.session.get.return_value = response

    assert client.poll('/api/operation') is None
    assert client.poll('/api/operation') is None
    assert client.session.get.call_count == 1  # second served from negative cache

    # Simulate a successful write to /api/operation invalidating the read cache
    client._invalidate_cache('/api/operation')

    ok = MagicMock()
    ok.status_code = 200
    ok.text = '{"real_mode": "self_consumption"}'
    ok.headers = {'Content-Type': 'application/json'}
    client.session.get.return_value = ok

    assert client.poll('/api/operation') == {'real_mode': 'self_consumption'}
    assert client.session.get.call_count == 2
