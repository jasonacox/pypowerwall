"""CLI `get`: per-device temperatures and fan speeds join the other metrics in
every output format when the connection mode reports them, and the output is
unchanged when it doesn't."""
import json
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.__main__ import main

BASE_KEYS = ['site', 'site_id', 'din', 'firmware', 'mode', 'reserve', 'soc', 'grid_status',
             'grid', 'home', 'battery', 'solar', 'grid_charging', 'grid_export_mode',
             'time_remaining']
TEMPS = {"TEPOD--1707000-25-J--TG1253370033TB": 24.1, "TEPOD--1707000-25-J--TG125337002LNY": None}
FANS = {
    "TEPINV--1707000-11-M--TG1253370033TB": {
        "PCH_FanSpeed_A": 1391, "PCH_FanSpeed_B": 1395, "PCH_FanDuty_A": 18.7, "PCH_FanDuty_B": 19.1},
    "PVAC--1538100-01-G--ADU25114D001SC": {
        "PVAC_Fan_Speed_Actual_RPM": 1234, "PVAC_Fan_Speed_Target_RPM": None},
}


def _run_get(capsys, fmt, temps=None, fans=None):
    pw = MagicMock()
    pw.is_connected.return_value = True
    pw.mode = 'tedapi'
    pw.siteid = None
    for method, value in [('site_name', 'Test Site'), ('din', 'DIN123'), ('version', '26.26.11'),
                          ('get_mode', 'self_consumption'), ('get_reserve', 20.0), ('level', 50.0),
                          ('grid_status', 'UP'), ('grid', 100.0), ('home', 900.0), ('battery', 0.0),
                          ('solar', 800.0), ('get_grid_charging', False),
                          ('get_grid_export', 'battery_ok'), ('get_time_remaining', 12.5)]:
        getattr(pw, method).return_value = value
    pw.temps.return_value = temps or {}
    if fans is None:
        pw.tedapi = False  # cloud/fleetapi/local: no TEDAPI client
    else:
        pw.tedapi.get_fan_speeds.return_value = fans
    argv = ['pypowerwall', 'get', '-tedapi', '-gw_pwd', 'ABCDEXXXXX', '-format', fmt]
    with patch('sys.argv', argv), patch('pypowerwall.Powerwall', return_value=pw):
        main()
    return capsys.readouterr().out


def test_json_nests_temps_and_fans(capsys):
    out = json.loads(_run_get(capsys, 'json', TEMPS, FANS))
    assert list(out) == BASE_KEYS + ['temps', 'fans']
    assert out['temps'] == TEMPS
    assert out['fans'] == FANS


def test_csv_flattens_to_device_columns(capsys):
    header, values = _run_get(capsys, 'csv', TEMPS, FANS).strip().splitlines()
    row = dict(zip(header.split(','), values.split(',')))
    assert list(row)[:len(BASE_KEYS)] == BASE_KEYS
    assert row['temps.TEPOD--1707000-25-J--TG1253370033TB'] == '24.1'
    assert row['temps.TEPOD--1707000-25-J--TG125337002LNY'] == 'N/A'
    assert row['fans.TEPINV--1707000-11-M--TG1253370033TB.PCH_FanSpeed_A'] == '1391'
    assert row['fans.PVAC--1538100-01-G--ADU25114D001SC.PVAC_Fan_Speed_Target_RPM'] == 'N/A'


def test_text_lists_one_row_per_device(capsys):
    out = _run_get(capsys, 'text', TEMPS, FANS)
    assert '  Temperatures\n' in out and '  Fans\n' in out
    row = "    {:<38}{}".format
    assert row('TEPOD--1707000-25-J--TG1253370033TB', '24.1') in out
    assert row('TEPOD--1707000-25-J--TG125337002LNY', 'N/A') in out
    assert row('TEPINV--1707000-11-M--TG1253370033TB', 'PCH_FanSpeed_A=1391, PCH_FanSpeed_B=1395, '
               'PCH_FanDuty_A=18.7, PCH_FanDuty_B=19.1') in out
    assert 'PVAC_Fan_Speed_Target_RPM=N/A' in out


@pytest.mark.parametrize('fmt', ['json', 'csv', 'text'])
def test_unchanged_without_temps_or_fans(capsys, fmt):
    # Modes without vitals or a TEDAPI client keep the exact pre-existing output
    out = _run_get(capsys, fmt)
    if fmt == 'json':
        assert list(json.loads(out)) == BASE_KEYS
    elif fmt == 'csv':
        assert out.splitlines()[0] == ','.join(BASE_KEYS)
    else:
        assert 'Temperatures' not in out and 'Fans' not in out


def _build(argv):
    """Run main() with argv and return the kwargs Powerwall() was built with."""
    with patch('sys.argv', ['pypowerwall'] + argv), patch('pypowerwall.Powerwall') as pw_cls:
        pw_cls.return_value.is_connected.return_value = False  # stop after construction
        with pytest.raises(SystemExit):
            main()
    return pw_cls.call_args.kwargs


def test_tedapi_options_reach_powerwall():
    kwargs = _build(['get', '-tedapi', '-gw_pwd', 'ABCDEXXXXX',
                     '-tedapi_api_version', 'V2026_06', '-tedapi_auth_mode', 'bearer'])
    assert kwargs['tedapi_api_version'] == 'V2026_06'
    assert kwargs['tedapi_auth_mode'] == 'bearer'


def test_v1r_takes_api_version(tmp_path):
    key = tmp_path / 'key.pem'
    key.write_text('x')
    kwargs = _build(['get', '-v1r', '-host', '10.42.1.40', '-gw_pwd', 'ABCDEXXXXX',
                     '-rsa_key_path', str(key), '-tedapi_api_version', 'V2026_06'])
    assert kwargs['tedapi_api_version'] == 'V2026_06'
    assert 'tedapi_auth_mode' not in kwargs


def test_unset_options_keep_library_defaults():
    kwargs = _build(['get', '-tedapi', '-gw_pwd', 'ABCDEXXXXX'])
    assert 'tedapi_api_version' not in kwargs and 'tedapi_auth_mode' not in kwargs


@pytest.mark.parametrize('argv, message', [
    (['get', '-cloud', '-tedapi_api_version', 'V2026_06'], 'require -tedapi or -v1r'),
    (['set', '-reserve', '20', '-tedapi_auth_mode', 'bearer'], 'require -tedapi or -v1r'),
    (['get', '-v1r', '-host', '10.42.1.40', '-gw_pwd', 'ABCDEXXXXX',
      '-tedapi_auth_mode', 'bearer'], 'applies to -tedapi only'),
])
def test_options_rejected_where_they_would_be_ignored(capsys, argv, message):
    with patch('sys.argv', ['pypowerwall'] + argv), patch('pypowerwall.Powerwall') as pw_cls:
        with pytest.raises(SystemExit) as excinfo:
            main()
    assert excinfo.value.code == 1
    assert message in capsys.readouterr().out
    pw_cls.assert_not_called()
