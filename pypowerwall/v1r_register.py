#!/usr/bin/env python3
"""
Tesla RSA Key Registration for Powerwall LAN TEDapi v1r

Generates an RSA-4096 key pair, registers it with the Powerwall via
Tesla Owner API (recommended) or Fleet API OAuth, and saves the
private key for use with pypowerwall's v1r LAN mode.

Two authentication paths are supported:

  Owner API (recommended — no developer app needed):
    Just your Tesla account email and password, same login as
    'python -m pypowerwall setup' (Cloud Mode).
    python -m pypowerwall register

  Fleet API (requires a Tesla developer app):
    Needs CLIENT_ID, CLIENT_SECRET, and a hosted redirect URI.
    See https://developer.tesla.com/ to set up an app first.
    Credentials can be passed via environment variables:
      export TESLA_CLIENT_ID="your-client-id"
      export TESLA_CLIENT_SECRET="your-client-secret"
      export TESLA_REDIRECT_URI="https://your-domain.com/callback"
    python -m pypowerwall register
"""

import json
import os
import sys
import ssl
import time
import base64
import urllib.request
import urllib.parse
import secrets

# ── Configuration ──
# Read from env vars first, prompt interactively if missing
AUTH_BASE = "https://auth.tesla.com"
TOKEN_BASE = "https://fleet-auth.prd.vn.cloud.tesla.com"
SCOPE = "openid offline_access energy_device_data energy_cmds"
OWNER_API_BASE = "https://owner-api.teslamotors.com"
OWNER_AUTHFILE = ".pypowerwall.auth"  # Shared with Cloud Mode

CERT_DIR = os.getcwd()
RSA_PRIVATE_KEY_FILE = os.path.join(CERT_DIR, "tedapi_rsa_private.pem")
RSA_PUBLIC_KEY_FILE = os.path.join(CERT_DIR, "tedapi_rsa_public.der")
TOKENS_FILE = os.path.join(CERT_DIR, "fleet_tokens.json")

SSL_CTX = ssl.create_default_context()

# Fleet API region endpoints
FLEET_REGIONS = {
    "na":     "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu":     "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn":     "https://fleet-api.prd.cn.vn.cloud.tesla.com",
}


def get_config():
    """Get OAuth credentials from env vars or interactive prompts."""
    client_id = os.getenv("TESLA_CLIENT_ID", "")
    client_secret = os.getenv("TESLA_CLIENT_SECRET", "")
    redirect_uri = os.getenv("TESLA_REDIRECT_URI", "")
    fleet_api_base = os.getenv("TESLA_FLEET_API_BASE", "")

    if client_id and client_secret and redirect_uri:
        if not fleet_api_base:
            fleet_api_base = FLEET_REGIONS["na"]
        return client_id, client_secret, redirect_uri, fleet_api_base

    # Interactive mode
    print("=" * 70)
    print("  Tesla Fleet API — RSA Key Registration")
    print("=" * 70)
    print()
    print("No credentials found in environment variables.")
    print("Enter your Tesla developer app credentials below.")
    print()
    print("Don't have these yet? Go to https://developer.tesla.com/")
    print("and create an application first.")
    print()

    if not client_id:
        client_id = input("  TESLA_CLIENT_ID: ").strip()
    if not client_secret:
        client_secret = input("  TESLA_CLIENT_SECRET: ").strip()
    if not redirect_uri:
        redirect_uri = input("  TESLA_REDIRECT_URI (e.g. https://your-domain.com/callback): ").strip()

    if not all([client_id, client_secret, redirect_uri]):
        print("\nERROR: All three credentials are required.")
        sys.exit(1)

    if not fleet_api_base:
        print()
        print("  Fleet API region:")
        print("    [1] North America (default)")
        print("    [2] Europe")
        print("    [3] China")
        choice = input("  Select [1]: ").strip() or "1"
        region_map = {"1": "na", "2": "eu", "3": "cn"}
        fleet_api_base = FLEET_REGIONS.get(region_map.get(choice, "na"), FLEET_REGIONS["na"])

    print()
    return client_id, client_secret, redirect_uri, fleet_api_base


