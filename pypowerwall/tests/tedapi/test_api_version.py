"""Tests for the two-version TEDAPI query path (june_2024 + june_2026).

Priority is the default-unchanged guarantee: with tedapi_api_version unset the
june_2024 request bytes must be exactly what they were before the migration.
"""
from unittest.mock import patch

import pytest

from pypowerwall.tedapi import TEDAPI, tedapi_pb2
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi.api_version import TEDAPIApiVersion
from pypowerwall.tedapi.protobuf.june_2026 import tedapi_v2_transport_pb2 as tx
from pypowerwall.tedapi.protobuf.june_2026 import tedapi_v2_energy_device_pb2 as ed


@pytest.fixture
def api():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="TEST_DIN"):
        a = TEDAPI("test_password")
    a.din = "1538000-45-D--TESTDIN0000000"
    a.v1r = False
    return a


# --- version selection ------------------------------------------------------

def test_default_version_is_june_2024(api):
    assert api.tedapi_api_version == "june_2024"


def test_invalid_version_falls_back_to_june_2024():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        a = TEDAPI("pw", tedapi_api_version="nonsense")
    assert a.tedapi_api_version == "june_2024"


def test_june_2026_version_is_stored():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        a = TEDAPI("pw", tedapi_api_version="june_2026")
    assert a.tedapi_api_version == "june_2026"


def test_version_is_enum_instance(api):
    # stored value is the enum (str input is coerced), and still == the string
    assert isinstance(api.tedapi_api_version, TEDAPIApiVersion)
    assert api.tedapi_api_version is TEDAPIApiVersion.JUNE_2024


def test_accepts_enum_input():
    with patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        a = TEDAPI("pw", tedapi_api_version=TEDAPIApiVersion.JUNE_2026)
    assert a.tedapi_api_version is TEDAPIApiVersion.JUNE_2026


# --- query registry ---------------------------------------------------------

def test_get_query_june_2024_default():
    dc = q.get_query("device_controller_basic")
    assert dc is q.JUNE_2024_QUERIES["device_controller_basic"]
    assert dc.version == 0 and not dc.signed_bytes


def test_get_query_june_2026_maps_device_controller():
    dc = q.get_query("device_controller_full", "june_2026")
    assert dc.version == 2 and dc.signed_bytes and len(dc.code) == 139


def test_get_query_june_2026_components_maps_to_pw3query():
    # Full parity: Tesla replaced ComponentsQuery with PW3Query (same component
    # types); june_2026 uses Tesla's query, never the june_2024 fallback.
    comp = q.get_query("components", "june_2026")
    assert comp is q.JUNE_2026_QUERIES["PW3Query"]
    assert comp.version == 2 and comp.signed_bytes


def test_june_2026_never_falls_back_to_june_2024():
    # Every june_2024 role must resolve to a real Tesla query under june_2026.
    for role in q.JUNE_2024_QUERIES:
        assert q.get_query(role, "june_2026") in q.JUNE_2026_QUERIES.values()


def test_get_query_by_name_diagnostics():
    for name in ("PW3Query", "ComplianceQuery", "TulipQuery", "IEEE20305Query"):
        assert q.get_query_by_name(name).signed_bytes


# --- TEDAPIApiVersion.coerce() ----------------------------------------------

def test_coerce_string_input():
    assert TEDAPIApiVersion.coerce("june_2024") is TEDAPIApiVersion.JUNE_2024
    assert TEDAPIApiVersion.coerce("june_2026") is TEDAPIApiVersion.JUNE_2026


def test_coerce_enum_input_passthrough():
    assert TEDAPIApiVersion.coerce(TEDAPIApiVersion.JUNE_2026) is TEDAPIApiVersion.JUNE_2026


@pytest.mark.parametrize("bad", ["nonsense", "legacy", "", None, 123])
def test_coerce_invalid_falls_back_to_june_2024(bad):
    # invalid input (incl. the retired "legacy" label and non-strings) -> default
    assert TEDAPIApiVersion.coerce(bad) is TEDAPIApiVersion.JUNE_2024


