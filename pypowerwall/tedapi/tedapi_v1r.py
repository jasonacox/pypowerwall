# pyPowerWall - TEDAPIv1r Transport Class
# -*- coding: utf-8 -*-
"""
TEDAPIv1r — RSA-signed transport for Powerwall 3 LAN TEDapi (/tedapi/v1r)

This module provides authenticated access to the Tesla Powerwall TEDAPI
over the wired LAN using RSA-4096 signed protobuf messages. Unlike the
WiFi-only /tedapi/v1 endpoint (HTTP Basic auth), /tedapi/v1r uses RSA
signatures embedded in RoutableMessage protobufs for authentication.

Requires a pre-registered RSA-4096 key pair (see v1r_register.py).
"""

import hashlib
import json
import logging
import math
import struct
import time
import uuid
import warnings
from typing import Optional, Tuple

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from .protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2

urllib3.disable_warnings(InsecureRequestWarning)

log = logging.getLogger(__name__)


def _decode_payload_preview(raw: bytes, max_len: int = 200) -> str:
    """Return a human-readable preview of a raw gateway response for diagnostics."""
    try:
        text = raw.decode('utf-8', errors='replace').strip()
        if text and any(32 <= ord(c) < 127 for c in text[:20]):
            return repr(text[:max_len])
    except Exception:
        pass
    return raw[:max_len].hex()


def _encode_varint(value: int) -> bytes:
    """Encode a non-negative protobuf varint."""
    if value < 0:
        raise ValueError("protobuf varint must be non-negative")
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _read_varint(payload: bytes, offset: int) -> Tuple[int, int]:
    """Read one protobuf varint and return its value and next offset."""
    value = 0
    shift = 0
    while offset < len(payload):
        current = payload[offset]
        offset += 1
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value, offset
        shift += 7
        if shift >= 64:
            break
    raise ValueError("invalid protobuf varint")


def _length_delimited_field(payload: bytes, wanted_field: int) -> Optional[bytes]:
    """Return the first length-delimited protobuf field with the given number."""
    offset = 0
    while offset < len(payload):
        key, offset = _read_varint(payload, offset)
        field_number, wire_type = key >> 3, key & 0x07
        if wire_type == 0:
            _, offset = _read_varint(payload, offset)
            continue
        if wire_type == 2:
            length, offset = _read_varint(payload, offset)
            end = offset + length
            if end > len(payload):
                raise ValueError("truncated protobuf length-delimited field")
            if field_number == wanted_field:
                return payload[offset:end]
            offset = end
            continue
        if wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        if offset > len(payload):
            raise ValueError("truncated protobuf fixed-width field")
    return None


def _island_mode_response_result(teg_payload: bytes) -> Optional[int]:
    """Return setIslandModeResponse.result (TEG oneof field 4), if present."""
    response_payload = _length_delimited_field(teg_payload, wanted_field=4)
    if response_payload is None:
        return None
    offset = 0
    while offset < len(response_payload):
        key, offset = _read_varint(response_payload, offset)
        field_number, wire_type = key >> 3, key & 0x07
        if wire_type == 0:
            value, offset = _read_varint(response_payload, offset)
            if field_number == 1:
                return value
            continue
        if wire_type == 2:
            length, offset = _read_varint(response_payload, offset)
            offset += length
        elif wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        if offset > len(response_payload):
            raise ValueError("truncated setIslandModeResponse field")
    return None


