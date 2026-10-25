"""Tests for the strict opt-in signed WiFi-v1r route (PW_LOCAL_FIRST_WIFI).

With the flag, a LAN-failed leader uses signed WiFi-v1r only. The legacy WiFi
TEDAPI path stays available for flag-off users and for followers, but it is
never a read/write rescue for the flagged leader.
"""
import time
from unittest.mock import MagicMock, patch

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r


def _make_tedapi():
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
        ted = TEDAPI(gw_pwd="testpassword")
    ted.gw_ip = "10.42.1.1"
    ted.v1r = True
    ted.v1r_transport = MagicMock()
    ted.wifi_host = "192.168.1.39"
    ted.wifi_v1r_fallback = True
    ted.wifi_v1r_transport = MagicMock()
    ted.wifi_v1r_transport.get_config_v1r.return_value = {"site_info": {}}
    ted.lan_failed = True
    ted.lan_recover_after = time.time() + 3600
    ted.din = "TEST_DIN"
    return ted


def _with_ready(ted):
    ted._wifi_v1r_ready_until = time.monotonic() + 60.0
    return ted


def test_wifi_transport_keeps_lan_auth_defaults():
    with patch("pypowerwall.tedapi.tedapi_v1r.TEDAPIv1r") as transport_cls, \
            patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
        TEDAPI(
            host="10.0.0.1", password="pw", gw_pwd="pw",
            rsa_key_path="key.pem", wifi_host="192.168.91.1",
            v1r=True, wifi_v1r_fallback=True,
        )
    wifi_call = transport_cls.call_args_list[1]
    assert wifi_call.kwargs.get("auto_login", True) is True


def test_default_has_no_wifi_v1r_transport():
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
        ted = TEDAPI(gw_pwd="testpassword")
    assert ted.wifi_v1r_fallback is False
    assert ted.wifi_v1r_transport is None
    assert ted._v1r_write_transport() is ted.v1r_transport
    assert ted._v1r_read_transport() is ted.v1r_transport


def test_read_selector_returns_none_when_requested_transport_missing():
    ted = _make_tedapi()
    ted.wifi_v1r_transport = None
    assert ted._v1r_read_transport() is None


def test_v1r_call_with_no_transport_returns_none():
    ted = _make_tedapi()
    assert ted._v1r_call(None, "post_v1r", b"env", "TEST_DIN") is None


def test_probe_false_without_opt_in():
    ted = _make_tedapi()
    ted.wifi_v1r_fallback = False
    assert ted.wifi_v1r_ready() is False


def test_probe_false_without_din():
    ted = _make_tedapi()
    ted.din = None
    assert ted.wifi_v1r_ready() is False


def test_probe_false_without_lan_failed():
    ted = _make_tedapi()
    ted.lan_failed = False
    assert ted.wifi_v1r_ready() is False


def test_probe_success_sets_readiness():
    ted = _make_tedapi()
    assert ted.wifi_v1r_ready() is True
    assert ted._wifi_v1r_ready_until > time.monotonic()


def test_probe_failure_does_not_set_readiness():
    ted = _make_tedapi()
    ted.wifi_v1r_transport.get_config_v1r.return_value = None
    assert ted.wifi_v1r_ready() is False
    assert ted._wifi_v1r_ready_until == 0.0


def test_write_selector_probes_once_then_uses_wifi():
    ted = _make_tedapi()
    assert ted._v1r_write_transport() is ted.wifi_v1r_transport
    ted.wifi_v1r_transport.get_config_v1r.assert_called_once_with("TEST_DIN")
    ted.wifi_v1r_transport.get_config_v1r.reset_mock()
    assert ted._v1r_write_transport() is ted.wifi_v1r_transport
    ted.wifi_v1r_transport.get_config_v1r.assert_not_called()


def test_write_selector_returns_none_on_probe_failure():
    ted = _make_tedapi()
    ted.wifi_v1r_transport.get_config_v1r.return_value = None
    assert ted._v1r_write_transport() is None
    ted.v1r_transport.write_config_v1r.assert_not_called()


def test_write_config_does_not_dispatch_when_probe_fails():
    ted = _make_tedapi()
    ted.wifi_v1r_transport.get_config_v1r.return_value = None
    assert ted._write_config({"site_info.backup_reserve_percent": 9.75}) is False
    ted.wifi_v1r_transport.write_config_v1r.assert_not_called()
    ted.v1r_transport.write_config_v1r.assert_not_called()


