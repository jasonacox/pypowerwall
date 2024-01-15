# pyPowerWall - Tesla FleetAPI - Setup
# -*- coding: utf-8 -*-
"""
 Tesla FleetAPI - Poll Live Status
 
 This script is an example of using the Tesla FleetAPI to poll 
 configuration and power data from the PowerWall.
 
 Requirements:
    - Tesla Partner Account
    - Run setup.py first to get tokens

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

"""
# Import Modules
import requests
import json
import os

# Configuration Files - Required
ENV_FILE = ".env"  # Location of CLIENT_ID
USER_TOKENS_FILE = ".fleetapi.user_tokens.json"

# Load Environment Variables
if os.path.isfile(ENV_FILE):
    with open(ENV_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                # remove any quotes and whitespace
                value = value.strip().strip("'").strip('"')
                os.environ[key] = value

CLIENT_ID=os.environ.get('CLIENT_ID', '')

# Load Access Token
try:
    with open(USER_TOKENS_FILE, 'r') as f:
        user_tokens = json.loads(f.read())
        access_token = user_tokens['access_token']
        refresh_token = user_tokens['refresh_token']
    print(f"Using cached user tokens: {user_tokens}\n")
except:
    print("No cached user tokens found, please run setup.py first.")
    exit(1)

# Utility Function to Refresh Token
def new_token():
    global access_token, refresh_token
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

# Function to poll FleetAPI
def poll(api="api/1/products"):
    url = f"https://fleet-api.prd.na.vn.cloud.tesla.com/{api}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + access_token
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 401:
        # Token expired, refresh token and try again
        new_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + access_token
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 401:
            print("Token expired, refresh token failed, exiting...")
            return None
    return response.json()

# Get list of sites
print(" Get list of Sites")
site_id = "0"
payload = poll("api/1/products")
print(f"  Response: {payload}")
if payload and 'response' in payload:
    # Extract the site_id from the response
    site_id = payload['response'][0]['energy_site_id']
    print(f"  Site ID: {site_id}\n")
else:
    print("  No sites found, exiting...\n")
    exit(1)

# Get the current power information for the site.
payload = poll(f"api/1/energy_sites/{site_id}/live_status")    
print(f"  Response: {payload}\n")

# Get site info
payload = poll(f"api/1/energy_sites/{site_id}/site_info")
print(f"  Response: {payload}\n")


