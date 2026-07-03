# Code Review Findings — 2026-07-03

Full-codebase review (core library, all four backends, proxy server) plus documentation audit.
Documentation fixes have already been applied; the items below are **code changes still needed**,
ordered by priority. None of the suggested fixes change public API signatures or return shapes
unless explicitly marked "maintainer decision".

## P0 — Real bugs with user-visible damage

1. **`set_operation()` silently lowers the battery reserve** — `pypowerwall/__init__.py:733-740`.
   When `level is None`, it back-fills from `get_reserve()` (default `scale=True`, app scale) and
   posts that as raw `backup_reserve_percent`. In local mode the write path expects raw scale, so
   every `set_mode("backup")` call ratchets the real reserve down ~5 points (raw 20% → ~15.8%).
   Also crashes with `TypeError` when `get_reserve()` returns `None`.
   Fix: back-fill with `get_reserve(scale=False)`; guard `None`.
   Related (maintainer decision): the write-scale contract is inconsistent across backends —
   local `post('/api/operation')` expects raw %, cloud/fleetapi/tedapi expect app %. Round-trip
   `set_reserve(50)/get_reserve()` returns 50 on cloud/fleetapi/tedapi but 47.4 on local.

2. **`alerts(alertsonly=False)` always crashes** — `pypowerwall/__init__.py:636`.
   `alerts.add({device: i})` on a `set()` raises `TypeError: unhashable type: 'dict'` on the first
   device alert. This path has never worked. Fix: collect tuples internally, rebuild the
   documented list-of-dicts shape at return.

3. **FleetAPI token refresh can wedge permanently** — `pypowerwall/fleetapi/fleetapi.py:289-321`.
   `new_token()` sets `self.refreshing = True` with no try/finally and calls `response.json()`
   before checking status. Any error leaves `refreshing=True` forever; all future 401s skip
   refresh until process restart. Fix: try/finally reset; check status before `.json()`; use a
   real `threading.Lock`.

4. **Proxy degradation-cache type collision crashes `/csv` and `/json` during outages** —
   `proxy/server.py:1270` caches a JSON *string* under key `"/aggregates"`; `generate_csv` (1344)
   and `generate_json` (1848) cache a *dict* under the same key. During an outage whichever was
   stored last is served; the CSV/JSON paths call `.get()` on a possible string → `AttributeError`
   exactly when graceful degradation is supposed to help. Fix: namespace cache keys by format, or
   always cache the dict.

5. **TEDAPI `available_blocks` always 0** — `pypowerwall/tedapi/pypowerwall_tedapi.py:628-629`.
   Reads `control.batteryBlocks` from the **config** payload; it lives in **status**. Fix:
   `lookup(status, ["control", "batteryBlocks"])`. Same function: `get_blocks()` can return
   `None` → `TypeError` on iteration (line 631-634); guard with `or {}`.

6. **TEDAPI `PINV_GridState` always None (copy-paste bug)** — `pypowerwall/tedapi/__init__.py:2028`.
   Uses `p` (THC entry) instead of `pinv`. Nulls `pinv_grid_state` downstream in `get_blocks()`
   and `battery_blocks()`. Fix: `p` → `pinv`.

7. **Cloud `set_grid_charging`/`set_grid_export` return a tuple** —
   `pypowerwall/cloud/pypowerwall_cloud.py:883-888, 907-912`. `_site_api()` returns
   `(response, cached)`; these two return it un-unpacked, so cloud mode returns `({...}, False)`
   where fleetapi returns a dict and tedapi returns bool. Fix: unpack the tuple.

8. **Cloud `post_api_operation` drifted behind fleetapi** —
   `pypowerwall/cloud/pypowerwall_cloud.py:1191-1237` vs `fleetapi/pypowerwall_fleetapi.py:759-787`.
   Cloud copy KeyErrors on partial payloads (swallowed into `{'error': "'real_mode'"}`) and does
   not normalize `False` → `0` for reserve. Port the fleetapi logic.

## P1 — Security

9. **Proxy: allowlist/DISABLED bypass via query string; open proxy to gateway** —
   `proxy/server.py:2009-2014, 2187-2211`. Exact-match against a path that still contains the
   query string: `GET /api/customer/registration?x=1` bypasses DISABLED, and any unmatched path
   is forwarded to the gateway **with the proxy's auth attached**. Fix: match on
   `urlparse(path).path`; restrict the passthrough fallback to known web-asset prefixes.

10. **Proxy: unauthenticated GET `/control/*` incl. a write side effect** —
    `proxy/server.py:2015-2064`. GETs require no token, and GET `/control/max_backup` calls
    `cancel_max_backup` (a write) — CSRF-trivial with `Access-Control-Allow-Origin: *`.
    Fix: move the auto-cancel behind the token check; consider requiring token on GETs.
    (Docs were updated to describe current behavior; code should still be hardened.)

