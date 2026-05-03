"""
pypowerwall.tesla_auth - Pure Python Tesla OAuth 2.0 PKCE authentication

Replaces the external tesla_auth binary. Users can authenticate with Tesla
and obtain refresh tokens using only Python — no Rust binary needed.

Supports:
  - Interactive browser login (opens browser, catches redirect via localhost)
  - Headless/manual mode (prints URL, user pastes redirect URL back)
  - Cross-platform: Linux, macOS, Windows, headless servers

Usage:
    python -m pypowerwall login
    python -m pypowerwall login --headless
    python -m pypowerwall login --email user@example.com
    python -m pypowerwall login --region cn

Or programmatically:
    from pypowerwall.tesla_auth import login, save_token
    refresh_token = login(email="user@example.com")
    save_token(refresh_token)

Based on the OAuth 2.0 PKCE flow from tesla_auth (Rust) by Adrian Kumpf.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import sys
import threading
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

# Tesla's custom URI scheme — used by the native tesla_auth app via WebView interception.
# We do NOT use this directly; instead we try localhost or fall back to void/callback.
REDIRECT_URL_CUSTOM = "tesla://auth/callback"

# Tesla's void callback — shows "Page Not Found" but the URL contains the auth code.
# This is what teslapy uses for the manual paste flow.
REDIRECT_URL_VOID = "https://auth.tesla.com/void/callback"

SCOPES = ["openid", "email", "offline_access"]

REGION_CONFIG = {
    "us": {
        "auth_url": AUTH_URL_US,
        "token_url": TOKEN_URL_US,
        "void_redirect": "https://auth.tesla.com/void/callback",
    },
    "cn": {
        "auth_url": AUTH_URL_CN,
        "token_url": TOKEN_URL_CN,
        "void_redirect": "https://auth.tesla.cn/void/callback",
    },
}


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def generate_code_verifier() -> str:
    """Generate a PKCE code_verifier (43-128 chars, base64url-encoded random bytes)."""
    return secrets.token_urlsafe(86)  # 86 bytes → ~115 base64url chars


def generate_code_challenge(code_verifier: str) -> str:
    """Generate S256 code_challenge from code_verifier."""
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
    redirect_uri: str = REDIRECT_URL_VOID,
) -> str:
    """Build the Tesla OAuth authorization URL."""
    cfg = REGION_CONFIG.get(region, REGION_CONFIG["us"])
    params = {
        "client_id": CLIENT_ID,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "redirect_uri": redirect_uri,
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
    redirect_uri: str,
    region: str = "us",
) -> dict:
    """
    Exchange an authorization code for tokens.

    Returns dict with: access_token, refresh_token, expires_in, token_type, etc.
    Raises RuntimeError on failure.
    """
    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")

    cfg = REGION_CONFIG.get(region, REGION_CONFIG["us"])
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }

    resp = requests.post(cfg["token_url"], data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed (HTTP {resp.status_code}): {resp.text}"
        )

    result = resp.json()
    if "refresh_token" not in result:
        raise RuntimeError(f"No refresh_token in response: {result}")

    return result


# ---------------------------------------------------------------------------
# Localhost redirect catcher
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _RedirectHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth redirect."""

    auth_result = None  # type: ignore  # set by the handler
    auth_event = None  # type: ignore  # threading.Event

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            self._respond(
                400,
                "<h1>Authentication Failed</h1>"
                f"<p>Error: {error}</p>"
                f"<p>You can close this window.</p>",
            )
            _RedirectHandler.auth_result = {"error": error}
        elif code:
            self._respond(
                200,
                "<h1>&#x2705; Authentication Successful!</h1>"
                "<p>You can close this window and return to the terminal.</p>",
            )
            _RedirectHandler.auth_result = {"code": code, "state": state}
        else:
            self._respond(
                400,
                "<h1>Invalid Response</h1><p>No authorization code received.</p>",
            )
            _RedirectHandler.auth_result = {"error": "no_code"}

        if _RedirectHandler.auth_event:
            _RedirectHandler.auth_event.set()

    def _respond(self, status: int, html: str):
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        """Suppress default stderr logging."""
        pass


def _catch_redirect_on_localhost(port: int, timeout: int = 300) -> dict:
    """Start a localhost HTTP server and wait for the OAuth redirect."""
    _RedirectHandler.auth_result = None
    _RedirectHandler.auth_event = threading.Event()

    server = http.server.HTTPServer(("127.0.0.1", port), _RedirectHandler)
    server.timeout = timeout

    # Run server in a thread
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    # Wait for the redirect or timeout
    if not _RedirectHandler.auth_event.wait(timeout=timeout):
        server.server_close()
        raise TimeoutError(
            f"Timed out waiting for redirect after {timeout} seconds. "
            "Try running with --headless instead."
        )

    server.server_close()
    return _RedirectHandler.auth_result


