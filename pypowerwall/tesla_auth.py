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
import ssl
import sys
import urllib.parse

try:
    import requests
except ImportError:
    requests = None  # type: ignore

# Optional HTTP/2 support for Tesla auth (required as of June 2026)
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


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


def _httpx_auth_verify(verify=True):
    """Return an httpx-compatible verify setting pinned to TLS 1.3 when possible."""
    if verify is False:
        return False
    if isinstance(verify, (str, bytes)):
        return verify
    if isinstance(verify, ssl.SSLContext):
        return verify
    if hasattr(ssl, "TLSVersion") and hasattr(ssl.TLSVersion, "TLSv1_3"):
        try:
            ctx = ssl.create_default_context()
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
            ctx.maximum_version = ssl.TLSVersion.TLSv1_3
            return ctx
        except Exception:
            pass
    return verify


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


def _refresh_access_token(refresh_token: str, region: str = "us") -> dict:
    """Exchange a refresh token for a fresh access token.

    Tesla OAuth refresh: POST /oauth2/v3/token with grant_type=refresh_token,
    client_id=ownerapi, refresh_token.
    """
    if requests is None and not HAS_HTTPX:
        raise ImportError("The 'requests' or 'httpx' package is required.")

    auth_host = REGION_HOSTS.get(region, REGION_HOSTS["us"])
    url = f"{auth_host}{TOKEN_URL_PATH}"
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }

    # Tesla now requires HTTP/2 for auth.tesla.com token endpoints
    if HAS_HTTPX:
        try:
            with httpx.Client(http2=True, verify=_httpx_auth_verify()) as client:
                resp = client.post(url, json=payload, timeout=30)
                if resp.status_code != 200:
                    raise RuntimeError(f"Token refresh failed (HTTP {resp.status_code}): {resp.text}")
                data = resp.json()
                if "access_token" not in data:
                    raise RuntimeError(f"No access_token in refresh response: {data}")
                return data
        except RuntimeError:
            raise  # Application errors (non-200, missing token) should not fall back
        except Exception as exc:
            # Transport/connection errors only — fall back to requests if available
            if requests is None:
                raise RuntimeError(f"HTTP/2 transport failed and 'requests' not installed: {exc}") from exc

    if requests is None:
        raise ImportError("The 'requests' or 'httpx' package is required.")
    resp = requests.post(url, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"No access_token in refresh response: {data}")

    return data


def _exchange_code(auth_code: str, code_verifier: str, region: str = "us") -> dict:
    """Exchange authorization code for tokens.

    Returns the full token response dict (contains access_token, refresh_token, etc.).

    Matches tesla_auth: POST to /oauth2/v3/token with grant_type=authorization_code,
    client_id=ownerapi, code, code_verifier, redirect_uri.
    """
    if requests is None and not HAS_HTTPX:
        raise ImportError("The 'requests' or 'httpx' package is required. Install with: pip install requests")

    auth_host = REGION_HOSTS.get(region, REGION_HOSTS["us"])
    url = f"{auth_host}{TOKEN_URL_PATH}"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": auth_code,
        "code_verifier": code_verifier,
        "redirect_uri": REDIRECT_URI,
    }

    # Tesla now requires HTTP/2 for auth.tesla.com token endpoints
    if HAS_HTTPX:
        try:
            with httpx.Client(http2=True, verify=_httpx_auth_verify()) as client:
                resp = client.post(url, json=payload, timeout=30)
                if resp.status_code != 200:
                    raise RuntimeError(f"Token exchange failed (HTTP {resp.status_code}): {resp.text}")
                data = resp.json()
                if "refresh_token" not in data:
                    raise RuntimeError(f"No refresh_token in response: {data}")
                return data
        except RuntimeError:
            raise  # Application errors (non-200, missing token) should not fall back
        except Exception as exc:
            # Transport/connection errors only — fall back to requests if available
            if requests is None:
                raise RuntimeError(f"HTTP/2 transport failed and 'requests' not installed: {exc}") from exc

    if requests is None:
        raise ImportError("The 'requests' package is required. Install with: pip install requests")
    resp = requests.post(url, json=payload, timeout=30)
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

