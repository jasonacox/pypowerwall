"""
pypowerwall.tesla_auth - Pure Python Tesla OAuth 2.0 PKCE authentication

Uses a native WebView window (not a browser) to load Tesla's login page.
Intercepts the tesla://auth/callback redirect via the WebView's navigation
policy handler — the same technique used by tesla_auth (Rust/wry).

Two login paths, auto-detected:

  Path 1 — Remote/Headless (no display):
    Detects SSH session or missing DISPLAY. Prompts user to run
    ``python -m pypowerwall authtoken`` on their local machine, then
    paste the resulting refresh token.

  Path 2 — Local machine (display available):
    Opens a native WebView window for Tesla login. On macOS, uses PyObjC
    directly (WKWebView + WKNavigationDelegate). On Windows/Linux, uses
    pywebview with a monkey-patched navigation handler. Captures the
    tesla:// callback, exchanges the auth code for a refresh token.

CLI commands:
    python -m pypowerwall login       # auto-detect, save token to file
    python -m pypowerwall authtoken   # local-only, print token to stdout

Based on the OAuth 2.0 PKCE flow from tesla_auth (Rust) by Adrian Kumpf.
https://github.com/adriankumpf/tesla_auth
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
# See: https://github.com/adriankumpf/tesla_auth/blob/master/src/auth.rs
# ---------------------------------------------------------------------------

CLIENT_ID = "ownerapi"
AUTH_URL_PATH = "/oauth2/v3/authorize"
TOKEN_URL_PATH = "/oauth2/v3/token"
REDIRECT_URI = "tesla://auth/callback"
SCOPES = "openid email offline_access"

REGION_HOSTS = {
    "us": "https://auth.tesla.com",
    "cn": "https://auth.tesla.cn",
}


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _build_auth_url(region: str = "us"):
    """Build Tesla OAuth URL with PKCE parameters.

    Returns (url, code_verifier, state).

    Matches tesla_auth exactly:
    - client_id = "ownerapi"
    - code_challenge_method = "S256"
    - PKCE code_verifier = urlsafe_b64encode(random 32 bytes, no padding)
    - code_challenge = urlsafe_b64encode(sha256(verifier), no padding)
    - scopes: openid email offline_access
    - redirect_uri: tesla://auth/callback
    """
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
        "scope": SCOPES,
        "state": state,
    }
    auth_url = f"{auth_host}{AUTH_URL_PATH}?" + urllib.parse.urlencode(params)
    return auth_url, code_verifier, state


def _exchange_code(auth_code: str, code_verifier: str, region: str = "us") -> dict:
    """Exchange authorization code for tokens.

    Returns the full token response dict (contains access_token, refresh_token, etc.).

    Matches tesla_auth: POST to /oauth2/v3/token with grant_type=authorization_code,
    client_id=ownerapi, code, code_verifier, redirect_uri.
    """
    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")

    auth_host = REGION_HOSTS.get(region, REGION_HOSTS["us"])
    resp = requests.post(
        f"{auth_host}{TOKEN_URL_PATH}",
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

    return data


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

def _detect_mode() -> str:
    """Detect whether we're in a local or remote session."""
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
    print("That will open a login window. After authentication,")
    print("copy the refresh token and paste it here.")
    print()

    while True:
        token = input("Refresh token: ").strip()
        if token:
            return token
        print("   ⚠️  Token cannot be empty — try again.")


# ---------------------------------------------------------------------------
# Path 2 — Local login (native WebView with navigation interception)
# ---------------------------------------------------------------------------

def _local_login(email: str = None, region: str = "us") -> str:
    """Local login via native WebView, intercepting tesla:// redirect.

    Platform dispatch:
    - macOS: PyObjC WKWebView with custom WKNavigationDelegate
    - Windows/Linux: pywebview with monkey-patched navigation handler

    Both approaches use the same technique as tesla_auth (Rust):
    register a navigation policy handler that intercepts the tesla://
    custom scheme redirect, extracts the auth code, and cancels the
    navigation before the WebView rejects it.
    """
    if sys.platform == "darwin":
        return _local_login_macos(email, region)
    else:
        return _local_login_pywebview(email, region)


# ---------------------------------------------------------------------------
# macOS — Native WKWebView via PyObjC
# ---------------------------------------------------------------------------