11. **Credential files created world-readable** — `pypowerwall/tesla_auth.py:1209-1211`,
    `v1r_register.py:166-176, 258-260, 575-577` (chmod-after-write race);
    `fleetapi/fleetapi.py:285-286` (`.pypowerwall.fleetapi` with tokens+secret, no chmod at all);
    `local/pypowerwall_local.py:110-113` (`.powerwall` cache with auth cookie, no chmod).
    Fix: `os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)` at creation.

12. **FleetAPI logs live tokens at DEBUG** — `fleetapi/fleetapi.py:317-318`. Redact.

13. **Proxy `/help` stored XSS** — `proxy/server.py:1935-1936, 2269-2274`. Request paths (incl.
    query strings) are rendered into `/help` HTML unescaped. Fix: `html.escape()`.

14. **Proxy misc hardening** — non-constant-time token compare (1058 → `hmac.compare_digest`);
    unbounded POST body read (1042 → cap at a few KB); real gateway auth cookies handed to any
    client in cookie mode (2133-2148 → guard `pw.client` None; consider opt-out).

## P2 — Crash-on-None / robustness (all trivially fixable)

15. Local vitals-404 firmware gate: `version()` may be `None` → `TypeError` —
    `local/pypowerwall_local.py:184-185`. Guard `is not None`.
16. `parse_version()` raises on digit-less versions (e.g. "unknown") instead of returning `None` —
    `pypowerwall_base.py:17-24`. Wrap `int()` in try/except.
17. `self.client` never assigned when all modes fail → raw `AttributeError` on every call —
    `__init__.py:180, 232-234`. Assign `None` and fail gracefully.
18. `get_pw3_vitals()` unguarded (`config['battery_blocks']` on None; no try/except around
    follower JSON parse) — `tedapi/__init__.py:1028-1029, 1083-1196`; call sites missing `or {}` —
    `pypowerwall_tedapi.py:532, 578`.
19. TEDAPI solar sum: `v_solar_sum += lookup(...)` can be None — `pypowerwall_tedapi.py:543`.
20. TEDAPI vitals POD/PINV indexed by THC loop index without bounds/None guard (PVS has one) —
    `tedapi/__init__.py:1988, 2023`.
21. TEDAPI lock timeout raises `TimeoutError` out of `poll()`/`vitals()` under contention; every
    other backend degrades to `None` — `api_lock.py:68-69` + call sites. Catch and return cached/None.
22. Local: `'json' in r.headers.get('Content-Type')` TypeError when header missing —
    `local/pypowerwall_local.py:236, 310`. Default to `''`.
23. `poll()`/`post()` catch `JSONDecodeError` where `TypeError` is raised (dead except; implicit
    None fall-through) — `__init__.py:358-364, 379-385`.
24. CLI `set -current`: `float(pw.level())` crashes when level is None — `__main__.py:789`.
25. `strings()` fragile indexing (devicemap cap 9, `PVAC_Pout` KeyError, string_map cap 36) —
    `__init__.py:439-505`; `battery_blocks()` direct indexing — `__init__.py:880-897`.
26. FleetAPI `load_config()` site auto-discovery: `sites[0]` on None, may pick a vehicle —
    `fleetapi/fleetapi.py:259-262`. Filter for `energy_site_id`.
27. `PyPowerwallFleetAPI.getsites()` returns None when `siteid is None`, defeating the
    auto-default in `connect()` — `fleetapi/pypowerwall_fleetapi.py:221-222`. Delete the guard.
28. Cloud sitefile parse failure defaults `siteid=0` → hard connect failure —
    `cloud/pypowerwall_cloud.py:76-79`. Use None.
29. Cloud `get_time_remaining` `in None` crash — `cloud/pypowerwall_cloud.py:604`.
30. Proxy gateway-passthrough: only catches `AttributeError`; `ConnectionError`/`Timeout`/missing
    Content-Type header kill the handler; corrupt 404 path (double send_response, no end_headers) —
    `proxy/server.py:2193-2218`.
31. Proxy `/tedapi/*`, `/cloud/*`, `/fleetapi/*` routes bypass `safe_pw_call` — exceptions escape
    during outages — `proxy/server.py:1976-2006`.
32. Proxy null `instant_power` fields crash `/csv` and `/aggregates` (guarded in `/json` only) —
    `proxy/server.py:1295, 1354, 1361`. Normalize `or 0` before comparisons.
33. Proxy `ssl.wrap_socket` removed in Python 3.12 (`PW_HTTPS=yes` crashes outside the 3.10
    Docker image) — `proxy/server.py:2293`. Use `SSLContext`.

## P3 — Performance

34. Local negative caching ineffective: error paths store `pwcache[api]=None` but the cache-hit
    test requires `is not None`, so failing endpoints are hammered every poll —
    `local/pypowerwall_local.py:142 vs 190-223`. Use a sentinel.
