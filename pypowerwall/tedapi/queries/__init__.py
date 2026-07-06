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
"""
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

# Map call-site roles V2024_06 -> V2026_06 Tesla operation names.
# Tesla replaced ComponentsQuery with PW3Query, which
# covers the same component types (pws/pch/bms/hvp/baggr) with inline filters.
V2026_06_ROLES = {
    QueryRole.DEVICE_CONTROLLER_BASIC: "DeviceControllerQuery",
    QueryRole.DEVICE_CONTROLLER_FULL:  "DeviceControllerQuery",
    QueryRole.COMPONENTS:              "PW3Query",
}

QUERY_SETS = {
    TEDAPIApiVersion.V2024_06: V2024_06_QUERIES,
    TEDAPIApiVersion.V2026_06: V2026_06_QUERIES,
}


def get_query(role, api_version=TEDAPIApiVersion.V2024_06) -> TEDAPIQuery:
    """Look up a TEDAPIQuery by call-site role for the given api version.

    ``role`` is a QueryRole (a plain string also works — QueryRole is a str-enum).
    V2026_06 resolves strictly to Tesla's own queries (raises if a role has no
    Tesla equivalent — by design, the V2026_06 path never falls back)."""
    if api_version == TEDAPIApiVersion.V2026_06:
        return V2026_06_QUERIES[V2026_06_ROLES[role]]
    return V2024_06_QUERIES[role]


def get_query_by_name(operation_name: str) -> TEDAPIQuery:
    """Fetch a V2026_06 query directly by Tesla GraphQL operation name
    (for diagnostics / free-form use: PW3Query, ComplianceQuery, etc.)."""
    return V2026_06_QUERIES[operation_name]


def apply_query(send_payload, query: TEDAPIQuery) -> None:
    """Populate a V2024_06 tedapi QueryType SendMessage payload (text/code/b)."""
    send_payload.payload.text = query.text
    send_payload.code = query.code
    send_payload.b.value = query.b_value
