"""Tests for the generator section of TEDAPI /api/meters/aggregates:

- A gateway whose config.json declares a generator meter gets a "generator"
  section with instant_power from meterAggregates' GENERATOR location
- Sites without a generator meter get no "generator" section, even though
  meterAggregates lists a GENERATOR location (realPowerW 0) on them too
- Lifetime energy_imported/energy_exported merge from the gateway's native
  /api/meters/aggregates generator section, when it serves one
"""
from unittest.mock import patch

from pypowerwall.tedapi.pypowerwall_tedapi import PyPowerwallTEDAPI

# Shape observed on a Backup Gateway 2 (firmware 26.34.2) with a standby generator
CONFIG_WITH_GENERATOR = {
    'vin': 'GW--123',
    'meters': [
        {'location': 'site', 'type': 'neurio_tcp'},
        {'location': 'solar', 'type': 'neurio_tcp'},
        {'location': 'generator', 'type': 'neurio_tcp'},
    ],
}
CONFIG_WITHOUT_GENERATOR = {
    'vin': 'GW--123',
    'meters': [
        {'location': 'site', 'type': 'neurio_tcp'},
        {'location': 'solar', 'type': 'neurio_tcp'},
    ],
}
POWER = {'site': -15.6, 'load': 982.4, 'solar': 2099.5, 'battery': -1120, 'generator': 1.73}

NATIVE_WITH_GENERATOR = {
    "site": {"energy_exported": 1469391, "energy_imported": 4902666.25},
    "battery": {"energy_exported": 4712126, "energy_imported": 4803385},
    "load": {"energy_exported": 0, "energy_imported": 11679089},
    "solar": {"energy_exported": 8337073, "energy_imported": 0},
    "generator": {"instant_power": 1.67, "energy_exported": 271310.88, "energy_imported": 6768.85},
}


def _make_backend(config):
    with patch('pypowerwall.tedapi.pypowerwall_tedapi.TEDAPI'):
        backend = PyPowerwallTEDAPI(gw_pwd='password')
    backend.tedapi.pw3 = False
    backend.tedapi.current_power.side_effect = lambda force=False, location=None: POWER.get(location.lower())
    backend.tedapi.get_config.return_value = config
    backend.tedapi.get_status.return_value = {
        'system': {'time': '2026-11-09T16:23:18Z'},
        'esCan': {'bus': {}},
    }
    backend.tedapi.get_native_meters_aggregates.return_value = None
    return backend


class TestGeneratorSection:

    def test_generator_section_when_config_declares_meter(self):
        backend = _make_backend(CONFIG_WITH_GENERATOR)
        data = backend.get_api_meters_aggregates()

        assert 'generator' in data
        gen = data['generator']
        assert gen['instant_power'] == 1.73
        assert gen['last_communication_time'] == '2026-11-09T16:23:18Z'
        assert gen['last_communication_time'] == data['site']['last_communication_time']
        assert gen['num_meters_aggregated'] == 1
        # Without the native endpoint the lifetime counters stay at the stub's 0s
        assert gen['energy_exported'] == 0
        assert gen['energy_imported'] == 0
        assert gen['disclaimer'].startswith('generator:')
        # Other sections unchanged
        assert data['solar']['instant_power'] == 2099.5

    def test_no_generator_section_without_generator_meter(self):
        backend = _make_backend(CONFIG_WITHOUT_GENERATOR)
        data = backend.get_api_meters_aggregates()

        assert 'generator' not in data
        assert set(data) == {'site', 'battery', 'load', 'solar'}
        # current_power('generator') must not even be asked for
        locations = [c.kwargs.get('location') for c in backend.tedapi.current_power.call_args_list]
        assert 'generator' not in locations

    def test_no_generator_section_when_config_has_no_meters_list(self):
        for config in ({'vin': 'GW--123'}, {'vin': 'GW--123', 'meters': None},
                       {'vin': 'GW--123', 'meters': ['generator', None]}):
            backend = _make_backend(config)
            assert 'generator' not in backend.get_api_meters_aggregates()

    def test_generator_location_is_case_insensitive(self):
        config = dict(CONFIG_WITH_GENERATOR, meters=[{'location': 'GENERATOR'}])
        backend = _make_backend(config)
        assert backend.get_api_meters_aggregates()['generator']['instant_power'] == 1.73

    def test_generator_power_missing_from_meter_aggregates(self):
        # Config declares the meter but meterAggregates lacks GENERATOR (or control is null):
        # keep the section, with power None like the other extractors do
        backend = _make_backend(CONFIG_WITH_GENERATOR)
        backend.tedapi.current_power.side_effect = lambda force=False, location=None: None
        data = backend.get_api_meters_aggregates()
        assert data['generator']['instant_power'] is None

    def test_native_energy_merge_includes_generator(self):
        backend = _make_backend(CONFIG_WITH_GENERATOR)
        backend.tedapi.get_native_meters_aggregates.return_value = NATIVE_WITH_GENERATOR
        data = backend.get_api_meters_aggregates()

        gen = data['generator']
        assert gen['energy_exported'] == 271310.88
        assert gen['energy_imported'] == 6768.85
        assert gen['disclaimer'].endswith('; energy from gateway local API')
        # instant_power still comes from TEDAPI, not the native payload
        assert gen['instant_power'] == 1.73

    def test_native_generator_section_ignored_without_generator_meter(self):
        backend = _make_backend(CONFIG_WITHOUT_GENERATOR)
        backend.tedapi.get_native_meters_aggregates.return_value = NATIVE_WITH_GENERATOR
        data = backend.get_api_meters_aggregates()
        assert 'generator' not in data
        assert data['site']['energy_imported'] == 4902666.25