35. `api_lock.py` busy-wait backoff adds up to ~2s idle latency per contended call; native
    `lock.acquire(timeout=...)` does it properly — `api_lock.py:38-54`.
36. FleetAPI builds a new HTTP/2 client (full TLS handshake) per request; the requests-fallback
    can silently *duplicate POSTs* (e.g. set reserve twice) after an httpx timeout —
    `fleetapi/fleetapi.py:174-190`. Reuse a client; never fall back after a POST may have sent.
37. FleetAPI caches error (None) results and grows `pwcache` unboundedly on timestamped history
    URLs — `fleetapi/fleetapi.py:359-367, 623`.
38. Cloud `_site_api` "lock" is a racy boolean dict flag (duplicate Tesla calls); wait-timeout
    returns None even when fresh cache exists — `cloud/pypowerwall_cloud.py:413-440`.
39. Proxy holds `proxystats_lock` across a network call (`pw.site_name`) in `/stats` and `/help` —
    stalls all request threads during outages — `proxy/server.py:1422-1509, 1906-1917`.
40. Proxy `proxystats["uri"]` grows without bound (every unique path+query becomes a permanent
    key; all other tracking dicts are capped) — `proxy/server.py:2269-2274`. Strip query + cap.
41. Proxy Content-Length counts characters, not bytes — non-ASCII payloads truncate —
    `proxy/server.py:1249, 2279`. Encode first.
42. TEDAPI reconnect leaks sessions and startup connects 3×; non-200 on `GET /` misclassifies
    PW2 as PW3 — `tedapi/__init__.py:190-192, 1436-1450`; `close_session()` in local and tedapi
    backends never closes the underlying `requests.Session`.

## P4 — API inconsistencies (flag for maintainer decision; do not change silently)

Status: safe subset fixed on fix/fable-5-review-findings; remaining shape inconsistencies documented in DESIGN.md (frozen public API).

- **Failure shapes vary**: `None` vs `0.0` (`site()` etc. after parse failure) vs `{}` vs `[]` vs
  proxy literal `TIMEOUT!` body with HTTP 200. Downstream tools likely depend on some of these.
- **`poll(api, raw=True)` is ignored in local mode** (`local/pypowerwall_local.py:139` zeroes it).
- **Cross-backend divergences** (full table in review): `get_grid_export()` default
  (`"battery_ok"` cloud/fleetapi vs `None` tedapi); `get_time_remaining()` `None` vs `0.0`;
  `status()['git_hash']` hard-coded fake hash in cloud/fleetapi; `grid_status()` reachable states
  (7 local vs 2 elsewhere); `system_status()['battery_blocks']` `[]` stub vs synthesized list;
  simulated vitals can inject `""` into `alerts()` (cloud/fleetapi).
- **`/fans` returns `null` but `/fans/pw` returns `{}`** on failure; GET error bodies return 200
  while POST maps to 400/401.
- **`connect(retry_modes=True)` blocks forever by design** — document, or add optional cap.
- **CLI `-local` without `-host` silently becomes cloud mode** — `__main__.py:114-115`.
- **Mode fallback permanently mutates `self.mode`** and skips re-validation —
  `__init__.py:298-327`.
- **`InvalidBatteryReserveLevelException` is exported but never raised.**
- Three drifted copies of `lookup()` and of `decorators.py` — consolidate to prevent future drift.

## P5 — Cleanups / annotations

- `get_mode()` annotated `Optional[float]`, returns str (`__init__.py:683`).
- `tesla_auth.py` `-> str` annotations on 3-tuple returns (409, 724); pywebview monkey-patches
  never restored; httpx→requests fallback retries single-use auth codes (148-162, 200-213);
  silent runtime `pip install` side effect (426-435, 742-749).
- `scan.py` Ctrl+C waits for all queued hosts; PW3 results omit `up_time` (185-186, 287-295).
- Dead code: `api_lock.py` unused imports; `pwcooldown` attr on facade; unused `MockPowerwall`
  in `proxy/tests/test_csv_endpoints.py:12-48`.
- Proxy: `removeprefix` identity-check idiom (1030, 1262); degraded-mode recovery uses
  `total % 3 == 0` instead of consecutive successes (428-435); `/stats/clear` doesn't reset
  `posts`/`timeout` (1513-1517); `PW_HTTPS` case-sensitive, unguarded `int()` env parsing
  (173-219); root-page JS injection dead code / `/?query` serves unsubstituted template (2153,
  2231); static assets with query strings never served locally (`transform.py:17-22`).

## Test-coverage gaps worth closing

- No test for: degradation-cache fallback path, per-field null `instant_power`, `/csv/v2`,
  GET `/control/*`, POST `/control/grid_export` (a `json.loads` assertion would have caught the
  invalid-JSON bug), `alerts(alertsonly=False)`, `set_operation` back-fill, `parse_version`
  junk input. Overall coverage ~12%.
