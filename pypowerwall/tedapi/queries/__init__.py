"""
Versioned TEDAPI GraphQL queries.

Two date-labeled sets are stored as JSON next to this module and loaded into
TEDAPIQuery records at import time; `tedapi_api_version` selects between them:
  - june_2024.json : the original hand-rolled {text, code, b} captures, keyed by
                     call-site role. Sent via the legacy QueryType path.
  - june_2026.json : Newer Tesla-signed pairs keyed by Tesla GraphQL operation name.
                     Sent via the energy_device SignedGraphQLQuery path.

The labels are deliberately date-based. Both files share one schema per query: {text, code (hex ECDSA signature), b_value
(variables JSON), version (SignedGraphQLQuery version; 0 for june_2024), signed_bytes (hex; june_2026 only)}.
"""
import json
from pathlib import Path

from ..api_version import TEDAPIApiVersion
from .base import TEDAPIQuery

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


JUNE_2024_QUERIES = _load_query_set("june_2024.json")   # keyed by call-site role
JUNE_2026_QUERIES = _load_query_set("june_2026.json")   # keyed by Tesla operation name

# Map call-site roles june_2024 -> june_2026 Tesla operation names.
# Tesla replaced ComponentsQuery with PW3Query, which
# covers the same component types (pws/pch/bms/hvp/baggr) with inline filters.
JUNE_2026_ROLES = {
    "device_controller_basic": "DeviceControllerQuery",
    "device_controller_full":  "DeviceControllerQuery",
    "components":              "PW3Query",
}

QUERY_SETS = {
    TEDAPIApiVersion.JUNE_2024: JUNE_2024_QUERIES,
    TEDAPIApiVersion.JUNE_2026: JUNE_2026_QUERIES,
}


def get_query(role: str, api_version=TEDAPIApiVersion.JUNE_2024) -> TEDAPIQuery:
    """Look up a TEDAPIQuery by call-site role for the given api version.

    june_2026 resolves strictly to Tesla's own queries (raises if a role has no
    Tesla equivalent — by design, the june_2026 path never falls back)."""
    if api_version == TEDAPIApiVersion.JUNE_2026:
        return JUNE_2026_QUERIES[JUNE_2026_ROLES[role]]
    return JUNE_2024_QUERIES[role]


def get_query_by_name(operation_name: str) -> TEDAPIQuery:
    """Fetch a june_2026 query directly by Tesla GraphQL operation name
    (for diagnostics / free-form use: PW3Query, ComplianceQuery, etc.)."""
    return JUNE_2026_QUERIES[operation_name]


def apply_query(send_payload, query: TEDAPIQuery) -> None:
    """Populate a june_2024 tedapi QueryType SendMessage payload (text/code/b)."""
    send_payload.payload.text = query.text
    send_payload.code = query.code
    send_payload.b.value = query.b_value
