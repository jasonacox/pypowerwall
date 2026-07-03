"""Regression tests for cloud backend bugs:
- set_grid_charging()/set_grid_export() returned the (response, cached) tuple
  from _site_api() instead of the response
- post_api_operation() raised KeyError on partial payloads and did not
  normalize a False reserve to 0
"""
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.cloud.pypowerwall_cloud import PyPowerwallCloud


@pytest.fixture(name="cloud")
def fixture_cloud(tmp_path):
    # authpath pointed at tmp so no site/auth files are picked up
    return PyPowerwallCloud(email='test@example.com', authpath=str(tmp_path))


class TestSetGridChargingExport:

    def test_set_grid_charging_returns_response_not_tuple(self, cloud):
        api_response = {'code': 201, 'message': 'Updated'}
        with patch.object(cloud, '_site_api', return_value=(api_response, False)):
            result = cloud.set_grid_charging('on')
        assert not isinstance(result, tuple)
        assert result == api_response

    def test_set_grid_export_returns_response_not_tuple(self, cloud):
        api_response = {'code': 201, 'message': 'Updated'}
        with patch.object(cloud, '_site_api', return_value=(api_response, False)):
            result = cloud.set_grid_export('battery_ok')
        assert not isinstance(result, tuple)
        assert result == api_response

    def test_set_grid_charging_failure_is_falsy(self, cloud):
        # _site_api returns (None, False) when disconnected
        with patch.object(cloud, '_site_api', return_value=(None, False)):
            result = cloud.set_grid_charging('on')
        assert not result


class TestPostApiOperation:

    def _make_battery(self):
        battery = MagicMock()
        battery.set_backup_reserve_percent.return_value = 202
        battery.set_operation.return_value = 202
        return battery

    def test_partial_payload_real_mode_only(self, cloud):
        battery = self._make_battery()
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = [battery]

        resp = cloud.post_api_operation(payload={'real_mode': 'backup'})
        # Used to KeyError on 'backup_reserve_percent' (swallowed into {'error': ...})
        assert 'error' not in resp
        assert resp['set_operation']['real_mode'] == 'backup'
        assert resp['set_operation']['result'] == 202
        battery.set_operation.assert_called_once_with('backup')
        battery.set_backup_reserve_percent.assert_not_called()

    def test_partial_payload_reserve_only(self, cloud):
        battery = self._make_battery()
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = [battery]

        resp = cloud.post_api_operation(payload={'backup_reserve_percent': 30})
        assert 'error' not in resp
        assert resp['set_backup_reserve_percent']['backup_reserve_percent'] == 30
        battery.set_backup_reserve_percent.assert_called_once_with(30)
        battery.set_operation.assert_not_called()

    def test_false_reserve_normalized_to_zero(self, cloud):
        battery = self._make_battery()
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = [battery]

        payload = {'backup_reserve_percent': False, 'real_mode': 'self_consumption'}
        resp = cloud.post_api_operation(payload=payload)
        # False must be converted to 0 for the Tesla Cloud API (matches fleetapi).
        # Identity check needed: False == 0 in Python, so assert_called_with(0) is not enough.
        battery.set_backup_reserve_percent.assert_called_once()
        sent = battery.set_backup_reserve_percent.call_args[0][0]
        assert sent == 0 and sent is not False
        # ...but the reported payload value is unchanged
        assert resp['set_backup_reserve_percent']['backup_reserve_percent'] is False
        assert resp['set_operation']['real_mode'] == 'self_consumption'

    def test_full_payload_return_shape_unchanged(self, cloud):
        battery = self._make_battery()
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = [battery]

        resp = cloud.post_api_operation(payload={'backup_reserve_percent': 25,
                                                 'real_mode': 'backup'}, din=None)
        assert set(resp.keys()) == {'set_backup_reserve_percent', 'set_operation'}
        assert resp['set_backup_reserve_percent'] == {
            'backup_reserve_percent': 25, 'din': None, 'result': 202}
        assert resp['set_operation'] == {'real_mode': 'backup', 'din': None, 'result': 202}

    def test_battery_not_found_partial_payload(self, cloud):
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = []

        resp = cloud.post_api_operation(payload={'real_mode': 'backup'})
        assert resp['set_operation']['result'] == 'BatteryNotFound'
        assert resp['set_backup_reserve_percent']['backup_reserve_percent'] is None
