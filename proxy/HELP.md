# pyPowerwall Proxy Help

Besides providing authentication and payload caching, the Proxy exposes several APIs that aggregating Powerwall data into simple JSON output for convenient processing.  It also provides several read-only pass through Powerwall API calls.

## pyPowerwall Proxy Functions

* /stats - pyPowerwall Stats
* /temps - Powerwall Temperatures
* /temps/pw - Powerwall Temperatures with Simplified Key (PWx_temp)
* /csv - Key power data in CSV format (grid, home, solar, battery, batterylevel)
* /vitals - Powerwall Device Vitals 
* /strings - Powerwall Inverter String Data
* /soe - Powerwall Battery Level
* /freq - Frequency, Current and Voltage from Device Vitals

## Powerwall Proxy Allowed API Calls

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
