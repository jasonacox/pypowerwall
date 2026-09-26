"""Unit tests for TEDAPIv1r transport hardening.

Covers:
  1. read/write methods return their failure shape (None/False) when called
     without a DIN instead of raising from the signing/protobuf build;
  2. the retry after a 401/403 re-login is re-signed (fresh expiry and uuid);
  3. write_config_v1r checks the reply type (MessageEnvelope has no 'error'
     field; the old check raised ValueError) and rejects a non-update reply;
  4. get_din handles a gzip-compressed body;
  5. concurrent key-auth failures emit one UserWarning.

The RSA key and HTTP session are mocked — nothing here touches a gateway.
"""
import gzip
import threading
import warnings
from unittest.mock import MagicMock, patch

import pytest

from pypowerwall.tedapi.protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2
from pypowerwall.tedapi.tedapi_v1r import TEDAPIv1r

DIN = "1707000-11-J--TG0123456789AB"


def make_transport():
    with patch.object(TEDAPIv1r, "__init__", lambda self, *a, **kw: None):
        t = TEDAPIv1r.__new__(TEDAPIv1r)
    t.pending_verification = False
    t.key_unknown = False
    t._flag_lock = threading.Lock()
    t.host = "10.42.1.1"
    t.timeout = 5
    t.token = "fake-token"
    t.din = None
    t.rsa_key_path = None
    t.key_fingerprint = "f" * 64
    t._private_key = MagicMock()
    t._private_key.sign.return_value = b"\x00" * 64
    t._public_key_der = b"\x00" * 32
    t.session = MagicMock()
    return t


def response(status=200, inner=b"", content=None):
    r = MagicMock()
    r.status_code = status
    if content is None:
        msg = combined_pb2.RoutableMessage()
        msg.protobuf_message_as_bytes = inner
        content = msg.SerializeToString()
    r.content = content
    return r


def envelope(**filestore):
    env = combined_pb2.MessageEnvelope()
    for field, value in filestore.items():
        getattr(env.filestore, field).CopyFrom(value)
    return env.SerializeToString()


class TestNoDin:

    @pytest.mark.parametrize("din", [None, ""])
    def test_failure_shapes(self, din):
        t = make_transport()
        teg = combined_pb2.TEGMessages()
        assert t.post_v1r(b"env", din) is None
        assert t.get_config_v1r(din) is None
        assert t.write_config_v1r(din, {"a": 1}) is False
        assert t.send_teg_message(din, teg) is None
        t.session.post.assert_not_called()


class TestReloginRetry:

    def test_retry_is_resigned(self):
        t = make_transport()
        t.login = MagicMock(return_value=True)
        t.session.post.side_effect = [response(status=401), response(inner=b"data")]
        clock = MagicMock()
        clock.time.side_effect = [1000.0, 1020.0]   # first signing, retry signing
        with patch("pypowerwall.tedapi.tedapi_v1r.time", clock):
            assert t.post_v1r(b"env", DIN) == b"data"
        first, second = (combined_pb2.RoutableMessage.FromString(c.kwargs["data"])
                         for c in t.session.post.call_args_list)
        assert first.signature_data.rsa_data.expires_at == 1012
        assert second.signature_data.rsa_data.expires_at == 1032
        assert first.uuid != second.uuid
        assert t._private_key.sign.call_count == 2


class TestWriteReply:

    def _write(self, reply_bytes):
        t = make_transport()
        read = combined_pb2.FileStoreAPIReadFileResponse()
        read.file.blob = b'{"site_info": {}}'
        read.hash = b"h"
        t.post_v1r = MagicMock(side_effect=[envelope(readFileResponse=read), reply_bytes])
        return t.write_config_v1r(DIN, {"site_info.backup_reserve_percent": 20})

    def test_update_response_is_success(self):
        assert self._write(envelope(updateFileResponse=combined_pb2.FileStoreAPIUpdateFileResponse())) is True

    def test_other_filestore_reply_is_failure(self):
        assert self._write(envelope(readFileResponse=combined_pb2.FileStoreAPIReadFileResponse())) is False

    def test_non_filestore_reply_is_failure_without_valueerror(self, caplog):
        env = combined_pb2.MessageEnvelope()
        env.teg.SetInParent()
        assert self._write(env.SerializeToString()) is False
        assert "failed to parse write response" not in caplog.text


class TestGetDin:

    @pytest.mark.parametrize("body", [DIN.encode(), gzip.compress(DIN.encode())])
    def test_plain_and_gzip(self, body):
        t = make_transport()
        r = MagicMock()
        r.status_code = 200
        r.content = body + b"\n" if body == DIN.encode() else body
        t.session.get.return_value = r
        assert t.get_din() == DIN


class TestWarningOnce:

    def test_concurrent_failures_warn_once(self):
        t = make_transport()
        barrier = threading.Barrier(8)

        def fail():
            barrier.wait(5)
            t._key_auth_warning("key_unknown", "key not recognized")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            threads = [threading.Thread(target=fail) for _ in range(8)]
            for th in threads:
                th.start()
            for th in threads:
                th.join(5)
        assert len([w for w in caught if issubclass(w.category, UserWarning)]) == 1
        assert t.key_unknown is True
