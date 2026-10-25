"""Regression tests for the FleetAPI thundering-herd fixes (issue #433):

The proxy (ThreadingHTTPServer) serves every dashboard poller on its own
thread, all sharing one FleetAPI instance. When the cache expires, every
thread missed at the same moment and issued its own fetch - 6-8 identical
live_status GETs within tens of milliseconds - which piled into Tesla's
rate limit (1,332 HTTP 429s vs 547 HTTP 200s in a 10 minute DEBUG log) and
stirred up intermittent HTTP/2 connection-reuse corruption on the shared
httpx client. The fixes tested here:

- single-flight coalescing: concurrent identical GETs share one in-flight
  request (the leader fetches, followers wait for and share its result)
- 429 backoff: Tesla's "Retry in N seconds" guidance (Retry-After header or
  body) arms one shared backoff window during which cache-missing reads
  fail fast with None - no library call ever sleeps
- cache expiry jitter: cached stamps are backdated so endpoints cached
  together in a burst don't all expire on the same future tick
- PW_FLEETAPI_HTTP=1.1: forces a deterministic HTTP/1.1 transport (requests)
  instead of riding the HTTP/2 failure-path fallback
"""
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pypowerwall.fleetapi.fleetapi as fleetapi_module
from pypowerwall.fleetapi.fleetapi import FleetAPI, _parse_retry_after


def _write_config(tmp_path, site_id='SITE123'):
    configfile = tmp_path / 'config.fleetapi'
    configfile.write_text(json.dumps({
        'CLIENT_ID': 'cid', 'CLIENT_SECRET': 'secret', 'DOMAIN': 'example.com',
        'REDIRECT_URI': 'https://example.com', 'AUDIENCE': 'aud',
        'partner_token': 'pt', 'partner_account': {}, 'access_token': 'at',
        'refresh_token': 'rt', 'site_id': site_id,
    }))
    return str(configfile)


def make_fleet(tmp_path, pwcacheexpire=5, timeout=5):
    return FleetAPI(configfile=_write_config(tmp_path),
                    pwcacheexpire=pwcacheexpire, timeout=timeout)


