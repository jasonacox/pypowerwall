"""TEDAPI query/protobuf version selector.

`tedapi_api_version` chooses which date-labeled query + protobuf set to use.
It is a str-valued enum, so members compare equal to their plain string
("V2024_06"/"V2026_06") and interoperate transparently with environment
variables, CLI args, dict keys, and JSON — while still being a real enum.
"""
import logging
import re
from enum import Enum

log = logging.getLogger(__name__)

# Member labels are date-encoded: V<year:4>_<month:2> with an OPTIONAL
# _<day:2> — "V2026_06" or "V2026_06_01". Ordering is derived from that date
# (see TEDAPIApiVersion._rank), so the format is load-bearing, not cosmetic; a
# new member must follow it. All three components are zero-padded fixed width.
LABEL_RE = re.compile(r"^V(\d{4})_(\d{2})(?:_(\d{2}))?$")

# Day used when a label carries no day component. Zero (not 1) so a month-only
# label is strictly distinct from — and sorts before — every dated label in the
# same month. That matches how the day would come to be used: a month-only set
# ships first, and a later set in that same month needs a day to disambiguate
# itself, so the undated one is the earlier of the two. Day 0 cannot collide
# with a real label because _parse_label only accepts days 01-31.
_NO_DAY = 0


def _parse_label(label: str, owner: str = "TEDAPIApiVersion") -> tuple:
    """Parse a VYYYY_MM[_DD] label into a sortable (year, month, day) triple.

    The day is optional; when absent it is reported as 0 (see _NO_DAY), which
    sorts a month-only label ahead of any dated label in the same month.

    Rejects anything that does not match the format, including out-of-range
    month or day values: ordering is only meaningful if the label really is a
    date, so a malformed label must fail rather than sort somewhere arbitrary.
    Day validation is a plain 01-31 range check, not a calendar lookup — these
    are release labels, and rejecting e.g. Feb 30 would buy nothing.
    """
    match = LABEL_RE.match(label) if isinstance(label, str) else None
    if not match:
        raise ValueError(
            f"{owner} label {label!r} is not of the form V<YYYY>_<MM> or "
            "V<YYYY>_<MM>_<DD> (e.g. 'V2026_06', 'V2026_06_01'); ordering is "
            "derived from that date")
    year, month, day = match.group(1), match.group(2), match.group(3)
    year, month = int(year), int(month)
    if not 1 <= month <= 12:
        raise ValueError(
            f"{owner} label {label!r} has month {month:02d}, which is not 01-12")
    if day is None:
        return year, month, _NO_DAY
    day = int(day)
    if not 1 <= day <= 31:
        raise ValueError(
            f"{owner} label {label!r} has day {day:02d}, which is not 01-31")
    return year, month, day


class TEDAPIApiVersion(str, Enum):
    """Which TEDAPI query + protobuf set to use (date-labeled, not APK version)."""
    V2024_06 = "V2024_06"   # original hand-rolled captures (legacy QueryType path)
    V2026_06 = "V2026_06"   # Tesla-signed energy_device SignedGraphQLQuery path

    def __str__(self) -> str:
        # Stable display across Python versions (avoids "TEDAPIApiVersion.V2024_06").
        return self.value

    # --- ordering -----------------------------------------------------------
    # Order is derived from the (year, month, day) the label encodes, NOT from
    # declaration order and NOT from str's lexical comparison. Parsing the date
    # means a member inserted out of sequence still sorts correctly, and it makes
    # the VYYYY_MM[_DD] format an enforced contract rather than a convention:
    # anything that does not match it is rejected.
    # (Contrast with coerce() below: unknown versions there fall back with a
    # warning by design — see its docstring before changing either behavior.)

    def _rank(self) -> tuple:
        """(year, month, day) parsed from this member's VYYYY_MM[_DD] label."""
        return _parse_label(self.value, type(self).__name__)

    @classmethod
    def _rank_of(cls, other) -> tuple:
        """Rank of a member or a known version string; TypeError on anything else.

        Raising beats returning NotImplemented here. Members are str subclasses,
        so NotImplemented would NOT produce a TypeError — Python would fall back
        to plain str comparison and answer from lexical order, silently. A
        lowercase typo is the nasty case: 'v2026_06' > 'V2026_06' in ASCII, so
        the comparison quietly reverses. That is the exact fragility these
        operators exist to remove, so a non-version operand fails loudly.

        The operand must be a member, not merely a well-formed label: this enum
        is the closed set of query/protobuf sets the library actually ships, so
        ordering against a version it cannot serve is a bug worth surfacing.
        """
        if isinstance(other, cls):
            return other._rank()
        try:
            return cls(other)._rank()
        except (ValueError, KeyError, TypeError):
            raise TypeError(
                f"cannot order {cls.__name__} against {other!r}: not a known "
                f"version ({', '.join(m.value for m in cls)})") from None

    def __lt__(self, other):
        return self._rank() < self._rank_of(other)

    def __le__(self, other):
        return self._rank() <= self._rank_of(other)

    def __gt__(self, other):
        return self._rank() > self._rank_of(other)

    def __ge__(self, other):
        return self._rank() >= self._rank_of(other)

    @classmethod
    def coerce(cls, value) -> "TEDAPIApiVersion":
        """Accept a TEDAPIApiVersion or a string (e.g. from an env var / CLI);
        unknown values fall back to V2024_06 with a warning.

        NOTE: This leniency is deliberate and intentionally OPPOSITE to the
        ordering operators above, which raise TypeError on unknown versions.
        coerce() sits at the config boundary (env vars, CLI, Docker PW_* vars)
        where a typo must degrade to the safe legacy query set rather than
        crash a 24/7 proxy; ordering sits in protocol-dispatch code where
        there is no safe True/False guess. Do not "harmonize" one to match
        the other — both are load-bearing.
        """
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


def _validate_member_labels() -> None:
    """Enforce the label contract at import.

    Ordering parses member labels as dates, so a member that does not match
    VYYYY_MM[_DD] would break comparisons at some arbitrary later call site.
    Failing at import points straight at the offending member instead.
    """
    for member in TEDAPIApiVersion:
        _parse_label(member.value)


_validate_member_labels()
