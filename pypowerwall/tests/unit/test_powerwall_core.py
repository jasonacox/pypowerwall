import json
import pytest
from pypowerwall import Powerwall
from pypowerwall.pypowerwall_base import PyPowerwallBase

class StubClient(PyPowerwallBase):
    def __init__(self):
        super().__init__(email='test@example.com')
        self.calls = []
        # minimal caches
        self._poll_map = {
            '/api/meters/aggregates': {
                'site': {'instant_power': 1000},
                'solar': {'instant_power': 2000},
                'battery': {'instant_power': -500},
                'load': {'instant_power': 1500}
            },
            '/api/status': {'version': '23.44.1', 'din': 'DIN123', 'up_time_seconds': 1234},
            '/api/system_status/grid_status': {'grid_status': 'SystemGridConnected'},
            '/api/system_status': {'battery_blocks': [], 'grid_faults': [], 'system_island_state': 'SystemGridConnected'},
            '/api/operation': {'backup_reserve_percent': 20, 'real_mode': 'self_consumption'},
            '/api/site_info/site_name': {'site_name': 'Test Site'},
            '/api/solar_powerwall': {
                'pvac_status': {'string_vitals': []},
                'pvac_alerts': {'OverVoltage': True, 'UnderTemp': False},
                'pvs_alerts': {'StringFault': True}
            }
        }
        self._vitals = {
            'TETHC--X--SN123': {
                'THC_AmbientTemp': 25.5,
                'THC_State': 'Normal'
            }
        }

    def authenticate(self):
        return True

    def close_session(self):
        return True

    def poll(self, api: str, force: bool = False, recursive: bool = False, raw: bool = False):
        self.calls.append(('poll', api, force))
        return self._poll_map.get(api)

    def post(self, api: str, payload, din: str, recursive: bool = False, raw: bool = False):
        self.calls.append(('post', api, payload))
        # Simulate modifying backup_reserve_percent
        if api == '/api/operation' and payload:
            if payload.get('backup_reserve_percent') is not False:
                self._poll_map['/api/operation']['backup_reserve_percent'] = payload['backup_reserve_percent']
            if payload.get('real_mode'):
                self._poll_map['/api/operation']['real_mode'] = payload['real_mode']
        return {'ok': True, 'payload': payload}

    def vitals(self):
        return self._vitals

    def get_time_remaining(self):
        return 4.5

@pytest.fixture(name="pw")
def fixture_powerwall():
    # Instantiate Powerwall but replace its client with our stub
    inst = Powerwall(host='', password='', email='test@example.com', cloudmode=True, siteid=None)
    inst.client = StubClient()
    return inst

def test_poll_jsonformat(pw):
    out = pw.poll('/api/site_info/site_name', jsonformat=True)
    assert isinstance(out, str)
    data = json.loads(out)
    assert data['site_name'] == 'Test Site'

def test_level_and_power(pw):
    lvl = pw.level()
    assert lvl is None  # because /api/system_status/soe not in map
    p = pw.power()
    assert p['site'] == 1000 and p['solar'] == 2000 and p['battery'] == -500 and p['load'] == 1500


def test_grid_status(pw):
    assert pw.grid_status() == 'UP'
    assert pw.grid_status(type='numeric') == 1
    j = pw.grid_status(type='json')
    assert 'grid_status' in json.loads(j)


def test_alerts_with_vitals_and_fallback(pw):
    # With vitals present, alerts set should be empty until fallback
    # Simulate vitals absent to trigger fallback logic
    pw.client._vitals = {}
    alerts = pw.alerts()
    # Expect inferred alerts from solar_powerwall and grid status mapping
    assert 'OverVoltage' in alerts
    assert 'StringFault' in alerts
    assert 'SystemConnectedToGrid' in alerts


def test_set_operation_validation(pw):
    # Invalid level
    assert pw.set_operation(level=150) is None
    # Valid update
    resp = pw.set_operation(level=30, mode='backup')
    assert resp['ok'] is True


def test_get_reserve_and_mode(pw):
    r = pw.get_reserve(scale=False)
    assert r == 20
    m = pw.get_mode()
    assert m == 'self_consumption'


def test_set_mode_and_reserve_helpers(pw):
    # set_reserve wraps set_operation
    resp = pw.set_reserve(40)
    assert resp['ok'] is True
    assert pw.get_reserve(scale=False) == 40
    resp2 = pw.set_mode('backup')
    assert resp2['ok'] is True


def test_battery_blocks_temp_merge(pw):
    # system_status has empty battery_blocks so battery_blocks() should handle gracefully
    blocks = pw.battery_blocks()
    assert blocks is None or isinstance(blocks, (dict, list))


def test_temps(pw):
    t = pw.temps()
    assert isinstance(t, dict)


def test_site_name(pw):
    assert pw.site_name() == 'Test Site'
