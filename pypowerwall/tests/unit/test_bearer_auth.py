"""Unit tests for the bearer TEDAPI transport.

Covers the bearer auth-mode code paths, mocked at the transport boundary
(``TEDAPI.session``) so nothing here touches a gateway:

  1. AuthMode.coerce() and its incompatibility guards.
  2. _init_session() auth wiring (HTTP Basic only in basic mode).
  3. _authenv_post() AuthEnvelope wrap/unwrap of bare MessageEnvelope bytes,
     including the gzip, busy-code and malformed-response failure paths.
  4. Bearer 401/403 re-authentication: re-login once and retry, never loop.
  5. The _post_tedapi() bearer route — the Message/Tail wrapper is stripped to
     the bare envelope there (shared with v1r; no AuthEnvelope type-pun of the
     request) — and the _parse_response() / get_config() branches that read a
     bare MessageEnvelope instead of a full Message.

The failure paths matter more than the happy paths here: this transport runs
unattended on other people's Powerwalls, where a silent None is a stalled
dashboard and a mis-parse is silently empty data.

Note the AuthEnvelope always carries externalAuth.type = PRESENCE. That is the
protobuf-level external-auth enum every local client sets (verified against the
Tesla app bundle); it is unrelated to the removed "presence" auth mode.
"""
import gzip
import logging
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi import TEDAPI, tedapi_pb2
from pypowerwall.tedapi.auth_mode import AuthMode
from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2
from pypowerwall.tedapi.queries import QueryRole

try:
    from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_transport_pb2 as _tx  # noqa
    HAVE_V2026 = True
except Exception:
    HAVE_V2026 = False

v2026_only = pytest.mark.skipif(not HAVE_V2026, reason="V2026_06 protos require protobuf>=6.33.6")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tedapi(auth_mode="bearer", **kwargs):
    """Build a TEDAPI in the given auth mode with a mocked session.

    connect() is patched out (it would log in over the network); the session is
    replaced with a MagicMock so tests drive HTTP status/content directly.
    """
    with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="TEST_DIN"):
        api = TEDAPI("testpassword", auth_mode=auth_mode, **kwargs)
    api.din = "1538000-45-D--TESTDIN0000000"
    api.gw_ip = "192.168.91.1"
    api.session = MagicMock()
    return api


def make_message(text="", config_text=""):
    """Serialize a full transport Message (envelope + tail), as basic mode sends."""
    msg = tedapi_pb2.Message()
    msg.message.deliveryChannel = 1
    if text:
        msg.message.payload.recv.text = text
    if config_text:
        msg.message.config.recv.file.text = config_text
    msg.tail.value = 1
    return msg.SerializeToString()


def inner_envelope(message_bytes: bytes) -> bytes:
    """The bare MessageEnvelope (field 1) of a serialized full Message."""
    return tedapi_pb2.Message.FromString(message_bytes).message.SerializeToString()


def make_envelope(text="", config_text=""):
    """Serialize a bare MessageEnvelope, as the bearer transport returns."""
    env = tedapi_pb2.MessageEnvelope()
    if text:
        env.payload.recv.text = text
    if config_text:
        env.config.recv.file.text = config_text
    return env.SerializeToString()


def auth_wrapped(payload: bytes) -> bytes:
    """Wrap payload bytes in an AuthEnvelope, as the gateway answers."""
    auth = combined_pb2.AuthEnvelope()
    auth.payload = payload
    auth.externalAuth.type = combined_pb2.EXTERNAL_AUTH_TYPE_PRESENCE
    return auth.SerializeToString()


def mock_response(content=b"", status_code=HTTPStatus.OK):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


def posted_auth_envelope(session_mock, call_index=0):
    """Parse the AuthEnvelope actually POSTed on the given session.post call."""
    _, kwargs = session_mock.post.call_args_list[call_index]
    sent = combined_pb2.AuthEnvelope()
    sent.ParseFromString(kwargs["data"])
    return sent


# ---------------------------------------------------------------------------
# AuthMode coercion and mode guards
# ---------------------------------------------------------------------------

