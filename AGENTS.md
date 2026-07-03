# AGENTS.md - AI Agent Guidelines for pypowerwall

This document provides guidelines for AI code agents (Claude, Copilot, etc.) working on this codebase. Read [DESIGN.md](DESIGN.md) first for architecture; this file is the hands-on companion.

## Quick Reference

```bash
# Run tests (unit + proxy; skips live-hardware tests)
pytest -m "not live"

# Run tests without coverage output (faster inner loop)
pytest -m "not live" --no-cov

# Lint (CI runs pylint across Python 3.9-3.13)
pylint pypowerwall proxy/server.py

# Run the proxy locally
python3 proxy/server.py

# Run against the simulator instead of real hardware
cd pwsimulator && docker build -t pwsimulator . && docker run -p 443:443 pwsimulator
# then: PW_HOST=localhost PW_PASSWORD=password PW_EMAIL=me@example.com python3 example.py

# CLI smoke test
python3 -m pypowerwall version
```

## The Prime Directive: Never Break the Public API

This library and its proxy are depended on by [Powerwall-Dashboard](https://github.com/jasonacox/Powerwall-Dashboard) and many other consumers running unattended 24/7. That means:

- **Method signatures**: existing positional/keyword parameters keep their names, order, and defaults. Add new parameters at the end with defaults. Legacy quirks like the `jsonformat` kwarg and the deprecated `type` argument to `grid_status()` stay.
- **Return shapes**: including *failure* shapes. If a method returns `None` on error today, it keeps returning `None` — not an exception, not `{}`.
- **Proxy HTTP responses**: status codes, JSON shapes, even oddities (some error paths return HTTP 200 with a JSON error body; Telegraf configs depend on current shapes). Fix bugs *behind* the interface, never by changing the interface.
- **The local `/api/...` URI namespace**: it is the internal lingua franca. Every non-local backend must answer the same URIs the local gateway does.

If a fix seems to require a breaking change, stop and flag it for the maintainer instead.

## Code Style

The library predates auto-formatters and is linted with **pylint** (not Black). Match the file you are editing:

- **Quotes**: single quotes dominate in `pypowerwall/`; double quotes dominate in `proxy/server.py`. Follow the surrounding file.
- **Line length**: ~100-120 characters is the norm. Don't reflow existing code.
- **Indentation**: 4 spaces.
- **Type hints**: public methods carry `Optional[Union[dict, list, str, bytes]]`-style annotations; internals are often untyped. Add hints to new public methods; don't retrofit whole files.
- **Naming**: `snake_case` functions; backend classes are `PyPowerwall<Mode>`; cache/state attributes use the `pw` prefix (`pwcache`, `pwcachetime`, `pwcacheexpire`, `pwcooldown`); proxy env vars are `PW_*`.
- **Comments**: this codebase favors generous explanatory comments, including root-cause narratives for workarounds (see the cloud 403 saga in `cloud/pypowerwall_cloud.py`). Keep that habit for anything non-obvious, especially firmware-version-specific behavior.
- **Module headers**: new modules get the banner-style docstring (description, "Author: Jason A. Cox", repo URL, Features/Functions lists) used everywhere else.

### Logging

Every module follows this pattern — do the same:

```python
import logging
log = logging.getLogger(__name__)

# ... and a module-level toggle:
def set_debug(toggle=True, color=True):
    ...
```

- Never log credentials, tokens, or cookies — not even at DEBUG level.
- Library code logs errors and returns `None`; it does not print. The CLI (`__main__.py`) and proxy do the printing.

### Error handling conventions (load-bearing — see DESIGN.md)

- Read methods: `log.error(...)` and **return `None`** on failure. Never raise to callers.
- `authenticate()`: **raise** on failure — this drives mode fallback in `connect()`.
- Invalid arguments: raise `ValueError` / `PyPowerwallInvalidConfigurationParameter`.
- Gateway rate limiting (429/503): set a cooldown, don't retry-loop.
- Guard every `lookup()`/dict access on gateway payloads — fields can be `None` or missing depending on firmware and hardware (PW2 vs PW3 vs cloud). Prefer `.get(key, default)` and `x or 0` over direct indexing.

## How to Add Things

### A new API endpoint (library)

Local mode passes any `/api/...` URI through automatically. The other three backends need explicit handlers — **all three, always**:

1. `pypowerwall/cloud/pypowerwall_cloud.py` — add `"/api/foo": self.get_api_foo` to `init_poll_api_map()`, implement `def get_api_foo(self, **kwargs)` using `self._site_api(...)`.
2. `pypowerwall/fleetapi/pypowerwall_fleetapi.py` — same pattern in its `init_poll_api_map()`.
3. `pypowerwall/tedapi/pypowerwall_tedapi.py` — same, pulling from `self.tedapi.get_status()/get_config()` with `lookup()`.
4. If a backend can't provide real data: add a constant to that backend's `mock_data.py`, decorate the handler with `@not_implemented_mock_data`, and return `json.loads(MOCK_CONSTANT)`. For partially-real data, deep-copy a template from `stubs.py` and fill it in.
5. Writable endpoints: add to `init_post_api_map()` in all three, and extend `WRITE_OP_READ_OP_CACHE_MAP` in `pypowerwall_base.py` if the write must invalidate a cached read.
6. Facade convenience method in `pypowerwall/__init__.py` — and update the module docstring's Functions list, README.md, and API.md.
7. If the proxy should expose it: append the URI to `ALLOWLIST` in `proxy/server.py`.
8. Make it CI-testable: add a handler to `pwsimulator/stub.py`.

### A new proxy route

- Add an `elif request_path == "/myroute":` branch in `Handler.do_GET` in `proxy/server.py`. For cached JSON routes use `cached_route_handler("/myroute", lambda: safe_endpoint_call("/myroute", pw.some_method, jsonformat=True))`; never call `pw.*` directly in a handler — always go through `safe_pw_call`/`safe_endpoint_call` so gateway outages can't crash the handler.
- `/pw/<name>` convenience routes go in the `simple_mappings` dict instead.
- Write (control) routes go in `do_POST`, gated by the `PW_CONTROL_SECRET` token check.
- New config knobs are `PW_*` env vars read at module import; document them in `proxy/README.md` (settings list) and `proxy/API.md`.
- Bump `BUILD = "tNN"` in `proxy/server.py` and add a `proxy/RELEASE.md` entry.
- Add tests in `proxy/tests/` following `test_api_endpoints.py` (mock `proxy.server.pw`, clear `_performance_cache`).

### A new backend mode

Create `pypowerwall/<mode>/pypowerwall_<mode>.py` with `class PyPowerwall<Mode>(PyPowerwallBase)` implementing the six abstract methods, plus the standard sibling files (`exceptions.py`, `mock_data.py`, `stubs.py`, `decorators.py` — copy from `cloud/`). Wire it into `Powerwall.connect()`, `auto_select`, and `_validate_init_configuration()` in `pypowerwall/__init__.py`; patch the new class in the autouse fixture in `pypowerwall/tests/test_mode_selection.py`; add its exception types to `safe_pw_call` in `proxy/server.py`.

## Testing

- `pytest -m "not live"` must pass before any change is complete. Live tests require real hardware and self-skip.
- **`Powerwall` construction must never require network in tests** — unit tests patch backend classes by name (`patch('pypowerwall.PyPowerwallTEDAPI')`). Don't restructure imports in `pypowerwall/__init__.py` in a way that breaks patch-by-name.
- Coverage is thin outside the tested paths (~12% overall). When you touch a code path, add a test for it — especially failure paths (`None` payloads, missing dict keys, gateway timeouts), which is where most latent bugs in this codebase live.
- Proxy tests mock at the `proxy.server.pw` boundary; don't make real HTTP calls in tests.
- End-to-end verification without hardware: run the `pwsimulator` Docker image and point `example.py` (or the proxy) at it.

## Versioning & Release Checklist

- Library version: bump `version_tuple` in `pypowerwall/__init__.py` (the only place).
- Add a `## vX.Y.Z - Title` entry at the top of `RELEASE.md` (conventional-ish `feat(scope):`/`fix(scope):` bullets, PR refs like `(#345)`).
- Proxy changes: bump `BUILD = "tNN"` in `proxy/server.py` + entry in `proxy/RELEASE.md`. After a library release, update the pin in `proxy/requirements.txt`.
- Do not run `upload.sh` / `proxy/upload.sh` — publishing is the maintainer's job.

## Gotchas an Agent Must Know

- **Reserve scaling**: `/api/system_status/soe` and `/api/operation` values exist in two scales — the raw gateway percentage and the Tesla-app scale (`(raw/0.95) - 5/0.95`). `level(scale=True)` and `get_reserve(scale=True)` convert. Be very careful which scale a value is in before writing it back; mixing them silently changes users' backup reserve.
- **Firmware variance**: gateways on different firmware return different fields (and firmware ≥ 23.44 removed the local vitals API entirely — gated via `parse_version()`). Never assume a payload key exists.
- **PW2 vs PW3**: different vitals paths (protobuf vs TEDAPI components), different device trees. Test logic against both shapes.
- **The vendored `teslapy` fork** (`pypowerwall/cloud/teslapy/`) is patched for HTTP/2 and TLS fingerprinting. Never replace it with the PyPI package or "upgrade" it casually — Tesla's endpoints reject the default TLS fingerprint (and musl-based images break token refresh, which is why the Docker image is Debian-based).
- **Caches everywhere**: library `pwcache` (5s), 404 negative cache (600s), 429/503 cooldown (300s), proxy performance cache, proxy degradation cache (`PW_CACHE_TTL`, 30s). When debugging "stale data," check all layers; when adding a write path, make sure reads are invalidated.
- **Thread-safety matters**: the proxy is a `ThreadingHTTPServer`, so all library code runs multi-threaded. Never hold a lock across a network call; use real `threading.Lock`s, not boolean flags.
- **Secrets on disk**: auth/config files (`.pypowerwall.auth`, `.pypowerwall.fleetapi`, `.powerwall`) contain tokens. Create them with `0o600` permissions (use `os.open(..., 0o600)` at creation, not chmod-after-write).
- **`verify=False` is intentional** for gateway HTTPS (self-signed certs on the appliance) — don't "fix" it, and don't copy the pattern to non-gateway URLS.
