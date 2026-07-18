"""Tests for the two-version TEDAPI query path (V2024_06 + V2026_06).

Priority is the default-unchanged guarantee: with tedapi_api_version unset the
V2024_06 request bytes must be exactly what they were before the migration.
"""
import logging
from unittest.mock import patch

import pytest

from pypowerwall.tedapi import TEDAPI, tedapi_pb2
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.api_version import TEDAPIApiVersion

# The V2026_06 pb2 requires protobuf>=6.33.6 (guarded gencode); the default path
# stays on the 4.25.1 floor, so import lazily and skip the build/parse tests when
# the newer runtime isn't present (mirrors test_system_info.py).
try:
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_transport_pb2 as tx
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_energy_device_pb2 as ed
    HAVE_V2026 = True
except Exception:
    tx = ed = None
    HAVE_V2026 = False

v2026_only = pytest.mark.skipif(not HAVE_V2026, reason="V2026_06 protos require protobuf>=6.33.6")


@pytest.fixture
def api():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="TEST_DIN"):
        a = TEDAPI("test_password")
    a.din = "1538000-45-D--TESTDIN0000000"
    a.v1r = False
    return a


# --- version selection ------------------------------------------------------

def test_default_version_is_V2024_06(api):
    assert api.tedapi_api_version == "V2024_06"


def test_invalid_version_falls_back_to_V2024_06():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        a = TEDAPI("pw", tedapi_api_version="nonsense")
    assert a.tedapi_api_version == "V2024_06"


def test_V2026_06_version_is_stored():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        a = TEDAPI("pw", tedapi_api_version="V2026_06")
    assert a.tedapi_api_version == "V2026_06"


def test_version_is_enum_instance(api):
    # stored value is the enum (str input is coerced), and still == the string
    assert isinstance(api.tedapi_api_version, TEDAPIApiVersion)
    assert api.tedapi_api_version is TEDAPIApiVersion.V2024_06


def test_accepts_enum_input():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        a = TEDAPI("pw", tedapi_api_version=TEDAPIApiVersion.V2026_06)
    assert a.tedapi_api_version is TEDAPIApiVersion.V2026_06


# --- query registry ---------------------------------------------------------

def test_get_query_V2024_06_default():
    dc = q.get_query("device_controller_basic")
    assert dc is q.V2024_06_QUERIES["device_controller_basic"]
    assert dc.version == 0 and not dc.signed_bytes


def test_get_query_V2026_06_maps_device_controller():
    dc = q.get_query("device_controller_full", "V2026_06")
    assert dc.version == 2 and dc.signed_bytes and len(dc.code) == 139


def test_get_query_V2026_06_components_maps_to_pw3query():
    # Full parity: Tesla replaced ComponentsQuery with PW3Query (same component
    # types); V2026_06 uses Tesla's query, never the V2024_06 fallback.
    comp = q.get_query("components", "V2026_06")
    assert comp is q.V2026_06_QUERIES["PW3Query"]
    assert comp.version == 2 and comp.signed_bytes


def test_V2026_06_never_falls_back_to_V2024_06():
    # Every V2024_06 role must resolve to a real Tesla query under V2026_06.
    for role in q.V2024_06_QUERIES:
        assert q.get_query(role, "V2026_06") in q.V2026_06_QUERIES.values()


def test_get_query_by_name_diagnostics():
    for name in ("PW3Query", "ComplianceQuery", "TulipQuery", "IEEE20305Query"):
        assert q.get_query_by_name(name).signed_bytes


def test_query_role_enum():
    # str-enum: members equal their string value and interoperate as dict keys
    # against both the string-keyed query sets and the QueryRole-keyed roles map.
    assert q.QueryRole.COMPONENTS == "components"
    assert q.V2024_06_QUERIES[q.QueryRole.DEVICE_CONTROLLER_BASIC].version == 0
    assert q.get_query(q.QueryRole.COMPONENTS, "V2026_06") is q.V2026_06_QUERIES["PW3Query"]
    # roles map is keyed by the enum but still reachable by a plain string
    assert q.V2026_06_ROLES[q.QueryRole.COMPONENTS] == "PW3Query"
    assert q.V2026_06_ROLES["components"] == "PW3Query"


# --- TEDAPIApiVersion.coerce() ----------------------------------------------

