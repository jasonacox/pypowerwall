## pyPowerwall Proxy Release Notes

### Proxy t72 (16 Apr 2025)

* Add routes to map library functions into `/pw/` APIs (e.g. /pw/power)

### Proxy t71 (6 Apr 2025)

* Add routes for fan speeds: `/fans` and `/fans/pw` (simple enumerated values for dashboard)

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
