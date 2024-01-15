# pyPowerWall - Tesla FleetAPI - Setup
# -*- coding: utf-8 -*-
"""
 Tesla FleetAPI Setup
 
 This script will walk you through the steps to setup access to the
 Tesla FleetAPI. It will generate a partner token, register your
 partner account, generate a user token, and get the site_id for
 your Tesla Powerwall.
 
 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Requirements

 * Register your application https://developer.tesla.com/

 * Before running this script, you must first run create_pem_key.py
   to create a PEM key and register it with Tesla. Put the public
   key in {site}/.well-known/appspecific/com.tesla.3p.public-key.pem

 Requires: pip install requests
"""

# Imports
import requests
import sys
import json
import os

# Print Header
print("Tesla FleetAPI Setup")
print("--------------------")
print()
print("Step 1 - Register your application at https://developer.tesla.com/")
print("Step 2 - Run create_pem_key.py to create a PEM key file for your website.")
print("         Put the public key in {site}/.well-known/appspecific/com.tesla.3p.public-key.pem")
print("Step 3 - Run this script to generate a partner token, register your partner account,")
print("         generate a user token, and get the site_id and live data for your Tesla Powerwall.")
print()

# Default Settings
ENV_FILE = ".env"
PARTNER_TOKEN_FILE = ".fleetapi.partner_token.txt"
PARTNER_ACCOUNT_FILE = ".fleetapi.partner_account.json"
USER_TOKENS_FILE = ".fleetapi.user_tokens.json"
SITE_ID_FILE = ".fleetapi.site_id.txt"

# Function to return a random string of characters and numbers
def random_string(length):
    import random
    import string
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

# Function to load environment variables from a file
def load_env_file(file_path):
    # check if file exists
    if not os.path.isfile(file_path):
        return False
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                # remove any quotes and whitespace
                value = value.strip().strip("'").strip('"')
                os.environ[key] = value
    return True
                
# Registration - Tesla Developer FleetAPI at https://developer.tesla.com/
have_env = load_env_file(ENV_FILE)
CLIENT_ID=os.environ.get('CLIENT_ID', '')
CLIENT_SECRET=os.environ.get('CLIENT_SECRET', '')
DOMAIN=os.environ.get('DOMAIN','')
REDIRECT_URI=os.environ.get('REDIRECT_URI',f'https://{DOMAIN}/access')
# Region Specific Variables
AUDIENCE="https://fleet-api.prd.na.vn.cloud.tesla.com"
# Token Scopes
SCOPE = "openid offline_access energy_device_data energy_cmds"

# Prompt User to change the above variables if needed
print()
if have_env:
    print("Current Settings:")
    print(f"    CLIENT_ID: {CLIENT_ID}")
    print(f"    CLIENT_SECRET: {CLIENT_SECRET}")
    print(f"    DOMAIN: {DOMAIN}")
    print(f"    REDIRECT_URI: {REDIRECT_URI}")
    print()
    print("Do you want to change existing settings? (y/N)", end='')
    change_vars = input()
if not have_env or change_vars.lower() == 'y':
    print("Note: Before running this script, you must first register your application at https://developer.tesla.com/")
    print()
    print("Enter your Tesla Developer Account:\n")
    print(f"  Enter CLIENT_ID [{CLIENT_ID}]: ", end='')
    ans = input()
    if ans:
        CLIENT_ID = ans
    print(f"  Enter CLIENT_SECRET [{CLIENT_SECRET}]: ", end='')
    ans = input()
    if ans:
        CLIENT_SECRET = ans
    print(f"  Enter DOMAIN [{DOMAIN}]: ", end='')
    ans = input()
    if ans:
        DOMAIN = ans
    if REDIRECT_URI == f'https:///access':
        REDIRECT_URI = f'https://{DOMAIN}/access'
    print(f"  Enter REDIRECT_URI [{REDIRECT_URI}]: ", end='')
    ans = input()
    if ans:
        REDIRECT_URI = ans
    # Write to .env file
    with open('.env', 'w') as f:
        f.write(f"CLIENT_ID='{CLIENT_ID}'\n")
        f.write(f"CLIENT_SECRET='{CLIENT_SECRET}'\n")
        f.write(f"DOMAIN='{DOMAIN}'\n")
        f.write(f"REDIRECT_URI='{REDIRECT_URI}'\n")
    print("  Settings saved to .env file.")
else:
    print("  No changes made.")

# Verify that the PEM key file exists
verify_url = f"https://{DOMAIN}/.well-known/appspecific/com.tesla.3p.public-key.pem"
response = requests.get(verify_url)
if response.status_code != 200:
    print(f"ERROR: Could not verify PEM key file at {verify_url}")
    print(f"       Make sure you have created the PEM key file and uploaded it to your website.")
    print()
    print("Run create_pem_key.py to create a PEM key file for your website.")
    exit(1)
else:
    print(f"\nSuccess: PEM Key file verified at {verify_url}.\n")
    