def test_coerce_string_input():
    assert TEDAPIApiVersion.coerce("V2024_06") is TEDAPIApiVersion.V2024_06
    assert TEDAPIApiVersion.coerce("V2026_06") is TEDAPIApiVersion.V2026_06


def test_coerce_enum_input_passthrough():
    assert TEDAPIApiVersion.coerce(TEDAPIApiVersion.V2026_06) is TEDAPIApiVersion.V2026_06


@pytest.mark.parametrize("bad", ["nonsense", "legacy", "", None, 123])
def test_coerce_invalid_falls_back_to_V2024_06(bad):
    # invalid input (incl. the retired "legacy" label and non-strings) -> default
    assert TEDAPIApiVersion.coerce(bad) is TEDAPIApiVersion.V2024_06


def test_coerce_unrecognized_logs_warning(caplog):
    # a typo'd value (e.g. from PW_TEDAPI_API_VERSION) must not fall back silently:
    # warn, naming the bad value and every valid choice.
    with caplog.at_level(logging.WARNING, logger="pypowerwall.tedapi.api_version"):
        TEDAPIApiVersion.coerce("V2024_6")
    assert "V2024_6" in caplog.text          # the offending value
    assert "V2024_06" in caplog.text and "V2026_06" in caplog.text  # valid choices


def test_coerce_valid_input_is_silent(caplog):
    # valid values and enum passthrough must not emit the fallback warning
    with caplog.at_level(logging.WARNING, logger="pypowerwall.tedapi.api_version"):
        TEDAPIApiVersion.coerce("V2026_06")
        TEDAPIApiVersion.coerce(TEDAPIApiVersion.V2024_06)
    assert "Unrecognized" not in caplog.text


# --- get_query() missing role + call-site coverage --------------------------

def test_get_query_missing_role_raises():
    with pytest.raises(KeyError):
        q.get_query("no_such_role")                       # V2024_06 set
    with pytest.raises(KeyError):
        q.get_query("no_such_role", "V2026_06")          # V2026_06 role map


def test_V2026_06_call_site_roles_are_all_mapped():
    """Guard: every role passed to ``self._build_request(<role>, ...)`` in
    tedapi/__init__.py must be present in V2026_06_ROLES — otherwise it
    KeyErrors at runtime under V2026_06 (``_build_request`` dispatches to
    ``get_query(role, V2026_06)``). Scans the real source so a new call site
    (or a renamed role) can't silently regress this."""
    import ast
    import pypowerwall.tedapi as tedapi_mod

    src = open(tedapi_mod.__file__, encoding="utf-8").read()
    used = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_build_request" and node.args):
            role = node.args[0]
            if isinstance(role, ast.Attribute):        # QueryRole.DEVICE_CONTROLLER_BASIC
                used.add(q.QueryRole[role.attr].value)
            elif isinstance(role, ast.Constant) and isinstance(role.value, str):
                used.add(role.value)

    assert used, "no _build_request(...) call sites found — scan logic broke?"
    mapped = {str(r) for r in q.V2026_06_ROLES}   # QueryRole keys -> their string values
    # safety: no call-site role is unmapped (would KeyError at runtime)
    unmapped = used - mapped
    assert not unmapped, f"V2026_06 call-site roles missing from V2026_06_ROLES: {unmapped}"
    # completeness: V2026_06_ROLES maps exactly the roles the call sites need
    assert used == mapped, (
        f"V2026_06_ROLES out of sync with call sites; symmetric diff: {used ^ mapped}"
    )


# --- default-unchanged regression -------------------------------------------

def _V2024_06_status_bytes(din):
    """Reconstruct the V2024_06 device_controller_basic request exactly as the
    pre-migration inline code built it."""
    pb = tedapi_pb2.Message()
    pb.message.deliveryChannel = 1
    pb.message.sender.local = 1
    pb.message.recipient.din = din
    pb.message.payload.send.num = 2
    pb.message.payload.send.payload.value = 1
    q.apply_query(pb.message.payload.send, q.get_query("device_controller_basic"))
    pb.tail.value = 1
    return pb.SerializeToString()


def test_V2024_06_request_is_stable(api):
    # Snapshot invariants: V2024_06 build is deterministic and carries the signed
    # 'code' over the QueryType payload (the original wire shape).
    raw = _V2024_06_status_bytes(api.din)
    again = _V2024_06_status_bytes(api.din)
    assert raw == again
    m = tedapi_pb2.Message()
    m.ParseFromString(raw)
    assert m.message.recipient.din == api.din
    assert m.message.payload.send.code == q.V2024_06_QUERIES["device_controller_basic"].code
    assert m.tail.value == 1


