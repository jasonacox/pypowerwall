from __future__ import annotations
"""
pypowerwall.tesla_auth - Pure Python Tesla OAuth 2.0 PKCE authentication

Replaces the external tesla_auth binary. Users can authenticate with Tesla
and obtain refresh tokens using only Python — no Rust binary or WebView needed.

How it works:
  1. Registers tesla:// as a custom URI scheme handler on the OS
  2. Starts a local HTTP server to catch the forwarded callback
  3. Opens the browser to Tesla's OAuth login page
  4. After login, Tesla redirects to tesla://auth/callback?code=...
  5. The OS calls our handler, which forwards the URL to the local server
  6. We capture the auth code and exchange it for tokens
  7. Cleanup: unregister the handler

Supports:
  - Interactive browser login (auto-captures callback via URI handler)
  - Headless/manual mode (prints URL, user pastes redirect URL)
  - Cross-platform: Linux (xdg), macOS (lsregister), Windows (registry)
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
import http.server
import json
import os
import platform
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
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

# Temp files for inter-process communication
HANDLER_PORT_FILE = os.path.join(tempfile.gettempdir(), "tesla_auth_port.txt")
HANDLER_SCRIPT_PATH = os.path.join(tempfile.gettempdir(), "tesla_uri_handler.py")


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def generate_code_verifier() -> str:
    """Generate a PKCE code_verifier (base64url-encoded random bytes)."""
    return secrets.token_urlsafe(32)


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

def build_auth_url(code_challenge: str, state: str, region: str = "us") -> str:
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

def exchange_code(code: str, code_verifier: str, token_url: str) -> dict:
    """Exchange an authorization code for tokens."""
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
        raise RuntimeError(f"Token exchange failed (HTTP {resp.status_code}): {resp.text}")

    result = resp.json()
    if "refresh_token" not in result:
        raise RuntimeError(f"No refresh_token in response: {result}")

    return result


def refresh_access_token(refresh_token: str, token_url: str = TOKEN_URL_US) -> dict:
    """Refresh an access token using a refresh token."""
    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")

    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }

    resp = requests.post(token_url, data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed (HTTP {resp.status_code}): {resp.text}")

    return resp.json()


# ---------------------------------------------------------------------------
# Callback URL parsing
# ---------------------------------------------------------------------------

def parse_callback_url(callback_url: str) -> dict:
    """Parse the redirect callback URL to extract code, state, and issuer."""
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

    token_url = TOKEN_URL_US
    if issuer and "auth.tesla.cn" in issuer:
        token_url = TOKEN_URL_CN

    return {
        "code": code,
        "state": state,
        "issuer": issuer,
        "token_url": token_url,
    }


# ---------------------------------------------------------------------------
# Local HTTP callback server
# ---------------------------------------------------------------------------

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that receives the forwarded tesla:// callback."""

    auth_result = None  # type: ignore

    def do_GET(self):
        if self.path.startswith("/callback"):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            _CallbackHandler.auth_result = params
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authentication successful!</h2>"
                             b"<p>You can close this tab.</p></body></html>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


