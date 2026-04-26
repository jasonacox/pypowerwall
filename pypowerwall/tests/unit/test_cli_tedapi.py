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
    )