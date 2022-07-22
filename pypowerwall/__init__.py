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
    Powerwall(host, password, email, timezone, pwcacheexpire, timeout)

 Functions 
    poll(api, json, force)    # Return data from Powerwall api (dict if json=True, bypass cache force=True)
    level()                   # Return battery power level percentage
    power()                   # Return power data returned as dictionary
    site(verbose)             # Return site sensor data (W or raw JSON if verbose=True)
    solar(verbose):           # Return solar sensor data (W or raw JSON if verbose=True)
    battery(verbose):         # Return battery sensor data (W or raw JSON if verbose=True)
    load(verbose)             # Return load sensor data (W or raw JSON if verbose=True)
    grid()                    # Alias for site()
    home()                    # Alias for load()
    vitals(json)              # Return Powerwall device vitals (dict or json if True)
    strings(json, verbose)    # Return solar panel string data
    din()                     # Return DIN
    uptime()                  # Return uptime - string hms format
    version()                 # Return system version
    status(param)             # Return status (JSON) or individual param
    site_name()               # Return site name
    temps()                   # Return Powerwall Temperatures
    alerts()                  # Return array of Alerts from devices
    system_status(json)       # Returns the system status
    battery_blocks(json)      # Returns battery specific information merged from system_status() and vitals()
    grid_status(type)         # Return the power grid status, type ="string" (default), "json", or "numeric"
                              #     - "string": "UP", "DOWN", "SYNCING"
                              #     - "numeric": -1 (Syncing), 0 (DOWN), 1 (UP)
    is_connected()            # Returns True if able to connect and login to Powerwall

 Parameters
    host                    # (required) hostname or IP of the Tesla gateway
    password                # (required) password for logging into the gateway
    email                   # (required) email used for logging into the gateway
    timezone                # (required) desired timezone
    pwcacheexpire = 5       # Set API cache timeout in seconds
    timeout = 10            # Timeout for HTTPS calls in seconds
