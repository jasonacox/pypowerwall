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
    poll(api, jsonformat)           # Fetch data from Powerwall API URI
    level()                         # Fetch battery power level percentage (float)
    power()                         # Fetch power data returned as dictionary
    site(verbose)                   # Fetch site sensor data (W or raw json if verbose=True)
    solar(verbose):                 # Fetch solar sensor data (W or raw json if verbose=True)
    battery(verbose):               # Fetch battery sensor data (W or raw json if verbose=True)
    load(verbose)                   # Fetch load sensor data (W or raw json if verbose=True)
    vitals(jsonformat)              # Fetch raw Powerwall vitals
    strings(jsonformat, verbose)    # Fetch solar panel string data
    din()                           # Display DIN
    uptime()                        # Display uptime - string hms format
    version()                       # Display system version
    status(param)                   # Display status (JSON) or individual param
    site_name()                     # Display site name
    temps()                         # Display Powerwall Temperatures

"""
import json, time
import requests
import urllib3
urllib3.disable_warnings() # Disable SSL warnings
import logging
import sys
from . import tesla_pb2           # Protobuf definition for vitals

version_tuple = (0, 3, 0)
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

    def poll(self, api='/api/site_info/site_name', jsonformat=False, raw=False, recursive=False):
        """
        Query Tesla Energy Gateway Powerwall for API Response
        
        Args:
            api         = URI 
            jsonformat  = If True, convert JSON response to Python Dictionary, otherwise return text
            raw         = If True, send raw data back (useful for binary responses)
            recursive   = If True, this is a recursive call and do not allow additional recursive calls
        """
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
            try:
                if(raw):
                    r = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout, stream=True)
                else:
                    r = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout)
            except requests.exceptions.Timeout:
                log.debug('ERROR Timeout waiting for Powerwall API %s' % url)
                return None
            except requests.exceptions.ConnectionError:
                log.debug('ERROR Unable to connect to Powerwall at %s' % url)
                return None
            except:
                log.debug('ERROR Unknown error connecting to Powerwall at %s' % url)
                return None
            if r.status_code >= 400 and r.status_code < 500:
                # Session Expired - Try to get a new one unless we already tried
                if(not recursive):
                    self._get_session()
                    return self.poll(api, jsonformat, raw, True)
                else:
                    log.debug('ERROR Unable to establish session with Powerwall at %s - check password' % url)
                    return None
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
        
    def level(self, scale=False):
        """ 
        Battery Level Percentage 
        
        Args:
            scale = If True, convert battery level to app scale value
            Note: Tesla App reserves 5% of battery = ( (batterylevel / 0.95) - (5 / 0.95) )
        """
        # Return power level percentage for battery
        level = 0
        payload = self.poll('/api/system_status/soe', jsonformat=True)
        if(payload is not None and 'percentage' in payload):
            level = payload['percentage']
        if scale:
            return ((level / 0.95) - (5 / 0.95))
        else:
            return level
    
    def power(self):
        """
        Power Usage for Site, Solar, Battery and Load
        """
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

    def vitals(self, jsonformat=False):
        """
        Device Vitals Data

        Args:
           jsonformat = If True, return JSON format otherwise return Python Dictionary
        """
        # Pull vitals payload - binary protobuf 
        stream = self.poll('/api/devices/vitals')
        if(not stream):
            return None

        # Protobuf payload processing
        pb = tesla_pb2.DevicesWithVitals()
        pb.ParseFromString(stream)
        num = len(pb.devices)
        log.debug("Found %d devices." % num)

        # Decode Device Details
        x = 0
        output = {}
        while(x < num):
            # Each device
            device = pb.devices[x].device.device
            name = str(device.din.value)
            if name not in output.keys():
                output[name] = {}                    
                # Capture all primary fields
                try:
                    if device.HasField("componentParentDin"):
                        output[name]['componentParentDin'] = str(device.componentParentDin.value)
                    if device.HasField("partNumber"):
                        output[name]['partNumber'] = str(device.partNumber.value)
                    if device.HasField("serialNumber"):
                        output[name]['serialNumber'] = str(device.serialNumber.value)
                    if device.HasField("manufacturer"):
                        output[name]['manufacturer'] = str(device.manufacturer.value)
                    if device.HasField("firmwareVersion"):
                        output[name]['firmwareVersion'] = str(device.firmwareVersion.value)
                    if device.HasField("firstCommunicationTime"):
                        output[name]['firstCommunicationTime'] = int(device.firstCommunicationTime.seconds)                    
                    if device.HasField("lastCommunicationTime"):
                        output[name]['lastCommunicationTime'] = int(device.lastCommunicationTime.seconds)
                except:
                    log.debug("Error: Unable to extract primary fields - skipping.")
            if device.HasField("deviceAttributes"):
                # Capture all attributes
                try:
                    attributes = device.deviceAttributes
                    if attributes.HasField("teslaEnergyEcuAttributes"):
                        output[name]['teslaEnergyEcuAttributes'] = {}
                        output[name]['teslaEnergyEcuAttributes']['ecuType'] = int(attributes.teslaEnergyEcuAttributes.ecuType)
                    if attributes.HasField("generatorAttributes"):
                        output[name]['generatorAttributes'] = {}
                        output[name]['generatorAttributes']['nameplateRealPowerW'] = int(attributes.generatorAttributes.nameplateRealPowerW)
                        output[name]['generatorAttributes']['nameplateApparentPowerVa'] = int(attributes.generatorAttributes.nameplateApparentPowerVa)
                    if attributes.HasField("pvInverterAttributes"):
                        output[name]['pvInverterAttributes'] = {}
                        output[name]['pvInverterAttributes']['nameplateRealPowerW'] = int(attributes.pvInverterAttributes.nameplateRealPowerW)
                    if attributes.HasField("meterAttributes"):
                        output[name]['meterAttributes'] = {}
                        output[name]['meterAttributes']['meterLocation'] = []
                        for location in attributes.meterAttributes.meterLocation:
                            output[name]['meterAttributes']['meterLocation'].append(int(location))
                except:
                    log.debug("Error: Unable to extract deviceAttributes - skipping.")

            # Capture all vital data points
            for y in pb.devices[x].vitals:
                vital_name = str(y.name)
                vital_value = None
                if (y.HasField('intValue')):
                    vital_value = y.intValue
                if(y.HasField('boolValue')):
                    vital_value = y.boolValue
                if(y.HasField('stringValue')):
                    vital_value = y.stringValue
                if(y.HasField('floatValue')):
                    vital_value = y.floatValue
                # Record in output dictionary
                output[name][vital_name] = vital_value
            # Capture all alerts into an array
            alerts = pb.devices[x].alerts
            if len(alerts) > 0:
                output[name]['alerts'] = []
                for a in alerts:
                    output[name]['alerts'].append(a)
            # Next device
            x = x + 1
        # Return result
        if (jsonformat):
            json_out = json.dumps(output, indent=4, sort_keys=True)
            return json_out
        else:
            return output

    def strings(self, jsonformat=False, verbose=False):
        """
        Solar Strings Data (current, voltage, power, state, connected)

        Args:
           jsonformat = If True, return JSON format otherwise return Python Dictionary
           verbose    = If True, return all String data details otherwise basics
        """
        result = {}
        devicemap = ['','1','2','3','4','5','6','7','8']
        deviceidx = 0
        v = self.vitals(jsonformat=False)
        if(not v):
            return None
        for device in v:
            if device.split('--')[0] == 'PVAC':
                # Check for PVS data
                look = "PVS" + str(device)[4:]
                if look in v:
                    # Inject the PVS string data into the dictionary
                    for ee in v[look]:
                        if 'String' in ee:
                            v[device][ee] = v[look][ee]
                if verbose:
                    result[device] = {}
                    result[device]['PVAC_Pout'] = v[device]['PVAC_Pout']
                    for e in v[device]:
                        if 'PVAC_PVCurrent' in e or 'PVAC_PVMeasuredPower' in e or \
                            'PVAC_PVMeasuredVoltage' in e or 'PVAC_PvState' in e or \
                            'PVS_String' in e:
                            result[device][e] = v[device][e]
                else:   # simplified results
                    for e in v[device]:
                        if 'PVAC_PVCurrent' in e or 'PVAC_PVMeasuredPower' in e or \
                            'PVAC_PVMeasuredVoltage' in e or 'PVAC_PvState' in e or \
                            'PVS_String' in e:
                                name = e[-1] + devicemap[deviceidx]
                                if 'Current' in e:
                                    idxname = 'Current'
                                if 'Power' in e:
                                    idxname = 'Power'
                                if 'Voltage' in e:
                                    idxname = 'Voltage'
                                if 'State' in e:
                                    idxname = 'State'
                                if 'Connected' in e:
                                    idxname = 'Connected'
                                    name = e[10] + devicemap[deviceidx]
                                if name not in result:
                                    result[name] = {}
                                result[name][idxname] = v[device][e]
                        # if
                    # for   
                    deviceidx += 1
                # else
        if (jsonformat):
            json_out = json.dumps(result, indent=4, sort_keys=True)
            return json_out
        else:
            return result

    # Pull Power Data
    def site(self, verbose=False):
        """ Grid Usage """
        return self._fetchpower('site',verbose)
        
    def solar(self, verbose=False):
        """" Solar Power Generation """
        return self._fetchpower('solar',verbose)

    def battery(self, verbose=False):
        """ Battery Power Flow """
        return self._fetchpower('battery',verbose)

    def load(self, verbose=False):
        """ Home Power Usage """
        return self._fetchpower('load',verbose)

    # Helpful Power Aliases
    def grid(self, verbose=False):
        """ Grid Power Usage """
        return self.site(verbose)

    def home(self, verbose=False):
        """ Home Power Usage """
        return self.load(verbose)

    # Shortcut Functions 
    def site_name(self):
        """ System Site Name """
        payload = self.poll('/api/site_info/site_name', jsonformat=True)
        try:
            site_name = payload['site_name']
        except:
            log.debug('ERROR unable to parse payload for site_name: %r' % payload)
        return site_name

    def status(self, param=None, jsonformat=False):
        """ 
        Return Systems Status

        Args: 
          params = only respond with this param data

          Available param:
            din = payload['din']
            start_time = payload['start_time-time']
            up_time_seconds = payload['up_time_seconds']
            is_new = payload['is_new']
            version = payload['version']
            githash = payload['git_hash']
            commission_count = payload['commission_count']
            device_type = payload['device_type']
            sync_type = payload['sync_type']
            leader = payload['leader']
            followers = payload['followers']
            cellular_disabled = payload['cellular_disabled']
        """
        payload = self.poll('/api/status', jsonformat=True)
        if param is None:
            if jsonformat:
                return json.dumps(payload, indent=4, sort_keys=True)
            else:
                return payload 
        else:
            if param in payload:
                return payload[param]
            else:
                log.debug('ERROR unable to find %s in payload: %r' % (param, payload))
                return None

    def version(self):
        """ Firmware Version """
        return self.status('version')

    def uptime(self):
        """ System Uptime """
        return self.status('up_time_seconds')

    def din(self):
        """ System DIN """
        return self.status('din')

    def temps(self, jsonformat=False):
        """ Temperatures of Powerwalls  """
        temps = {}
        devices = self.vitals()
        for device in devices:
            if device.startswith('TETHC'):
                try:
                    temps[device] = devices[device]['THC_AmbientTemp']
                except:
                    temps[device] = None
        if (jsonformat):
            json_out = json.dumps(temps, indent=4, sort_keys=True)
            return json_out
        else:
            return temps