# --- get_query() missing role + call-site coverage --------------------------

def test_get_query_missing_role_raises():
    with pytest.raises(KeyError):
        q.get_query("no_such_role")                       # june_2024 set
    with pytest.raises(KeyError):
        q.get_query("no_such_role", "june_2026")          # june_2026 role map


def test_june_2026_call_site_roles_are_all_mapped():
    """Guard: every ``get_query(<role>, JUNE_2026)`` call in tedapi/__init__.py
    must use a role present in JUNE_2026_ROLES — otherwise it KeyErrors at
    runtime under june_2026. Scans the real source so a new call site (or a
    renamed role) can't silently regress this."""
    import ast
    import pypowerwall.tedapi as tedapi_mod

    src = open(tedapi_mod.__file__, encoding="utf-8").read()
    used = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "get_query" and len(node.args) >= 2):
            second = node.args[1]
            is_2026 = (
                (isinstance(second, ast.Attribute) and second.attr == "JUNE_2026")
                or (isinstance(second, ast.Constant) and second.value == "june_2026")
            )
            role = node.args[0]
            if is_2026 and isinstance(role, ast.Constant) and isinstance(role.value, str):
                used.add(role.value)

    assert used, "no get_query(..., JUNE_2026) call sites found — scan logic broke?"
    # safety: no call-site role is unmapped (would KeyError at runtime)
    unmapped = used - set(q.JUNE_2026_ROLES)
    assert not unmapped, f"june_2026 call-site roles missing from JUNE_2026_ROLES: {unmapped}"
    # completeness: JUNE_2026_ROLES maps exactly the roles the call sites need
    assert used == set(q.JUNE_2026_ROLES), (
        f"JUNE_2026_ROLES out of sync with call sites; symmetric diff: "
        f"{used ^ set(q.JUNE_2026_ROLES)}"
    )


# --- default-unchanged regression -------------------------------------------

def _june_2024_status_bytes(din):
    """Reconstruct the june_2024 device_controller_basic request exactly as the
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


def test_june_2024_request_is_stable(api):
    # Snapshot invariants: june_2024 build is deterministic and carries the signed
    # 'code' over the QueryType payload (the original wire shape).
    raw = _june_2024_status_bytes(api.din)
    again = _june_2024_status_bytes(api.din)
    assert raw == again
    m = tedapi_pb2.Message()
    m.ParseFromString(raw)
    assert m.message.recipient.din == api.din
    assert m.message.payload.send.code == q.JUNE_2024_QUERIES["device_controller_basic"].code
    assert m.tail.value == 1


# --- june_2026 build / parse ------------------------------------------------

def test_build_signed_query_request(api):
    query = q.get_query("device_controller_full", "june_2026")
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


def test_build_signed_query_follower_routing(api):
    query = q.get_query_by_name("PW3Query")
    raw = api._build_signed_query_request(
        query, recipient_din="FOLLOWER-DIN", sender_din=api.din, tail=2)
    m = tx.Message()
    m.ParseFromString(raw)
    assert m.message.recipient.din == "FOLLOWER-DIN"
    assert m.message.sender.din == api.din
    assert m.tail.value == 2


def test_parse_signed_response_basic(api):
    api.v1r = False
    resp = tx.Message()
    resp.message.graphql.queryResponse.status = 1
    resp.message.graphql.queryResponse.data = '{"control":{"x":1}}'
    assert api._parse_signed_query_response(resp.SerializeToString()) == '{"control":{"x":1}}'


def test_parse_signed_response_v1r_bare_envelope(api):
    api.v1r = True
    env = ed.MessageEnvelope()
    env.graphql.queryResponse.status = 1
    env.graphql.queryResponse.data = '{"v1r":true}'
    assert api._parse_signed_query_response(env.SerializeToString()) == '{"v1r":true}'


def test_parse_signed_response_empty_returns_none(api):
    assert api._parse_signed_query_response(b"") is None
