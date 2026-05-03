from __future__ import annotations
"""
pypowerwall.tesla_auth - Pure Python Tesla OAuth 2.0 PKCE authentication

Replaces the external tesla_auth binary. Users can authenticate with Tesla
and obtain refresh tokens using only Python — no Rust binary needed.

Tesla requires redirect_uri=tesla://auth/callback for the ownerapi client_id.
Since this is a custom URI scheme, we cannot use a localhost HTTP server to
catch the callback automatically. Instead, both interactive and headless modes
require the user to paste the redirect URL back into the terminal after login.

Supports:
  - Interactive browser login (opens browser, user pastes redirect URL)
  - Headless/manual mode (prints URL, user opens on another device, pastes URL)
  - Cross-platform: Linux, macOS, Windows, headless servers
  - Region auto-detection from callback issuer parameter

Usage:
    python -m pypowerwall login
    python -m pypowerwall login --headless
    python -m pypowerwall login --email user@example.com

Or programmatically:
    from pypowerwall.tesla_auth import login, save_token
    refresh_token = login(email="user@example.com")
    save_token(refresh_token)

Based on the OAuth 2.0 PKCE flow from tesla_auth (Rust) by Adrian Kumpf.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
import webbrowser

try:
    import requests
except ImportError:
    requests = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants — match tesla_auth exactly
# ---------------------------------------------------------------------------

CLIENT_ID = "ownerapi"

AUTH_URL_US = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL_US = "https://auth.tesla.com/oauth2/v3/token"

AUTH_URL_CN = "https://auth.tesla.cn/oauth2/v3/authorize"
TOKEN_URL_CN = "https://auth.tesla.cn/oauth2/v3/token"

# Tesla only accepts this custom URI scheme for the ownerapi client_id.
# The native tesla_auth app intercepts this via a WebView navigation handler.
# We use it in the auth URL; after login, Tesla redirects to this URI with
# code/state/issuer query params. The user copies the full URL from the browser.
REDIRECT_URI = "tesla://auth/callback"

SCOPES = ["openid", "email", "offline_access"]

REGION_CONFIG = {
    "us": {
        "auth_url": AUTH_URL_US,
        "token_url": TOKEN_URL_US,
    },
    "cn": {
        "auth_url": AUTH_URL_CN,
        "token_url": TOKEN_URL_CN,
    },
}


# ---------------------------------------------------------------------------
# PKCE helpers — match tesla_auth's oauth2 crate behavior
# ---------------------------------------------------------------------------

def generate_code_verifier() -> str:
    """Generate a PKCE code_verifier (base64url-encoded random bytes).

    tesla_auth uses oauth2 crate's PkceCodeChallenge::new_random_sha256()
    which generates 32 random bytes → base64url (43 chars). We match that.
    """
    return secrets.token_urlsafe(32)  # 32 bytes → 43 base64url chars


def generate_code_challenge(code_verifier: str) -> str:
    """Generate S256 code_challenge from code_verifier (RFC 7636 §4.2)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    """Generate a random state parameter for CSRF protection."""
    return secrets.token_urlsafe(16)


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

def build_auth_url(
    code_challenge: str,
    state: str,
    region: str = "us",
) -> str:
    """Build the Tesla OAuth authorization URL with tesla:// redirect."""
    cfg = REGION_CONFIG.get(region, REGION_CONFIG["us"])
    params = {
        "client_id": CLIENT_ID,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

def exchange_code(
    code: str,
    code_verifier: str,
    token_url: str,
) -> dict:
    """
    Exchange an authorization code for tokens.

    Args:
        code: The authorization code from the callback.
        code_verifier: The PKCE code verifier.
        token_url: The token endpoint URL (region-specific).

    Returns:
        dict with: access_token, refresh_token, expires_in, etc.

    Raises:
        RuntimeError on failure.
        ImportError if requests is not installed.
    """
    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": REDIRECT_URI,
    }

    resp = requests.post(token_url, data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed (HTTP {resp.status_code}): {resp.text}"
        )

    result = resp.json()
    if "refresh_token" not in result:
        raise RuntimeError(f"No refresh_token in response: {result}")

    return result


