"""Regression tests for TEDAPI backend bugs:
- available_blocks read control.batteryBlocks from config instead of status (always 0)
- get_blocks() returning None crashed get_api_system_status()
- PINV_GridState was looked up in the THC entry instead of the PINV entry
"""
from unittest.mock import MagicMock, patch

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
