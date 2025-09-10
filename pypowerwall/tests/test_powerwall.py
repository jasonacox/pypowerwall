import pytest
from unittest.mock import MagicMock

@pytest.fixture()
def pw_fixture():
    # Mock Powerwall object for unit testing
    pw = MagicMock()
    pw.get_mode.return_value = 'self_consumption'
    pw.set_mode.return_value = {'set_operation': {'result': 'Updated', 'real_mode': 'backup'}}
    pw.get_reserve.return_value = 50
    pw.set_reserve.return_value = {'set_backup_reserve_percent': {'result': 'Updated', 'backup_reserve_percent': 100}}
    pw.is_connected.return_value = True
    pw.site_name.return_value = 'Test Site'
    pw.version.return_value = '1.2.3'
    pw.uptime.return_value = '12345'
    pw.din.return_value = 'DIN12345'
    pw.level.return_value = 80.0
    pw.power.return_value = {'site': 1000, 'solar': 2000, 'battery': -500, 'load': 1500}
    pw.site.return_value = {'power': 1000}
    pw.solar.return_value = {'power': 2000}
    pw.battery.return_value = {'power': -500}
    pw.load.return_value = {'power': 1500}
    pw.grid.return_value = {'power': 1000}
    pw.home.return_value = {'power': 1500}
    pw.vitals.return_value = {'vitals': 'ok'}
    pw.strings.return_value = {'strings': 'ok'}
    pw.temps.return_value = {'temps': 'ok'}
    pw.alerts.return_value = ['alert1', 'alert2']
    pw.system_status.return_value = {'nominal_full_pack_energy': 25547, 'system_island_state': 'SystemGridConnected', 'available_blocks': 2, 'battery_blocks': []}
    pw.battery_blocks.return_value = [{'serial': 'B1'}, {'serial': 'B2'}]
    pw.grid_status.return_value = 'UP'
    pw.get_time_remaining.return_value = 4.5
    pw.poll.return_value = {'result': 'ok'}
    return pw

def test_battery_mode_change(pw_fixture):
    pw = pw_fixture
    original_mode = pw.get_mode(force=True)
    new_mode = 'backup' if original_mode != 'backup' else 'self_consumption'
    resp = pw.set_mode(mode=new_mode)
    assert resp['set_operation']['result'] == 'Updated'
    assert resp['set_operation']['real_mode'] == new_mode

def test_battery_reserve_change(pw_fixture):
    pw = pw_fixture
    original_reserve_level = pw.get_reserve(force=True)
    new_reserve_level = 100 if original_reserve_level != 100 else 50
    resp = pw.set_reserve(level=new_reserve_level)
    assert resp['set_backup_reserve_percent']['result'] == 'Updated'
    assert resp['set_backup_reserve_percent']['backup_reserve_percent'] == new_reserve_level

def test_is_connected(pw_fixture):
    pw = pw_fixture
    assert pw.is_connected() is True

def test_site_name(pw_fixture):
    pw = pw_fixture
    assert pw.site_name() == 'Test Site'

def test_version(pw_fixture):
    pw = pw_fixture
    assert pw.version() == '1.2.3'

def test_uptime(pw_fixture):
    pw = pw_fixture
    assert pw.uptime() == '12345'

def test_din(pw_fixture):
    pw = pw_fixture
    assert pw.din() == 'DIN12345'

def test_level(pw_fixture):
    pw = pw_fixture
    assert pw.level() == 80.0

def test_power(pw_fixture):
    pw = pw_fixture
    result = pw.power()
    assert isinstance(result, dict)
    assert result['site'] == 1000
    assert result['solar'] == 2000
    assert result['battery'] == -500
    assert result['load'] == 1500

def test_site(pw_fixture):
    pw = pw_fixture
    assert pw.site()['power'] == 1000

def test_solar(pw_fixture):
    pw = pw_fixture
    assert pw.solar()['power'] == 2000

def test_battery(pw_fixture):
    pw = pw_fixture
    assert pw.battery()['power'] == -500

def test_load(pw_fixture):
    pw = pw_fixture
    assert pw.load()['power'] == 1500

def test_grid(pw_fixture):
    pw = pw_fixture
    assert pw.grid()['power'] == 1000

def test_home(pw_fixture):
    pw = pw_fixture
    assert pw.home()['power'] == 1500

def test_vitals(pw_fixture):
    pw = pw_fixture
    assert pw.vitals()['vitals'] == 'ok'

def test_strings(pw_fixture):
    pw = pw_fixture
    assert pw.strings()['strings'] == 'ok'

def test_temps(pw_fixture):
    pw = pw_fixture
    assert pw.temps()['temps'] == 'ok'

def test_alerts(pw_fixture):
    pw = pw_fixture
    alerts = pw.alerts()
    assert isinstance(alerts, list)
    assert 'alert1' in alerts

def test_system_status(pw_fixture):
    pw = pw_fixture
    status = pw.system_status()
    assert status['nominal_full_pack_energy'] == 25547
    assert status['system_island_state'] == 'SystemGridConnected'
    assert status['available_blocks'] == 2

def test_battery_blocks(pw_fixture):
    pw = pw_fixture
    blocks = pw.battery_blocks()
    assert isinstance(blocks, list)
    assert blocks[0]['serial'] == 'B1'

def test_grid_status(pw_fixture):
    pw = pw_fixture
    assert pw.grid_status() == 'UP'

def test_get_time_remaining(pw_fixture):
    pw = pw_fixture
    assert pw.get_time_remaining() == 4.5

def test_poll(pw_fixture):
    pw = pw_fixture
    assert pw.poll('/api/meters/aggregates')['result'] == 'ok'