def api_call(url, method="GET", data=None, headers=None, token=None):
    """Make an API call."""
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data is not None:
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
        elif isinstance(data, str):
            data = data.encode()
        req.data = data

    try:
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=30)
        body = resp.read().decode()
        try:
            return resp.status, json.loads(body)
        except json.JSONDecodeError:
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def generate_rsa_key():
    """Generate RSA-4096 key pair for TEDapi v1r signing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    if os.path.exists(RSA_PRIVATE_KEY_FILE):
        print(f"  RSA key already exists at {RSA_PRIVATE_KEY_FILE}, reusing")
        with open(RSA_PRIVATE_KEY_FILE, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        public_key_der = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.PKCS1
        )
        return private_key, public_key_der

    print("  Generating RSA-4096 key pair...")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    # Save private key (PEM)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()
    )
    with open(RSA_PRIVATE_KEY_FILE, "wb") as f:
        f.write(pem)
    os.chmod(RSA_PRIVATE_KEY_FILE, 0o600)

    # Get public key (DER PKCS1)
    public_key_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.PKCS1
    )
    with open(RSA_PUBLIC_KEY_FILE, "wb") as f:
        f.write(public_key_der)

    print(f"  Private key saved: {RSA_PRIVATE_KEY_FILE}")
    print(f"  Public key saved:  {RSA_PUBLIC_KEY_FILE}")
    return private_key, public_key_der


def step1_get_auth_code(client_id, redirect_uri):
    """Generate auth URL and get authorization code from user."""
    state = secrets.token_hex(32)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
    }
    auth_url = f"{AUTH_BASE}/oauth2/v3/authorize?{urllib.parse.urlencode(params)}"

    print("=" * 70)
    print("  STEP 1: Tesla OAuth Login")
    print("=" * 70)
    print()
    print("  Open this URL in your browser:")
    print()
    print(f"  {auth_url}")
    print()
    print(f"  After authorizing, Tesla will redirect to {redirect_uri}")
    print("  The page will show a 404 — that's expected.")
    print("  Copy the FULL URL from your browser's address bar.")
    print()

    redirect_url = input("  Paste the redirect URL here: ").strip()

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)

    if "code" not in params:
        print(f"\n  ERROR: No 'code' parameter found in URL: {redirect_url}")
        sys.exit(1)

    code = params["code"][0]
    print(f"  Got authorization code: {code[:20]}...")
    return code


def step2_exchange_token(code, client_id, client_secret, redirect_uri, fleet_api_base):
    """Exchange authorization code for access + refresh tokens."""
    print()
    print("=" * 70)
    print("  STEP 2: Exchanging code for tokens...")
    print("=" * 70)

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "audience": fleet_api_base,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
    }).encode()

    req = urllib.request.Request(
        f"{TOKEN_BASE}/oauth2/v3/token",
        data=data,
        method="POST",
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=30)
        tokens = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\n  Token exchange failed ({e.code}): {body}")
        sys.exit(1)

    # Save tokens
    tokens["obtained_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKENS_FILE, 0o600)

    print(f"  Access token:  {tokens['access_token'][:30]}...")
    print(f"  Refresh token: {tokens.get('refresh_token', 'N/A')[:30]}...")
    print(f"  Expires in:    {tokens.get('expires_in', '?')}s")
    print(f"  Saved to:      {TOKENS_FILE}")
    return tokens["access_token"]


class _TokenExpiredError(Exception):
    """Raised when the API returns 401 (token expired)."""


def step3_get_site_id(token, fleet_api_base):
    """Get energy_site_id from Tesla API."""
    print()
    print("=" * 70)
    print("  STEP 3: Finding your Powerwall site...")
    print("=" * 70)

    code, resp = api_call(f"{fleet_api_base}/api/1/products", token=token)
    if code == 401:
        raise _TokenExpiredError(resp)
    if code != 200:
        print(f"\n  Failed to get products ({code}): {resp}")
        sys.exit(1)

    sites = []
    for product in resp.get("response", []):
        if "energy_site_id" in product:
            sites.append({
                "energy_site_id": product["energy_site_id"],
                "gateway_din": product.get("gateway_id", "unknown"),
                "site_name": product.get("site_name", "unknown"),
            })

    if not sites:
        print("\n  No energy sites found on this account!")
        sys.exit(1)

    print(f"\n  Found {len(sites)} energy site(s):")
    for i, site in enumerate(sites):
        print(f"    [{i}] {site['site_name']} (ID: {site['energy_site_id']}, DIN: {site['gateway_din']})")

    if len(sites) == 1:
        selected = sites[0]
    else:
        print()
        idx = int(input("  Select site number: "))
        selected = sites[idx]

    print(f"\n  Using: {selected['site_name']} ({selected['energy_site_id']})")
    return selected["energy_site_id"], selected["gateway_din"]


def _check_key_state(resp):
    """Extract client state from Fleet API registration/list response.

    Returns the state integer if found, None otherwise.
    State values: 1=PENDING, 2=PENDING_VERIFICATION, 3=VERIFIED
    """
    try:
        msg = resp["response"]["message"]["Payload"]["Authorization"]["Message"]
    except (KeyError, TypeError):
        try:
            msg = resp["response"]["message"]["payload"]["authorization"]["message"]
        except (KeyError, TypeError):
            return None

    # Check AddAuthorizedClientResponse (registration response)
    for key in ("AddAuthorizedClientResponse", "add_authorized_client_response"):
        if key in msg:
            client = msg[key].get("client") or msg[key].get("Client")
            if client:
                state = client.get("state") or client.get("State")
                if state is not None:
                    return int(state)

    # Check ListAuthorizedClientsResponse (list response)
    for key in ("ListAuthorizedClientsResponse", "list_authorized_clients_response"):
        if key in msg:
            clients = msg[key].get("clients") or msg[key].get("Clients") or []
            for client in clients:
                state = client.get("state") or client.get("State")
                if state is not None:
                    return int(state)

    return None


def _poll_key_state(token, energy_site_id, fleet_api_base, attempts=3, delay=5):
    """Poll list_authorized_clients_request to check key verification state.

    Returns the state integer of the most recently registered key, or None.
    """
    verify_payload = {
        "command_properties": {
            "message": {
                "authorization": {
                    "list_authorized_clients_request": {}
                }
            },
            "identifier_type": 1,
        },
        "command_type": "grpc_command",
    }

    for attempt in range(attempts):
        if attempt > 0:
            time.sleep(delay)
        code, resp = api_call(
            f"{fleet_api_base}/api/1/energy_sites/{energy_site_id}/command",
            method="POST",
            data=verify_payload,
            token=token,
        )
        print(f"  Poll attempt {attempt + 1}/{attempts}: ({code})")
        state = _check_key_state(resp)
        if state is not None:
            print(f"  Key state: {state} ({'VERIFIED' if state == 3 else 'PENDING' if state < 3 else 'UNKNOWN'})")
            if state == 3:
                return state
        else:
            # Show raw response for debugging if state couldn't be parsed
            if isinstance(resp, dict):
                print(f"  {json.dumps(resp, indent=2)[:2000]}")

    return state


def step4_register_key(token, energy_site_id, public_key_der, fleet_api_base):
    """Register RSA public key with the Powerwall via Fleet API."""
    print()
    print("=" * 70)
    print("  STEP 4: Registering RSA public key with Powerwall...")
    print("=" * 70)

    b64_pubkey = base64.b64encode(public_key_der).decode()

    payload = {
        "command_properties": {
            "message": {
                "authorization": {
                    "add_authorized_client_request": {
                        "key_type": 1,
                        "public_key": b64_pubkey,
                        "authorized_client_type": 1,
                        "description": "Powerwall LAN Client",
                    }
                }
            },
            "identifier_type": 1,
        },
        "command_type": "grpc_command",
    }

    code, resp = api_call(
        f"{fleet_api_base}/api/1/energy_sites/{energy_site_id}/command",
        method="POST",
        data=payload,
        token=token,
    )

    if code != 200:
        print(f"\n  Registration failed ({code}): {json.dumps(resp, indent=2)}")
        sys.exit(1)

    # Check if cloud registration auto-verified the key
    state = _check_key_state(resp)
    if state == 3:
        print("\n  Key verified automatically via cloud — no breaker toggle needed!")
    else:
        if state is not None:
            print(f"\n  Registration response state: {state} (not yet verified)")
        else:
            print(f"\n  Response ({code}): {json.dumps(resp, indent=2)}")
        # Poll to see if state transitions to VERIFIED
        print("\n  Checking key verification status...")
        state = _poll_key_state(token, energy_site_id, fleet_api_base)
        if state == 3:
            print("\n  Key verified via cloud!")
        else:
            # Fallback: physical confirmation
            print()
            print("=" * 70)
            print("  STEP 5: Physical confirmation required")
            print("=" * 70)
            print()
            print("  Cloud auto-verification did not complete.")
            print("  Toggle ONE Powerwall breaker OFF, wait 2 seconds, then back ON.")
            print("  This confirms the key registration on the device.")
            print()
            input("  Press Enter after toggling the breaker...")
            print("\n  Verifying key registration...")
            state = _poll_key_state(token, energy_site_id, fleet_api_base, attempts=6)

    # Done
    verified = state == 3
    print()
    print("=" * 70)
    print(f"  {'Registration complete!' if verified else 'Registration sent.'}")
    print("=" * 70)
    print()
    if verified:
        print("  Key is VERIFIED and ready for use.")
    else:
        print("  Key state could not be confirmed as verified.")
        print("  It may still be pending — check again later with list_authorized_clients.")
    print(f"\n  RSA private key: {RSA_PRIVATE_KEY_FILE}")
    print()
    print("  Next steps (library usage):")
    print("    import pypowerwall")
    print('    pw = pypowerwall.Powerwall(host="POWERWALL_IP", password="XXXXX",')
    print('         email="you@example.com", rsa_key_path="tedapi_rsa_private.pem")')
    print()
    print("  Next steps (Docker / Powerwall-Dashboard):")
    print("    1. Copy the key to your Powerwall-Dashboard .auth/ directory")
    print("    2. Set PW_RSA_KEY_PATH=/app/.auth/tedapi_rsa_private.pem")
    print("    3. Set PW_HOST to your Powerwall's wired LAN IP")
    print("    4. Set PW_PASSWORD to your customer password")
    print("    5. Start the container — v1r mode is auto-detected")
    print()


def owner_api_login(email=None, authpath="", force_reauth=False):
    """
    Authenticate with the Tesla Owner API using teslapy.

    This is the same login flow as 'python -m pypowerwall setup' (Cloud Mode).
    No developer app or hosted key is required — just your Tesla account
    email and password.

    Args:
        email:        Tesla account email (prompted if not provided).
        authpath:     Directory containing the auth cache file.
        force_reauth: If True, delete the cached token and require a fresh login.

    Returns the Bearer access token string on success.
    """
    from pypowerwall.cloud.teslapy import Tesla

    authfile = os.path.join(authpath, OWNER_AUTHFILE) if authpath else OWNER_AUTHFILE

    print("=" * 70)
    print("  Tesla Owner API — Login")
    print("=" * 70)
    print()

    if force_reauth:
        if os.path.exists(authfile):
            os.remove(authfile)
            print(f"  Removed expired token cache ({authfile})")
        print("  Please log in again to obtain a fresh token.")
        print()
    else:
        print("  This is the same login used by Cloud Mode (python -m pypowerwall setup).")
        print("  No developer app setup required.")
        print()

    if not email:
        while True:
            email = input("  Tesla account email: ").strip()
            if "@" in email:
                break
            print("  Invalid email address, please try again.")

    tesla = Tesla(email, cache_file=authfile)

    if tesla.authorized and not force_reauth:
        print(f"  Using cached credentials from {authfile}")
    else:
        # PKCE OAuth flow — mirrors PyPowerwallCloud.setup()
        state = tesla.new_state()
        code_verifier = tesla.new_code_verifier()

        try:
            auth_url = tesla.authorization_url(state=state, code_verifier=code_verifier)
        except Exception as e:
            print(f"\n  ERROR: Could not generate login URL — {e}")
            sys.exit(1)

        print("  Open this URL in your browser to log in to your Tesla account:")
        print()
        print(f"  {auth_url}")
        print()
        print("  After logging in, you will be redirected to a 'Page Not Found' page.")
        print("  Copy the FULL URL from your browser's address bar and paste it below.")
        print()

        tesla.close()
        tesla = Tesla(email, state=state, code_verifier=code_verifier, cache_file=authfile)

        if not tesla.authorized:
            try:
                tesla.fetch_token(authorization_response=input("  Paste the redirect URL: ").strip())
            except Exception as e:
                print(f"\n  ERROR: Login failed — {e}")
                sys.exit(1)

        print(f"\n  Login successful, credentials cached to {authfile}")

    token = (tesla.token or {}).get("access_token")
    if not token:
        print("  ERROR: Could not retrieve access token.")
        sys.exit(1)
    return token


def main():
    print("=" * 70)
    print("  Tesla RSA Key Registration for Powerwall v1r LAN Mode")
    print("=" * 70)
    print()
    print("  Choose how to authenticate with Tesla:")
    print()
    print("    [1] Owner API  (recommended — just your Tesla email and password,")
    print("                   same login as 'python -m pypowerwall setup')")
    print("    [2] Fleet API  (requires a developer app at developer.tesla.com)")
    print()
    choice = input("  Select [1]: ").strip() or "1"

    print()
    print("=" * 70)
    print("  Generating RSA key pair...")
    print("=" * 70)
    print()
    private_key, public_key_der = generate_rsa_key()

    if choice == "2":
        # ── Fleet API path ────────────────────────────────────────────────────
        client_id, client_secret, redirect_uri, fleet_api_base = get_config()

        # Check for existing Fleet API tokens
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE) as f:
                tokens = json.load(f)
            token = tokens.get("access_token")
            print(f"\n  Found existing Fleet API tokens from {tokens.get('obtained_at', '?')}")
            use = input("  Use existing token? [Y/n]: ").strip().lower()
            if use != "n":
                site_id, din = step3_get_site_id(token, fleet_api_base)
                step4_register_key(token, site_id, public_key_der, fleet_api_base)
                return

        code = step1_get_auth_code(client_id, redirect_uri)
        token = step2_exchange_token(code, client_id, client_secret, redirect_uri, fleet_api_base)
        site_id, din = step3_get_site_id(token, fleet_api_base)
        step4_register_key(token, site_id, public_key_der, fleet_api_base)
    else:
        # ── Owner API path (default) ──────────────────────────────────────────
        email = None
        for attempt in range(2):
            token = owner_api_login(email=email, force_reauth=(attempt > 0))
            try:
                site_id, din = step3_get_site_id(token, OWNER_API_BASE)
                break
            except _TokenExpiredError as e:
                if attempt == 0:
                    print(f"\n  Token expired ({e}).")
                    print("  Clearing cached credentials and requesting a new login...")
                    # Preserve the email so the re-auth prompt is skipped
                    email = input("  Confirm your Tesla account email (or press Enter to re-enter): ").strip() or None
                else:
                    print("\n  ERROR: Authentication failed after token refresh. Please try again.")
                    sys.exit(1)
        step4_register_key(token, site_id, public_key_der, OWNER_API_BASE)


if __name__ == "__main__":
    main()
