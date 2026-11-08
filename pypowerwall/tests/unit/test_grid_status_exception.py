"""Regression test: grid_status()'s exception handler crashed on its own log line.

grid_status() keeps a deprecated `type` keyword argument for backward
compatibility, which shadows the builtin type() inside the method. Its
`except` block logged `type(e).__name__`, so any exception from the backend
(e.g. PyPowerwallCloudTeslaNotConnected after a failed reconnect) was replaced
by "TypeError: 'NoneType' object is not callable" ('str' when type= was
passed) and the error log line was never written.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall import Powerwall


class GatewayGone(Exception):
    pass


@pytest.fixture(name="pw")
def fixture_powerwall():
    with patch.object(Powerwall, 'connect', return_value=True):
        pw = Powerwall(host='', password='', email='test@example.com', cloudmode=True)
    pw.client = MagicMock()
    pw.client.poll.side_effect = GatewayGone('gateway gone')
    return pw


@pytest.mark.parametrize('kwargs', [{}, {'output_type': 'numeric'}, {'type': 'numeric'}])
def test_grid_status_reraises_original_exception(pw, kwargs, caplog):
    with caplog.at_level(logging.ERROR, logger='pypowerwall'):
        with pytest.raises(GatewayGone):
            pw.grid_status(**kwargs)
    assert 'grid_status(): Exception GatewayGone: gateway gone' in caplog.text


def test_grid_status_deprecated_type_still_overrides(pw):
    pw.client.poll.side_effect = None
    pw.client.poll.return_value = {'grid_status': 'SystemGridConnected'}
    assert pw.grid_status(type='numeric') == 1
    assert pw.grid_status() == 'UP'
