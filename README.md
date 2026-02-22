# pyPowerwall

[![License](https://img.shields.io/github/license/jasonacox/pypowerwall)](https://img.shields.io/github/license/jasonacox/pypowerwall)
[![PyPI version](https://badge.fury.io/py/pypowerwall.svg)](https://badge.fury.io/py/pypowerwall)
[![CI](https://github.com/jasonacox/pypowerwall/actions/workflows/test.yml/badge.svg)](https://github.com/jasonacox/pypowerwall/actions/workflows/test.yml)
[![simtest](https://github.com/jasonacox/pypowerwall/actions/workflows/simtest.yml/badge.svg)](https://github.com/jasonacox/pypowerwall/actions/workflows/simtest.yml)
[![Python Version](https://img.shields.io/pypi/pyversions/pypowerwall)](https://img.shields.io/pypi/pyversions/pypowerwall)
[![PyPI Downloads](https://static.pepy.tech/badge/pypowerwall/month)](https://static.pepy.tech/badge/pypowerwall/month)

pyPowerwall is a Python module to interface with Tesla Energy Gateways for Powerwall and solar power data. It supports local access to Powerwall, Powerwall 2, Powerwall+ and Powerwall 3 systems. It also provides Tesla Owner and FleetAPI cloud access for all systems including Solar-only systems.

> ⚠️ **NOTICE:** As of Powerwall Firmware version 25.10.0, network routing to the TEDAPI endpoint (`192.168.91.1`) is no longer supported by Tesla. You must connect directly to the Powerwall's Wi‑Fi access point to access TEDAPI data.

## Description

This Python module can be used to monitor and control Tesla Energy Powerwalls. It uses a single class (`Powerwall`) and simple functions to fetch energy data and poll API endpoints on the Gateway.  

pyPowerwall will cache the authentication headers and API call responses to help reduce the number of calls made to the Gateway (useful if you are polling the Powerwall frequently for trending data).

* Works with Tesla Energy Gateways - Powerwall and Powerwall+
* Access provided via Local Gateway APIs, Tesla FleetAPI (official), and Tesla Owners API (unofficial).
* Will cache authentication to reduce load on Powerwall Gateway
* Will cache responses to limit the number of calls to the Powerwall Gateway or cloud (optional/user‑definable)
* Will re-use HTTP connections to the Powerwall Gateway for reduced load and faster response times
* Provides solar string data for Powerwall+ systems.

## Setup

You can clone this repo or install the package with pip.  Once installed, pyPowerwall can scan your local network to find the IP address of your Tesla Powerwall Gateway.

```bash
# Install pyPowerwall
python3 -m pip install pypowerwall

# Option 1 - LOCAL MODE - Scan Network for Powerwalls
python3 -m pypowerwall scan

# Option 2 - FLEETAPI MODE - Setup to use the official Tesla FleetAPI - See notes below.
python3 -m pypowerwall fleetapi

# Option 3 - CLOUD MODE - Setup to use Tesla Owners cloud API
python3 -m pypowerwall setup

# Option 4 - TEDAPI MODE - Test this mode (requires extended setup - see below)
python3 -m pypowerwall tedapi
```

### Local Setup - Option 1

The Tesla Powerwall, Powerwall 2 and Powerwall+ have a local LAN based Web Portal and API that you can use to monitor your Powerwall. It requires that you (or your installer) have the IP address (see scan above) and set up *Customer Login* credentials on your Powerwall Gateway. That is all that is needed to connect. 

The Powerwall 3 does not have a Web Portal or API but you can access it via the cloud (see options 2 and 3) and via the TEDAPI access point (option 4).

Locally accessible extended device vitals metrics are available using the TEDAPI method (see option 4 below).

### FleetAPI Setup - Option 2

FleetAPI is the official Tesla API for accessing your Tesla products. This setup has some additional setup requirements that you will be prompted to do:

Step 1 - Tesla Partner Account - Sign in to Tesla Developer Portal and make an App Access Request: See [Tesla App Access Request](https://developer.tesla.com/request) - During this process, you will need to set up and remember the following account settings: 

   * CLIENT_ID - This will be provided to you by Tesla when your request is approved.
   * CLIENT_SECRET - Same as above.
   * DOMAIN - The domain name of a website you own and control.
   * REDIRECT_URI - This is the URL that Tesla will direct you to after you authenticate. This landing URL (on your website) will extract the GET variable `code`, which is a one-time use authorization code needed during the pyPowerwall setup. You can use https://pypowerwall.com/code or copy the code from [index.html](./tools/fleetapi/index.html) to your site and update REDIRECT_URI with that URL. Alternatively, you can just copy the URL from the 404 page during the authorization process (the code is in the URL).

Step 2 - Run the [create_pem_key.py](./tools/fleetapi/create_pem_key.py) script and place the **public** key on your website at the URL: https://{DOMAIN}/.well-known/appspecific/com.tesla.3p.public-key.pem

Step 3 - Run `python3 -m pypowerwall fleetapi` - The credentials and tokens will be stored in the `.pypowerwall.fleetapi` file.

### Cloud Mode - Option 3

The unofficial Tesla Owners API allows FleetAPI access (option 2) without having to set up a website and PEM key. Follow the directions given to you by running `python3 -m pypowerwall setup`. The credentials and site_id will be stored in `.pypowerwall.auth` and `.pypowerwall.site`.

### TEDAPI Mode - Option 4

With version v0.10.0+, pypowerwall can access the TEDAPI endpoint on the Gateway. This API offers additional metrics related to string data, voltages, and alerts. However, you will need the Gateway/Wi‑Fi password (often found on the QR sticker on the Powerwall Gateway). Additionally, your computer will need network access to the Gateway at 192.168.91.1. You can join your computer to the Gateway’s local Wi‑Fi or add a route:

Tip: `gw_pwd` is the local Gateway Wi‑Fi password. Leaving `password` empty with `gw_pwd` set will auto‑enable full TEDAPI mode; on PW2/+ you can also combine customer `password`/`email` with `gw_pwd` for a hybrid mode.

In the examples below, change **192.168.0.100** to the IP address of the Powerwall Gateway (or Inverter) on your LAN. Also, the **onlink** parameter may be necessary for Linux.

#### Linux Ubuntu and RPi
```bash
# Can add to /etc/rc.local for persistence
sudo ip route add 192.168.91.1 via 192.168.0.100 [onlink]
```

See `examples/network_route.py` for two different approaches to do this programmatically in Python.

#### macOS
```
sudo route add -host 192.168.91.1 192.168.0.100 # Temporary 
networksetup -setadditionalroutes Wi-Fi 192.168.91.1 255.255.255.255 192.168.0.100 # Persistent
```

#### Windows - Using the persistence flag - Administrator Shell
```
route -p add 192.168.91.1 mask 255.255.255.255 192.168.0.100
```

#### Windows Subsystem for Linux (WSL 2–specific)
Follow the instructions for Linux, but you must edit (from the host Windows OS) `%USERPROFILE%\.wslconfig` and add the following settings:
```
[wsl2]
networkingMode=mirrored
```

```bash
# Test
python3 -m pypowerwall tedapi
```

#### TEDAPI Troubleshooting

- Connection refused/timeout: Ensure you’re connected to the Powerwall’s Wi‑Fi or have a working route to 192.168.91.1. Some firmware versions (25.10.0+) block routing; connect directly to the PW Wi‑Fi.
- Auth failures: Use the Gateway Wi‑Fi password from the QR label as `gw_pwd` (case‑sensitive). Customer portal passwords do not work for TEDAPI.
- TLS/certificate warnings: TEDAPI uses a self‑signed cert; most tools need `--insecure` (curl) or `verify=False` (requests). Use only on trusted networks.
- Hybrid mode quirks (PW2/+): If both customer `password`/`email` and `gw_pwd` are provided, TEDAPI data augments local APIs; try removing customer creds if you only need TEDAPI.
- QNAP/Appliance routing: Static routes from shell may be ignored; use the appliance’s network control panel to add a persistent host route.



### FreeBSD Install

FreeBSD users can install from ports or pkg [FreshPorts](https://www.freshports.org/net-mgmt/py-pypowerwall):

Via pkg:
```bash
# pkg install net-mgmt/py-pypowerwall
```

Via ports:
```bash
# cd /usr/ports/net-mgmt/py-pypowerwall/ && make install clean
```

Note: pyPowerwall installation will attempt to install these required Python packages: _requests_, _protobuf_ and _teslapy_.

## Programming with pyPowerwall

After importing pypowerwall, you simply create a handle for your Powerwall device 
and call functions to poll data. A simple example is below or see [example.py](example.py) for an extended version:

```python
import pypowerwall

# Optional: Turn on Debug Mode
# pypowerwall.set_debug(True)

# Select option you wish to use.
OPTION = 4

# Connect to Powerwall based on selected option
if OPTION == 1:
   # Option 1 - LOCAL MODE - Customer Login (Powerwall 2 and Powerwall+ only)
   password="password"
   email="email@example.com"
   host = "10.0.1.123"               # Address of your Powerwall Gateway
   timezone = "America/Los_Angeles"  # Your local timezone
   gw_pwd = None

if OPTION == 2:
   # Option 2 - FLEETAPI MODE - Requires Setup (Powerwall & Solar-Only)
   host = password = email = ""
   timezone = "America/Los_Angeles"
   gw_pwd = None 

if OPTION == 3:
   # Option 3 - CLOUD MODE - Requires Setup (Powerwall & Solar-Only)
   host = password = ""
   email='email@example.com'
   timezone = "America/Los_Angeles"
   gw_pwd = None

if OPTION == 4:
   # Option 4 - TEDAPI MODE - Requires access to Gateway (Powerwall 2, Powerwall+, and Powerwall 3)
   host = "192.168.91.1"
   gw_pwd = "ABCDEFGHIJ"
   password = email = ""
   timezone = "America/Los_Angeles"
   # Uncomment the following for hybrid mode (Powerwall 2 and +)
   #password="password"
   #email="email@example.com"

# Note on gw_pwd (TEDAPI)
# - `gw_pwd` is the local Gateway Wi‑Fi password printed on the QR label.
# - It is only required for TEDAPI features (local diagnostics like vitals/strings) 
#   and is not used for cloud/FleetAPI authentication.
# - If you set `gw_pwd` and leave `password` empty, pyPowerwall will auto‑enable full TEDAPI mode.
# - On Powerwall 2 and Powerwall+ you can optionally provide both `password`/`email` and `gw_pwd` 
#   to run in a hybrid mode that combines customer APIs with TEDAPI.

# Connect to Powerwall - auto_select mode (local, fleetapi, cloud, tedapi)
pw = pypowerwall.Powerwall(host, password, email, timezone, gw_pwd=gw_pwd, auto_select=True)

# Some System Info
print("Site Name: %s - Firmware: %s - DIN: %s" % (pw.site_name(), pw.version(), pw.din()))
print("System Uptime: %s\n" % pw.uptime())

# Pull Sensor Power Data
grid = pw.grid()
solar = pw.solar()
battery = pw.battery()
home = pw.home()

# Display Data
print("Battery power level: %0.0f%%" % pw.level())  # Actual level including 5% Tesla reserve
print("Tesla app level: %0.0f%%" % pw.level(scale=True))  # Level as shown in Tesla App
print("Combined power metrics: %r" % pw.power())
print("")

# Display Power in kW
print("Grid Power: %0.2fkW" % (float(grid)/1000.0))
print("Solar Power: %0.2fkW" % (float(solar)/1000.0))
print("Battery Power: %0.2fkW" % (float(battery)/1000.0))
print("Home Power: %0.2fkW" % (float(home)/1000.0))
print("")

# Raw JSON Payload Examples
print("Grid raw: %r\n" % pw.grid(verbose=True))
print("Solar raw: %r\n" % pw.solar(verbose=True))

# Display Device Vitals
print("Vitals: %r\n" % pw.vitals())

# Display String Data
print("String Data: %r\n" % pw.strings())

# Display System Status (e.g. Battery Capacity)
print("System Status: %r\n" % pw.system_status())
```

### pyPowerwall Module Class and Functions 

```
 set_debug(True, color=True)

 Classes
    Powerwall(host, password, email, timezone, pwcacheexpire, timeout, poolmaxsize, 
        cloudmode, siteid, authpath, authmode, cachefile, fleetapi, auto_select, retry_modes, gw_pwd)

 Parameters
    host                      # Hostname or IP of the Tesla gateway (host:port)
    password                  # Customer password for gateway
    email                     # (required) Customer email for gateway / cloud
    timezone                  # Desired timezone
    pwcacheexpire = 5         # Set API cache timeout in seconds
    timeout = 5               # Timeout for HTTPS calls in seconds
    poolmaxsize = 10          # Pool max size for HTTP connection reuse (persistent
                                connections disabled if zero)
    cloudmode = False         # If True, use Tesla cloud for data (default is False)
    siteid = None             # If cloudmode is True, use this siteid (default is None)
    authpath = ""             # Path to cloud auth and site files (default current directory)
    authmode = "cookie"       # "cookie" (default) or "token" - use cookie or bearer token for auth
    cachefile = ".powerwall"  # Path to cache file (default current directory)
    fleetapi = False          # If True, use Tesla FleetAPI for data (default is False)
    auth_path = ""            # Path to configfile (default current directory)
    auto_select = False       # If True, select the best available mode to connect (default is False)
    retry_modes = False       # If True, retry connection to Powerwall
    gw_pwd = None             # TEG Gateway password (used for local mode access to tedapi)
    
 Functions 
   poll(api, json, force)    # Return data from Powerwall API (dict if json=True, bypass cache force=True)
   post(api, payload, json)  # Send payload to Powerwall API (dict if json=True)
    level(scale)              # Return battery power level percentage (scale=False: actual level, scale=True: Tesla app level)
    power()                   # Return power data returned as dictionary
    site(verbose)             # Return site sensor data (W or raw JSON if verbose=True)
    solar(verbose):           # Return solar sensor data (W or raw JSON if verbose=True)
    battery(verbose):         # Return battery sensor data (W or raw JSON if verbose=True)
    load(verbose)             # Return load sensor data (W or raw JSON if verbose=True)
    grid()                    # Alias for site()
    home()                    # Alias for load()
    vitals(json)              # Return Powerwall device vitals (dict or json if True)
    strings(json, verbose)    # Return solar panel string data
    din()                     # Return DIN
    uptime()                  # Return uptime - string hms format
    version()                 # Return system version
    status(param)             # Return status (JSON) or individual param
    site_name()               # Return site name
    temps()                   # Return Powerwall Temperatures
    alerts()                  # Return array of Alerts from devices
    system_status(json)       # Returns the system status
    battery_blocks(json)      # Returns battery specific information merged from system_status() and vitals()
    grid_status(type)         # Return the power grid status, type ="string" (default), "json", or "numeric"
                              #     - "string": "UP", "DOWN", "SYNCING"
                              #     - "numeric": -1 (Syncing), 0 (DOWN), 1 (UP)
    is_connected()            # Returns True if able to connect and login to Powerwall
    get_reserve(scale)        # Get Battery Reserve Percentage
    get_mode()                # Get Current Battery Operation Mode
    set_reserve(level)        # Set Battery Reserve Percentage
    set_mode(mode)            # Set Current Battery Operation Mode
    get_time_remaining()      # Get the backup time remaining on the battery
    set_operation(level, mode, json)        # Set Battery Reserve Percentage and/or Operation Mode
    set_grid_charging(mode)   # Enable or disable grid charging (mode = True or False)
    set_grid_export(mode)     # Set grid export mode (mode = battery_ok, pv_only, never)
    get_grid_charging()       # Get the current grid charging mode
    get_grid_export()         # Get the current grid export mode
```

## Tools

The following are some useful tools based on pypowerwall:

* [Powerwall Proxy](proxy) - Use this caching proxy to handle authentication to the Powerwall Gateway and make basic read-only API calls to /api/meters/aggregates (power metrics), /api/system_status/soe (battery level) and many [others](https://github.com/jasonacox/pypowerwall/blob/main/proxy/API.md). This is useful for metrics gathering tools like telegraf to pull metrics without needing to authenticate. Because pyPowerwall is designed to cache the auth and high frequency API calls, this will also reduce the load on the Gateway and prevent crash/restart issues that can happen if too many sessions are created on the Gateway.

* [Powerwall Simulator](simulator) - A Powerwall simulator to mimic the responses from the Tesla Powerwall Gateway. This is useful for testing purposes.

* [Powerwall Dashboard](https://github.com/jasonacox/Powerwall-Dashboard#powerwall-dashboard) - Monitoring Dashboard for the Tesla Powerwall using Grafana, InfluxDB, Telegraf and pyPowerwall.

## pyPowerwall Command Line Interface (CLI)

pyPowerwall has a built-in feature to scan your network for available Powerwall gateways and set/get operational and reserve modes.

```
Usage: PyPowerwall [-h] {setup,scan,set,get,version} ...

PyPowerwall Module v0.8.1

Options:
  -h, --help            Show this help message and exit

Commands (run <command> -h to see usage information):
  {setup,fleetapi,tedapi,scan,set,get,version}
    setup                 Setup Tesla Login for Cloud Mode access
    fleetapi              Setup Tesla FleetAPI for Cloud Mode access
    tedapi                Test TEDAPI connection to Powerwall Gateway
    scan                  Scan local network for Powerwall gateway
    set                   Set Powerwall Mode and Reserve Level
    get                   Get Powerwall Settings and Power Levels
    version               Print version information

   set options:
      -mode MODE          Powerwall Mode: self_consumption, backup, or autonomous
      -reserve RESERVE    Set Battery Reserve Level [Default=20]
      -current            Set Battery Reserve Level to Current Charge
      -gridcharging MODE  Set Grid Charging (allow) Mode ("on" or "off")
      -gridexport MODE    Set Export to Grid Mode ("battery_ok", "pv_only", or "never")

   get options:
      -format FORMAT      Output format: text, json, csv
      -host HOST          IP address of Powerwall Gateway
      -password PASSWORD  Password for Powerwall Gateway
```
   
```bash
# Install pyPowerwall if you haven't already
python -m pip install pypowerwall

# Scan Network for Powerwalls
python -m pypowerwall scan
```

Example Output
```
pyPowerwall Network Scanner [0.1.2]
Scan local network for Tesla Powerwall Gateways

    Your network appears to be: 10.0.1.0/24

    Enter Network or press enter to use 10.0.1.0/24: 

    Running Scan...
      Host: 10.0.1.16 ... OPEN - Not a Powerwall
      Host: 10.0.1.26 ... OPEN - Not a Powerwall
      Host: 10.0.1.36 ... OPEN - Found Powerwall 1232100-00-E--TG123456789ABG
      Done                           

Discovered 1 Powerwall Gateway
     10.0.1.36 [1232100-00-E--TG123456789ABG]
```

Get Power Levels, Operation Mode, and Battery Reserve Level

```bash
# Setup Connection with Tesla Cloud
python -m pypowerwall setup

# Get Power Levels, Operation Mode, and Battery Reserve Setting
#
# Usage: PyPowerwall get [-h] [-format FORMAT]
#  -h, --help      show this help message and exit
#  -format FORMAT  Output format: text, json, csv
#
python -m pypowerwall get
python -m pypowerwall get -format json
python -m pypowerwall get -format csv

# Set Operation Mode and Battery Reserve Setting
#
# Usage: PyPowerwall set [-h] [-mode MODE] [-reserve RESERVE] [-current]
#  -h, --help        show this help message and exit
#  -mode MODE        Powerwall Mode: self_consumption, backup, or autonomous
#  -reserve RESERVE  Set Battery Reserve Level [Default=20]
#  -current          Set Battery Reserve Level to Current Charge
#
python -m pypowerwall set -mode self_consumption
python -m pypowerwall set -reserve 30
python -m pypowerwall set -current
```

## Example API Calls

The following APIs are a result of help from other projects as well as my own investigation. 

* pw.poll('/api/system_status/soe') - Battery percentage (JSON with float 0-100)

   ```json
   {"percentage":40.96227949234631}
   ```

* pw.poll('/api/meters/aggregates') - Site, Load, Solar and Battery (JSON)

   ```json
   {
      "site": {
         "last_communication_time": "2021-11-22T22:15:06.590577619-07:00",
         "instant_power": -23,
         "instant_reactive_power": -116,
         "instant_apparent_power": 118.25819210524064,
         "frequency": 0,
         "energy_exported": 3826.313294918422,
         "energy_imported": 1302981.2128324094,
         "instant_average_voltage": 209.59546822390985,
         "instant_average_current": 5.4655000000000005,
         "i_a_current": 0,
         "i_b_current": 0,
         "i_c_current": 0,
         "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
         "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
         "timeout": 1500000000,
         "num_meters_aggregated": 1,
         "instant_total_current": 5.4655000000000005
      },
      "battery": {
         "last_communication_time": "2021-11-22T22:15:06.590178016-07:00",
         "instant_power": 1200,
         "instant_reactive_power": 0,
         "instant_apparent_power": 1200,
         "frequency": 59.997,
         "energy_exported": 635740,
         "energy_imported": 730610,
         "instant_average_voltage": 242.15000000000003,
         "instant_average_current": -28.6,
         "i_a_current": 0,
         "i_b_current": 0,
         "i_c_current": 0,
         "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
         "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
         "timeout": 1500000000,
         "num_meters_aggregated": 2,
         "instant_total_current": -28.6
      },
      "load": {
         "last_communication_time": "2021-11-22T22:15:06.590178016-07:00",
         "instant_power": 1182.5,
         "instant_reactive_power": -130.5,
         "instant_apparent_power": 1189.6791584288599,
         "frequency": 0,
         "energy_exported": 0,
         "energy_imported": 2445454.899537491,
         "instant_average_voltage": 209.59546822390985,
         "instant_average_current": 5.641820455472543,
         "i_a_current": 0,
         "i_b_current": 0,
         "i_c_current": 0,
         "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
         "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
         "timeout": 1500000000,
         "instant_total_current": 5.641820455472543
      },
      "solar": {
         "last_communication_time": "2021-11-22T22:15:06.594908129-07:00",
         "instant_power": 10,
         "instant_reactive_power": 0,
         "instant_apparent_power": 10,
         "frequency": 59.988,
         "energy_exported": 1241170,
         "energy_imported": 0,
         "instant_average_voltage": 241.60000000000002,
         "instant_average_current": 0.04132231404958678,
         "i_a_current": 0,
         "i_b_current": 0,
         "i_c_current": 0,
         "last_phase_voltage_communication_time": "0001-01-01T00:00:00Z",
         "last_phase_power_communication_time": "0001-01-01T00:00:00Z",
         "timeout": 1000000000,
         "num_meters_aggregated": 1,
         "instant_total_current": 0.04132231404958678
      }
   }
   ```

* pw.strings(jsonformat=True)

   ```json 
   {
      "A": {
         "Connected": true,
         "Current": 1.81,
         "Power": 422.0,
         "State": "PV_Active",
         "Voltage": 230.0
      },
      "B": {
         "Connected": false,
         "Current": 0.0,
         "Power": 0.0,
         "State": "PV_Active",
         "Voltage": -2.5
      },
      "C": {
         "Connected": true,
         "Current": 4.47,
         "Power": 892.0,
         "State": "PV_Active",
         "Voltage": 202.4
      },
      "D": {
         "Connected": true,
         "Current": 4.44,
         "Power": 889.0,
         "State": "PV_Active_Parallel",
         "Voltage": 202.10000000000002
      }
   }
   ```

* pw.temps(jsonformat=True)

   ```json
   {
      "TETHC--2012170-25-E--TGxxxxxxxxxxxx": 17.5,
      "TETHC--3012170-05-B--TGxxxxxxxxxxxx": 17.700000000000003
   }
   ```

* pw.status(jsonformat=True)

   ```json
   {
      "din": "1232100-00-E--TGxxxxxxxxxxxx",
      "start_time": "2022-01-05 09:20:47 +0800",
      "up_time_seconds": "62h48m24.076725628s",
      "is_new": false,
      "version": "21.44.1 c58c2df3",
      "git_hash": "c58c2df39ec207708c4cde0c747db7cf31750f29",
      "commission_count": 8,
      "device_type": "teg",
      "sync_type": "v2.1",
      "leader": "",
      "followers": null,
      "cellular_disabled": false
   }
   ```
* pw.vitals(jsonformat=True)

   * Example Output: [here](https://github.com/jasonacox/pypowerwall/blob/main/docs/vitals-example.json)
   * Produces device vitals and alerts. For more information see [here](https://github.com/jasonacox/pypowerwall/tree/main/docs#devices-and-alerts).

* pw.grid_status(type="json")

   ```json
   {
    "grid_services_active": false,
    "grid_status": "SystemGridConnected"
   }
   ```
* pw.system_status(jsonformat=True)

   ```json
   {
    "all_enable_lines_high": true,
    "auxiliary_load": 0,
    "available_blocks": 2,
    "battery_blocks": [
        {
            "OpSeqState": "Active",
            "PackagePartNumber": "3012170-10-B",
            "PackageSerialNumber": "TG122xxx", 
            "Type": "",
            "backup_ready": true,
            "charge_power_clamped": false,
            "disabled_reasons": [],
            "energy_charged": 21410,
            "energy_discharged": 950,
            "f_out": 60.016999999999996,
            "i_out": 6.800000000000001,
            "nominal_energy_remaining": 13755,
            "nominal_full_pack_energy": 13803,
            "off_grid": false,
            "p_out": -370,
            "pinv_grid_state": "Grid_Compliant",
            "pinv_state": "PINV_GridFollowing",
            "q_out": -10,
            "v_out": 243.60000000000002,
            "version": "b0ec24329c08e4",
            "vf_mode": false,
            "wobble_detected": false
        },
        {
            "OpSeqState": "Active",
            "PackagePartNumber": "3012170-10-B",
            "PackageSerialNumber": "TG122yyy", 
            "Type": "",
            "backup_ready": true,
            "charge_power_clamped": false,
            "disabled_reasons": [],
            "energy_charged": 20460,
            "energy_discharged": 1640,
            "f_out": 60.016000000000005,
            "i_out": 3.6,
            "nominal_energy_remaining": 13789,
            "nominal_full_pack_energy": 13816,
            "off_grid": false,
            "p_out": -210,
            "pinv_grid_state": "Grid_Compliant",
            "pinv_state": "PINV_GridFollowing",
            "q_out": 20,
            "v_out": 243.20000000000002,
            "version": "b0ec24329c08e4",
            "vf_mode": false,
            "wobble_detected": false
        }
    ],
    "battery_target_power": -706,
    "battery_target_reactive_power": 0,
    "blocks_controlled": 2,
    "can_reboot": "Yes",
    "command_source": "Configuration",
    "expected_energy_remaining": 0,
    "ffr_power_availability_high": 11658,
    "ffr_power_availability_low": 194,
    "grid_faults": [
        {
            "alert_is_fault": false,
            "alert_name": "PINV_a006_vfCheckUnderFrequency",
            "alert_raw": 432374469357469696,
            "decoded_alert": "[{\"name\":\"PINV_alertID\",\"value\":\"PINV_a006_vfCheckUnderFrequency\"},{\"name\":\"PINV_alertType\",\"value\":\"Warning\"},{\"name\":\"PINV_a006_frequency\",\"value\":58.97,\"units\":\"Hz\"}]",
            "ecu_package_part_number": "1081100-22-U",
            "ecu_package_serial_number": "CN321365D2U06J",
            "ecu_type": "TEPINV",
            "git_hash": "b0ec24329c08e4",
            "site_uid": "1232100-00-E--TG120325001C3D",
            "timestamp": 1645733844019
        }
    ],
    "grid_services_power": 0,
    "instantaneous_max_apparent_power": 30690,
    "instantaneous_max_charge_power": 14000,
    "instantaneous_max_discharge_power": 20000,
    "inverter_nominal_usable_power": 11700,
    "last_toggle_timestamp": "2022-02-22T08:18:22.51778899-07:00",
    "load_charge_constraint": 0,
    "max_apparent_power": 10000,
    "max_charge_power": 10000,
    "max_discharge_power": 10000,
    "max_power_energy_remaining": 0,
    "max_power_energy_to_be_charged": 0,
    "max_sustained_ramp_rate": 2512500,
    "nominal_energy_remaining": 27624,
    "nominal_full_pack_energy": 27668,
    "primary": true,
    "score": 10000,
    "smart_inv_delta_p": 0,
    "smart_inv_delta_q": 0,
    "solar_real_power_limit": -1,
    "system_island_state": "SystemGridConnected"
   }
   ```

* pw.battery_blocks(jsonformat=True)

   ```json
   {  
      "TG122xxx": {
         "OpSeqState": "Active",
         "PackagePartNumber": "3012170-10-B",
         "THC_State": "THC_STATE_AUTONOMOUSCONTROL",
         "Type": "",
         "backup_ready": true,
         "charge_power_clamped": false,
         "disabled_reasons": [],
         "energy_charged": 21020,
         "energy_discharged": 880,
         "f_out": 60.016000000000005,
         "i_out": 2.7,
         "nominal_energy_remaining": 13812,
         "nominal_full_pack_energy": 13834,
         "off_grid": false,
         "p_out": -160,
         "pinv_grid_state": "Grid_Compliant",
         "pinv_state": "PINV_GridFollowing",
         "q_out": 20,
         "temperature": 21.799999999999997,
         "v_out": 243.9,
         "version": "b0ec24329c08e4",
         "vf_mode": false,
         "wobble_detected": false
      },
      "TG122yyy": {
         "OpSeqState": "Active",
         "PackagePartNumber": "3012170-10-B",
         "THC_State": "THC_STATE_AUTONOMOUSCONTROL",
         "Type": "",
         "backup_ready": true,
         "charge_power_clamped": false,
         "disabled_reasons": [],
         "energy_charged": 21020,
         "energy_discharged": 880,
         "f_out": 60.016000000000005,
         "i_out": 2.7,
         "nominal_energy_remaining": 13812,
         "nominal_full_pack_energy": 13834,
         "off_grid": false,
         "p_out": -160,
         "pinv_grid_state": "Grid_Compliant",
         "pinv_state": "PINV_GridFollowing",
         "q_out": 20,
         "temperature": 18.5,
         "v_out": 243.9,
         "version": "b0ec24329c08e4",
         "vf_mode": false,
         "wobble_detected": false
      }
   }
   ```


## Documentation

For detailed documentation, see the [Documentation Hub](docs/README.md).

### Quick Reference

* [Firmware Version History](docs/reference/firmware-history.md) - Complete history of Powerwall firmware versions and release notes
* [Device Information](docs/reference/devices.md) - Detailed information about Powerwall devices and alerts  
* [Alert Codes](docs/reference/alerts.md) - Comprehensive list of alert codes
* [Python API Reference](API.md) - Full API documentation

## Glossary

This is an unofficial list of terms that are seen in Powerwall responses and messages. 

* Site = Utility Grid
* Load = Home (think of it as the "load" that the battery or grid powers)
* instant_power = Current power (instant) - also called "true power" in wattage (W)
* instant_reactive_power = The dissipated power resulting from inductive and capacitive loads measured in volt-amperes reactive (VAR)
* instant_apparent_power = The combination of reactive and true power measure in volt-amperes (VA)
* energy_imported = kWh pulled from grid over a duration of time (since Powerwall commissioning it seems)
* energy_exported = kWh pushed to grid

### Support

There are several ways you can support this project.

* Submit ideas, issues, discussions and code! Thanks to our active community, the project continues to grow and improve. Your engagement and help is needed and appreciated.
* Tell others. If you find this useful, please share with others to help build our community.
* Help test the code. We need help testing the project on different platforms and systems. Report your finding and any suggestions to make it easier to better.
* Some of you have asked how you can contribute to help fund the project. This is work of love and a hobby. I'm not looking for financial help. However, if you are considering purchasing a Tesla Solar and/or Powerwall system, please take advantage of this code for a discount and I'll get a referral credit as well: https://www.tesla.com/referral/jason50054

## References

* Tesla Powerwall 2 – Local Gateway API documentation – https://github.com/vloschiavo/powerwall2
* TESLA PowerWall 2 Security Shenanigans – https://github.com/hackerschoice/thc-tesla-powerwall2-hack
* Powerwall Monitoring – https://github.com/mihailescu2m/powerwall_monitor
* Protocol Buffers (protobuf) Basics - https://developers.google.com/protocol-buffers/docs/pythontutorial
* Powerwall Dashboard - The project that started pypowerwall - https://github.com/jasonacox/Powerwall-Dashboard

# Acknowledgements

* [Tesla Energy](https://www.tesla.com/energy/design?referral=jason50054&redirect=no) - Tesla is not affiliated with this project but we want to thank the brilliant minds at Tesla for creating such a great system for solar home energy generation. Tesla and Powerwall are trademarks of Tesla, Inc.
* Tesla ([tesla.proto](tesla.proto)) Research and Credit to @brianhealey
* Status Functions - Thanks to @wcwong for contribution: system_status(), battery_blocks(), grid_status()
* Special thanks to the entire pypowerwall community for the great engagement, contributions and encouragement! See [RELEASE notes](https://github.com/jasonacox/pypowerwall/releases) for the ever growing list of improvements and contributors making this project possible.

## Other Tools and Similar Projects

* NetZero app - iOS and Android App for monitoring your System - https://www.netzeroapp.io/
* Python Tesla Powerwall API – https://github.com/jrester/tesla_powerwall
* GoTesla - go based Tesla API - https://github.com/bmah888/gotesla

## Contributors

<a href="https://github.com/jasonacox/pypowerwall/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=jasonacox/pypowerwall" />
</a>

## Citation

If you wish to cite this project, please use:

```bibtex
@software{pyPowerwall,
  author = {Cox, Jason A.},
  title = {pyPowerwall: Python API for Tesla Powerwall and Solar Energy Data.},
  year = {2023},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/jasonacox/pypowerwall}},
}
```
