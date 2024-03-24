import functools
import logging

log = logging.getLogger('pypowerwall.cloud.pypowerwall_cloud')
WARNED_ONCE = {}


def not_implemented_mock_data(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not WARNED_ONCE.get(func.__name__):
            log.warning(f"This API [{func.__name__}] is using mock data in cloud mode. This message will be "
                        "printed only once at the warning level.")
            WARNED_ONCE[func.__name__] = 1
        else:
            log.debug(f"This API [{func.__name__}] is using mock data in cloud mode.")
        return func(*args, **kwargs)

    return wrapper