class TestAuthMode:
    """AuthMode.coerce() must fail loudly — a silent fallback changes transport."""

    @pytest.mark.parametrize("value,expected", [
        ("basic", AuthMode.BASIC),
        ("bearer", AuthMode.BEARER),
        ("BEARER", AuthMode.BEARER),       # case-insensitive (CLI args)
        ("Bearer", AuthMode.BEARER),
        (AuthMode.BASIC, AuthMode.BASIC),  # enum passthrough
    ])
    def test_coerce_accepts(self, value, expected):
        assert AuthMode.coerce(value) is expected

    @pytest.mark.parametrize("value", ["", "bear", "none", "Basic ", None, 0])
    def test_coerce_rejects_unknown(self, value):
        """Unknown auth mode must raise, never fall back to a different transport."""
        with pytest.raises(ValueError, match="Invalid auth_mode"):
            AuthMode.coerce(value)

    @pytest.mark.parametrize("value", ["", "bear", "presence", "  bearer", None, 0])
    def test_coerce_default_falls_back(self, value):
        """With default= (env-var callers), an unknown value must warn and fall
        back instead of raising — a container env typo must not be fatal."""
        assert AuthMode.coerce(value, default=AuthMode.BASIC) is AuthMode.BASIC

    def test_coerce_default_does_not_mask_valid_values(self):
        assert AuthMode.coerce("bearer", default=AuthMode.BASIC) is AuthMode.BEARER

    def test_coerce_default_warns_with_value_and_choices(self, caplog):
        """The warning must name the offending value and the valid choices."""
        with caplog.at_level(logging.WARNING, logger="pypowerwall.tedapi.auth_mode"):
            AuthMode.coerce("bear", default=AuthMode.BASIC)
        assert "'bear'" in caplog.text
        assert "'basic'" in caplog.text
        assert "'bearer'" in caplog.text

    def test_presence_mode_is_gone(self):
        """'presence' was a Gateway 1 switch-flip flow (api/auth/toggle/*) that
        PW3 gateways answer with 404. It was removed, so it must now be rejected
        rather than silently accepted as some other transport."""
        with pytest.raises(ValueError, match="Invalid auth_mode"):
            AuthMode.coerce("presence")
        assert not hasattr(AuthMode, "PRESENCE")
        assert [m.value for m in AuthMode] == ["basic", "bearer"]

    def test_str_enum_interop(self):
        """Members compare equal to plain strings and render as the bare value."""
        assert AuthMode.BEARER == "bearer"
        assert str(AuthMode.BASIC) == "basic"
        assert f"{AuthMode.BEARER}" == "bearer"

    def test_default_mode_is_basic(self):
        api = make_tedapi(auth_mode="basic")
        assert api.auth_mode is AuthMode.BASIC

    def test_v1r_incompatible(self):
        """v1r has its own RSA transport — pairing it with bearer must fail."""
        with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="X"):
            with pytest.raises(ValueError, match="incompatible with v1r"):
                TEDAPI("pw", auth_mode="bearer", v1r=True)

    def test_invalid_mode_raises_from_constructor(self):
        with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="X"):
            with pytest.raises(ValueError, match="Invalid auth_mode"):
                TEDAPI("pw", auth_mode="nonsense")


class TestSessionInit:
    """_init_session() wires HTTP Basic auth for basic mode only."""

    def test_basic_mode_sets_http_auth(self):
        api = make_tedapi(auth_mode="basic")
        session = api._init_session()
        assert session.auth == ("Tesla_Energy_Device", "testpassword")

    def test_bearer_leaves_http_auth_unset(self):
        """Bearer uses an Authorization header, not HTTP Basic; sending Basic
        anyway can make the gateway reject the call."""
        api = make_tedapi("bearer")
        session = api._init_session()
        assert session.auth is None

    @pytest.mark.parametrize("mode", ["basic", "bearer"])
    def test_content_type_is_octet_stream(self, mode):
        """Corrected from the non-existent 'application/octet-string' MIME type."""
        api = make_tedapi(auth_mode=mode)
        assert api._init_session().headers["Content-type"] == "application/octet-stream"


# ---------------------------------------------------------------------------
# _authenv_post() — AuthEnvelope wrap / unwrap
# ---------------------------------------------------------------------------

