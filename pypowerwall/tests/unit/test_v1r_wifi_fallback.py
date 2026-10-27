"""Tests for the strict opt-in signed WiFi-v1r route (wifi_v1r_fallback).

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
    ted.wifi_v1r_transport.token = None
    ted.wifi_v1r_transport.get_config_v1r.return_value = {"site_info": {}}
    ted.lan_failed = True
    ted.lan_recover_after = time.time() + 3600
    ted.din = "TEST_DIN"
    return ted


def _with_ready(ted):
    ted._wifi_v1r_ready_until = time.monotonic() + 60.0
    return ted


def test_wifi_transport_reuses_lan_transport_args():
    with patch("pypowerwall.tedapi.tedapi_v1r.TEDAPIv1r") as transport_cls, \
            patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
        TEDAPI(
            host="10.0.0.1", password="pw", gw_pwd="pw",
            rsa_key_path="key.pem", wifi_host="192.168.91.1",
            v1r=True, wifi_v1r_fallback=True,
        )
    lan_call, wifi_call = transport_cls.call_args_list
    for key in ("password", "rsa_key_path", "timeout", "poolmaxsize"):
        assert wifi_call.kwargs[key] == lan_call.kwargs[key]
    assert wifi_call.kwargs["host"] == "192.168.91.1"
    assert "auto_login" not in wifi_call.kwargs


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


def test_failed_probe_revokes_earlier_readiness():
    """A failed probe must not leave an earlier success's write window open."""
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.get_config_v1r.return_value = None
    assert ted.wifi_v1r_ready() is False
    assert ted._wifi_v1r_ready_until == 0.0
    assert ted._v1r_write_transport() is None  # probes again, fails, no write


def test_probe_exception_revokes_earlier_readiness():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.get_config_v1r.side_effect = RuntimeError("down")
    assert ted.wifi_v1r_ready() is False
    assert ted._wifi_v1r_ready_until == 0.0


def test_failed_probe_clears_readiness_set_by_concurrent_probe():
    """Probe B succeeds while probe A waits; A then fails. The last probe to
    finish decides, so writes must not stay enabled."""
    ted = _make_tedapi()

    def concurrent_success_then_fail(*_args):
        ted._wifi_v1r_ready_until = time.monotonic() + 60.0  # probe B finished
        return None                                         # probe A fails

    ted.wifi_v1r_transport.get_config_v1r.side_effect = concurrent_success_then_fail
    assert ted.wifi_v1r_ready() is False
    assert ted._wifi_v1r_ready_until == 0.0

    def concurrent_success_then_raise(*_args):
        ted._wifi_v1r_ready_until = time.monotonic() + 60.0
        raise RuntimeError("down")

    ted.wifi_v1r_transport.get_config_v1r.side_effect = concurrent_success_then_raise
    assert ted.wifi_v1r_ready() is False
    assert ted._wifi_v1r_ready_until == 0.0


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


def test_reconnect_grid_uses_wifi_transport():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.send_island_mode.return_value = {"result": 1}
    assert ted.reconnect_grid() == {"result": 1}
    ted.wifi_v1r_transport.send_island_mode.assert_called_once_with(
        "TEST_DIN", mode=1
    )
    ted.v1r_transport.send_island_mode.assert_not_called()


def test_schedule_max_backup_uses_wifi_transport():
    ted = _with_ready(_make_tedapi())
    ted.cancel_max_backup = MagicMock(return_value=True)
    response = MagicMock()
    response.HasField.side_effect = lambda field: field == "teg"
    response.teg.HasField.return_value = True
    ted.wifi_v1r_transport.send_teg_message.return_value = response
    assert ted.schedule_max_backup(60) is True
    ted.wifi_v1r_transport.send_teg_message.assert_called_once()
    ted.v1r_transport.send_teg_message.assert_not_called()


