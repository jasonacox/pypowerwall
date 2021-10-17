# pyPowerwall

[![PyPI version](https://badge.fury.io/py/pypowerwall.svg)](https://badge.fury.io/py/pypowerwall)
[![CI](https://github.com/jasonacox/pypowerwall/actions/workflows/test.yml/badge.svg)](https://github.com/jasonacox/pypowerwall/actions/workflows/test.yml)

Python module to interface with Tesla Energy Gateways for Powerwall and solar power data.

## Description

This python module can be used to monitor and control Tesla Energy Gateway Powerwalls. It uses a single class (`Powerwall`) and simple functions to fetch energy data and
poll API endpoints on the Gateway.  

pyPowerwall will cache the authentication headers and API call responses for up to 5s to help reduce the number of calls made to the Gateway (useful if you are polling the Powerwall frequently for trending data).

### Key Features

* Works with Tesla Energy Gateways - Powerwall+ 
* Simple access through easy to use functions using customer credentials
* Will cache authentication to reduce load on Powerwall Gateway
* Will cache responses for 5s to limit number of calls to Powerwall Gateway

NOTE: This module requires that you (or your installer) have set up customer credentials
on your Powerwall Gateway.

## Setup

You can clone this repo or install the package with pip.  Once installed, pyPowerwall can scan your local network to find th IP address of your Tesla Powerwall Gateway.

```bash
# Install pyPowerwall
python -m pip install pypowerwall

# Scan Network for Powerwalls
python -m pypowerwall scan
```

## Programming with pyPowerwall

After importing pypowerwall, you simply create a handle for your Powerwall device 
and call function to poll data.  Here is an example:

```python
    import pypowerwall

    # Optional: Turn on Debug Mode
    # pypowerwall.set_debug(True)

    # Credentials for your Powerwall - Customer Login Data
    password='password'
    email='email@email.com'
    host = "10.0.1.123"               # Address of your Powerwall Gateway
    timezone = "America/Los_Angeles"  # Your local timezone
 
    # Connect to Powerwall
    pw = pypowerwall.Powerwall(host,password,email,timezone)

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

```

### pyPowerwall Module Class and Functions 
```
 Classes
    Powerwall(host, password, email, timezone)

 Functions 
    poll(api, jsonformat)   # Fetch data from Powerwall API URI (return json if True)
    level()                 # Fetch battery power level percentage
    power()                 # Fetch power data returned as dictionary
    site(verbose)           # Fetch site sensor data (W or raw json if verbose=True)
    solar(verbose):         # Fetch solar sensor data (W or raw json if verbose=True)
    battery(verbose):       # Fetch battery sensor data (W or raw json if verbose=True)
    load(verbose)           # Fetch load sensor data (W or raw json if verbose=True)
    grid()                  # Alias for site()
    home()                  # Alias for load()
```

## Credits and References

* Tesla Powerwall 2 – Local Gateway API documentation – https://github.com/vloschiavo/powerwall2
* Python Tesla Powerwall API – https://github.com/jrester/tesla_powerwall
* TESLA PowerWall 2 Security Shenanigans – https://github.com/hackerschoice/thc-tesla-powerwall2-hack
* Powerwall Monitoring – https://github.com/mihailescu2m/powerwall_monitor