def _read_masked(prompt: str) -> str:
    """Read a line from the terminal echoing '*' for every character typed.

    Reads directly from /dev/tty (Unix) or via msvcrt (Windows) so it works
    even when sys.stdin has been redirected or left in a broken state.
    Uses raw mode to bypass the terminal's 1024-byte canonical line buffer,
    which would otherwise truncate long tokens on paste.
    Handles backspace, Ctrl+C, and Ctrl+D correctly.
    Falls back to a plain readline if the terminal cannot be put into raw mode.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()

    # ---- Windows --------------------------------------------------------
    if sys.platform == 'win32':
        import msvcrt
        chars = []
        while True:
            ch = msvcrt.getwch()
            if ch in ('\r', '\n'):
                sys.stdout.write('\n')
                sys.stdout.flush()
                break
            if ch in ('\x08', '\x7f'):          # backspace
                if chars:
                    chars.pop()
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            elif ch == '\x03':                   # Ctrl+C
                raise KeyboardInterrupt
            elif ch.isprintable():
                chars.append(ch)
                sys.stdout.write('*')
                sys.stdout.flush()
        return ''.join(chars).strip()

    # ---- Unix (macOS / Linux) -------------------------------------------
    try:
        import termios
        import tty
    except ImportError:
        # termios not available — plain readline fallback
        line = sys.stdin.readline()
        sys.stdout.write('\n')
        sys.stdout.flush()
        return line.rstrip('\n').strip()

    # Always read from the controlling terminal so we work even when
    # sys.stdin has been redirected or reset after an NSApplication run.
    try:
        tty_fd = open('/dev/tty', 'r+b', buffering=0)
    except OSError:
        line = sys.stdin.readline()
        sys.stdout.write('\n')
        sys.stdout.flush()
        return line.rstrip('\n').strip()

    chars = []
    old_settings = termios.tcgetattr(tty_fd)
    try:
        tty.setraw(tty_fd)
        while True:
            ch = tty_fd.read(1).decode('utf-8', errors='replace')
            if ch in ('\n', '\r'):
                sys.stdout.write('\n')
                sys.stdout.flush()
                break
            if ch in ('\x7f', '\x08'):           # backspace / delete
                if chars:
                    chars.pop()
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            elif ch == '\x03':                    # Ctrl+C
                sys.stdout.write('\n')
                sys.stdout.flush()
                raise KeyboardInterrupt
            elif ch == '\x04':                    # Ctrl+D / EOF
                sys.stdout.write('\n')
                sys.stdout.flush()
                raise EOFError
            elif ch.isprintable():
                chars.append(ch)
                sys.stdout.write('*')
                sys.stdout.flush()
    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_settings)
        tty_fd.close()

    return ''.join(chars).strip()


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
        token = _read_masked("Refresh token: ")
        if token:
            return token
        print("   ⚠️  Token cannot be empty — try again.")


# ---------------------------------------------------------------------------
# Path 2 — Local login (native WebView with navigation interception)
# ---------------------------------------------------------------------------

def _local_login(email: str = None, region: str = "us", debug: bool = False,
                   show_token_page: bool = False):
    """Local login via native WebView. Returns (refresh_token, email, token_data) tuple.

    Args:
        show_token_page: If True, show a success page with the token after auth
                         (for `authtoken` command). If False, auto-close window
                         after token capture (for `setup` command).
    """
    if sys.platform == "darwin":
        return _local_login_macos(email, region, debug=debug,
                                  show_token_page=show_token_page)
    else:
        return _local_login_pywebview(email, region,
                                      show_token_page=show_token_page)


# ---------------------------------------------------------------------------
# macOS — Native WKWebView via PyObjC
# ---------------------------------------------------------------------------

def _local_login_macos(email: str = None, region: str = "us", debug: bool = False,
                          show_token_page: bool = False) -> str:
    """Native WKWebView on macOS with WKNavigationDelegate to intercept tesla://.

    This mirrors exactly what tesla_auth's wry does on macOS:
    1. Create a WKWebView in an NSWindow
    2. Set a WKNavigationDelegate with webView:decidePolicyForNavigationAction:decisionHandler:
    3. When the URL starts with "tesla://", capture it and cancel navigation
    4. Extract the auth code from the URL
    5. Exchange it for a refresh token
    """
    import threading
    try:
        import AppKit
        import WebKit
        import Foundation
        from PyObjCTools import AppHelper
    except ImportError:
        print("Installing pyobjc-framework-WebKit...")
        import subprocess
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyobjc-framework-WebKit", "-q"]
        )
        import AppKit
        import WebKit
        import Foundation
        from PyObjCTools import AppHelper

    auth_url, code_verifier, state = _build_auth_url(region)
    if email:
        auth_url += f"&login_hint={urllib.parse.quote(email)}"

    result = {"token": None, "error": None, "email": "", "token_data": {}}
    exchange_done = threading.Event()
    webview_ref = [None]  # mutable container so closure can access it
    window_ref = [None]   # mutable container for the NSWindow


    def dbg(msg):
        if debug:
            print(f"  [debug] {msg}")

    class TeslaNavDelegate(AppKit.NSObject):
        """WKNavigationDelegate that intercepts tesla:// redirects."""

        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self, webview, action, handler
        ):
            try:
                url = str(action.request().URL().absoluteString())
            except Exception as e:
                dbg(f"Could not get URL: {e}")
                handler(1)
                return

            dbg(f"Navigation: {url[:100]}")

            # Handle our own action URLs
            if url.startswith("pypowerwall://"):
                action = url.split("pypowerwall://")[1].split("?")[0]
                dbg(f"pypowerwall action: {action}")
                if action == "copy":
                    try:
                        token = result.get("token", "")
                        if token:
                            pb = AppKit.NSPasteboard.generalPasteboard()
                            pb.clearContents()
                            pb.setString_forType_(token, AppKit.NSPasteboardTypeString)
                            dbg("Token copied to clipboard via button")
                    except Exception as e:
                        dbg(f"Clipboard error: {e}")
                elif action == "close":
                    # Close window explicitly — triggers windowWillClose_ → stop_()
                    if window_ref[0]:
                        window_ref[0].close()
                    else:
                        AppKit.NSApplication.sharedApplication().stop_(None)
                handler(0)
                return

            if url.startswith("tesla://"):
                dbg(f"INTERCEPTED tesla:// URL: {url[:120]}")
                try:
                    parsed = urllib.parse.urlparse(url)
                    params = urllib.parse.parse_qs(parsed.query)
                    dbg(f"Params: {list(params.keys())}")

                    error = params.get("error", [None])[0]
                    if error:
                        result["error"] = f"Tesla auth error: {error}"
                        dbg(f"Auth error from Tesla: {error}")
                        handler(0)
                        AppKit.NSApplication.sharedApplication().stop_(None)
                        return

                    code = params.get("code", [None])[0]
                    returned_state = params.get("state", [None])[0]
                    dbg(f"Code present: {bool(code)}, State match: {returned_state == state}")

                    if not code:
                        result["error"] = f"No auth code in redirect: {url}"
                        handler(0)
                        AppKit.NSApplication.sharedApplication().stop_(None)
                        return

                    if returned_state != state:
                        result["error"] = "CSRF state mismatch"
                        dbg(f"State mismatch: got {returned_state!r} expected {state!r}")
                        handler(0)
                        AppKit.NSApplication.sharedApplication().stop_(None)
                        return

                    dbg("Auth code captured — exchanging for token...")

                    def do_exchange():
                        try:
                            data = _exchange_code(code, code_verifier, region)
                            token = data["refresh_token"] if isinstance(data, dict) else data
                            dbg(f"Token exchange succeeded, token length: {len(token)}")
                            result["token"] = token
                            result["token_data"] = data if isinstance(data, dict) else {}
                            # Extract email from id_token if available
                            if isinstance(data, dict) and data.get("id_token"):
                                result["email"] = _extract_email_from_token(data["id_token"])
                                dbg(f"Email from id_token: {result['email']}")
                            # Copy to macOS clipboard via NSPasteboard
                            try:
                                pb = AppKit.NSPasteboard.generalPasteboard()
                                pb.clearContents()
                                pb.setString_forType_(token, AppKit.NSPasteboardTypeString)
                                clipboard_ok = True
                            except Exception:
                                clipboard_ok = False
                            # Print immediately to terminal
                            print("\n" + "=" * 60)
                            print("\u2705 Tesla Refresh Token:")
                            print("-" * 60)
                            print(token)
                            print("-" * 60)
                            if not show_token_page:
                                # Auto-close for setup — no success page needed
                                print("  \u2705 Token captured — setup will continue.")
                            elif clipboard_ok:
                                print("Token copied to clipboard! You can now close the window.")
                            else:
                                print("Copy the token above. You can now close the window.")
                            # Only load success page for authtoken (show_token_page=True)
                            if show_token_page:
                              success_html = f"""<!DOCTYPE html><html><head>
<meta charset='utf-8'>
<style>
  body {{ font-family: -apple-system, sans-serif; padding: 20px; background: #f5f5f7; }}
  h2 {{ color: #1d1d1f; }}
  .token-box {{ background: white; border: 1px solid #d2d2d7; border-radius: 10px;
    padding: 15px; word-break: break-all; font-family: monospace; font-size: 11px;
    color: #333; margin: 15px 0; }}
  .copy-btn {{ background: #0071e3; color: white; border: none; border-radius: 8px;
    padding: 10px 20px; font-size: 15px; cursor: pointer; width: 100%; }}
  .copy-btn:active {{ background: #0077ed; }}
  p {{ color: #6e6e73; font-size: 13px; }}
</style></head><body>
<h2>\u2705 Authentication Successful</h2>
<p>Your Tesla refresh token is ready. It has been <strong>copied to your clipboard</strong> automatically.</p>
<div class='token-box' id='tokenText'>{token}</div>
<div style='display:flex; gap:10px; margin-top:5px'>
  <a href='pypowerwall://copy' style='flex:1; text-decoration:none'>
    <button class='copy-btn' id='copyBtn' style='width:100%' onclick="
      document.getElementById('copyBtn').textContent = '\u2705 Copied!';
      document.getElementById('copyBtn').style.background = '#34c759';
      setTimeout(function(){{
        document.getElementById('copyBtn').textContent = 'Copy Token';
        document.getElementById('copyBtn').style.background = '#0071e3';
      }}, 2500);
    ">Copy Token</button>
  </a>
  <a href='pypowerwall://close' style='flex:1; text-decoration:none'>
    <button style='width:100%; background:#636366; color:white; border:none; border-radius:8px;
      padding:10px 20px; font-size:15px; cursor:pointer'>Close Window</button>
  </a>
</div>
</body></html>"""
                              def load_success():
                                  webview_ref[0].loadHTMLString_baseURL_(success_html, None)
                              AppHelper.callAfter(load_success)
                        except Exception as e:
                            result["error"] = f"Token exchange failed: {e}"
                            dbg(f"Token exchange error: {e}")
                        finally:
                            exchange_done.set()
                            if not show_token_page:
                                # Auto-close for setup — token is saved to file
                                def close_after_exchange():
                                    if window_ref[0]:
                                        window_ref[0].close()
                                    else:
                                        AppKit.NSApplication.sharedApplication().stop_(None)
                                AppHelper.callAfter(close_after_exchange)
                            # else: Window stays open for user to click Close button

                    threading.Thread(target=do_exchange, daemon=True).start()

                except Exception as e:
                    result["error"] = f"Failed to parse redirect: {e}"
                    dbg(f"Parse error: {e}")
                    AppKit.NSApplication.sharedApplication().stop_(None)

                handler(0)  # Cancel the tesla:// navigation
            else:
                # Allow all normal navigation
                handler(1)

    def run_window():
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
        config = WebKit.WKWebViewConfiguration.alloc().init()
        # Use non-persistent data store so every run starts with no cookies/cache
        config.setWebsiteDataStore_(WebKit.WKWebsiteDataStore.nonPersistentDataStore())
        webview_obj = WebKit.WKWebView.alloc().initWithFrame_configuration_(
            Foundation.NSMakeRect(0, 0, 500, 750), config,
        )
        webview_ref[0] = webview_obj
        delegate = TeslaNavDelegate.alloc().init()
        delegate.retain()
        webview_obj.setNavigationDelegate_(delegate)

        class WindowDelegate(AppKit.NSObject):
            def windowWillClose_(self, notification):
                app = AppKit.NSApplication.sharedApplication()
                window = notification.object()
                window.orderOut_(None)  # ensure window disappears immediately
                app.hide_(None)  # return focus to previous app
                app.stop_(None)
        win_delegate = WindowDelegate.alloc().init()
        win_delegate.retain()

        ns_window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(200, 200, 500, 750),
            (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
             | AppKit.NSWindowStyleMaskResizable),
            AppKit.NSBackingStoreBuffered, False,
        )
        ns_window.setContentView_(webview_obj)
        ns_window.setTitle_("Tesla Login - pypowerwall")
        ns_window.setDelegate_(win_delegate)
        ns_window.makeKeyAndOrderFront_(None)
        ns_window.retain()
        window_ref[0] = ns_window
        req = Foundation.NSURLRequest.requestWithURL_(
            Foundation.NSURL.URLWithString_(auth_url)
        )
        webview_obj.loadRequest_(req)
        app.activateIgnoringOtherApps_(True)

        # Add Edit menu so Cmd+V (paste) and other shortcuts work in WKWebView
        edit_menu = AppKit.NSMenu.alloc().initWithTitle_("Edit")
        edit_menu.addItemWithTitle_action_keyEquivalent_("Cut", "cut:", "x")
        edit_menu.addItemWithTitle_action_keyEquivalent_("Copy", "copy:", "c")
        edit_menu.addItemWithTitle_action_keyEquivalent_("Paste", "paste:", "v")
        edit_menu.addItemWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a")
        edit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Edit", None, "")
        edit_item.setSubmenu_(edit_menu)
        main_menu = AppKit.NSMenu.alloc().init()
        main_menu.addItem_(edit_item)
        app.setMainMenu_(main_menu)

        AppHelper.runEventLoop()

    print("Opening Tesla login window...")
    run_window()
    exchange_done.wait(timeout=15)

    if result["error"]:
        raise RuntimeError(result["error"])
    if not result["token"]:
        raise RuntimeError("Login cancelled - no token received.")
    return result["token"], result.get("email", ""), result.get("token_data", {})


