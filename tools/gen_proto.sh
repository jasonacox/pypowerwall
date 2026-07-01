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
# PREREQUISITES:
#   pip install -r tools/requirements-tools.txt
#
# IMPORTANT - VERSION PINNING:
#   tools/requirements-tools.txt pins the generator to grpcio-tools 1.81.x /
#   protobuf 6.33.x. The generated pb2 files embed a runtime version check
#   ("Protobuf Python Version: 6.33.5") and therefore require protobuf>=6.33.5
#   at runtime. requirements.txt and setup.py pin protobuf>=6.33.6 to match.
#   If you upgrade tools/requirements-tools.txt you MUST also update the
#   protobuf floor in requirements.txt and setup.py to stay aligned.
#
# USAGE:
#   bash tools/gen_proto.sh
#
# PROTO → PB2 MAPPINGS:
#   tesla.proto                              → pypowerwall/local/tesla_pb2.py
#   pypowerwall/tedapi/protobuf/june_2024/tedapi.proto          → tedapi_pb2.py (same dir)
#   pypowerwall/tedapi/protobuf/june_2024/tedapi_combined.proto → tedapi_combined_pb2.py (same dir)
#   pypowerwall/tedapi/protobuf/june_2026/tedapi_v2_*.proto     → ..._pb2.py (same dir)
#
# The bundle's TEDAPI schema spans several protobuf
# packages, so it is emitted as one file per package (energy_device.v1,
# energy_registration.v1, common.v1, google.rpc), referencing google.protobuf
# well-knowns via protoc's built-in imports. Regenerate the source .proto set
# from a bundle with: bash tools/tedapi_v2_extractor/regen.sh <bundle-path>

set -e
cd "$(git rev-parse --show-toplevel)"
python -m grpc_tools.protoc -I. --python_out=pypowerwall/local tesla.proto
# Legacy (June 2024) TEDAPI protos.
PROTO_V1_DIR=pypowerwall/tedapi/protobuf/june_2024
python -m grpc_tools.protoc -I "$PROTO_V1_DIR" --python_out="$PROTO_V1_DIR" "$PROTO_V1_DIR"/tedapi.proto
python -m grpc_tools.protoc -I "$PROTO_V1_DIR" --python_out="$PROTO_V1_DIR" "$PROTO_V1_DIR"/tedapi_combined.proto
# energy_device.v1 (June 2026). Date-neutral name (does not reveal the source APK version).
PROTO_V2_DIR=pypowerwall/tedapi/protobuf/june_2026
python -m grpc_tools.protoc -I "$PROTO_V2_DIR" --python_out="$PROTO_V2_DIR" "$PROTO_V2_DIR"/tedapi_v2_*.proto
# protoc emits bare cross-imports (`import tedapi_v2_x_pb2`); rewrite to package-
# relative (`from . import tedapi_v2_x_pb2`) so the dir works as a Python package.
# Deterministic, so committed output == script output (CI git-diff stays clean).
sed -i -E 's/^import (tedapi_v2_[a-z_]+_pb2) as /from . import \1 as /' "$PROTO_V2_DIR"/tedapi_v2_*_pb2.py
# Ensure the package marker exists.
[ -f "$PROTO_V2_DIR/__init__.py" ] || printf '"""TEDAPI v2 energy_device protobufs (Tesla One, June 2026 query set)."""\n' > "$PROTO_V2_DIR/__init__.py"
