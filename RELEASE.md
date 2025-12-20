# RELEASE NOTES

## v0.14.5 - Variable Shadowing and Type Annotation Fixes

* Fix variable shadowing in `grid_status()` method: renamed `type` parameter to `output_type` to avoid shadowing Python's built-in `type()` function
* Add backward compatibility for deprecated `type` parameter - still supported but `output_type` is now preferred
* Fix return type annotation for `extract_grid_status()` method: changed from `str` to `Optional[str]` to accurately reflect function can return `None`
* Proxy server build t86

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