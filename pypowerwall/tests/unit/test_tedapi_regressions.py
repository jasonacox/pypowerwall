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
