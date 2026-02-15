#!/usr/bin/env python3
"""
Tesla Powerwall LAN-Based TEDAPI Access Script

Enables direct local network communication with Tesla Powerwall gateways using
the TEDAPI (Tesla Energy Device API) protocol with RSA-signed messages.

HOW IT WORKS:
    This script uses a hybrid cloud + LAN approach:
    
    SETUP PHASE (Cloud - one time):
    1. Authenticate with Tesla via OAuth (using pypowerwall's TeslaPy)
    2. Query Tesla Cloud API to discover your Powerwall gateway details
    3. Generate RSA-4096 key pair locally
    4. Register public key with gateway via Tesla Cloud API
    5. Physical confirmation required: toggle any Powerwall switch OFF/ON
       within 30 seconds to approve the pairing
    
    OPERATION PHASE (LAN - ongoing):
    6. Build TEDAPI protobuf messages locally
    7. Sign messages with RSA private key
    8. Send signed requests directly to Powerwall's local IP via HTTPS
    9. Receive and parse responses
    
    After initial pairing, all communication happens over your local network
    without requiring internet access (except for OAuth token refresh).

REQUIREMENTS:
    pip install pypowerwall requests cryptography protobuf

REQUIRED FILES:
    - tedapi_combined_pb2.py (protobuf generated file)
    - tedapi_combined.proto (optional, for regenerating protobuf)

USAGE:
    python lan_tedapi.py
    
    First Run:
    - Enter Tesla account email
    - Enter Powerwall local IP (e.g., https://192.168.91.1)
    - Complete OAuth in browser
    - Toggle Powerwall switch when prompted
    - Script retrieves config.json from gateway
    
    Subsequent Runs:
    - Uses saved credentials automatically
    - Sends requests directly over LAN
    - No switch toggle required

OUTPUT FILES (auto-generated):
    - .pypowerwall.auth: OAuth token cache
    - credentials.json: RSA keypair and gateway info
    - config_signed.json: Retrieved Powerwall configuration

CREDITS:
    Based on research and implementations by:
    - pypowerwall's Tesla OAuth implementation
    - @Matthew1471's RSA key pairing discovery
    - @Nexarian's TEDAPI protocol documentation
"""

import json
import requests
import urllib3
import time
import os
import base64
import math
import uuid

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# Import combined protobuf
import tedapi_combined_pb2 as pb

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration constants
DIN = ""  # Auto-detected from cloud API
AUTHFILE_PATH = ".pypowerwall.auth"
CREDENTIALS_FILE = "credentials.json"
TIMEOUT = 10
SIGNATURE_EXPIRY_SECONDS = 12

# User credentials (will be prompted interactively)
POWERWALL_IP = None
TESLA_EMAIL = None

# ============================================================================
# Helpers
# ============================================================================

