"""Shared TEDAPI query record type."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TEDAPIQuery:
    text: str
    code: bytes                # Tesla ECDSA signature (june_2024 'code' / june_2026 signature)
    b_value: str = "{}"        # variables JSON
    version: int = 0           # SignedGraphQLQuery version; 0 = legacy QueryType path
    signed_bytes: bytes = b""  # exact SignedGraphQLQuery bytes (june_2026 only)


# DeviceControllerQuery — original (no variables, no msa/teslaRemoteMeter/ieee20305).
# Used by get_status().
