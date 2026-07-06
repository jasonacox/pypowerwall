"""Shared TEDAPI query record type."""
from dataclasses import dataclass
from enum import Enum


class QueryRole(str, Enum):
    """Call-site role for a TEDAPI query — the stable key that selects the right
    versioned query (a V2024_06 hand-rolled capture or a V2026_06 Tesla operation).

    A str-valued enum, so members compare/hash equal to their string value and
    work transparently as dict keys against the string-keyed query sets and the
    JSON files (and against plain strings passed from older callers)."""
    DEVICE_CONTROLLER_BASIC = "device_controller_basic"   # get_status()
    DEVICE_CONTROLLER_FULL = "device_controller_full"     # get_device_controller()
    COMPONENTS = "components"                              # get_components / pw3_vitals / battery_block

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TEDAPIQuery:
    text: str
    code: bytes                # Tesla ECDSA signature (V2024_06 'code' / V2026_06 signature)
    b_value: str = "{}"        # variables JSON
    version: int = 0           # SignedGraphQLQuery version; 0 = legacy QueryType path
    signed_bytes: bytes = b""  # exact SignedGraphQLQuery bytes (V2026_06 only)


# DeviceControllerQuery — original (no variables, no msa/teslaRemoteMeter/ieee20305).
# Used by get_status().
