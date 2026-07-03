import logging

from pypowerwall.helpers import not_implemented_mock_data_factory

log = logging.getLogger('pypowerwall.tedapi.pypowerwall_tedapi')
WARNED_ONCE = {}

# Thin shim - the shared implementation lives in pypowerwall.helpers;
# this binds the tedapi logger and mode string for the log messages
not_implemented_mock_data = not_implemented_mock_data_factory(log, 'tedapi', WARNED_ONCE)
