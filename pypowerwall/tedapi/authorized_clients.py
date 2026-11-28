# pyPowerwall - TEDAPI authorized clients (paired keys) model
# -*- coding: utf-8 -*-
"""
 Tesla TEDAPI Authorized Clients

 Model for the gateway's authorized clients: the public keys (Tesla app,
 vehicles, v1r clients such as pypowerwall) that may send signed commands.

 The data comes from the ``authorization`` TEDAPI messages (see
 ``protobuf/V2024_06/tedapi_combined.proto``):
    * list_authorized_clients_request (read-only) -- validated on a Powerwall 3,
      firmware 26.34.3, over signed v1r and Gateway Wi-Fi basic auth
      (2026-11-14);
    * add_authorized_client_request / remove_authorized_client_request --
      sent over signed v1r only; validated on the same Powerwall 3
      (2026-11-14). A removed key disappears from the list.

 A newly added key waits in PENDING_VERIFICATION for about 10 minutes. A key
 added over signed v1r is not vouched for by the signing key (it is listed
 as PENDING_VERIFICATION, verification HERMES_COMMAND, no authorized_by), and
 a key added locally over Gateway Wi-Fi basic auth never verified on a Powerwall 3
 (firmware 26.34.1, 2026-10-29): the On/Off switch toggle that verifies keys
 registered through Tesla's cloud did not verify it, and it timed out.

 Keys are DER encoded; RSA keys are PKCS#1, the encoding v1r_register.py
 registers and the gateway lists back. The SHA-256 fingerprint of that DER is
 the same fingerprint 'python -m pypowerwall register' and the v1r transport
 print for a key.

 Privacy:
    Descriptions (often a device or person's name) and identifiers are only
    returned with ``details=True`` and are kept out of the model's ``repr``.

 Classes:
    AuthorizedClient - One authorized client record
    AuthorizedClients - All records plus the gateway's line-switch flag

 Functions:
    fingerprint(public_key) - SHA-256 hex fingerprint of a DER public key
    rsa_public_key_der(key) - PKCS#1 DER for an RSA key given as PEM / DER / base64
    public_key_bytes(key) - Raw key bytes for a key given as listed (base64), PEM or DER

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
"""
import base64
import binascii
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2

KeyInput = Union[bytes, bytearray, str]

# Enum name prefixes, stripped for display (``AUTHORIZED_STATE_VERIFIED`` ->
# ``VERIFIED``, as in the README's key-state table and v1r_register.py).
_PREFIXES = {
    'AuthorizedClientType': 'AUTHORIZED_CLIENT_TYPE_',
    'AuthorizedKeyType': 'AUTHORIZED_KEY_TYPE_',
    'AuthorizationRole': 'AUTHORIZATION_ROLE_',
    'AuthorizedState': 'AUTHORIZED_STATE_',
    'AuthorizedVerificationType': 'AUTHORIZED_VERIFICATION_TYPE_',
}


def enum_label(enum_type, value: int) -> str:
    """Short name of a protobuf enum value (``VERIFIED``), or
    ``"UNKNOWN (<value>)"`` for a value this schema does not define."""
    try:
        name = enum_type.Name(value)
    except ValueError:
        return f'UNKNOWN ({value})'
    prefix = _PREFIXES.get(enum_type.DESCRIPTOR.name, '')
    return name[len(prefix):] if name.startswith(prefix) else name


def fingerprint(public_key: bytes) -> Optional[str]:
    """SHA-256 hex fingerprint of DER public key bytes, or None when empty."""
    if not public_key:
        return None
    return hashlib.sha256(bytes(public_key)).hexdigest()


def _as_bytes(key: KeyInput) -> bytes:
    if isinstance(key, (bytes, bytearray)):
        return bytes(key)
    if isinstance(key, str):
        return key.strip().encode('ascii', errors='strict')
    raise ValueError('public key must be bytes or str')


def _is_pem(data: bytes) -> bool:
    return data.lstrip().startswith(b'-----BEGIN ')


def _b64decode(data: bytes) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('public key is not PEM, DER or base64') from exc


def _load_public_key(data: bytes):
    """A cryptography public key object for PEM (public or private, the latter
    reduced to its public half) or DER (PKCS#1 or SubjectPublicKeyInfo)."""
    from cryptography.hazmat.primitives import serialization
    if _is_pem(data):
        if b'PRIVATE KEY-----' in data:
            return serialization.load_pem_private_key(data, password=None).public_key()
        return serialization.load_pem_public_key(data)
    return serialization.load_der_public_key(data)