def test_write_selector_requires_lan_failed():
    ted = _with_ready(_make_tedapi())
    ted.lan_failed = False
    assert ted._v1r_write_transport() is ted.v1r_transport
    assert ted._v1r_read_transport() is ted.v1r_transport


def test_write_config_uses_wifi_transport():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.write_config_v1r.return_value = True
    assert ted._write_config({"site_info.backup_reserve_percent": 9.75}) is True
    ted.wifi_v1r_transport.write_config_v1r.assert_called_once_with(
        "TEST_DIN", {"site_info.backup_reserve_percent": 9.75}
    )
    ted.v1r_transport.write_config_v1r.assert_not_called()


def test_islanding_uses_wifi_transport():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.send_island_mode.return_value = {"result": 1}
    assert ted.go_off_grid() == {"result": 1}
    ted.wifi_v1r_transport.send_island_mode.assert_called_once_with(
        "TEST_DIN", mode=6, force=True
    )
    ted.v1r_transport.send_island_mode.assert_not_called()


def test_max_backup_read_uses_wifi_transport():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.send_teg_message.return_value = None
    assert ted.get_backup_events() is None
    ted.wifi_v1r_transport.send_teg_message.assert_called_once()
    ted.v1r_transport.send_teg_message.assert_not_called()


def test_max_backup_cancel_uses_wifi_transport():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.send_teg_message.return_value = None
    assert ted.cancel_max_backup() is False
    ted.wifi_v1r_transport.send_teg_message.assert_called_once()
    ted.v1r_transport.send_teg_message.assert_not_called()


def test_lan_failover_enabled_with_wifi_v1r_only():
    ted = _make_tedapi()
    ted.wifi_session = None
    assert ted._lan_failover_enabled() is True
    ted.wifi_v1r_transport = None
    assert ted._lan_failover_enabled() is False


def test_lan_failover_disabled_with_flag_off_uses_wifi_session():
    ted = _make_tedapi()
    ted.wifi_v1r_fallback = False
    ted.wifi_v1r_transport = None
    ted.wifi_session = MagicMock()
    assert ted._lan_failover_enabled() is True


def test_lan_failover_never_uses_wifi_session_when_flagged():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport = None
    assert ted._lan_failover_enabled() is False


def test_post_tedapi_uses_same_signed_request_on_lan_and_wifi():
    lan = _make_tedapi()
    lan.lan_failed = False
    lan.v1r_transport.post_v1r.return_value = b"inner"
    with patch.object(lan, "_envelope_bytes", return_value=b"env"):
        assert lan._post_tedapi(b"request") == b"inner"

    wifi = _make_tedapi()
    wifi.wifi_v1r_transport.post_v1r.return_value = b"inner"
    with patch.object(wifi, "_envelope_bytes", return_value=b"env"):
        assert wifi._post_tedapi(b"request") == b"inner"

    assert (
        lan.v1r_transport.post_v1r.call_args
        == wifi.wifi_v1r_transport.post_v1r.call_args
    )
    assert lan.v1r_transport.post_v1r.call_args == ((b"env", "TEST_DIN"), {})
    wifi.v1r_transport.post_v1r.assert_not_called()


def test_get_config_uses_same_signed_request_on_lan_and_wifi():
    config = {"site_info": {"backup_reserve_percent": 9.75}, "battery_blocks": []}
    lan = _with_ready(_make_tedapi())
    lan.lan_failed = False
    lan.v1r_transport.get_config_v1r.return_value = config
    assert lan.get_config(force=True) == config

    wifi = _with_ready(_make_tedapi())
    wifi.wifi_v1r_transport.get_config_v1r.return_value = config
    assert wifi.get_config(force=True) == config

    assert (
        lan.v1r_transport.get_config_v1r.call_args
        == wifi.wifi_v1r_transport.get_config_v1r.call_args
    )
    assert lan.v1r_transport.get_config_v1r.call_args == (("TEST_DIN",), {})
    wifi.v1r_transport.get_config_v1r.assert_not_called()


def test_post_tedapi_uses_wifi_v1r_without_wifi_session():
    ted = _make_tedapi()
    ted.wifi_session = None
    ted.wifi_v1r_transport.post_v1r.return_value = b"inner"
    with patch.object(ted, "_envelope_bytes", return_value=b"env"):
        assert ted._post_tedapi(b"request") == b"inner"
    ted.wifi_v1r_transport.post_v1r.assert_called_once_with(b"env", "TEST_DIN")
    ted.v1r_transport.post_v1r.assert_not_called()


