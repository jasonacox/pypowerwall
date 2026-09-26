"""
Versioned TEDAPI GraphQL queries.

Two date-labeled sets are stored as JSON next to this module and loaded into
TEDAPIQuery records at import time; `tedapi_api_version` selects between them:
  - V2024_06.json : the original hand-rolled {text, code, b} captures, keyed by
                     call-site role. Sent via the legacy QueryType path.
  - V2026_06.json : Newer Tesla-signed pairs keyed by Tesla GraphQL operation name.
                     Sent via the energy_device SignedGraphQLQuery path.

The labels are deliberately date-based. Both files share one schema per query: {text, code (hex ECDSA signature), b_value
(variables JSON), version (SignedGraphQLQuery version; 0 for V2024_06), signed_bytes (hex; V2026_06 only)}.

The JSON files are pristine captures and are never edited. Signals the library
requests beyond a capture live in EXTRA_SIGNAL_NAMES and are merged into the
request variables at import (V2024_06_REQUEST_QUERIES), which is what get_query()
returns for the V2024_06 wire.
"""
import dataclasses
import json
from pathlib import Path

from ..api_version import TEDAPIApiVersion
from .base import TEDAPIQuery, QueryRole

_DIR = Path(__file__).parent


def _load_query_set(filename: str) -> dict:
    """Load a query-set JSON file into {key: TEDAPIQuery}."""
    raw = json.loads((_DIR / filename).read_text(encoding="utf-8"))
    return {
        key: TEDAPIQuery(
            text=rec["text"],
            code=bytes.fromhex(rec.get("code", "")),
            b_value=rec.get("b_value", "{}"),
            version=rec.get("version", 0),
            signed_bytes=bytes.fromhex(rec.get("signed_bytes", "")),
        )
        for key, rec in raw.items()
    }


V2024_06_QUERIES = _load_query_set("V2024_06.json")   # keyed by call-site role
V2026_06_QUERIES = _load_query_set("V2026_06.json")   # keyed by Tesla operation name

# Signals requested in addition to a V2024_06 capture, per role and variables key.
# The capture's ECDSA signature covers only the query text: the *SignalNames
# variables are unsigned, and the gateway returns the signals it knows while
# silently dropping unknown names. Names are appended (never inserted) so every
# captured signal keeps its position in each component's response list.
#
# get_pw3_vitals() passes every COMPONENTS extra through to vitals as delivered
# (pch -> TEPINV block, bms/hvp -> each battery's TEPOD block), so adding a name
# here is the whole change. Derived values (temps()) use proven-live signals only.
#
# PW3 temperatures - hardware-validated 2026-09-24 on a PW3 leader + follower
# (WiFi TEDAPI and v1r LAN). PW3 has no TETHC thermal controller, so the PW2
# THC_AmbientTemp signal does not exist there. Temperatures are degrees C; the
# BMS_LOG_tempOutOfBounds* signals are over-temperature event counters (0 at
# validation; Tesla's own PW3Query requests them). PCH_heatsinkTemp read a constant
# 45.450980 (an 8-bit raw value) on both units while ambient moved over 7 C, so
# temps() doesn't use it. V2026_06 cannot carry extras: its PW3Query has the
# signal names inline in the signed text.
#
# PW3 fans - hardware-validated 2026-09-26 on the same PW3 leader + follower
# (firmware 26.18.1, no DC expansions). Each PW3 inverter (PCH) has two fans,
# A and B: PCH_FanSpeed_* is the measured speed in RPM (it jitters a few RPM
# between samples and differs between A and B at equal duty) and PCH_FanDuty_*
# is the drive duty cycle in percent. Both proved live in a 30-minute, 30 s
# sample while charging: duty is stepped, not continuous - the follower held
# 5.1/6.6% (~1000 RPM) for 27 minutes, then stepped to 16.4/17.2% and 18.7/19.1%
# within a minute as its inverter ambient reached 45.7 C and charge rose to
# 2.1 kW, with RPM following to ~1391/1395; the leader held 19.1% (~1395 RPM)
# throughout at 55-56 C. Values arrive as floats such as 5.1000000000000005
# and are passed through as delivered. There is no target-RPM, command, fault
# or state signal: a ~280k-name sweep of Fan/Pump/Blower name variants on every
# group (pws, pch, bms, hvp, baggr) echoed only these four, all on pch. The PW2
# PVAC_Fan_Speed_Actual/Target_RPM names are echoed by the device controller's
# msa components on PW3 but are always None there, which is why
# get_fan_speeds() used to be empty on PW3. As with the temperatures, V2026_06
# can't request the fans (its PW3Query doesn't list them), so there PW3 fan
# output stays {}.
PW3_FAN_SIGNAL_NAMES = ("PCH_FanSpeed_A", "PCH_FanSpeed_B", "PCH_FanDuty_A", "PCH_FanDuty_B")

