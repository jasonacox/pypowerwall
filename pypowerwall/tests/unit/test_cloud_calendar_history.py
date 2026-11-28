"""PyPowerwallCloud.get_calendar_history(): public Cloud-mode site history."""
import datetime
import threading
from unittest.mock import MagicMock

import pytest

from pypowerwall.cloud.pypowerwall_cloud import PyPowerwallCloud


@pytest.fixture(name="cloud")
def fixture_cloud(tmp_path):
    cloud = PyPowerwallCloud(email='test@example.com', authpath=str(tmp_path))
    cloud.tesla = MagicMock()
    cloud.site = MagicMock()
    return cloud


def test_returns_inner_response_and_maps_fleetapi_arguments(cloud):
    cloud.site.api.return_value = {"response": {"time_series": [{"grid_energy_imported": 5}]}}
    start = datetime.datetime(2024, 5, 1, tzinfo=datetime.timezone.utc)
    result = cloud.get_calendar_history(kind="energy", duration="lifetime",
                                        time_zone="America/Los_Angeles", start=start)
    assert result == {"time_series": [{"grid_energy_imported": 5}]}
    cloud.site.api.assert_called_once_with(
        "CALENDAR_HISTORY_DATA", kind="energy", period="lifetime",
        time_zone="America/Los_Angeles", start_date="2024-05-01T00:00:00+00:00")


def test_live_request_not_cached(cloud):
    cloud.site.api.side_effect = [{"response": {"n": 1}}, {"response": {"n": 2}}]
    assert cloud.get_calendar_history(kind="energy", duration="day") == {"n": 1}
    assert cloud.get_calendar_history(kind="power", duration="day") == {"n": 2}
    assert cloud.pwcache.get("CALENDAR_HISTORY_DATA") is None


def test_failure_returns_none(cloud):
    cloud.site.api.side_effect = RuntimeError("boom")
    assert cloud.get_calendar_history(kind="energy", duration="lifetime") is None


def test_not_connected_returns_none(cloud):
    cloud.tesla = None
    assert cloud.get_calendar_history(kind="energy") is None
    cloud.site.api.assert_not_called()


def test_lock_timeout_returns_none_not_other_query(cloud):
    cloud.timeout = 0.01
    lock = threading.Lock()
    cloud._api_locks["CALENDAR_HISTORY_DATA"] = lock
    lock.acquire()
    try:
        assert cloud.get_calendar_history(kind="energy") is None
    finally:
        lock.release()
    cloud.site.api.assert_not_called()