class _CallbackServer:
    """Local HTTP server that waits for the callback from the URI handler."""

    def __init__(self, port: int):
        _CallbackHandler.auth_result = None
        self._server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
        self._server.timeout = 1
        self._port = port
        self._got_it = threading.Event()

    def start_background(self):
        """Start serving in a background thread."""
        t = threading.Thread(target=self._serve_loop, daemon=True)
        t.start()

    def _serve_loop(self):
        while not self._got_it.is_set():
            self._server.handle_request()

    def wait_for_code(self, timeout: int = 120) -> dict | None:
        """Wait for the callback to arrive. Returns the parsed query params."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _CallbackHandler.auth_result is not None:
                self._got_it.set()
                return _CallbackHandler.auth_result
            time.sleep(0.5)
        self._got_it.set()
        return None

    def shutdown(self):
        self._got_it.set()
        self._server.server_close()


# ---------------------------------------------------------------------------
# URI handler script (written to /tmp, called by OS when tesla:// is opened)
# ---------------------------------------------------------------------------

def _write_handler_script():
    """Write the URI handler script that forwards tesla:// URLs to our server."""
    # Use stdlib only — no requests dependency for the handler
    script = f'''#!/usr/bin/env python3
"""URI handler for tesla:// scheme — forwards to local callback server."""
import sys
try:
    import urllib.request
    import urllib.parse
    uri = sys.argv[1] if len(sys.argv) > 1 else ""
    if not uri:
        sys.exit(1)
    try:
        with open("{HANDLER_PORT_FILE}", "r") as f:
            port = f.read().strip()
    except Exception:
        sys.exit(1)
    parsed = urllib.parse.urlparse(uri)
    qs = urllib.parse.urlencode(urllib.parse.parse_qs(parsed.query), doseq=True)
    url = f"http://127.0.0.1:{{port}}/callback?{{qs}}"
    try:
        urllib.request.urlopen(url, timeout=5)
    except Exception:
        pass
except Exception:
    pass
'''
    with open(HANDLER_SCRIPT_PATH, "w") as f:
        f.write(script)
    os.chmod(HANDLER_SCRIPT_PATH, 0o755)


# ---------------------------------------------------------------------------
# OS-specific protocol handler registration
# ---------------------------------------------------------------------------

def _get_python_path() -> str:
    """Get the current Python interpreter path."""
    return sys.executable


def _register_linux() -> bool:
    """Register tesla:// URI scheme on Linux via xdg-mime."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)

    desktop_file = os.path.join(apps_dir, "tesla-auth-helper.desktop")
    python_path = _get_python_path()

    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Tesla Auth Helper\n"
        f"Exec={python_path} {HANDLER_SCRIPT_PATH} %u\n"
        "MimeType=x-scheme-handler/tesla\n"
        "NoDisplay=true\n"
    )

    with open(desktop_file, "w") as f:
        f.write(content)

    try:
        subprocess.run(
            ["xdg-mime", "default", "tesla-auth-helper.desktop",
             "x-scheme-handler/tesla"],
            capture_output=True, timeout=10, check=False,
        )
        subprocess.run(
            ["update-desktop-database", apps_dir],
            capture_output=True, timeout=10, check=False,
        )
        return True
    except FileNotFoundError:
        return False


def _register_macos() -> bool:
    """Register tesla:// URI scheme on macOS via a small .app bundle."""
    # Create a minimal .app bundle
    app_dir = os.path.expanduser("~/Library/TeslaAuthHelper.app")
    contents_dir = os.path.join(app_dir, "Contents")
    macos_dir = os.path.join(contents_dir, "MacOS")
    os.makedirs(macos_dir, exist_ok=True)

    # Write Info.plist with URI scheme registration
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>CFBundleIdentifier</key>'
        '<string>com.pypowerwall.teslaauth</string>\n'
        '  <key>CFBundleName</key>'
        '<string>TeslaAuthHelper</string>\n'
        '  <key>CFBundleURLTypes</key><array><dict>\n'
        '    <key>CFBundleURLSchemes</key><array>'
        '<string>tesla</string></array>\n'
        '    <key>CFBundleURLName</key>'
        '<string>Tesla Auth</string>\n'
        '  </dict></array>\n'
        '</dict></plist>\n'
    )
    with open(os.path.join(contents_dir, "Info.plist"), "w") as f:
        f.write(plist)

    # Write the launcher script
    launcher = os.path.join(macos_dir, "TeslaAuthHelper")
    python_path = _get_python_path()
    with open(launcher, "w") as f:
        f.write(f"#!/bin/bash\nexec {python_path} {HANDLER_SCRIPT_PATH} \"$1\"\n")
    os.chmod(launcher, 0o755)

    # Register with LaunchServices
    try:
        subprocess.run(
            ["/System/Library/Frameworks/CoreServices.framework/Frameworks/"
             "LaunchServices.framework/Support/lsregister",
             "-f", app_dir],
            capture_output=True, timeout=15, check=False,
        )
        return True
    except FileNotFoundError:
        return False


