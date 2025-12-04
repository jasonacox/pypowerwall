# Tesla Developer - FleetAPI for Powerwall

⚠️ **DEPRECATION NOTICE**: This directory (`tools/fleetapi/`) contains outdated development code and should NOT be used. 

**Please use the built-in pypowerwall FleetAPI module instead:**

```bash
# Recommended method - use the pypowerwall module
python -m pypowerwall.fleetapi setup
python -m pypowerwall.fleetapi status --json
```

For full documentation, see the main README: https://github.com/jasonacox/pypowerwall?tab=readme-ov-file#fleetapi-setup---option-2

---

## Legacy Documentation (For Reference Only)

FleetAPI is a RESTful data and command service providing access to Tesla Powerwalls. Developers can interact with their own devices, or devices for which they have been granted access by a customer, through this API.

Note: the FleetAPI provides third party access to Tesla Vehicles as well as Energy Products.

## Requirements

* Tesla Partner Account - To be a developer, you will need to sign up as a Tesla Partner. This requires that you have a name (e.g. sole proprietor or business entity) and website.
* Web Site - You will need to own a domain name (website) and have control of that website. 

## Setup

Step 1 - Sign in to Tesla Developer Portal and make an App Access Request: See [Tesla App Access Request](https://developer.tesla.com/request) - During this process, you will need to set up and remember the following account settings:

* CLIENT_ID - This will be provided to you by Tesla when your request is approved.
* CLIENT_SECRET - Same as above.
* DOMAIN - The domain name of a website your own and control.
* REDIRECT_URI - This is the URL that Tesla will direct you to after you authenticate. This landing URL (on your website) will extract the GET variable `code`, which is a one-time use authorization code needed to generate the Bearer auth and Refresh token used to access your Tesla Powerwall energy devices. Place the [index.html](./index.html) file in a folder under this domain and use this as the REDIRECT_URI path in the setup below. Alternatively, you can just copy the URL from the 404 page during the authorization process (the code is in the URL).

Step 2 - Run the `create_pem_key.py` script and place the **public** key on your website at the URL: https://{DOMAIN}/.well-known/appspecific/com.tesla.3p.public-key.pem

Step 3 - Run SETUP using the built in pyPowerwall `fleetapi` setup mode. This will ask for all the details above, generate a partner token, register your partner account, generate a user token needed to access your Powerwall. It will also get the site_id and run a query to pull live power data for your Powerwall.

```bash
python -m pypowerwall fleetapi
```

Configuration data will be stored in `.pypowerwall.fleetap`.

## Command Line Usage

You can use the command line tool of pypowerwall to monitor and manage your Powerwall vit FleetAPI. Here are the commands:

```
PyPowerwall Module v0.10.2

commands (run <command> -h to see usage information):
  fleetapi            Setup Tesla FleetAPI for Cloud Mode access
  scan                Scan local network for Powerwall gateway
  set                 Set Powerwall Mode and Reserve Level
  get                 Get Powerwall Settings and Power Levels

  get options:
    -format FORMAT    Output format: text, json, csv

  set options:
    -mode MODE        Powerwall Mode: self_consumption, backup, or autonomous
    -reserve RESERVE  Set Battery Reserve Level [Default=20]
    -current          Set Battery Reserve Level to Current Charge

```

Examples

```bash
# Setup
python3 -m pypowerwall fleetapi

# Get Current Status
python3 -m pypowerwall get

# Set battery reserve level to 30%
python3 -m pypowerwall set -reserve 30

# Set Powerwall mode to autonomous TOU
python3 -m pypowerwall set -mode autonomous

```

## Stand Alone Tools

The `fleetapi.py` script is a command line utility and python class that you can use to monitor and manage your Powerwall. Here are teh command lines:

```
Tesla FleetAPI - Command Line Interface

Usage: fleetapi.py command [arguments] [-h] [--debug] [--config CONFIG] [--site SITE] [--json]

Commands:
    setup               Setup FleetAPI for your site
    sites               List available sites
    status              Report current power status for your site
    info                Display information about your site
    getmode             Get current operational mode setting
    getreserve          Get current battery reserve level setting
    setmode             Set operatinoal mode (self_consumption or autonomous)
    setreserve          Set battery reserve level (prcentage or 'current')
    
options:
  -h, --help            Show this help message and exit
  --debug               Enable debug mode
  --config CONFIG       Specify alternate config file (default: .fleetapi.config)
  --site SITE           Specify site_id
  --json                Output in JSON format
```

Examples

```bash
# Set battery reserve to 80%
python fleetapi.py setreserve 80

# Set battery reserver to be equal to current charge level
python fleetapi.py setreserve current

# Set operatinoal mode to Self Consumption
python fleetapi.py setmode self
```

## FleetAPI Class

You can import and use the FleetAPI class in your own scripts.

```
Class:
    FleetAPI - Tesla FleetAPI Class

 Functions:
    poll(api, action, data) - poll FleetAPI
    get_sites() - get sites
    site_name() - get site name

    get_live_status() - get the current power information for the site
    get_site_info() - get site info
    get_battery_reserve() - get battery reserve level
    get_operating_mode() - get operating mode
    solar_power() - get solar power
    grid_power() - get grid power
    battery_power() - get battery power
    load_power() - get load power
    battery_level() - get battery level
    energy_left() - get energy left
    total_pack_energy() - get total pack energy
    grid_status() - get grid status
    island_status() - get island status
    firmware_version() - get firmware version
    
    set_battery_reserve(reserve) - set battery reserve level (percent)
    set_operating_mode(mode) - set operating mode (self_consumption or autonomous)
     
```

Example Usage

```python
from fleetapi import FleetAPI

fleet = FleetAPI()

# Current Status
print(f"Solar: {fleet.solar_power()}")
print(f"Grid: {fleet.grid_power()}")
print(f"Load: {fleet.load_power()}")
print(f"Battery: {fleet.battery_power()}")
print(f"Battery Level: {fleet.battery_level()}")

# Change Reserve to 30%
fleet.set_battery_reserve(30)

# Change Operating Mode to Autonomous
fleet.set_operating_mode("autonomous")
```

## References

* Developer Documentation about APIs - https://developer.tesla.com/docs/fleet-api#energy-endpoints

