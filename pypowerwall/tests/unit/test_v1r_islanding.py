"""Non-actuating wire-format tests for the signed v1r islanding command."""

from unittest.mock import MagicMock, call

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r


def _response_with_result(result: int) -> bytes:
    """Build a legacy TEG response in MessageEnvelope field 5."""
    teg_response = b"\x22\x02\x08" + bytes([result])
    return b"\x2a" + bytes([len(teg_response)]) + teg_response


def test_send_island_mode_preserves_legacy_off_grid_message(monkeypatch):
    """Mode 6/force is encoded as Tesla's legacy TEG request field 3."""
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    captured = {}

    def fake_post(payload, din):
        captured["payload"] = payload
        captured["din"] = din
        return _response_with_result(7)

    monkeypatch.setattr(transport, "post_v1r", fake_post)

    result = transport.send_island_mode("TEST_DIN", mode=6, force=True)

    assert captured["din"] == "TEST_DIN"
    assert captured["payload"] == (
        b"\x08\x02\x12\x02\x20\x01\x1a\x0a\x0a\x08TEST_DIN"
        b"\x2a\x06\x1a\x04\x08\x06\x10\x01"
    )
    assert result == {"mode": 6, "force": True, "result": 7}


def test_send_island_mode_encodes_reconnect_without_force(monkeypatch):
    """Mode 1 reconnect omits the false force field."""
    transport = TEDAPIv1r.__new__(TEDAPIv1r)
    captured = {}

    def fake_post(payload, _din):
        captured["payload"] = payload
        return _response_with_result(0)

    monkeypatch.setattr(transport, "post_v1r", fake_post)

    result = transport.send_island_mode("TEST_DIN", mode=1)

    assert captured["payload"].endswith(b"\x2a\x04\x1a\x02\x08\x01")
    assert result == {"mode": 1, "force": False, "result": 0}


def test_tedapi_routes_islanding_calls_to_v1r_transport():
    """The TEDAPI backend sends both public islanding operations through v1r."""
    tedapi = TEDAPI.__new__(TEDAPI)
    tedapi.v1r = True
    tedapi.v1r_transport = MagicMock()
    tedapi.din = "TEST_DIN"
    tedapi.v1r_transport.send_island_mode.side_effect = [
        {"mode": 6, "force": True, "result": 0},
        {"mode": 1, "force": False, "result": 0},
    ]

    assert tedapi.go_off_grid() == {"mode": 6, "force": True, "result": 0}
    assert tedapi.reconnect_grid() == {"mode": 1, "force": False, "result": 0}
    assert tedapi.v1r_transport.send_island_mode.call_args_list == [
        call("TEST_DIN", mode=6, force=True),
        call("TEST_DIN", mode=1),
    ]
