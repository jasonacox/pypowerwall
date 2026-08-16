"""Tests for the two-version TEDAPI query path (V2024_06 + V2026_06).

Priority is the default-unchanged guarantee: with tedapi_api_version unset the
V2024_06 request bytes must be exactly what they were before the migration.
"""
import logging
from unittest.mock import patch

import pytest
from pypowerwall.tedapi import TEDAPI
from pypowerwall.tedapi import queries as q
from pypowerwall.tedapi import tedapi_pb2
from pypowerwall.tedapi.api_version import (LABEL_RE, TEDAPIApiVersion,
                                            _parse_label)
from pypowerwall.tedapi.auth_mode import AuthMode

# The V2026_06 pb2 requires protobuf>=6.33.6 (guarded gencode); the default path
# stays on the 4.25.1 floor, so import lazily and skip the build/parse tests when
# the newer runtime isn't present (mirrors test_system_info.py).
try:
    from pypowerwall.tedapi.protobuf.V2026_06 import \
        tedapi_v2_energy_device_pb2 as ed
    from pypowerwall.tedapi.protobuf.V2026_06 import \
        tedapi_v2_transport_pb2 as tx
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


# --- TEDAPIApiVersion ordering ----------------------------------------------
# Ordering is by the date parsed from each member's label, not by comparing the
# string labels lexically, so a future version whose label does not sort
# lexically still ranks correctly.

V24, V26 = TEDAPIApiVersion.V2024_06, TEDAPIApiVersion.V2026_06


def test_ordering_between_members():
    assert V24 < V26
    assert V26 > V24
    assert V24 <= V26 and V26 >= V24
    assert not (V26 < V24)
    assert not (V24 > V26)


def test_ordering_is_reflexive_for_le_ge():
    assert V26 <= V26 and V26 >= V26
    assert not (V26 < V26)
    assert not (V26 > V26)


def test_threshold_semantics():
    """Capability-threshold semantics: only versions OLDER than the floor fail
    it; the floor itself, and anything newer, satisfy it."""
    assert V24 < V26          # older than the floor
    assert not (V26 < V26)    # exactly the floor
    assert V26 >= V26         # floor satisfies its own threshold


def test_ordering_against_plain_strings():
    """Version strings are the documented input form (env var / CLI), so they
    must order correctly from either side of the operator."""
    assert V24 < "V2026_06"
    assert V26 >= "V2024_06"
    # reflected: a plain str on the left must still use enum ordering, because
    # TEDAPIApiVersion is a str subclass and Python tries its reflected op first
    assert "V2024_06" < V26
    assert not ("V2026_06" < V24)


def test_rank_is_the_parsed_date():
    """Ordering is derived from the date the label encodes, not from declaration
    order and not from lexical string order. Day 0 marks a month-only label."""
    assert TEDAPIApiVersion.V2024_06._rank() == (2024, 6, 0)
    assert TEDAPIApiVersion.V2026_06._rank() == (2026, 6, 0)


# --- rank tuple shape -------------------------------------------------------
# Comparison is Python's tuple comparison: scan with == to the first differing
# index, then apply the operator to that pair alone, falling back to length if
# no index differs. Two properties of the rank tuples are what make that give
# correct date ordering, and neither is guaranteed by the ordering tests below —
# so pin them directly.

@pytest.mark.parametrize("label", [
    "V2024_06", "V2026_06", "V2026_06_01", "V2026_06_31", "V9999_12_31", "V0001_01",
])
def test_rank_is_always_three_ints(label):
    """Uniform arity and homogeneous int elements.

    Arity: tuples of different lengths still ORDER sanely (a prefix sorts
    first), so a ragged rank would slip past every ordering assertion — but
    (2026, 6) != (2026, 6, 0), so equality would silently break instead.

    Types: tuple comparison reaches the first differing pair and applies the
    operator to it, so a stray str or None in a rank raises TypeError mid-compare
    rather than misordering. Both failure modes are invisible to sort tests.
    """
    rank = _parse_label(label)
    assert isinstance(rank, tuple)
    assert len(rank) == 3, f"{label!r} produced a {len(rank)}-tuple; ranks must be uniform"
    assert all(isinstance(part, int) for part in rank), \
        f"{label!r} produced non-int parts {rank!r}; comparison would raise"


def test_every_member_rank_is_three_ints():
    for member in TEDAPIApiVersion:
        rank = member._rank()
        assert len(rank) == 3 and all(isinstance(p, int) for p in rank), \
            f"{member.value!r} rank {rank!r} is not a 3-int tuple"


