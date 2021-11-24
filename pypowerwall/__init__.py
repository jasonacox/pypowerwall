# pyPowerWall Module
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Features
    * Works with Tesla Energy Gateways - Powerwall+ 
    * Simple access through easy to use functions using customer credentials
    * Will cache authentication to reduce load on Powerwall Gateway
    * Will cache responses for 5s to limit number of calls to Powerwall Gateway

 Classes
    Powerwall(host, password, email, timezone)

 Functions 
    poll(api, jsonformat)   # Fetch data from Powerwall API URI
    level()                 # Fetch battery power level percentage (float)
    power()                 # Fetch power data returned as dictionary
    site(verbose)           # Fetch site sensor data (W or raw json if verbose=True)
    solar(verbose):         # Fetch solar sensor data (W or raw json if verbose=True)
    battery(verbose):       # Fetch battery sensor data (W or raw json if verbose=True)
    load(verbose)           # Fetch load sensor data (W or raw json if verbose=True)

"""
import json, time
import requests
import urllib3
urllib3.disable_warnings() # Disable SSL warnings
import logging
import sys

version_tuple = (0, 0, 3)
version = __version__ = '%d.%d.%d' % version_tuple
__author__ = 'jasonacox'

log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

def set_debug(toggle=True, color=True):
    """Enable verbose logging"""
    if(toggle):
        if(color):
            logging.basicConfig(format='\x1b[31;1m%(levelname)s:%(message)s\x1b[0m',level=logging.DEBUG)
        else:
            logging.basicConfig(format='%(levelname)s:%(message)s',level=logging.DEBUG)
        log.setLevel(logging.DEBUG)
        log.debug("%s [%s]\n" % (__name__, __version__))
    else:
        log.setLevel(logging.NOTSET)

class Powerwall(object):
    def __init__(self, host="", password="", email="nobody@nowhere.com", timezone="America/Los_Angeles"):
        """
        Represents a Tesla Energy Gateway Powerwall device.

        Args:
            host        = Hostname or IP address of Powerwall (e.g. 10.0.1.99)
            password    = Customer password set up on Powerwall gateway
            email       = Customer email 
            timezone    = Timezone for location of Powerwall 
                (see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) 

        """

        # Attributes
        self.cachefile = ".powerwall"  # Stores auth session information
        self.host = host
        self.password = password
        self.email = email
        self.timezone = timezone
        self.timeout = 10           # 10s timeout for http calls
        self.auth = {}              # caches authentication cookies
        self.pwcachetime = {}       # holds the cached data timestamps for api
        self.pwcache = {}           # holds the cached data for api
        self.pwcacheexpire = 5      # seconds to expire cache 

        # Get auth session
        try:
            f = open(self.cachefile, "r")
            self.auth = json.load(f)
            log.debug('loaded auth from cache file %s' % self.cachefile)
        except:
            log.debug('no auth cachefile - creating')
            self._get_session()

    def _get_session(self):
        # Login and create a new session
        url = "https://%s/api/login/Basic" % self.host
        pload = {"username":"customer","password":self.password,
            "email":self.email,"clientInfo":{"timezone":self.timezone}}
        r = requests.post(url,data = pload, verify=False, timeout=self.timeout)
        log.debug('login - %s' % r.text)

        # Save Auth cookies
        self.auth = {'AuthCookie': r.cookies['AuthCookie'], 'UserRecord': r.cookies['UserRecord']}
        try:
            f = open(self.cachefile, "w") 
            json.dump(self.auth,f)
            f.close()
        except:
            log.debug('unable to cache auth session - continuing')

    def _close_session(self):
        # Log out
        url = "https://%s/api/logout" % self.host
        g = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout)
        self.auth = {}

    def poll(self, api='/api/site_info/site_name', jsonformat=False, raw=False):
        # Query powerwall and return payload as string
        # First check to see if in cache
        fetch = True
        if(api == '/api/devices/vitals'):
            # Force true for vitals call = protobuf binary payload
            raw = True
        if(api in self.pwcache and api in self.pwcachetime):
            # is it expired?
            if(time.time() - self.pwcachetime[api] < self.pwcacheexpire):
                payload = self.pwcache[api]
                fetch = False
        if(fetch):
            url = "https://%s%s" % (self.host, api)
            if(raw):
                r = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout, stream=True)
            else:
                r = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout)
            if r.status_code >= 400 and r.status_code < 500:
                # Session Expired - get a new one
                self._get_session()
                if(raw):
                    r = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout, stream=True)
                else:
                    r = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout)
            if(raw):
                payload = r.raw.data
            else:
                payload = r.text
            self.pwcache[api] = payload
            self.pwcachetime[api] = time.time()
        if(jsonformat):
            try:
                data = json.loads(payload)
                return data
            except:
                log.debug('ERROR invalid json response: %r' % payload)
                return None
        else:
            return payload
        
    def level(self):
        # Return power level percentage for battery
        level = 0
        payload = self.poll('/api/system_status/soe', jsonformat=True)
        if(payload is not None and 'percentage' in payload):
            level = payload['percentage']
        return level
    
    def power(self):
        # Return power for (site, solar, battery, load) as dictionary
        site = solar = battery = load = 0.0
        payload = self.poll('/api/meters/aggregates', jsonformat=True)
        try:
            site = payload['site']['instant_power']
            solar = payload['solar']['instant_power']
            battery = payload['battery']['instant_power']
            load = payload['load']['instant_power']
        except:
            log.debug('ERROR unable to parse payload for power: %r' % payload)
        return {'site': site, 'solar': solar, 'battery': battery, 'load': load}
        
    def _fetchpower(self, sensor, verbose=False):
        # Helper function - pull individual power for sensor
        if(verbose):
            payload = self.poll('/api/meters/aggregates', jsonformat=True)
            if(payload and sensor in payload):
                return payload[sensor]
            else:
                return None
        r = self.power()
        if(r and sensor in r):
            return r[sensor]

    # Pull Power Data from Sensor
    def site(self, verbose=False):
        return self._fetchpower('site',verbose)
        
    def solar(self, verbose=False):
        return self._fetchpower('solar',verbose)

    def battery(self, verbose=False):
        return self._fetchpower('battery',verbose)

    def load(self, verbose=False):
        return self._fetchpower('load',verbose)

    # Helpful aliases
    def grid(self, verbose=False):
        return self.site(verbose)

    def home(self, verbose=False):
        return self.load(verbose)