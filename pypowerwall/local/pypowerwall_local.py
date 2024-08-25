import json
import logging
import time
from typing import Union, Tuple, Optional, Any

import requests
from requests import Response

import pypowerwall.local.tesla_pb2 as tesla_pb2

from pypowerwall.local.exceptions import LoginError
from pypowerwall.pypowerwall_base import PyPowerwallBase, parse_version
from pypowerwall.tedapi import TEDAPI, GW_IP

log = logging.getLogger(__name__)


class PyPowerwallLocal(PyPowerwallBase):

    def __init__(self, host: str, password: str, email: str, timezone: str, timeout: Union[int, Tuple[int, int]],
                 pwcacheexpire: int, poolmaxsize: int, authmode: str, cachefile: str, gw_pw: str = None):
        super().__init__(email)
        self.host = host
        self.password = password
        self.poolmaxsize = poolmaxsize  # pool max size for http connection re-use
        self.cachefile = cachefile  # Stores auth session information
        self.authmode = authmode  # cookie or token
        self.timeout = timeout
        self.timezone = timezone
        self.session = None
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire cache
        self.pwcache = {}  # holds the cached data for api
        self.pwcooldown = 0  # rate limit cooldown time - pause api calls
        self.vitals_api = True  # vitals api is available for local mode
        self.gw_pw = gw_pw  # Powerwall Gateway password for TEDAPI
        self.tedapi = None  # TEDAPI object
        self.pw3 = False  # Powerwall 3 detected

    def authenticate(self):
        log.debug('Tesla local mode enabled')
        if self.poolmaxsize > 0:
            # Create session object for http connection re-use
            self.session = requests.Session()
            # noinspection PyUnresolvedReferences
            a = requests.adapters.HTTPAdapter(pool_maxsize=self.poolmaxsize)
            self.session.mount('https://', a)
        else:
            # Disable http persistent connections
            self.session = requests
        # Enforce authmode
        if self.authmode not in ['cookie', 'token']:
            log.debug("Invalid value for parameter 'authmode' (%s) switching to default" % str(self.authmode))
            self.authmode = 'cookie'
        # Load cached auth session
        try:
            f = open(self.cachefile, "r")
            self.auth = json.load(f)
            # Check to see if we have a valid cached session for the mode
            if self.authmode == "token":
                if 'Authorization' in self.auth:
                    self.token = self.auth['Authorization'].split(' ')[1]
                else:
                    self.auth = {}
            else:
                if 'AuthCookie' not in self.auth or 'UserRecord' not in self.auth:
                    self.auth = {}
            log.debug('loaded auth from cache file %s (%s authmode)' % (self.cachefile, self.authmode))
        except Exception as exc:
            log.debug(f'no auth cache file: {exc}')
            pass
        # Create new session
        if self.auth == {}:
            self._get_session()
        # Check for TEDAPI capability
        if self.gw_pw and self.host == GW_IP:
            # TEDAPI is requested now test
            self.tedapi = TEDAPI(self.gw_pw)
            if self.tedapi.connect():
                log.debug('TEDAPI connected - Vitals metrics enabled')
                self.pw3 = self.tedapi.pw3
            else:
                log.debug('TEDAPI connection failed - continuing')
                self.tedapi = None

    def _get_session(self):
        # Login and create a new session
        url = "https://%s/api/login/Basic" % self.host
        pload = {"username": "customer", "password": self.password,
                 "email": self.email, "clientInfo": {"timezone": self.timezone}}
        try:
            r = self.session.post(url, data=pload, verify=False, timeout=self.timeout)
            log.debug('login - %s' % r.text)
        except Exception as exc:
            err = f"Unable to connect to Powerwall at https://{self.host}: {exc}"
            log.debug(err)
            raise ConnectionError(err)

        # Save Auth cookies
        try:
            if self.authmode == "token":
                self.token = r.json()['token']
                self.auth = {'Authorization': 'Bearer ' + self.token}
            else:
                self.auth = {'AuthCookie': r.cookies['AuthCookie'], 'UserRecord': r.cookies['UserRecord']}
            try:
                f = open(self.cachefile, "w")
                json.dump(self.auth, f)
                f.close()
            except Exception as exc:
                log.debug(f'unable to cache auth session - continuing: {exc}')
        except Exception as e:
            log.debug(f'login failed: {e}')
            raise LoginError("Invalid Powerwall Login")

    def close_session(self):
        url = "https://%s/api/logout" % self.host
        if self.authmode == "token":
            self.session.get(url, headers=self.auth, verify=False, timeout=self.timeout)
        else:
            self.session.get(url, cookies=self.auth, verify=False, timeout=self.timeout)

        self.auth = {}

    def poll(self, api: str, force: bool = False,
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:

        # Query powerwall and return payload
        raw = False
        payload = None
        # Check cache
        if self.pwcache.get(api) is not None and self.pwcachetime.get(api) is not None:
            # is it expired?
            if time.perf_counter() - self.pwcachetime[api] < self.pwcacheexpire:
                payload = self.pwcache[api]
                log.debug(' -- local: Returning cached %s' % api)
                # We do the override here to ensure that we cache the force entry

        if not payload or force:
            if self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            if api == '/api/devices/vitals':
                if not self.vitals_api:
                    # Vitals API is not available
                    return None
                # Always want the raw stream output from the vitals call; protobuf binary payload
                raw = True

            log.debug(' -- local: Request Powerwall for %s' % api)
            url = "https://%s%s" % (self.host, api)
            try:
                if self.authmode == "token":
                    r: Response = self.session.get(url, headers=self.auth, verify=False, timeout=self.timeout,
                                                   stream=raw)
                else:
                    r: Response = self.session.get(url, cookies=self.auth, verify=False, timeout=self.timeout,
                                                   stream=raw)
            except requests.exceptions.Timeout:
                log.debug('ERROR Timeout waiting for Powerwall API %s' % url)
                return None
            except requests.exceptions.ConnectionError:
                log.debug('ERROR Unable to connect to Powerwall at %s' % url)
                return None
            except Exception as exc:
                log.debug(f'ERROR Unknown error connecting to Powerwall at {url}: {exc}')
                return None
            if r.status_code == 404:
                # API not found or no longer supported
                log.error('404 Powerwall API not found at %s' % url)
                if api == '/api/devices/vitals':
                    # Check Powerwall Firmware version
                    version = self.version(int_value=True)
                    if version >= 23440:
                        # Vitals API not available for Firmware >= 23.44.0
                        self.vitals_api = False
                        log.error('Firmware %s detected - Does not support vitals API - disabling.' % version)
                        # Cache and increase cache TTL by 10 minutes
                self.pwcachetime[api] = time.perf_counter() + 600
                self.pwcache[api] = None
                return None
            elif r.status_code == 429:
                # Rate limited - Switch to cooldown mode for 5 minutes
                self.pwcooldown = time.perf_counter() + 300
                log.error('429 Rate limited by Powerwall API at %s - Activating 5 minute cooldown' % url)
                return None
            elif r.status_code == 401 or r.status_code == 403:
                # Session Expired - Try to get a new one unless we already tried
                log.debug('Session Expired - Trying to get a new one')
                if not recursive:
                    if raw:
                        # Drain the stream before retrying
                        # noinspection PyUnusedLocal
                        payload = r.raw.data
                    self._get_session()
                    return self.poll(api, raw=raw, recursive=True)
                else:
                    if r.status_code == 401:
                        log.error('Unable to establish session with Powerwall at %s - check password' % url)
                    else:
                        log.error('403 Unauthorized by Powerwall API at %s - Endpoint disabled in this firmware or '
                                  'user lacks permission' % url)
                    self.pwcachetime[api] = time.perf_counter() + 600
                    self.pwcache[api] = None
                    return None
            elif 400 <= r.status_code < 500:
                log.error('Unhandled HTTP response code %s at %s' % (r.status_code, url))
                return None
            elif r.status_code == 503:
                log.error('503 Service Unavailable at %s - Activating 5 minute API cooldown' % url)
                self.pwcachetime[api] = time.perf_counter() + 300
                self.pwcache[api] = None
                return None
            elif r.status_code >= 500:
                log.error('Server-side problem at Powerwall API (status code %s) at %s' % (r.status_code, url))
                return None

            if raw:
                payload = r.raw.data
            else:
                payload = r.text
                if not payload:
                    log.debug(f"Empty response from Powerwall at {url}")
                    return None
                elif 'application/json' in r.headers.get('Content-Type'):
                    try:
                        payload = json.loads(payload)
                    except Exception as exc:
                        log.error(f"Unable to parse payload '{payload}' as JSON, even though it was supposed to "
                                  f"be a json: {exc}")
                        return None
                else:
                    log.debug(f"Non-json response from Powerwall at {url}: '{payload}', serving as is.")
            self.pwcache[api] = payload
            self.pwcachetime[api] = time.perf_counter()
            return payload
        else:
            # should be already a dict in cache, so just return it
            return payload

    def post(self, api: str, payload: Optional[dict], din: Optional[str],
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:

        # We probably should not cache responses here
        # Also, we may have to use different HTTP Methods such as POST, PUT, PATCH based on Powerwall API requirements
        # For now we assume it's taking POST calls

        url = "https://%s%s" % (self.host, api)
        try:
            if self.authmode == "token":
                r = self.session.post(url, headers=self.auth, json=payload, verify=False, timeout=self.timeout,
                                      stream=raw)
            else:
                r = self.session.post(url, cookies=self.auth, json=payload, verify=False, timeout=self.timeout,
                                      stream=raw)
        except requests.exceptions.Timeout:
            log.debug('ERROR Timeout waiting for Powerwall API %s' % url)
            return None
        except requests.exceptions.ConnectionError:
            log.debug('ERROR Unable to connect to Powerwall at %s' % url)
            return None
        except Exception as exc:
            log.debug('ERROR Unknown error connecting to Powerwall at %s: %s' % (url, exc))
            return None
        if r.status_code == 404:
            log.debug('404 Powerwall API not found at %s' % url)
            return None
        elif r.status_code == 401:
            # Session Expired - Try to get a new one unless we already tried
            log.debug('Session Expired - Trying to get a new one')
            if not recursive:
                if raw:
                    # Drain the stream before retrying
                    # noinspection PyUnusedLocal
                    response = r.raw.data
                self._get_session()
                return self.post(api=api, payload=payload, din=din, raw=raw, recursive=True)
            else:
                log.error('Unable to establish session with Powerwall at %s - check password' % url)
                return None
        elif r.status_code == 403:
            # Unauthorized
            log.error('403 Unauthorized by Powerwall API at %s - Endpoint disabled in this firmware or '
                      'user lacks permission' % url)
            return None
        elif 400 <= r.status_code < 500:
            log.error('Unhandled HTTP response code %s at %s' % (r.status_code, url))
            return None
        elif r.status_code >= 500:
            log.error('Server-side problem at Powerwall API (status code %s) at %s' % (r.status_code, url))
            return None
        if raw:
            response = r.raw.data
        else:
            response = r.text
            if not response:
                log.debug(f"Empty response from Powerwall at {url}")
                return None
            elif 'application/json' in r.headers.get('Content-Type'):
                try:
                    response = json.loads(response)
                except Exception as exc:
                    log.error(f"Unable to parse response '{response}' as JSON, even though it was supposed to "
                              f"be a json: {exc}")
                    return None
            else:
                log.debug(f"Non-json response from Powerwall at {url}: '{response}', serving as is.")
        # invalidate appropriate read cache on (more or less) successful call to writable API
        super()._invalidate_cache(api)
        return response

    def version(self, int_value=False):
        """ Firmware Version """
        if not int_value:
            return self.status('version')
        # Convert version to integer
        return parse_version(self.status('version'))

    def status(self, param=None) -> Any:
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
        payload = self.poll('/api/status')
        if payload is None:
            return None
        if param is None:
            return payload
        else:
            if param in payload:
                return payload[param]
            else:
                log.debug('ERROR unable to find %s in payload: %r' % (param, payload))
                return None

    def vitals(self) -> Optional[dict]:
        # Check for TEDAPI mode
        if self.tedapi:
            return self.tedapi.vitals()
        # Pull vitals payload - binary protobuf
        stream = self.poll('/api/devices/vitals')
        if not stream:
            return None

        # Protobuf payload processing
        pb = tesla_pb2.DevicesWithVitals()
        pb.ParseFromString(stream)
        num = len(pb.devices)
        log.debug("Found %d devices." % num)

        # Decode Device Details
        x = 0
        output = {}
        while x < num:
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
                except Exception as exc:
                    log.debug(f"Error: Unable to extract primary fields - skipping. Exception: {exc}")
            if device.HasField("deviceAttributes"):
                # Capture all attributes
                try:
                    attributes = device.deviceAttributes
                    if attributes.HasField("teslaEnergyEcuAttributes"):
                        output[name]['teslaEnergyEcuAttributes'] = {}
                        output[name]['teslaEnergyEcuAttributes']['ecuType'] = int(
                            attributes.teslaEnergyEcuAttributes.ecuType)
                    if attributes.HasField("generatorAttributes"):
                        output[name]['generatorAttributes'] = {}
                        output[name]['generatorAttributes']['nameplateRealPowerW'] = int(
                            attributes.generatorAttributes.nameplateRealPowerW)
                        output[name]['generatorAttributes']['nameplateApparentPowerVa'] = int(
                            attributes.generatorAttributes.nameplateApparentPowerVa)
                    if attributes.HasField("pvInverterAttributes"):
                        output[name]['pvInverterAttributes'] = {}
                        output[name]['pvInverterAttributes']['nameplateRealPowerW'] = int(
                            attributes.pvInverterAttributes.nameplateRealPowerW)
                    if attributes.HasField("meterAttributes"):
                        output[name]['meterAttributes'] = {}
                        output[name]['meterAttributes']['meterLocation'] = []
                        for location in attributes.meterAttributes.meterLocation:
                            output[name]['meterAttributes']['meterLocation'].append(int(location))
                except Exception as exc:
                    log.debug(f"Error: Unable to extract deviceAttributes - skipping. Exception: {exc}")

            # Capture all vital data points
            for y in pb.devices[x].vitals:
                vital_name = str(y.name)
                vital_value = None
                if y.HasField('intValue'):
                    vital_value = y.intValue
                if y.HasField('boolValue'):
                    vital_value = y.boolValue
                if y.HasField('stringValue'):
                    vital_value = y.stringValue
                if y.HasField('floatValue'):
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

        return output

    def get_time_remaining(self) -> Optional[float]:
        # Compute based on battery level and load
        d: dict = self.poll('/api/system_status') or {}
        if d.get('nominal_energy_remaining') is not None:
            load = self.fetchpower('load') or 0
            if load > 0:
                return d['nominal_energy_remaining'] / load
        # Default
        return None

    # Functions not available in local mode

    def set_grid_charging(self, mode: str) -> None:
        log.error('Function set_grid_charging not available in local mode')

    def set_grid_export(self, mode: str) -> None:
        log.error('Function set_grid_export not available in local mode')

    def get_grid_charging(self, force=False) -> None:
        log.error('Function get_grid_charging not available in local mode')

    def get_grid_export(self, force=False) -> None:
        log.error('Function get_grid_export not available in local mode')