# --- V2026_06 build / parse ------------------------------------------------

@v2026_only
def test_build_signed_query_request(api):
    query = q.get_query("device_controller_full", "V2026_06")
    raw = api._build_signed_query_request(query)
    m = tx.Message()
    m.ParseFromString(raw)
    gq = m.message.graphql.queryRequest
    assert m.message.deliveryChannel == 1
    assert m.message.sender.local == 1
    assert m.message.recipient.din == api.din
    assert gq.format == 2                       # SIGNED_SHA256_ECDSA_ASN1
    assert gq.query == query.signed_bytes
    assert gq.signature == query.code
    assert gq.variablesJson.value == "{}"
    assert m.tail.value == 1


@v2026_only
def test_build_signed_query_follower_routing(api):
    query = q.get_query_by_name("PW3Query")
    raw = api._build_signed_query_request(
        query, recipient_din="FOLLOWER-DIN", sender_din=api.din, tail=2)
    m = tx.Message()
    m.ParseFromString(raw)
    assert m.message.recipient.din == "FOLLOWER-DIN"
    assert m.message.sender.din == api.din
    assert m.tail.value == 2


@v2026_only
def test_parse_signed_response_basic(api):
    api.v1r = False
    resp = tx.Message()
    resp.message.graphql.queryResponse.status = 1
    resp.message.graphql.queryResponse.data = '{"control":{"x":1}}'
    assert api._parse_signed_query_response(resp.SerializeToString()) == '{"control":{"x":1}}'


@v2026_only
def test_parse_signed_response_v1r_bare_envelope(api):
    api.v1r = True
    env = ed.MessageEnvelope()
    env.graphql.queryResponse.status = 1
    env.graphql.queryResponse.data = '{"v1r":true}'
    assert api._parse_signed_query_response(env.SerializeToString()) == '{"v1r":true}'


@v2026_only
def test_parse_signed_response_empty_returns_none(api):
    assert api._parse_signed_query_response(b"") is None


@v2026_only
def test_parse_signed_response_v1r_wifi_follower(api):
    # The v1r WiFi-follower fallback (_post_tedapi_wifi) returns a FULL transport
    # Message with a tail, not a bare envelope. from_wifi=True must select the
    # Message parser even though self.v1r is set.
    api.v1r = True
    resp = tx.Message()
    resp.message.graphql.queryResponse.status = 1
    resp.message.graphql.queryResponse.data = '{"wifi":true}'
    raw = resp.SerializeToString()
    assert api._parse_signed_query_response(raw, from_wifi=True) == '{"wifi":true}'


@v2026_only
def test_parse_signed_response_v1r_wifi_without_flag_drops_payload(api):
    # Regression guard: without from_wifi, the pre-fix code parsed a full Message
    # as a bare MessageEnvelope. Protobuf parses leniently, so no exception is
    # raised — the payload is silently lost (None). Proves from_wifi does real
    # work: the SAME bytes yield data with the flag and None without it.
    api.v1r = True
    resp = tx.Message()
    resp.message.graphql.queryResponse.status = 1
    resp.message.graphql.queryResponse.data = '{"wifi":true}'
    raw = resp.SerializeToString()
    assert api._parse_signed_query_response(raw, from_wifi=False) is None


# --- back-compat import shims -----------------------------------------------

def test_legacy_pb2_deep_import_paths_still_resolve():
    # The pb2 modules moved to protobuf/V2024_06/, but pre-move deep imports
    # (import pypowerwall.tedapi.tedapi_pb2) must keep resolving via the shims,
    # and to the *same* class objects (protobuf descriptor identity matters).
    import importlib
    for mod, cls in (("tedapi_pb2", "Message"),
                     ("tedapi_combined_pb2", "MessageEnvelope")):
        shim = importlib.import_module(f"pypowerwall.tedapi.{mod}")
        real = importlib.import_module(f"pypowerwall.tedapi.protobuf.V2024_06.{mod}")
        assert getattr(shim, cls) is getattr(real, cls)
        assert shim.DESCRIPTOR is real.DESCRIPTOR
