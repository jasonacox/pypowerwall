#!/bin/bash
# gen_proto.sh - Regenerate Python protobuf files from .proto source definitions
#
# WHY THIS EXISTS:
#   pypowerwall communicates with the Powerwall Gateway using Protocol Buffers
#   (protobuf). The message formats are defined in human-readable .proto files.
#   The corresponding *_pb2.py files are auto-generated Python bindings that the
#   code actually imports at runtime. These generated files must be kept in sync
#   with their .proto sources.
#
# WHEN TO RUN:
#   Run this script any time a .proto file is modified. It is also invoked
#   automatically by the pre-commit hook (.pre-commit-config.yaml) whenever a
#   .proto file is staged for commit, and by the GitHub Actions workflow
#   (.github/workflows/check-protobuf.yml) to verify the committed pb2 files
#   are up to date with their sources.
#
# DUAL TOOLCHAIN (the runtime protobuf floor stays at >=4.25.1):
#   The library runtime floor is protobuf>=4.25.1. To keep the default path on
#   that floor while letting the opt-in V2026_06 query set use the latest protoc,
#   two generator toolchains are used, each producing a different pb2 subset:
#     * LEGACY  (tesla.proto, V2024_06/*.proto): grpcio-tools 1.62.x / protobuf
#       4.25.x. protobuf 4.25.x does NOT embed ValidateProtobufRuntimeVersion, so
#       this gencode runs on any protobuf>=4.25.1 runtime. This is the floor that
#       requirements.txt / setup.py pin. (tools/requirements-tools.txt; grpcio-
#       tools 1.62.x has no wheels for Python 3.13+, so LEGACY_PY must be <=3.12.)
#     * V2026_06 (tedapi_v2_*.proto): grpcio-tools 1.81.x / protobuf 6.33.x. This
#       gencode embeds the runtime-version guard and requires protobuf>=6.33.6,
#       but the modules are imported lazily and only when a caller opts into
#       tedapi_api_version="V2026_06" (see TEDAPI._import_v2026_pb2), so the
#       default path is unaffected. (tools/requirements-tools-v2.txt; any Py 3.9+.)
#   DO NOT raise the protobuf floor in requirements.txt / setup.py to match the
#   V2026_06 toolchain — the whole point is that the floor stays at 4.25.1.
#
# USAGE:
#   bash tools/gen_proto.sh
#   Provisions two throwaway venvs (.gen-legacy, .gen-v2; git-ignored) and uses
#   each for its proto subset. Override the interpreters with LEGACY_PY (default
#   python3.12) and V2_PY (default python3), or point at pre-made venvs with
#   LEGACY_VENV / V2_VENV.
#
# PROTO → PB2 MAPPINGS:
#   tesla.proto                              → pypowerwall/local/tesla_pb2.py        [LEGACY]
#   pypowerwall/tedapi/protobuf/V2024_06/tedapi.proto          → tedapi_pb2.py       [LEGACY]
#   pypowerwall/tedapi/protobuf/V2024_06/tedapi_combined.proto → tedapi_combined_pb2.py [LEGACY]
#   pypowerwall/tedapi/protobuf/V2026_06/tedapi_v2_*.proto     → ..._pb2.py          [V2026_06]
#
# The bundle's TEDAPI schema spans several protobuf
# packages, so it is emitted as one file per package (energy_device.v1,
# energy_registration.v1, common.v1, google.rpc), referencing google.protobuf
# well-knowns via protoc's built-in imports. Regenerate the source .proto set
# from a bundle with: bash tools/tedapi_v2_extractor/regen.sh <bundle-path>

set -e
cd "$(git rev-parse --show-toplevel)"

LEGACY_PY="${LEGACY_PY:-python3.12}"   # grpcio-tools 1.62.x wheels: Python <=3.12
V2_PY="${V2_PY:-python3}"              # grpcio-tools 1.81.x wheels: any Python 3.9+
LEGACY_VENV="${LEGACY_VENV:-.gen-legacy}"
V2_VENV="${V2_VENV:-.gen-v2}"

provision() {  # <venv-dir> <python> <requirements-file>
    if [ ! -x "$1/bin/python" ]; then
        echo "gen_proto: provisioning $1 ($2, $3)"
        "$2" -m venv "$1"
        "$1/bin/pip" install -q --upgrade pip
        "$1/bin/pip" install -q -r "$3"
    fi
}
provision "$LEGACY_VENV" "$LEGACY_PY" tools/requirements-tools.txt
provision "$V2_VENV"     "$V2_PY"     tools/requirements-tools-v2.txt

# --- LEGACY toolchain: guard-free, protobuf 4.25 (runs on protobuf>=4.25.1) ---
"$LEGACY_VENV/bin/python" -m grpc_tools.protoc -I. --python_out=pypowerwall/local tesla.proto
PROTO_V1_DIR=pypowerwall/tedapi/protobuf/V2024_06
"$LEGACY_VENV/bin/python" -m grpc_tools.protoc -I "$PROTO_V1_DIR" --python_out="$PROTO_V1_DIR" "$PROTO_V1_DIR"/tedapi.proto
"$LEGACY_VENV/bin/python" -m grpc_tools.protoc -I "$PROTO_V1_DIR" --python_out="$PROTO_V1_DIR" "$PROTO_V1_DIR"/tedapi_combined.proto

# --- V2026_06 toolchain: latest protoc, guarded (protobuf>=6.33.6, opt-in only) ---
PROTO_V2_DIR=pypowerwall/tedapi/protobuf/V2026_06
"$V2_VENV/bin/python" -m grpc_tools.protoc -I "$PROTO_V2_DIR" --python_out="$PROTO_V2_DIR" "$PROTO_V2_DIR"/tedapi_v2_*.proto
# protoc emits bare cross-imports (`import tedapi_v2_x_pb2`); rewrite to package-
# relative (`from . import tedapi_v2_x_pb2`) so the dir works as a Python package.
# Deterministic, so committed output == script output (CI git-diff stays clean).
sed -i -E 's/^import (tedapi_v2_[a-z_]+_pb2) as /from . import \1 as /' "$PROTO_V2_DIR"/tedapi_v2_*_pb2.py
# Ensure the package marker exists.
[ -f "$PROTO_V2_DIR/__init__.py" ] || printf '"""TEDAPI v2 energy_device protobufs (Tesla One, June 2026 query set)."""\n' > "$PROTO_V2_DIR/__init__.py"