# --- lexicographic precedence -----------------------------------------------
# The first differing component decides the whole comparison, so significance
# must fall off year -> month -> day. These cases are adversarial: the less
# significant components point the OPPOSITE way to the correct answer, so they
# fail if precedence is ever inverted or flattened.
#
# Day-level cases go through _parse_label rather than the enum operators: both
# shipped members are month-only, and the operators deliberately reject a label
# that is not a member, so there is no day-bearing member to compare against.
# _parse_label is where the ordering actually comes from, so that is the right
# level for these.

def test_year_dominates_month_and_day():
    """A late month/day in an earlier year must still sort first."""
    assert _parse_label("V2025_12_31") < _parse_label("V2026_01")
    assert _parse_label("V2025_12_31") < _parse_label("V2026_01_01")
    assert not (_parse_label("V2026_01_01") < _parse_label("V2025_12_31"))


def test_month_dominates_day():
    """The last day of a month must still sort before the first of the next."""
    assert _parse_label("V2026_06_31") < _parse_label("V2026_07_01")
    assert _parse_label("V2026_06_31") < _parse_label("V2026_07")
    assert not (_parse_label("V2026_07_01") < _parse_label("V2026_06_31"))


def test_day_decides_only_when_year_and_month_tie():
    assert _parse_label("V2026_06_02") < _parse_label("V2026_06_10")
    # ...and cannot flip a decision already made by year or month
    assert _parse_label("V2026_06_28") < _parse_label("V2027_06_01")


def test_sorting_is_monotonic_across_all_three_components():
    """One shuffled list exercising year, month and day transitions at once."""
    labels = [
        "V2026_07_01", "V2024_06", "V2026_06_28", "V2025_12_31",
        "V2026_06", "V2026_06_02", "V2027_01", "V2026_01",
    ]
    ordered = sorted(labels, key=_parse_label)
    assert ordered == [
        "V2024_06", "V2025_12_31", "V2026_01", "V2026_06",
        "V2026_06_02", "V2026_06_28", "V2026_07_01", "V2027_01",
    ]
    for older, newer in zip(ordered, ordered[1:]):
        assert _parse_label(older) < _parse_label(newer), \
            f"{older} must sort strictly before {newer}"


def test_member_ranks_are_unique():
    """Distinct members must not tie. A tie makes both `a < b` and `a > b` false,
    which silently breaks sorting and threshold checks."""
    ranks = [m._rank() for m in TEDAPIApiVersion]
    assert len(set(ranks)) == len(ranks), f"duplicate ranks among members: {ranks}"


def test_every_member_label_matches_the_format():
    """The VYYYY_MM[_DD] format is load-bearing — ordering parses it — so a new
    member that breaks it must be caught here (and at import)."""
    for member in TEDAPIApiVersion:
        assert LABEL_RE.match(member.value), \
            f"{member.value!r} is not V<YYYY>_<MM>[_<DD>]; ordering would break"


def test_ordering_sorts_by_date_across_declaration_order():
    """A member declared out of sequence must still sort by its date. Built from
    labels rather than the live enum so the property holds for future members."""
    labels = ["V2027_01", "V2024_06", "V2026_06", "V2024_11"]
    assert sorted(labels, key=_parse_label) == \
        ["V2024_06", "V2024_11", "V2026_06", "V2027_01"]


# --- optional day component -------------------------------------------------
# Labels may carry a day: V2026_06_01. Not used today, but the format must
# accept and order it correctly if a future set needs same-month precision.

def test_day_component_is_parsed():
    assert _parse_label("V2026_06_01") == (2026, 6, 1)
    assert _parse_label("V2026_06_15") == (2026, 6, 15)
    assert _parse_label("V2026_06_31") == (2026, 6, 31)


def test_month_only_label_sorts_before_dated_labels_in_that_month():
    """The deliberate convention: a day-less label ranks at day 0, so it is
    strictly distinct from — and earlier than — any dated label in the same
    month. A month-only set ships first; a later set that same month is the one
    that needs a day to disambiguate itself."""
    assert _parse_label("V2026_06") < _parse_label("V2026_06_01")
    assert _parse_label("V2026_06") != _parse_label("V2026_06_01"), \
        "a month-only label must not rank equal to a dated one (ties break ordering)"


