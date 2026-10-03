import json
from unittest.mock import MagicMock, patch


def test_main_forwards_tedapi_v1r_args():
    from pypowerwall.__main__ import main

    argv = [
        'pypowerwall', 'tedapi',
        '-host', '10.42.1.40',
        '-v1r',
        '-gw_pwd', 'ABCDEXXXXX',
        '-rsa_key_path', '/tmp/test.pem',
    ]

    with patch('sys.argv', argv), \
         patch('pypowerwall.tedapi.__main__.run_tedapi_test') as mock_run:
        main()

    mock_run.assert_called_once_with(
        argv=['-gw_pwd', 'ABCDEXXXXX', '-host', '10.42.1.40', '-v1r', '-rsa_key_path', '/tmp/test.pem'],
        debug=False,
    )


def test_run_tedapi_test_v1r_derives_password_from_gw_pwd(tmp_path, monkeypatch):
    from pypowerwall.tedapi.__main__ import run_tedapi_test

    mock_ted = MagicMock()
    mock_ted.din = 'DIN123'
    mock_ted.get_config.return_value = {}
    mock_ted.get_status.return_value = {}
    monkeypatch.chdir(tmp_path)

    with patch('requests.get') as mock_get, \
         patch('pypowerwall.tedapi.TEDAPI', return_value=mock_ted) as mock_tedapi:
        mock_get.return_value.status_code = 200
        run_tedapi_test([
            '-host', '10.42.1.40',
            '-v1r',
            '-gw_pwd', 'ABCDEXXXXX',
            '-rsa_key_path', '/tmp/test.pem',
        ])

    mock_tedapi.assert_called_once_with(
        gw_pwd='ABCDEXXXXX',
        host='10.42.1.40',
        v1r=True,
        password='XXXXX',
        rsa_key_path='/tmp/test.pem',
        wifi_host=None,
        tedapi_api_version='V2024_06',
    )


def test_run_tedapi_test_v1r_password_only_no_gw_pwd(tmp_path, monkeypatch):
    """v1r with -password but no -gw_pwd must not hang on interactive input."""
    from pypowerwall.tedapi.__main__ import run_tedapi_test

    mock_ted = MagicMock()
    mock_ted.din = 'DIN123'
    mock_ted.get_config.return_value = {}
    mock_ted.get_status.return_value = {}
    monkeypatch.chdir(tmp_path)

    with patch('requests.get') as mock_get, \
         patch('pypowerwall.tedapi.TEDAPI', return_value=mock_ted) as mock_tedapi, \
         patch('builtins.input') as mock_input:
        mock_get.return_value.status_code = 200
        run_tedapi_test([
            '-host', '10.42.1.40',
            '-v1r',
            '-password', 'mypass',
            '-rsa_key_path', '/tmp/test.pem',
        ])

    mock_input.assert_not_called()
    mock_tedapi.assert_called_once_with(
        gw_pwd='',
        host='10.42.1.40',
        v1r=True,
        password='mypass',
        rsa_key_path='/tmp/test.pem',
        wifi_host=None,
        tedapi_api_version='V2024_06',
    )

def test_render_firmware_plain_details_and_none():
    from pypowerwall.tedapi.__main__ import _render_firmware

    # plain: just the version string
    assert _render_firmware("26.11.1 abcd1234") == "26.11.1 abcd1234"
    # missing: friendly message, never raises
    assert "no response" in _render_firmware(None)
    # details: dict with a bytes githash (both protos type it as bytes) must be
    # JSON-safe -- hex-encoded, not a TypeError
    payload = {"system": {"version": {"text": "26.11.1", "githash": b"\xde\xad\xbe\xef"}}}
    out = _render_firmware(payload, details=True)
    assert "deadbeef" in out and "26.11.1" in out


