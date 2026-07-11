"""Offline round-trip tests for the firmware/system-info path.

These exercise TEDAPI._get_system_info / _parse_system_info against the real
generated protobufs (no gateway), guarding the field paths the code depends on so
a protobuf regen can't silently break them. The V2026_06 protos require
protobuf>=6.33.6, so those tests skip on an older runtime.
"""
import json
from unittest.mock import patch

import pytest

from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi.api_version import TEDAPIApiVersion
from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_pb2
from pypowerwall.tedapi.system_info import SystemInfo, RadioDevice

try:
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_transport_pb2 as _tx  # noqa
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_energy_device_pb2 as _ed  # noqa
    HAVE_V2026 = True
except Exception:
    HAVE_V2026 = False

v2026_only = pytest.mark.skipif(not HAVE_V2026, reason="V2026_06 protos require protobuf>=6.33.6")

DIN = "1538000-45-D--GF225311003KW7"
VERSION = "26.11.1 abcd1234"
GITHASH = b"abcd1234"          # ASCII git short-hash (bytes field)
PART = "1538000-45-D"
SERIAL = "GF225311003KW7"


def _make_api(api_version, v1r):
    # Patch connect() so construction doesn't reach the network (mirrors test_init).
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
        api = TEDAPI("test_password", pwcacheexpire=50)
    api.din = DIN
    api.v1r = v1r
    api.tedapi_api_version = api_version
    return api


def _v2026_response(*, v1r):
    """Synthesize a CommonAPIGetSystemInfoResponse in the transport the code expects:
    basic -> full transport Message (with tail); v1r -> bare energy_device envelope."""
    env = _ed.MessageEnvelope()
    info = env.common.getSystemInfoResponse
    info.firmwareVersion.version = VERSION
    info.firmwareVersion.githash = GITHASH
    info.din = DIN
    info.deviceId.partNumber = PART
    info.deviceId.serialNumber = SERIAL
    info.deviceType = 6
    info.systemUpdate.updateStatus = 2
    info.installedFirmwareSignature = b"\x01\x02\x03\x04"
    info.offlineFirmwareSignature = b"\x05\x06"
    rl = info.complianceInformation.radioLegalInformation.add()
    rl.manufacturer.value = "Quectel"
    rl.model.value = "EG25-G"
    rl.fccId.value = "XMR201903EG25G"
    rl.icId.value = "10224A-201903EG25G"
    if v1r:
        return env.SerializeToString()
    m = _tx.Message()
    m.message.CopyFrom(env)
    m.tail.value = 1
    return m.SerializeToString()


@v2026_only
@pytest.mark.parametrize("v1r", [False, True])
def test_get_system_info_v2026_round_trip(v1r):
    api = _make_api(TEDAPIApiVersion.V2026_06, v1r=v1r)
    with patch.object(api, "_post_tedapi", return_value=_v2026_response(v1r=v1r)):
        info = api._get_system_info()
    assert isinstance(info, SystemInfo)
    assert info.version == VERSION
    assert info.githash == "abcd1234"          # decoded at parse (GITHASH = b"abcd1234")
    assert info.din == DIN
    assert info.gateway_part_number == PART and info.gateway_serial_number == SERIAL
    # the 5 fields the parser used to drop / hardcode empty
    assert info.device_type == 6
    assert info.system_update.get("updateStatus") == 2
    assert info.installed_firmware_signature == "01020304"   # bytes -> hex
    assert info.offline_firmware_signature == "0506"
    # radioLegalInformation mapped to the RadioDevice model (was hardcoded [])
    assert info.wireless == [RadioDevice("Quectel", "EG25-G",
                                         "XMR201903EG25G", "10224A-201903EG25G")]
    # the full details payload must still serialize
    json.dumps(info.to_details_dict())


@v2026_only
def test_get_system_info_v2026_request_uses_common_arm():
    """The build side must target the `common.getSystemInfoRequest` envelope arm
    (NOT graphql, NOT the removed legacy `firmware` arm) and address our DIN."""
    api = _make_api(TEDAPIApiVersion.V2026_06, v1r=False)
    with patch.object(api, "_post_tedapi", return_value=_v2026_response(v1r=False)) as post:
        api._get_system_info()
    sent = _tx.Message()
    sent.ParseFromString(post.call_args.args[0])
    assert sent.message.WhichOneof("payload") == "common"
    assert sent.message.common.HasField("getSystemInfoRequest")
    assert sent.message.recipient.din == DIN


@v2026_only
def test_get_system_info_returns_none_when_gateway_silent():
    api = _make_api(TEDAPIApiVersion.V2026_06, v1r=False)
    with patch.object(api, "_post_tedapi", return_value=None):
        assert api._get_system_info() is None


def _legacy_response(populate, *, v1r):
    """Serialize a legacy firmware.system response in the transport the parser
    expects: v1r -> bare MessageEnvelope; basic -> Message with a tail. `populate`
    fills in the firmware.system message (parallels _v2026_response's v1r handling)."""
    if v1r:
        env = tedapi_pb2.MessageEnvelope()
        populate(env.firmware.system)
        return env.SerializeToString()
    msg = tedapi_pb2.Message()
    populate(msg.message.firmware.system)
    msg.tail.value = 1
    return msg.SerializeToString()