def refresh_access_token(
    refresh_token: str,
    token_url: str = TOKEN_URL_US,
) -> dict:
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: The Tesla refresh token.
        token_url: The token endpoint URL (region-specific).

    Returns:
        dict with: access_token, refresh_token, expires_in, etc.
    """
    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")

    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }

    resp = requests.post(token_url, data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Token refresh failed (HTTP {resp.status_code}): {resp.text}"
        )

    return resp.json()


# ---------------------------------------------------------------------------
# Callback URL parsing
# ---------------------------------------------------------------------------

def parse_callback_url(callback_url: str) -> dict:
    """
    Parse the redirect callback URL to extract code, state, and issuer.

    The callback URL looks like:
        tesla://auth/callback?code=...&state=...&issuer=https://auth.tesla.com/...

    Returns dict with: code, state, issuer, token_url
    """
    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)

    error = params.get("error", [None])[0]
    if error:
        raise RuntimeError(f"Tesla authentication error: {error}")

    code = params.get("code", [None])[0]
    state = params.get("state", [None])[0]
    issuer = params.get("issuer", [None])[0]

    if not code:
        raise RuntimeError("No authorization code found in the redirect URL.")
    if not state:
        raise RuntimeError("No state parameter found in the redirect URL.")

    # Determine token_url from issuer (matching tesla_auth's retrieve_tokens)
    token_url = TOKEN_URL_US  # default
    if issuer and "auth.tesla.cn" in issuer:
        token_url = TOKEN_URL_CN

    return {
        "code": code,
        "state": state,
        "issuer": issuer,
        "token_url": token_url,
    }


# ---------------------------------------------------------------------------
# Main login function
# ---------------------------------------------------------------------------

def _has_display() -> bool:
    """Check if a display is available for opening a browser."""
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def login(
    email: str = None,
    headless: bool = False,
    region: str = "us",
) -> str:
    """
    Authenticate with Tesla and return a refresh token.

    Uses the OAuth 2.0 PKCE flow matching tesla_auth. The redirect URI is
    tesla://auth/callback — Tesla's only accepted redirect for ownerapi.
    After login, the browser redirects to this custom URI. The user must
    copy the full URL from the browser's address bar and paste it back.

    Args:
        email: Tesla account email (optional, will prompt if needed).
        headless: If True, don't open browser (just print URL).
        region: 'us' (default) or 'cn' for China. Overridden by issuer in callback.
        timeout: Removed — no server to timeout.

    Returns:
        refresh_token string.

    Raises:
        RuntimeError: On authentication failure.
    """
    # Generate PKCE parameters
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = generate_state()

    # Prompt for email if not provided
    if not email:
        email = input("Tesla account email: ").strip()
        if not email or "@" not in email:
            raise ValueError("A valid email address is required.")

    print(f"\nTesla login for: {email}")
    print("-" * 60)

    # Build auth URL
    auth_url = build_auth_url(code_challenge, state, region)

    # Open browser if not headless and display available
    if not headless and _has_display():
        print("Opening browser for Tesla login...")
        webbrowser.open(auth_url)
        print(
            "\nAfter logging in, your browser will show an error or blank page.\n"
            "This is expected — the URL in the address bar contains your auth code.\n"
            "Copy the FULL URL from the address bar and paste it below.\n"
        )
    else:
        print(
            "\nOpen the following URL in your browser to log into your Tesla account:\n"
        )
        print(f"  {auth_url}\n")
        print(
            "After logging in, you will be redirected to a tesla:// URL.\n"
            "Copy the FULL URL from your browser's address bar and paste it below.\n"
        )

    callback_url = input("Paste the redirect URL: ").strip()

    if not callback_url:
        raise RuntimeError("No callback URL provided.")

    # Parse callback
    callback = parse_callback_url(callback_url)

    # Validate state (CSRF protection)
    if callback["state"] != state:
        raise RuntimeError("CSRF state mismatch — possible tampering.")

    # Exchange code for tokens (use issuer-detected token_url)
    print("  Exchanging authorization code for tokens...")
    tokens = exchange_code(callback["code"], code_verifier, callback["token_url"])

    refresh_token = tokens["refresh_token"]
    print(f"  ✅ Refresh token obtained (expires in {tokens.get('expires_in', '?')}s)")
    return refresh_token


# ---------------------------------------------------------------------------
# Token storage — compatible with pypowerwall's existing auth format
# ---------------------------------------------------------------------------

def save_token(refresh_token: str, path: str = None, email: str = None):
    """
    Save a refresh token to pypowerwall's auth file.

    The file format is a JSON dict keyed by email, compatible with teslapy's
    cache format:
        {
            "user@example.com": {
                "refresh_token": "...",
                "access_token": "",
                "expires_at": 0
            }
        }

    Args:
        refresh_token: The Tesla refresh token string.
        path: Path to the auth file. Defaults to .pypowerwall.auth in current dir.
        email: Email to key the token under. If None, prompts for input.
    """
    if not path:
        path = os.path.join(os.getcwd(), ".pypowerwall.auth")

    if not email:
        email = input("Tesla account email: ").strip()

    # Load existing data or start fresh
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}

    # Update with new token
    data[email] = {
        "refresh_token": refresh_token,
        "access_token": "",
        "expires_at": 0,
    }

    # Ensure directory exists
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Token saved to {path}")
    return path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for `python -m pypowerwall login`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="pypowerwall login",
        description="Authenticate with Tesla and obtain a refresh token",
    )
    parser.add_argument("--email", "-e", type=str, help="Tesla account email address")
    parser.add_argument(
        "--headless", "-H", action="store_true",
        help="Manual mode — don't open browser, paste URL instead",
    )
    parser.add_argument(
        "--region", "-r", type=str, default="us", choices=["us", "cn"],
        help="Tesla region: 'us' (default) or 'cn' (China)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Path to save the auth file (default: .pypowerwall.auth in current dir)",
    )

    args = parser.parse_args()

    print("⚡ Tesla Authentication — pypowerwall")
    print("=" * 60)

    try:
        refresh_token = login(
            email=args.email,
            headless=args.headless,
            region=args.region,
        )
    except (KeyboardInterrupt, EOFError):
        print("\n\nLogin cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        sys.exit(1)

    # Save the token
    email = args.email or ""
    save_token(refresh_token, path=args.output, email=email)

    print("\n✅ Done! You can now use pypowerwall with cloud mode.")
    print("   Run: python -m pypowerwall setup")


if __name__ == "__main__":
    main()
