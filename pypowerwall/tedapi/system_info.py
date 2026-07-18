# pyPowerwall - TEDAPI firmware / system-info model
# -*- coding: utf-8 -*-
"""Normalized gateway firmware / system-info model.

Both TEDAPI parse paths populate this identically (verified byte-for-byte on live
hardware): the legacy ``firmware.system`` FirmwarePayload (V2024_06) and
``common.getSystemInfoResponse`` (V2026_06). All fields are JSON-safe (githash and
signatures are already decoded to str). :meth:`SystemInfo.to_details_dict` renders
the stable ``get_firmware_version(details=True)`` payload that predates the model.
"""
from dataclasses import dataclass, field, asdict
from operator import attrgetter
from typing import Any, Dict, List

from .enums import DeviceType, label, resolve_system_update


def decode_githash(value):
    """Render a firmware githash JSON-safe. It's a protobuf ``bytes`` field, so
    leaving it raw makes the details payload non-serializable. Decode printable
    ASCII as text (a git short-hash usually is), otherwise fall back to hex."""
    if not isinstance(value, (bytes, bytearray)):
        return value
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError:
        return value.hex()
    return text if text.isprintable() else value.hex()


@dataclass(frozen=True)
class _SysInfoSchema:
    """Protobuf field paths for one TEDAPI version's firmware/system-info message.
    This table IS the entire difference between the two versions: fields whose proto
    name matches across versions are defaulted, so a schema spells out ONLY what
    differs. ``message_path`` is the dotted path from the parsed envelope to the
    system-info message; ``radio_fields`` are the per-radio source field names
    mapping to (company, model, fcc_id, ic)."""
    message_path: str
    version: str
    githash: str
    part: str
    serial: str
    radios: str
    radio_fields: tuple
    din: str = "din"
    device_type: str = "deviceType"
    system_update: str = "systemUpdate"
    installed: str = "installedFirmwareSignature"
    offline: str = "offlineFirmwareSignature"


V2026_SYS_SCHEMA = _SysInfoSchema(
    message_path="common.getSystemInfoResponse",
    version="firmwareVersion.version",
    githash="firmwareVersion.githash",
    part="deviceId.partNumber",
    serial="deviceId.serialNumber",
    radios="complianceInformation.radioLegalInformation",
    radio_fields=("manufacturer", "model", "fccId", "icId")
)

V2024_SYS_SCHEMA = _SysInfoSchema(
    message_path="firmware.system",
    version="version.text",
    githash="version.githash",
    part="gateway.partNumber",
    serial="gateway.serialNumber",
    radios="wireless.device",
    radio_fields=("company", "model", "fcc_id", "ic")
)


@dataclass
class RadioDevice:
    """A wireless radio's regulatory identity.

    Tesla names this ``RadioLegalInformation`` (manufacturer/model/fccId/icId); the
    legacy proto names it ``DeviceInfo`` (company/model/fcc_id/ic). Same 4 fields.
    E.g. a Quectel cellular modem or a Murata Wi-Fi/BT module.
    """
    company: str = ""
    model: str = ""
    fcc_id: str = ""
    ic: str = ""


@dataclass
class SystemInfo:
    """Gateway firmware / system info, unified across the V2024_06 and V2026_06
    TEDAPI protobuf paths.

    Field-name provenance (Tesla's names, from energy_device.v1
    CommonAPIGetSystemInfoResponse; the legacy proto's reverse-engineered
    placeholders in parens): ``device_type`` (was ``six``), ``system_update``
    (was ``five``/FirmwareFive), ``installed_firmware_signature`` /
    ``offline_firmware_signature`` (were ``field8``/``field9``).
    """
    version: str = ""                          # firmware version string
    githash: str = ""                          # decoded (ascii or hex)
    din: str = ""
    gateway_part_number: str = ""
    gateway_serial_number: str = ""
    device_type: int = 0                       # Tesla DeviceType enum (4 = SITECONTROLLER)
    system_update: Dict[str, Any] = field(default_factory=dict)
    installed_firmware_signature: str = ""     # hex
    offline_firmware_signature: str = ""       # hex
    wireless: List[RadioDevice] = field(default_factory=list)

    @classmethod
    def from_proto(cls, envelope, schema: _SysInfoSchema) -> "SystemInfo":
        """Build from a parsed transport ``envelope`` using ``schema`` for the
        per-version field paths. Both TEDAPI versions funnel through here: the schema
        is the only thing that differs. Normalization (githash decode, signature hex,
        SystemUpdate -> dict, RadioDevice list) is shared."""
        from google.protobuf.json_format import MessageToDict
        info = attrgetter(schema.message_path)(envelope)

        def get(path):
            return attrgetter(path)(info)

        return cls(
            version=get(schema.version),
            githash=decode_githash(get(schema.githash)),
            din=get(schema.din),
            gateway_part_number=get(schema.part),
            gateway_serial_number=get(schema.serial),
            device_type=get(schema.device_type),
            system_update=MessageToDict(get(schema.system_update),
                                        preserving_proto_field_name=True),
            installed_firmware_signature=get(schema.installed).hex(),
            offline_firmware_signature=get(schema.offline).hex(),
            wireless=[RadioDevice(*(getattr(r, f).value for f in schema.radio_fields))
                      for r in get(schema.radios)],
        )

    @property
    def device_type_name(self) -> str:
        """The DeviceType enum name for :attr:`device_type` (e.g.
        ``DEVICE_TYPE_SITECONTROLLER``)."""
        return label(DeviceType, self.device_type)

    def to_details_dict(self) -> Dict[str, Any]:
        """Render the ``get_firmware_version(details=True)`` payload. The status
        enums (``deviceType`` and the ``systemUpdate`` result fields) are rendered
        as their string names instead of raw ints, so the output reads meaningfully;
        the raw ints remain on the model (``device_type``, ``system_update``)."""
        return {"system": {
            "gateway": {"partNumber": self.gateway_part_number,
                        "serialNumber": self.gateway_serial_number},
            "din": self.din,
            "version": {"text": self.version, "githash": self.githash},
            "deviceType": self.device_type_name,
            "systemUpdate": resolve_system_update(self.system_update),
            "installedFirmwareSignature": self.installed_firmware_signature,
            "offlineFirmwareSignature": self.offline_firmware_signature,
            "wireless": {"device": [asdict(d) for d in self.wireless]},
        }}