def test_islanding_uses_same_transport_args_on_lan_and_wifi():
    lan = _with_ready(_make_tedapi())
    lan.lan_failed = False
    wifi = _with_ready(_make_tedapi())
    lan.v1r_transport.send_island_mode.return_value = {"result": 1}
    wifi.wifi_v1r_transport.send_island_mode.return_value = {"result": 1}
    assert lan.go_off_grid() == {"result": 1}
    assert wifi.go_off_grid() == {"result": 1}
    assert (
        lan.v1r_transport.send_island_mode.call_args
        == wifi.wifi_v1r_transport.send_island_mode.call_args
    )


def test_write_transport_error_does_not_fallback_to_lan():
    ted = _with_ready(_make_tedapi())
    ted.wifi_v1r_transport.write_config_v1r.side_effect = TimeoutError("timeout")
    assert ted._write_config({"site_info.backup_reserve_percent": 9.75}) is False
    ted.wifi_v1r_transport.write_config_v1r.assert_called_once_with(
        "TEST_DIN", {"site_info.backup_reserve_percent": 9.75}
    )
    ted.v1r_transport.write_config_v1r.assert_not_called()


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


def test_get_din_reuses_existing_wifi_v1r_token():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.wifi_v1r_transport.token = "cached-token"
    ted.wifi_v1r_transport.get_din.return_value = "WIFI_V1R_DIN"
    assert ted.get_din(force=True) == "WIFI_V1R_DIN"
    ted.wifi_v1r_transport.login.assert_not_called()


def test_get_din_relogs_in_when_cached_token_is_rejected():
    ted = _make_tedapi()
    ted.wifi_v1r_transport.token = "expired-token"
    ted.wifi_v1r_transport.login.return_value = True
    ted.wifi_v1r_transport.get_din.side_effect = [None, "WIFI_V1R_DIN"]
    assert ted.get_din(force=True) == "WIFI_V1R_DIN"
    ted.wifi_v1r_transport.login.assert_called_once()


def test_cold_failover_relogs_in_when_cached_token_is_rejected():
    """A token left from an earlier attempt may have expired; cold failover
    must log in again rather than retrying it forever."""
    ted = _make_tedapi()
    ted.din = None
    ted.wifi_session = None
    ted.wifi_v1r_transport.token = "expired-token"
    ted.wifi_v1r_transport.login.return_value = True
    ted.wifi_v1r_transport.get_din.side_effect = [None, "WIFI_V1R_DIN"]
    assert ted._v1r_cold_failover() == "WIFI_V1R_DIN"
    ted.wifi_v1r_transport.login.assert_called_once()


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


def _auth_transport(token="old-token"):
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    transport.host = "192.168.1.39"
    transport.timeout = 5
    transport.token = token
    transport.session = MagicMock()
    return transport


def test_auto_login_relogins_on_403_api_get():
    transport = _auth_transport()
    forbidden = MagicMock()
    forbidden.status_code = 403
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"ok": True}
    transport.session.get.side_effect = [forbidden, ok]

    def relogin():
        transport.token = "new-token"
        return True

    transport.login = MagicMock(side_effect=relogin)
    assert transport.api_get("/api/meters/aggregates") == {"ok": True}
    transport.login.assert_called_once()
    assert transport.session.get.call_count == 2
    assert transport.session.get.call_args.kwargs["headers"]["Authorization"] == (
        "Bearer new-token"
    )


def test_auto_login_relogins_on_403_post():
    transport = _auth_transport(token=None)
    forbidden = MagicMock()
    forbidden.status_code = 403
    failed_retry = MagicMock()
    failed_retry.status_code = 500
    transport.session.post.side_effect = [forbidden, failed_retry]
    transport.login = MagicMock(return_value=True)
    with patch.object(transport, "_signed_payload", return_value=b"signed"):
        assert transport.post_v1r(b"env", "TEST_DIN") is None
    transport.login.assert_called_once()
    assert transport.session.post.call_count == 2


