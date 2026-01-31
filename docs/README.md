# pyPowerwall Documentation

Welcome to the pyPowerwall documentation hub. This page provides organized access to all documentation resources for users, developers, and contributors.

## Getting Started

New to pyPowerwall? Start with the main [README](../README.md) for installation instructions and basic setup.

## How-To Guides

### View Local Tesla Powerwall Portal

The Powerwall 2 gateway has a web based portal that you can access to the power flow animation. This requires that you find the local IP address of you Powerwall.  You can do that using `pypowerwall`:


```bash
# Install pyPowerwall if you haven't already
python -m pip install pypowerwall

# Scan Network for Powerwall
python -m pypowerwall scan
```

After confirming your local network address space, it will scan your network looking for a Tesla Powerwall and respond with something like this:

```
Discovered 1 Powerwall Gateway
     10.0.1.23 [1234567-00-E--TG123456789ABC]
```

For Powerwall 2 and + systems, point your browser to that address http://10.0.1.23 and you will be able to log in and see the power details and flow animation:

[![portal.png](portal.png)](portal.png)

Note: This is not available for Powerwall 3 systems. See the [pypowerwall-server](https://github.com/jasonacox/pypowerwall-server) project for an alternative local portal.

### Solar Panel Strings

You can use pyPowerwall to grab individual string data.  It uses the protobuf payload from the 'vitals' API.

```python
import pypowerwall

# Credentials for your Powerwall
password='password'
email='email@example.com'
host = "10.0.1.123"               # Address of your Powerwall Gateway
timezone = "America/Los_Angeles"  # Your local timezone

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Print String Data in JSON
print(pw.strings(True))   # True = JSON format output
```

Output example:

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

### Device Vitals

Access detailed device vitals data from your Powerwall system:

```python
import pypowerwall

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Display Device Vitals
print("Device Vitals:\n %s\n" % pw.vitals(True))
```

Example Output: [vitals-example.json](vitals-example.json)

## Reference Documentation

### Firmware History
Complete list of Powerwall firmware versions, release dates, and known features/issues.
- [Firmware History](reference/firmware-history.md)

### Devices
Comprehensive information about Powerwall devices (STSTSM, TETHC, TEPOD, TEPINV, TESYNC, TEMSA, PVAC, PVS, NEURIO, TESLA) including ECU types, part numbers, and component relationships.
- [Device Reference](reference/devices.md)

### Alerts
Detailed alert codes and descriptions that may appear in device vitals.
- [Alert Codes](reference/alerts.md)

## API Documentation

Full API reference for pyPowerwall methods and endpoints.
- [API Documentation](../API.md)

## Contributing

Interested in contributing? See our contribution guidelines.
- [Contributing Guide](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
