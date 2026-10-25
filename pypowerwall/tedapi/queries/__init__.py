"""
Versioned TEDAPI GraphQL queries.

Two date-labeled sets are stored as JSON next to this module and loaded into
TEDAPIQuery records at import time; `tedapi_api_version` selects between them:
  - V2024_06.json : the original hand-rolled {text, code, b} captures, keyed by
                     call-site role. Sent via the legacy QueryType path.
  - V2026_06.json : Newer pre-signed pairs keyed by GraphQL operation name.
                     Sent via the energy_device SignedGraphQLQuery path.

The labels are deliberately date-based. Both files share one schema per query: {text, code (hex ECDSA signature), b_value
(variables JSON), version (SignedGraphQLQuery version; 0 for V2024_06), signed_bytes (hex; V2026_06 only)}.

The JSON files are pristine captures and are never edited. Signals the library
requests beyond a capture live in EXTRA_SIGNAL_NAMES and component types in
EXTRA_COMPONENT_TYPES; both are merged into the request variables at import
(V2024_06_REQUEST_QUERIES), which is what get_query() returns for the V2024_06
wire.
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
# validation; the V2026_06 PW3Query requests them). PCH_heatsinkTemp read a constant
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

#
# Gateway uptime (#418): SYNC_Uptime is the Backup Gateway sync board's uptime in
# milliseconds, on the msa component whose serial is esCan.bus.SYNC's. Validated
# 2026-10-11 on 2x PW3 + Backup Gateway 2 over WiFi and v1r: after 16 days it put the
# start within a minute of the 2026-09-24 firmware-update reboot. A ~24k-name sweep
# found no other uptime signal. V2026_06 can't request it (signal names are inline
# in its signed query).
GATEWAY_MSA_SIGNAL_NAMES = ("SYNC_Uptime",)

#
# PW3 signals that the V2026_06 queries request (PW3Query and
# ComplianceQuery list them inline) but our V2024_06 capture doesn't. All 23 were
# echoed live on 2x PW3 (firmware 26.26.11) on 2026-10-11. Battery health on bms:
# BMS_kwhDischargeTotal (kWh), BMS_LOG_ahDischargeTotal (Ah), BMS_LOG_cacAvg
# (capacity, Ah), BMS_LOG_selfDischargeRate, BMS_LOG_numFullBattCycles (0 on both
# units so far) and BMS_LOG_overDischargeCounter.
PW3_APP_SIGNAL_NAMES = {
    "pchSignalNames": ("PCH_AcRealPowerSum", "PCH_AcVoltageCN", "PCH_AcVoltageLL", "PCH_pcbaId", "PCH_usageId"),
    "bmsSignalNames": ("BMS_kwhDischargeTotal", "BMS_LOG_ahDischargeTotal", "BMS_LOG_cacAvg",
                       "BMS_LOG_numFullBattCycles", "BMS_LOG_overDischargeCounter", "BMS_LOG_selfDischargeRate"),
    "hvpSignalNames": ("HVP_SafetyBiDisconnectState", "HVP_a061_LockoutOnIsoFaultRetry"),
    "pwsSignalNames": ("PWS_ExtSwitch_State", "PWS_RSDSelfTest_Result", "PWS_RSDSelfTest_State", "PWS_RSD_State",
                       "PWS_assemblyId", "PWS_pcbaId", "PWS_reversePolarityStrings"),
    "baggrSignalNames": ("BAGGR_ExpectedEnergyRemaining", "BAGGR_ExpectedFullPackEnergy", "BAGGR_OperationType"),
}

#
# PW2 per-Powerwall signals - hardware-validated 2026-10-09/11 on 4x Powerwall 2
# behind a Backup Gateway 1 (firmware 26.34.0, v1r LAN), and on 2026-10-11 on a second
# Backup Gateway 1 site with 4x Powerwall 2 on firmware 26.18.3, one a warranty
# replacement with different TETHC/TEPINV part numbers. The capture's msaComp component
# types are unchanged. They fill TEDAPI vitals keys that mirror the original
# /api/devices/vitals and were placeholders (None) until now, plus three new TEPINV
# keys. The msa TEPINV (battery module), TETHC (package) and TESYNC (gateway)
# components deliver them; vitals() pairs each TEPINV with its package by component
# order (_pw2_msa_module_pairing) and leaves its values None if that can't be proven.
#   PINV_EnergyCharged / PINV_EnergyDischarged: per-module lifetime counters in Wh.
#     The four modules' discharged sum matched the site's Fleet API cumulative battery
#     discharge to 0.12% (2026-10-09 and again 2026-10-11), and over 5.9 hours of
#     charging on 2026-10-10 the charged counters rose 30,048 Wh against 30,067.6 Wh
#     integrated from the gateway's battery meter (0.07%).
#   PINV_LifetimeEnergyCharged / PINV_LifetimeEnergyDischarged: equal to the two
#     above in all 16 pack-reads on 2026-10-11; passed through as delivered.
#   PINV_HeatsinkTemp: degrees C, differed by unit and drifted between reads
#     (34.5-39.2 C across the four units, idle).
#   PINV_PllFrequency, PINV_PllLocked, PINV_Qout, PINV_ReadyForGridForming,
#     PINV_HardwareEnableLine, THC_State, SYNC_ExternallyPowered and
#     SYNC_SiteSwitchEnabled: live, same units/strings as docs/vitals-example.json.
#     Booleans arrive in boolValue and enums in textValue (see _signal_value).
#   PINV_PowerLimiter: echoed, but None on every unit on that firmware.
# On Powerwall 3 (2x PW3, firmware 26.26.11, WiFi TEDAPI and v1r) the gateway accepts
# this request with an unchanged response structure and echoes the names as null,
# except SYNC_ExternallyPowered / SYNC_SiteSwitchEnabled on a site that reports a SYNC
# device (such as a Backup Gateway 2): those now fill TESYNC there too (False, as in the
# original /api/devices/vitals).
# The TEPOD POD_* placeholders need TEPOD added to msaComp: that is now done, see
# PW2_POD_POWER_SIGNAL_NAMES and PW2_MSA_COMPONENT_TYPES below.
PW2_MSA_SIGNAL_NAMES = (
    "PINV_EnergyCharged", "PINV_EnergyDischarged",
    "PINV_LifetimeEnergyCharged", "PINV_LifetimeEnergyDischarged",
    "PINV_HeatsinkTemp", "PINV_PllFrequency", "PINV_PllLocked", "PINV_Qout",
    "PINV_ReadyForGridForming", "PINV_HardwareEnableLine", "PINV_PowerLimiter",
    "THC_State", "SYNC_ExternallyPowered", "SYNC_SiteSwitchEnabled",
)

#
# PW2 instantaneous available power - hardware-validated 2026-10-18 on a 2x
# Powerwall 2 site (firmware 26.34.1, tedapi "full" mode). The capture's
# msaComp.types lacks TEPOD, so its POD components never arrived and the TEPOD
# POD_* vitals placeholders and the instantaneous power fields had no source.
# With TEPOD appended (PW2_MSA_COMPONENT_TYPES), the gateway returns each POD
# module's TEPOD component plus 8 serial-less empty slots; the two signal names
# below echo on the TEPOD components with live values (7000/7000 and 7000/8570
# on the validation site) and as null on the empty slots. Their per-unit sums
# (14000/15570) are exactly what the gateway's local /api/system_status
# reported as instantaneous_max_charge_power / instantaneous_max_discharge_power
# in the same combined run (an earlier local capture read 15590 - the values
# follow the battery's state and move between reads). POD_available_apparent_
# power and the long POD_available_discharge_power name were not echoed. The type is
# spelled TEPOD: "POD" is not a ComponentType member and fails the whole query
# ("Variable \"types\" has invalid value POD"), which comes back as an empty
# response - the trap this block deliberately avoided before TEPOD was
# validated. Under V2026_06 none of this can be requested (types and signals
# are inline in its signed query).
PW2_POD_POWER_SIGNAL_NAMES = ("POD_available_charge_power", "POD_available_dischg_power")
PW2_MSA_COMPONENT_TYPES = ("TEPOD",)

EXTRA_SIGNAL_NAMES = {
    QueryRole.COMPONENTS: {
        "pchSignalNames": ("PCH_AmbientTemp", "PCH_heatsinkTemp") + PW3_FAN_SIGNAL_NAMES
                          + PW3_APP_SIGNAL_NAMES["pchSignalNames"],
        "bmsSignalNames": ("BMS_LOG_tempOutOfBounds", "BMS_LOG_tempOutOfBoundsCharge")
                          + PW3_APP_SIGNAL_NAMES["bmsSignalNames"],
        "hvpSignalNames": ("HVP_PackTempMax", "HVP_PackTempMin", "HVP_ShuntTemperature")
                          + PW3_APP_SIGNAL_NAMES["hvpSignalNames"],
        "pwsSignalNames": PW3_APP_SIGNAL_NAMES["pwsSignalNames"],
        "baggrSignalNames": PW3_APP_SIGNAL_NAMES["baggrSignalNames"],
    },
    QueryRole.DEVICE_CONTROLLER_FULL: {
        # SYNC_Uptime first (#419), then the PW2 per-Powerwall names, then the
        # TEPOD available-power names
        "msaSignals": GATEWAY_MSA_SIGNAL_NAMES + PW2_MSA_SIGNAL_NAMES + PW2_POD_POWER_SIGNAL_NAMES,
    },
}

# Component types requested beyond a V2024_06 capture, per role and variables key:
# names are appended to the variable's ``types`` list (never inserted), so the
# capture keeps its type order. Only ComponentType enum members are allowed - one
# value outside the enum fails the whole query and the response comes back empty.
EXTRA_COMPONENT_TYPES = {
    QueryRole.DEVICE_CONTROLLER_FULL: {
        "msaComp": PW2_MSA_COMPONENT_TYPES,
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


def _with_extra_component_types(query: TEDAPIQuery, extras) -> TEDAPIQuery:
    """Return ``query`` with ``extras`` appended to its variables' component-type
    lists (the same object when there is nothing to add)."""
    if not extras:
        return query
    variables = json.loads(query.b_value)
    for key, names in extras.items():
        component_filter = variables.get(key)
        if not isinstance(component_filter, dict):
            continue
        current = component_filter.get("types") or []
        component_filter["types"] = current + [name for name in names if name not in current]
    # Compact separators, same as _with_extra_signals: the only wire difference
    # is the appended types.
    return dataclasses.replace(query, b_value=json.dumps(variables, separators=(",", ":")))


# What the V2024_06 wire actually sends: each capture plus its EXTRA_SIGNAL_NAMES
# and EXTRA_COMPONENT_TYPES.
V2024_06_REQUEST_QUERIES = {
    role: _with_extra_component_types(
        _with_extra_signals(query, EXTRA_SIGNAL_NAMES.get(role)),
        EXTRA_COMPONENT_TYPES.get(role))
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
    V2026_06 resolves strictly to its own pre-signed queries (raises if a role has no
    V2026_06 equivalent — by design, the V2026_06 path never falls back). V2024_06
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