def _local_login_pywebview(email: str = None, region: str = "us",
                            show_token_page: bool = False) -> str:
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
                token = result["token"]
                print("\n" + "=" * 60)
                print("\u2705 Tesla Refresh Token:")
                print("-" * 60)
                print(token)
                print("-" * 60)

                if show_token_page:
                    # Show success page with Copy Token button
                    # Uses hidden textarea + execCommand fallback because
                    # navigator.clipboard.writeText() fails in WebView2 on Windows
                    # (requires secure context / HTTPS which local HTML doesn't have)
                    # Try Python-side clipboard copy first (works on all platforms)
                    try:
                        import subprocess
                        if sys.platform == 'win32':
                            subprocess.run(['clip'], input=token.encode(), check=True)
                            print("Token copied to clipboard!")
                        elif sys.platform == 'linux':
                            # Try xclip, then xsel, then wl-copy
                            for cmd in [['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input'], ['wl-copy']]:
                                try:
                                    subprocess.run(cmd, input=token.encode(), check=True)
                                    print("Token copied to clipboard!")
                                    break
                                except (FileNotFoundError, subprocess.CalledProcessError):
                                    continue
                        elif sys.platform == 'darwin':
                            subprocess.run(['pbcopy'], input=token.encode(), check=True)
                            print("Token copied to clipboard!")
                    except Exception:
                        pass
                    print("Copy the token above or use the button in the window.")
                    success_html = f"""<!DOCTYPE html><html><head>
<meta charset='utf-8'>
<style>
  body {{ font-family: -apple-system, sans-serif; padding: 20px; background: #f5f5f7; }}
  h2 {{ color: #1d1d1f; }}
  .token-box {{ background: white; border: 1px solid #d2d2d7; border-radius: 10px;
    padding: 15px; word-break: break-all; font-family: monospace; font-size: 11px;
    color: #333; margin: 15px 0; user-select: all; cursor: text; }}
  .copy-btn {{ background: #0071e3; color: white; border: none; border-radius: 8px;
    padding: 10px 20px; font-size: 15px; cursor: pointer; width: 100%; }}
  .copy-btn:active {{ background: #0077ed; }}
  p {{ color: #6e6e73; font-size: 13px; }}
  #fallback {{ position: absolute; left: -9999px; }}
</style></head><body>
<h2>\u2705 Authentication Successful</h2>
<p>Your Tesla refresh token is shown below. Click the token box to select it, then press Ctrl+C to copy.</p>
<div class='token-box' id='tokenText' onclick="document.execCommand('selectAll',false,null)">{token}</div>
<textarea id='fallback'>{token}</textarea>
<button class='copy-btn' id='copyBtn' onclick=\"
  var ta = document.getElementById('fallback');
  ta.style.position='fixed'; ta.style.left='0'; ta.style.top='0';
  ta.style.opacity='0'; ta.select(); ta.setSelectionRange(0, 99999);
  var ok = document.execCommand('copy');
  ta.style.position='absolute'; ta.style.left='-9999px';
  if(ok){{
    document.getElementById('copyBtn').textContent = '\u2705 Copied!';
    document.getElementById('copyBtn').style.background = '#34c759';
    setTimeout(function(){{
      document.getElementById('copyBtn').textContent = 'Copy Token';
      document.getElementById('copyBtn').style.background = '#0071e3';
    }}, 2500);
  }} else {{
    document.getElementById('tokenText').click();
    document.getElementById('copyBtn').textContent = 'Press Ctrl+C to copy';
    document.getElementById('copyBtn').style.background = '#ff9500';
  }}
\">Copy Token</button>
<p style='margin-top:15px'>Token is also printed in your terminal. You can safely close this window.</p>
</body></html>"""
                    try:
                        window.load_html(success_html)
                    except Exception:
                        try:
                            window.destroy()
                        except Exception:
                            pass
                else:
                    # Auto-close window for setup flow (token is saved to file)
                    print("  \u2705 Token captured — setup will continue.")
                    def _close():
                        for attempt in range(5):
                            try:
                                window.destroy()
                                return
                            except Exception:
                                time.sleep(0.2 * (attempt + 1))
                    _close()
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
    return result["token"], "", {}


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
    """Patch pywebview's Windows EdgeChrome/WebView2 handler to intercept tesla:// URLs.

    pywebview on Windows uses EdgeChromium (WebView2). The EdgeChrome class connects
    NavigationStarting to self.on_navigation_start. We monkey-patch that method to
    intercept tesla:// URLs before the browser tries to navigate to them.
    """
    try:
        from webview.platforms import edgechromium as chromium_mod
    except ImportError:
        try:
            from webview.platforms import winforms
            chromium_mod = getattr(winforms, 'Chromium', None)
            if chromium_mod is None:
                return
        except ImportError:
            return

    EdgeChrome = getattr(chromium_mod, 'EdgeChrome', None)
    if EdgeChrome is None:
        return

    original_on_navigation_start = EdgeChrome.on_navigation_start

    def patched_on_navigation_start(self, sender, args):
        try:
            uri = str(args.get_Uri())
            if uri and uri.startswith("tesla://"):
                # Cancel the navigation — tesla:// is not a real scheme
                args.set_Cancel(True)

                parsed = urllib.parse.urlparse(uri)
                params = urllib.parse.parse_qs(parsed.query)

                error = params.get("error", [None])[0]
                if error:
                    result["error"] = f"Tesla auth error: {error}"
                    return

                code = params.get("code", [None])[0]
                returned_state = params.get("state", [None])[0]

                if not code:
                    result["error"] = "No auth code in redirect"
                    return

                if returned_state != expected_state:
                    result["error"] = "CSRF state mismatch"
                    return

                result["code"] = code
                return
        except Exception:
            pass

        # Fall through to original handler for non-tesla:// URLs
        original_on_navigation_start(self, sender, args)

    EdgeChrome.on_navigation_start = patched_on_navigation_start


