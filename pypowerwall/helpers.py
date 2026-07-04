# pyPowerWall Module - Shared Helpers
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Shared helper functions used by the cloud, fleetapi and tedapi backends.
 Consolidated here so the copies in each backend cannot drift apart; the
 backend modules re-export these names for backward compatibility.

 Functions
    lookup(data, keylist)                       # None-safe nested dictionary lookup
    not_implemented_mock_data_factory(log, mode) # Build a per-backend mock-data decorator
"""
import functools


def lookup(data, keylist):
    """
    Lookup a value in a nested dictionary or return None if not found.
        data - nested dictionary
        keylist - list of keys to traverse

    None-safe: if any intermediate value is missing or not a dictionary
    (gateway payloads vary by firmware and hardware), returns None instead
    of raising.
    """
    for key in keylist:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data


def not_implemented_mock_data_factory(logger, mode, warned_once):
    """
    Build the @not_implemented_mock_data decorator for a backend.

    Args:
        logger      - the backend's logger to emit the warning on
        mode        - backend mode name used in the log message (e.g. 'cloud')
        warned_once - per-backend dict tracking which functions already warned

    The returned decorator logs a warning the first time each decorated
    handler is called (then logs at debug) to flag that the API is serving
    mock data in that mode.
    """
    def not_implemented_mock_data(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not warned_once.get(func.__name__):
                logger.warning(f"This API [{func.__name__}] is using mock data in {mode} mode. This message will be "
                               "printed only once at the warning level.")
                warned_once[func.__name__] = 1
            else:
                logger.debug(f"This API [{func.__name__}] is using mock data in {mode} mode.")
            return func(*args, **kwargs)

        return wrapper

    return not_implemented_mock_data