def test_post_tedapi_prefers_wifi_v1r_over_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.post_v1r.return_value = b"inner"
    with patch.object(ted, "_post_tedapi_wifi", return_value=b"legacy") as legacy, \
            patch.object(ted, "_envelope_bytes", return_value=b"env"):
        assert ted._post_tedapi(b"request") == b"inner"
    legacy.assert_not_called()
    ted.wifi_v1r_transport.post_v1r.assert_called_once_with(b"env", "TEST_DIN")


def test_post_tedapi_retries_signed_on_next_call_after_failure():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.post_v1r.side_effect = [None, b"inner"]
    with patch.object(ted, "_post_tedapi_wifi", return_value=b"legacy") as legacy, \
            patch.object(ted, "_envelope_bytes", return_value=b"env"):
        assert ted._post_tedapi(b"request") is None
        assert ted._post_tedapi(b"request") == b"inner"
    legacy.assert_not_called()
    ted.v1r_transport.post_v1r.assert_not_called()
    assert ted.wifi_v1r_transport.post_v1r.call_count == 2


def test_post_tedapi_signed_failure_does_not_fallback_to_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.post_v1r.return_value = None
    with patch.object(ted, "_post_tedapi_wifi", return_value=b"legacy") as legacy, \
            patch.object(ted, "_envelope_bytes", return_value=b"env"):
        assert ted._post_tedapi(b"request") is None
    legacy.assert_not_called()
    ted.v1r_transport.post_v1r.assert_not_called()


def test_post_tedapi_without_transport_does_not_fallback_to_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport = None
    with patch.object(ted, "_post_tedapi_wifi", return_value=b"legacy") as legacy:
        assert ted._post_tedapi(b"request") is None
    legacy.assert_not_called()


def test_post_tedapi_flag_off_keeps_legacy_wifi_path():
    ted = _make_tedapi()
    ted.wifi_v1r_fallback = False
    ted.wifi_session = MagicMock()
    msg = MagicMock()
    msg.message.SerializeToString.return_value = b"inner"
    with patch.object(ted, "_post_tedapi_wifi", return_value=b"raw") as legacy, \
            patch.object(ted, "_transport_message", return_value=msg):
        assert ted._post_tedapi(b"request") == b"inner"
    legacy.assert_called_once()
    ted.wifi_v1r_transport.post_v1r.assert_not_called()
    ted.v1r_transport.post_v1r.assert_not_called()


def test_get_config_uses_wifi_v1r_without_wifi_session():
    ted = _with_ready(_make_tedapi())
    ted.wifi_session = None
    ted.wifi_v1r_transport.get_config_v1r.return_value = {
        "site_info": {"backup_reserve_percent": 9.75},
        "battery_blocks": [],
    }
    config = ted.get_config(force=True)
    assert config["site_info"]["backup_reserve_percent"] == 9.75
    ted.wifi_v1r_transport.get_config_v1r.assert_called_once_with("TEST_DIN")
    ted.v1r_transport.get_config_v1r.assert_not_called()


def test_get_config_prefers_wifi_v1r_over_wifi_tedapi():
    ted = _with_ready(_make_tedapi())
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.get_config_v1r.return_value = {
        "site_info": {"backup_reserve_percent": 9.75},
        "battery_blocks": [],
    }
    with patch.object(ted, "_post_tedapi_wifi", return_value={}) as legacy:
        config = ted.get_config(force=True)
    assert config["site_info"]["backup_reserve_percent"] == 9.75
    legacy.assert_not_called()
    ted.wifi_v1r_transport.get_config_v1r.assert_called_once_with("TEST_DIN")


def test_get_config_signed_failure_does_not_fallback_to_wifi_tedapi():
    ted = _with_ready(_make_tedapi())
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.get_config_v1r.return_value = None
    with patch.object(ted, "_post_tedapi_wifi", return_value={}) as legacy:
        assert ted.get_config(force=True) is None
    legacy.assert_not_called()


def test_get_config_without_transport_does_not_fallback_to_wifi_tedapi():
    ted = _with_ready(_make_tedapi())
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport = None
    with patch.object(ted, "_post_tedapi_wifi", return_value={}) as legacy:
        assert ted.get_config(force=True) is None
    legacy.assert_not_called()


