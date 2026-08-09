"""TEDAPI gateway authentication mode selector.

`auth_mode` chooses how HTTP requests to the gateway are authenticated. It is a
str-valued enum, so members compare equal to their plain string
("basic"/"bearer") and interoperate transparently with CLI args, dict keys, and
JSON — while still being a real enum.
"""
import logging
from enum import Enum

log = logging.getLogger(__name__)


class AuthMode(str, Enum):
    """How TEDAPI authenticates to the Powerwall Gateway."""
    BASIC = "basic"    # HTTP Basic Auth; needs a route to 192.168.91.1
    BEARER = "bearer"  # /api/login/Basic token + AuthEnvelope(PRESENCE)

    def __str__(self) -> str:
        # Stable display across Python versions (avoids "AuthMode.BASIC").
        return self.value

    @classmethod
    def coerce(cls, value, default=None) -> "AuthMode":
        """Accept an AuthMode or a string (case-insensitive, e.g. from a CLI arg).

        Auth mode is behavior- and security-critical, so an unrecognized value
        must never silently select a different transport. With no `default`
        (library callers) it raises ValueError. Pass `default` where a bad
        value must not be fatal — e.g. a typo in a container env var would
        otherwise surface much later as a connection error and a restart
        loop — and it logs a warning naming the bad value and the valid
        choices, then falls back. The warning reaches stderr even before
        logging is configured (logging's last-resort handler).
        """
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except (ValueError, KeyError):
            valid = ", ".join(repr(m.value) for m in cls)
            if default is None:
                raise ValueError(
                    f"Invalid auth_mode {value!r}: must be one of {valid}")
            default = cls.coerce(default)
            log.warning(f"Invalid auth_mode {value!r}: must be one of {valid}"
                        f" - defaulting to {default}")
            return default
