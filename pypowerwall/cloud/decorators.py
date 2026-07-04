import logging

from pypowerwall.helpers import not_implemented_mock_data_factory

log = logging.getLogger('pypowerwall.cloud.pypowerwall_cloud')
WARNED_ONCE = {}

# Thin shim - the shared implementation lives in pypowerwall.helpers;
# this binds the cloud logger and mode string for the log messages
not_implemented_mock_data = not_implemented_mock_data_factory(log, 'cloud', WARNED_ONCE)
