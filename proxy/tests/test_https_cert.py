"""PW_HTTPS=yes certificate: the bundled default (with a warning) or the user's."""

import logging
import os
import ssl

import pytest

from proxy.server import BUNDLED_CERT, https_certificate

PROXY_DIR = os.path.dirname(BUNDLED_CERT)


def test_bundled_certificate_is_the_default_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        certfile, keyfile = https_certificate()
    assert (certfile, keyfile) == (BUNDLED_CERT, None)
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(certfile, keyfile)
    assert "PW_HTTPS_CERT" in caplog.text


def test_user_certificate_wins_without_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        assert https_certificate("my.crt", "my.key") == ("my.crt", "my.key")
    assert "localhost.pem" not in caplog.text


@pytest.mark.parametrize("pair", [("my.crt", ""), ("", "my.key")])
def test_user_certificate_needs_both_files(pair):
    with pytest.raises(ValueError):
        https_certificate(*pair)


@pytest.mark.parametrize("dockerfile", ["Dockerfile", "Dockerfile.beta"])
def test_docker_images_ship_the_bundled_certificate(dockerfile):
    """Images since v0.15.0 left it out, so PW_HTTPS=yes failed to start."""
    copies = [line for line in open(os.path.join(PROXY_DIR, dockerfile))
              if line.startswith("COPY")]
    assert any("localhost.pem" in line.split() for line in copies)
    ignore = open(os.path.join(PROXY_DIR, ".dockerignore")).read().split()
    assert "!localhost.pem" in ignore[ignore.index("*.pem"):]