class TestAuthEnvPostWrap:
    """The request side: _authenv_post() wraps the bare MessageEnvelope bytes it
    is handed, verbatim. Stripping the Message/Tail wrapper is _post_tedapi's
    job (TestPostTedapiRouting) — not a re-parse of the request here."""

    def test_wraps_envelope_bytes_verbatim(self):
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))
        envelope = make_envelope(text="hello")

        api._authenv_post(envelope)

        assert posted_auth_envelope(api.session).payload == envelope

    def test_external_auth_type_is_presence(self):
        """The protobuf external-auth enum every local client sets — verified
        against the Tesla app bundle, and unrelated to the removed auth mode."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))

        api._authenv_post(make_envelope(text="x"))

        assert posted_auth_envelope(api.session).externalAuth.type == \
            combined_pb2.EXTERNAL_AUTH_TYPE_PRESENCE

    def test_unparseable_input_is_wrapped_verbatim(self):
        """Garbage in must not raise out of the transport — wrap and let the
        gateway reject it."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))
        junk = b"\xff\xff\xff\xff not protobuf"

        api._authenv_post(junk)

        assert posted_auth_envelope(api.session).payload == junk

    def test_posts_to_url_suffix(self):
        """Follower queries route to /tedapi/device/{din}/v1."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))

        api._authenv_post(make_envelope(text="x"), url_suffix="/tedapi/device/DIN123/v1")

        args, kwargs = api.session.post.call_args
        assert args[0] == "https://192.168.91.1/tedapi/device/DIN123/v1"
        assert kwargs["timeout"] == api.timeout


class TestAuthEnvPostUnwrap:
    """The response side: AuthEnvelope unwrap, decompression, and error paths."""

    def test_unwraps_to_bare_envelope_bytes(self):
        api = make_tedapi("bearer")
        envelope = make_envelope(text='{"ok":true}')
        api.session.post.return_value = mock_response(auth_wrapped(envelope))

        assert api._authenv_post(make_envelope(text="x")) == envelope

    def test_gzip_response_is_decompressed(self):
        """Firmware 25.42.2+ gzips TEDAPI responses."""
        api = make_tedapi("bearer")
        envelope = make_envelope(text='{"gz":1}')
        api.session.post.return_value = mock_response(gzip.compress(auth_wrapped(envelope)))

        assert api._authenv_post(make_envelope(text="x")) == envelope

    def test_busy_code_activates_cooldown(self, caplog):
        """429/503 must trip the 5-minute cooldown, not just return None."""
        api = make_tedapi("bearer")
        api.pwcooldown = 0
        api.session.post.return_value = mock_response(b"", HTTPStatus.TOO_MANY_REQUESTS)

        with caplog.at_level(logging.ERROR):
            assert api._authenv_post(make_envelope(text="x")) is None

        assert api.pwcooldown > 0, "rate limit must activate cooldown"
        assert "cooldown" in caplog.text.lower()

    def test_service_unavailable_activates_cooldown(self):
        api = make_tedapi("bearer")
        api.pwcooldown = 0
        api.session.post.return_value = mock_response(b"", HTTPStatus.SERVICE_UNAVAILABLE)

        assert api._authenv_post(make_envelope(text="x")) is None
        assert api.pwcooldown > 0

    @pytest.mark.parametrize("status", [HTTPStatus.INTERNAL_SERVER_ERROR,
                                        HTTPStatus.NOT_FOUND,
                                        HTTPStatus.BAD_REQUEST])
    def test_error_status_returns_none(self, status, caplog):
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(b"", status)

        with caplog.at_level(logging.ERROR):
            assert api._authenv_post(make_envelope(text="x")) is None

        assert str(int(status)) in caplog.text

    def test_malformed_response_returns_none(self, caplog):
        """A response that is not an AuthEnvelope must return None, not raise —
        callers contractually get None on error."""
        api = make_tedapi("bearer")
        # wire-type 4 (end-group) is invalid at top level -> DecodeError
        api.session.post.return_value = mock_response(b"\x0c\xff\xff\xff")

        with caplog.at_level(logging.ERROR):
            assert api._authenv_post(make_envelope(text="x")) is None

        assert "unwrapping" in caplog.text.lower()

    def test_empty_response_yields_empty_payload(self):
        """An empty body parses as an empty AuthEnvelope; the empty payload is
        handed back for the parse layer to reject."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(b"")

        assert api._authenv_post(make_envelope(text="x")) == b""


# ---------------------------------------------------------------------------
# Bearer 401/403 re-authentication
# ---------------------------------------------------------------------------

