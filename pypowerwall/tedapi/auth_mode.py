"""TEDAPI gateway authentication mode selector.

`auth_mode` chooses how HTTP requests to the gateway are authenticated. It is a
str-valued enum, so members compare equal to their plain string
("basic"/"bearer"/"presence") and interoperate transparently with CLI args,
dict keys, and JSON — while still being a real enum.
"""
from enum import Enum


class AuthMode(str, Enum):
    """How TEDAPI authenticates to the Powerwall Gateway."""
    BASIC = "basic"        # HTTP Basic Auth; needs a route to 192.168.91.1
    BEARER = "bearer"      # /api/login/Basic token + AuthEnvelope(PRESENCE)
    PRESENCE = "presence"  # Powerwall 3 physical switch-flip installer login

    def __str__(self) -> str:
        # Stable display across Python versions (avoids "AuthMode.BASIC").
        return self.value

    @classmethod
    def coerce(cls, value) -> "AuthMode":
        """Accept an AuthMode or a string (case-insensitive, e.g. from a CLI arg).

        Raises ValueError on anything unrecognized — auth mode is behavior- and
        security-critical, so an unknown value must fail loudly rather than
        silently fall back to a different transport.
        """
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except (ValueError, KeyError):
            raise ValueError(
                f"Invalid auth_mode {value!r}: must be one of "
                f"{', '.join(repr(m.value) for m in cls)}")