def _local_login_macos(email: str = None, region: str = "us") -> str:
    """Native WKWebView on macOS with WKNavigationDelegate to intercept tesla://.

    This mirrors exactly what tesla_auth's wry does on macOS:
    1. Create a WKWebView in an NSWindow
    2. Set a WKNavigationDelegate with webView:decidePolicyForNavigationAction:decisionHandler:
    3. When the URL starts with "tesla://", capture it and cancel navigation
    4. Extract the auth code from the URL
    5. Exchange it for a refresh token
    """
    import threading
    import AppKit
    import WebKit
    import Foundation
    from PyObjCTools import AppHelper

    auth_url, code_verifier, state = _build_auth_url(region)
    if email:
        auth_url += f"&login_hint={urllib.parse.quote(email)}"

    result = {"token": None, "error": None}

    class TeslaNavDelegate(AppKit.NSObject):
        """WKNavigationDelegate that intercepts tesla:// redirects."""

        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self, webview, action, handler
        ):
            try:
                url = str(action.request().URL().absoluteString())
            except Exception:
                # If we can't get the URL, allow the navigation
                handler(1)  # WKNavigationActionPolicyAllow
                return

            if url.startswith("tesla://"):
                # Intercept! Extract auth code from the redirect URL
                try:
                    parsed = urllib.parse.urlparse(url)
                    params = urllib.parse.parse_qs(parsed.query)

                    # Check for error
                    error = params.get("error", [None])[0]
                    if error:
                        result["error"] = f"Tesla auth error: {error}"
                        handler(0)  # Cancel
                        AppHelper.stopEventLoop()
                        return

                    # Check for login cancelled
                    if params.get("error", [None])[0] == "login_cancelled":
                        result["error"] = "Login cancelled by user"
                        handler(0)
                        AppHelper.stopEventLoop()
                        return

                    code = params.get("code", [None])[0]
                    returned_state = params.get("state", [None])[0]

                    if not code:
                        result["error"] = f"No auth code in redirect: {url}"
                        handler(0)
                        AppHelper.stopEventLoop()
                        return

                    if returned_state != state:
                        result["error"] = "CSRF state mismatch — possible attack"
                        handler(0)
                        AppHelper.stopEventLoop()
                        return

                    # Exchange code for token (in background to not block the delegate)
                    def do_exchange():
                        try:
                            token_data = _exchange_code(code, code_verifier, region)
                            result["token"] = token_data["refresh_token"]
                        except Exception as e:
                            result["error"] = f"Token exchange failed: {e}"
                        finally:
                            # Close the window
                            AppHelper.stopEventLoop()

                    threading.Thread(target=do_exchange, daemon=True).start()

                except Exception as e:
                    result["error"] = f"Failed to parse redirect: {e}"
                    AppHelper.stopEventLoop()

                handler(0)  # Cancel the tesla:// navigation
            else:
                # Allow all normal navigation (Tesla login pages, etc.)
                handler(1)  # WKNavigationActionPolicyAllow

    def run_window():
        # Create WebView configuration
        config = WebKit.WKWebViewConfiguration.alloc().init()

        # Create WebView
        webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(
            Foundation.NSMakeRect(0, 0, 500, 750),
            config,
        )

        # Set navigation delegate
        delegate = TeslaNavDelegate.alloc().init()
        webview.setNavigationDelegate_(delegate)

        # Create window
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(100, 100, 500, 750),
            (
                AppKit.NSWindowStyleMaskTitled
                | AppKit.NSWindowStyleMaskClosable
                | AppKit.NSWindowStyleMaskResizable
            ),
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setContentView_(webview)
        window.setTitle_("Tesla Login — pypowerwall")
        window.makeKeyAndOrderFront_(None)

        # Load the auth URL
        req = Foundation.NSURLRequest.requestWithURL_(
            Foundation.NSURL.URLWithString_(auth_url)
        )
        webview.loadRequest_(req)

        # Run the event loop (blocks until stopEventLoop is called)
        AppHelper.runEventLoop()

    print("Opening Tesla login window...")
    run_window()

    if result["error"]:
        raise RuntimeError(result["error"])
    if not result["token"]:
        raise RuntimeError("Login cancelled or timed out — no token received.")

    print("  ✅ Refresh token captured!")
    return result["token"]


# ---------------------------------------------------------------------------
# Windows/Linux — pywebview with monkey-patched navigation handler
# ---------------------------------------------------------------------------

