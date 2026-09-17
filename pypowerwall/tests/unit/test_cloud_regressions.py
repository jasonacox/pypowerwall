"""Regression tests for cloud backend bugs and Tesla tariff/site recovery:
- set_grid_charging()/set_grid_export() returned the (response, cached) tuple
  from _site_api() instead of the response
- post_api_operation() raised KeyError on partial payloads and did not
  normalize a False reserve to 0
- Tesla tariff read/write cache invalidation and stale-site recovery behavior
"""
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.cloud.pypowerwall_cloud import PyPowerwallCloud


@pytest.fixture(name="cloud")
def fixture_cloud(tmp_path):
    # authpath pointed at tmp so no site/auth files are picked up
    return PyPowerwallCloud(email='test@example.com', authpath=str(tmp_path))


class FakeHttpError(Exception):
    """Minimal HTTP-style exception exposing response.status_code."""

    def __init__(self, status_code):
        super().__init__(f"{status_code} Client Error")
        self.response = MagicMock(status_code=status_code)


class FakeSite(dict):
    """Dict-like Tesla site with a controllable api() result."""

    def __init__(self, site_id, site_name='Test Site', gateway_id=None,
                 api_result=None, api_error=None):
        super().__init__(energy_site_id=site_id, site_name=site_name)
        if gateway_id is not None:
            self['gateway_id'] = gateway_id
        self.api_result = api_result
        self.api_error = api_error
        self.api_calls = []

    def api(self, name, **kwargs):
        self.api_calls.append((name, kwargs))
        if self.api_error is not None:
            raise self.api_error
        return self.api_result


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

    def test_reserve_zero_only_not_rejected_as_empty(self, cloud):
        # Regression (PW3 mode-persistence race): {'backup_reserve_percent': 0}
        # alone used to fail the truthiness-based "missing parameters" guard.
        battery = self._make_battery()
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = [battery]

        resp = cloud.post_api_operation(payload={'backup_reserve_percent': 0})
        assert 'error' not in resp
        assert resp['set_backup_reserve_percent']['backup_reserve_percent'] == 0
        battery.set_backup_reserve_percent.assert_called_once_with(0)
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


class TestTeslaTariffApi:

    def test_get_api_tariff_rate_unwraps_response(self, cloud):
        tariff = {'code': 'TEST', 'energy_charges': {'AllYear': {'OFF_PEAK': 0.1}}}
        with patch.object(cloud, '_site_api', return_value=({'response': tariff}, False)) as site_api:
            result = cloud.get_api_tariff_rate(force=True)

        assert result == tariff
        site_api.assert_called_once_with('SITE_TARIFF', ttl=cloud.pwcacheexpire, force=True)

    def test_get_api_tariff_rate_none_passthrough(self, cloud):
        with patch.object(cloud, '_site_api', return_value=(None, False)):
            assert cloud.get_api_tariff_rate() is None

    def test_tou_post_invalidates_tariff_cache_through_base_map(self, cloud):
        response = {'response': '{"Message":"Updated","Code":201}\n'}
        site = FakeSite(123, api_result=response)
        cloud.site = site
        cloud.siteid = 123
        cloud.tesla = MagicMock()
        cloud.pwcache['SITE_TARIFF'] = {'response': {'code': 'OLD'}}
        cloud.pwcachetime['SITE_TARIFF'] = 1.0
        payload = {'tou_settings': {'optimization_strategy': 'economics'}}

        result = cloud.post('/api/tesla/time_of_use_settings', payload, None)

        assert result == response
        assert site.api_calls == [('TIME_OF_USE_SETTINGS', payload)]
        assert cloud.pwcache['SITE_TARIFF'] is None

    def test_set_time_of_use_settings_rejects_invalid_payload(self, cloud):
        cloud.site = FakeSite(123)
        assert cloud.set_time_of_use_settings(None) is None
        assert cloud.site.api_calls == []

    def test_set_time_of_use_settings_requires_selected_site(self, cloud):
        assert cloud.set_time_of_use_settings({'tou_settings': {}}) is None


