"""Tesla TLS policy per platform (#350): TLS 1.2 cap on Windows and macOS, where a
TLS 1.3 ClientHello gets the token "tainted" (403 on owner-api), and TLS 1.3 pin on Linux.
The three context builders must agree."""
import ssl
import sys

import pytest

from pypowerwall import tesla_auth
from pypowerwall import v1r_register
from pypowerwall.cloud.teslapy import Tesla

BUILDERS = {
    'tesla_auth._httpx_auth_verify': tesla_auth._httpx_auth_verify,
    'teslapy.Tesla._httpx_auth_verify': Tesla._httpx_auth_verify,
    'v1r_register._ssl_ctx': v1r_register._ssl_ctx,
}


@pytest.mark.parametrize('name', BUILDERS)
@pytest.mark.parametrize('platform, version', [
    ('win32', ssl.TLSVersion.TLSv1_2),
    ('darwin', ssl.TLSVersion.TLSv1_2),
    ('linux', ssl.TLSVersion.TLSv1_3),
])
def test_tls_version_pinned_per_platform(monkeypatch, name, platform, version):
    # A faked sys.platform also reaches ssl.create_default_context() (Windows loads its
    # certificate store), so hand the builders a plain client context instead.
    monkeypatch.setattr(ssl, 'create_default_context', lambda *a, **k: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    monkeypatch.setattr(sys, 'platform', platform)
    ctx = BUILDERS[name]()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.minimum_version == version
    assert ctx.maximum_version == version
