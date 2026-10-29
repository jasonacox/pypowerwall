"""PW_HTTPS=yes certificate: the bundled default (with a warning) or the user's."""

import logging
import os
import ssl

import pytest
from cryptography.hazmat.primitives import serialization

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
        assert https_certificate(BUNDLED_CERT, BUNDLED_CERT) == (BUNDLED_CERT, BUNDLED_CERT)
    assert "localhost.pem" not in caplog.text


def test_an_encrypted_user_key_is_rejected_without_prompting(tmp_path):
    """OpenSSL would wait for a passphrase on the terminal, blocking startup."""
    with open(BUNDLED_CERT, "rb") as f:
        bundled = serialization.load_pem_private_key(f.read(), None)
    key = tmp_path / "encrypted.key"
    key.write_bytes(bundled.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"secret")))
    with pytest.raises(ValueError, match="encrypted"):
        https_certificate(BUNDLED_CERT, str(key))


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