def _register_windows() -> bool:
    """Register tesla:// URI scheme on Windows via Registry."""
    try:
        import winreg
    except ImportError:
        return False

    python_path = _get_python_path()
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\tesla")
        winreg.SetValue(key, "", winreg.REG_SZ, "URL:Tesla Auth Protocol")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        cmd_key = winreg.CreateKey(key, r"shell\open\command")
        winreg.SetValue(
            cmd_key, "",
            winreg.REG_SZ,
            f'"{python_path}" "{HANDLER_SCRIPT_PATH}" "%1"',
        )
        winreg.CloseKey(cmd_key)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _register_protocol_handler() -> bool:
    """Register the tesla:// URI scheme handler for the current OS."""
    system = sys.platform
    if system == "linux":
        return _register_linux()
    elif system == "darwin":
        return _register_macos()
    elif system == "win32":
        return _register_windows()
    return False


def _unregister_protocol_handler():
    """Remove the tesla:// URI scheme registration."""
    system = sys.platform

    if system == "linux":
        desktop_file = os.path.expanduser(
            "~/.local/share/applications/tesla-auth-helper.desktop"
        )
        try:
            if os.path.exists(desktop_file):
                os.remove(desktop_file)
            apps_dir = os.path.expanduser("~/.local/share/applications")
            subprocess.run(
                ["update-desktop-database", apps_dir],
                capture_output=True, timeout=10, check=False,
            )
        except Exception:
            pass

    elif system == "darwin":
        app_dir = os.path.expanduser("~/Library/TeslaAuthHelper.app")
        try:
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir, ignore_errors=True)
            subprocess.run(
                ["/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                 "LaunchServices.framework/Support/lsregister",
                 "-u", app_dir],
                capture_output=True, timeout=10, check=False,
            )
        except Exception:
            pass

    elif system == "win32":
        try:
            import winreg
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\tesla\shell\open\command",
            )
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\tesla\shell\open",
            )
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\tesla\shell",
            )
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\tesla",
            )
        except Exception:
            pass

    # Clean up handler script and port file
    for f in [HANDLER_SCRIPT_PATH, HANDLER_PORT_FILE]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _has_display() -> bool:
    """Check if a display is available for opening a browser."""
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


# ---------------------------------------------------------------------------
# Main login function
# ---------------------------------------------------------------------------

