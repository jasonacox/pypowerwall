import logging

from pypowerwall.helpers import not_implemented_mock_data_factory

log = logging.getLogger('pypowerwall.fleetapi.pypowerwall_fleetapi')
WARNED_ONCE = {}

# Thin shim - the shared implementation lives in pypowerwall.helpers;
# this binds the fleetapi logger and mode string for the log messages
not_implemented_mock_data = not_implemented_mock_data_factory(log, 'fleetapi', WARNED_ONCE)