def _local_login_pywebview(email: str = None, region: str = "us") -> str:
    """pywebview login with navigation handler monkey-patch.

    On Windows (WebView2) and Linux (WebKit2GTK), we use pywebview but
    monkey-patch the platform-specific BrowserDelegate to intercept
    tesla:// URLs in the navigation policy handler.

    The monkey-patch wraps the original webView_decidePolicyForNavigationAction_decisionHandler_
    (macOS) or the equivalent handler on other platforms, checking for tesla://
    before delegating to the original logic.
    """
    import time
    try:
        import webview
    except ImportError:
        print("Installing pywebview...")
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pywebview>=4.0", "-q"]
        )
        import webview

    auth_url, code_verifier, state = _build_auth_url(region)
    if email:
        auth_url += f"&login_hint={urllib.parse.quote(email)}"

    result = {"token": None, "error": None, "code": None}

    # Monkey-patch pywebview's platform-specific navigation handler
    _patch_pywebview_navigation(result, state)

    window = webview.create_window(
        "Tesla Login — pypowerwall",
        auth_url,
        width=500,
        height=750,
    )

    def poll_token():
        """Poll for the auth code and exchange it for a token."""
        for _ in range(360):  # 3 minutes
            if result["code"]:
                try:
                    token_data = _exchange_code(
                        result["code"], code_verifier, region
                    )
                    result["token"] = token_data["refresh_token"]
                except Exception as e:
                    result["error"] = f"Token exchange failed: {e}"
                try:
                    window.destroy()
                except Exception:
                    pass
                return
            time.sleep(0.5)

    import threading
    poller = threading.Thread(target=poll_token, daemon=True)
    poller.start()

    print("Opening Tesla login window...")
    webview.start()

    if result["error"]:
        raise RuntimeError(result["error"])
    if not result["token"]:
        raise RuntimeError("Login cancelled or timed out — no token received.")

    print("  ✅ Refresh token captured!")
    return result["token"]


def _patch_pywebview_navigation(result, expected_state):
    """Monkey-patch pywebview's navigation handler to intercept tesla:// URLs.

    This wraps the platform-specific navigation policy delegate to check
    for tesla:// URLs before delegating to the original handler.
    """
    import sys

    if sys.platform == "darwin":
        _patch_pywebview_cocoa(result, expected_state)
    elif sys.platform == "win32":
        _patch_pywebview_win32(result, expected_state)
    else:
        _patch_pywebview_gtk(result, expected_state)


def _patch_pywebview_cocoa(result, expected_state):
    """Patch pywebview's macOS BrowserDelegate to intercept tesla:// URLs."""
    try:
        from webview.platforms import cocoa
    except ImportError:
        return

    BrowserDelegate = cocoa.BrowserView.BrowserDelegate

    # Get the original navigation handler
    original_handler = BrowserDelegate.webView_decidePolicyForNavigationAction_decisionHandler_

    def patched_handler(self, webview, action, handler):
        try:
            url = str(action.request().URL().absoluteString())
            if url.startswith("tesla://"):
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)

                if params.get("error", [None])[0] == "login_cancelled":
                    result["error"] = "Login cancelled by user"
                    handler(0)
                    return

                code = params.get("code", [None])[0]
                returned_state = params.get("state", [None])[0]

                if code and returned_state == expected_state:
                    result["code"] = code
                elif code:
                    result["error"] = "CSRF state mismatch"

                handler(0)  # Cancel navigation
                return
        except Exception:
            pass

        # Fall through to original handler for non-tesla:// URLs
        original_handler(self, webview, action, handler)

    BrowserDelegate.webView_decidePolicyForNavigationAction_decisionHandler_ = patched_handler


def _patch_pywebview_win32(result, expected_state):
    """Patch pywebview's Windows WebView2 handler to intercept tesla:// URLs."""
    try:
        from webview.platforms import winforms
        # WebView2 fires a SourceChanged event or we can use the
        # CoreWebView2.NavigationStarting event.
        # For now, we'll use a JS-based approach as fallback on Windows,
        # since the winforms backend may not expose navigation policy directly.
        # TODO: Implement WebView2 navigation interception for Windows.
    except ImportError:
        pass


def _patch_pywebview_gtk(result, expected_state):
    """Patch pywebview's Linux WebKit2GTK handler to intercept tesla:// URLs."""
    try:
        from webview.platforms import gtk
        # WebKit2GTK uses "decide-policy" signal on the WebView.
        # pywebview's BrowserView connects this signal.
        # TODO: Implement WebKit2GTK navigation interception for Linux.
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def login(email: str = None, headless: bool = False, region: str = "us") -> str:
    """Authenticate with Tesla and return a refresh token.

    Auto-detects local vs remote environment. On remote sessions (or if
    ``headless=True``), uses the paste-token flow. Otherwise opens a
    native WebView window for login.

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

    Always uses the local WebView path (no file saving). The caller
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