def test_get_config_flag_off_keeps_legacy_wifi_path():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_fallback = False
    ted.wifi_session = MagicMock()
    with patch.object(ted, "_post_tedapi_wifi", return_value=b"raw") as legacy, \
            patch.object(ted, "_parse_legacy_response", return_value={}), \
            patch.object(ted, "_decode_json", return_value={"site_info": {}}):
        config = ted.get_config(force=True)
    assert config == {"site_info": {}, "battery_blocks": []}
    legacy.assert_called_once()
    ted.wifi_v1r_transport.get_config_v1r.assert_not_called()
    ted.v1r_transport.get_config_v1r.assert_not_called()


def test_cold_failover_uses_wifi_v1r_login_without_wifi_session():
    ted = _make_tedapi()
    ted.v1r_transport.login.return_value = False
    ted.wifi_session = None
    ted.wifi_v1r_transport.login.return_value = True
    ted.wifi_v1r_transport.get_din.return_value = "WIFI_V1R_DIN"
    assert ted._v1r_cold_failover() == "WIFI_V1R_DIN"
    assert ted.din == "WIFI_V1R_DIN"
    assert ted.lan_failed is True


def test_cold_failover_prefers_wifi_v1r_over_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.login.return_value = True
    ted.wifi_v1r_transport.get_din.return_value = "WIFI_V1R_DIN"
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted._v1r_cold_failover() == "WIFI_V1R_DIN"
    legacy.assert_not_called()
    assert ted.din == "WIFI_V1R_DIN"


def test_cold_failover_signed_failure_does_not_fallback_to_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.login.return_value = False
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted._v1r_cold_failover() is None
    legacy.assert_not_called()
    assert ted.din == "TEST_DIN"


def test_cold_failover_without_transport_does_not_fallback_to_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport = None
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted._v1r_cold_failover() is None
    legacy.assert_not_called()


def test_cold_failover_flag_off_keeps_legacy_wifi_path():
    ted = _make_tedapi()
    ted.wifi_v1r_fallback = False
    ted.wifi_session = MagicMock()
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted._v1r_cold_failover() == "LEGACY_DIN"
    legacy.assert_called_once()
    ted.wifi_v1r_transport.login.assert_not_called()


def test_get_din_strict_uses_wifi_v1r_directly():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.login.return_value = True
    ted.wifi_v1r_transport.get_din.return_value = "WIFI_V1R_DIN"
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted.get_din(force=True) == "WIFI_V1R_DIN"
    legacy.assert_not_called()
    ted.wifi_v1r_transport.login.assert_called_once()
    ted.wifi_v1r_transport.get_din.assert_called_once()


def test_get_din_strict_does_not_fallback_to_wifi_tedapi():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport = None
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted.get_din(force=True) is None
    legacy.assert_not_called()


def test_get_din_flag_off_keeps_legacy_wifi_path():
    ted = _make_tedapi()
    ted.wifi_v1r_fallback = False
    ted.wifi_session = MagicMock()
    with patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted.get_din(force=True) == "LEGACY_DIN"
    legacy.assert_called_once()
    ted.wifi_v1r_transport.login.assert_not_called()


def test_close_session_closes_both_v1r_sessions():
    ted = _make_tedapi()
    ted.v1r_transport.session = MagicMock()
    ted.wifi_v1r_transport.session = MagicMock()
    ted.close_session()
    ted.v1r_transport.session.close.assert_called_once()
    ted.wifi_v1r_transport.session.close.assert_called_once()


def test_auto_login_disabled_does_not_relogin_on_post():
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.host = "192.168.1.39"
    transport.auto_login = False
    transport.session = MagicMock()
    response = MagicMock()
    response.status_code = 401
    transport.session.post.return_value = response
    transport.login = MagicMock(return_value=True)
    with patch.object(transport, "_signed_payload", return_value=b"signed"):
        assert transport.post_v1r(b"env", "TEST_DIN") is None
    transport.login.assert_not_called()


def test_auto_login_disabled_does_not_relogin_on_api_get():
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.host = "192.168.1.39"
    transport.auto_login = False
    transport.token = None
    transport.session = MagicMock()
    response = MagicMock()
    response.status_code = 401
    transport.session.get.return_value = response
    transport.login = MagicMock(return_value=True)
    assert transport.api_get("/api/operation") is None
    transport.login.assert_not_called()
