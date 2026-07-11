# RELEASE NOTES

## Unreleased - TEDAPI V2026_06 Query Set (Signed GraphQL / Bearer Mode)

* feat(tedapi): add date-labeled TEDAPI query/protobuf sets selectable via `tedapi_api_version` (`"V2024_06"` default, `"V2026_06"`). `V2026_06` sends Tesla-signed `SignedGraphQLQuery` payloads over the energy_device GraphQL path; `V2024_06` keeps the original hand-rolled captures. Selectable in code (`TEDAPI(..., tedapi_api_version=...)`), env/CLI (`-tedapi_api_version=V2026_06`), and coerced from plain strings.
* note(tedapi): the default `V2024_06` path and its protobufs are unchanged — the library floor stays at `protobuf>=4.25.1` (the `local`/`V2024_06` `*_pb2.py` are still generated with the protobuf 4.25.x toolchain and are byte-identical to prior releases). Only the opt-in `V2026_06` query set is built with the latest protoc, so its `*_pb2.py` embed a `runtime_version.ValidateProtobufRuntimeVersion()` guard and require `protobuf>=6.33.6`. Those modules are imported lazily only when `tedapi_api_version="V2026_06"` is selected, so an older runtime raises a clear, actionable error (`tedapi_api_version="V2026_06" requires protobuf>=6.33.6 — pip install -U protobuf`) at opt-in time — everyone on the default path is unaffected.
* robustness(tedapi): when the gateway rejects a `V2026_06` signed query, pyPowerwall now logs a warning suggesting a fallback to `tedapi_api_version="V2024_06"` — a total `V2026_06` failure after a firmware update most likely means Tesla rotated the query signing keys, so the bundled signatures no longer validate.

## v0.16.1 - Windows TLS Fix for Tesla Auth

