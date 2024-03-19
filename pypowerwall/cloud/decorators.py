import functools
import logging

log = logging.getLogger('pypowerwall.cloud.pypowerwall_cloud')


def not_implemented_mock_data(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        log.warning("This API is using mock data in cloud mode.")
        return func(*args, **kwargs)

    return wrapper