class TestStaleSiteRecovery:

    def _configure_tesla(self, cloud, sites):
        cloud.tesla = MagicMock()
        cloud.tesla.battery_list.return_value = sites
        cloud.tesla.solar_list.return_value = []

    def test_http_status_from_response(self, cloud):
        assert cloud._http_status_from_error(FakeHttpError(404)) == 404

    def test_http_status_fallback_from_exception_text(self, cloud):
        assert cloud._http_status_from_error(RuntimeError('404 Client Error: not_found')) == 404

    def test_stale_site_404_switches_site_persists_clears_cache_and_retries(self, cloud):
        old_site = FakeSite(111, site_name='Home', gateway_id='GW1',
                            api_error=FakeHttpError(404))
        new_response = {'response': {'code': 'NEW'}}
        new_site = FakeSite(222, site_name='Home', gateway_id='GW1', api_result=new_response)
        cloud.site = old_site
        cloud.siteid = 111
        cloud.siteindex = 0
        cloud.pwcache['SITE_TARIFF'] = {'response': {'code': 'OLD'}}
        cloud.pwcachetime['SITE_TARIFF'] = 1.0
        self._configure_tesla(cloud, [new_site])

        result = cloud._call_site_api('SITE_TARIFF')

        assert result == new_response
        assert cloud.site is new_site
        assert cloud.siteid == 222
        assert cloud.siteindex == 0
        assert cloud.pwcache == {}
        assert cloud.pwcachetime == {}
        with open(cloud.sitefile, encoding='utf-8') as site_file:
            assert site_file.read() == '222'
        assert old_site.api_calls == [('SITE_TARIFF', {})]
        assert new_site.api_calls == [('SITE_TARIFF', {})]

    def test_recovery_prefers_gateway_match_over_first_site(self, cloud):
        old_site = FakeSite(111, site_name='Home', gateway_id='GW-HOME')
        wrong_site = FakeSite(222, site_name='Cabin', gateway_id='GW-CABIN')
        replacement = FakeSite(333, site_name='Home Renamed', gateway_id='GW-HOME')
        cloud.site = old_site
        cloud.siteid = 111
        self._configure_tesla(cloud, [wrong_site, replacement])

        assert cloud._recover_stale_site() is True
        assert cloud.site is replacement
        assert cloud.siteid == 333
        assert cloud.siteindex == 1

    def test_recovery_uses_site_name_when_gateway_id_missing(self, cloud):
        old_site = FakeSite(111, site_name='Home')
        wrong_site = FakeSite(222, site_name='Cabin')
        replacement = FakeSite(333, site_name='Home')
        cloud.site = old_site
        cloud.siteid = 111
        self._configure_tesla(cloud, [wrong_site, replacement])

        assert cloud._recover_stale_site() is True
        assert cloud.site is replacement
        assert cloud.siteindex == 1

    def test_404_does_not_switch_when_current_site_still_exists(self, cloud):
        current_site = FakeSite(111, api_error=FakeHttpError(404))
        cloud.site = current_site
        cloud.siteid = 111
        self._configure_tesla(cloud, [current_site])

        with pytest.raises(FakeHttpError):
            cloud._call_site_api('SITE_TARIFF')

        assert cloud.site is current_site
        assert cloud.siteid == 111
        assert current_site.api_calls == [('SITE_TARIFF', {})]

    def test_recovery_cooldown_avoids_repeated_product_list_calls(self, cloud):
        current_site = FakeSite(111)
        cloud.site = current_site
        cloud.siteid = 111
        self._configure_tesla(cloud, [current_site])

        assert cloud._recover_stale_site() is False
        assert cloud._recover_stale_site() is False

        cloud.tesla.battery_list.assert_called_once()
        cloud.tesla.solar_list.assert_called_once()

    def test_recovery_lock_is_non_blocking(self, cloud):
        cloud.site = FakeSite(111)
        cloud.siteid = 111
        self._configure_tesla(cloud, [FakeSite(222)])
        assert cloud._site_recovery_lock.acquire(blocking=False)
        try:
            assert cloud._recover_stale_site() is False
        finally:
            cloud._site_recovery_lock.release()

        cloud.tesla.battery_list.assert_not_called()
        cloud.tesla.solar_list.assert_not_called()

    def test_non_404_does_not_attempt_site_recovery(self, cloud):
        current_site = FakeSite(111, api_error=FakeHttpError(403))
        cloud.site = current_site
        cloud.siteid = 111
        self._configure_tesla(cloud, [FakeSite(222)])

        with pytest.raises(FakeHttpError):
            cloud._call_site_api('SITE_TARIFF')

        cloud.tesla.battery_list.assert_not_called()
        cloud.tesla.solar_list.assert_not_called()


class TestGetTimeRemaining:
    """get_time_remaining() must not crash when the cloud returns
    {'response': None} - `'key' in None` raises TypeError."""

    def test_null_response_body(self, cloud):
        with patch.object(cloud, '_site_api', return_value=({'response': None}, False)):
            assert cloud.get_time_remaining() == 0.0

    def test_none_response(self, cloud):
        with patch.object(cloud, '_site_api', return_value=(None, False)):
            assert cloud.get_time_remaining() is None

    def test_valid_response(self, cloud):
        payload = {'response': {'time_remaining_hours': 7.9}}
        with patch.object(cloud, '_site_api', return_value=(payload, False)):
            assert cloud.get_time_remaining() == 7.9


class TestSimulatedVitalsAlerts:
    """Simulated vitals used to inject an empty-string alert when
    island_status was unrecognized, so Powerwall.alerts() returned ""."""

    def _vitals(self, cloud, island_status, grid_status=None):
        config = {'response': {'id': 'PN--SN', 'version': '23.44.0'}}
        power = {'response': {'island_status': island_status,
                              'grid_status': grid_status}}
        with patch.object(cloud, 'get_site_config', return_value=config), \
             patch.object(cloud, 'get_site_power', return_value=power):
            return cloud.get_vitals()

    def test_unknown_island_status_no_empty_alert(self, cloud):
        vitals = self._vitals(cloud, island_status='mystery_state')
        assert vitals['STSTSM--PN--SN']['alerts'] == []

    def test_on_grid_alert_present(self, cloud):
        vitals = self._vitals(cloud, island_status='on_grid')
        assert vitals['STSTSM--PN--SN']['alerts'] == ['SystemConnectedToGrid']

    def test_alerts_facade_no_empty_string(self, cloud):
        """Powerwall.alerts() with these vitals must not contain ""."""
        from unittest.mock import MagicMock as MM
        import pypowerwall
        vitals = self._vitals(cloud, island_status='mystery_state')
        # Patch by name so a cached .pypowerwall.auth in CWD can't reach the network
        with patch('pypowerwall.PyPowerwallCloud'):
            pw = pypowerwall.Powerwall(host='', password='', email='test@example.com',
                                       cloudmode=True)
        pw.client = MM()
        pw.client.vitals.return_value = vitals
        pw.client.poll.return_value = None  # no grid_status augmentation
        alerts = pw.alerts()
        assert '' not in alerts
