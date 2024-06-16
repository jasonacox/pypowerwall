import abc
import logging
from typing import Optional, Any, Union

log = logging.getLogger(__name__)

# Define which write API calls should invalidate which read API cache keys
WRITE_OP_READ_OP_CACHE_MAP = {
    '/api/operation': ['/api/operation', 'SITE_CONFIG']  # local and cloud mode respectively
}


def parse_version(version: str) -> Optional[int]:
    if version is None or not isinstance(version, str):
        return None

    val = version.split(" ")[0]
    val = ''.join(i for i in val if i.isdigit() or i in './\\')
    while len(val.split('.')) < 3:
        val = val + ".0"
    line = [int(x, 10) for x in val.split('.')]
    line.reverse()
    vint = sum(x * (100 ** i) for i, x in enumerate(line))
    return vint


class PyPowerwallBase:

    def __init__(self, email: str):
        super().__init__()
        self.pwcache = {}  # holds the cached data for api
        self.auth = None
        self.token = None  # caches bearer token
        self.email = email

    @abc.abstractmethod
    def authenticate(self):
        raise NotImplementedError

    @abc.abstractmethod
    def close_session(self):
        raise NotImplementedError

    @abc.abstractmethod
    def poll(self, api: str, force: bool = False,
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        raise NotImplementedError

    @abc.abstractmethod
    def post(self, api: str, payload: Optional[dict], din: Optional[str],
             recursive: bool = False, raw: bool = False) -> Optional[Union[dict, list, str, bytes]]:
        raise NotImplementedError

    @abc.abstractmethod
    def vitals(self) -> Optional[dict]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_time_remaining(self) -> Optional[float]:
        raise NotImplementedError

    # pylint: disable=inconsistent-return-statements
    def fetchpower(self, sensor, verbose=False) -> Any:
        if verbose:
            payload: dict = self.poll('/api/meters/aggregates')
            if payload and sensor in payload:
                return payload[sensor]
            else:
                return None
        r = self.power()
        if r and sensor in r:
            return r[sensor]

    def power(self) -> dict:
        site = solar = battery = load = 0.0
        payload: dict = self.poll('/api/meters/aggregates')
        try:
            site = payload['site']['instant_power']
            solar = payload['solar']['instant_power']
            battery = payload['battery']['instant_power']
            load = payload['load']['instant_power']
        except Exception as e:
            log.debug(f"ERROR unable to parse payload '{payload}': {e}")
        return {'site': site, 'solar': solar, 'battery': battery, 'load': load}

    def _invalidate_cache(self, api: str):
        cache_keys = WRITE_OP_READ_OP_CACHE_MAP.get(api, [])
        for cache_key in cache_keys:
            self.pwcache[cache_key] = None
