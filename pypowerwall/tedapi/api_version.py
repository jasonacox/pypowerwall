"""TEDAPI query/protobuf version selector.

`tedapi_api_version` chooses which date-labeled query + protobuf set to use.
It is a str-valued enum, so members compare equal to their plain string
("V2024_06"/"V2026_06") and interoperate transparently with environment
variables, CLI args, dict keys, and JSON — while still being a real enum.
"""
import logging
from enum import Enum

log = logging.getLogger(__name__)


class TEDAPIApiVersion(str, Enum):
    """Which TEDAPI query + protobuf set to use (date-labeled, not APK version)."""
    V2024_06 = "V2024_06"   # original hand-rolled captures (legacy QueryType path)
    V2026_06 = "V2026_06"   # Tesla-signed energy_device SignedGraphQLQuery path

    def __str__(self) -> str:
        # Stable display across Python versions (avoids "TEDAPIApiVersion.V2024_06").
        return self.value

    @classmethod
    def coerce(cls, value) -> "TEDAPIApiVersion":
        """Accept a TEDAPIApiVersion or a string (e.g. from an env var / CLI);
        fall back to V2024_06 on anything unrecognized.

        Unlike the CLI (protected by argparse ``choices=``), the env-var path
        (PW_TEDAPI_API_VERSION) has no such guard, so a typo would silently run
        the legacy path. Log a warning naming the bad value and the valid choices
        so the fallback is diagnosable instead of invisible."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except (ValueError, KeyError):
            log.warning(
                "Unrecognized tedapi_api_version %r — falling back to %s. "
                "Valid values: %s.",
                value, cls.V2024_06.value, ", ".join(m.value for m in cls),
            )
            return cls.V2024_06
