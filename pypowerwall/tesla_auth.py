"""
pypowerwall.tesla_auth - Pure Python Tesla OAuth 2.0 PKCE authentication

Two login paths, auto-detected:

  Path 1 — Remote/Headless (no display):
    Detects SSH session or missing DISPLAY. Prompts user to run
    ``python -m pypowerwall authtoken`` on their local machine, then
    paste the resulting refresh token.

  Path 2 — Local machine (display available):
    Opens a native pywebview window for Tesla login. Captures the
    tesla:// callback, exchanges the auth code for a refresh token.

CLI commands:
    python -m pypowerwall login       # auto-detect, save token to file
    python -m pypowerwall authtoken   # local-only, print token to stdout

Based on the OAuth 2.0 PKCE flow from tesla_auth (Rust) by Adrian Kumpf.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse

try:
    import requests
except ImportError:
    requests = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants — match tesla_auth Rust exactly
# ---------------------------------------------------------------------------

AUTH_HOST = "https://auth.tesla.com"
CLIENT_ID = "ownerapi"
REDIRECT_URI = "tesla://auth/callback"

REGION_HOSTS = {
    "us": "https://auth.tesla.com",
    "cn": "https://auth.tesla.cn",
}


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _build_auth_url(region: str = "us"):
    """Build Tesla OAuth URL with PKCE parameters. Returns (url, code_verifier, state)."""
    auth_host = REGION_HOSTS.get(region, REGION_HOSTS["us"])

    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": CLIENT_ID,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email offline_access",
        "state": state,
    }
    auth_url = f"{auth_host}/oauth2/v3/authorize?" + urllib.parse.urlencode(params)
    return auth_url, code_verifier, state


def _exchange_code(auth_code: str, code_verifier: str, region: str = "us") -> str:
    """Exchange authorization code for a refresh token. Returns refresh_token string."""
    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")

    auth_host = REGION_HOSTS.get(region, REGION_HOSTS["us"])
    resp = requests.post(
        f"{auth_host}/oauth2/v3/token",
        json={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": auth_code,
            "code_verifier": code_verifier,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    if "refresh_token" not in data:
        raise RuntimeError(f"No refresh_token in response: {data}")

    return data["refresh_token"]


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

def _detect_mode() -> str:
    """Detect whether we're in a local or remote session.

    Returns 'remote' if SSH env vars are set or DISPLAY is empty on Linux,
    otherwise 'local'.
    """
    if os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        return "remote"
    if sys.platform == "linux" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return "remote"
    return "local"


# ---------------------------------------------------------------------------
# Path 1 — Remote/Headless login (paste token)
# ---------------------------------------------------------------------------

def _remote_login() -> str:
    """Remote login: instruct user to run authtoken locally, then paste token."""
    print("\n" + "=" * 60)
    print("Tesla Authentication — Remote Session Detected")
    print("=" * 60)
    print()
    print("You're on a remote session. On your local Mac/PC with")
    print("pypowerwall installed, run:")
    print()
    print("    python -m pypowerwall authtoken")
    print()
    print("That will open a browser window, log you in, and print")
    print("your refresh token.")
    print()
    print("Paste the token here when ready:")
    print()

    while True:
        token = input("Token: ").strip()
        if token:
            return token
        print("   ⚠️  Token cannot be empty — try again.")


# ---------------------------------------------------------------------------
# Path 2 — Local login (pywebview)
# ---------------------------------------------------------------------------

def _local_login(email: str = None, region: str = "us") -> str:
    """Local login: open pywebview window, capture callback, exchange for token.

    Returns refresh_token string.
    """
    try:
        import webview  # noqa: F401
    except ImportError:
        print("⚠️  pywebview is not installed.")
        print("   Installing pywebview for native browser login...")
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pywebview", "--quiet"]
        )
        print("   ✅ pywebview installed.\n")
        # Re-import after install
        import webview

    auth_url, code_verifier, state = _build_auth_url(region)

    if email:
        # Append login_hint for a smoother UX
        auth_url += f"&login_hint={urllib.parse.quote(email)}"

    result = {}

    class TeslaAuthApi:
        """JS API bridge — called from injected JS when tesla:// redirect fires."""
        def __init__(self, window_holder):
            self.window_holder = window_holder

        def capture(self, url):
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            result["code"] = params.get("code", [None])[0]
            self.window_holder["window"].destroy()

    window_holder = {}
    api = TeslaAuthApi(window_holder)

    # JS injected on every page load — overrides window.open and link clicks
    # to intercept the tesla:// redirect before the browser tries to launch it
    intercept_js = """
    (function() {
        var _open = window.open;
        window.open = function(url, target, features) {
            if (url && url.indexOf('tesla://') === 0) {
                window.pywebview.api.capture(url);
                return;
            }
            return _open(url, target, features);
        };
        document.addEventListener('click', function(e) {
            var el = e.target;
            while (el) {
                if (el.tagName === 'A' && el.href && el.href.indexOf('tesla://') === 0) {
                    e.preventDefault();
                    window.pywebview.api.capture(el.href);
                    return;
                }
                el = el.parentElement;
            }
        }, true);
    })();
    """

    def on_loaded():
        window_holder["window"].evaluate_js(intercept_js)

    print("Opening Tesla login window...")
    window = webview.create_window(
        "Tesla Login — pypowerwall", auth_url, width=500, height=750, js_api=api
    )
    window_holder["window"] = window
    webview.start(on_loaded)

    auth_code = result.get("code")
    if not auth_code:
        raise RuntimeError("Login cancelled or timed out — no authorization code received.")

    print("  ✅ Authorization code captured!")
    print("  Exchanging for refresh token...")
    refresh_token = _exchange_code(auth_code, code_verifier, region)
    return refresh_token


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def login(email: str = None, headless: bool = False, region: str = "us") -> str:
    """Authenticate with Tesla and return a refresh token.

    Auto-detects local vs remote environment. On remote sessions (or if
    ``headless=True``), uses the paste-token flow. Otherwise opens a
    pywebview window for browser login.

    Args:
        email: Tesla account email (optional, used as login hint).
        headless: Force remote/paste mode regardless of environment.
        region: 'us' (default) or 'cn'.

    Returns:
        refresh_token string.
    """
    if headless or _detect_mode() == "remote":
        return _remote_login()

    return _local_login(email=email, region=region)


def get_authtoken(region: str = "us") -> str:
    """Get a refresh token for the ``authtoken`` CLI command.

    Always uses the local pywebview path (no file saving). The caller
    is responsible for displaying or using the token.
    """
    return _local_login(region=region)


def save_token(refresh_token: str, path: str = None, email: str = None):
    """Save a refresh token to the pypowerwall auth file (.pypowerwall.auth).

    Args:
        refresh_token: The token to save.
        path: File path (default: .pypowerwall.auth in current directory).
        email: Email address to associate with the token.
    """
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
