"""PW_HTTPS=yes certificate: per install, reused, user certificate wins."""

import os
import stat
import sys

import pytest
from cryptography import x509

from proxy.server import https_certificate


def test_generates_a_private_certificate_once_and_reuses_it(tmp_path):
    directory = str(tmp_path / "tls")
    cert, key = https_certificate(directory=directory)
    if sys.platform != "win32":  # POSIX permission bits
        assert stat.S_IMODE(os.stat(key).st_mode) == 0o600
    first = open(cert, "rb").read()
    sans = x509.load_pem_x509_certificate(first).extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value
    assert "localhost" in sans.get_values_for_type(x509.DNSName)
    assert https_certificate(directory=directory) == (cert, key)
    assert open(cert, "rb").read() == first


def test_each_install_gets_its_own_key(tmp_path):
    _, a = https_certificate(directory=str(tmp_path / "a"))
    _, b = https_certificate(directory=str(tmp_path / "b"))
    assert open(a, "rb").read() != open(b, "rb").read()


def test_generates_without_fchmod(tmp_path, monkeypatch):
    """Windows has no os.fchmod: generation still works."""
    monkeypatch.delattr(os, "fchmod", raising=False)
    cert, key = https_certificate(directory=str(tmp_path / "tls"))
    assert os.path.isfile(cert) and os.path.isfile(key)


def test_user_certificate_wins_and_needs_both_files(tmp_path):
    assert https_certificate("my.crt", "my.key", str(tmp_path)) == ("my.crt", "my.key")
    with pytest.raises(ValueError):
        https_certificate("my.crt", "", str(tmp_path))


def test_the_shared_bundled_key_is_gone():
    assert not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "localhost.pem"))


@pytest.mark.parametrize("damage", ["empty", "truncated", "other_key"])
def test_a_broken_or_mismatched_key_is_regenerated(tmp_path, damage):
    """A still-valid certificate with an unusable key would fail every restart."""
    import ssl
    directory = str(tmp_path / "tls")
    cert, key = https_certificate(directory=directory)
    if damage == "other_key":
        content = open(https_certificate(directory=str(tmp_path / "other"))[1], "rb").read()
    else:
        content = b"" if damage == "empty" else open(key, "rb").read()[:40]
    with open(key, "wb") as f:
        f.write(content)
    https_certificate(directory=directory)
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(cert, key)  # loads again


def test_a_non_ascii_hostname_is_left_out(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "gethostname", lambda: "café")
    cert, _ = https_certificate(directory=str(tmp_path / "tls"))
    sans = x509.load_pem_x509_certificate(open(cert, "rb").read()).extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value
    assert sans.get_values_for_type(x509.DNSName) == ["localhost"]


def test_an_expired_certificate_is_replaced(tmp_path):
    import datetime
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    directory = str(tmp_path / "tls")
    cert, key = https_certificate(directory=directory)
    # Sign with the existing key so expiry is the only reason to replace it
    private = serialization.load_pem_private_key(open(key, "rb").read(), None)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "old")])
    past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    expired = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(private.public_key()).serial_number(1)
               .not_valid_before(past).not_valid_after(past + datetime.timedelta(days=1))
               .sign(private, hashes.SHA256()))
    with open(cert, "wb") as f:
        f.write(expired.public_bytes(serialization.Encoding.PEM))
    https_certificate(directory=directory)
    assert x509.load_pem_x509_certificate(open(cert, "rb").read()).subject != name