EXTRA_SIGNAL_NAMES = {
    QueryRole.COMPONENTS: {
        "pchSignalNames": ("PCH_AmbientTemp", "PCH_heatsinkTemp") + PW3_FAN_SIGNAL_NAMES,
        "bmsSignalNames": ("BMS_LOG_tempOutOfBounds", "BMS_LOG_tempOutOfBoundsCharge"),
        "hvpSignalNames": ("HVP_PackTempMax", "HVP_PackTempMin", "HVP_ShuntTemperature"),
    },
}


def _with_extra_signals(query: TEDAPIQuery, extras) -> TEDAPIQuery:
    """Return ``query`` with ``extras`` appended to its variables' signal lists
    (the same object when there is nothing to add)."""
    if not extras:
        return query
    variables = json.loads(query.b_value)
    for key, names in extras.items():
        current = variables.get(key) or []
        variables[key] = current + [name for name in names if name not in current]
    # Compact separators reproduce the (compact) capture byte-for-byte, so the
    # only wire difference is the appended names.
    return dataclasses.replace(query, b_value=json.dumps(variables, separators=(",", ":")))


# What the V2024_06 wire actually sends: each capture plus its EXTRA_SIGNAL_NAMES.
V2024_06_REQUEST_QUERIES = {
    role: _with_extra_signals(query, EXTRA_SIGNAL_NAMES.get(role))
    for role, query in V2024_06_QUERIES.items()
}

# Map call-site roles V2024_06 -> V2026_06 Tesla operation names.
# Tesla replaced ComponentsQuery with PW3Query, which
# covers the same component types (pws/pch/bms/hvp/baggr) with inline filters.
V2026_06_ROLES = {
    QueryRole.DEVICE_CONTROLLER_BASIC: "DeviceControllerQuery",
    QueryRole.DEVICE_CONTROLLER_FULL:  "DeviceControllerQuery",
    QueryRole.COMPONENTS:              "PW3Query",
}

# The pristine captured sets. What goes on the wire is get_query(), which adds
# EXTRA_SIGNAL_NAMES to the V2024_06 captures.
QUERY_SETS = {
    TEDAPIApiVersion.V2024_06: V2024_06_QUERIES,
    TEDAPIApiVersion.V2026_06: V2026_06_QUERIES,
}


def get_query(role, api_version=TEDAPIApiVersion.V2024_06) -> TEDAPIQuery:
    """Look up a TEDAPIQuery by call-site role for the given api version.

    ``role`` is a QueryRole (a plain string also works — QueryRole is a str-enum).
    V2026_06 resolves strictly to Tesla's own queries (raises if a role has no
    Tesla equivalent — by design, the V2026_06 path never falls back). V2024_06
    returns the request form: the capture plus any EXTRA_SIGNAL_NAMES."""
    if api_version == TEDAPIApiVersion.V2026_06:
        return V2026_06_QUERIES[V2026_06_ROLES[role]]
    return V2024_06_REQUEST_QUERIES[role]


def get_query_by_name(operation_name: str) -> TEDAPIQuery:
    """Fetch a V2026_06 query directly by Tesla GraphQL operation name
    (for diagnostics / free-form use: PW3Query, ComplianceQuery, etc.)."""
    return V2026_06_QUERIES[operation_name]


def apply_query(send_payload, query: TEDAPIQuery) -> None:
    """Populate a V2024_06 tedapi QueryType SendMessage payload (text/code/b)."""
    send_payload.payload.text = query.text
    send_payload.code = query.code
    send_payload.b.value = query.b_value