def test_run_tedapi_test_firmware_mode_exits_early(tmp_path, monkeypatch, capsys):
    """`-firmware` fetches the version, prints it, and skips config/status."""
    from pypowerwall.tedapi.__main__ import run_tedapi_test

    mock_ted = MagicMock()
    mock_ted.din = 'DIN123'
    mock_ted.get_firmware_version.return_value = "26.11.1 abcd1234"
    monkeypatch.chdir(tmp_path)

    with patch('requests.get') as mock_get, \
         patch('pypowerwall.tedapi.TEDAPI', return_value=mock_ted):
        mock_get.return_value.status_code = 200
        run_tedapi_test(['-host', '10.42.1.40', '-gw_pwd', 'ABCDEXXXXX', '-firmware'])

    mock_ted.get_firmware_version.assert_called_once_with(force=True, details=False)
    mock_ted.get_config.assert_not_called()
    mock_ted.get_status.assert_not_called()
    assert "26.11.1 abcd1234" in capsys.readouterr().out


def test_main_forwards_tedapi_firmware_flags():
    from pypowerwall.__main__ import main

    argv = ['pypowerwall', 'tedapi', '-host', '10.42.1.40',
            '-gw_pwd', 'ABCDEXXXXX', '-firmware', '-details']
    with patch('sys.argv', argv), \
         patch('pypowerwall.tedapi.__main__.run_tedapi_test') as mock_run:
        main()

    forwarded = mock_run.call_args.kwargs['argv']
    assert '-firmware' in forwarded and '-details' in forwarded


def test_get_local_without_host_exits_with_error(capsys):
    """CLI 'get -local' without -host used to silently flip to cloud mode."""
    import pytest
    from pypowerwall.__main__ import main

    argv = ['pypowerwall', 'get', '-local']
    with patch('sys.argv', argv), \
         patch('pypowerwall.Powerwall') as mock_pw:
        with pytest.raises(SystemExit) as excinfo:
            main()

    assert excinfo.value.code == 1
    assert '-local requires -host' in capsys.readouterr().out
    mock_pw.assert_not_called()


def _run_cli_with_status(status_payload, tmp_path, monkeypatch):
    """Drive run_tedapi_test() with a mocked TEDAPI returning status_payload."""
    from pypowerwall.tedapi.__main__ import run_tedapi_test

    mock_ted = MagicMock()
    mock_ted.din = 'DIN123'
    mock_ted.get_config.return_value = {"site": "test"}
    mock_ted.get_status.return_value = status_payload
    mock_ted.get_firmware_version.return_value = "26.26.11 test"
    monkeypatch.chdir(tmp_path)

    with patch('requests.get') as mock_get, \
         patch('pypowerwall.tedapi.TEDAPI', return_value=mock_ted):
        mock_get.return_value.status_code = 200
        run_tedapi_test([
            '-host', '10.42.1.40',
            '-v1r',
            '-gw_pwd', 'ABCDEXXXXX',
            '-rsa_key_path', '/tmp/test.pem',
        ])
    return mock_ted