def _patch_pywebview_gtk(result, expected_state):
    """Patch pywebview's Linux WebKit2GTK BrowserView to intercept tesla:// URLs.

    pywebview on Linux uses WebKit2GTK. BrowserView connects the 'decide-policy' signal
    to self.on_navigation. We monkey-patch on_navigation to intercept tesla:// URLs
    before the browser tries to navigate (which would fail since tesla:// is not real).

    The on_navigation signature is: on_navigation(self, webview, decision, decision_type)
    where decision_type is a WebKit2.PolicyDecisionType enum and decision is a
    NavigationPolicyDecision (for NAVIGATION_ACTION) or ResponsePolicyDecision.
    """
    # Check for system-level GTK/WebKit2 dependencies early so we can give
    # a clear error rather than a cryptic ImportError later.
    try:
        import gi  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Missing system libraries required for the Linux login window.\n"
            "Please install them with your package manager and try again:\n\n"
            "  Debian/Ubuntu:  sudo apt install python3-gi gir1.2-webkit2-4.0\n"
            "  Fedora/RHEL:    sudo dnf install python3-gobject webkit2gtk4.0\n"
            "  Arch:           sudo pacman -S python-gobject webkit2gtk\n\n"
            "These are system packages and cannot be installed via pip."
        )

    try:
        from webview.platforms import gtk as gtk_mod
    except ImportError:
        return

    BrowserView = getattr(gtk_mod, 'BrowserView', None)
    if BrowserView is None:
        return

    original_on_navigation = BrowserView.on_navigation

    def patched_on_navigation(self, webview, decision, decision_type):
        try:
            # WebKit2.PolicyDecisionType.NAVIGATION_ACTION = 0
            if decision_type == 0:
                nav_decision = decision
                request = nav_decision.get_request()
                uri = request.get_uri() if request else None

                if uri and uri.startswith("tesla://"):
                    # Ignore the request — tesla:// is not a real scheme
                    nav_decision.ignore()

                    parsed = urllib.parse.urlparse(uri)
                    params = urllib.parse.parse_qs(parsed.query)

                    error = params.get("error", [None])[0]
                    if error:
                        result["error"] = f"Tesla auth error: {error}"
                        return

                    code = params.get("code", [None])[0]
                    returned_state = params.get("state", [None])[0]

                    if not code:
                        result["error"] = "No auth code in redirect"
                        return

                    if returned_state != expected_state:
                        result["error"] = "CSRF state mismatch"
                        return

                    result["code"] = code
                    return
        except Exception:
            pass

        # Fall through to original handler for non-tesla:// URLs
        original_on_navigation(self, webview, decision, decision_type)

    BrowserView.on_navigation = patched_on_navigation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def login(email: str = None, headless: bool = False, region: str = "us", debug: bool = False):
    """Authenticate with Tesla. Returns (refresh_token, email, token_data) tuple."""
    if headless or _detect_mode() == "remote":
        return _remote_login(), "", {}
    return _local_login(email=email, region=region, debug=debug,
                        show_token_page=False)