# --- LAN recovers between the lan_failed check and route selection ---
# Another thread can clear lan_failed after the outer check; _wifi_v1r_requested()
# then returns False. The opted-in request must stay on a signed transport (the
# LAN one now), never legacy Wi-Fi TEDAPI.

def _recovered_mid_call(ted):
    return patch.object(ted, "_wifi_v1r_requested", return_value=False)


def test_get_din_lan_recovery_mid_call_stays_signed():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.v1r_transport.get_din.return_value = "LAN_DIN"
    with _recovered_mid_call(ted), \
            patch.object(ted, "_fetch_wifi_din", return_value="LEGACY_DIN") as legacy:
        assert ted.get_din(force=True) == "LAN_DIN"
    legacy.assert_not_called()


def test_get_config_lan_recovery_mid_call_stays_signed():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.v1r_transport.get_config_v1r.return_value = {"site_info": {}}
    with _recovered_mid_call(ted), \
            patch.object(ted, "_post_tedapi_wifi", return_value={}) as legacy:
        assert ted.get_config(force=True) == {"site_info": {}, "battery_blocks": []}
    legacy.assert_not_called()
    ted.v1r_transport.get_config_v1r.assert_called_once()


def test_post_tedapi_lan_recovery_mid_call_stays_signed():
    ted = _make_tedapi()
    ted.wifi_session = MagicMock()
    ted.v1r_transport.post_v1r.return_value = b"lan"
    with _recovered_mid_call(ted), \
            patch.object(ted, "_post_tedapi_wifi", return_value=b"legacy") as legacy, \
            patch.object(ted, "_envelope_bytes", return_value=b"env"):
        assert ted._post_tedapi(b"request") == b"lan"
    legacy.assert_not_called()


# --- Native /api/* reads (get_native_api) ---
# The flagged, LAN-failed leader reads native endpoints through the selected
# signed transport's api_get() only: no customer-session host loop, so a
# failed WiFi read never retries the dead LAN.

AGGREGATES = {s: {"instant_power": 0} for s in ("site", "battery", "load", "solar")}


def _native_tedapi():
    ted = _make_tedapi()
    ted.wifi_v1r_transport.token = "wifi-token"
    ted.wifi_v1r_transport.api_get.return_value = {"ok": 1}
    ted.api_session = MagicMock()
    return ted


def test_native_read_uses_wifi_v1r_api_get():
    ted = _native_tedapi()
    with patch.object(ted, "_native_get") as legacy:
        assert ted.get_native_api("/api/meters/aggregates") == {"ok": 1}
    ted.wifi_v1r_transport.api_get.assert_called_once_with("/api/meters/aggregates")
    ted.wifi_v1r_transport.login.assert_not_called()  # token reused
    ted.v1r_transport.api_get.assert_not_called()
    legacy.assert_not_called()


def test_native_read_signed_failure_does_not_retry_lan():
    ted = _native_tedapi()
    ted.wifi_v1r_transport.api_get.return_value = None
    with patch.object(ted, "_native_get") as legacy:
        assert ted.get_native_api("/api/meters/aggregates") is None
    ted.wifi_v1r_transport.api_get.assert_called_once()
    ted.v1r_transport.api_get.assert_not_called()
    legacy.assert_not_called()
    ted.api_session.get.assert_not_called()
    ted.api_session.post.assert_not_called()


def test_native_read_logs_in_when_wifi_v1r_has_no_token():
    ted = _native_tedapi()
    ted.wifi_v1r_transport.token = None
    ted.wifi_v1r_transport.login.return_value = True
    assert ted.get_native_api("/api/meters/aggregates") == {"ok": 1}
    ted.wifi_v1r_transport.login.assert_called_once()
    ted.wifi_v1r_transport.api_get.assert_called_once()