def test_run_tedapi_test_null_control_payload(tmp_path, monkeypatch, capsys):
    """Regression: explicit null 'control' must not crash (PW3 fw 26.26.11)."""
    status = {"control": None, "gateway": {"something": 1}}
    _run_cli_with_status(status, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "WARNING" in out and "'control'" in out
    assert "Battery Full Charge Unknown" in out
    saved = json.loads((tmp_path / "status.json").read_text())
    assert saved == status
    assert json.loads((tmp_path / "config.json").read_text()) == {"site": "test"}


def test_run_tedapi_test_null_system_status(tmp_path, monkeypatch, capsys):
    """Regression: null 'control.systemStatus' must not crash."""
    status = {"control": {"systemStatus": None, "meterAggregates": []}}
    _run_cli_with_status(status, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "Battery Full Charge Unknown" in out
    assert json.loads((tmp_path / "status.json").read_text()) == status


def test_run_tedapi_test_null_meter_aggregates(tmp_path, monkeypatch, capsys):
    """Regression: null 'control.meterAggregates' must not crash."""
    status = {
        "control": {
            "systemStatus": {
                "nominalEnergyRemainingWh": 7500,
                "nominalFullPackEnergyWh": 10000,
            },
            "meterAggregates": None,
        }
    }
    _run_cli_with_status(status, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "Battery Charge: 75.0%" in out
    assert json.loads((tmp_path / "status.json").read_text()) == status


def test_run_tedapi_test_normal_power_payload(tmp_path, monkeypatch, capsys):
    """Normal payload still renders battery charge and meters."""
    status = {
        "control": {
            "systemStatus": {
                "nominalEnergyRemainingWh": 5000,
                "nominalFullPackEnergyWh": 10000,
            },
            "meterAggregates": [
                {"location": "load", "realPowerW": 1234},
                {"location": "solar", "realPowerW": 250},
            ],
        }
    }
    _run_cli_with_status(status, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "Battery Charge: 50.0%" in out
    assert "Load: 1234W" in out and "Solar: 250W" in out
    assert "WARNING" not in out
    assert json.loads((tmp_path / "status.json").read_text()) == status


def _run_cli_with_payloads(status_payload, config_payload, tmp_path, monkeypatch):
    """Drive run_tedapi_test() with mocked TEDAPI config and status payloads."""
    from pypowerwall.tedapi.__main__ import run_tedapi_test

    mock_ted = MagicMock()
    mock_ted.din = 'DIN123'
    mock_ted.get_config.return_value = config_payload
    mock_ted.get_status.return_value = status_payload
    mock_ted.get_firmware_version.return_value = "26.26.11 test"
    monkeypatch.chdir(tmp_path)

    with patch('requests.get') as mock_get, \
         patch('pypowerwall.tedapi.TEDAPI', return_value=mock_ted):
        mock_get.return_value.status_code = 200
        run_tedapi_test([
            '-host', '10.42.1.40',
            '-v1r',
            '-gw_pwd', 'ABCDEXXXXX',
            '-rsa_key_path', '/tmp/test.pem',
        ])
    return mock_ted


def test_run_tedapi_test_sitemanager_not_running(tmp_path, monkeypatch, capsys):
    """Trimmed shape of the reporter's capture: site manager down -> control null."""
    status = {
        "control": None,
        "system": {"sitemanagerStatus": {"isRunning": False}},
    }
    _run_cli_with_payloads(status, {"site_info": {"site_name": "Test"}}, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "site manager is not running" in out
    assert "Tesla app" in out
    assert "not a pypowerwall problem" in out
    assert "isRunning: False" in out
    assert "schema" not in out.split("WARNING")[1].split("Battery")[0]
    assert json.loads((tmp_path / "status.json").read_text()) == status


def test_run_tedapi_test_sitemanager_running_null_control(tmp_path, monkeypatch, capsys):
    """Site manager running but control null -> ask for the payload."""
    status = {
        "control": None,
        "system": {"sitemanagerStatus": {"isRunning": True}},
    }
    _run_cli_with_payloads(status, {}, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "isRunning: True" in out
    assert "share it in a GitHub issue" in out
    assert "site manager is not running" not in out


def test_run_tedapi_test_null_meter_entry_fields(tmp_path, monkeypatch, capsys):
    """Null realPowerW / location values and null meter entries must not crash."""
    status = {
        "control": {
            "systemStatus": {
                "nominalEnergyRemainingWh": 5000,
                "nominalFullPackEnergyWh": 10000,
            },
            "meterAggregates": [
                {"location": None, "realPowerW": None},
                None,
                {"location": "load", "realPowerW": 1234},
            ],
        }
    }
    _run_cli_with_payloads(status, {}, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "Battery Charge: 50.0%" in out
    assert "Unknown: 0W" in out
    assert "Load: 1234W" in out


def test_run_tedapi_test_control_as_list(tmp_path, monkeypatch, capsys):
    """control as a non-empty list must not crash .get() lookups."""
    status = {"control": [{"bogus": 1}]}
    _run_cli_with_payloads(status, {}, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "Battery Full Charge Unknown" in out


def test_run_tedapi_test_null_config_fields(tmp_path, monkeypatch, capsys):
    """Null site_info / battery_blocks in config must not crash."""
    status = {"control": None}
    config = {"site_info": None, "vin": None, "battery_blocks": None}
    _run_cli_with_payloads(status, config, tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert "Site Name: Unknown" in out
    assert "Number of Powerwalls: 0" in out
    assert json.loads((tmp_path / "config.json").read_text()) == config