def get_authtoken(region: str = "us", debug: bool = False) -> str:
    """Get a refresh token for the authtoken CLI command (no file save)."""
    token, _, _ = _local_login(region=region, debug=debug, show_token_page=True)
    return token


def _extract_email_from_token(token: str) -> str:
    """Extract email from a JWT id_token payload."""
    try:
        import base64, json
        parts = token.split('.')
        if len(parts) >= 2:
            # Add padding
            padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
            return (data.get('email') or
                    data.get('data', {}).get('email') or '')
    except Exception:
        pass
    return ''


def save_token(token_data: dict, path: str = None, email: str = None, region: str = "us"):
    """Save token data to the pypowerwall auth file (.pypowerwall.auth).

    Writes in teslapy-compatible format so PyPowerwallCloud can read it.

    Args:
        token_data: Full token response dict from Tesla (contains access_token,
                    refresh_token, expires_in, token_type, id_token).
        path: File path (default: .pypowerwall.auth in current directory).
        email: Email address to associate with the token.
        region: Tesla region for token refresh if access_token is missing.
    """
    import time

    if not path:
        path = os.path.join(os.getcwd(), ".pypowerwall.auth")

    if not email:
        email = input("Tesla account email: ").strip()

    # If access_token is missing, refresh it from the refresh_token
    if not token_data.get("access_token") and token_data.get("refresh_token"):
        try:
            refreshed = _refresh_access_token(token_data["refresh_token"], region=region)
            token_data.update(refreshed)
            print("  Access token refreshed successfully.")
        except Exception as e:
            print(f"  Warning: Could not refresh access token: {e}")

    # Build teslapy-compatible cache entry
    expires_in = token_data.get("expires_in", 28800)
    expires_at = int(time.time() + expires_in)

    sso = {
        "token_type": token_data.get("token_type", "Bearer"),
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at": expires_at,
        "expires_in": expires_in,
    }
    if token_data.get("id_token"):
        sso["id_token"] = token_data["id_token"]

    cache = {}
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    cache[email] = {
        "url": "https://auth.tesla.com/",
        "sso": sso,
    }

    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    with open(path, "w") as f:
        json.dump(cache, f, indent=2)
    os.chmod(path, 0o600)

    print(f"  Token saved to {path}")
    return path
