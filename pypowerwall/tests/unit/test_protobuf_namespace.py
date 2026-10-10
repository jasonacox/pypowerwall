"""Protobuf descriptors are registered under pypowerwall's own namespace (issue #408).

Python protobuf keeps one default descriptor pool per process, keyed by proto file
name and fully-qualified symbol name. pypowerwall used to register generic names
(tedapi.proto / package tedapi, tesla.proto / package teslapower, google.rpc.Status)
that other libraries also register - aiopowerwall <= 0.4.1 (Home Assistant's
Teslemetry integration), tesla-protocol < 4, googleapis-common-protos - and the
second import failed with "duplicate file name" / "duplicate symbol".
tools/gen_proto.sh now registers each module under its import path.
"""
import importlib
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import pypowerwall
from pypowerwall.tedapi import TEDAPI

PACKAGE_ROOT = Path(pypowerwall.__file__).parent

# Generated modules (not the re-export shims like pypowerwall/tedapi/tedapi_pb2.py)
GENERATED = sorted(
    p for p in PACKAGE_ROOT.rglob('*_pb2.py')
    if 'AddSerializedFile' in p.read_text() and 'tests' not in p.parts
)


def _module_name(path):
    return '.'.join(path.relative_to(PACKAGE_ROOT.parent).with_suffix('').parts)


def test_generated_modules_found():
    assert len(GENERATED) == 8


@pytest.mark.parametrize('path', GENERATED, ids=lambda p: p.name)
def test_registered_under_import_path(path):
    try:
        module = importlib.import_module(_module_name(path))
    except ImportError:
        pytest.skip('V2026_06 protos require protobuf>=6.33.6')
    rel = path.relative_to(PACKAGE_ROOT.parent)
    prefix = '.'.join(rel.parent.parts)
    assert module.DESCRIPTOR.name == rel.with_name(path.name[:-len('_pb2.py')] + '.proto').as_posix()
    assert module.DESCRIPTOR.package.startswith(prefix + '.')


# Bare names other libraries register in the same process, in the shape they
# collided with: file name and one symbol from each of our former registrations.
BARE_REGISTRATIONS = [
    ('tedapi.proto', 'tedapi', 'ConfigString'),
    ('tedapi_combined.proto', 'tedapi_combined', 'AuthEnvelope'),
    ('tesla.proto', 'teslapower', 'AccumulatedEnergy'),
    ('google/rpc/status.proto', 'google.rpc', 'Status'),
    ('tedapi_v2_common.proto', 'tesla.proto.common.v1', 'UUIDv4'),
    ('tedapi_v2_energy_registration.proto', 'tesla.proto.energy_registration.v1', 'AnonymizedSiteDetails'),
    ('tedapi_v2_energy_device.proto', 'tesla.proto.energy_device.v1', 'AcceptedPackage'),
    ('tedapi_v2_transport.proto', 'tedapi_v2_transport', 'Message'),
]


def test_coexists_with_bare_named_copies():
    # Fresh interpreter: the default pool is process-wide and pypowerwall is
    # already imported here. Register the bare names first, then load everything.
    script = textwrap.dedent(f"""
        from google.protobuf import descriptor_pb2, descriptor_pool
        for name, package, message in {BARE_REGISTRATIONS!r}:
            f = descriptor_pb2.FileDescriptorProto(name=name, package=package, syntax='proto3')
            f.message_type.add(name=message)
            descriptor_pool.Default().AddSerializedFile(f.SerializeToString())
        import pypowerwall
        import pypowerwall.local.tesla_pb2
        from pypowerwall.tedapi import TEDAPI, tedapi_pb2, tedapi_combined_pb2
        try:
            from pypowerwall.tedapi.protobuf.V2026_06 import tedapi_v2_transport_pb2  # noqa: F401
        except Exception as e:  # protobuf < 6.33.6: V2026_06 unavailable, not a clash
            assert 'duplicate' not in str(e), e
        print('ok')
    """)
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                            cwd=PACKAGE_ROOT.parent)
    assert result.returncode == 0 and result.stdout.strip() == 'ok', result.stderr


@pytest.mark.parametrize('version, expected', [
    ('4.25.1', 'requires protobuf>=6.33.6'),
    ('7.36.2', 'failed to load'),
])
def test_v2026_import_error_names_the_real_cause(version, expected, monkeypatch):
    # Only an old runtime gets the upgrade advice; anything else (e.g. a
    # descriptor-pool clash) is reported as itself. Make the transport module
    # fail to import: off the package and None in sys.modules.
    v2026 = importlib.import_module('pypowerwall.tedapi.protobuf.V2026_06')
    monkeypatch.delattr(v2026, 'tedapi_v2_transport_pb2', raising=False)
    monkeypatch.setitem(sys.modules, 'pypowerwall.tedapi.protobuf.V2026_06.tedapi_v2_transport_pb2', None)
    with patch('google.protobuf.__version__', version):
        with pytest.raises(ImportError, match=expected):
            TEDAPI._import_v2026_pb2()
