# pyPowerwall - TEDAPI energy_device.v1 status enums
# -*- coding: utf-8 -*-
"""Tesla ``energy_device.v1`` status enums, extracted from the Tesla One app.

These give the numeric status fields in the gateway firmware/system info their
string meaning (e.g. ``deviceType`` 4 -> ``DEVICE_TYPE_SITECONTROLLER``).
"""
from enum import IntEnum


class DeviceType(IntEnum):
    DEVICE_TYPE_INVALID = 0
    DEVICE_TYPE_GEN3WC = 1
    DEVICE_TYPE_PVCOM = 2
    DEVICE_TYPE_MSA = 3
    DEVICE_TYPE_SITECONTROLLER = 4


class UpdateStatus(IntEnum):
    UPDATE_STATUS_INVALID = 0
    UPDATE_STATUS_IDLE = 1
    UPDATE_STATUS_DOWNLOADING = 2
    UPDATE_STATUS_DOWNLOADED = 3
    UPDATE_STATUS_STAGED = 4


class UpdateHandshakeResult(IntEnum):
    UPDATE_HANDSHAKE_RESULT_INVALID = 0
    UPDATE_HANDSHAKE_RESULT_UNDERWAY = 1
    UPDATE_HANDSHAKE_RESULT_FAILED = 2
    UPDATE_HANDSHAKE_RESULT_NON_ACTIONABLE = 3
    UPDATE_HANDSHAKE_RESULT_UPDATE_STAGED = 4


class LastUpdateResult(IntEnum):
    LAST_UPDATE_RESULT_INVALID = 0
    LAST_UPDATE_RESULT_FAILED = 1
    LAST_UPDATE_RESULT_SUCCEEDED = 2


# SystemUpdate integer fields that carry an enum meaning (proto field names).
_SYSTEM_UPDATE_ENUM_FIELDS = {
    "updateStatus": UpdateStatus,
    "handshakeResult": UpdateHandshakeResult,
    "lastUpdateResult": LastUpdateResult,
}


def label(enum_cls, value):
    """Return the enum member name for ``value``, or ``"UNKNOWN (<value>)"`` for a
    value the app didn't define (so newer firmware can't crash the render)."""
    try:
        return enum_cls(value).name
    except ValueError:
        return f"UNKNOWN ({value})"


def resolve_system_update(system_update):
    """Return a copy of a ``systemUpdate`` dict with its integer status fields
    (updateStatus / handshakeResult / lastUpdateResult) rendered as their string
    names; other fields are left as-is."""
    out = dict(system_update)
    for key, enum_cls in _SYSTEM_UPDATE_ENUM_FIELDS.items():
        if key in out:
            out[key] = label(enum_cls, out[key])
    return out