# ---------------------------------------------------------------------------
# Main login function
# ---------------------------------------------------------------------------

def login(
    email: str = None,
    headless: bool = False,
    region: str = "us",
    timeout: int = 300,
) -> str:
    """
    Authenticate with Tesla and return a refresh token.

    Args:
        email: Tesla account email (optional, will prompt if needed).
        headless: If True, skip browser and use manual URL paste mode.
        region: 'us' (default) or 'cn' for China.
        timeout: Seconds to wait for browser redirect (default 300).

    Returns:
        refresh_token string.

    Raises:
        RuntimeError: On authentication failure.
        TimeoutError: If redirect not received within timeout.
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

    # Try localhost redirect first (unless headless)
    if not headless and _has_display():
        refresh_token = _login_interactive(
            code_verifier, code_challenge, state, region, email, timeout
        )
        if refresh_token:
            return refresh_token
        # Interactive failed — fall through to manual mode
        print("\nFalling back to manual mode...")

    # Headless / manual mode — use void/callback redirect
    return _login_manual(code_verifier, code_challenge, state, region, email)


def _has_display() -> bool:
    """Check if a display is available for opening a browser."""
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _login_interactive(
    code_verifier: str,
    code_challenge: str,
    state: str,
    region: str,
    email: str,
    timeout: int,
) -> str | None:
    """Try interactive browser login with localhost redirect."""
    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"

    auth_url = build_auth_url(code_challenge, state, region, redirect_uri=redirect_uri)

    print(f"Opening browser for Tesla login...")
    print(f"If the browser doesn't open, visit:\n\n  {auth_url}\n")

    # Open browser
    webbrowser.open(auth_url)

    # Wait for redirect
    try:
        result = _catch_redirect_on_localhost(port, timeout=timeout)
    except TimeoutError:
        return None

    if result is None:
        return None

    if "error" in result:
        print(f"  Error from Tesla: {result['error']}")
        return None

    # Validate state
    if result.get("state") != state:
        print("  Error: CSRF state mismatch — possible tampering.")
        return None

    # Exchange code for tokens
    print("  Exchanging authorization code for tokens...")
    try:
        tokens = exchange_code(result["code"], code_verifier, redirect_uri, region)
    except Exception as e:
        print(f"  Token exchange failed: {e}")
        return None

    refresh_token = tokens["refresh_token"]
    print(f"  ✅ Refresh token obtained (expires in {tokens.get('expires_in', '?')}s)")
    return refresh_token


def _login_manual(
    code_verifier: str,
    code_challenge: str,
    state: str,
    region: str,
    email: str,
) -> str:
    """Manual mode — user pastes the redirect URL from the browser."""
    redirect_uri = REDIRECT_URL_VOID
    auth_url = build_auth_url(code_challenge, state, region, redirect_uri=redirect_uri)

    print("\nOpen the following URL in your browser to log into your Tesla account:\n")
    print(f"  {auth_url}\n")
    print(
        "After logging in, you will be redirected to a 'Page Not Found' page.\n"
        "Copy the FULL URL from your browser's address bar and paste it below.\n"
    )

    redirect_response = input("Enter the URL after login: ").strip()

    # Parse the code and state from the redirect URL
    parsed = urllib.parse.urlparse(redirect_response)
    params = urllib.parse.parse_qs(parsed.query)

    error = params.get("error", [None])[0]
    if error:
        raise RuntimeError(f"Tesla authentication error: {error}")

    code = params.get("code", [None])[0]
    returned_state = params.get("state", [None])[0]

    if not code:
        raise RuntimeError("No authorization code found in the redirect URL.")

    if returned_state != state:
        raise RuntimeError("CSRF state mismatch — possible tampering.")

    print("  Exchanging authorization code for tokens...")
    tokens = exchange_code(code, code_verifier, redirect_uri, region)

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
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

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
    parser.add_argument(
        "--timeout", "-t", type=int, default=300,
        help="Seconds to wait for browser redirect (default: 300)",
    )

    args = parser.parse_args()

    print("⚡ Tesla Authentication — pypowerwall")
    print("=" * 60)

    try:
        refresh_token = login(
            email=args.email,
            headless=args.headless,
            region=args.region,
            timeout=args.timeout,
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
    print(f"   Run: python -m pypowerwall setup")


if __name__ == "__main__":
    main()