def test_day_does_not_leak_across_month_or_year_boundaries():
    labels = ["V2026_07_01", "V2026_06", "V2026_06_28", "V2025_12_31", "V2026_06_02"]
    assert sorted(labels, key=_parse_label) == [
        "V2025_12_31", "V2026_06", "V2026_06_02", "V2026_06_28", "V2026_07_01"]


def test_dated_labels_order_within_a_month():
    assert _parse_label("V2026_06_02") < _parse_label("V2026_06_10")
    assert _parse_label("V2026_06_10") < _parse_label("V2026_06_28")


@pytest.mark.parametrize("bad", [
    "v2026_06",      # lowercase: sorts ABOVE uppercase lexically, silently reversing
    "V2026_6",       # unpadded month
    "V26_06",        # short year
    "V2026-06",      # wrong separator
    "V2026_13",      # month out of range
    "V2026_00",
    "V2026_06_1",    # unpadded day
    "V2026_06_32",   # day out of range
    "V2026_06_00",   # day 0 is the no-day sentinel, never a valid label
    "V2026_06_",     # trailing separator, no day
    "V2026_06_01_02",  # too many components
    "nonsense", "", 3, None,
])
def test_parse_label_rejects_non_conforming_values(bad):
    with pytest.raises(ValueError):
        _parse_label(bad)  # type: ignore[arg-type]


def test_ordering_rejects_non_version_operand():
    """Comparing against a non-version must raise with a useful message, not
    fall back to str order (NotImplemented would do exactly that, since members
    are str subclasses)."""
    for bad in ("V9999_99", "v2026_06", "nonsense", 3):
        with pytest.raises(TypeError) as exc:
            _ = TEDAPIApiVersion.V2024_06 < bad
        assert "not a known version" in str(exc.value)
        assert "V2026_06" in str(exc.value), "error must list the valid versions"


def test_malformed_member_label_is_rejected_at_import():
    """The import-time guard: a member that breaks the format must be refused."""
    with pytest.raises(ValueError, match="V<YYYY>_<MM>"):
        _parse_label("V26_6", "TEDAPIApiVersion")


def test_equality_and_dict_use_still_string_based():
    """Only ordering is overridden — equality and hashing stay str's, so members
    keep comparing equal to their plain string and keep working as dict keys."""
    assert V26 == "V2026_06"
    assert {"V2026_06": 1}[V26] == 1
    assert {V26: 1}["V2026_06"] == 1

# --- auth_mode <-> version coupling warning ---------------------------------
# Bearer is the AuthEnvelope transport the newer gateways use and needs the
# signed-GraphQL query set introduced in V2026_06 (a MINIMUM, not an exact
# match). Selecting it with the older V2024_06 default is a likely
# misconfiguration, so __init__ warns (non-fatal).
#
# All three tests key off one marker: the positive test asserts it is present
# and the negative tests assert it is absent. Reword the warning and the
# positive test fails loudly, instead of the negative tests silently passing
# because they now search for a string that no longer exists anywhere.
COUPLING_WARNING_MARKER = "signed-GraphQL query set"


@pytest.mark.parametrize("mode", [AuthMode.BEARER, "bearer"])
def test_bearer_with_legacy_version_warns(mode, caplog):
    with caplog.at_level(logging.WARNING, logger="pypowerwall.tedapi"), \
            patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        TEDAPI("pw", auth_mode=mode)  # tedapi_api_version defaults to V2024_06
    assert COUPLING_WARNING_MARKER in caplog.text
    assert "V2026_06" in caplog.text
    assert "V2024_06" in caplog.text


@pytest.mark.parametrize("mode", [AuthMode.BEARER, "bearer"])
def test_bearer_with_V2026_06_is_silent(mode, caplog):
    with caplog.at_level(logging.WARNING, logger="pypowerwall.tedapi"), \
            patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        TEDAPI("pw", auth_mode=mode, tedapi_api_version="V2026_06")
    assert COUPLING_WARNING_MARKER not in caplog.text


def test_basic_mode_with_legacy_version_is_silent(caplog):
    # the default transport must never emit the bearer coupling warning
    with caplog.at_level(logging.WARNING, logger="pypowerwall.tedapi"), \
            patch('pypowerwall.tedapi.TEDAPI.connect', return_value="X"):
        TEDAPI("pw")  # auth_mode=basic, version=V2024_06 (both defaults)
    assert COUPLING_WARNING_MARKER not in caplog.text


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