def test_native_read_failed_login_returns_none():
    ted = _native_tedapi()
    ted.wifi_v1r_transport.token = None
    ted.wifi_v1r_transport.login.return_value = False
    with patch.object(ted, "_native_get") as legacy:
        assert ted.get_native_api("/api/meters/aggregates") is None
    ted.wifi_v1r_transport.api_get.assert_not_called()
    legacy.assert_not_called()


def test_native_read_without_transport_does_not_fallback():
    ted = _native_tedapi()
    ted.wifi_v1r_transport = None
    with patch.object(ted, "_native_get") as legacy:
        assert ted.get_native_api("/api/meters/aggregates") is None
    ted.v1r_transport.api_get.assert_not_called()
    legacy.assert_not_called()


def test_native_read_lan_recovery_mid_call_stays_signed():
    ted = _native_tedapi()
    ted.v1r_transport.token = "lan-token"
    ted.v1r_transport.api_get.return_value = {"lan": 1}
    with patch.object(ted, "_wifi_v1r_requested", side_effect=[True, False]), \
            patch.object(ted, "_native_get") as legacy:
        assert ted.get_native_api("/api/meters/aggregates") == {"lan": 1}
    ted.wifi_v1r_transport.api_get.assert_not_called()
    legacy.assert_not_called()


def test_native_meters_aggregates_uses_wifi_v1r():
    ted = _native_tedapi()
    ted.wifi_v1r_transport.api_get.return_value = AGGREGATES
    with patch.object(ted, "_native_get") as legacy:
        assert ted.get_native_meters_aggregates(force=True) == AGGREGATES
    legacy.assert_not_called()


def test_native_read_signed_wire_calls_on_wifi_host():
    """Real TEDAPIv1r, mocked at its HTTP session: one login and one Bearer
    GET, both to wifi_host, and nothing to the LAN or the customer session."""
    ted = _native_tedapi()
    transport = _auth_transport(token=None)
    transport.password = "pw"
    ted.wifi_v1r_transport = transport
    login = MagicMock(status_code=200)
    login.json.return_value = {"token": "wifi-token"}
    ok = MagicMock(status_code=200)
    ok.json.return_value = AGGREGATES
    transport.session.post.return_value = login
    transport.session.get.return_value = ok
    assert ted.get_native_api("/api/meters/aggregates") == AGGREGATES
    assert transport.session.post.call_args.args[0] == "https://192.168.1.39/api/login/Basic"
    get = transport.session.get.call_args
    assert get.args[0] == "https://192.168.1.39/api/meters/aggregates"
    assert get.kwargs["headers"]["Authorization"] == "Bearer wifi-token"
    ted.v1r_transport.api_get.assert_not_called()
    ted.api_session.get.assert_not_called()
    ted.api_session.post.assert_not_called()


def _legacy_native_hosts(ted):
    calls = []
    with patch.object(ted, "_native_get", side_effect=lambda h, p: calls.append(h)):
        assert ted.get_native_api("/api/x") is None
    return calls


def test_native_read_flag_off_keeps_legacy_host_loop():
    ted = _native_tedapi()
    ted.wifi_v1r_fallback = False
    assert _legacy_native_hosts(ted) == ["192.168.1.39", "10.42.1.1"]
    ted.wifi_v1r_transport.api_get.assert_not_called()
    ted.v1r_transport.api_get.assert_not_called()


def test_native_read_flag_on_lan_healthy_keeps_legacy_host_loop():
    ted = _native_tedapi()
    ted.lan_failed = False
    assert _legacy_native_hosts(ted) == ["10.42.1.1", "192.168.1.39"]
    ted.wifi_v1r_transport.api_get.assert_not_called()


def test_native_read_flag_on_failover_off_keeps_lan_only():
    ted = _native_tedapi()
    ted.failover = False
    assert _legacy_native_hosts(ted) == ["10.42.1.1"]
    ted.wifi_v1r_transport.api_get.assert_not_called()
