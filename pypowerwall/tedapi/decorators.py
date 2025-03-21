import functools
import inspect
import logging
import time

log = logging.getLogger('pypowerwall.tedapi.pypowerwall_tedapi')
WARNED_ONCE = {}


def not_implemented_mock_data(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not WARNED_ONCE.get(func.__name__):
            log.warning(f"This API [{func.__name__}] is using mock data in tedapi mode. This message will be "
                        "printed only once at the warning level.")
            WARNED_ONCE[func.__name__] = 1
        else:
            log.debug(f"This API [{func.__name__}] is using mock data in tedapi mode.")
        return func(*args, **kwargs)

    return wrapper

# Connection Decorator
# Checks to see whether a connection exists, and if not, attempts to connect
def uses_connection_required(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get status")
                return None
        return func(self, *args, **kwargs)
    return wrapper

# Cache Decorator
# Checks to see whether a cached result exists for the function, and if so, returns it. If not, it calls the function and caches the result.
def uses_cache(cache_key):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # We probably can't guarantee that "force" will be the first argument for the function, so let's find it
            sig = inspect.signature(func)
            namedArgs = sig.bind(self, *args, **kwargs).arguments
            force = False
            if 'force' in namedArgs:
                force = namedArgs['force']
            
            # Check Cache
            if not force and cache_key in self.pwcachetime:
                if time.time() - self.pwcachetime[cache_key] < self.pwcacheexpire:
                    log.debug(f"Using Cached {cache_key}")
                    return self.pwcache[cache_key]
                
            # Check Rate Limit
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            result = func(self, *args, **kwargs)

            # Update Cache
            if result is not None:
                self.pwcachetime[cache_key] = time.time()
                self.pwcache[cache_key] = result
            return result
        return wrapper
    return decorator