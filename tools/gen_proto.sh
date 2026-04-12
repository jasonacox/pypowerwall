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
#   tools/requirements-tools.txt currently pins the generator to protobuf
#   4.25.x, and the generated pb2 files currently target protobuf>=4.25.1.
#   (protobuf 4.25.x does NOT embed ValidateProtobufRuntimeVersion, so any
#   4.x runtime is compatible — but 5.x is not.)
#   If you upgrade tools/requirements-tools.txt you MUST also update the
#   protobuf floor/cap in requirements.txt and setup.py to stay aligned.
#
# USAGE:
#   bash tools/gen_proto.sh
#
# PROTO → PB2 MAPPINGS:
#   tesla.proto                              → pypowerwall/local/tesla_pb2.py
#   pypowerwall/tedapi/tedapi.proto          → pypowerwall/tedapi/tedapi_pb2.py
#   pypowerwall/tedapi/tedapi_combined.proto → pypowerwall/tedapi/tedapi_combined_pb2.py

set -e
cd "$(git rev-parse --show-toplevel)"
python -m grpc_tools.protoc -I. --python_out=pypowerwall/local tesla.proto
python -m grpc_tools.protoc -I pypowerwall/tedapi --python_out=pypowerwall/tedapi pypowerwall/tedapi/tedapi.proto
python -m grpc_tools.protoc -I pypowerwall/tedapi --python_out=pypowerwall/tedapi pypowerwall/tedapi/tedapi_combined.proto
