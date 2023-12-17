#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 Python library to pull live Powerwall or Solar history data from Tesla Owner API 
 (Tesla cloud).

 Author: Jason A. Cox based on tesla-history.py by Michael Birse
 For more information see https://github.com/jasonacox/pypowerwall

 Classes
    TeslaCloud(email, timezone, pwcacheexpire, timeout)

 Parameters
    email                   # (required) email used for logging into the gateway
    timezone                # (required) desired timezone
    pwcacheexpire = 5       # Set API cache timeout in seconds
    timeout = 10            # Timeout for HTTPS calls in seconds

"""
import sys
try:
    from teslapy import Tesla, Retry, JsonDict, Battery, SolarPanel
except:
    sys.exit("ERROR: Missing python teslapy module. Run 'pip install teslapy'.")
import pypowerwall
import logging

AUTHFILE = f"pypowerwall.auth"
ALLOWLIST = [
    '/api/status', '/api/site_info/site_name', '/api/meters/site',
    '/api/meters/solar', '/api/sitemaster', '/api/powerwalls', 
    '/api/customer/registration', '/api/system_status', '/api/system_status/grid_status',
    '/api/system/update/status', '/api/site_info', '/api/system_status/grid_faults',
    '/api/operation', '/api/site_info/grid_codes', '/api/solars', '/api/solars/brands',
    '/api/customer', '/api/meters', '/api/installer', '/api/networks', 
    '/api/system/networks', '/api/meters/readings', '/api/synchrometer/ct_voltage_references',
    '/api/troubleshooting/problems', '/api/auth/toggle/supported'
    ]

version_tuple = pypowerwall.version_tuple
version = __version__ = '%d.%d.%d' % version_tuple
__author__ = pypowerwall.__author__

log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

def lookup(data, keylist):
    """
    Search data for list of keys and return the first matching key's value if found, otherwise return None
    """
    for key in keylist:
        if key in data:
            return data[key]
    return None

class TeslaCloud:
    def __init__(self, email, pwcacheexpire=5, timeout=10):
        self.email = email
        self.timeout = timeout
        self.site = None
        self.tesla = None   
        self.retry = None
        self.pwcachetime = {}                   # holds the cached data timestamps for api
        self.pwcache = {}                       # holds the cached data for api
        self.pwcacheexpire = pwcacheexpire      # seconds to expire cache 
        
        # Create retry instance for use after successful login
        self.retry = Retry(total=2, status_forcelist=(500, 502, 503, 504), backoff_factor=10)

        # Create Tesla instance
        self.tesla = Tesla(email, cache_file=AUTHFILE)

        if not self.tesla.authorized:
            # Login to Tesla account and cache token
            state = self.tesla.new_state()
            code_verifier = self.tesla.new_code_verifier()

            try:
                self.tesla.fetch_token(authorization_response=self.tesla.authorization_url(state=state, code_verifier=code_verifier))
            except Exception as err:
                log.error(f"ERROR: Login failure - {repr(err)}")
        else:
            # Enable retries
            self.tesla.close()
            self.tesla = Tesla(email, retry=self.retry, cache_file=AUTHFILE)

    def poll(self, api):
        """
        Poll the Tesla Cloud API to get data for the API request

        TODO: Make this work - placeholders only
        """
        if self.tesla is None:
            return None
        # Check to see if we have cached data
        if api in self.pwcache:
            if self.pwcachetime[api] > time.time() - self.pwcacheexpire:
                return self.pwcache[api]
        else:
            # Determine what data we need based on Powerwall APIs (ALLOWLIST)
            if api == '/api/status':
                data = self.tesla.get_status()
            elif api == '/api/site_info/site_name':
                data = self.tesla.get_site_info()
            elif api == '/api/meters/site':
                data = self.tesla.get_meter_sites()
            elif api == '/api/meters/solar':
                data = self.tesla.get_meter_solar()
            elif api == '/api/sitemaster':
                data = self.tesla.get_sitemaster()
            elif api == '/api/powerwalls':
                data = self.tesla.get_powerwalls()
            elif api == '/api/customer/registration':
                data = self.tesla.get_customer_registration()
            elif api == '/api/system_status':
                data = self.tesla.get_system_status()
            elif api == '/api/system_status/grid_status':
                data = self.tesla.get_system_status_grid_status()
            elif api == '/api/system/update/status':
                data = self.tesla.get_system_update_status()
            elif api == '/api/site_info':
                data = self.tesla.get_site_info()
            elif api == '/api/system_status/grid_faults':
                data = self.tesla.get_system_status_grid_faults()
            elif api == '/api/operation':
                data = self.tesla.get_operation()
            elif api == '/api/site_info/grid_codes':
                data = self.tesla.get_site_info_grid_codes()
            elif api == '/api/solars':
                data = self.tesla.get_solars()
            elif api == '/api/solars/brands':
                data = self.tesla.get_solars_brands()
            elif api == '/api/customer':
                data = self.tesla.get_customer()
            elif api == '/api/meters':
                data = self.tesla.get_meters()
            elif api == '/api/installer':
                data = self.tesla.get_installer()
            elif api == '/api/networks':
                data = self.tesla.get_networks()
            elif api == '/api/system/networks':
                data = self.tesla.get_system_networks()
            elif api == '/api/meters/readings':
                data = self.tesla.get_meter_readings()
            elif api == '/api/synchrometer/ct_voltage_references':
                data = self.tesla.get_synchrometer_ct_voltage_references()
        return data
    
    def getsites(self):
        """
        Get list of Tesla Energy sites

        TODO: Make this work
        """
        if self.tesla is None:
            return None
        try:
            sitelist = self.tesla.battery_list() + self.tesla.solar_list()
        except Exception as err:
            log.error(f"ERROR: Failed to retrieve sitelist - {repr(err)}")
            return None
        return sitelist
    
    def setup(self):
        """
        Set up the Tesla Cloud connection

        TODO: Make this work
        """
        print("\nTesla Account Setup")
        print("-" * 19)

        while True:
            response = input("Email address: ").strip()
            if "@" not in response:
                print("Invalid email address\n")
            else:
                TUSER = response
                break

        # Create retry instance for use after successful login
        retry = Retry(total=2, status_forcelist=(500, 502, 503, 504), backoff_factor=10)

        # Create Tesla instance
        tesla = Tesla(self.email, cache_file=AUTHFILE)

        if not tesla.authorized:
            # Login to Tesla account and cache token
            state = tesla.new_state()
            code_verifier = tesla.new_code_verifier()

            try:
                print("Open the below address in your browser to login.\n")
                print(tesla.authorization_url(state=state, code_verifier=code_verifier))
            except Exception as err:
                log.error(f"ERROR: Connection failure - {repr(err)}")

            print("\nAfter login, paste the URL of the 'Page Not Found' webpage below.\n")

            tesla.close()
            tesla = Tesla(self.email, retry=retry, state=state, code_verifier=code_verifier, cache_file=AUTHFILE)

            if not tesla.authorized:
                try:
                    tesla.fetch_token(authorization_response=input("Enter URL after login: "))
                    print("-" * 40)
                except Exception as err:
                    sys_exit(f"ERROR: Login failure - {repr(err)}")
        else:
            # Enable retries
            tesla.close()
            tesla = Tesla(self.email, retry=retry, cache_file=AUTHFILE)


# TODO: Test code