def fake_response(status_code=200, payload=None, text='', headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason_phrase = 'OK' if status_code < 400 else 'Error'
    resp.text = text or json.dumps(payload or {})
    resp.headers = headers or {}
    if payload is not None:
        resp.json.return_value = payload
    else:
        resp.json.return_value = {}
    return resp


# --- single-flight coalescing ---

def test_concurrent_cache_misses_coalesce_to_one_request(tmp_path):
    """8 pollers hitting the same cache expiry boundary must produce exactly
    one FleetAPI request, with every thread sharing the leader's result."""
    fleet = make_fleet(tmp_path)
    payload = {'response': {'solar_power': 1234}}
    calls = []
    lock = threading.Lock()

    def slow_fake_req(method, url, **kwargs):
        with lock:
            calls.append(url)
        time.sleep(0.3)  # hold the in-flight window open so followers join
        return fake_response(200, payload)

    barrier = threading.Barrier(8, timeout=5)
    results = [None] * 8

    def worker(i):
        barrier.wait()
        results[i] = fleet.poll('api/1/energy_sites/SITE123/live_status')

    with patch.object(fleetapi_module, '_http2_request', side_effect=slow_fake_req):
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert len(calls) == 1, f"expected exactly 1 network request, got {len(calls)}"
    assert all(r == payload for r in results)
    assert fleet._inflight == {}  # entry cleaned up after the fetch


def test_leader_failure_does_not_wedge_single_flight(tmp_path):
    """If the leader's request raises, the entry must still be cleaned up
    (followers get None, the next miss starts a fresh fetch)."""
    fleet = make_fleet(tmp_path)
    payload = {'response': {'ok': True}}
    state = {'boom': True}

    def flaky_req(method, url, **kwargs):
        if state['boom']:
            state['boom'] = False
            raise RuntimeError('h2 state corruption')
        return fake_response(200, payload)

    with patch.object(fleetapi_module, '_http2_request', side_effect=flaky_req):
        # Leader blows up - poll propagates the exception (existing behavior
        # for non-timeout transport errors)
        try:
            fleet.poll('api/1/energy_sites/SITE123/live_status')
            raised = False
        except RuntimeError:
            raised = True
        assert raised
        # The single-flight entry must not leak - next call is a fresh leader
        assert fleet._inflight == {}
        assert fleet.poll('api/1/energy_sites/SITE123/live_status') == payload


def test_401_refresh_retry_through_single_flight_no_deadlock(tmp_path):
    """The recursive 401 retry re-enters poll() on the leader's own thread -
    it must not join its own in-flight entry (would wait on itself forever)."""
    fleet = make_fleet(tmp_path)
    payload = {'response': {'refreshed': True}}
    responses = [fake_response(401, text='unauthorized'),
                 fake_response(200, payload)]

    with patch.object(fleetapi_module, '_http2_request',
                      side_effect=responses), \
         patch.object(FleetAPI, 'new_token') as new_token:
        result = fleet.poll('api/1/energy_sites/SITE123/live_status')

    assert result == payload
    assert new_token.call_count == 1
    assert fleet._inflight == {}


def test_follower_wait_is_bounded(tmp_path):
    """A follower whose leader never wakes it must return None after the
    bounded wait, not hang forever."""
    fleet = make_fleet(tmp_path, timeout=1)
    # Pre-register a stuck in-flight entry with no leader behind it. Short-
    # circuit Event.wait to simulate the wait timing out instantly while
    # still capturing the timeout the code asked for.
    stuck = fleetapi_module._InflightRequest()
    wait_args = []
    stuck.event.wait = lambda timeout=None: (wait_args.append(timeout), False)[1]
    fleet._inflight['api/1/energy_sites/SITE123/site_info'] = stuck
    result = fleet.poll('api/1/energy_sites/SITE123/site_info')
    assert result is None
    # wait_limit = 2 * REFRESH_TIMEOUT: leader worst case after fail-fast
    # backoff is GET + 401 refresh + retry GET (two refresh attempts max)
    assert wait_args and wait_args[0] == 2 * fleetapi_module.REFRESH_TIMEOUT


# --- 429 shared backoff ---

def test_429_body_retry_guidance_arms_shared_backoff(tmp_path):
    fleet = make_fleet(tmp_path)
    ok = {'response': {'solar_power': 1}}
    calls = []

    def req(method, url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return fake_response(429, text='Rate limited. Please retry in 10 seconds.')
        return fake_response(200, ok)

    with patch.object(fleetapi_module, '_http2_request', side_effect=req):
        assert fleet.poll('api/1/energy_sites/SITE123/live_status') is None
        # Backoff armed for ~10s per the body guidance
        remaining = fleet._backoff_until - time.time()
        assert 9.0 < remaining <= 10.0
        # A cache-missing read during the window fails fast: None, no
        # request, and no sleeping inside the library
        started = time.time()
        assert fleet.poll('api/1/energy_sites/SITE123/live_status') is None
        assert time.time() - started < 0.1
        assert len(calls) == 1
        # The first read after the window elapses fetches normally
        fleet._backoff_until = 0.0
        assert fleet.poll('api/1/energy_sites/SITE123/live_status') == ok
        assert len(calls) == 2


def test_backoff_serves_cache_without_waiting(tmp_path, monkeypatch):
    """Cached data must still be served during a backoff window - the wait
    only guards new network fetches."""
    fleet = make_fleet(tmp_path)
    ok = {'response': {'solar_power': 1}}
    with patch.object(fleetapi_module, '_http2_request',
                      return_value=fake_response(200, ok)):
        fleet.poll('api/1/energy_sites/SITE123/live_status')  # prime cache
    fleet._backoff_until = time.time() + 60.0
    with patch.object(fleetapi_module, '_http2_request') as req:
        started = time.time()
        assert fleet.poll('api/1/energy_sites/SITE123/live_status') == ok
        assert req.call_count == 0
        assert time.time() - started < 0.1  # cache hit, no waiting


def test_parse_retry_after_sources_and_cap():
    # Retry-After header (delay-seconds) wins over the body
    resp = SimpleNamespace(headers={'Retry-After': '3'},
                           text='retry in 10 seconds')
    assert _parse_retry_after(resp) == 3
    # Tesla body phrasing
    resp = SimpleNamespace(headers={}, text='Rate limited. Please retry in 7 seconds.')
    assert _parse_retry_after(resp) == 7
    # shorthand "10s"
    resp = SimpleNamespace(headers={}, text='please retry in 10s')
    assert _parse_retry_after(resp) == 10
    # no guidance anywhere -> conservative default
    resp = SimpleNamespace(headers={}, text='too many requests')
    assert _parse_retry_after(resp) == 10
    # absurd values are capped so a malformed header can't wedge the client
    resp = SimpleNamespace(headers={'Retry-After': '9999'}, text='')
    assert _parse_retry_after(resp) == 60
    # garbage header falls through to the body
    resp = SimpleNamespace(headers={'Retry-After': 'soon-ish'},
                           text='retry in 4 seconds')
    assert _parse_retry_after(resp) == 4
    # inf/nan headers raise OverflowError/ValueError in int(float()) and
    # must fall through to the body instead of raising out of poll()
    resp = SimpleNamespace(headers={'Retry-After': 'inf'},
                           text='retry in 4 seconds')
    assert _parse_retry_after(resp) == 4
    resp = SimpleNamespace(headers={'Retry-After': 'nan'}, text='')
    assert _parse_retry_after(resp) == 10


# --- in-flight cache recheck (review: cache-election race) ---

def test_inflight_recheck_uses_cache_filled_while_paused(tmp_path):
    """Regression for the cache-election race: a caller that misses the
    cache, pauses before acquiring the in-flight lock, and resumes after
    another thread has filled the cache must return that cached result
    instead of issuing a duplicate GET."""
    fleet = make_fleet(tmp_path)
    stale = {'response': {'solar_power': 0}}
    fresh = {'response': {'solar_power': 1}}
    api = 'api/1/energy_sites/SITE123/site_info'
    # Expired cache entry so the first (unlocked) freshness check misses
    fleet.pwcachetime[api] = time.time() - 999
    fleet.pwcache[api] = stale

    real_lock = fleet._inflight_lock

    class PausedLock:
        def __enter__(self):
            # Simulate another thread filling the cache while this caller
            # was paused between its cache check and the lock acquisition
            fleet.pwcachetime[api] = time.time()
            fleet.pwcache[api] = fresh
            return real_lock.__enter__()

        def __exit__(self, *args):
            return real_lock.__exit__(*args)

    fleet._inflight_lock = PausedLock()
    with patch.object(fleetapi_module, '_http2_request') as req:
        assert fleet.poll(api) == fresh
        assert req.call_count == 0
    assert fleet._inflight == {}  # never registered a duplicate entry


def test_follower_waits_through_leader_401_refresh(tmp_path):
    """Combined path: while the leader rides out a 401 token refresh and
    retries, a follower must wait on the bounded window and share the
    leader's final result rather than timing out into None."""
    fleet = make_fleet(tmp_path, timeout=1)
    ok = {'response': {'solar_power': 1}}
    api = 'api/1/energy_sites/SITE123/site_info'
    leader_started = threading.Event()
    refresh_done = threading.Event()

    def req(method, url, **kwargs):
        if url.endswith('/token'):
            refresh_done.wait(timeout=10)
            return fake_response(200, {'access_token': 'at2', 'refresh_token': 'rt2'})
        if not leader_started.is_set():
            leader_started.set()
            return fake_response(401, text='expired')
        return fake_response(200, ok)

    def slow_new_token(*args, **kwargs):
        # Simulate the token refresh taking a while (HTTP/2 timeout plus an
        # HTTP/1.1 fallback) before the retry GET succeeds
        time.sleep(0.3)
        refresh_done.set()

    with patch.object(fleetapi_module, '_http2_request', side_effect=req), \
            patch.object(fleet, 'new_token', side_effect=slow_new_token):
        follower_result = []

        def follower():
            follower_result.append(fleet.poll(api))

        t = threading.Thread(target=follower)
        t.start()
        leader_started.wait(timeout=5)  # let the leader elect first
        leader_result = fleet.poll(api)
        t.join(timeout=10)
    assert leader_result == ok
    assert follower_result == [ok]  # shared the leader's result, no timeout


# --- cache expiry jitter ---

def test_cache_stamp_backdated_within_jitter_bound(tmp_path):
    """Cache stamps are backdated by up to 25% of TTL (max 10s) so a burst of
    endpoints cached together don't expire on the same future tick."""
    fleet = make_fleet(tmp_path, pwcacheexpire=30)  # jitter bound: 7.5s
    ok = {'response': {'site_name': 'Home'}}
    api = 'api/1/energy_sites/SITE123/site_info'
    with patch.object(fleetapi_module, '_http2_request',
                      return_value=fake_response(200, ok)):
        assert fleet.poll(api) == ok
    backdate = time.time() - fleet.pwcachetime[api]
    assert 0 <= backdate <= 7.5 + 0.05
    # Still fresh enough to be served from cache immediately
    with patch.object(fleetapi_module, '_http2_request') as req:
        assert fleet.poll(api) == ok
        assert req.call_count == 0


# --- PW_FLEETAPI_HTTP=1.1 escape hatch ---

def test_pw_fleetapi_http_11_forces_requests_transport(tmp_path, monkeypatch):
    monkeypatch.setenv('PW_FLEETAPI_HTTP', '1.1')
    fake = fake_response(200, {'response': {}})
    with patch.object(fleetapi_module.requests, 'get', return_value=fake) as rget, \
         patch.object(fleetapi_module, '_get_http2_client',
                      side_effect=AssertionError('httpx client used despite force')):
        resp = fleetapi_module._http2_request('GET', 'https://fleet-api.example.test/api/1/products')
    assert resp is fake
    rget.assert_called_once()


def test_pw_fleetapi_http_unset_uses_http2_client(tmp_path, monkeypatch):
    monkeypatch.delenv('PW_FLEETAPI_HTTP', raising=False)
    fake = fake_response(200, {'response': {}})
    client = MagicMock()
    client.request.return_value = fake
    with patch.object(fleetapi_module, '_get_http2_client', return_value=client), \
         patch.object(fleetapi_module.requests, 'get',
                      side_effect=AssertionError('requests used without force')) as rget:
        resp = fleetapi_module._http2_request('GET', 'https://fleet-api.example.test/api/1/products')
    assert resp.status_code == 200
    client.request.assert_called_once()
