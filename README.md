# pyPowerwall

[![License](https://img.shields.io/github/license/jasonacox/pypowerwall)](https://img.shields.io/github/license/jasonacox/pypowerwall)
[![PyPI version](https://badge.fury.io/py/pypowerwall.svg)](https://badge.fury.io/py/pypowerwall)
[![CI](https://github.com/jasonacox/pypowerwall/actions/workflows/test.yml/badge.svg)](https://github.com/jasonacox/pypowerwall/actions/workflows/test.yml)
[![simtest](https://github.com/jasonacox/pypowerwall/actions/workflows/simtest.yml/badge.svg)](https://github.com/jasonacox/pypowerwall/actions/workflows/simtest.yml)
[![Python Version](https://img.shields.io/pypi/pyversions/pypowerwall)](https://img.shields.io/pypi/pyversions/pypowerwall)
[![PyPI Downloads](https://static.pepy.tech/badge/pypowerwall/month)](https://static.pepy.tech/badge/pypowerwall/month)

Python module to interface with Tesla Energy Gateways for Powerwall and solar power data.

## Description

This python module can be used to monitor and control Tesla Energy Powerwalls. It uses a single class (`Powerwall`) and simple functions to fetch energy data and
poll API endpoints on the Gateway.  

pyPowerwall will cache the authentication headers and API call responses to help reduce the number of calls made to the Gateway (useful if you are polling the Powerwall frequently for trending data).

* Works with Tesla Energy Gateways - Powerwall and Powerwall+
* Simple access through easy to use functions using customer credentials
* Will cache authentication to reduce load on Powerwall Gateway
* Will cache responses to limit number of calls to Powerwall Gateway (optional/user definable)
* Easy access to decoded binary device vitals (/api/devices/vitals in JSON format)
* Provides solar string data for Powerwall+ systems

NOTE: This module requires that you (or your installer) have set up *Customer Login* credentials
on your Powerwall Gateway.

## Setup

You can clone this repo or install the package with pip.  Once installed, pyPowerwall can scan your local network to find th IP address of your Tesla Powerwall Gateway.

```bash
# Install pyPowerwall
python -m pip install pypowerwall

# Scan Network for Powerwalls
python -m pypowerwall scan
```

Note: pyPowerwall installation will attempt to install these required python packages: _requests_ and _protobuf_.

## Programming with pyPowerwall

After importing pypowerwall, you simply create a handle for your Powerwall device 
and call function to poll data.  Here is an example:

```python
    import pypowerwall

    # Optional: Turn on Debug Mode
    # pypowerwall.set_debug(True)

    # Credentials for your Powerwall - Customer Login Data
    password='password'
    email='email@example.com'
    host = "10.0.1.123"               # Address of your Powerwall Gateway
    timezone = "America/Los_Angeles"  # Your local timezone
 
    # Connect to Powerwall
    pw = pypowerwall.Powerwall(host,password,email,timezone)

    # Some System Info
    print("Site Name: %s - Firmware: %s - DIN: %s" % (pw.site_name(), pw.version(), pw.din()))
    print("System Uptime: %s\n" % pw.uptime())

    # Pull Sensor Power Data
    grid = pw.grid()
    solar = pw.solar()
    battery = pw.battery()
    home = pw.home()

    # Display Data
    print("Battery power level: %0.0f%%" % pw.level())
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

```

### pyPowerwall Module Class and Functions 
```
 set_debug(True, color=True)

 Classes
    Powerwall(host, password, email, timezone)

 Functions 
    poll(api, json)         # Return data from Powerwall API URI (return JSON if True)
    level()                 # Return battery power level percentage
    power()                 # Return power data returned as dictionary
    site(verbose)           # Return site sensor data (W or raw JSON if verbose=True)
    solar(verbose):         # Return solar sensor data (W or raw JSON if verbose=True)
    battery(verbose):       # Return battery sensor data (W or raw JSON if verbose=True)
    load(verbose)           # Return load sensor data (W or raw JSON if verbose=True)
    grid()                  # Alias for site()
    home()                  # Alias for load()
    vitals(json)            # Return Powerwall device vitals
    strings(json, verbose)  # Return solar panel string data
    din()                   # Return DIN
    uptime()                # Return uptime - string hms format
    version()               # Return system version
    status(param)           # Return status (JSON) or individual param
    site_name()             # Return site name
    temps()                 # Return Powerwall Temperatures
    alerts()                # Return array of Alerts from devices

 Variables
    pwcacheexpire = 5       # Set API cache timeout in seconds
    timeout = 10            # Timeout for HTTPS calls in seconds
```

## Tools

The following are some useful tools based on pypowerwall:

* [Powerwall Proxy](proxy) - Use this caching proxy to handle authentication to the Powerwall Gateway and make basic read-only API calls to /api/meters/aggregates (power metrics) and /api/system_status/soe (battery level). This is handy proxy with metrics gathering tools like telegraf to pull metrics without needing to authenticate. Because pyPowerwall is designed to cache the auth and high frequency API calls, this will reduce the load on the Gateway and prevent crash/restart issues that can happen if too many session are created on the Gateway.

* [Powerwall Simulator](simulator) - A Powerwall simulator to mimic the responses from the Tesla Powerwall Gateway. This is useful for testing purposes.

## Powerwall Scanner

pyPowerwall has a built in feature to scan your network for available Powerwall gateways.  This will help you find the IP address of your Powerwall.

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

## Credits and References

* Tesla Powerwall 2 – Local Gateway API documentation – https://github.com/vloschiavo/powerwall2
* Python Tesla Powerwall API – https://github.com/jrester/tesla_powerwall
* TESLA PowerWall 2 Security Shenanigans – https://github.com/hackerschoice/thc-tesla-powerwall2-hack
* Powerwall Monitoring – https://github.com/mihailescu2m/powerwall_monitor
* Protocol Buffers (protobuf) Basics - https://developers.google.com/protocol-buffers/docs/pythontutorial
* Tesla ([tesla.proto](tesla.proto)) Research and Credit to @brianhealey