@pytest.mark.parametrize("v1r", [False, True])
def test_get_system_info_legacy_round_trip_is_json_safe(v1r):
    """Legacy (V2024_06) details payload must be JSON-safe and emit the same field
    set as V2026, with the opaque fields surfaced under Tesla's real names
    (`systemUpdate`/`deviceType`). Covers both transports (basic Message + v1r bare
    envelope)."""
    def populate(s):
        s.version.text = VERSION
        s.version.githash = GITHASH
        s.din = DIN
        s.gateway.partNumber = PART
        s.gateway.serialNumber = SERIAL
        s.systemUpdate.updateStatus = 42
        s.deviceType = 7
        s.installedFirmwareSignature = b"\x01\x02\x03\x04"
        s.offlineFirmwareSignature = b"\x05\x06"

    api = _make_api(TEDAPIApiVersion.V2024_06, v1r=v1r)
    with patch.object(api, "_post_tedapi", return_value=_legacy_response(populate, v1r=v1r)):
        info = api._get_system_info()

    assert info.version == VERSION
    # legacy opaque fields surfaced under Tesla's real names (parity with V2026)
    assert info.device_type == 7                        # was `six`
    assert info.system_update == {"updateStatus": 42}   # was `five`; five.d == updateStatus
    # fields 8/9 now surfaced, under the same keys V2026 uses (bytes -> hex)
    assert info.installed_firmware_signature == "01020304"
    assert info.offline_firmware_signature == "0506"
    json.dumps(info.to_details_dict())                  # must not raise


@pytest.mark.parametrize("v1r", [False, True])
def test_get_system_info_legacy_recovers_full_systemupdate(v1r):
    """The legacy proto now models the full SystemUpdate directly (was the truncated
    FirmwareFive{d}), so a mid-update gateway reports the complete update state, not
    just updateStatus. (Nested serverStagedVersion uses the legacy FirmwareVersion,
    whose field is `text`, vs V2026's `version`.)"""
    def populate(s):
        s.version.text = VERSION
        s.din = DIN
        su = s.systemUpdate
        su.updateStatus = 2
        su.totalBytes = 987654321
        su.isSideloading = True
        su.serverStagedVersion.text = "26.12.0"

    api = _make_api(TEDAPIApiVersion.V2024_06, v1r=v1r)
    with patch.object(api, "_post_tedapi", return_value=_legacy_response(populate, v1r=v1r)):
        info = api._get_system_info()

    assert info.system_update == {
        "updateStatus": 2,
        "totalBytes": "987654321",             # MessageToDict renders uint64 as str
        "isSideloading": True,
        "serverStagedVersion": {"text": "26.12.0"},
    }
    json.dumps(info.to_details_dict())   # still serializes


def test_to_details_dict_shape_and_json_safe():
    """SystemInfo.to_details_dict renders the stable {"system": {...}} payload,
    JSON-safe, with status enums rendered as their string names."""
    info = SystemInfo(
        version=VERSION, githash="abcd1234", din=DIN,
        gateway_part_number=PART, gateway_serial_number=SERIAL,
        device_type=4, system_update={"updateStatus": 1},
        installed_firmware_signature="deadbeef", offline_firmware_signature="cafe",
        wireless=[RadioDevice("Quectel", "EG21", "XMR...", "10224A-...")])
    d = info.to_details_dict()["system"]
    json.dumps(d)   # must not raise
    assert d["version"] == {"text": VERSION, "githash": "abcd1234"}
    # status enums resolved to their string meaning (raw ints stay on the model)
    assert d["deviceType"] == "DEVICE_TYPE_SITECONTROLLER"
    assert d["systemUpdate"]["updateStatus"] == "UPDATE_STATUS_IDLE"
    assert info.device_type == 4 and info.device_type_name == "DEVICE_TYPE_SITECONTROLLER"
    assert d["installedFirmwareSignature"] == "deadbeef"
    assert d["wireless"] == {"device": [{"company": "Quectel", "model": "EG21",
                                         "fcc_id": "XMR...", "ic": "10224A-..."}]}


def test_enum_label_and_resolve_system_update():
    from pypowerwall.tedapi.enums import (
        DeviceType, UpdateStatus, label, resolve_system_update)

    assert label(DeviceType, 4) == "DEVICE_TYPE_SITECONTROLLER"
    assert label(UpdateStatus, 1) == "UPDATE_STATUS_IDLE"
    assert label(DeviceType, 99) == "UNKNOWN (99)"          # unseen value -> no crash
    # only the known status fields are resolved; others pass through untouched
    su = resolve_system_update(
        {"updateStatus": 2, "handshakeResult": 1, "lastUpdateResult": 2, "totalBytes": "500"})
    assert su == {"updateStatus": "UPDATE_STATUS_DOWNLOADING",
                  "handshakeResult": "UPDATE_HANDSHAKE_RESULT_UNDERWAY",
                  "lastUpdateResult": "LAST_UPDATE_RESULT_SUCCEEDED",
                  "totalBytes": "500"}
    assert resolve_system_update({}) == {}


def test_decode_githash_binary_falls_back_to_hex():
    from pypowerwall.tedapi.system_info import decode_githash
    assert decode_githash(b"\xde\xad\xbe\xef") == "deadbeef"
    assert decode_githash(b"abcd1234") == "abcd1234"
    assert decode_githash("already-str") == "already-str"
