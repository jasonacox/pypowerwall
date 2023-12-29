## pyPowerwall Proxy Release Notes

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