def create_bearer_headers(token):
    """Create authorization headers for Tesla API."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_prompt_input(prompt, default=None):
    """Get user input with optional default value."""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()

# ============================================================================
# Phase 1: Tesla OAuth Authentication
# ============================================================================

def get_token_from_file(authfile, email):
    """Load token from existing auth file."""
    try:
        with open(authfile, "r") as f:
            auth_data = json.load(f)
            token = auth_data[email]["sso"]["access_token"]
            expires_at = auth_data[email]["sso"].get("expires_at", 0)
            
            if expires_at and time.time() > expires_at:
                print(f"⚠️  Token expired at {time.ctime(expires_at)}")
                return None, True
            
            ttl = expires_at - time.time() if expires_at else 0
            if ttl > 0:
                print(f"✓ Token valid (expires in {int(ttl/3600)} hours)")
            return token, False
    except Exception as e:
        print(f"✗ Error reading auth file: {e}")
        return None, False

def get_token_from_tesla():
    """Get a new token from Tesla via OAuth."""
    try:
        from pypowerwall.cloud.teslapy import Tesla
    except ImportError:
        print("✗ Error: pypowerwall not available")
        print("Install with: pip install pypowerwall")
        return None
    
    print(f"Authenticating with Tesla account: {TESLA_EMAIL}")
    tesla = Tesla(TESLA_EMAIL, cache_file=AUTHFILE_PATH, timeout=TIMEOUT)
    
    if not tesla.authorized:
        # Need full OAuth flow
        state = tesla.new_state()
        code_verifier = tesla.new_code_verifier()
        
        print("\n" + "="*70)
        print("Open this URL in your browser:")
        print("="*70)
        print(tesla.authorization_url(state=state, code_verifier=code_verifier))
        print("="*70)
        
        tesla.close()
        tesla = Tesla(TESLA_EMAIL, state=state, code_verifier=code_verifier, cache_file=AUTHFILE_PATH)
        
        try:
            callback_url = input("\nPaste the 'Page Not Found' URL: ").strip()
            tesla.fetch_token(authorization_response=callback_url)
            print("✓ Successfully authenticated!")
        except Exception as err:
            print(f"✗ Authentication failed: {err}")
            return None
    
    # Get token from TeslaPy
    try:
        token = tesla.token.get('access_token')
        expires_at = tesla.token.get('expires_at', 0)
        
        if not token:
            print("✗ No token found in TeslaPy object")
            return None
            
        if expires_at and time.time() < expires_at:
            ttl = expires_at - time.time()
            print(f"✓ Token refreshed (valid for {int(ttl/3600)} hours)")
            return token
        
        print(f"⚠️  Token still expired after refresh")
        return None
    except Exception as e:
        print(f"✗ Error getting token: {e}")
        return None

# ============================================================================
# Phase 2: Tesla Owner API - Get Energy Site
# ============================================================================

def get_energy_site_info(token):
    """Get energy site ID and gateway DIN from Tesla Cloud API."""
    print("\nQuerying Tesla products...")
    
    try:
        resp = requests.get(
            "https://owner-api.teslamotors.com/api/1/products",
            headers=create_bearer_headers(token),
            timeout=TIMEOUT
        )
        
        if not resp.ok:
            print(f"✗ Products API failed: {resp.status_code}")
            return None, None
        
        products = resp.json().get("response", [])
        sites = [
            {
                'site_name': p.get('site_name'),
                'energy_site_id': p['energy_site_id'],
                'gateway_din': p['gateway_id'],
            }
            for p in products
            if 'energy_site_id' in p and 'gateway_id' in p
        ]
        
        if not sites:
            print("✗ No energy sites found")
            return None, None
        
        if len(sites) > 1:
            print(f"Found {len(sites)} energy sites:")
            for i, site in enumerate(sites, 1):
                print(f"  {i}. {site['site_name']} (ID: {site['energy_site_id']})")
            choice = int(input("Select site number: ")) - 1
            site = sites[choice]
        else:
            site = sites[0]
            print(f"✓ Found site: {site['site_name']}")
        
        print(f"  Energy Site ID: {site['energy_site_id']}")
        print(f"  Gateway DIN: {site['gateway_din']}")
        
        return site['energy_site_id'], site['gateway_din']
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return None, None

# ============================================================================
# Phase 3: RSA Key Generation & Device Pairing
# ============================================================================

def generate_rsa_keys():
    """Generate RSA-4096 key pair for device pairing."""
    print("\nGenerating RSA-4096 key pair...")
    
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096
    )
    
    private_key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_key_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.PKCS1
    )
    
    print(f"✓ Private key: {len(private_key_bytes)} bytes")
    print(f"✓ Public key: {len(public_key_bytes)} bytes")
    
    return private_key, private_key_bytes, public_key_bytes

def pair_device_via_cloud(token, energy_site_id, public_key_bytes, device_name="pypowerwall"):
    """Register public key with gateway via Tesla Cloud API."""
    print(f"\nPairing device '{device_name}' via Cloud API...")
    
    base64_public_key = base64.b64encode(public_key_bytes).decode('utf-8')
    
    payload = {
        'command_properties': {
            'message': {
                'authorization': {
                    'add_authorized_client_request': {
                        'key_type': 1,
                        'public_key': base64_public_key,
                        'authorized_client_type': 1,
                        'description': device_name
                    }
                }
            },
            'identifier_type': 1
        },
        'command_type': 'grpc_command'
    }
    
    try:
        resp = requests.post(
            f"https://owner-api.teslamotors.com/api/1/energy_sites/{energy_site_id}/command",
            headers=create_bearer_headers(token),
            json=payload,
            timeout=TIMEOUT
        )
        
        if resp.ok:
            result = resp.json()
            print(f"✓ Pairing request sent!")
            print(f"Response: {json.dumps(result, indent=2)}")
            print("\n" + "="*70)
            print("⚠️  ACTION REQUIRED: Power toggle a Powerwall switch NOW")
            print("="*70)
            print("The gateway needs physical confirmation to accept the pairing.")
            print("Toggle any Powerwall power switch OFF then ON within 30 seconds.")
            input("\nPress Enter after toggling the switch...")
            return True
        else:
            print(f"✗ Pairing failed: {resp.status_code}")
            print(f"Response: {resp.text}")
            return False
            
    except Exception as e:
        print(f"✗ Pairing error: {e}")
        return False

# ============================================================================
# Phase 4: RSA Message Signing
# ============================================================================

def to_tlv(tag: int, value_bytes: bytes) -> bytes:
    """Encode tag-length-value for signature."""
    return tag.to_bytes(1, 'big') + len(value_bytes).to_bytes(1, 'big') + value_bytes

def build_tlv_payload(din: str, expires_at: int, routable_message) -> bytes:
    """Build TLV-encoded payload for RSA signature."""
    return b''.join([
        to_tlv(pb.TAG_SIGNATURE_TYPE, pb.SIGNATURE_TYPE_RSA.to_bytes(1, 'big')),
        to_tlv(pb.TAG_DOMAIN, pb.DOMAIN_ENERGY_DEVICE.to_bytes(1, 'big')),
        to_tlv(pb.TAG_PERSONALIZATION, din.encode()),
        to_tlv(pb.TAG_EXPIRES_AT, expires_at.to_bytes(4, 'big')),
        pb.TAG_END.to_bytes(1, 'big'),
        routable_message.protobuf_message_as_bytes
    ])

def sign_routable_message(private_key, public_key_bytes, din, routable_message):
    """Sign a RoutableMessage with RSA-4096."""
    expires_at = math.ceil(time.time()) + SIGNATURE_EXPIRY_SECONDS
    tlv_payload = build_tlv_payload(din, expires_at, routable_message)
    
    signature = private_key.sign(
        data=tlv_payload,
        padding=padding.PKCS1v15(),
        algorithm=hashes.SHA512()
    )
    
    routable_message.signature_data.CopyFrom(
        pb.SignatureData(
            signer_identity=pb.KeyIdentity(public_key=public_key_bytes),
            rsa_data=pb.RsaSignatureData(
                expires_at=expires_at,
                signature=signature
            )
        )
    )

# ============================================================================
# Phase 5: Build and Send Signed TEDAPI Message
# ============================================================================

def build_config_request(din):
    """Build FileStore config.json request."""
    msg = pb.Message()
    msg.message.deliveryChannel = pb.DELIVERY_CHANNEL_HERMES_COMMAND
    msg.message.sender.authorizedClient = pb.AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP
    msg.message.recipient.din = din
    msg.message.filestore.readFileRequest.domain = pb.FILE_STORE_API_DOMAIN_CONFIG_JSON
    msg.message.filestore.readFileRequest.name = "config.json"
    return msg.message

def parse_tedapi_response(response_content):
    """Parse TEDAPI response and extract config data."""
    resp_routable = pb.RoutableMessage()
    resp_routable.ParseFromString(response_content)
    print(f"✓ Parsed RoutableMessage ({len(resp_routable.protobuf_message_as_bytes)} bytes)")
    
    resp_envelope = pb.MessageEnvelope()
    resp_envelope.ParseFromString(resp_routable.protobuf_message_as_bytes)
    print(f"✓ Parsed MessageEnvelope")
    
    # Check response structure
    if not resp_envelope.HasField('filestore'):
        print("  - No filestore in response")
        return None
    
    filestore = resp_envelope.filestore
    if not filestore.HasField('readFileResponse'):
        print("  - No readFileResponse in filestore")
        return None
    
    file_response = filestore.readFileResponse.file
    print(f"  - File: {file_response.name}")
    
    if not file_response.HasField('blob'):
        print("  - No blob data in file")
        return None
    
    print(f"  - Blob size: {len(file_response.blob)} bytes")
    return json.loads(file_response.blob.decode('utf-8'))

def send_signed_message(private_key, public_key_bytes, din, base_url):
    """Build, sign, and send a TEDAPI message."""
    print("\nBuilding signed config request...")
    
    # Build and wrap message
    message_envelope = build_config_request(din)
    message_bytes = message_envelope.SerializeToString()
    print(f"✓ MessageEnvelope: {len(message_bytes)} bytes")
    
    routable_message = pb.RoutableMessage()
    routable_message.to_destination.domain = pb.DOMAIN_ENERGY_DEVICE
    routable_message.protobuf_message_as_bytes = message_bytes
    routable_message.uuid = str(uuid.uuid4()).encode()
    print(f"✓ RoutableMessage UUID: {routable_message.uuid.decode()}")
    
    # Sign and serialize
    sign_routable_message(private_key, public_key_bytes, din, routable_message)
    print(f"✓ Signed ({len(routable_message.signature_data.rsa_data.signature)} byte signature)")
    
    payload = routable_message.SerializeToString()
    print(f"✓ Payload: {len(payload)} bytes")
    
    # Send to gateway
    url = f"{base_url}/tedapi/v1r"
    print(f"\nSending to {url}...")
    
    try:
        session = requests.Session()
        session.verify = False
        response = session.post(
            url,
            data=payload,
            headers={"Content-Type": "application/octet-stream"},
            timeout=TIMEOUT
        )
        
        print(f"✓ Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"✗ Failed: {response.content[:200]}")
            return False
        
        # Parse and extract config
        config_data = parse_tedapi_response(response.content)
        
        if config_data:
            print("\n" + "="*70)
            print("SUCCESS! Config Retrieved")
            print("="*70)
            print(f"Keys: {', '.join(list(config_data.keys())[:10])}")
            print(f"VIN: {config_data.get('vin', 'N/A')}")
            
            with open("config_signed.json", "w") as f:
                json.dump(config_data, f, indent=2)
            print(f"\n✓ Saved to config_signed.json")
        else:
            print("\n✗ No config data found in response")
        
        return True
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

# ============================================================================
# Phase 6: Save/Load Credentials
# ============================================================================

def save_credentials(energy_site_id, din, private_key_bytes, public_key_bytes):
    """Save credentials to file."""
    creds = {
        "gateway": {
            "din": din,
            "host": POWERWALL_IP.replace("https://", ""),
            "paired_device": {
                "private_key": base64.b64encode(private_key_bytes).decode(),
                "public_key": base64.b64encode(public_key_bytes).decode()
            }
        },
        "tesla": {
            "energy_site_id": energy_site_id
        }
    }
    
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f, indent=2)
    
    print(f"\n✓ Credentials saved to {CREDENTIALS_FILE}")

def load_credentials():
    """Load credentials from file."""
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
        
        din = creds["gateway"]["din"]
        private_key_bytes = base64.b64decode(creds["gateway"]["paired_device"]["private_key"])
        public_key_bytes = base64.b64decode(creds["gateway"]["paired_device"]["public_key"])
        private_key = serialization.load_der_private_key(private_key_bytes, password=None)
        
        print(f"✓ Loaded credentials from {CREDENTIALS_FILE}")
        print(f"  DIN: {din}")
        print(f"  Keys: RSA-{private_key.key_size}")
        
        return private_key, private_key_bytes, public_key_bytes, din
        
    except FileNotFoundError:
        return None, None, None, None
    except Exception as e:
        print(f"✗ Error loading credentials: {e}")
        return None, None, None, None

# ============================================================================
# Main Workflow
# ============================================================================

def get_user_inputs():
    """Prompt user for email and Powerwall IP address."""
    global TESLA_EMAIL, POWERWALL_IP
    
    print("="*70)
    print("Tesla Powerwall LAN-Based TEDAPI Access")
    print("="*70)
    print("Setup: OAuth → Cloud Pairing → Physical Confirmation")
    print("Operation: RSA-Signed Messages → Direct LAN Communication")
    print("="*70)
    print()
    
    # Load defaults from saved credentials
    default_email = None
    default_ip = None
    
    try:
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, "r") as f:
                default_ip = json.load(f)['gateway']['host']
    except:
        pass
    
    try:
        if os.path.exists(AUTHFILE_PATH):
            with open(AUTHFILE_PATH, "r") as f:
                auth_data = json.load(f)
                default_email = list(auth_data.keys())[0] if auth_data else None
    except:
        pass
    
    # Get user inputs
    TESLA_EMAIL = get_prompt_input("Tesla account email", default_email)
    ip_address = get_prompt_input("Powerwall IP address (e.g., 192.168.91.1)", default_ip)
    
    # Add https:// prefix if needed
    if not ip_address.startswith(("http://", "https://")):
        POWERWALL_IP = f"https://{ip_address}"
    else:
        POWERWALL_IP = ip_address
    
    print()

def main():
    get_user_inputs()
    
    print("[Phase 1] Tesla OAuth Authentication")
    print("-" * 70)
    
    # Check for existing token
    token = None
    if os.path.exists(AUTHFILE_PATH):
        print(f"Found {AUTHFILE_PATH}")
        token, expired = get_token_from_file(AUTHFILE_PATH, TESLA_EMAIL)
        if expired or not token:
            token = get_token_from_tesla()
    else:
        token = get_token_from_tesla()
    
    if not token:
        print("\n✗ No token available. Exiting.")
        return
    
    # Check for existing paired device
    print("\n[Phase 2] Device Pairing")
    print("-" * 70)
    
    private_key, private_key_bytes, public_key_bytes, din = load_credentials()
    
    if private_key:
        print("✓ Found existing paired device")
        response = input("Use existing keys? [Y/n]: ").strip().lower()
        if response not in ['', 'y', 'yes']:
            private_key = None
    
    if not private_key:
        # Get energy site info
        energy_site_id, gateway_din = get_energy_site_info(token)
        if not energy_site_id:
            print("\n✗ Could not get energy site info. Exiting.")
            return
        
        din = gateway_din if gateway_din else DIN
        
        # Generate keys
        private_key, private_key_bytes, public_key_bytes = generate_rsa_keys()
        
        # Pair device
        if not pair_device_via_cloud(token, energy_site_id, public_key_bytes):
            print("\n✗ Pairing failed. Exiting.")
            return
        
        # Save credentials
        save_credentials(energy_site_id, din, private_key_bytes, public_key_bytes)
    
    # Send signed message
    print("\n[Phase 3] Send Signed TEDAPI Request")
    print("-" * 70)
    
    success = send_signed_message(private_key, public_key_bytes, din, POWERWALL_IP)
    
    if success:
        print("\n" + "="*70)
        print("✓ Complete! TEDAPI access working with RSA signatures")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("✗ Failed. Check pairing status or try re-pairing.")
        print("="*70)

if __name__ == "__main__":
    main()
