# Tesla Powerwall LAN-Based TEDAPI Access

Direct local network communication with Tesla Powerwall gateways using the TEDAPI (Tesla Energy Device API) protocol with RSA-signed messages.

## Overview

This script enables access to your Powerwall over your **local network (LAN)** without requirning direct WiFi connection to the Powerwall WiFi access point. It uses a two-phase approach:

1. **Initial Setup (Cloud)**: One-time pairing process via Tesla's cloud API
2. **Ongoing Operation (LAN)**: All subsequent communication happens directly with your Powerwall over your local network

### How It Works

**Setup Phase (First Run)**:
- Authenticate with Tesla via OAuth
- Query Tesla Cloud API to discover gateway details (DIN, site ID)
- Generate RSA-4096 key pair locally
- Register public key with gateway via Tesla Cloud API
- **Physical confirmation**: Toggle any Powerwall switch OFF then ON within 30 seconds
- Credentials saved for future use

**Operation Phase (Subsequent Runs)**:
- Load saved RSA keys and gateway info
- Build TEDAPI protobuf messages
- Sign messages with private key
- Send directly to Powerwall's local IP address (e.g., 192.168.91.1)
- Parse responses

After pairing, you can communicate with your Powerwall even if your internet connection is down (OAuth token permitting).

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the script:
   ```bash
   python lan_tedapi.py
   ```

3. Follow the interactive prompts:
   - Enter your Tesla account email
   - Enter your Powerwall local IP address (e.g., https://192.168.91.1)
   - Complete OAuth authentication in your browser
   - **Toggle a Powerwall switch** when prompted to confirm pairing

## Files

**Required**:
- `lan_tedapi.py` - Main script
- `tedapi_combined_pb2.py` - Compiled protobuf definitions
- `requirements.txt` - Python dependencies

**Optional**:
- `tedapi_combined.proto` - Protobuf source (for regenerating Python file)

## Output Files (Auto-Generated)

These files are created automatically and stored locally (excluded from git):

- `.pypowerwall.auth` - OAuth token cache (auto-refreshed as needed)
- `.pypowerwall.site` - Energy site ID cache (TeslaPy library)
- `credentials.json` - Your RSA keypair and gateway information
- `config_signed.json` - Retrieved Powerwall configuration data

## What This Retrieves

The script demonstrates TEDAPI access by retrieving `config.json` from your Powerwall, which contains:
- System configuration
- Component information (batteries, inverters, meters)
- Site details
- Firmware versions

The same signing and communication method can be adapted to send other TEDAPI commands.

## Technical Details

### Protocol Stack
- **Transport**: HTTPS directly to Powerwall local IP
- **Endpoint**: `/tedapi/v1r` on the gateway
- **Format**: Protocol Buffers (protobuf)
- **Authentication**: RSA-4096 signatures (PKCS1v15 + SHA512)
- **Signing**: TLV-encoded payload with expiration

### Message Flow
1. Build `MessageEnvelope` (TEDAPI request)
2. Serialize to bytes
3. Wrap in `RoutableMessage` with UUID
4. Create TLV payload (signature type, domain, personalization, expiry)
5. Sign with RSA-4096 private key
6. Attach signature and public key
7. Serialize complete message
8. POST to `https://<powerwall-ip>/tedapi/v1r`
9. Parse response `RoutableMessage`
10. Extract and decode data

## Regenerating Protobuf (Advanced)

If you modify the protocol definitions:
```bash
protoc --python_out=. tedapi_combined.proto
```

This recreates `tedapi_combined_pb2.py`.

## Credits

Based on research by:
- **pypowerwall** - Tesla OAuth implementation
- **@Matthew1471** - RSA key pairing discovery
- **@Nexarian** - TEDAPI protocol documentation

## Security Notes

- RSA private key stored locally in `credentials.json` - **keep this secure**
- OAuth tokens stored in `.pypowerwall.auth` - **keep this secure**
- Communication uses HTTPS but certificate verification is disabled (self-signed Powerwall cert)
- Physical access required for initial pairing (switch toggle)
