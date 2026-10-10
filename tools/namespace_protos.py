#!/usr/bin/env python3
"""Stage pypowerwall's .proto sources under their package paths for protoc.

Python protobuf keeps one default descriptor pool per process, keyed by proto
file name and fully-qualified symbol name. Compiled as-is, our modules would
register generic names (tedapi.proto, package tedapi; tesla.proto, package
teslapower; google.rpc.Status) that other libraries in the same process (Home
Assistant integrations, googleapis-common-protos) also register, and the second
import fails with "duplicate file name" / "duplicate symbol" (issue #408).

Each source is copied to <stage>/<target dir>/<name>.proto, so protoc registers
it by its import path (pypowerwall/tedapi/protobuf/V2024_06/tedapi.proto), and
its package is prefixed with that path in dotted form
(pypowerwall.tedapi.protobuf.V2024_06.tedapi): unique by construction, like the
Python module path. Sibling imports are rewritten to the staged paths and
google.protobuf references are fully qualified (a prefixed google.rpc package
would otherwise shadow them). Message encoding is unchanged: fields are
encoded by number, not name. The one place a name reaches the wire is a
google.protobuf.Any, whose type_url carries the packed message's full name, so
packing one of these messages now yields the namespaced URL (pypowerwall packs
none). The checked-in .proto sources are not modified.

Usage: namespace_protos.py <stage-dir> <source.proto>:<target-dir> [...]
"""
import re
import sys
from pathlib import Path

_PACKAGE = re.compile(r'^(\s*package\s+)([\w.]+)(\s*;)', re.MULTILINE)
_IMPORT = re.compile(r'^(\s*import\s+")([^"]+)(";)', re.MULTILINE)
_WELL_KNOWN = re.compile(r'(?<![\w.])google\.protobuf\.')


def stage(stage_dir, mappings):
    sources = {Path(src).name: target for src, target in mappings}
    for src, target in mappings:
        text = Path(src).read_text()
        prefix = target.strip('/').replace('/', '.')
        text, count = _PACKAGE.subn(lambda m: f'{m[1]}{prefix}.{m[2]}{m[3]}', text)
        if count != 1:
            raise SystemExit(f'{src}: expected one package statement, found {count}')
        text = _IMPORT.sub(
            lambda m: f'{m[1]}{sources[m[2]]}/{m[2]}{m[3]}' if m[2] in sources else m[0], text)
        text = _WELL_KNOWN.sub('.google.protobuf.', text)
        out = Path(stage_dir, target, Path(src).name)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)


if __name__ == '__main__':
    stage(sys.argv[1], [arg.split(':', 1) for arg in sys.argv[2:]])