# Step 3A - Generating a partner authentication token
#   Generates a token to be used for managing a partner's 
#   account or devices they own.
print("Generating a partner authentication token...")
# Check to see if already cached
try:
    with open(PARTNER_TOKEN_FILE, 'r') as f:
        partner_token = f.read()
    print(f"Using cached token: {partner_token}\n")
except:
    # If not cached, generate a new token
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'openid offline_access energy_device_data energy_cmds',
        'audience': AUDIENCE
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.post('https://auth.tesla.com/oauth2/v3/token', 
                    data=data, headers=headers)
    print(f"Response Code: {response.status_code}")
    partner_token = response.json()['access_token']
    print(f"Got Token: {partner_token}\n")
    # Write token to file
    with open(PARTNER_TOKEN_FILE, 'w') as f:
        f.write(partner_token)

# Step 3B - Register Partner Account in Region
print("Registering Partner Account in Region...")
# Check to see if already registered
try:
    with open(PARTNER_ACCOUNT_FILE, 'r') as f:
        partner_account = json.loads(f.read())
    print(f"Using cached partner account: {partner_account}\n")
except:
    # If not registered, register
    url = 'https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/partner_accounts'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + partner_token
    }
    data = {
        'domain': DOMAIN
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    print(f"Response Code: {response.status_code}")
    print(f"Response: {response.json()}\n")
    # Write response to file
    with open(PARTNER_ACCOUNT_FILE, 'w') as f:
        f.write(json.dumps(response.json()))

# Step 3C - Generating a third-party token on behalf of a customer
#   We will Use an Authorization Code to generate a token that
#   can be used to make API calls on behalf of a customer.
print("Generating a third-party token on behalf of a customer...")
# Check to see if already cached
try:
    with open(USER_TOKENS_FILE, 'r') as f:
        user_tokens = json.loads(f.read())
        access_token = user_tokens['access_token']
        refresh_token = user_tokens['refresh_token']
    print(f"Using cached user tokens: {user_tokens}\n")
except:
    scope = SCOPE.replace(" ", "%20")
    state = random_string(64)
    url = f"https://auth.tesla.com/oauth2/v3/authorize?&client_id={CLIENT_ID}&locale=en-US&prompt=login&redirect_uri={REDIRECT_URI}&response_type=code&scope={scope}&state={state}"
    # Prompt user to login to Tesla account and authorize access
    print("  Login to your Tesla account to authorize access.")
    print(f"  Go to this URL: {url}")
    # If on Mac, automatically open the URL in the default browser
    if sys.platform == 'darwin':
        import subprocess
        subprocess.call(['open', url])
    print("\nAfter authorizing access, copy the code from the URL and paste it below.")
    code = input("  Enter the code: ")
    print()

    # Step 3D - Exchange the authorization code for a token
    #   The access_token will be used as the Bearer token 
    #   in the Authorization header when making API requests.
    print("Exchange the authorization code for a token")
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'audience': AUDIENCE,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                    data=data, headers=headers)
    # Extract access_token and refresh_token from this response
    access_token = response.json()['access_token']
    refresh_token = response.json()['refresh_token']
    print(f"Response Code: {response.status_code}")
    print(f"Access Token: {access_token}")
    print(f"Refresh Token: {refresh_token}\n")
    # Write both tokens to file
    with open(USER_TOKENS_FILE, 'w') as f:
        f.write(json.dumps(response.json()))

# Utility Function to Refresh Token
def refresh_token():
    print("Token expired, refreshing token...")
    data = {
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'refresh_token': refresh_token
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.post('https://auth.tesla.com/oauth2/v3/token',
                    data=data, headers=headers)
    # Extract access_token and refresh_token from this response
    access_token = response.json()['access_token']
    refresh_token = response.json()['refresh_token']
    print(f"  Response Code: {response.status_code}")
    print(f"  Access Token: {access_token}")
    print(f"  Refresh Token: {refresh_token}\n")
    # Write both tokens to file
    with open(USER_TOKENS_FILE, 'w') as f:
        f.write(json.dumps(response.json()))

# Step 3E - Get list of Sites
#   Get a list of sites associated with the account.
print("Get list of Sites...")
url = "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/products"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token
}
response = requests.get(url, headers=headers)
# Did we get a 403 response?
if response.status_code == 403:
    # Refresh token
    refresh_token()
    # Try again
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token
    }
    response = requests.get(url, headers=headers)
print(f"Response Code: {response.status_code}")
# Print response
print(f"Response: {response.json()}\n")
# Extract the site_id from the response
site_id = response.json()['response'][0]['energy_site_id']
print(f"Site ID: {site_id}\n")
# Write site_id to file
with open(SITE_ID_FILE, 'w') as f:
    f.write(str(site_id))

# Step 3F - Get Site Power Information
#   Get the current power information for the site.
print("Get Site Power Information...")
url = f"https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/energy_sites/{site_id}/live_status"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer " + access_token
}
response = requests.get(url, headers=headers)
if response.status_code == 403:
    # Refresh token
    refresh_token()
    # Try again
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token
    }
    response = requests.get(url, headers=headers)
print(f"Response Code: {response.status_code}")
print(f"Response: {response.json()}\n")