class TEDAPIv1r:
    """RSA-signed transport for Powerwall /tedapi/v1r endpoint."""

    def __init__(self, host: str, password: str, rsa_key_path: str,
                 timeout: int = 5, poolmaxsize: int = 10) -> None:
        self.host = host
        self.password = password
        self.timeout = timeout
        self.poolmaxsize = poolmaxsize
        self.token: Optional[str] = None
        self.din: Optional[str] = None
        # Tracks key-auth failure state so warnings fire once per session
        self.pending_verification: bool = False
        self.key_unknown: bool = False

        # Load RSA private key
        from cryptography.hazmat.primitives import serialization
        try:
            with open(rsa_key_path, 'rb') as f:
                self._private_key = serialization.load_pem_private_key(f.read(), password=None)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"RSA private key not found at {rsa_key_path}. "
                "Run v1r_register.py (or: python -m pypowerwall register) to generate and register a key pair."
            )
        # Cache DER-encoded public key for signature identity
        self._public_key_der = self._private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.PKCS1
        )
        # SHA-256 fingerprint of the public key in use. Included in key-auth
        # failure messages so users can compare against the fingerprint printed
        # by 'python -m pypowerwall register' — key mismatches from multiple
        # registration attempts are a common root cause (see issue #352).
        self.key_fingerprint = hashlib.sha256(self._public_key_der).hexdigest()
        log.debug(f"v1r RSA public key fingerprint (SHA256): {self.key_fingerprint}")
        # HTTP session (no Basic auth — v1r uses RSA signatures)
        self.session = self._init_session()

    def _init_session(self) -> requests.Session:
        """Initialize requests session for v1r communication."""
        session = requests.Session()
        if self.poolmaxsize > 0:
            retries = urllib3.Retry(total=3, backoff_factor=1, raise_on_status=False)
            adapter = requests.adapters.HTTPAdapter(
                max_retries=retries,
                pool_connections=self.poolmaxsize,
                pool_maxsize=self.poolmaxsize,
                pool_block=True,
            )
            session.mount("https://", adapter)
        else:
            session.headers.update({'Connection': 'close'})
        session.verify = False
        return session

    def login(self) -> bool:
        """Login via POST /api/login/Basic to get Bearer token."""
        url = f'https://{self.host}/api/login/Basic'
        payload = json.dumps({
            "username": "customer",
            "password": self.password,
            "email": "customer@customer.domain",
            "clientInfo": {"timezone": "America/Chicago"},
        })
        try:
            r = self.session.post(url, data=payload,
                                  headers={'Content-Type': 'application/json'},
                                  timeout=self.timeout)
            if r.status_code != 200:
                log.error(f"v1r login failed ({r.status_code}): {r.text}")
                return False
            data = r.json()
            self.token = data.get("token")
            log.debug(f"v1r login successful, token: [redacted] (len={len(self.token) if self.token else 0})")
            return True
        except Exception as e:
            log.error(f"v1r login error: {e}")
            return False

    def get_din(self) -> Optional[str]:
        """Get DIN via GET /tedapi/din with Bearer auth."""
        url = f'https://{self.host}/tedapi/din'
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        try:
            r = self.session.get(url, headers=headers, timeout=self.timeout)
            if r.status_code != 200:
                log.error(f"v1r get_din failed ({r.status_code})")
                return None
            self.din = r.text.strip()
            log.debug(f"v1r DIN: {self.din}")
            return self.din
        except Exception as e:
            log.error(f"v1r get_din error: {e}")
            return None

    # ── TLV + RSA Signing ────────────────────────────────────────────

    @staticmethod
    def _to_tlv(tag: int, value_bytes: bytes) -> bytes:
        """Encode a single tag-length-value entry."""
        return bytes([tag]) + bytes([len(value_bytes)]) + value_bytes

    def _build_tlv_payload(self, din: str, expires_at: int,
                           inner_bytes: bytes) -> bytes:
        """Build TLV-encoded payload for RSA signature."""
        return b''.join([
            self._to_tlv(0, bytes([7])),                    # TAG_SIGNATURE_TYPE = RSA (7)
            self._to_tlv(1, bytes([7])),                    # TAG_DOMAIN = ENERGY_DEVICE (7)
            self._to_tlv(2, din.encode()),                  # TAG_PERSONALIZATION = DIN
            self._to_tlv(4, struct.pack('>I', expires_at)), # TAG_EXPIRES_AT
            bytes([255]),                                   # TAG_END (0xFF)
            inner_bytes,                                    # protobuf_message_as_bytes
        ])

    def _sign(self, tlv_payload: bytes) -> bytes:
        """RSA PKCS1v15 + SHA-512 sign the TLV payload."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        return self._private_key.sign(
            data=tlv_payload,
            padding=padding.PKCS1v15(),
            algorithm=hashes.SHA512(),
        )

    # ── v1r POST ─────────────────────────────────────────────────────

    def _key_auth_warning(self, flag: str, msg: str) -> None:
        """Log a key-auth failure and emit a UserWarning once per failure episode.

        The flag ('pending_verification' or 'key_unknown') suppresses repeat
        warnings while the condition persists; it is cleared by post_v1r() on
        the next successful response so a later recurrence warns again.
        """
        log.error("v1r: %s", msg)
        if not getattr(self, flag):
            setattr(self, flag, True)
            warnings.warn(msg, UserWarning, stacklevel=3)

    def post_v1r(self, envelope_bytes: bytes, din: str) -> Optional[bytes]:
        """
        Wrap envelope_bytes in a signed RoutableMessage and POST to /tedapi/v1r.

        Args:
            envelope_bytes: Serialized inner protobuf (MessageEnvelope or tedapi_pb2.Message)
            din: Device Identification Number

        Returns:
            Raw protobuf_message_as_bytes from the response RoutableMessage, or None on error.
        """
        # Build RoutableMessage
        routable = combined_pb2.RoutableMessage()
        routable.to_destination.domain = combined_pb2.DOMAIN_ENERGY_DEVICE
        routable.protobuf_message_as_bytes = envelope_bytes
        routable.uuid = str(uuid.uuid4()).encode()

        # Build TLV and sign
        expires_at = math.ceil(time.time()) + 12
        tlv_payload = self._build_tlv_payload(din, expires_at,
                                              routable.protobuf_message_as_bytes)
        signature = self._sign(tlv_payload)

        # Attach signature to RoutableMessage
        routable.signature_data.signer_identity.public_key = self._public_key_der
        routable.signature_data.rsa_data.expires_at = expires_at
        routable.signature_data.rsa_data.signature = signature

        # POST
        url = f'https://{self.host}/tedapi/v1r'
        payload = routable.SerializeToString()
        headers = {'Content-Type': 'application/octet-stream'}

        try:
            r = self.session.post(url, data=payload, headers=headers,
                                  timeout=self.timeout)
            if r.status_code == 401 or r.status_code == 403:
                log.warning(f"v1r auth error ({r.status_code}), attempting re-login")
                if self.login():
                    # Retry once after re-login
                    r = self.session.post(url, data=payload, headers=headers,
                                          timeout=self.timeout)
                else:
                    return None
            if r.status_code != 200:
                log.error(f"v1r POST failed ({r.status_code})")
                return None

            response_size = len(r.content)

            # Parse response RoutableMessage
            resp_msg = combined_pb2.RoutableMessage()
            resp_msg.ParseFromString(r.content)

            # Check for message faults
            fault = resp_msg.signed_message_status.message_fault
            if fault != combined_pb2.MESSAGEFAULT_ERROR_NONE:
                fault_name = combined_pb2.MessageFault_E.Name(fault)
                if fault == combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID:
                    raw_preview = _decode_payload_preview(r.content)
                    msg = (
                        "v1r RSA key is not recognized by the gateway (UNKNOWN_KEY_ID). "
                        "The key file may not match the registered key, or no key has been "
                        "registered. Run 'python -m pypowerwall register' to register or "
                        f"verify your key. Key fingerprint in use (SHA256): {self.key_fingerprint} "
                        f"Gateway payload ({response_size} bytes): {raw_preview} "
                        "See: https://github.com/jasonacox/pypowerwall/issues/274"
                    )
                    self._key_auth_warning('key_unknown', msg)
                elif fault == combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT:
                    log.debug(f"v1r response fault: {fault_name} (sub-device may not be routable via v1r)")
                else:
                    log.error(f"v1r response fault: {fault_name}")
                return None

            # Extract inner protobuf bytes
            inner = resp_msg.protobuf_message_as_bytes
            raw_lower = r.content.lower()

            # Check for plain-text authorization errors in raw response or inner payload.
            # When the RSA key is registered but not yet verified, the gateway
            # returns HTTP 200 with MESSAGEFAULT_ERROR_NONE but the payload
            # contains a plain-text error like "v1r: client authorization not verified"
            # instead of a valid protobuf inner payload.
            if b'authorization not verified' in raw_lower or (inner and b'authorization not verified' in inner.lower()):
                raw_preview = _decode_payload_preview(r.content)
                msg = (
                    "v1r RSA key is registered but not yet VERIFIED by the gateway "
                    "(PENDING_VERIFICATION). "
                    "Toggle ONE Powerwall circuit breaker OFF, wait 2 seconds, then back ON. "
                    "Wait 30-60 seconds, then retry. "
                    "Run 'python -m pypowerwall register' to check key state. "
                    f"Gateway payload ({response_size} bytes): {raw_preview} "
                    "See: https://github.com/jasonacox/pypowerwall/issues/274"
                )
                self._key_auth_warning('pending_verification', msg)
                return None

            if not inner:
                # Empty inner payload with no recognized fault code — the response
                # may be a plain-text or binary auth rejection the gateway didn't
                # encode as a fault.  Reveal the raw payload so users can troubleshoot.
                raw_preview = _decode_payload_preview(r.content)
                msg = (
                    f"v1r key authentication failed — gateway returned an unexpected "
                    f"response ({response_size} bytes) with no data. "
                    f"Gateway payload: {raw_preview} "
                    "The RSA key may not be registered or recognized by this gateway. "
                    f"Key fingerprint in use (SHA256): {self.key_fingerprint} "
                    "Run 'python -m pypowerwall register' to register or verify your key. "
                    "See: https://github.com/jasonacox/pypowerwall/issues/274"
                )
                self._key_auth_warning('key_unknown', msg)
                return None

            # Success — if a previous call flagged a key-auth failure, the key
            # has since been verified/recognized (e.g., breaker toggle completed
            # while running). Clear the flags so any future failure warns again.
            if self.pending_verification or self.key_unknown:
                log.info("v1r: key authentication recovered — gateway accepted signed request")
                self.pending_verification = False
                self.key_unknown = False

            return inner

        except Exception as e:
            log.error(f"v1r POST error: {e}")
            return None

    def get_config_v1r(self, din: str) -> Optional[dict]:
        """
        Get config.json via v1r using FileStore protobuf format.

        v1r uses a different message format than v1 for config requests:
        - v1:  tedapi_pb2.Message with config.send.file = "config.json"
        - v1r: tedapi_combined_pb2.Message with filestore.readFileRequest
        """
        # Build inner MessageEnvelope for config request
        msg = combined_pb2.Message()
        msg.message.deliveryChannel = combined_pb2.DELIVERY_CHANNEL_HERMES_COMMAND
        msg.message.sender.authorizedClient = 1
        msg.message.recipient.din = din
        msg.message.filestore.readFileRequest.domain = combined_pb2.FILE_STORE_API_DOMAIN_CONFIG_JSON
        msg.message.filestore.readFileRequest.name = 'config.json'

        envelope_bytes = msg.message.SerializeToString()
        inner = self.post_v1r(envelope_bytes, din)
        if not inner:
            return None

        # Parse response — extract JSON from filestore response
        try:
            resp_envelope = combined_pb2.MessageEnvelope()
            resp_envelope.ParseFromString(inner)
            if resp_envelope.HasField('filestore'):
                blob = resp_envelope.filestore.readFileResponse.file.blob
                return json.loads(blob.decode('utf-8'))
        except Exception:
            pass

        # Fallback: find JSON in raw bytes
        try:
            text = inner.decode('utf-8', errors='replace')
            json_start = text.find('{')
            if json_start >= 0:
                # Find matching closing brace
                depth = 0
                for i, ch in enumerate(text[json_start:], json_start):
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            return json.loads(text[json_start:i + 1])
        except Exception as e:
            log.error(f"v1r config parse error: {e}")

        return None

    def write_config_v1r(self, din: str, updates: dict) -> bool:
        """
        Write config.json via v1r using FileStore updateFileRequest (read-modify-write).

        1. Read current config via readFileRequest to get blob + hash
        2. Apply updates (dotted-path keys) to the config dict
        3. Write back via updateFileRequest with the original hash (optimistic lock)

        Args:
            din: Device DIN
            updates: dict of dotted paths to values, e.g. {'site_info.backup_reserve_percent': 5}
        Returns:
            True on success, False on error.
        """
        # Step 1: Read current config + hash
        msg = combined_pb2.Message()
        msg.message.deliveryChannel = combined_pb2.DELIVERY_CHANNEL_HERMES_COMMAND
        msg.message.sender.authorizedClient = 1
        msg.message.recipient.din = din
        msg.message.filestore.readFileRequest.domain = combined_pb2.FILE_STORE_API_DOMAIN_CONFIG_JSON
        msg.message.filestore.readFileRequest.name = 'config.json'

        envelope_bytes = msg.message.SerializeToString()
        inner = self.post_v1r(envelope_bytes, din)
        if not inner:
            log.error("write_config_v1r: failed to read current config")
            return False

        # Parse response to get blob + hash
        try:
            resp_envelope = combined_pb2.MessageEnvelope()
            resp_envelope.ParseFromString(inner)
            if not resp_envelope.HasField('filestore'):
                log.error("write_config_v1r: no filestore in response")
                return False
            blob = resp_envelope.filestore.readFileResponse.file.blob
            config_hash = resp_envelope.filestore.readFileResponse.hash
            config = json.loads(blob.decode('utf-8'))
        except Exception as e:
            log.error(f"write_config_v1r: failed to parse config response: {e}")
            return False

        # Step 2: Apply updates
        for dotted_path, value in updates.items():
            keys = dotted_path.split('.')
            d = config
            for key in keys[:-1]:
                if key not in d or not isinstance(d[key], dict):
                    d[key] = {}
                d = d[key]
            d[keys[-1]] = value
        log.debug(f"write_config_v1r: applying updates {updates}")

        # Step 3: Write back via updateFileRequest
        write_msg = combined_pb2.Message()
        write_msg.message.deliveryChannel = combined_pb2.DELIVERY_CHANNEL_HERMES_COMMAND
        write_msg.message.sender.authorizedClient = 1
        write_msg.message.recipient.din = din
        update_req = write_msg.message.filestore.updateFileRequest
        update_req.domain = combined_pb2.FILE_STORE_API_DOMAIN_CONFIG_JSON
        update_req.file.name = 'config.json'
        update_req.file.blob = json.dumps(config).encode('utf-8')
        update_req.hash = config_hash

        write_envelope = write_msg.message.SerializeToString()
        write_inner = self.post_v1r(write_envelope, din)
        if not write_inner:
            log.error("write_config_v1r: failed to write config")
            return False

        # Parse write response
        try:
            write_resp = combined_pb2.MessageEnvelope()
            write_resp.ParseFromString(write_inner)
            if write_resp.HasField('filestore'):
                # updateFileResponse means success
                log.info(f"write_config_v1r: config updated successfully: {list(updates.keys())}")
                return True
            # Check for error
            if write_resp.HasField('error'):
                log.error(f"write_config_v1r: error response: {write_resp.error}")
                return False
        except Exception as e:
            log.error(f"write_config_v1r: failed to parse write response: {e}")
            return False

        log.error("write_config_v1r: unexpected response")
        return False

    # ── TEGMessages Command ───────────────────────────────────────────

    def send_teg_message(self, din: str, teg_message) -> Optional[combined_pb2.MessageEnvelope]:
        """
        Send a TEGMessages command via v1r, return parsed response envelope.

        Args:
            din: Device DIN (leader)
            teg_message: A populated TEGMessages protobuf instance

        Returns:
            Parsed MessageEnvelope from the response, or None on error.
        """
        msg = combined_pb2.MessageEnvelope()
        msg.deliveryChannel = combined_pb2.DELIVERY_CHANNEL_HERMES_COMMAND
        msg.sender.authorizedClient = 1  # CUSTOMER_MOBILE_APP
        msg.recipient.din = din
        msg.teg.CopyFrom(teg_message)

        envelope_bytes = msg.SerializeToString()
        inner = self.post_v1r(envelope_bytes, din)
        if not inner:
            return None
        try:
            resp = combined_pb2.MessageEnvelope()
            resp.ParseFromString(inner)
            return resp
        except Exception as e:
            log.error(f"send_teg_message: failed to parse response: {e}")
            return None

    def send_island_mode(self, din: str, mode: int, force: bool = False) -> Optional[dict]:
        """Send Tesla's legacy TEGAPISetIslandModeRequest via signed v1r.

        The current V2024_06 generated protobuf set begins its TEG command
        fields at 45, while Tesla's islanding command is defined in the older
        TEG schema as oneof field 3. Build that wire encoding directly inside a
        MessageEnvelope so it can still use the normal signed /tedapi/v1r path.
        """
        if mode not in (1, 6):
            raise ValueError("island mode must be 1 (reconnect) or 6 (off-grid)")

        # TEGAPISetIslandModeRequest: int32 mode = 1; bool force = 2.
        request = b"\x08" + _encode_varint(mode)
        if force:
            request += b"\x10\x01"
        # TEGMessages.setIslandModeRequest is legacy oneof field 3.
        teg_payload = b"\x1a" + _encode_varint(len(request)) + request

        try:
            envelope = combined_pb2.MessageEnvelope()
            envelope.deliveryChannel = combined_pb2.DELIVERY_CHANNEL_HERMES_COMMAND
            envelope.sender.authorizedClient = 1  # CUSTOMER_MOBILE_APP
            envelope.recipient.din = din
            # MessageEnvelope.teg is field 5. Appending preserves the legacy
            # field 3 within TEGMessages, which the generated class omits.
            envelope_bytes = envelope.SerializeToString()
            envelope_bytes += b"\x2a" + _encode_varint(len(teg_payload)) + teg_payload
            response_bytes = self.post_v1r(envelope_bytes, din)
            if not response_bytes:
                log.error("send_island_mode: no v1r response")
                return None

            response_teg = _length_delimited_field(response_bytes, wanted_field=5)
            result = (
                _island_mode_response_result(response_teg)
                if response_teg is not None else None
            )
            if result is None:
                log.warning("send_island_mode: response omitted setIslandModeResponse.result")
            return {"mode": mode, "force": force, "result": result}
        except Exception as e:
            log.error(f"send_island_mode error: {e}")
            return None

    # ── Standard API (Bearer token) ──────────────────────────────────

    def api_get(self, path: str) -> Optional[dict]:
        """
        Make authenticated GET request to standard Powerwall API endpoints.

        These endpoints work on the wired LAN with Bearer token auth:
        /api/meters/aggregates, /api/system_status/soe, /api/system_status/grid_status, etc.

        Args:
            path: API path (e.g., '/api/meters/aggregates')

        Returns:
            Parsed JSON response dict, or None on error.
        """
        url = f'https://{self.host}{path}'
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        try:
            r = self.session.get(url, headers=headers, timeout=self.timeout)
            if r.status_code in (401, 403):
                log.warning(f"v1r api_get auth error ({r.status_code}), attempting re-login")
                if self.login():
                    headers['Authorization'] = f'Bearer {self.token}'
                    r = self.session.get(url, headers=headers, timeout=self.timeout)
                else:
                    return None
            if r.status_code != 200:
                log.error(f"v1r api_get {path} failed ({r.status_code})")
                return None
            return r.json()
        except Exception as e:
            log.error(f"v1r api_get {path} error: {e}")
            return None

    def build_query_envelope(self, din: str, query_pb_bytes: bytes) -> bytes:
        """
        Build a v1r envelope wrapping an inner tedapi_pb2.Message (status/components/etc).

        For GraphQL-style queries (get_status, get_components, etc.), the inner
        protobuf is identical to the WiFi v1 format (tedapi_pb2.Message with
        ECDSA codes). We just need to wrap it differently for v1r transport.

        The inner tedapi_pb2.Message bytes are placed inside a MessageEnvelope
        using deliveryChannel=HERMES_COMMAND and sender.authorizedClient=1.

        NOTE: This method is not used by the current transport.  The active v1r
        transport path in TEDAPI._post_tedapi() extracts the MessageEnvelope
        directly from a tedapi_pb2.Message rather than building a combined_pb2
        wrapper.  This stub is retained for reference but raises NotImplementedError
        to prevent accidental use with incorrect (empty) output.
        """
        raise NotImplementedError(
            "build_query_envelope is not implemented. "
            "Use TEDAPI._post_tedapi() which extracts the envelope from a "
            "tedapi_pb2.Message directly."
        )