def login(
    email: str = None,
    headless: bool = False,
    region: str = "us",
    timeout: int = 120,
) -> str:
    """
    Authenticate with Tesla and return a refresh token.

    Uses OAuth 2.0 PKCE flow. When a display is available:
      1. Registers tesla:// URI handler on the OS
      2. Starts a local HTTP server
      3. Opens browser → user logs in → Tesla redirects to tesla://...
      4. OS handler forwards to local server → captures auth code
      5. Exchanges code for tokens
      6. Cleans up URI registration

    In headless mode or when handler registration fails, falls back to
    manual paste mode (user copies URL from browser address bar).

    Args:
        email: Tesla account email (optional, will prompt if needed).
        headless: If True, skip browser and use manual paste mode.
        region: 'us' (default) or 'cn' for China.
        timeout: Seconds to wait for automatic callback (default: 120).

    Returns:
        refresh_token string.
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

    # Determine mode: try automatic capture if display available and not headless
    use_auto = not headless and _has_display()

    callback_url = None
    server = None

    if use_auto:
        try:
            port = _find_free_port()

            # Write port file for handler script
            with open(HANDLER_PORT_FILE, "w") as f:
                f.write(str(port))

            # Write handler script
            _write_handler_script()

            # Register protocol handler
            registered = _register_protocol_handler()

            if registered:
                # Start local HTTP server
                server = _CallbackServer(port)
                server.start_background()

                # Open browser
                print("Opening browser for Tesla login...")
                print(
                    "\nAfter logging in, the browser will redirect automatically.\n"
                    "If the redirect fails, copy the FULL URL from the address bar\n"
                    "and paste it below.\n"
                )
                webbrowser.open(auth_url)

                # Wait for automatic callback
                print(f"Waiting for redirect (up to {timeout}s)...")
                result = server.wait_for_code(timeout=timeout)

                if result and "code" in result:
                    codes = result["code"]
                    states = result.get("state", [None])
                    issuers = result.get("issuer", [None])

                    if codes and states and states[0] == state:
                        # Build a fake callback URL to parse consistently
                        issuer = issuers[0] if issuers else None
                        token_url = TOKEN_URL_US
                        if issuer and "auth.tesla.cn" in issuer:
                            token_url = TOKEN_URL_CN

                        print("  ✅ Auth code captured automatically!")
                        tokens = exchange_code(codes[0], code_verifier, token_url)
                        refresh_token = tokens["refresh_token"]
                        print(f"  ✅ Refresh token obtained (expires in {tokens.get('expires_in', '?')}s)")
                        return refresh_token
                    else:
                        print("  ⚠️ State mismatch or empty code, falling back to manual mode.")
                else:
                    print("  ⚠️ Timed out waiting for automatic redirect.")
                    print("  Falling back to manual paste mode.\n")
            else:
                print("  ⚠️ Could not register URI handler, using manual paste mode.\n")

        except Exception as e:
            print(f"  ⚠️ Auto-capture failed ({e}), falling back to manual paste mode.\n")
        finally:
            # Always clean up
            if server:
                try:
                    server.shutdown()
                except Exception:
                    pass
            _unregister_protocol_handler()

    # Manual paste mode (headless, fallback, or auto-capture failed)
    if not headless and _has_display() and callback_url is None:
        # Already opened browser above in auto attempt
        print("Open the following URL if the browser didn't open:")
        print(f"  {auth_url}\n")
        print(
            "After logging in, copy the FULL URL from the address bar\n"
            "(it will start with tesla://) and paste it below.\n"
        )
    elif callback_url is None:
        print(
            "\nOpen the following URL in your browser to log into your Tesla account:\n"
        )
        print(f"  {auth_url}\n")
        print(
            "After logging in, copy the FULL redirect URL from your browser\n"
            "(it will start with tesla://) and paste it below.\n"
        )

    # In auto mode, we may have already opened the browser — offer to open again
    if use_auto and callback_url is None:
        if not headless and _has_display():
            # Browser was already opened; just prompt for paste
            pass
        else:
            webbrowser.open(auth_url)

    callback_url = input("Paste the redirect URL (or press Enter to retry): ").strip()

    if not callback_url:
        raise RuntimeError("No callback URL provided.")

    # Parse callback
    callback = parse_callback_url(callback_url)

    # Validate state (CSRF protection)
    if callback["state"] != state:
        raise RuntimeError("CSRF state mismatch — possible tampering.")

    # Exchange code for tokens
    print("  Exchanging authorization code for tokens...")
    tokens = exchange_code(callback["code"], code_verifier, callback["token_url"])

    refresh_token = tokens["refresh_token"]
    print(f"  ✅ Refresh token obtained (expires in {tokens.get('expires_in', '?')}s)")
    return refresh_token


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

def save_token(refresh_token: str, path: str = None, email: str = None):
    """Save a refresh token to pypowerwall's auth file."""
    if not path:
        path = os.path.join(os.getcwd(), ".pypowerwall.auth")

    if not email:
        email = input("Tesla account email: ").strip()

    data = {}
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}

    data[email] = {
        "refresh_token": refresh_token,
        "access_token": "",
        "expires_at": 0,
    }

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
        "--timeout", "-t", type=int, default=120,
        help="Seconds to wait for automatic redirect (default: 120)",
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
            timeout=args.timeout,
        )
    except (KeyboardInterrupt, EOFError):
        print("\n\nLogin cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        sys.exit(1)

    email = args.email or ""
    save_token(refresh_token, path=args.output, email=email)

    print("\n✅ Done! You can now use pypowerwall with cloud mode.")
    print("   Run: python -m pypowerwall setup")


if __name__ == "__main__":
    main()
