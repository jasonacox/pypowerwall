"""TEDAPI query/protobuf version selector.

`tedapi_api_version` chooses which date-labeled query + protobuf set to use.
It is a str-valued enum, so members compare equal to their plain string
("june_2024"/"june_2026") and interoperate transparently with environment
variables, CLI args, dict keys, and JSON — while still being a real enum.
"""
from enum import Enum


class TEDAPIApiVersion(str, Enum):
    """Which TEDAPI query + protobuf set to use (date-labeled, not APK version)."""
    JUNE_2024 = "june_2024"   # original hand-rolled captures (legacy QueryType path)
    JUNE_2026 = "june_2026"   # Tesla-signed energy_device SignedGraphQLQuery path

    def __str__(self) -> str:
        # Stable display across Python versions (avoids "TEDAPIApiVersion.JUNE_2024").
        return self.value

    @classmethod
    def coerce(cls, value) -> "TEDAPIApiVersion":
        """Accept a TEDAPIApiVersion or a string (e.g. from an env var / CLI);
        fall back to JUNE_2024 on anything unrecognized."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except (ValueError, KeyError):
            return cls.JUNE_2024