def rsa_public_key_der(key: KeyInput) -> bytes:
    """PKCS#1 DER of an RSA public key, the encoding the gateway registers.

    ``key`` may be a PEM public key, a PEM private key (only its public half is
    used; nothing is kept), DER bytes (PKCS#1 or SubjectPublicKeyInfo), or a
    base64 string of the DER. Raises ValueError for anything else, including
    non-RSA keys."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    data = _as_bytes(key)
    if not data:
        raise ValueError('public key is empty')
    if not _is_pem(data) and isinstance(key, str):
        data = _b64decode(data)
    try:
        public_key = _load_public_key(data)
    except (ValueError, TypeError) as exc:
        raise ValueError('public key could not be read (expected an RSA key as PEM, DER or base64)') from exc
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError('only RSA keys can be added')
    return public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.PKCS1)


def public_key_bytes(key: KeyInput) -> bytes:
    """Key bytes to identify an existing client: raw DER bytes as given, the
    base64 string exactly as listed (``public_key`` with ``details=True``), or
    a PEM key (an RSA key is converted to the PKCS#1 DER the gateway lists).
    Raises ValueError for empty or undecodable input."""
    data = _as_bytes(key)
    if not data:
        raise ValueError('public key is empty')
    if _is_pem(data):
        return rsa_public_key_der(data)
    if isinstance(key, str):
        data = _b64decode(data)
    return data


def _timestamp(value) -> Optional[datetime]:
    if not value.seconds and not value.nanos:
        return None
    return datetime.fromtimestamp(value.seconds + value.nanos / 1e9, tz=timezone.utc)


@dataclass
class AuthorizedClient:
    """One authorized client record. Enum fields hold the raw protobuf values;
    ``to_dict`` renders their short names. The description and identifier are
    excluded from ``repr`` so they do not end up in debug logs."""
    public_key: bytes = field(default=b'', repr=False)
    type: int = 0                                  # AuthorizedClientType
    key_type: int = 0                              # AuthorizedKeyType
    roles: List[int] = field(default_factory=list)  # AuthorizationRole
    state: int = 0                                 # AuthorizedState
    verification: int = 0                          # AuthorizedVerificationType
    added_time: Optional[datetime] = None
    authorized_by_public_key: bytes = field(default=b'', repr=False)
    description: str = field(default='', repr=False)
    identifier: str = field(default='', repr=False)

    @classmethod
    def from_proto(cls, record) -> 'AuthorizedClient':
        """Build from a parsed ``AuthorizationRecord`` protobuf message."""
        return cls(
            public_key=bytes(record.public_key),
            type=record.type,
            key_type=record.key_type,
            roles=list(record.roles),
            state=record.state,
            verification=record.verification,
            added_time=_timestamp(record.added_time) if record.HasField('added_time') else None,
            authorized_by_public_key=bytes(record.authorized_by_public_key),
            description=record.description,
            identifier=record.identifier,
        )

    @property
    def fingerprint(self) -> Optional[str]:
        """SHA-256 fingerprint of the client's public key."""
        return fingerprint(self.public_key)

    @property
    def state_name(self) -> str:
        """Short AuthorizedState name, e.g. ``VERIFIED``."""
        return enum_label(combined_pb2.AuthorizedState, self.state)

    def to_dict(self, details: bool = False, current_key: Optional[bytes] = None) -> Dict[str, Any]:
        """Render the JSON-safe payload for this client. ``current_key`` (the
        DER key this connection signs with, if any) sets ``current_key``;
        without it the value is None. ``details`` adds the description,
        identifier and base64 public key."""
        data: Dict[str, Any] = {
            'fingerprint': self.fingerprint,
            'type': enum_label(combined_pb2.AuthorizedClientType, self.type),
            'key_type': enum_label(combined_pb2.AuthorizedKeyType, self.key_type),
            'roles': [enum_label(combined_pb2.AuthorizationRole, role) for role in self.roles],
            'state': self.state_name,
            'verification': enum_label(combined_pb2.AuthorizedVerificationType, self.verification),
            'added_time': self.added_time.isoformat() if self.added_time else None,
            'authorized_by': fingerprint(self.authorized_by_public_key),
            'current_key': None if current_key is None else self.public_key == current_key,
        }
        if details:
            data['description'] = self.description or None
            data['identifier'] = self.identifier or None
            data['public_key'] = base64.b64encode(self.public_key).decode('ascii') if self.public_key else None
        return data


@dataclass
class AuthorizedClients:
    """All authorized client records, in the gateway's order, and the
    gateway's ``enable_line_switch_off`` flag (meaning not documented)."""
    clients: List[AuthorizedClient] = field(default_factory=list)
    enable_line_switch_off: bool = False

    @classmethod
    def from_proto(cls, response) -> 'AuthorizedClients':
        """Build from a parsed ``AuthorizationAPIListAuthorizedClientsResponse``."""
        return cls(clients=[AuthorizedClient.from_proto(r) for r in response.clients],
                   enable_line_switch_off=response.enable_line_switch_off)

    def find(self, prefix: str) -> List[AuthorizedClient]:
        """Clients whose fingerprint starts with ``prefix`` (case-insensitive)."""
        prefix = prefix.lower()
        return [c for c in self.clients if c.fingerprint and c.fingerprint.startswith(prefix)]

    def to_dict(self, details: bool = False, current_key: Optional[bytes] = None) -> Dict[str, Any]:
        """Render the ``get_authorized_clients()`` payload."""
        return {
            'clients': [c.to_dict(details=details, current_key=current_key) for c in self.clients],
            'enable_line_switch_off': self.enable_line_switch_off,
        }
