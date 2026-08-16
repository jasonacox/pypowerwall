"""Shared pytest configuration for the pypowerwall test suite.

Blocks real network I/O in every non-live test.

This is not just hygiene. TEDAPI's default host is GW_IP = 192.168.91.1 — a real
Powerwall Gateway on the developer's LAN — and TEDAPI.connect() probes it through
a urllib3 Retry adapter (5 attempts, backoff_factor=1). A test that forgets to
mock the session therefore does not fail fast: it spends ~60s talking to live
hardware and then usually passes anyway, so the mistake never surfaces in CI and
the suite quietly depends on whatever the gateway happened to answer.

Tests that genuinely require hardware are marked `live` (see pytest.ini) and are
exempt; the standard run deselects them with -m "not live".
"""
import socket

import pytest


class NetworkAccessAttempted(BaseException):
    """A non-live test tried to open a real socket.

    Deliberately derived from BaseException, not Exception: the library code
    under test is full of broad `except Exception` handlers that degrade to a
    logged error and a None return (TEDAPI.connect() is the main one). An
    Exception subclass gets swallowed by them, so the offending test still
    passes and the escape goes unnoticed — the connection is blocked but the
    mistake is invisible. BaseException propagates through those handlers and
    fails the test where the mistake actually is.
    """


_DENY_MESSAGE = (
    "This test attempted a real network connection.\n"
    "Unit tests must mock the transport boundary — patch TEDAPI.session (or "
    "TEDAPI._init_session / requests) rather than letting a request escape.\n"
    "Note that TEDAPI defaults to host 192.168.91.1, a real Powerwall Gateway, "
    "so an unmocked call talks to live hardware.\n"
    "If this test truly needs hardware, mark it with @pytest.mark.live."
)


@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    """Fail fast and loudly on any real socket connection."""
    if request.node.get_closest_marker("live"):
        return  # live tests are expected to reach the gateway

    def deny(*args, **kwargs):
        raise NetworkAccessAttempted(_DENY_MESSAGE)

    # connect/connect_ex cover socket use directly and via requests/urllib3;
    # create_connection is the higher-level helper urllib3 actually calls.
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
