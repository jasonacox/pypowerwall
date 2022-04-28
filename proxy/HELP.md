# pyPowerwall Proxy Help

Besides providing authentication and payload caching, the Proxy exposes several APIs that aggregating Powerwall data into simple JSON output for convenient processing.  It also provides several read-only pass through Powerwall API calls. See [README](https://github.com/jasonacox/pypowerwall/blob/main/proxy/README.md) for setup instructions.

## pyPowerwall Proxy Functions

There are several shortcut API URLs that aggregate or otherwise process Powerwall data for convenient use for other projects or dashboarding tools. Unless otherwise specified, expect JSON response.

* /stats - pyPowerwall Stats
* /temps - Powerwall Temperatures
* /temps/pw - Powerwall Temperatures with Simplified Key (PWx_temp)
* /csv - Key power data in CSV format: (grid, home, solar, battery, batterylevel)
* /vitals - Powerwall Device Vitals 
* /strings - Powerwall Inverter String Data
* /soe - Powerwall Battery Level
* /freq - Frequency, Current and Voltage from Device Vitals
* /pod - Battery States and Power Data
* /version - Powerwall Firmware Version (string and integer representation)
* /alerts - Summary of Powerwall Alerts from Device Vitals

## Powerwall Proxy Allowed API Calls

Pass-through calls to Powerwall APIs. 

* /api/status - Powerwall Firmware and Uptime Status
* /api/site_info/site_name
* /api/meters/site
* /api/meters/solar
* /api/sitemaster
* /api/powerwalls
* /api/customer/registration
* /api/system_status
* /api/system_status/grid_status
* /api/system/update/status
* /api/site_info
* /api/system_status/grid_faults
* /api/operation
* /api/site_info/grid_codes
* /api/solars
* /api/solars/brands
* /api/customer
* /api/meters
* /api/installer
* /api/networks
* /api/system/networks
* /api/meters/readings

## Release Notes

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
