# RELEASE NOTES

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
* Breaking change to Protobuf schemea (PR #2) including:
* Files `tesla.proto` and `tesla_pb2.py`
* Impacted output from function `vitals()` and [examples/vitals.py](examples/vitals.py).

## v0.1.4 - Battery Level Percentage Scaling

* PyPI 0.1.4
* Changed "Network Scan" default timeout to 400ms for better detection.
* Added Tesla App style "Battery Level Percentage" Conversion option to `level()` to convert the level reading to the 95% scale used by the App. Ths converts the battery level percentage to be consistent with the Tesla App:

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