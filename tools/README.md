# Tools

## Set Reserve

This command line tool allows you to read and set the Powerwall minimum backup reserve battery level (percentage).

### Setup

```bash
# Install python modules
pip install python-dateutil teslapy

# Login to Tesla account to set up token
python3 set-reserve.py --login
```

This will create the config file, save an auth token so you will not need to login again, and then display the energy site details associated with your Tesla account. It will run in an interactive mode.

```
Config file 'set-reserve.conf' not found

Do you want to create the config now? [Y/n] Y

Tesla Account Setup
-------------------
Email address: your@email.address
Save auth token to: [set-reserve.auth]

Config saved to 'set-reserve.conf'
```

After the config is saved, you will be prompted to login to your Tesla account. This is done by opening the displayed URL in your browser and then logging in.

**NOTE**: After you log in, it will take you to a *404 Page Not Found* error page - do not panic, 
this is what you want.

```
----------------------------------------
Tesla account: your@email.address
----------------------------------------
Open the below address in your browser to login.

<copy URL to browser> e.g.: https://auth.tesla.com/oauth2/v3/authorize?response_type=code...etc.

After login, paste the URL of the 'Page Not Found' webpage below.

Enter URL after login: <paste URL from browser> e.g.: https://auth.tesla.com/void/callback?code=...etc.
```

After you have logged in successfully, the browser will show a 'Page Not Found' webpage. Copy the URL of this page and paste it at the prompt.

Once logged in successfully, you will be shown details of the energy site(s) associated with your account:

```
----------------------------------------
Tesla account: your@email.address
----------------------------------------
      Site ID: 1234567890
    Site name: My Powerwall
     Timezone: Australia/Sydney
    Installed: 2021-04-01 13:09:54+11:00
  System time: 2022-10-13 22:40:59+11:00
----------------------------------------
```

Once these steps are completed, you should not have to login again.

### Usage

* Display Current Battery Reserve Setting

    ```bash
    # Verbose Response
    python3 set-reserve.py --read

    # Abbreviated Response
    python3 set-reserve.py --read -n
    ```

* Set Battery Reserve Setting

    ```bash
    # Set reserve percentage
    python3 set-reserve.py --set 25

    # Set reserve based on current battery level - useful 
    # to pause charging and discharging 
    python3 set-reserve.py --current
    ```

  `READ: Current Battery Reserve Setting: 25% for 2 Powerwalls`

  `SET: Current Battery Reserve Setting: 25% - Response: Updated`


* Cron Job Examples

  See the [cron.sh](cron.sh) example script on how you can use set-reserve.py to optimize your Powerwall usage.
  

## Set Mode

This command line tool allows you to read and set the Powerwall operational mode (self-powered or time-based control).

### Setup

```bash
# Install python modules
pip install python-dateutil teslapy

# Login to Tesla account to set up token
python3 set-mode.py --login
```

This will create the config file, save an auth token so you will not need to login again, and then display the energy site details associated with your Tesla account. It will run in an interactive mode.  See the instructions for the "Set Reserve" tool above.

### Usage

* Display Current Operational Mode

    ```bash
    # Verbose Response
    python3 set-mode.py --read

    # Abbreviated Response
    python3 set-mode.py --read -n
    ```

  `READ: Current Operational Mode: self_consumption with 2 Powerwalls`

* Set Operational Mode

    ```bash
    # Set to Self Powered mode
    python3 set-reserve.py --set self

    # Set to Time-Based Control mode
    python3 set-reserve.py --set time
    ```
## TesSolarCharge

This python script allows you to change your Tesla car charging speed (amps) in realtime with solar production and home energy consumption (to minimize drawing and feeding power back to the grid), using PyPowerwall to get the energy data from the PowerWall local gateway, and TeslaPy to set charging speed via Tesla's Cloud API.

### Setup

Modify the TesSolarCharge.py file and enter in your Tesla-associated email address (login), your latitude and longitude (as numeric with three decimal places), the IP address of the computer running PyPowerwall on your local network, and the hour of the day when you want charging to stop:
```
username = 'yourname@example.com' # Fill in Tesla login email address/account
lat, lon  = ##.###, -###.###        # Fill in Location where charging will occur (shown at startup)
pypowerwall_IP = '10.x.x.x:8675'	# Fill in IP address and port for pypowerwall docker container
stop_charge_hour = 16 #hour of the day to stop charging (i.e. peak electricity rates to not discharge powerwall or when solar production expected to be around min charging rate causing charging to start and stop frequently
```

Install Python modules and try to authorize TeslaPy
```bash
# Install python modules
pip install teslapy

# Login to Tesla account to set up token
python3 TesSolarCharge.py
```

The first time you run the script if TeslaPy is not authorized, it should provide a Tesla website URL, where you can login with your Tesla account credentials.

**NOTE**: After you log in, it will take you to a *404 Page Not Found* error page - do not panic, 
this is what you want.

```
----------------------------------------
Tesla account: your@email.address
----------------------------------------
Open the below address in your browser to login.

<copy URL to browser> e.g.: https://auth.tesla.com/oauth2/v3/authorize?response_type=code...etc.

After login, paste the URL of the 'Page Not Found' webpage below.

Enter URL after login: <paste URL from browser> e.g.: https://auth.tesla.com/void/callback?code=...etc.
```

After you have logged in successfully, the browser will show a 'Page Not Found' webpage. Copy the URL of this page and paste it at the prompt.

### Usage

* Run the TesSolarCharge.py script

    ```bash
    # Run TesSolarCharge.py to start charging your car and adjusting rate based on solar
    python3 TesSolarCharge.py
    ```
	
### Credit

These tools (set-reserve and set-mode) are based on the the amazing [tesla_history.py](https://github.com/jasonacox/Powerwall-Dashboard/tree/main/tools/tesla-history) tool by Michael Birse (@mcbirse) that imports Tesla cloud history into the [Powerwall-Dashboard](https://github.com/jasonacox/Powerwall-Dashboard).

TesSolarCharge is based on TesSense w/ SenseLink  by Randy Spencer (https://github.com/israndy/TesSense), modified by Nate Carroll to work with PyPowerwall and add a few features. 
