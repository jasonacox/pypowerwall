"""Regression tests for FleetAPI robustness:
- PyPowerwallFleetAPI.getsites() returned None whenever siteid was unset,
  which defeated connect()'s auto-default-to-first-site logic
- FleetAPI.load_config() site auto-discovery crashed when getsites() returned
  None and could pick a vehicle (no energy_site_id) from the products list
- _http2_request built a new httpx.Client (full TLS handshake) per call and
  fell back to a duplicate requests POST after ANY httpx error, which could
  silently repeat non-idempotent operations (e.g. set battery reserve twice)
- poll() cached error (None) results and every unique timestamped history URL
"""
import json
from unittest.mock import MagicMock, patch

import pypowerwall.fleetapi.fleetapi as fleetapi_module
from pypowerwall.fleetapi.fleetapi import FleetAPI
from pypowerwall.fleetapi.pypowerwall_fleetapi import PyPowerwallFleetAPI


def test_getsites_without_siteid(tmp_path):
    """getsites() must return the site list even when siteid is None."""
    backend = PyPowerwallFleetAPI(email='test@example.com', authpath=str(tmp_path))
    backend.siteid = None
    backend.fleet = MagicMock()
    sites = [{'energy_site_id': 1234, 'site_name': 'Home'}]
    backend.fleet.getsites.return_value = sites
    # Used to return None because of the `if self.siteid is None` guard
    assert backend.getsites() == sites


def test_getsites_error_returns_none(tmp_path):
    backend = PyPowerwallFleetAPI(email='test@example.com', authpath=str(tmp_path))
    backend.fleet = MagicMock()
    backend.fleet.getsites.side_effect = RuntimeError('api down')
    assert backend.getsites() is None


def _write_config(tmp_path, site_id=None):
    configfile = tmp_path / 'config.fleetapi'
    configfile.write_text(json.dumps({
        'CLIENT_ID': 'cid', 'CLIENT_SECRET': 'secret', 'DOMAIN': 'example.com',
        'REDIRECT_URI': 'https://example.com', 'AUDIENCE': 'aud',
        'partner_token': 'pt', 'partner_account': {}, 'access_token': 'at',
        'refresh_token': 'rt', 'site_id': site_id,
    }))
    return str(configfile)


def test_load_config_sites_none_does_not_crash(tmp_path):
    """getsites() returning None (API error) must not TypeError in load_config()."""
    configfile = _write_config(tmp_path)
    with patch.object(FleetAPI, 'getsites', return_value=None):
        fleet = FleetAPI(configfile=configfile)  # used to raise TypeError
    assert not fleet.site_id


def test_load_config_skips_vehicles(tmp_path):
    """Products list can mix in vehicles - pick the first energy site."""
    configfile = _write_config(tmp_path)
    products = [
        {'vin': '5YJ3E1EA0000000', 'display_name': 'Car'},  # vehicle - no energy_site_id
        {'energy_site_id': 9999, 'site_name': 'Home'},
    ]
    with patch.object(FleetAPI, 'getsites', return_value=products):
        fleet = FleetAPI(configfile=configfile)
    assert fleet.site_id == 9999


# --- _http2_request transport behavior ---

def _fake_httpx_response(status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason_phrase = 'OK'
    resp.content = b'{}'
    resp.http_version = 'HTTP/2'
    return resp


def test_http2_client_reused_across_calls(monkeypatch):
    """Two requests must reuse a single httpx.Client (one TLS handshake)."""
    monkeypatch.setattr(fleetapi_module, '_http2_client', None)
    created = []

    class FakeClient:
        is_closed = False

        def __init__(self, **kwargs):
            created.append(self)

        def request(self, method, url, **kwargs):
            return _fake_httpx_response()

    monkeypatch.setattr(fleetapi_module.httpx, 'Client', FakeClient)
    r1 = fleetapi_module._http2_request('GET', 'https://example.com/a')
    r2 = fleetapi_module._http2_request('GET', 'https://example.com/b')
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(created) == 1
    assert fleetapi_module._http2_client is created[0]


def test_post_timeout_does_not_fall_back_to_requests(monkeypatch):
    """A POST that may have been transmitted must NOT be re-sent via requests."""
    monkeypatch.setattr(fleetapi_module, '_http2_client', None)

    class TimeoutClient:
        is_closed = False

        def __init__(self, **kwargs):
            pass

        def request(self, method, url, **kwargs):
            raise fleetapi_module.httpx.ReadTimeout('read timed out')

    monkeypatch.setattr(fleetapi_module.httpx, 'Client', TimeoutClient)
    post_mock = MagicMock()
    get_mock = MagicMock()
    monkeypatch.setattr(fleetapi_module.requests, 'post', post_mock)
    monkeypatch.setattr(fleetapi_module.requests, 'get', get_mock)

    result = fleetapi_module._http2_request('POST', 'https://example.com/backup',
                                            data='{"backup_reserve_percent": 20}')
    assert result is None
    post_mock.assert_not_called()
    get_mock.assert_not_called()


def test_get_connect_error_still_falls_back_to_requests(monkeypatch):
    """Connection-establishment errors on GET keep the HTTP/1.1 fallback."""
    monkeypatch.setattr(fleetapi_module, '_http2_client', None)

    class ConnErrClient:
        is_closed = False

        def __init__(self, **kwargs):
            pass

        def request(self, method, url, **kwargs):
            raise fleetapi_module.httpx.ConnectError('no route to host')

    monkeypatch.setattr(fleetapi_module.httpx, 'Client', ConnErrClient)
    sentinel = MagicMock(status_code=200)
    get_mock = MagicMock(return_value=sentinel)
    monkeypatch.setattr(fleetapi_module.requests, 'get', get_mock)

    result = fleetapi_module._http2_request('GET', 'https://example.com/products')
    assert result is sentinel
    get_mock.assert_called_once()


# --- poll() cache hygiene ---

def test_poll_does_not_cache_errors_or_history_urls(tmp_path, monkeypatch):
    fleet = FleetAPI(configfile=str(tmp_path / 'missing.fleetapi'))

    # Non-200 responses (data=None) must not be written into the cache
    err = MagicMock(status_code=500, text='server error')
    monkeypatch.setattr(fleetapi_module, '_http2_request', MagicMock(return_value=err))
    assert fleet.poll('api/1/products') is None
    assert 'api/1/products' not in fleet.pwcache
    assert 'api/1/products' not in fleet.pwcachetime

    ok = MagicMock(status_code=200)
    ok.json.return_value = {'response': []}
    monkeypatch.setattr(fleetapi_module, '_http2_request', MagicMock(return_value=ok))

    # Parameterized (timestamped) history URLs must never become cache entries
    history_api = 'api/1/energy_sites/123/history?kind=power&start_date=2026-07-01'
    assert fleet.poll(history_api) == {'response': []}
    assert history_api not in fleet.pwcache

    # Normal endpoints still cache successful responses
    assert fleet.poll('api/1/products') == {'response': []}
    assert fleet.pwcache['api/1/products'] == {'response': []}
