# pyPowerwall Proxy Help

Besides providing authentication and payload caching, the Proxy exposes several APIs that aggregating Powerwall data into simple JSON output for convenient processing.  It also provides several read-only pass through Powerwall API calls. See [README](https://github.com/jasonacox/pypowerwall/blob/main/proxy/README.md) for setup instructions.

## pyPowerwall Proxy Functions

There are several shortcut API URLs that aggregate or otherwise process Powerwall data for convenient use for other projects or dashboarding tools. Unless otherwise specified, expect JSON response.

* /stats - pyPowerwall Stats
* /temps - Powerwall Temperatures
* /temps/pw - Powerwall Temperatures with Simplified Key (PWx_temp)
* /csv - Key power data in CSV format: (grid, home, solar, battery, batterylevel)
* /csv/v2 - CSV format: (grid, home, solar, battery, batterylevel, grid_up, reserve)
* /vitals - Powerwall Device Vitals 
* /strings - Powerwall Inverter String Data
* /soe - Powerwall Battery Level
* /freq - Frequency, Current and Voltage from Device Vitals
* /pod - Battery States and Power Data
* /version - Powerwall Firmware Version (string and integer representation)
* /alerts - Summary of Powerwall Alerts from Device Vitals
* /alerts/pw - Summary of Powerwall Alerts in dictionary/object format
* / - Display Powerwall Flow Animation

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

Release notes are in the [RELEASE.md](https://github.com/jasonacox/pypowerwall/blob/main/proxy/RELEASE.md) file.
