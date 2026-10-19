"""Regression tests for TEDAPI backend bugs:
- available_blocks read control.batteryBlocks from config instead of status (always 0)
- get_blocks() returning None crashed get_api_system_status()
- PINV_GridState was looked up in the THC entry instead of the PINV entry

Also covers the max power fields (site nameplate capped at the inverter usable
power), inverter_nominal_usable_power and the instantaneous power fields filled
from the msa TEPOD components.
"""
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI


class TestGetApiSystemStatus:

    def _make_backend(self):
        with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI') as mock_tedapi_class:
            backend = PyPowerwallTEDAPI(gw_pwd='password')
        assert backend.tedapi is mock_tedapi_class.return_value
        return backend

    def test_available_blocks_from_status(self):
        backend = self._make_backend()
        backend.tedapi.get_status.return_value = {
            'control': {
                'batteryBlocks': [{'din': 'PW1'}, {'din': 'PW2'}],
                'systemStatus': {
                    'nominalFullPackEnergyWh': 27000,
                    'nominalEnergyRemainingWh': 13500,
                },
                'alerts': {'active': ['SystemConnectedToGrid']},
            },
        }
        backend.tedapi.get_config.return_value = {'vin': 'GW--123'}  # no batteryBlocks here
        backend.tedapi.get_blocks.return_value = {'PW1': {'Type': 'battery'}}

        data = backend.get_api_system_status()
        assert data['available_blocks'] == 2
        assert data['blocks_controlled'] == 2
        assert data['battery_blocks'] == [{'Type': 'battery'}]

    def test_get_blocks_none_does_not_crash(self):
        backend = self._make_backend()
        backend.tedapi.get_status.return_value = {
            'control': {
                'batteryBlocks': [{'din': 'PW1'}],
                'systemStatus': {},
                'alerts': {'active': []},
            },
        }
        backend.tedapi.get_config.return_value = {'vin': 'GW--123'}
        backend.tedapi.get_blocks.return_value = None  # gateway outage

        data = backend.get_api_system_status()  # used to raise TypeError
        assert data['available_blocks'] == 1
        assert data['battery_blocks'] == []

    def _status_with_config(self, config):
        backend = self._make_backend()
        backend.tedapi.get_status.return_value = {
            'control': {
                'batteryBlocks': [{'din': 'PW1'}, {'din': 'PW2'}],
                'systemStatus': {},
                'alerts': {'active': []},
            },
        }
        backend.tedapi.get_config.return_value = config
        backend.tedapi.get_blocks.return_value = {}
        return backend.get_api_system_status()

    def test_max_power_from_site_nominal_power(self):
        """Without inverter values, max charge/discharge/apparent power = config
        site_info nominal_system_power_ac (kW) in W, the nameplate_power Cloud
        and FleetAPI report (2x PW3 site: 13.44 kW -> 13440, not 13440.000000000002)."""
        data = self._status_with_config({'site_info': {'nominal_system_power_ac': 13.44}})
        assert data['max_charge_power'] == 13440
        assert data['max_discharge_power'] == 13440
        assert data['max_apparent_power'] == 13440
        assert isinstance(data['max_charge_power'], int)

    @pytest.mark.parametrize('config', [
        {'vin': 'GW--123'},
        {'site_info': None},
        {'site_info': {'nominal_system_power_ac': None}},
        {'site_info': {'nominal_system_power_ac': '13.44'}},
        {'site_info': {'nominal_system_power_ac': True}},
        {'site_info': {'nominal_system_power_ac': 0}},
        {'site_info': {'nominal_system_power_ac': -5}},
    ])
    def test_max_power_none_without_usable_nominal_power(self, config):
        data = self._status_with_config(config)
        assert data['max_charge_power'] is None
        assert data['max_discharge_power'] is None
        assert data['max_apparent_power'] is None

    def _status_with_pinv(self, pinv_units, config=None):
        backend = self._make_backend()
        backend.tedapi.get_status.return_value = {
            'control': {
                'batteryBlocks': [{'din': 'PW1'}, {'din': 'PW2'}],
                'systemStatus': {},
                'alerts': {'active': []},
            },
            'esCan': {'bus': {'PINV': pinv_units}},
        }
        backend.tedapi.get_config.return_value = config if config is not None else {
            'site_info': {'nominal_system_power_ac': 10}}
        backend.tedapi.get_blocks.return_value = {}
        return backend.get_api_system_status()

    @staticmethod
    def _pinv(*pnoms):
        return [{'PINV_PowerCapability': {'PINV_Pnom': p, 'isMIA': False}} for p in pnoms] + [
            {'PINV_PowerCapability': {'PINV_Pnom': 0, 'isMIA': True}}]

    # Real local-API captures: max_* = min(site nameplate, inverter usable power)
    @pytest.mark.parametrize('nominal_kw, pnoms, expected_max, expected_inverter', [
        (10, (4600, 4600), 9200, 9200),      # 2x PW2, single-phase derate (#423)
        (10.8, (5800, 5800), 10800, 11600),  # PW2 + PW+ (proxy/web/bogus sample)
        (10, (5850, 5850), 10000, 11700),    # README sample
    ])
    def test_max_power_matches_local_api(self, nominal_kw, pnoms, expected_max, expected_inverter):
        data = self._status_with_pinv(self._pinv(*pnoms), {'site_info': {'nominal_system_power_ac': nominal_kw}})
        assert data['inverter_nominal_usable_power'] == expected_inverter
        assert data['max_charge_power'] == expected_max
        assert data['max_discharge_power'] == expected_max
        assert data['max_apparent_power'] == expected_max

    def test_max_power_from_inverters_without_nameplate(self):
        data = self._status_with_pinv(self._pinv(4600, 4600), {'vin': 'GW--123'})
        assert data['max_charge_power'] == 9200

    def test_pw3_max_power_is_nameplate(self):
        """PW3: every esCan PINV slot is MIA with Pnom 0, so max_* = nameplate."""
        data = self._status_with_pinv(self._pinv(), {'site_info': {'nominal_system_power_ac': 13.44}})
        assert data['max_charge_power'] == 13440
        assert data['inverter_nominal_usable_power'] == 0

    def test_inverter_nominal_usable_power_mia_and_malformed_skipped(self):
        data = self._status_with_pinv([
            {'PINV_PowerCapability': {'PINV_Pnom': 4600, 'isMIA': False}},
            {'PINV_PowerCapability': {'PINV_Pnom': '4600', 'isMIA': False}},  # string
            {'PINV_PowerCapability': {'PINV_Pnom': True}},  # bool, no isMIA
            {'PINV_PowerCapability': {}},
            {},
        ])
        assert data['inverter_nominal_usable_power'] == 4600

    def test_inverter_nominal_usable_power_zero_without_es_can(self):
        """PW3 payloads have no esCan section: keep today's stub value 0."""
        data = self._status_with_config({'site_info': {'nominal_system_power_ac': 13.44}})
        assert data['inverter_nominal_usable_power'] == 0

    def _status_with_msa(self, msa, config=None):
        backend = self._make_backend()
        backend.tedapi.get_status.return_value = {
            'control': {
                'batteryBlocks': [{'din': 'PW1'}, {'din': 'PW2'}],
                'systemStatus': {},
                'alerts': {'active': []},
            },
        }
        backend.tedapi.get_config.return_value = config if config is not None else {
            'site_info': {'nominal_system_power_ac': 10}}
        backend.tedapi.get_blocks.return_value = {}
        backend.tedapi.get_device_controller.return_value = {'components': {'msa': msa}}
        return backend.get_api_system_status()

    def test_instantaneous_power_from_tepods(self):
        """Hardware basis (2026-10-18, 2x PW2, firmware 26.34.1): each POD module's
        msa TEPOD component reports POD_available_charge_power /
        POD_available_dischg_power; the site values are the per-unit sums
        (14000/15570 here) - the local API reported 14000/15570 in the same
        combined run (an earlier capture read 15590; the values move between
        reads). The empty serial-less slots echo both names as null and
        contribute nothing."""
        def tepod(charge, dischg):
            return [
                {"name": "POD_available_charge_power", "value": charge, "boolValue": None, "textValue": None},
                {"name": "POD_available_dischg_power", "value": dischg, "boolValue": None, "textValue": None}]
        msa = [
            {"partNumber": "1152100-13-E", "serialNumber": "GW_SERIAL", "signals": []},
            {"partNumber": "1092170-05-J", "serialNumber": "TETHC_SERIAL_1", "signals": [
                {"name": "THC_State", "value": None, "boolValue": None, "textValue": "THC_STATE_AUTONOMOUSCONTROL"}]},
            {"partNumber": "1081100-10-Q", "serialNumber": "PACKAGE_SERIAL_1", "signals": []},
            {"partNumber": "1081100-10-Q", "serialNumber": "MODULE_SERIAL_1", "signals": tepod(7000, 7000)},
            {"partNumber": "1081100-00-W", "serialNumber": "MODULE_SERIAL_2", "signals": tepod(7000, 8570)},
            {"partNumber": "", "serialNumber": "", "signals": tepod(None, None)},
        ]
        data = self._status_with_msa(msa)
        assert data['instantaneous_max_charge_power'] == 14000
        assert data['instantaneous_max_discharge_power'] == 15570

    def test_instantaneous_power_zero_without_tepods(self):
        """No msa TEPOD components (V2026_06 cannot carry the type): keep
        today's stub value 0."""
        data = self._status_with_config({'site_info': {'nominal_system_power_ac': 13.44}})
        assert data['instantaneous_max_charge_power'] == 0
        assert data['instantaneous_max_discharge_power'] == 0

    def test_instantaneous_power_duplicate_serial_counted_once(self):
        """A serial can appear on two msa components (its POD entry plus the
        empty slots echo names only): per signal only the last value per serial
        counts, so duplicates cannot double-count."""
        both = [
            {"name": "POD_available_charge_power", "value": 7000, "boolValue": None, "textValue": None},
            {"name": "POD_available_dischg_power", "value": 8570, "boolValue": None, "textValue": None}]
        msa = [
            {"partNumber": "1081100-10-Q", "serialNumber": "MODULE_1", "signals": both},
            {"partNumber": "1081100-10-Q", "serialNumber": "MODULE_1", "signals": both},
        ]
        data = self._status_with_msa(msa)
        assert data['instantaneous_max_charge_power'] == 7000
        assert data['instantaneous_max_discharge_power'] == 8570

    def test_instantaneous_power_malformed_values_skipped(self):
        msa = [
            None,
            "not-a-component",
            {"partNumber": "1081100-10-Q", "serialNumber": "S1", "signals": None},
            {"partNumber": "1081100-10-Q", "serialNumber": "S2", "signals": [
                {"name": "POD_available_charge_power", "value": "7000", "boolValue": None, "textValue": None},
                {"name": "POD_available_dischg_power", "value": True, "boolValue": None, "textValue": None},
                {"name": "POD_available_charge_power", "value": -5, "boolValue": None, "textValue": None}]},
            {"partNumber": "1081100-00-W", "serialNumber": "S3", "signals": [
                {"name": "POD_available_charge_power", "value": 7000, "boolValue": None, "textValue": None},
                {"name": "POD_available_dischg_power", "value": 8570.5, "boolValue": None, "textValue": None}]},
        ]
        data = self._status_with_msa(msa)
        assert data['instantaneous_max_charge_power'] == 7000
        assert data['instantaneous_max_discharge_power'] == 8570.5

    def test_instantaneous_power_serial_less_slot_skipped(self):
        """Serial-less placeholder slots can carry live-looking signals (cf.
        test_pw2_msa_signals.py:179) and must never count as another module:
        a 7000 W module plus a 7000 W serial-less slot stays 7000; a missing
        serialNumber key is skipped as well (review comment on #429)."""
        def tepod(charge, dischg):
            return [
                {"name": "POD_available_charge_power", "value": charge, "boolValue": None, "textValue": None},
                {"name": "POD_available_dischg_power", "value": dischg, "boolValue": None, "textValue": None}]
        msa = [
            {"partNumber": "1081100-10-Q", "serialNumber": "MODULE_SERIAL_1", "signals": tepod(7000, 8570)},
            {"partNumber": "", "serialNumber": "", "signals": tepod(7000, 7000)},
            {"partNumber": "", "signals": tepod(7000, 7000)},
        ]
        data = self._status_with_msa(msa)
        assert data['instantaneous_max_charge_power'] == 7000
        assert data['instantaneous_max_discharge_power'] == 8570


