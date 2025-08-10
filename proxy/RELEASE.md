## pyPowerwall Proxy Release Notes


### Proxy t81 (9 Aug 2025)

* Improve error logging: show poll() target URI on bad payload (TypeError) instead of generic message.
* Build descriptive function/endpoint name only when an error occurs (no added overhead on success path).
* Refactor safe_pw_call exception handlers to remove redundant code. No API or config changes.


### Proxy t80 (24 Jul 2025)

* **Connection Health Robustness Fix** ([#651](https://github.com/jasonacox/Powerwall-Dashboard/issues/651#issuecomment-3114228456)):
  - Fixed issue where `consecutive_failures` in connection health tracking could reset to zero even when the Powerwall connection was not restored.
  - Now, health tracking only resets on true, fresh connection success (not when returning cached or fallback responses).
  - Prevents misleading health status and ensures degraded mode is only exited after real network/API recovery.
  - Improves reliability of `/health` and monitoring endpoints under extended network outages or degraded conditions.

* **Internal Refactoring**:
  - Audited and updated health tracking logic in `safe_pw_call` and `safe_endpoint_call` wrappers to ensure correct behavior.
  - No user-facing API changes, but improved accuracy for health metrics and logs.

* **Documentation**:
  - Updated release notes to clarify health tracking behavior and robustness improvements for network error handling.


### Proxy t79 (16 Jul 2025)

* **Enhanced Health Endpoint**: Added pypowerwall version and proxy build information to `/health` endpoint for better version tracking and debugging
  - Health response now includes: `"pypowerwall": "0.13.2 Proxy t79"` combining version and build info in consistent format

* **Code Quality**: Added flake8 configuration (`.flake8`) and cleaned up trailing whitespace issues
  - Configured to ignore common acceptable lint errors (E501, W503, E722)
  - Fixed trailing whitespace issues throughout proxy codebase

### Proxy t78 (14 Jul 2025)

* Power flow animation update: Show an image of a Powerwall 3 instead of a Powerwall 2 if it is a PW3 by @JEMcats in https://github.com/jasonacox/pypowerwall/pull/193

### Proxy t77 (11 Jul 2025)

* **TEDAPI Lock Optimization and Error Handling**: Enhanced proxy stability and performance with comprehensive fixes for TEDAPI-related issues.
  - **Fixed KeyError exceptions** in proxy server when status response missing `version` or `git_hash` keys by implementing defensive key access with `.get()` method
  - **Fixed KeyError exceptions** when auth dictionary missing `AuthCookie` or `UserRecord` keys in cookie mode, now uses safe fallbacks
  - **TEDAPI Performance Improvements**: Optimized core TEDAPI functions (`get_config`, `get_status`, `get_device_controller`, `get_firmware_version`, `get_components`, `get_battery_block`) with cache-before-lock pattern to reduce lock contention
  - **Removed redundant API calls** in TEDAPI wrapper functions to improve response times
  - **Enhanced multi-threading support** for concurrent proxy requests with reduced lock timeout errors
  - **Improved error resilience** for different connection modes (local vs TEDAPI) that return varying data structures

* **Enhanced Health Monitoring**: Added comprehensive endpoint statistics tracking for better observability and debugging.
  - **Endpoint Call Statistics**: Added tracking of successful and failed API calls per endpoint with success rate calculations
  - **Enhanced `/health` endpoint**: Now includes detailed statistics showing:
    - Total calls, successful calls, and failed calls per endpoint
    - Success rate percentage for each endpoint
    - Time since last success and last failure for each endpoint
    - Overall proxy response counters (total_gets, total_posts, total_errors, total_timeouts)
  - **Improved `/health/reset` endpoint**: Now also clears endpoint statistics along with health counters and cache
  - **Automatic tracking**: All endpoints using `safe_endpoint_call()` automatically tracked (includes `/aggregates`, `/soe`, `/vitals`, `/strings`, etc.)

### Proxy t76 (6 Jul 2025)

* **Advanced Network Robustness Features**: Added comprehensive connection health monitoring and graceful degradation for improved reliability under poor network conditions, especially for frequent polling scenarios (e.g., telegraf every 5s).

  - **Connection Health Monitoring** (`PW_HEALTH_CHECK=yes`, default enabled):
    - Tracks consecutive failures, total error/success counts, and connection status
    - Automatically enters "degraded mode" after 5 consecutive failures
    - Exits degraded mode after 3 consecutive successes
    - Provides health status via `/health` endpoint for external monitoring

  - **Fail-Fast Mode** (`PW_FAIL_FAST=yes`, default disabled):
    - When connection is in degraded state, immediately returns cached/empty data
    - Prevents timeout delays for rapid polling scenarios
    - Reduces system load during extended network outages

  - **Graceful Degradation** (`PW_GRACEFUL_DEGRADATION=yes`, default enabled):
    - Maintains cache of last successful responses (TTL: 5 minutes)
    - Returns cached data when fresh data is unavailable
    - Ensures telegraf and other pollers receive valid data structures even during outages
    - Automatic cache size management (max 50 entries)

  - **Telegraf-Optimized Fallbacks**:
    - `/aggregates` returns minimal valid power structure on failure
    - `/soe` returns `{"percentage": 0}` on failure
    - CSV endpoints return zero values instead of empty responses
    - Maintains data type consistency for monitoring tools

  - **Enhanced API Endpoints**:
    - `/health` - Connection health status and feature configuration
    - `/health/reset` - Reset health counters and clear cache
    - `/stats` - Now includes connection health metrics when enabled

  - **Improved Error Handling**:
    - Enhanced `safe_pw_call()` with health tracking integration
    - New `safe_endpoint_call()` wrapper with automatic caching for JSON endpoints
    - Better separation of network vs API errors for targeted handling

  - **Configuration Options**:
    - `PW_FAIL_FAST=yes/no` - Enable fail-fast mode (default: no)
    - `PW_GRACEFUL_DEGRADATION=yes/no` - Enable cached fallbacks (default: yes)  
    - `PW_HEALTH_CHECK=yes/no` - Enable health monitoring (default: yes)

  - **Operational Benefits**:
    - Reduced timeout delays during network issues (fail-fast mode)
    - Improved telegraf reliability with consistent data structures
    - Better visibility into connection issues via health endpoints
    - Automatic recovery detection and logging
    - Memory-efficient caching with automatic cleanup

* **Weak WiFi / Network Error Optimization**: Added specialized handling for environments with poor network connectivity.
  - **Enhanced Exception Coverage**: Now catches all requests and urllib3 timeout/connection exceptions (ReadTimeout, ConnectTimeout, MaxRetryError, etc.)
  - **Rate Limiting**: Network errors are rate-limited to prevent log spam (default: 5 errors per minute per function)
  - **Summary Reporting**: Periodic summary reports (every 5 minutes) show network error counts instead of individual error logs
  - **Configurable Suppression**: 
    - `PW_SUPPRESS_NETWORK_ERRORS=yes` - Completely suppress individual network error logs (summary only)
    - `PW_NETWORK_ERROR_RATE_LIMIT=N` - Set max network errors logged per minute per function (default: 5)
  - **Thread Safety**: Added proper locking for all global statistics and error tracking
  - **Log Level Optimization**: Network errors use INFO level, API errors use WARNING level to reduce noise

* **Enhanced Error Handling**: Implemented global exception handling for all pypowerwall function calls to provide clean error logging instead of deep stack traces.
  - Added `safe_pw_call()` wrapper function that catches and handles pypowerwall-specific exceptions
  - Catches connection errors (ConnectionError, TimeoutError, OSError) and logs descriptive messages
  - Catches pypowerwall API exceptions (InvalidConfigurationParameter, TEDAPI, FleetAPI errors)
  - Maintains API functionality through graceful error responses (returns "TIMEOUT!" for failed calls)
  - Improves debugging with clean, descriptive error messages identifying the failing function
  - Error Statistics: Automatically increments `proxystats['errors']` for API errors and `proxystats['timeout']` for connection/timeout errors
  - Example log messages: `"Powerwall API Error in poll: Connection timeout"`, `"Connection Error in vitals: Network unreachable"`

### Proxy t75 (12 Jun 2025)

* Fix errant API base URL check - This PR fixes an API base URL check by removing an unreachable validation branch.

### Proxy t74 (12 May 2025)

* Add additional data elements to `/json` route:

```json
{
  "grid": 2423,
  "home": 3708.5000000000005,
  "solar": 1307,
  "battery": -26,
  "soe": 70.88757396449705,
  "grid_status": 1,
  "reserve": 70.0,
  "time_remaining_hours": 8.076041526223541,
  "full_pack_energy": 42250,
  "energy_remaining": 29950.000000000004,
  "strings": {
    "A": {
      "State": "Pv_Active",
      "Voltage": 188,
      "Current": 1.5999999999999996,
      "Power": 300.79999999999995,
      "Connected": true
    },
    "B": {
      "State": "Pv_Active",
      "Voltage": 318,
      "Current": 1.2999999999999998,
      "Power": 413.3999999999999,
      "Connected": true
    },
    "C": {
      "State": "Pv_Active",
      "Voltage": 152,
      "Current": 1.7499999999999998,
      "Power": 265.99999999999994,
      "Connected": true
    },
    "D": {
      "State": "Pv_Active",
      "Voltage": 190,
      "Current": 1.7499999999999998,
      "Power": 332.49999999999994,
      "Connected": true
    },
    "E": {
      "State": "Pv_Active",
      "Voltage": 0,
      "Current": 0.09999999999999964,
      "Power": 0.0,
      "Connected": true
    },
    "F": {
      "State": "Pv_Active_Parallel",
      "Voltage": 0,
      "Current": 0,
      "Power": 0,
      "Connected": true
    }
  }
}
```

### Proxy t73 (10 May 2025)

* Add `/json` route to return basic metrics:

```json
{
    "grid": -3,
    "home": 917.5,
    "solar": 5930,
    "battery": -5030,
    "soe": 61.391932759907306,
    "grid_status": 1,
    "reserve": 20,
    "time_remaining_hours": 17.03651226158038
}
```

### Proxy t72 (16 Apr 2025)

* Add routes to map library functions into `/pw/` APIs (e.g. /pw/power)

### Proxy t71 (6 Apr 2025)

* Add routes for fan speeds: `/fans` and `/fans/pw` (simple enumerated values for dashboard)
* Add API routes /pw/* to expose Powerwall() API methods (e.g. /pw/power) by @JohnJ9ml in https://github.com/jasonacox/pypowerwall/pull/166

### Proxy t70 (25 Mar 2025)

pyPowerwall v0.12.9:
* Add PVAC fan speeds to TEDAPI vitals monitoring (PVAC_Fan_Speed_Actual_RPM and PVAC_Fan_Speed_Target_RPM).
* Avoid divide by zero when nominalFullPackEnergyWh is zero by @rlpm in #150
* Add thread locking to TEDAPI by @Nexarian in #148

Proxy:
* Add PROXY_BASE_URL option for reverse proxying by @mccahan in https://github.com/jasonacox/pypowerwall/pull/155
* Fix issue with visualization showing blank with multiple tabs by @mccahan in https://github.com/jasonacox/pypowerwall/pull/156

### Proxy t69 (15 Mar 2025)

* pyPowerwall v0.12.7 - Added new data features (Neurio Vitals, Aggregates Data) and fixed a critical issue (SystemConnectedToGrid Fix) while normalizing Alerts.
* Add option to get CSV headers by @mccahan in https://github.com/jasonacox/pypowerwall/pull/149

```bash
curl http://localhost:8675/csv/v2?headers
curl http://localhost:8675/csv?headers
```

### Proxy t68 (20 Jan 2025)

* pyPowerwall v0.12.3 - Adds Custom GW IP for TEDAPI. 
* Add new API /csv/v2 which extends /csv by adding grids status (1/0) and battery reserve (%)setting:

```python
# Grid,Home,Solar,Battery,Battery_Level,Grid_Status,Reserve
```

### Proxy t67 (26 Dec 2024)

* pyPowerwall v0.12.2 - Fix bug in cache timeout code that was not honoring pwcacheexpire setting. Raised by @erikgiesele in https://github.com/jasonacox/pypowerwall/issues/122 - PW_CACHE_EXPIRE=0 not possible? (Proxy)
* Add WARNING log in proxy for settings below 5s.

### Proxy t66

* pyPowerwall v0.12.0

### Proxy t65 (22 Nov 2024)

* Add `PW_NEG_SOLAR` config option and logic to remove negative solar values for /aggregates and /csv APIs
* Update http://pypowerwall:8675/stats and http://pypowerwall:8675/help to show config data.
* PR https://github.com/jasonacox/pypowerwall/pull/113

### Proxy t64 (1 Sep 2024)

* Add PW3 features for pypowerwall v0.11.0

Updated APIs with PW3 payloads: 
* http://localhost:8675/vitals
* http://localhost:8675/help (pw3 flag True/False) 
* http://localhost:8675/tedapi/components
* http://localhost:8675/tedapi/battery  

### Proxy t63 (15 Jun 2024)

* Address pyLint code cleanup and minor command mode fixes.

### Proxy t62 (13 Jun 2024)

* Add battery full_pack and remaining energy data to `/pod` API call for all cases.

### Proxy t61 (9 Jun 2024)

* Fix 404 bug that would throw error when user requested non-supported URI.
* Add TEDAPI mode to stats.

### Proxy t60 (9 Jun 2024)

* Add error handling for `/csv` API to accommodate `None` data points.

### Proxy t59 (8 Jun 2024)

* Minor fix to send less ambiguous debug information during client disconnects.
* Update Neurio block to include correct location and adjust RealPower based on power scale factor.

### Proxy t58 (2 Jun 2024)

* Add support for pypowerwall v0.10.0 and TEDAPI with environmental variable `PW_GW_PWD` for Gateway Password. This unlocks new device vitals metrics (as seen with `/vitals`). It requires the user to have access to the Powerwall Gateway at 192.168.91.1, either via WiFi for by adding a route to their host or network. 
* Add FleetAPI, Cloud and TEDAPI specific GET calls, `/fleetapi`, `/cloud`, and `/tedapi` respectively.

### Proxy t57 (15 May 2024)

* Add pypowerwall v0.9.0 capabilities, specifically supporting Tesla FleetAPI for cloud connections (main data and control).

### Proxy t56 (14 May 2024)

* Fix error with site_name on Solar Only systems.

### Proxy t55 (4 May 2024)

* Fix `/pod` API to add `time_remaining_hours` and `backup_reserve_percent` for cloud mode.
* Replaced t54 - Move control to POST see https://github.com/jasonacox/pypowerwall/issues/87
* Added GET APIs to retrieve backup reserve and operating mode settings
* Added POST command APIs to set backup reserve and operating mode settings. **Requires setting `PW_CONTROL_SECRET` for the proxy. Use with caution.**

```bash
# Set Mode
export MODE=self_consumption
export RESERVE=20
export PW_CONTROL_SECRET=mySecretKey

curl -X POST -d "value=$MODE&token=$PW_CONTROL_SECRET" http://localhost:8675/control/mode

# Set Reserve
curl -X POST -d "value=$RESERVE&token=$PW_CONTROL_SECRET" http://localhost:8675/control/reserve

# Read Settings
curl http://localhost:8675/control/mode
curl http://localhost:8675/control/reserve
```

### Proxy t53 (11 Apr 2024)

* Add DISABLED API handling logic.

### Proxy t52 (5 Apr 2024)

*  Update to pyPowerwall proxy v0.8.1

### Proxy t51 (18 Mar 2024)

* Update to pypowerwall 0.8.0
* Minor bug fixes.

### Proxy t43 (17 Mar 2024)

* Update to pypowerwall 0.7.12 and add `/api/solar_powerwall` to ALLOWLIST. Using new API, proxy is able to produce `/alerts/` list and some `/strings` data for newer Firmware version (>23.44) that no longer support the vitals API.

### Proxy t42 (3 Mar 2024)

* Add Power Flow Animation style (set `PW_STYLE="solar"`) for Solar-Only display. Removes the Powerwall image and related text to display a Grid + Solar + Home powerflow animation.

<img width="443" alt="image" src="https://github.com/jasonacox/Powerwall-Dashboard/assets/836718/37fa7f7b-d4f9-4240-82bc-a81ba2f798c7">

### Proxy t41 (25 Feb 2024)

* Bug fixes for Solar-Only systems using `cloud mode` (see https://github.com/jasonacox/Powerwall-Dashboard/issues/437).

### Proxy t40 (20 Jan 2024)

* Use /api/system_status battery blocks data to augment /pod and /freq macro data APIs.

### Proxy t39 (12 Jan 2024)

* Fix Critical Bug - 404 HTTP Status Code Handling (Issue https://github.com/jasonacox/pypowerwall/issues/65).

### Proxy t36 (30 Dec 2023)

* Add `PW_AUTH_PATH` to set location for cloud auth and site files.

### Proxy t35 (29 Dec 2023)

* Add `cloudmode` support for pypowerwall v0.7.1. 

### Proxy t32 (20 Dec 2023)

* Fix "flashing animation" problem by matching `hash` variable in index.html to firmware version `git_hash`.

### Proxy t29 (16 Dec 2023)

* Default page rendered by proxy (http://pypowerwall/) will render Powerflow Animation
* Animation assets (html, css, js, images, fonts, svg) will render from local filesystem instead of pulling from Powerwall TEG portal.
* Start prep for possible API removals from Powerwall TEG portal (see NOAPI settings)

### Proxy t28 (14 Oct 2023)

* Add a `grafana-dark` style for `PW_STYLE` settings to accommodate placing as iframe in newer Grafana versions (e.g. v9.4.14). See https://github.com/jasonacox/Powerwall-Dashboard/discussions/371.

### Proxy t27 (23 Sep 2023)

* Add Add Graceful Exit with SIGTERM to fix condition where container does not stop gracefully as raised in https://github.com/jasonacox/pypowerwall/pull/49 by @rcasta74 .

### Proxy t26 (4 May 2023)

* Update default `PW_POOL_MAXSIZE` from 10 to 15 to help address "Connection pool is full" errors reported by @jgleigh in https://github.com/jasonacox/Powerwall-Dashboard/discussions/261 - May the 4th be with you!

### Proxy t25 (21 Mar 2023)

* Fix Cache-Control no-cache header and added option to set max-age, fixes #31 by @dkerr64 in https://github.com/jasonacox/pypowerwall/pull/32

### Proxy t24 (16 Jan 2023)

* Added new alerts endpoint ('/alerts/pw') for retrieving the data in dictionary/object format (helps with telegraf usage).

### Proxy t23 (8 Jan 2023)

* Updated to Python 3.10

### Proxy t22 (23 Nov 2022)

* Added Powerwall Firmware version display to Power Flow Animation

### Proxy t20 t21 (23 Nov 2022)

* Added cache logic to better handle Powerwall firmware upgrades.

### Proxy t19 (15 Oct 2022)

* Fix `clear.js` (and others) to hide the compliance link button in the animation caused by the latest Powerwall firmware upgrade (22.26.1-foxtrot)

### Proxy t18 (8 Oct 2022)

* Fix Bug with `/version` for version numbers with alpha characters. #24
* Added error handling for socket error when sending response.
* Added uptime field for stats ('/stats') API.
* Enhanced help API ('/help') to provide HTML stats page and link to API documentation.
* Improved logging with timestamps.

### Proxy t17 (26 July 2022)

* Released with pyPowerwall v0.6.0 Enhancement
* Added HTTP persistent connections for API requests to Powerwall Gateway by @mcbirse in #21
* Requests to Gateway will now re-use persistent http connections which reduces load and increases response time.
* Added env PW_POOL_MAXSIZE to proxy server to allow this to be controlled (persistent connections disabled if set to zero).
* Added env PW_TIMEOUT to proxy server to allow timeout on requests to be adjusted.

### Proxy t16 (3 July 2022)

* Add support for specifying a bind address by @zi0r in https://github.com/jasonacox/pypowerwall/pull/16
* Add shebang for direct execution by @zi0r in https://github.com/jasonacox/pypowerwall/pull/17

### Proxy t15

* Breaking update to /api/system_status/soe endpoint that now provides the 95% scaled values.  This was important to make sure the Power Flow animation matches the Tesla App.  The /soe shortcut URL will continue to provide actual battery level (unscaled). See Issue https://github.com/jasonacox/Powerwall-Dashboard/issues/37

### Proxy t14

* Bug fix to remove scrollbars from web view (see https://github.com/jasonacox/pypowerwall/pull/15 and https://github.com/jasonacox/Powerwall-Dashboard/issues/29) thanks to @danisla.

### Proxy t13

* Added ability to change the style of the power flow animation background color: `clear` (default), `black`, `white`, `grafana` gray, and `dakboard` black.  Set using `PW_STYLE` environment variable:

    ```bash
    export PW_STYLE="clear"
    ```

### Proxy t12

* Added ability to proxy Powerwall web interface for power flow animation (by @danisla). #14
* Added optional HTTPS support for iframe compatibility via `PW_HTTPS` environment variable:

    ```bash
    # Turn on experimental HTTPS mode
    export PW_PORT="8676"
    export PW_PASSWORD="password"
    export PW_EMAIL="name@example.com"
    export PW_HOST="10.0.1.73"
    export PW_TIMEZONE="America/Los_Angeles"
    export PW_CACHE_EXPIRE="5"
    export PW_DEBUG="no"
    export PW_HTTPS="yes"

    python3 server.py
    ```

### Proxy t11

* Removed memory leak debug function.

### Proxy t10

* Bug Fix - ThreadingHTTPServer daemon_threads related memory leak fix. #13
* Proxy server memory metrics added to /stats response.

### Proxy t9

* Cleaned up /freq macro to better handle vitals response with missing ISLAND or METER metrics.

### Proxy t8

* Backup Switch: Added frequency, current and voltage for Backup Switch device.

### Proxy t7

* Bug Fix: Debug logging continued even when disable.
* Force exit added for faster termination instead of waiting on connections to drain.

### Proxy t6

* Added /pod to provide battery state information (e.g. ActiveHeating, ChargeComplete, PermanentlyFaulted) with boolean values as integers (1/0). 
* Added /version to provide Powerwall TEG Firmware Version in string and integer value calculated from the semantic version (e.g. 21.1.1 = 210101). 

### Proxy t5

* Added /alerts to provide list of alerts across devices.  
* Added /freq to provide Frequency, Current and Voltage data for Home, Grid, Powerwall.  

### Proxy t4

* Added /temps (raw) and /temps/pw (aliased) to provide temperature data for Powerwalls.
* Added /help to provide link to this page.

### Proxy t3

* Bug fix in NoneType for error counter.

### Proxy t2

* Added support for *allow list* of Powerwall API calls.

### Proxy t1

* Added multi-threading to HTTP handling using python ThreadingHTTPServer library.