* fix(windows): cap TLS to 1.2 on Windows to avoid Tesla token fingerprint rejection (#350)
  * Windows Python bundles an OpenSSL build whose TLS 1.3 ClientHello fingerprint is rejected by Tesla during PKCE code exchange and token refresh — tokens come back "tainted" and all `owner-api.teslamotors.com` calls return `403 Forbidden`
  * `_httpx_auth_verify()` in `tesla_auth.py` and `teslapy/__init__.py` now caps `maximum_version` to TLS 1.2 on Windows (`sys.platform == 'win32'`); Linux/macOS retain TLS 1.3 pinning
  * TLS 1.2 fully supports HTTP/2, so ALPN negotiation and h2 framing are unaffected
* fix(register): `api_call()` in `v1r_register.py` now uses httpx with HTTP/2 for Tesla API endpoints (was urllib/HTTP/1.1)
  * Tesla now requires HTTP/2 for `owner-api.teslamotors.com/api/1/*` calls (June 2026)
  * Falls back to urllib for non-Tesla URLs or if httpx is not installed
* docs(windows): README updated with Windows setup troubleshooting — native Windows TLS, WSL2 WebKitGTK limitation, and alternatives (tesla_auth app, full Linux VM, remote authtoken)
* diagnostics: `cloudcheck` now reports platform-aware TLS behaviour on Windows

## v0.16.0 - Code Review Fixes: Correctness, Security, and Robustness

Full-codebase review sweep (see `docs/code-review-2026-07-03.md` for the complete findings). 104 new regression tests (227 passing, up from 123). No public API signatures or return shapes changed. Hardware-verified against production proxies with `proxy/regression_test.py`: all 76 non-control endpoints byte-compatible across TEDAPI WiFi, v1r+WiFi hybrid, Cloud, and FleetAPI modes.

* fix(core): `set_operation()`/`set_mode()` no longer silently lowers the real battery reserve — the reserve back-fill is now scale-aware per backend (raw for local, app-scale for cloud/fleetapi/tedapi) and guards an unreadable reserve
* fix(core): `alerts(alertsonly=False)` crashed with `TypeError` since introduction; device alerts now returned as `{device: alert}` dicts as documented
* fix(core): a fully-failed `connect()` no longer leaves the facade without a client (raw `AttributeError` on every call) or with a mutated fallback mode; `retry_modes` indefinite blocking documented
* fix(fleetapi): token refresh could permanently wedge the client via a stuck `refreshing` flag; now lock-based with proper error handling
* fix(fleetapi): reuse one HTTP/2 client (was a TLS handshake per request); never re-send a POST via the HTTP/1.1 fallback after it may have been transmitted (duplicate write commands); stop caching errors and unique history URLs
* fix(tedapi): `available_blocks` always 0 (read from wrong payload); `PINV_GridState` always None (copy-paste); PW3 vitals None-crashes; POD/PINV bounds guards; lock timeouts return cached data instead of raising; 429/5xx no longer misclassifies PW2 as PW3; sessions closed on reconnect and `close_session()` (note: `TESYNC--None--None`/`TESLA--None` vitals blocks are intentionally kept - `TESLA--None` carries the gateway DIN in `componentParentDin`)
* fix(cloud): `set_grid_charging`/`set_grid_export` returned a raw tuple; `post_api_operation` failed on partial payloads and `False` reserve; racy `_site_api` flag replaced with real per-name locks; sitefile parse failure falls back to auto-select
* fix(local): documented `poll(api, raw=True)` now works; negative caching (404/403/503) now actually suppresses re-requests; missing Content-Type and None firmware version no longer raise
* fix(security): credential files (`.pypowerwall.auth`, `.pypowerwall.fleetapi`, `.powerwall`, v1r RSA keys/tokens) created with `0600` permissions atomically; tokens/secrets redacted from debug logs
* fix(cli): `-local` without `-host` errors clearly instead of silently using cloud mode; `set -current` handles unavailable battery level
* feat(docs): new `AGENTS.md` and `DESIGN.md` (architecture, conventions, invariants for contributors and AI agents); README/API docs corrected against the code
* refactor: shared None-safe `lookup()` and mock-data decorator in `pypowerwall/helpers.py` (ends three-way copy drift; existing import paths preserved)
* Proxy hardened separately — see `proxy/RELEASE.md` t95
* Bump library version to `0.16.0` (minor bump to signal the breadth of behavioral fixes; no public API signatures or return shapes changed)

## v0.15.13 - Fleet API HTTP/2 Upgrade

* feat(fleetapi): upgrade Fleet API transport to HTTP/2 with TLS 1.3 (#338)
  * Proactively upgrades Fleet API transport to HTTP/2 — Fleet API currently works over HTTP/1.1, but HTTP/2 improves reliability and future-proofs against enforcement (Tesla has already enforced HTTP/2 on Owner API endpoints)
  * All 9 `requests` call sites in `fleetapi/fleetapi.py` replaced with `_http2_request()` helper
  * New HTTP/2 transport helpers: `_httpx_auth_verify()`, `_HTTP2Response`, `_http2_request()`
    * `_httpx_auth_verify()` — pins TLS 1.3 via `ssl.SSLContext` when available
    * `_HTTP2Response` — `requests.Response`-compatible wrapper for `httpx` responses (`.status_code`, `.text`, `.json()`, `.raise_for_status()`)
    * `_http2_request()` — unified request helper: tries HTTP/2 first, falls back to HTTP/1.1 on any error (logged as warning)
  * Form-encoded `data=dict` correctly routes to `httpx data=` kwarg; raw bytes/str use `content=`
  * `raise_for_status()` correctly distinguishes 4xx (Client Error) from 5xx (Server Error)
  * Follows same pattern as PR #324 (Cloud mode HTTP/2 upgrade in `teslapy/__init__.py`)
  * HTTP/2 enabled when `httpx[http2]>=0.27.0` is installed (already in `requirements.txt`); falls back to `requests` (HTTP/1.1) if unavailable
  * Hardware-validated against live PW3 (fw 26.18.1): Fleet API read, write (set/reset reserve), and protocol negotiation all confirmed ✅
* Bump library version to `0.15.13`

## v0.15.12 - Remote Setup and Cloud Auth Improvements

* fix(cloud): Docker/container headless setup no longer fails with 403 on first connect (#333)
  * Root cause confirmed: `owner-api.teslamotors.com` requires a **code-exchange AT** (from PKCE WebView login) to bootstrap the session. A "cold" refresh (RT used immediately with no prior code-exchange AT) is rejected with 403. Once the session is bootstrapped, normal RT-based refresh works — the service self-heals automatically after the initial ~8h AT expiry.
  * `authtoken` command now outputs **both** the Refresh Token (RT, valid 90 days) and Access Token (AT, valid ~8h) — RT shown first in both terminal output and window UI
  * macOS WebView success page redesigned: RT with green badge first, AT with yellow badge second, separate Copy RT / Copy AT buttons
  * `setup -headless` now prompts for RT first, then AT (required to bootstrap the session on first connect)
  * Both tokens are saved to the auth file; `connect()` uses the code-exchange AT directly on first connect
  * `connect()` now handles 401 (expired AT) by refreshing via RT and retrying — warm refresh works, so no manual token renewal needed after initial setup
  * `expires_at` in auth file now set to `now + expires_in` (real expiry, ~8h) when AT is saved, rather than always `0` — allows accurate expiry reporting in `cloudcheck` and auth file inspection
* feat(cloud): New `cloudcheck` diagnostics command for cloud mode troubleshooting
  * Checks Python, platform, OpenSSL version, TLS 1.3 support
  * Checks httpx and h2 installation and versions
  * Checks proxy environment variables
  * Decodes and validates auth file: detects empty AT, expired AT, and whether AT has code-exchange markers (`owner-api` aud, `x-enc` present)
  * Live connectivity test to `auth.tesla.com` and `owner-api.teslamotors.com` (HTTP/2 protocol check)
  * Optional token refresh test with informative failure messages explaining the code-exchange AT requirement
  * `cloudcheck -noconnect` skips live tests for offline validation
  * Adding `-debug` to `setup`, `cloudcheck`, or `authtoken` automatically prints a full environment diagnostics header (Python, platform, OpenSSL, httpx, h2, proxy vars) before running the command
* fix(cloud): Remove stale energy-scope comments and contradictory `SCOPES` documentation across `tesla_auth.py`, `teslapy/__init__.py`, `pypowerwall_cloud.py`, and `__main__.py`
  * Energy scopes (`energy_device_data`, `energy_cmds`) are NOT required and were a red herring
  * Updated `AUTH.md` Section 7 to mark RCA-6 (energy scopes) as **DISPROVEN** and document the confirmed root cause as RCA-8 (code-exchange vs refreshed AT)
* Bump library version to `0.15.12`

## v0.15.11 - HTTP/2 for Tesla Owner API Calls

* fix(cloud): Extend HTTP/2 support to all owner-api.teslamotors.com API calls, not just auth endpoints (#324) - t93
  * Tesla now requires HTTP/2 for `owner-api.teslamotors.com/api/1/*` endpoints, matching the auth.tesla.com requirement
  * Pin `httpx` Tesla auth/API transports to TLS 1.3 when possible, mirroring the TeslaMate fix path for Tesla endpoints while preserving explicit custom `verify` settings
  * `Tesla.request()` now routes owner-api calls through `httpx` with HTTP/2 when available, with automatic fallback to `requests` (HTTP/1.1)
  * `_request_http2` now forwards all session headers (`Content-Type`, `X-Tesla-User-Agent`, `User-Agent`) to httpx instead of a minimal subset — ensures Tesla receives the same fingerprint as the original requests session
  * Adds `_HTTP2Response` wrapper class for requests/httpx response compatibility
  * Fixes 403 errors during `setup` flow (sitelist retrieval) reported in Powerwall-Dashboard #779
  * Fixes 403 errors during normal cloud-mode polling (PRODUCT_LIST, SITE_DATA, etc.)
  * Requires `httpx[http2]>=0.27.0` — the `[http2]` extra installs `h2`, which is required for HTTP/2 support; without it, httpx silently falls back to HTTP/1.1

## v0.15.10 - Combined Reserve + Mode Control Endpoint

* feat(proxy): Optional companion parameters on `/control/reserve` and `/control/mode` POST endpoints to update both reserve and mode in a single `set_operation()` call (#308) - t90
  * `/control/reserve` now accepts optional `mode=$MODE` parameter — calls `set_operation(level, mode)` instead of `set_reserve(level)`
  * `/control/mode` now accepts optional `level=$RESERVE` parameter — calls `set_operation(level, mode)` instead of `set_mode(mode)`
  * Prevents duplicate Tesla audit-log entries caused by calling set_reserve + set_mode separately
  * Invalid companion values return a 400 error without making any Powerwall call (no silent fallback)
  * Full backward compatibility: omitting the companion parameter preserves original behavior
  * Added unit tests for all code paths (legacy single-value, combined, and invalid companion)
  * Updated proxy README with combined-request examples

## v0.15.9 - Improved Connection Error Diagnostics

* Fix: Promote connection failure messages from `debug` to `error`/`warning` log level so users see actionable diagnostics without enabling debug mode (#160)
  * Login failures in local mode now show `error`-level messages with specific guidance (check password, check network reachability)
  * Login errors now distinguish between auth failures (401/403 → "check password") and connectivity failures (other HTTP status → "check gateway reachability")
  * Connection attempt fallback messages (Local → FleetAPI → Cloud) promoted from `debug` to `warning` level, including the exception details
  * API timeout and connection errors during polling now log at `error` level with the affected endpoint and host
  * Connection refused errors include the specific exception message
* Fix: Final "Unable to connect to Powerwall" error message now includes guidance to verify host, credentials, and network connectivity, and suggests enabling debug logging for more detail
* Bump library version to `0.15.9`

## v0.15.8 - authpath Support for v1r Setup Files

* Fix: `python -m pypowerwall setup -v1r -authpath <dir>` now correctly writes all generated files into the specified directory instead of the current working directory
  * `tedapi_rsa_private.pem` and `tedapi_rsa_public.der` are written to `<authpath>/`
  * `fleet_tokens.json` (Fleet API path) is written to `<authpath>/`
  * `<authpath>/` directory is created automatically if it does not exist
* Fix: `python -m pypowerwall get -v1r -authpath <dir>` now auto-discovers `tedapi_rsa_private.pem` in `<authpath>/` when `-rsa_key_path` is not explicitly specified
  * Lookup order: `<authpath>/tedapi_rsa_private.pem` → `./tedapi_rsa_private.pem` → error with path hint
* Refactor: Removed stale `RSA_PRIVATE_KEY_FILE` and `RSA_PUBLIC_KEY_FILE` module-level globals from `v1r_register.py` — file paths are now resolved dynamically from `authpath` at call time
* Refactor: Removed stale `TOKENS_FILE` module-level global from `v1r_register.py` — tokens file path is now resolved from `authpath` and threaded through `step2_exchange_token(tokens_file=...)`
* Bump library version to `0.15.8`

## v0.15.7 - Grid Noise Suppression and v1r Owner API Login Fix

* Docs: Document Tesla cloud/FleetAPI 80% backup reserve limit
     * Added warning in README and CLI examples for `set -reserve` when using cloud or FleetAPI mode
     * CLI now prints a WARNING when attempting to set reserve above 80% in cloud/FleetAPI mode, and a NOTE if Tesla caps the actual value
     * Added v1r LAN mode example showing how to set reserve above 80%
* Feat: Add `PW_SITE_ZERO_THRESHOLD` environment variable to suppress phantom grid noise readings
  * When set to a positive integer value (in watts), site power readings with absolute value at or below the threshold are reported as 0
  * Applies to `/api/meters/aggregates` site power, `/csv`/`/csv/v2` grid power, and `/json` grid power endpoints
  * Useful for off-grid and night-time scenarios where sensor noise causes small non-zero grid readings (e.g. 5–15W phantom draw)
  * Default is `0` (disabled — no suppression)
* Proxy build t89
* For /json endpoint, None values are now preserved. Previously, the proxy converted None to 0 for numeric fields, which could cause confusion when distinguishing between true zero values and missing data. Now, if a field is None in the underlying API response, it will be returned as None in the /json output, allowing clients to handle missing data appropriately. The /csv and /csv/v2 endpoints continue to convert None to 0 for numeric fields to maintain consistent numeric output.
* Fix: v1r Owner API registration (`python -m pypowerwall setup -v1r` → option 1) now uses the native `tesla_auth` WebView PKCE flow instead of the broken `teslapy` browser redirect. The `tesla://` custom URL scheme callback is intercepted by the WebView, eliminating the "missing_code" login failure (#300, reported in discussion #299)
* Fix: Cached token lookup in `owner_api_login()` now selects the account matching the requested `email` argument instead of always using the first entry in `.pypowerwall.auth`
* Bump library version to `0.15.7`

## v0.15.6 - Reserve Percent Scaling Fix + CLI Redesign

* Fix: `set_operation()` reserve percent scaling — reverse Tesla App scaling (0–100%) to raw API scale (5–100%) only in TEDAPI v1r mode, avoiding incorrect round-trip values in cloud and FleetAPI modes
* Fix: Correctly handle `level=0` in `set_reserve()` via `level is not None` check
* Fix: Revert universal scaling from `set_operation()`; move raw conversion into `PyPowerwallTEDAPI.post_api_operation()` where it belongs
* Fix: FleetAPI `get_api_system_status_soe()` was returning `battery_level()` (Tesla App-scaled, 0–100% usable) directly as the raw SOE percentage — missing the reverse-scaling applied by the cloud backend. This caused `level()` (default `scale=False`) to return the already-scaled app value instead of the physical percentage, making FleetAPI SOC appear ~2% lower than v1r/TEDAPI for the same battery. Fix: apply `soe = (percentage_charged + 5/0.95) * 0.95` to convert app scale → raw, matching the cloud backend.
* Fix: `get` command now reports SOC using `level(scale=True)` — matching the Tesla app display (usable capacity, 0–100% of non-reserved energy) rather than the raw physical percentage including Tesla's 5% buffer reserve.
* Fix: FleetAPI config validation in `Powerwall.__init__()` — changed `os.access(file, W_OK)` check (fails when file doesn't exist) to check directory writability when config file is absent, preventing spurious `PyPowerwallInvalidConfigurationParameter` on first-time setup
* Feat: CLI (`python -m pypowerwall`) redesigned for consistency across all connection modes
    * Replace string `-mode` flag on `get` (which clashed with `set -mode`) with explicit boolean connection flags: `-local`, `-cloud`, `-fleetapi`, `-tedapi`, `-v1r` — available on both `get` and `set`
    * **Backward compat:** `get -mode <value>` still accepted with a deprecation warning; e.g. `get -mode v1r` behaves identically to `get -v1r`
    * Add `-host`, `-password`, `-gw_pwd`, `-rsa_key_path` credential flags to `get` and `set` subcommands
    * Add global `-debug` and `-authpath` flags (via shared parent parser) available to every subcommand
    * `setup` subcommand now handles all auth flows: default/`-cloud` (Tesla Owners API), `-fleetapi` (Fleet API wizard), `-v1r` (RSA key registration) — replacing the now-deprecated `fleetapi` top-level command
    * `get` output expanded: adds `firmware`, `grid_status`, and `time_remaining` fields; `None` values display as `N/A` in text/CSV output
    * Pre-flight checks in `get` and `set`: if `-cloud` or `-fleetapi` is specified but the required config file is missing, a clear error message with setup instructions is printed before any connection attempt
    * Connection check (`is_connected()`) now runs before the output banner — no partial output on failure
    * `fleetapi` top-level command shows deprecation warning and points to `setup -fleetapi`; `login` command shows deprecation warning and exits
* Docs: Update `README.md` CLI section — new command list with global flags, connection mode flag reference table, examples for all 5 connection modes, updated setup commands (`fleetapi` → `setup -fleetapi`, `setup -v1r`)
* Release prep:
     * Bump library version to `0.15.6`
     * Update proxy pinned dependency to `pypowerwall==0.15.6`

## v0.15.5 - Native Python Tesla Authentication + v1r Key Verification Fixes

* Feat: Replace external `tesla-auth` binary dependency with native Python Tesla authentication — no more platform-specific binary downloads
* Feat: New `setup` command handles authentication and site selection in a single flow using a native WebView popup window (macOS, Windows, Linux)
* Feat: New `authtoken` command for obtaining a refresh token on a local machine, then using it on a remote/headless server
* Fix: Cross-platform WebView interception of `tesla://auth/callback` using WKWebView (macOS), WebView2 (Windows), and WebKit2GTK (Linux)
* Fix: `v1r_register.py` now verifies the specific newly-registered RSA key rather than any key in the authorized clients list — prevents false VERIFIED result when only the Tesla app key is verified (fixes #274)
* Fix: `tedapi_v1r.py` now detects and clearly logs `client authorization not verified` inner-payload errors, with actionable instructions to complete physical key verification — previously silently returned `None` with no diagnostic output
* Release prep:
     * Bump library version to `0.15.5`

## v0.15.4 - CLI Enhancements and Safety Guards

* Feat: `pypowerwall tedapi` CLI now accepts `-host HOST`, `-gw_pwd GW_PWD`, `-v1r`, `-password PASSWORD`, `-rsa_key_path RSA_KEY_PATH`, and `-wifi_host WIFI_HOST` flags, enabling full PW3 wired LAN (v1r) access directly from the command line
* Feat: `go_off_grid()` now requires `confirm=True` to prevent accidental islanding — calling without the flag logs an error and returns `None`
* Fix: Unsupported-method error logs in `go_off_grid()` and `reconnect_grid()` now include the backend class name for easier diagnosis
* Add: Unit tests for `go_off_grid()` confirm guard and CLI v1r argument forwarding/password derivation
* Release prep:
     * Bump library version to `0.15.4`
     * Update proxy pinned dependency to `pypowerwall==0.15.4`

## v0.15.3 - PW3 No-Solar None Handling

* Update scanner to use cidr by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/266
* Add go_off_grid() and reconnect_grid() for Powerwall island mode control by @bolagnaise in https://github.com/jasonacox/pypowerwall/pull/277
* Fix: Prevent `TypeError` in Powerwall 3 TEDAPI vitals parsing when `PCH_PvVoltage*` or `PCH_PvCurrent*` signals are `None` on systems without solar panels - by @anopheles in https://github.com/jasonacox/pypowerwall/pull/278
     * `get_pw3_vitals()` now guards `None` values before performing `> 0` comparisons
     * PV measured voltage, current, and power now safely report `0` when the gateway returns missing PV values
     * Prevents downstream failures in endpoints derived from PW3 vitals, including `/api/meters/aggregates`
     * Adds regression coverage for PW3 systems without solar panels so the no-solar path no longer raises and remains locked in by tests

* Release prep:
     * Bump library version to `0.15.3`
     * Update proxy pinned dependency to `pypowerwall==0.15.3`
     * Fix PyPI upload cleanup script to remove `pypowerwall.egg-info` instead of stale `tinytuya.egg-info`

## v0.15.2 - Minor Fixes

* v0.15.2 - Protobuf Support by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/276
* Fix: Remove `<5` upper cap on `protobuf` runtime dependency — constraint is now `protobuf>=4.25.1`; pb2 files generated with 4.25.x are compatible with 5.x, 6.x, and 7.x runtimes (confirmed and tested up to 7.34.1) and the cap was causing pip conflicts for users with newer protobuf versions installed (e.g. via TensorFlow)

## v0.15.1 - Code Quality and Build Pipeline Improvements

* Fix: Remove duplicate stub methods `get_grid_charging()` and `get_grid_export()` in `pypowerwall_tedapi.py` that were left over from a merge — the real implementations (reading/writing config via v1r transport) were already present and being shadowed
* Fix: Update `pwsimulator` `stub.py` to use `ssl.SSLContext` API replacing the removed `ssl.wrap_socket()` call, which caused the simulator container to silently exit on Python 3.12+
* Fix: Remove `linux/arm/v7` platform from `pwsimulator` Docker build (`upload.sh`) — platform is no longer supported
* Fix: Correct protobuf runtime dependency — `protobuf>=3.20.0` was misleading; set floor to `protobuf>=4.25.1` (the `<5` upper cap added here was subsequently lifted in v0.15.2)
* Add: `.pylintrc` with `[MESSAGES CONTROL]` disable list (restored), `[SIMILARITIES]` config, and `ignore-paths` to skip auto-generated `*_pb2.py` files
* Add: `tools/gen_proto.sh` — script to regenerate all `*_pb2.py` files from `.proto` sources using pinned `grpcio-tools`
* Add: `tools/requirements-tools.txt` — pinned dev tools (`grpcio-tools<1.64`, `protobuf<5`) to ensure pb2 files are generated consistently with a compatible protobuf version
* Add: `.pre-commit-config.yaml` — pre-commit hooks for protobuf regeneration and `pylint -E` checks on `pypowerwall/` and `proxy/` before every commit
* Add: `.github/workflows/check-protobuf.yml` — CI workflow to verify committed `*_pb2.py` files are in sync with their `.proto` sources

## v0.15.0 - Powerwall 3 Wired LAN TEDAPI Support (v1r)

* Docs: Note FleetAPI/Cloud mode requirement for `get_grid_charging()` and `get_grid_export()` - by @jasonacox-sam in https://github.com/jasonacox/pypowerwall/pull/268
* Insert empty `battery_blocks` array if missing to prevent downstream KeyError - by @zi0r in https://github.com/jasonacox/pypowerwall/pull/269
* Fix: Prevent shared-state race condition in stubs via factory functions - by @woofiwoof in https://github.com/jasonacox/pypowerwall/pull/270
    * `API_METERS_AGGREGATES_STUB` and `API_SYSTEM_STATUS_STUB` in cloud/fleetapi/tedapi stubs were module-level mutable dicts; concurrent polling of multiple gateways caused threads to overwrite each other's data
    * Replaced module-level dicts with `_..._TEMPLATE` constants and factory functions that return `copy.deepcopy()` copies, ensuring each gateway gets an independent data structure
* Add `/tedapi/v1r` transport for Powerwall 3 wired LAN access without requiring WiFi connection to `192.168.91.1` - by @nalditopr in https://github.com/jasonacox/pypowerwall/pull/265
    * New `tedapi_v1r.py` RSA-signed transport class — handles TLV payload construction, PKCS1v15+SHA512 signing, RoutableMessage protobuf wrapping, and Bearer token authentication
    * New `tedapi_combined_pb2.py` — compiled protobuf definitions for v1r message format (`RoutableMessage`, `MessageEnvelope`, etc.)
    * New `pypowerwall register` CLI command (and `v1r_register.py` script) for generating an RSA-4096 key pair and registering it with the Powerwall via Tesla Owner API (default) or Fleet API OAuth
    * `Powerwall()` constructor accepts new `rsa_key_path` parameter — when provided alongside `password`/`gw_pwd`, the library automatically selects v1r mode
    * `gw_pwd` (full 10-character QR code password from the Powerwall sticker) auto-derives the last-5-character Basic API password, simplifying configuration
    * Proxy server supports new `PW_RSA_KEY_PATH` environment variable to pass the RSA key path through to `Powerwall()`
    * `cryptography` package added to `install_requires` for RSA key loading and signing
    * Full feature parity with WiFi TEDAPI (mode 4): config, status, vitals, firmware version, power, battery level, grid status, per-device vitals, and component queries
    * LAN control support — set backup reserve, operation mode, grid charging, and grid export directly over the wired LAN via v1r filestore config writes (no cloud API needed)
    * WiFi fallback transport — when both wired LAN and WiFi TEDAPI are available, v1r mode transparently uses WiFi for follower queries; mode string dynamically reflects active transports (e.g., `Local (v1r+wifi+control)`)
    * Requires the Powerwall 3 leader's ethernet port to be on a routable subnet (`10.42.1.x/24` is the TEG's dedicated wired interface); see PR notes for bridge setup examples
* Drop `linux/arm/v7` (32-bit ARMv7) platform support from the pypowerwall proxy Docker container builds

## v0.14.10 - Host Port Support

* Add support for `host:port` format in the `host` parameter for local mode connections - Fix for https://github.com/jasonacox/pypowerwall/issues/254
     * Allows specifying a non-standard HTTPS port (e.g. `192.168.1.50:8443` or `powerwall.local:8443`)
     * Defaults to port 443 when no port is specified in `host`
     * Enables travel router / NAT proxy setups where multiple Powerwall gateways are each mapped to distinct `ip:port` endpoints on the local network
     * Updated `_validate_init_configuration()` to validate bare host first, then strip the optional port suffix — prevents false port detection inside IPv6 addresses (e.g. `2001:db8::1` is never mistaken for a host with port `1`)
     * Fixed TEDAPI hybrid mode detection in `PyPowerwallLocal` to match `192.168.91.1:443` (explicit default port) in addition to bare `192.168.91.1`, ensuring TEDAPI activates for direct gateway connections regardless of whether the port is stated
     * URL construction in local and TEDAPI modes naturally handles `host:port` format via `https://{host}/...` string formatting
     * Note: IPv6 addresses are accepted by validation but full URL construction support (bracket notation per RFC 2732) is not yet implemented

## v0.14.9 - TEDAPI Voltage Calculation Fix

* Fix `compute_LL_voltage()` function to handle `None` voltage values in grid down scenarios - Fix for https://github.com/jasonacox/Powerwall-Dashboard/issues/683
     * Added `None` value handling in three-phase voltage calculations to prevent `TypeError` exceptions
     * Converts `None` voltage parameters to `0` before performing arithmetic operations
     * Prevents crashes when grid is down and voltage readings are unavailable
     * Added comprehensive unit tests to verify None handling behavior for all scenarios: grid down (all None), mixed None/valid values, and numeric-only values

## v0.14.8 - CLI Tool and PW3 Power Vitals Fix

* Add standalone `pypowerwall` command-line tool - installed automatically with pip
     * Added `entry_points` to `setup.py` to create console script
     * Refactored `__main__.py` to use a `main()` function as entry point
     * Users can now run `pypowerwall` command directly instead of `python -m pypowerwall`
     * Maintains backward compatibility - both methods work identically
     * Available commands: `pypowerwall scan`, `pypowerwall setup`, `pypowerwall fleetapi`, `pypowerwall get`, `pypowerwall set`, `pypowerwall version`
* Fix Powerwall 3 power output (PINV_Pout) in vitals for TEDAPI mode
     * Corrected signal source from `PCH_AcRealPowerAB` to `PCH_BatteryPower` for accurate per battery power reporting

## v0.14.7 - Reserve Level 0 Fix

* Fix bug where `pypowerwall set` command could not set battery reserve level to 0 - Fix by @ParaAdBellum in https://github.com/jasonacox/pypowerwall/pull/252
     * Changed default value for `-reserve` argument from `None` to `-1` (sentinel value)
     * Updated conditional checks to compare against `-1` instead of using truthiness evaluation
     * Previously, `not args.reserve` evaluated to `True` when reserve was set to 0, preventing the reserve from being set

## v0.14.6 - Firmware 25.42.2+ Support

* Add gzip decompression support for firmware 25.42.2+ TEDAPI responses - Fix by @bolagnaise in https://github.com/jasonacox/pypowerwall/pull/251
     * Gateway firmware 25.42.2 and later returns gzip-compressed responses for DIN and other TEDAPI endpoints
     * Added `decompress_response()` helper function to handle both compressed and uncompressed responses transparently
     * Updated all TEDAPI methods (`get_din()`, `get_config()`, `get_status()`, `get_device_controller()`, `get_firmware_version()`, `get_components()`, `get_battery_block()`) to decompress responses
     * Added error handling for UnicodeDecodeError in DIN decode operation to gracefully handle corrupted or invalid responses
     * Maintains backward compatibility with older firmware versions that return uncompressed responses

## v0.14.5 - Performance Improvements

* Performance Fixes and Improvements
     * Fix variable shadowing in `grid_status()` method: renamed `type` parameter to `output_type` to avoid shadowing Python's built-in `type()` function
     * Add backward compatibility for deprecated `type` parameter - still supported but `output_type` is now preferred
     * Fix return type annotation for `extract_grid_status()` method: changed from `str` to `Optional[str]` to accurately reflect function can return `None`
     * Add age and expiration logging to TEDAPI Components cache for debugging consistency
     * Proxy server build t86
* Rename incorrect unit test file (test_ prefix indicates unit tests) by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/226
* Simple reliability improvements by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/240
* Add aggregation unit tests by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/241
* Update all Python versions to be consistent by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/243
* Add CSV endpoint tests to the proxy by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/244
* Add csv/v2 endpoint unit tests by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/245

## v0.14.4 - Expansion Pack Energy Fix

* **Fix expansion pack energy data** by processing all BMS components in TEDAPI responses - Fix by @rlerdorf in https://github.com/jasonacox/pypowerwall/pull/239
* Refactored `get_pw3_vitals()` to process ALL BMS components and match them to batteries (main units and expansions) via HVP serial numbers
* Creates individual TEPOD entries in `/vitals` for each battery including expansion packs with accurate energy data
* Simplified `/pod` endpoint by removing complex subtraction-based energy calculation logic - expansion packs now appear automatically as TEPOD entries
* Refactored `get_blocks()` to retrieve expansion pack energy from vitals TEPOD entries instead of making separate API calls
* Improves data accuracy and reduces API calls by directly extracting expansion pack energy from parallel BMS/HVP component arrays
* Validated on system with 2 Powerwall 3 units (Leader + Follower) and 1 Expansion Pack showing correct energy values for all three batteries
* Proxy server build t85

## v0.14.3 - Battery Expansion and Grid Meter Support

* Add support for Powerwall 3 Battery Expansion Packs in TEDAPI mode - Fix for issue https://github.com/jasonacox/pypowerwall/issues/227 by @rlerdorf in https://github.com/jasonacox/pypowerwall/pull/236
* Battery expansions (battery-only units without inverters) now appear in `/pw/battery_blocks`, `/pod`, and `/tedapi/battery` endpoints
* The `get_blocks()` function now reads battery expansion data from the configuration's `battery_expansions` array and fetches BMS component data for each expansion unit
* Expansion units are identified with `"Type": "BatteryExpansion"` and include battery capacity metrics (`nominal_energy_remaining`, `nominal_full_pack_energy`)
* Inverter-related fields (`pinv_state`, `p_out`, `v_out`, etc.) are set to `None` for expansions since they don't have inverters
* The `/pod` endpoint calculates expansion pack energy by subtracting known battery values from system totals (individual expansion BMS data not exposed by Tesla)
* For multiple expansion packs, the first entry shows combined totals with "(combined)" suffix, while additional entries show `null` values
* Add support for TEMSA/MSA grid meter data in `/vitals` endpoint for Powerwall 3 systems
* PW3 MSA data fallback: reads from `components.msa` with signals array format conversion when `esCan.bus.MSA` is unavailable
* Voltage reference mapping: converts PW3 ground-referenced voltages (VL1G/VL2G/VL3G) to neutral-referenced (VL1N/VL2N/VL3N) for consistency
* TEMSA block in vitals now includes grid voltage, current, and instantaneous power readings for PW3 backup switches

## v0.14.2 - Misc

* Move API lock timeout messages in exponential backoff mechanism to DEBUG logging to prevent noise for regular users.

## v0.14.1 - Test Coverage & battery_blocks Fix

* Add unit tests expanding coverage: version parsing, core Powerwall methods (poll json output, power aggregation, grid_status numeric/json, alerts fallback path, set_operation validation, reserve/mode helpers, temps, site_name)
* Introduce stub client in tests for deterministic, offline execution
* Fix `battery_blocks()` KeyError when vitals include a battery serial not present in `/api/system_status` `battery_blocks` (create entry lazily)
* Harden battery temperature/state merge logic for mixed firmware/mode scenarios
* No public API changes


## v0.14.0 - Fix for TeslaPy and FleetAPI

* Pin and embed TeslaPy code patch directly into pyPowerwall to help address issue setting Powerwall Mode - see https://github.com/jasonacox/pypowerwall/issues/197
* FleetAPI CLI: improved error handling, skips incomplete sites, clearer output to help address issue where token can't be refreshed due to missing energy_site_id key - see https://github.com/jasonacox/pypowerwall/issues/198

## v0.13.2 - TEDAPI Lock Optimization

* Fix TEDAPI lock contention issues causing "Timeout for locked object" errors under concurrent load by optimizing cache-before-lock pattern in core functions
* Optimize `get_config()`, `get_status()`, `get_device_controller()`, `get_firmware_version()`, `get_components()`, and `get_battery_block()` to check cache before acquiring expensive locks
* Remove redundant API call in `pypowerwall_tedapi.py` `get_api_system_status()` method
* Fix proxy server KeyError when status response missing version or git_hash keys by using defensive key access
* Fix proxy server KeyError when auth dictionary missing AuthCookie or UserRecord keys in cookie mode
* Improve performance and reduce lock timeout errors in multi-threaded environments like the pypowerwall proxy server
* Enhance `compute_LL_voltage()` function with voltage threshold detection (100V) to better handle single-phase systems with residual voltages on inactive legs, as well as split- and three-phase systems.
* These optimizations benefit all methods that depend on the core TEDAPI functions, including `vitals()`, `get_blocks()`, and `get_battery_blocks()`

## v0.13.1 - TEDAPI Battery Blocks

* Fix missing battery_blocks data on PW3 with Multiple Powerwalls in Local Mode in https://github.com/jasonacox/pypowerwall/issues/131
* Fix errant API base URL check. by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/185
* Update TEDAPI to pull battery blocks from vitals for PW3 Systems by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/184

## v0.13.0 - TEDAPI Updates

* Additional values /json endpoint by @erikgieseler in https://github.com/jasonacox/pypowerwall/pull/176
* Use Neurio for TEDAPI data when Tesla Remote Meter is not present by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/157
* Initial simple unit test by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/181
* Add connection pool to TEDAPI by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/177
* Add METER_Z (Backup Switch) data to vitals and aggregates data - See https://github.com/jasonacox/Powerwall-Dashboard/discussions/629#discussioncomment-13284217
* Update and add documentation helps: contributor, conduct and API (python and proxy)
* Fix logic for aggregates API for consolidated voltage and current data by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/183

## v0.12.12 - Multiple PW3 Fix

* Bug Fix - Logic added in https://github.com/jasonacox/pypowerwall/pull/169 does not iterate through all PW3 strings. This adds logic to handle multiple PW3 string sets. Reported in https://github.com/jasonacox/pypowerwall/issues/172. 

## v0.12.11 - Error Handling

* Fix error handling in component data handling in TEDAPI.

## v0.12.10 - Power Flow and Other Fixes

* Add PROXY_BASE_URL option for reverse proxying by @mccahan in https://github.com/jasonacox/pypowerwall/pull/155
* Fix issue with power flow animation showing blank when opened more than once by @mccahan in https://github.com/jasonacox/pypowerwall/pull/156
* Add fan speed routes and update proxy version to t71 by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/161
* Fix for
TypeError: PyPowerwallTEDAPI.vitals() got an unexpected keyword argument 'force' by @F1p in https://github.com/jasonacox/pypowerwall/pull/164
* Catch error condition when components payload is empty or malformed. Bug in extract_fan_speeds() reported by by @jgleigh in jasonacox/Powerwall-Dashboard#392 and https://github.com/jasonacox/pypowerwall/issues/167
* Issue #162: add /pw/XXX endpoints to expose Powerwall() API methods by @JohnJ9ml in https://github.com/jasonacox/pypowerwall/pull/166
* PW3 Vitals Fix - Switch from using device specific URI https://{GW_IP}/tedapi/device/{pw_din}/v1 to https://{GW_IP}/tedapi/v1 - Corrects 502 error condition on some Powerwall 3 systems by @johncuthbertuk in https://github.com/jasonacox/pypowerwall/pull/169

## v0.12.9 - Fan Speeds

* Add PVAC fan speeds to TEDAPI vitals monitoring (PVAC_Fan_Speed_Actual_RPM and PVAC_Fan_Speed_Target_RPM).

## v0.12.8 - TEDAPI Improvements

* Avoid divide by zero when nominalFullPackEnergyWh is zero by @rlpm in https://github.com/jasonacox/pypowerwall/pull/150
* Add thread locking to TEDAPI by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/148

## v0.12.7 - SystemConnectedToGrid Fix

* Alerts in extract_grid_status can be None. Block this edge case. #145

## v0.12.6 - Aggregates Data

* Updated aggregates call to include site current (METER_X) and external PV inverter data in solar (METER_Y). Reported in Issue #140.

## v0.12.5 - Normalize Alerts

* Fix an issue in TEDAPI where the grid status is not accurately reported in certain edge cases. Now, only the "SystemConnectedToGrid" alert will appear if it is present in alerts API. This update also eliminates the risk of duplicate and redundant ("SystemGridConnected") alerts and normalizes this specific alert. PR https://github.com/jasonacox/pypowerwall/pull/139 by @Nexarian

## v0.12.4 - Neurio Vitals

* Update proxy for /csv/v2 API support by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/134
* Fix CTS data retrieval in TEDAPI vitals processor #136 by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/137
* Fix bug in TEDAPI vitals processor that was not pulling in all Neurio CTS data. Issue reported in https://github.com/jasonacox/Powerwall-Dashboard/discussions/578#discussioncomment-12034018 and tracked in https://github.com/jasonacox/pypowerwall/issues/136.

## v0.12.3 - Custom GW IP

* Fix TEDAPI URL from constant GW_IP to constructor selectable host gw_ip by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/129 - The hard-coded 192.168.91.1 for the TEDAPI internal endpoint doesn't always work if you're using NAT. This change enables support for this use-case.
* See https://gist.github.com/jasonacox/91479957d0605248d7eadb919585616c?permalink_comment_id=5373785#gistcomment-5373785 for NAP implementation example.

## v0.12.2 - Cache Expiration Fix

* Fix bug in cache expiration timeout code that was not honoring pwcacheexpire setting. Raised by @erikgiesele in https://github.com/jasonacox/pypowerwall/issues/122 - PW_CACHE_EXPIRE=0 not possible? (Proxy)
* Add WARNING log in proxy for settings below 5s.
* Change TEDAPI config default timeout from 300s to 5s and link to pwcacheexpire setting.

## v0.12.1 - Scanner Update

* Large-scale refactor of scan function by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/117
     - Function `scan()` returns a list of the discovered devices for use as a utility function.
     - Ability to silence output for use as a utility.
     - Improve performance of multi-threaded scan by using a Queue.
     - General code flow improvements and encapsulation.
     - Add ability to work with standalone inverters.

```python
from pypowerwall.scan import scan
found_devices = scan(interactive = False)
```


## v0.12.0 - Add Controller Data

* TEDAPI: Add `get_device_controller()` to get device data which includes Powerwall THC_AmbientTemp data. Credit to @ygelfand for discovery and reported in https://github.com/jasonacox/Powerwall-Dashboard/discussions/392#discussioncomment-11360474
* Updated `vitals()` to include Powerwall temperature data. 
* Proxy Updated to t66 to include API response for /tedapi/controller.
* Remove Negative Solar Values [Option] by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/113
* Solar-Only Cloud Access - Fix errors with site references by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/115

## v0.11.1 - PW3 and FleetAPI Bugfix

* TEDAPI: Fix bug with activeAlerts logic causing errors on systems with multiple Powerwall 3's. Identified by @rmotapar in https://github.com/jasonacox/Powerwall-Dashboard/issues/387#issuecomment-2336431741 
* FleetAPI: Fix connect() to handle non-energy products in the getsites response. Identified by @gregrahn in https://github.com/jasonacox/pypowerwall/issues/111

## v0.11.0 - Add PW3 Vitals

* Add polling of Powerwall 3 Devices to pull in PW3 specific string data, capacity, voltages, frequencies, and alerts. 
* This creates mock TEPOD, PVAC and PVS compatible payloads available in vitals().

Proxy URLs updated for PW3:
* http://localhost:8675/vitals 
* http://localhost:8675/help (verify pw3 shows True) 
* http://localhost:8675/tedapi/components
* http://localhost:8675/tedapi/battery  

## v0.10.10 - Add Grid Control

* Add a function and command line options to allow user to get and set grid charging and exporting modes (see https://github.com/jasonacox/pypowerwall/issues/108).
* Supports FleetAPI and Cloud modes only (not Local mode)

#### Command Line Examples

```bash
# Connect to Cloud
python3 -m pypowerwall setup # or fleetapi

# Get Current Settings
python3 -m pypowerwall get

# Turn on Grid charging
python3 -m pypowerwall set -gridcharging on

# Turn off Grid charging
python3 -m pypowerwall  set -gridcharging off

# Set Grid Export to Solar (PV) energy only
python3 -m pypowerwall set -gridexport pv_only

# Set Grid Export to Battery and Solar energy
python3 -m pypowerwall set -gridexport battery_ok

# Disable export of all energy to grid
python3 -m pypowerwall set -gridexport never
```

#### Programming Examples

```python
import pypowerwall

# FleetAPI Mode
PW_HOST=""
PW_EMAIL="my@example.com"
pw = pypowerwall.Powerwall(host=PW_HOST, email=PW_EMAIL, fleetapi=True)

# Get modes
pw.get_grid_charging()
pw.get_grid_export()

# Set modes
pw.set_grid_charging("on") # set grid charging mode (on or off)
pw.set_grid_export("pv_only")   # set grid export mode (battery_ok, pv_only, or never)
```

## v0.10.9 - TEDAPI Voltage & Current

* Add computed voltage and current to `/api/meters/aggregates` from TEDAPI status data.
* Fix error in `num_meters_aggregated` calculation in aggregates.

## v0.10.8 - TEDAPI Firmware Version

* Add TEDAPI `get_firmware_version()` to poll Powerwall for firmware version. Discovered by @geptto in https://github.com/jasonacox/pypowerwall/issues/97. This function has been integrated into pypowerwall existing APIs (e.g. `pw.version()`)
* Add TEDAPI `get_components()` and `get_battery_block()` functions which providing additional Powerwall 3 related device vital information for Powerwall 3 owners. Discovered by @lignumaqua in https://github.com/jasonacox/Powerwall-Dashboard/discussions/392#discussioncomment-9864364. The plan it to integrate this data into the other device vitals payloads (TODO).

## v0.10.7 - Energy History

* FleetAPI - Add `get_history()` and `get_calendar_history()` to return energy, power, soe, and other history data.

```python
import pypowerwall

pw = pypowerwall.Powerwall(host=PW_HOST, email=PW_EMAIL, fleetapi=True)
pw.client.fleet.get_calendar_history(kind="soe")
pw.client.fleet.get_history(kind="power")
```

## v0.10.6 - pyLint Cleanup

* Minor Bug Fixes - TEDAPI get_reserve() fix to address unscaled results.
* pyLint Cleanup of Code

## v0.10.5 - Minor Fixes

* Fix for TEDAPI "full" (e.g. Powerwall 3) mode, including `grid_status` bug resulting in false reports of grid status, `level()` bug where data gap resulted in 0% state of charge and `alerts()` where data gap from tedapi resulted in a `null` alert.
* Add TEDAPI API call locking to limit load caused by concurrent polling.
* Proxy - Add battery full_pack and remaining energy data to `/pod` API call for all cases.

## v0.10.4 - Powerwall 3 Local API Support

* Add local support for Powerwall 3 using TEDAPI. 
* TEDAPI will activate in `hybrid` (using TEDAPI for vitals and existing local APIs for other metrics) or `full` (all data from TEDAPI) mode to provide better Powerwall 3 support.
* The `full` mode will automatically activate when the customer `password` is blank and `gw_pwd` is set.
* Note: The `full` mode will provide less metrics than `hybrid` mode since Powerwall 2/+ systems have additional APIs that are used in `hybrid` mode to fetch additional data

```python
import pypowerwall

# Activate HYBRID mode (for Powerwall / 2 / + systems)
pw = pypowerwall.Powerwall("192.168.91.1", password=PASSWORD, email=EMAIL, gw_pwd=PW_GW_PWD)

# Activate FULL mode (for all systems including Powerwall 3)
pw = pypowerwall.Powerwall("192.168.91.1", gw_pwd=PW_GW_PWD)
```

Related:
* #97 
* https://github.com/jasonacox/Powerwall-Dashboard/issues/387


## v0.10.3 - TEDAPI Connect Update

* Update `setup.py` to include dependencies on `protobuf>=3.20.0`.
* Add TEDAPI `connect()` logic to better validate Gateway endpoint access.
* Add documentation for TEDAPI setup.
* Update CLI to support TEDAPI calls.
* Proxy t60 - Fix edge case where `/csv` API will error due to NoneType inputs.
* Add TEDAPI argument to set custom GW IP address.

```bash
# Connect to TEDAPI and pull data
python3 -m pypowerwall tedapi

# Direct call to TEDAPI class test function (optional password)
python3 -m pypowerwall.tedapi GWPASSWORD
python3 -m pypowerwall.tedapi --debug
python3 -m pypowerwall.tedapi --gw_ip 192.168.91.1 --debug
```

## v0.10.2 - FleetAPI Hotfix

* Fix FleetAPI setup script as raised in https://github.com/jasonacox/pypowerwall/issues/98.
* Update FleetAPI documentation and CLI usage.

## v0.10.1 - TEDAPI Vitals Hotfix

* Fix PVAC lookup error logic in TEDAPI class vitals() function.
* Add alerts and other elements to PVAC TETHC TESYNC vitals.
* Update vitals Neurio block to include correct location and adjust RealPower based on power scale factor.

## v0.10.0 - New Device Vitals

* Add support for `/tedapi` API access on Gateway (requires connectivity to 192.168.91.1 GW and Gateway Password) with access to "config" and "status" data.
* Adds drop-in replacement for depreciated `/vitals` API and payload using the new TEDAPI class. This allows easy access to Powerwall device vitals.
* Proxy update to t58 to support TEDAPI with environmental variable `PW_GW_PWD` for Gateway Password. Also added FleetAPI, Cloud and TEDAPI specific GET calls, `/fleetapi`, `/cloud`, and `/tedapi` respectively.

```python
# How to Activate the TEDAPI Mode
import pypowerwall

gw_pwd = "GW_PASSWORD" # Gateway Passowrd usually on QR code on Gateway

host = "192.168.91.1" # Direct Connect to GW
pw = pypowerwall.Powerwall(host,password,email,timezone,gw_pwd=gw_pwd)
print(pw.vitals())
```

```python
# New TEDAPI Class
import pypowerwall.tedapi

tedapi = pypowerwall.tedapi.TEDAPI("GW_PASSWORD")

config = tedapi.get_config()
status = tedapi.get_status()

meterAggregates = status.get('control', {}).get('meterAggregates', [])
for meter in meterAggregates:
    location = meter.get('location', 'Unknown').title()
    realPowerW = int(meter.get('realPowerW', 0))
    print(f"   - {location}: {realPowerW}W")

```

## v0.9.1 - Bug Fixes and Updates

* Fix bug in time_remaining_hours() and convert print statements in FleetAPI to log messages.
* Fix CLI bug related to `site_id` as raised by @darroni in https://github.com/jasonacox/pypowerwall/issues/93
* Add CLI option for local mode to get status:

```bash
python -m pypowerwall get -host 10.1.2.3 -password 'myPassword'
```

## v0.9.0 - FleetAPI Support

* v0.9.0 - Tesla (official) FleetAPI cloud mode support by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/91 - This adds the FleetAPI class and mapping for pypowerwall.
* FleetAPI setup provided by module CLI: `python -m pypowerwall fleetapi`
* Adds `auto_select` mode for instatiating a Powerwall connection: `local` mode, `fleetapi` mode and `cloud` mode. Provides `pw.mode` class variable as the mode selected.

```python
    import pypowerwall

    # Option 1 - LOCAL MODE - Credentials for your Powerwall - Customer Login
    password="password"
    email="email@example.com"
    host = "10.0.1.123"               # Address of your Powerwall Gateway
    timezone = "America/Los_Angeles"  # Your local timezone

    # Option 2 - FLEETAPI MODE - Requires Setup
    host = password = email = ""
    timezone = "America/Los_Angeles" 

    # Option 3 - CLOUD MODE - Requires Setup
    host = password = ""
    email='email@example.com'
    timezone = "America/Los_Angeles"
 
    # Connect to Powerwall - auto_select mode (local, fleetapi, cloud)
    pw = pypowerwall.Powerwall(host,password,email,timezone,auto_select=True)

    print(f"Connected to Powerwall with mode: {pw.mode}")
```

## v0.8.5 - Solar Only

* Fix bug with setup for certain Solar Only systems where setup process fails. Identified by @hulkster in https://github.com/jasonacox/Powerwall-Dashboard/discussions/475

## v0.8.4 - Set Reserve

* Updated `set_reserve(level)` logic to handle levels from 0 to 100. Identified by @spoonwzd in #85

## v0.8.3 - Error Handling

* Added additional error handling logic to clean up exceptions.
* Proxy: Added command APIs for setting backup reserve and operating mode.

## v0.8.2 - 503 Error Handling

* Added 5 minute cooldown for HTTP 503 Service Unavailable errors from API calls.
* Proxy: Added DISABLED API handling logic.

## v0.8.1 - Set battery reserve, operation mode

* Added `get_mode()`, `set_mode()`,`set_reserve()`,and `set_operation()` function to set battery operation mode and/or reserve level by @emptywee in https://github.com/jasonacox/pypowerwall/pull/78. Likely won't work in the local mode.
* Added basic validation for main class `__init__()` parameters (a.k.a. user input).
* Better handling of 401/403 errors from Powerwall in local mode.
* Handle 50x errors from Powerwall in local mode.
* Added Alerts for Grid Status `alerts()`.
* New command line functions (`set` and `get`):

```
usage: PyPowerwall [-h] {setup,scan,set,get,version} ...

PyPowerwall Module v0.8.1

options:
  -h, --help            show this help message and exit

commands (run <command> -h to see usage information):
  {setup,scan,set,get,version}
    setup               Setup Tesla Login for Cloud Mode access
    scan                Scan local network for Powerwall gateway
    set                 Set Powerwall Mode and Reserve Level
    get                 Get Powerwall Settings and Power Levels
    version             Print version information
```

## v0.8.0 - Refactoring

* Refactored pyPowerwall by @emptywee in https://github.com/jasonacox/pypowerwall/pull/77 including:
  * Moved Local and Cloud based operation code into respective modules, providing better abstraction and making it easier to maintain and extend going forward.
  * Made meaning of the `jsonformat` parameter consistent across all method calls (breaking API change).
  * Removed Python 2.7 support.
  * Cleaned up code and adopted a more pythoinc style.
* Fixed battery_blocks() for non-vitals systems.

## v0.7.12 - Cachefile, Alerts & Strings

* Added logic to pull string data from `/api/solar_powerwall` API if vitals data is not available by @jasonacox in #76.
* Added alerts from `/api/solar_powerwall` when vitals not present by @DerickJohnson in #75. The vitals API is not present in firmware versions > 23.44, this provides a workaround to get alerts.
* Allow customization of the cachefile location and name by @emptywee in #74 via `cachefile` parameter.

```python
# Example
import pypowerwall
pw = pypowerwall.Powerwall(
     host="10.1.2.30",
     password="secret",
     email="me@example.com",
     timezone="America/Los_Angeles",
     pwcacheexpire=5, 
     timeout=5, 
     poolmaxsize=10,
     cloudmode=False, 
     siteid=None, 
     authpath="", 
     authmode="cookie",
     cachefile=".powerwall",
     )
```

## v0.7.11 - Cooldown Mode

* Updated logic to disable vitals API calls for Firmware 23.44.0+
* Added rate limit detection and cooldown mode to allow Powerwall gateway time to recover.

## v0.7.10 - Cache 404 Responses

* Add cache and extended TTL for 404 responses from Powerwall as identified in issue https://github.com/jasonacox/Powerwall-Dashboard/issues/449. This will help reduce load on Powerwall gateway that may be causing rate limiting for some users (Firmware 23.44.0+).

## v0.7.9 - Cloud Grid Status

* Bug fix for correct grid status for Solar-Only systems on `cloud mode` (see https://github.com/jasonacox/Powerwall-Dashboard/issues/437)

## v0.7.8 - Cloud Fixes

* Fix enumeration of energy sites during `cloud mode` setup to handle incomplete sites with Unknown names or types by @dcgibbons in https://github.com/jasonacox/pypowerwall/pull/72 
* Proxy t41 Updates - Bug fixes for Solar-Only systems using `cloud mode` (see https://github.com/jasonacox/Powerwall-Dashboard/issues/437).

## v0.7.7 - Battery Data and Network Scanner

* Proxy t40: Use /api/system_status battery blocks data to augment /pod and /freq macro data APIs by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/67 thanks to @ceeeekay in https://github.com/jasonacox/Powerwall-Dashboard/discussions/402#discussioncomment-8193776
* Network Scanner: Improve network scan speed by scanning multiple hosts simultaneously by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/67. The number of hosts to scan simultaneously can be adjusted using the optional `-hosts=` argument (default = 30, maximum = 100), e.g. `python -m pypowerwall scan -hosts=50`

## v0.7.6 - 404 Bug Fix

* Fix Critical Bug - 404 HTTP Status Code Handling (Issue https://github.com/jasonacox/pypowerwall/issues/65).

## v0.7.5 - Cloud Mode Setup

* Added optional email address argument to Cloud Mode setup (`python -m pypowerwall setup -email=<email>`) by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/64 to streamline Powerwall-Dashboard setup script.
* Updated network scanner output to advise Powerwall 3 is supported in Cloud Mode by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/64

## v0.7.4 - Bearer Token Auth

pyPowerwall Updates
* This release adds the ability to use a Bearer Token for Authentication for the local Powerwall gateway API calls. This is selectable by defining `authmode='token'` in the initialization. The default mode uses the existing `AuthCookie` and `UserRecord` method.

```python
import pypowerwall

pw = pypowerwall.Powerwall(HOST, PASSWORD, EMAIL, TIMEZONE, authmode="token")
```

Proxy
* The above option is extended to the pyPowerwall Proxy via the environmental variable `PW_AUTH_MODE` set to cookie (default) or token.

Powerwall Network Scanner
* Added optional IP address argument to network scanner by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/63. The Scan Function can now accept an additional argument `-ip=` to override the host IP address detection (`python -m pypowerwall scan -ip=192.168.1.100`). This may be useful where the host IP address/network cannot be detected correctly, for instance if pypowerwall is running inside a container.

## v0.7.3 - Cloud Mode Setup

* Setup will now check for `PW_AUTH_PATH` environmental variable to set the path for `.pypowerwall.auth` and `.pypowerwall.site` by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/62
* Proxy t37 - Move signal handler to capture SIGTERM when proxy halts due to config error by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/62. This ensures a containerized proxy will exit without delay when stopping or restarting the container.

## v0.7.2 - Cloud Auth Path

* Add pypowerwall setting to define path to cloud auth cache and site files in the initialization. It will default to current directory.
* Add pypowerwall setting to define energy site id in the initialization. It will default to None.

```python
import pypowerwall

pw = pypowerwall.Powerwall(email="email@example.com",cloudmode=True,siteid=1234567,authpath=".auth")
```

* Proxy will now use `PW_AUTH_PATH` as an environmental variable to set the path for `.pypowerwall.auth` and `.pypowerwall.site`.
* Proxy also has `PW_SITEID` as an environmental variable to set `siteid`.

## v0.7.1 - Tesla Cloud Mode

* Simulate Powerwall Energy Gateway via Tesla Cloud API calls. In `cloudmode` API calls to pypowerwall APIs will result in calls made to the Tesla API to fetch the data.

Cloud Mode Setup - Use pypowerwall to fetch your Tesla Owners API Token

```bash
python3 -m pypowerwall setup

# Token and site information stored in .pypowerwall.auth and .pypowerwall.site
```

Cloud Mode Code Example

```python
import pypowerwall
pw = pypowerwall.Powerwall(email="email@example.com",cloudmode=True)
pw.power()
# Output: {'site': 2977, 'solar': 1820, 'battery': -3860, 'load': 937}
pw.poll('/api/system_status/soe')
# Output: '{"percentage": 26.403205103271222}'
```

* Added new API function to compute estimated backup time remaining on the battery: `get_time_remaining()`

## v0.6.4 - Power Flow Animation

Proxy t29 Updates
* Default page rendered by proxy (http://pypowerwall:8675/) will render Powerflow Animation
* Animation assets (html, css, js, images, fonts, svg) will render from local filesystem instead of pulling from Powerwall TEG portal.
* Start prep for possible API removals from Powerwall TEG portal (see NOAPI settings)

Powerwall Network Scanner
* Adjust scan timeout default to 1,000ms (1s) to help with more consistent scans.

## v0.6.3 - Powerwall 3 Scan

* Added scan detection for new Powerwall 3 systems. API discovery is still underway so pypowerwall currently does not support Powerwall 3s. See https://github.com/jasonacox/Powerwall-Dashboard/issues/387

```
$ python3 -m pypowerwall scan

pyPowerwall Network Scanner [0.6.3]
Scan local network for Tesla Powerwall Gateways

    Your network appears to be: 10.0.1.0/24

    Enter Network or press enter to use 10.0.1.0/24: 

    Running Scan...
      Host: 10.0.1.2 ... OPEN - Not a Powerwall
      Host: 10.0.1.5 ... OPEN - Found Powerwall 3 [Currently Unsupported]
      Host: 10.0.1.8 ... OPEN - Not a Powerwall
      Host: 10.0.1.9 ... OPEN - Found Powerwall 3 [Currently Unsupported]
      Done                           

Discovered 2 Powerwall Gateway
     10.0.1.5 [Powerwall-3] Firmware Currently Unsupported - See https://tinyurl.com/pw3support
     10.0.1.9 [Powerwall-3] Firmware Currently Unsupported - See https://tinyurl.com/pw3support
```

## v0.6.2b - Proxy Grafana Support

* Proxy t28: Add a `grafana-dark` style for `PW_STYLE` settings to accommodate placing as iframe in newer Grafana versions (e.g. v9.4.14). See https://github.com/jasonacox/Powerwall-Dashboard/discussions/371.

## v0.6.2a - Proxy Graceful Exit

* Add alert PVS_a036_PvArcLockout by @JordanBelford in https://github.com/jasonacox/pypowerwall/pull/33
* Create `tessolarcharge.py` by @venturanc in https://github.com/jasonacox/pypowerwall/pull/36 &  https://github.com/jasonacox/pypowerwall/pull/37 & https://github.com/jasonacox/pypowerwall/pull/38
* Fix typos and spelling errors by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/40
* Add alert definitions per #42 by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/43
* Added two PVAC Alerts by @niabassey in https://github.com/jasonacox/pypowerwall/pull/46
* Added Firmware 23.28.1 to README.md by @niabassey in https://github.com/jasonacox/pypowerwall/pull/48
* Add proxy gracefully exit with SIGTERM by @rcasta74 in https://github.com/jasonacox/pypowerwall/pull/49

## v0.6.2 - Proxy Cache-Control

* PyPI 0.6.2
* Update docs for alerts by @DerickJohnson in https://github.com/jasonacox/pypowerwall/pull/29 and  https://github.com/jasonacox/pypowerwall/pull/30
* Fix Cache-Control no-cache header and allow for setting max-age, fixes #31 by @dkerr64 in https://github.com/jasonacox/pypowerwall/pull/32

## v0.6.1 - Add Grid Conditions

* PyPI 0.6.1
* Added new `SystemMicroGridFaulted` and `SystemWaitForUser` grid conditions to `grid_status()` function. Both are mapped to "DOWN" conditions. Discovery by @mcbrise in https://github.com/jasonacox/Powerwall-Dashboard/issues/158#issuecomment-1441648085.
* Revised error handling of SITE_DATA request due to issues noted in #12 when multiple sites are linked to the Tesla account by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/25
* Proxy t24: Added new `/alerts/pw` endpoint with dictionary/object response format by @DerickJohnson in https://github.com/jasonacox/pypowerwall/pull/26

## v0.6.0 - Add Persistent HTTP Connections

* PyPI 0.6.0
* Added HTTP persistent connections for API requests to Powerwall Gateway by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/21
* Requests to Gateway will now re-use persistent http connections which reduces load and increases response time.
* Uses default connection `poolmaxsize=10` to align with Session object defaults. Note: pool use applies to multi-threaded use of pyPowerwall only, e.g. as with the pyPowerwall Proxy Server.
* Added env `PW_POOL_MAXSIZE` to proxy server to allow this to be controlled (persistent connections disabled if set to zero).
* Added env `PW_TIMEOUT` to proxy server to allow timeout on requests to be adjusted.

## v0.5.1 - Fix grid_status() Off-Grid Map

* PyPI 0.5.1
* Add FreeBSD-specific installation instructions by @zi0r in https://github.com/jasonacox/pypowerwall/pull/18
* Add `grid_status()` responses for syncing to off-grid by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/19

## v0.5.0 - Exception Handling for Powerwall Connection

* PyPI 0.5.0
* Added additional exception handling to help identify connection and login errors.
* Added `is_connected()` function to test for a successful connection to the Powerwall.
* Added firmware version to command line network scan (`python -m pypowerwall scan`)

[Proxy Server](https://github.com/jasonacox/pypowerwall/tree/main/proxy#pypowerwall-proxy-server) Updates (Build t16) - See [here](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md#release-notes) for more Proxy Release notes.

* Add support for backup switch by @nhasan in https://github.com/jasonacox/pypowerwall/pull/12
* Add passthrough to Powerwall web interface and customize for iFrame displays by @danisla in https://github.com/jasonacox/pypowerwall/pull/14
* Remove scrollbars from web view by @danisla in https://github.com/jasonacox/pypowerwall/pull/15
* Add support for specifying a bind address by @zi0r in https://github.com/jasonacox/pypowerwall/pull/16
* Add shebang for direct execution by @zi0r in https://github.com/jasonacox/pypowerwall/pull/17

## v0.4.0 - Cache Bypass Option and New Functions

* PyPI 0.4.0
* Added parameter to `poll()` to force call (ignore cache)
* Added `alerts()` function to return an array of device alerts.
* Added `get_reserve()` function to return battery reserve setting.
* Added `grid_status()` function to return state of grid.
* Added `system_status()` function to return system status.
* Added `battery_blocks()` function to return battery specific information.
* Expanded class to include settings for cache expiration (`pwcacheexpire`) and connection `timeout`.

```python
# Force Poll
pw.poll('/api/system_status/soe',force=True)
'{"percentage":100}'

# Powerwall Alerts
pw.alerts()
['PodCommissionTime', 'GridCodesWrite', 'GridCodesWrite', 'FWUpdateSucceeded', 'THC_w155_Backup_Genealogy_Updated', 'PINV_a067_overvoltageNeutralChassis', 'THC_w155_Backup_Genealogy_Updated', 'PINV_a067_overvoltageNeutralChassis', 'PVS_a018_MciStringB', 'SYNC_a001_SW_App_Boot']

# Battery Reserve Setting
pw.get_reserve()
20.0

# State of Grid
pw.grid_status()
'UP'
```

## v0.3.0 - Device Vitals Alerts and Attributes

* PyPI 0.3.0
* Added alerts and additional attributes from `vitals()` output.
* Note: API change to `vitals()` output for dependant systems.

## v0.2.0 - Tesla Protocol Buffer Scheme Update

* PyPI 0.2.0
* Breaking change to Protobuf schema (PR #2) including:
* Files `tesla.proto` and `tesla_pb2.py`
* Impacted output from function `vitals()` and [examples/vitals.py](examples/vitals.py).

## v0.1.4 - Battery Level Percentage Scaling

* PyPI 0.1.4
* Changed "Network Scan" default timeout to 400ms for better detection.
* Added Tesla App style "Battery Level Percentage" Conversion option to `level()` to convert the level reading to the 95% scale used by the App. This converts the battery level percentage to be consistent with the Tesla App:

```python
>>> pw.level(scale=True)
39.971429212508326
>>> pw.level()
42.972857751882906
```

## v0.1.3 - Powerwall Temps

* PyPI 0.1.3
* Added `temp()` function to pull Powerwall temperatures.

```python
pw.temps(jsonformat=True)
```

```json
{
    "TETHC--2012170-25-E--TGxxxxxxxxxxxx": 17.5,
    "TETHC--3012170-05-B--TGxxxxxxxxxxxx": 17.700000000000003
}
```

## v0.1.2 - Error Handling and Proxy Stats

* PyPI 0.1.2
* Added better Error handling for calls to Powerwall with debug info for timeout and connection errors.
* Added timestamp stats to pypowerwall proxy server.py (via URI /stats and /stats/clear)

pyPowerwall Debug
```
DEBUG:pypowerwall [0.1.2]

DEBUG:loaded auth from cache file .powerwall
DEBUG:Starting new HTTPS connection (1): 10.0.1.2:443
DEBUG:ERROR Timeout waiting for Powerwall API https://10.0.1.2/api/devices/vitals
```

Proxy Stats
```json
{"pypowerwall": "0.1.2", "gets": 2, "errors": 3, "uri": {"/stats": 1, "/soe": 1}, "ts": 1641148636, "start": 1641148618, "clear": 1641148618}
```

## v0.1.1 - New System Info Functions

* PyPI 0.1.1
* Added stats to pypowerwall proxy server.py (via URI /stats and /stats/clear)
* Added Information Functions: `site_name()`, `version()`, `din()`, `uptime()`, and `status()`.

```python
     # Display System Info
     print("Site Name: %s - Firmware: %s - DIN: %s" % (pw.site_name(), pw.version(), pw.din()))
     print("System Uptime: %s\n" % pw.uptime())
```

## v0.1.0 - Vitals Data

* PyPI 0.1.0
* Added *protobuf* handling to support decoding the Powerwall Device Vitals data (requires protobuf package)
* Added function `vitals()` to pull Powerwall Device Vitals
* Added function `strings()` to pull data on solar panel strings (Voltage, Current, Power and State)

```python
     vitals = pw.vitals(jsonformat=False)
     strings = pw.strings(jsonformat=False, verbose=False)
```

## v0.0.3 - Binary Poll Function, Proxy Server and Simulator

* PyPI 0.0.3
* Added Proxy Server - Useful for metrics gathering tools like telegraf (see [proxy](proxy/)]).
* Added Powerwall Simulator - Mimics Powerwall Gateway responses for testing (see [pwsimulator](pwsimulator/)])
* Added raw binary poll capability to be able to pull *protobuf* formatted payloads like '/api/devices/vitals'.

```python
     payload = pw.poll('/api/devices/vitals')
```

## v0.0.2 - Scan Function

* PyPI 0.0.2
* pyPowerwall now has a network scan function to find the IP address of Powerwalls
```bash
# Scan Network for Powerwalls
python -m pypowerwall scan
```
Output Example:
```
pyPowerwall Network Scanner [0.0.2]
Scan local network for Tesla Powerwall Gateways

    Your network appears to be: 10.0.3.0/24

    Enter Network or press enter to use 10.0.3.0/24: 

    Running Scan...
      Host: 10.0.3.22 ... OPEN - Not a Powerwall
      Host: 10.0.3.45 ... OPEN - Found Powerwall 1234567-00-E--TG123456789ABC
      Done                           

Discovered 1 Powerwall Gateway
     10.0.1.45 [1234567-00-E--TG123456789ABC]
```

## v0.0.1 - Initial Release

* PyPI 0.0.1
* Initial Beta Release 0.0.1