class TestBearerReAuth:
    """Bearer tokens expire; the transport re-logs-in once and retries."""

    @pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN])
    def test_reauth_and_retry_succeeds(self, status):
        api = make_tedapi("bearer")
        envelope = make_envelope(text='{"after":"retry"}')
        api.session.post.side_effect = [
            mock_response(b"", status),
            mock_response(auth_wrapped(envelope)),
        ]

        with patch.object(api, "_bearer_login") as login:
            assert api._authenv_post(make_envelope(text="x")) == envelope

        assert login.call_count == 1, "expired token must trigger exactly one re-login"
        assert api.session.post.call_count == 2, "request must be retried after re-login"

    def test_retry_sends_identical_payload(self):
        """The retry must resend the same query, not a re-wrapped or empty one."""
        api = make_tedapi("bearer")
        api.session.post.side_effect = [
            mock_response(b"", HTTPStatus.UNAUTHORIZED),
            mock_response(auth_wrapped(make_envelope(text="{}"))),
        ]

        with patch.object(api, "_bearer_login"):
            api._authenv_post(make_envelope(text="x"))

        first = api.session.post.call_args_list[0][1]["data"]
        second = api.session.post.call_args_list[1][1]["data"]
        assert first == second

    def test_reauth_failure_returns_none(self, caplog):
        """If re-login itself fails, return None rather than propagating."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(b"", HTTPStatus.UNAUTHORIZED)

        with patch.object(api, "_bearer_login", side_effect=RuntimeError("gateway down")):
            with caplog.at_level(logging.ERROR):
                assert api._authenv_post(make_envelope(text="x")) is None

        assert "re-authentication failed" in caplog.text.lower()
        assert "gateway down" in caplog.text

    def test_retry_does_not_loop(self):
        """A second 401 after re-login must give up — no infinite re-auth loop."""
        api = make_tedapi("bearer")
        api.session.post.side_effect = [
            mock_response(b"", HTTPStatus.UNAUTHORIZED),
            mock_response(b"", HTTPStatus.UNAUTHORIZED),
        ]

        with patch.object(api, "_bearer_login") as login:
            assert api._authenv_post(make_envelope(text="x")) is None

        assert login.call_count == 1
        assert api.session.post.call_count == 2

    def test_busy_after_reauth_activates_cooldown(self):
        """The post-retry response still runs the busy/status checks."""
        api = make_tedapi("bearer")
        api.pwcooldown = 0
        api.session.post.side_effect = [
            mock_response(b"", HTTPStatus.UNAUTHORIZED),
            mock_response(b"", HTTPStatus.TOO_MANY_REQUESTS),
        ]

        with patch.object(api, "_bearer_login"):
            assert api._authenv_post(make_envelope(text="x")) is None

        assert api.pwcooldown > 0


class TestBearerLogin:
    """_bearer_login()/_bearer_logout() token handling."""

    def test_login_stores_token_and_header(self):
        api = make_tedapi("bearer")
        api.session.headers = {}
        api.session.post.return_value = MagicMock(
            status_code=200, json=lambda: {"token": "TOKEN123"})

        api._bearer_login()

        assert api.token == "TOKEN123"
        assert api.session.headers["Authorization"] == "Bearer TOKEN123"

    def test_login_posts_installer_credentials(self):
        api = make_tedapi("bearer", timezone="Europe/Berlin")
        api.session.headers = {}
        api.session.post.return_value = MagicMock(
            status_code=200, json=lambda: {"token": "T"})

        api._bearer_login()

        args, kwargs = api.session.post.call_args
        assert args[0] == "https://192.168.91.1/api/login/Basic"
        assert kwargs["json"]["username"] == "installer"
        assert kwargs["json"]["password"] == "testpassword"
        assert kwargs["json"]["clientInfo"]["timezone"] == "Europe/Berlin"

    def test_login_without_token_raises(self):
        """A 200 with no token field is a protocol error, not a usable session."""
        api = make_tedapi("bearer")
        api.session.headers = {}
        api.session.post.return_value = MagicMock(
            status_code=200, json=lambda: {"error": "bad password"})

        with pytest.raises(ValueError, match="missing 'token'"):
            api._bearer_login()
        assert api.token is None

    def test_logout_clears_token_and_header(self):
        api = make_tedapi("bearer")
        api.session.headers = {"Authorization": "Bearer T"}
        api.token = "T"

        api._bearer_logout()

        assert api.token is None
        assert "Authorization" not in api.session.headers

    def test_logout_is_noop_without_token(self):
        api = make_tedapi("bearer")
        api.token = None

        api._bearer_logout()

        api.session.get.assert_not_called()

    def test_logout_survives_network_error(self):
        """Best-effort: a failed logout must not raise into shutdown paths."""
        api = make_tedapi("bearer")
        api.session.headers = {"Authorization": "Bearer T"}
        api.token = "T"
        api.session.get.side_effect = OSError("connection reset")

        api._bearer_logout()

        assert api.token is None


class TestBearerConnect:
    """connect() in bearer mode logs in instead of probing the web portal."""

    def test_logs_in_before_din(self):
        with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="X"):
            api = TEDAPI("pw", auth_mode="bearer")

        with patch.object(TEDAPI, "_bearer_login") as login, \
                patch.object(TEDAPI, "get_din", return_value="TEST_DIN") as get_din:
            din = api.connect(force=True)

        assert din == "TEST_DIN"
        login.assert_called_once()
        get_din.assert_called_once()

    def test_failure_returns_none(self, caplog):
        """Login failure must return None (documented failure shape), not raise."""
        with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="X"):
            api = TEDAPI("pw", auth_mode="bearer")

        with patch.object(TEDAPI, "_bearer_login", side_effect=OSError("no route")):
            with caplog.at_level(logging.ERROR):
                assert api.connect(force=True) is None

        assert "gateway password" in caplog.text, \
            "bearer mode must not advise adding a 192.168.91.1 route"


# ---------------------------------------------------------------------------
# Parse / routing branches
# ---------------------------------------------------------------------------

class TestParseResponseBranches:
    """Bearer hands _parse_response a bare MessageEnvelope. Parsing it as a full
    Message does not raise — protobuf decodes leniently and yields silently
    empty data — so this branch needs real assertions."""

    def test_query_text_from_bare_envelope(self):
        api = make_tedapi("bearer")
        assert api._parse_response(make_envelope(text='{"q":1}')) == '{"q":1}'

    def test_config_text_from_bare_envelope(self):
        api = make_tedapi("bearer")
        parsed = api._parse_response(make_envelope(config_text='{"c":2}'), config=True)
        assert parsed == '{"c":2}'

    def test_basic_mode_still_parses_full_message(self):
        """Regression guard: the default transport must be untouched."""
        api = make_tedapi("basic")
        assert api._parse_response(make_message(text='{"q":1}')) == '{"q":1}'
        assert api._parse_response(make_message(config_text='{"c":2}'), config=True) == '{"c":2}'

    def test_bearer_misparse_would_be_caught(self):
        """Sanity check on the above: a bare envelope read as a full Message
        returns empty, which is exactly the silent failure this branch fixes."""
        api = make_tedapi("basic")
        assert api._parse_response(make_envelope(text='{"q":1}')) == ""


class TestPostTedapiRouting:
    """_post_tedapi() must route bearer through _authenv_post(), handing it the
    bare MessageEnvelope. The Message/Tail strip lives here — the same
    _envelope_bytes the v1r LAN path uses — not in a re-parse of the request
    as an AuthEnvelope inside _authenv_post()."""

    def test_routes_through_authenv_post(self):
        api = make_tedapi("bearer")
        request = make_message(text="x")
        with patch.object(api, "_authenv_post", return_value=b"envelope") as authenv:
            assert api._post_tedapi(request, url_suffix="/tedapi/v1") == b"envelope"
        authenv.assert_called_once_with(inner_envelope(request), url_suffix="/tedapi/v1")

    def test_strips_tail_before_wrapping(self):
        """A full Message must be reduced to its field-1 envelope before the
        AuthEnvelope wrap; forwarding the Message (with tail) would nest a
        wrapper the gateway does not expect."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))
        request = make_message(text="x")

        api._post_tedapi(request)

        sent = posted_auth_envelope(api.session)
        assert sent.payload == inner_envelope(request), \
            "AuthEnvelope must carry the bare MessageEnvelope"
        assert b"\x10\x01" not in sent.payload[-2:], "tail must not be forwarded"

    def test_bare_envelope_passes_through(self):
        """Input that is already a bare envelope has no field-1 Message to
        extract. protobuf parses it as an *empty* Message without raising, so
        an unguarded extract would send b"" — it must go out unchanged."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))
        bare = make_envelope(text="hello")

        api._post_tedapi(bare)

        assert posted_auth_envelope(api.session).payload == bare

    def test_unparseable_input_passes_through(self):
        """Garbage in must not raise out of the transport — wrap and let the
        gateway reject it."""
        api = make_tedapi("bearer")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))
        junk = b"\xff\xff\xff\xff not protobuf"

        api._post_tedapi(junk)

        assert posted_auth_envelope(api.session).payload == junk

    @v2026_only
    def test_v2026_signed_request_survives_strip(self):
        """The strip must parse with the transport proto matching
        tedapi_api_version: a V2026_06 signed-GraphQL request carries its
        payload in envelope field 16, which the legacy proto reinterprets as a
        QueryType and corrupts on the re-serialize."""
        api = make_tedapi("bearer", tedapi_api_version="V2026_06")
        api.session.post.return_value = mock_response(auth_wrapped(make_envelope("{}")))
        request = api._build_request(QueryRole.DEVICE_CONTROLLER_BASIC)

        api._post_tedapi(request)

        expected = _tx.Message.FromString(request).message.SerializeToString()
        assert posted_auth_envelope(api.session).payload == expected

    def test_follower_suffix_is_forwarded(self):
        """Multi-inverter follower queries must keep their per-DIN URL."""
        api = make_tedapi("bearer")
        with patch.object(api, "_authenv_post", return_value=b"x") as authenv:
            api._post_tedapi(make_message(text="x"), din="DIN9",
                             url_suffix="/tedapi/device/DIN9/v1")
        assert authenv.call_args[1]["url_suffix"] == "/tedapi/device/DIN9/v1"

    def test_basic_mode_does_not_use_authenv(self):
        api = make_tedapi("basic")
        api.session.post.return_value = mock_response(make_message(text="{}"))
        with patch.object(api, "_authenv_post") as authenv:
            api._post_tedapi(b"payload")
        authenv.assert_not_called()


class TestConfigFetchBranch:
    """get_config() rides the shared transport: _post_tedapi() for the fetch and
    the shared legacy parser for the response — no inline bearer branch."""

    def _prime(self, api):
        # bypass cache/cooldown so the fetch actually runs
        api.pwcachetime = {}
        api.pwcache = {}
        api.pwcooldown = 0
        api.pw3 = False

    def test_config_read_from_bare_envelope(self):
        api = make_tedapi("bearer")
        self._prime(api)
        envelope = make_envelope(config_text='{"vin":"GW--TEST"}')

        with patch.object(api, "_authenv_post", return_value=envelope) as authenv:
            config = api.get_config(force=True)

        assert config["vin"] == "GW--TEST"
        # get_config() normalizes the shape callers depend on
        assert config["battery_blocks"] == []
        # ...and reached the transport through _post_tedapi: what _authenv_post
        # got is the bare config.send envelope, tail already stripped
        sent = tedapi_pb2.MessageEnvelope.FromString(authenv.call_args[0][0])
        assert sent.config.send.file == "config.json"
        assert sent.recipient.din == api.din

    def test_config_returns_none_on_transport_error(self):
        """_authenv_post None (401/busy/malformed) must surface as None."""
        api = make_tedapi("bearer")
        self._prime(api)

        with patch.object(api, "_authenv_post", return_value=None):
            assert api.get_config(force=True) is None

    def test_bearer_v2026_config_is_parsed_as_legacy(self):
        """Bearer mode requires V2026_06, but config.json is still fetched with
        the legacy config.send protobuf on every api version. Routing the parse
        through _parse_response's version dispatch would hand the response to
        the signed-GraphQL parser and read back nothing — get_config must
        bypass it (_parse_legacy_response)."""
        api = make_tedapi("bearer", tedapi_api_version="V2026_06")
        self._prime(api)
        envelope = make_envelope(config_text='{"vin":"GW--V2026"}')

        with patch.object(api, "_post_tedapi", return_value=envelope):
            config = api.get_config(force=True)

        assert config["vin"] == "GW--V2026"

    @v2026_only
    def test_bearer_v2026_config_round_trip(self):
        """End to end at the session boundary under V2026_06: the config.send
        request survives the version-matched wrapper strip (envelope field 15
        parses as filestore.readFileRequest — same wire shape) and the response
        is read as a legacy envelope."""
        api = make_tedapi("bearer", tedapi_api_version="V2026_06")
        self._prime(api)
        api.session.post.return_value = mock_response(
            auth_wrapped(make_envelope(config_text='{"vin":"GW--RT"}')))

        config = api.get_config(force=True)

        assert config["vin"] == "GW--RT"
        sent = tedapi_pb2.MessageEnvelope.FromString(
            posted_auth_envelope(api.session).payload)
        assert sent.config.send.file == "config.json"

    def test_v1r_wifi_fallback_reads_full_message(self):
        """v1r with LAN down fetches config.json over the WiFi TEDAPI fallback,
        which answers with a full Message (tail). The shared legacy parser must
        be told so (from_wifi) or it would misparse the wrapper as an envelope
        and yield an empty config."""
        api = make_tedapi("basic")
        self._prime(api)
        api.v1r = True
        api.lan_failed = True
        api.wifi_session = object()   # truthy; _post_tedapi_wifi is patched
        with patch.object(api, "_post_tedapi_wifi",
                          return_value=make_message(config_text='{"vin":"GW--WIFI"}')) as wifi:
            config = api.get_config(force=True)

        assert config["vin"] == "GW--WIFI"
        assert config["battery_blocks"] == []
        sent = tedapi_pb2.Message.FromString(wifi.call_args[0][0])
        assert sent.message.config.send.file == "config.json"

    # --- default (basic) path ------------------------------------------------
    # get_config() shares _post_tedapi's basic branch now (busy -> cooldown,
    # non-200 -> None, gzip). Pin the default transport's behavior explicitly so
    # the reroute can't quietly change it.

    def test_basic_config_still_reads_full_message(self):
        api = make_tedapi("basic")
        self._prime(api)
        api.session.post.return_value = mock_response(
            make_message(config_text='{"vin":"GW--BASIC"}'))

        config = api.get_config(force=True)

        assert config["vin"] == "GW--BASIC"
        assert config["battery_blocks"] == []

    def test_basic_config_busy_activates_cooldown(self):
        api = make_tedapi("basic")
        self._prime(api)
        api.session.post.return_value = mock_response(b"", HTTPStatus.TOO_MANY_REQUESTS)

        assert api.get_config(force=True) is None
        assert api.pwcooldown > 0

    def test_basic_config_error_status_returns_none(self):
        api = make_tedapi("basic")
        self._prime(api)
        api.session.post.return_value = mock_response(
            b"", HTTPStatus.INTERNAL_SERVER_ERROR)

        assert api.get_config(force=True) is None

    def test_basic_config_gzip_is_decompressed(self):
        api = make_tedapi("basic")
        self._prime(api)
        api.session.post.return_value = mock_response(
            gzip.compress(make_message(config_text='{"vin":"GW--GZ"}')))

        assert api.get_config(force=True)["vin"] == "GW--GZ"

    def test_basic_config_bad_json_is_none(self):
        """Malformed JSON returns None (cache left alone), never an exception."""
        api = make_tedapi("basic")
        self._prime(api)
        api.session.post.return_value = mock_response(
            make_message(config_text="{not json"))

        assert api.get_config(force=True) is None


class TestDefensivePaths:
    """Failure shapes the library documents and callers depend on."""

    def test_failed_connect_is_logged_not_raised(self, caplog):
        """A failed connect leaves a constructed object (din=None) per the
        library's documented failure shape — construction must not raise."""
        with caplog.at_level(logging.ERROR):
            with patch("pypowerwall.tedapi.TEDAPI.connect", return_value=None):
                api = TEDAPI("pw", auth_mode="bearer")

        assert api.din is None
        assert "Failed to connect to Powerwall Gateway" in caplog.text

    def test_basic_connect_failure_advises_route(self, caplog):
        """Basic mode needs a static route; its guidance must stay mode-specific."""
        with patch("pypowerwall.tedapi.TEDAPI.connect", return_value="X"):
            api = TEDAPI("pw", auth_mode="basic")

        # _init_session must be mocked too: basic mode probes the web portal on
        # GET / before get_din(), which would otherwise be a real network call.
        with patch.object(TEDAPI, "_init_session", return_value=MagicMock()), \
                patch.object(TEDAPI, "get_din", side_effect=OSError("unreachable")):
            with caplog.at_level(logging.ERROR):
                assert api.connect(force=True) is None

        assert "route to the Gateway" in caplog.text

    def test_wifi_session_content_type(self):
        """The v1r WiFi session got the same octet-stream MIME correction."""
        api = make_tedapi("basic")
        api.wifi_host = "10.0.0.9"

        api._init_wifi_session("gwpassword")

        assert api.wifi_session.headers["Content-type"] == "application/octet-stream"
        assert api.wifi_session.auth == ("Tesla_Energy_Device", "gwpassword")