"""
import json, time
import requests
import urllib3
urllib3.disable_warnings() # Disable SSL warnings
import logging
import sys
from . import tesla_pb2           # Protobuf definition for vitals

version_tuple = (0, 5, 1)
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

class LoginError(Exception):
    pass

class ConnectionError(Exception):
    pass

class Powerwall(object):
    def __init__(self, host="", password="", email="nobody@nowhere.com", timezone="America/Los_Angeles", pwcacheexpire=5, timeout=10):
        """
        Represents a Tesla Energy Gateway Powerwall device.

        Args:
            host        = Hostname or IP address of Powerwall (e.g. 10.0.1.99)
            password    = Customer password set up on Powerwall gateway
            email       = Customer email 
            timezone    = Timezone for location of Powerwall 
                (see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) 
            pwcacheexpire = Seconds to expire cached entries
            timeout      = Seconds for the timeout on http requests

        """

        # Attributes
        self.cachefile = ".powerwall"  # Stores auth session information
        self.host = host
        self.password = password
        self.email = email
        self.timezone = timezone
        self.timeout = timeout                  # 10s timeout for http calls
        self.auth = {}                          # caches authentication cookies
        self.pwcachetime = {}                   # holds the cached data timestamps for api
        self.pwcache = {}                       # holds the cached data for api
        self.pwcacheexpire = pwcacheexpire      # seconds to expire cache 

        # Load cached auth session
        try:
            f = open(self.cachefile, "r")
            self.auth = json.load(f)
            log.debug('loaded auth from cache file %s' % self.cachefile)
        except:
            log.debug('no auth cache file')
            pass

        # Create new session
        if self.auth == {}:
            self._get_session()

    def _get_session(self):
        # Login and create a new session
        url = "https://%s/api/login/Basic" % self.host
        pload = {"username":"customer","password":self.password,
            "email":self.email,"clientInfo":{"timezone":self.timezone}}
        try:
            r = requests.post(url,data = pload, verify=False, timeout=self.timeout)
            log.debug('login - %s' % r.text)
        except:
            err = "Unable to connect to Powerwall at https://%s" % self.host
            log.debug(err)
            raise ConnectionError(err)

        # Save Auth cookies
        try:
            self.auth = {'AuthCookie': r.cookies['AuthCookie'], 'UserRecord': r.cookies['UserRecord']}
            try:
                f = open(self.cachefile, "w") 
                json.dump(self.auth,f)
                f.close()
            except:
                log.debug('unable to cache auth session - continuing')
        except:
            log.debug('login failed')
            raise LoginError("Invalid Powerwall Login")

    def _close_session(self):
        # Log out
        url = "https://%s/api/logout" % self.host
        g = requests.get(url, cookies=self.auth, verify=False, timeout=self.timeout)
        self.auth = {}

    def is_connected(self):
        """
        Attempt connection with Tesla Energy Gateway
        
        Return True if able to successfully connect and login to Powerwall
        """
        try:
            if self.status() is None:
                return False
            return True
        except:
            False

    def poll(self, api='/api/site_info/site_name', jsonformat=False, raw=False, recursive=False, force=False):
        """
        Query Tesla Energy Gateway Powerwall for API Response
        
        Args:
            api         = URI 
            jsonformat  = If True, convert JSON response to Python Dictionary, otherwise return text
            raw         = If True, send raw data back (useful for binary responses)
            recursive   = If True, this is a recursive call and do not allow additional recursive calls
            force       = If True, bypass the cache and make the API call to the gateway
        """
        # Query powerwall and return payload as string
        
        # First check to see if in cache
        fetch = True
        if(api in self.pwcache and api in self.pwcachetime):
            # is it expired?
            if(time.time() - self.pwcachetime[api] < self.pwcacheexpire):
                payload = self.pwcache[api]
                # We do the override here to ensure that we cache the force entry
                if force:
                    fetch = True
                else:
                    fetch = False

        if(fetch):
            if(api == '/api/devices/vitals'):
                # Always want the raw output from the vitals call; protobuf binary payload
                raw = True
        
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
            site_name = None
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

    def alerts(self, jsonformat=False, alertsonly=True):
        """ 
        Return Array of Alerts from all Devices 
        
        Args: 
          alertonly  = If True, return only alerts without device name
          jsonformat = If True, return JSON format otherwise return Python Dictionary
        """
        alerts = []
        devices = self.vitals()
        for device in devices:
            if 'alerts' in devices[device]:
                for i in devices[device]['alerts']:
                    if(alertsonly):
                        alerts.append(i)
                    else:
                        item = {}
                        item[device] = i
                        alerts.append(item)
        if (jsonformat):
            json_out = json.dumps(alerts, indent=4, sort_keys=True)
            return json_out
        else:
            return alerts

    def get_reserve(self, scale=True):
        """
        Get Battery Reserve Percentage  
        
        Args:
            scale    = If True (default) use Tesla's 5% reserve calculation
            Tesla App reserves 5% of battery = ( (batterylevel / 0.95) - (5 / 0.95) )
        """
        data = self.poll('/api/operation')
        if data is None:
            return None
        data = json.loads(data)
        percent = float(data['backup_reserve_percent'])
        if scale:
            # Get percentage based on Tesla App scale
            percent = float((percent / 0.95) - (5 / 0.95))
        return percent

    def grid_status(self, type="string"):
        """
        Get the status of the grid  
        
        Args:
            type == "string" (default) returns: "UP", "DOWN", "SYNCING"
            type == "json" return raw JSON
            type == "numeric" return -1 (Syncing), 0 (DOWN), 1 (UP)
        """
        if type not in ['json', 'string', 'numeric']:
            raise ValueError("Invalid value for parameter 'type': " + str(type))
        
        payload = self.poll('/api/system_status/grid_status', jsonformat=True)

        if type == "json":
            return json.dumps(payload, indent=4, sort_keys=True)

        map = {'SystemGridConnected': {'string': 'UP', 'numeric': 1}, 
               'SystemIslandedActive': {'string': 'DOWN', 'numeric': 0}, 
               'SystemTransitionToGrid': {'string': 'SYNCING', 'numeric': -1},
               'SystemTransitionToIsland': {'string': 'SYNCING', 'numeric': -1},
               'SystemIslandedReady': {'string': 'SYNCING', 'numeric': -1}}
        try:
            grid_status = payload['grid_status']
            return map[grid_status][type]
        except:
            # The payload from powerwall was not valid
            log.debug("ERROR Invalid return value received from gateway: " + str(payload.grid_status))
            return None

    def system_status(self, jsonformat=False):
        """
        Get the full system status and basically do a straight passthrough return

        Some data points of note are
            nominal_full_pack_energy
            nominal_energy_remaining
            system_island_state - returns same value as grid_status
            available_blocks - number of batteries
            battery_blocks - array of batteries
                PackageSerialNumber
                disabled_reasons
                nominal_energy_remaining
                nominal_full_pack_energy
                v_out - voltage out
                f_out - frequency out
                energy_charged
                energy_discharged
                backup_ready
            grid_faults - array of faults

        Args:
            jsonformat = If True, return JSON format otherwise return Python Dictionary
        """
        payload = self.poll('/api/system_status', jsonformat=True)
        if payload is None:
            return None

        if jsonformat:
            return json.dumps(payload, indent=4, sort_keys=True)
        else:
            return payload

    def battery_blocks(self, jsonformat=False):
        """
        Get detailed information about each battery. If you want to get aggregate power information 
        on all the batteries, use battery() 

        This function actually makes two API calls. The primary data is harvested from the 
        battery_blocks section in /api/system_status but the temperature data is only 
        available via /api/devices/vitals

        Some data points of note are
            battery_blocks - array of batteries
                disabled_reasons
                nominal_energy_remaining
                nominal_full_pack_energy
                v_out - voltage out
                f_out - frequency out
                energy_charged
                energy_discharged
                backup_ready
            grid_faults - array of faults

        Args:
            jsonformat = If True, return JSON format otherwise return Python Dictionary
        """
        system_status = self.system_status()
        if system_status is None:
            return None

        devices = self.vitals()
        if devices is None:
            return None

        result = {}
        # copy the info from system_status into result
        # but change the key to the battery serial number
        for i in range(system_status['available_blocks']):
            bat = system_status['battery_blocks'][i]
            sn = bat['PackageSerialNumber']
            bat_res = {}
            for j in bat:
                if j != 'PackageSerialNumber':
                    bat_res[j] = bat[j]
            result[sn] = bat_res

        # now merge in the "interesting" data from vitals
        # Right now we're just pulling in the temp and state from the TETHC block
        # There is also info in TPOD and TINV that could be associated with the battery.
        for device in devices:
            if device.startswith("TETHC--"):
                sn = device.split("--")[2]
                bat_res = {}
                bat_res['THC_State'] = devices[device]['THC_State']
                bat_res['temperature'] = devices[device]['THC_AmbientTemp']
                result[sn].update(bat_res)  

        if jsonformat:
            return json.dumps(result, indent=4, sort_keys=True)
        else:
            return result