class TestVitalsPinvGridState:

    def test_pinv_grid_state_from_pinv_entry(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            ted = TEDAPI(gw_pwd='password')
        ted.pw3 = False
        config = {'vin': 'GW--123'}
        status = {
            'control': {'alerts': {'active': []}},
            'components': {'msa': []},
            'esCan': {
                'bus': {
                    'PVAC': [],
                    'PVS': [],
                    'THC': [{
                        'packagePartNumber': 'X1',
                        'packageSerialNumber': 'S1',
                        'alerts': {'active': []},
                    }],
                    'POD': [{
                        'POD_EnergyStatus': {
                            'POD_nom_energy_remaining': 1000,
                            'POD_nom_full_pack_energy': 2000,
                        },
                    }],
                    'PINV': [{
                        'PINV_Status': {
                            'PINV_GridState': 'Grid_Compliant',
                            'PINV_State': 'PINV_GridFollowing',
                        },
                    }],
                    'SYNC': {},
                    'ISLANDER': {},
                    'MSA': {},
                },
            },
        }
        ted.get_config = MagicMock(return_value=config)
        ted.get_device_controller = MagicMock(return_value=status)

        vitals = ted.vitals()
        assert vitals is not None
        pinv = vitals['TEPINV--X1--S1']
        # Regression: was looked up in the THC entry ('p') and always None
        assert pinv['PINV_GridState'] == 'Grid_Compliant'
        assert pinv['PINV_State'] == 'PINV_GridFollowing'


class TestNoneConfigGuards:
    """get_pw3_vitals()/get_battery_blocks() must not crash when get_config()
    returns None (gateway outage or lock timeout)."""

    def _make_tedapi(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            ted = TEDAPI(gw_pwd='password')
        ted.din = '1707000-11-J--TG123456789012'
        return ted

    def test_get_pw3_vitals_none_config(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_components', return_value={'pch': []}), \
             patch.object(ted, 'get_config', return_value=None):
            # Used to raise TypeError on config['battery_blocks']
            assert ted.get_pw3_vitals() is None

    def test_get_pw3_vitals_config_without_battery_blocks(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_components', return_value={'pch': []}), \
             patch.object(ted, 'get_config', return_value={'vin': 'GW--123'}):
            assert ted.get_pw3_vitals() == {}

    def test_get_battery_blocks_none_config(self):
        ted = self._make_tedapi()
        with patch.object(ted, 'get_config', return_value=None):
            # Used to raise AttributeError on None.get()
            assert ted.get_battery_blocks() == []


class TestVitalsPodPinvBoundsGuard:
    """POD/PINV lists shorter than the THC list must not raise IndexError."""

    def test_vitals_missing_pod_pinv_entries(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            ted = TEDAPI(gw_pwd='password')
        ted.pw3 = False
        config = {'vin': 'GW--123'}
        status = {
            'control': {'alerts': {'active': []}},
            'components': {'msa': []},
            'esCan': {
                'bus': {
                    'PVAC': [],
                    'PVS': [],
                    'THC': [{
                        'packagePartNumber': 'X1',
                        'packageSerialNumber': 'S1',
                        'alerts': {'active': []},
                    }],
                    'POD': [],   # shorter than THC
                    'PINV': [],  # shorter than THC
                    'SYNC': {},
                    'ISLANDER': {},
                    'MSA': {},
                },
            },
        }
        ted.get_config = MagicMock(return_value=config)
        ted.get_device_controller = MagicMock(return_value=status)

        vitals = ted.vitals()  # used to raise IndexError
        assert vitals is not None
        assert vitals['TEPOD--X1--S1']['POD_nom_energy_remaining'] is None
        assert vitals['TEPINV--X1--S1']['PINV_Pout'] is None


class TestApiLockTimeout:
    """Lock contention must degrade to cached-data/None, not raise
    TimeoutError out of poll()/vitals()."""

    def _make_tedapi(self):
        with patch.object(TEDAPI, 'connect', return_value=True):
            ted = TEDAPI(gw_pwd='password')
        ted.din = 'DIN--X'
        return ted

    def test_get_status_lock_timeout_returns_cached(self):
        ted = self._make_tedapi()
        ted.pwcache['status'] = {'cached': True}
        with patch('pypowerwall.api_lock.acquire_with_exponential_backoff', return_value=False):
            assert ted.get_status() == {'cached': True}  # used to raise TimeoutError

    def test_get_status_lock_timeout_no_cache_returns_none(self):
        ted = self._make_tedapi()
        ted.pwcache.pop('status', None)
        with patch('pypowerwall.api_lock.acquire_with_exponential_backoff', return_value=False):
            assert ted.get_status() is None

    def test_get_config_lock_timeout_returns_cached(self):
        ted = self._make_tedapi()
        ted.pwcache['config'] = {'vin': 'GW--123'}
        with patch('pypowerwall.api_lock.acquire_with_exponential_backoff', return_value=False):
            assert ted.get_config() == {'vin': 'GW--123'}


class TestConnectHygiene:
    """connect() session/PW3-detection hygiene:
    - any non-200 on GET / used to flip PW3 mode (429/503 misclassified a PW2)
    - repeated connect() calls used to rebuild the session (and leak the old
      one) even when a DIN was already known
    """

    def _make_tedapi(self):
        with patch.object(TEDAPI, 'connect', return_value='DIN'):
            ted = TEDAPI(gw_pwd='password')
        return ted

    def _run_connect(self, ted, status_code):
        response = MagicMock()
        response.status_code = status_code
        session = MagicMock()
        session.get.return_value = response
        with patch.object(ted, '_init_session', return_value=session), \
             patch.object(ted, 'get_din', return_value='TEST_DIN'):
            return ted.connect(force=True)

    def test_403_detected_as_pw3(self):
        ted = self._make_tedapi()
        assert self._run_connect(ted, 403) == 'TEST_DIN'
        assert ted.pw3 is True

    def test_404_detected_as_pw3(self):
        """PW3 firmware variants answer GET / with 404 instead of 403 - any
        non-transient non-200 must be treated as the PW3 signature
        (regression: /pod lost battery data in TEDAPI WiFi mode)."""
        ted = self._make_tedapi()
        assert self._run_connect(ted, 404) == 'TEST_DIN'
        assert ted.pw3 is True

    def test_503_does_not_flip_pw3(self):
        """Transient gateway errors must not misclassify a PW2 as PW3."""
        ted = self._make_tedapi()
        assert self._run_connect(ted, 503) == 'TEST_DIN'
        assert ted.pw3 is False

    def test_503_keeps_prior_pw3_true(self):
        ted = self._make_tedapi()
        ted.pw3 = True
        self._run_connect(ted, 503)
        assert ted.pw3 is True

    def test_connect_noop_when_already_connected(self):
        """connect() must not rebuild the session when DIN+session exist."""
        ted = self._make_tedapi()
        ted.din = 'TEST_DIN'
        ted.session = MagicMock()
        with patch.object(ted, '_init_session') as mock_init, \
             patch.object(ted, 'get_din') as mock_din:
            assert ted.connect() == 'TEST_DIN'
        mock_init.assert_not_called()
        mock_din.assert_not_called()

    def test_connect_force_closes_previous_session(self):
        """A forced reconnect must close the old session before replacing it."""
        ted = self._make_tedapi()
        ted.din = 'TEST_DIN'
        old_session = MagicMock()
        ted.session = old_session
        self._run_connect(ted, 200)
        old_session.close.assert_called_once()


class TestGetGridExportDefault:
    """get_grid_export() must fall back to Tesla's default ("battery_ok") when
    the config field is unset, matching cloud/fleetapi behavior."""

    def _make_backend(self):
        with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
            backend = PyPowerwallTEDAPI(gw_pwd='password')
        return backend

    def test_unset_field_returns_battery_ok(self):
        backend = self._make_backend()
        backend.tedapi.get_config.return_value = {'site_info': {}}
        assert backend.get_grid_export() == 'battery_ok'

    def test_explicit_value_passthrough(self):
        backend = self._make_backend()
        backend.tedapi.get_config.return_value = {
            'site_info': {'customer_preferred_export_rule': 'pv_only'}
        }
        assert backend.get_grid_export() == 'pv_only'

    def test_config_failure_returns_none(self):
        backend = self._make_backend()
        backend.tedapi.get_config.return_value = None
        assert backend.get_grid_export() is None


class TestPollVitalsForwardsForce:
    """The '/vitals' poll-map entry must forward the force kwarg to
    tedapi.vitals() (it used to route to vitals(), which dropped it)."""

    def test_force_forwarded(self):
        with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
            backend = PyPowerwallTEDAPI(gw_pwd='password')
        backend.tedapi.vitals.return_value = {'VITALS': {}}
        backend.poll('/vitals', force=True)
        backend.tedapi.vitals.assert_called_once_with(force=True)


class TestVitalsPhantomBlocks:
    """When esCan.bus.SYNC is absent (typical PW3), vitals() emits
    TESYNC--None--None and TESLA--None blocks. Despite the odd names these
    are FROZEN behavior: TESLA--None's componentParentDin (STSTSM--<vin>) is
    the only place the gateway DIN/serial appears in TEDAPI vitals and
    consumers depend on it (hardware regression, PR #349)."""

    def _make_ted(self, status):
        with patch.object(TEDAPI, 'connect', return_value=True):
            ted = TEDAPI(gw_pwd='password')
        ted.pw3 = False
        ted.get_config = MagicMock(return_value={'vin': 'GW--123'})
        ted.get_device_controller = MagicMock(return_value=status)
        return ted

    def _status(self, sync=None, msa=None):
        return {
            'control': {'alerts': {'active': []}},
            'components': {'msa': []},
            'esCan': {
                'bus': {
                    'PVAC': [],
                    'PVS': [],
                    'THC': [],
                    'POD': [],
                    'PINV': [],
                    'SYNC': sync or {},
                    'ISLANDER': {},
                    'MSA': msa or {},
                },
            },
        }

    def test_no_sync_still_emits_tesla_block_with_gateway_din(self):
        """TESLA--None must be emitted even without SYNC data - its
        componentParentDin carries the gateway DIN/serial."""
        ted = self._make_ted(self._status())
        vitals = ted.vitals()
        assert vitals is not None
        assert 'TESYNC--None--None' in vitals
        assert 'TESLA--None' in vitals
        assert vitals['TESLA--None']['componentParentDin'] == 'STSTSM--GW--123'

    def test_sync_present_emits_tesync(self):
        sync = {
            'packagePartNumber': 'SYNCPN',
            'packageSerialNumber': 'SYNCSN',
            'alerts': {'active': []},
        }
        ted = self._make_ted(self._status(sync=sync))
        vitals = ted.vitals()
        assert 'TESYNC--SYNCPN--SYNCSN' in vitals

    def test_msa_present_emits_temsa_and_tesla(self):
        msa = {
            'packagePartNumber': 'MSAPN',
            'packageSerialNumber': 'MSASN',
            'alerts': {'active': []},
        }
        ted = self._make_ted(self._status(msa=msa))
        vitals = ted.vitals()
        assert 'TEMSA--MSAPN--MSASN' in vitals
        assert 'TESLA--MSASN' in vitals
