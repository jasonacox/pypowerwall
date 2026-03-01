# pyPowerWall - TEDAPIv1r Transport Class
# -*- coding: utf-8 -*-
"""
TEDAPIv1r — RSA-signed transport for Powerwall 3 LAN TEDapi (/tedapi/v1r)

This module provides authenticated access to the Tesla Powerwall TEDAPI
over the wired LAN using RSA-4096 signed protobuf messages. Unlike the
WiFi-only /tedapi/v1 endpoint (HTTP Basic auth), /tedapi/v1r uses RSA
signatures embedded in RoutableMessage protobufs for authentication.

Requires a pre-registered RSA-4096 key pair (see fleet_register.py).
"""

import json
import logging
import math
import ssl
import struct
import time
import uuid
from typing import Optional

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from . import tedapi_combined_pb2 as combined_pb2

urllib3.disable_warnings(InsecureRequestWarning)

log = logging.getLogger(__name__)


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

        # Load RSA private key
        from cryptography.hazmat.primitives import serialization
        try:
            with open(rsa_key_path, 'rb') as f:
                self._private_key = serialization.load_pem_private_key(f.read(), password=None)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"RSA private key not found at {rsa_key_path}. "
                "Run fleet_register.py to generate and register a key pair."
            )
        # Cache DER-encoded public key for signature identity
        self._public_key_der = self._private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.PKCS1
        )
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
            log.debug(f"v1r login successful, token: {self.token[:20]}...")
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
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        return self._private_key.sign(
            data=tlv_payload,
            padding=padding.PKCS1v15(),
            algorithm=hashes.SHA512(),
        )

    # ── v1r POST ─────────────────────────────────────────────────────

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

            # Parse response RoutableMessage
            resp_msg = combined_pb2.RoutableMessage()
            resp_msg.ParseFromString(r.content)

            # Check for message faults
            fault = resp_msg.signed_message_status.message_fault
            if fault != combined_pb2.MESSAGEFAULT_ERROR_NONE:
                fault_name = combined_pb2.MessageFault_E.Name(fault)
                if fault == combined_pb2.MESSAGEFAULT_ERROR_UNKNOWN_KEY_ID:
                    log.error(f"v1r response fault: {fault_name}")
                    log.error("RSA key not registered. Run fleet_register.py to register your key.")
                elif fault == combined_pb2.MESSAGEFAULT_ERROR_TIMEOUT:
                    log.debug(f"v1r response fault: {fault_name} (sub-device may not be routable via v1r)")
                else:
                    log.error(f"v1r response fault: {fault_name}")
                return None

            # Extract inner protobuf bytes
            inner = resp_msg.protobuf_message_as_bytes
            if not inner:
                log.error("v1r response has no protobuf_message_as_bytes")
                return None
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
        """
        msg = combined_pb2.Message()
        msg.message.deliveryChannel = combined_pb2.DELIVERY_CHANNEL_HERMES_COMMAND
        msg.message.sender.authorizedClient = 1
        msg.message.recipient.din = din
        return msg.message.SerializeToString()
