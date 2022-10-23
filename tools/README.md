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

After the config is saved, you will be prompted to login to your Tesla account. This is done by opening the displayed URL in your browser and then logging in:

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

* Display Battery Reserve Setting

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
    ```

`READ: Current Battery Reserve Setting: 25% for 2 Powerwalls`

`SET: Current Battery Reserve Setting: 25% - Response: Updated`
