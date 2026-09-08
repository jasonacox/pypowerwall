# TEDAPI Protobuf Schemas

The `.proto` files in this directory tree are the **single source of truth for
the TEDAPI wire schema**. The `*_pb2.py` files beside them are generated — never
edit those by hand, and never hand-roll protobuf wire bytes in library code
(varint encoders, field walkers, raw byte appends). If a message or field you
need is missing, extend the `.proto` and regenerate. See
[AGENTS.md](../../../AGENTS.md) ("A new TEDAPI protobuf message or TEG
command") for the full policy.

## Directory layout

| Directory | Selected by | Contents |
|---|---|---|
| `V2024_06/` | `tedapi_api_version="V2024_06"` (default) | Legacy QueryType path, from hand-rolled protocol captures: `tedapi.proto` (core message/envelope), `tedapi_combined.proto` (signing protocol + TEG/FileStore commands) |
| `V2026_06/` | `tedapi_api_version="V2026_06"` (opt-in, pairs with bearer auth) | Tesla-signed GraphQL query set: `tedapi_v2_*.proto`, one file per Tesla protobuf package, extracted from a Tesla app bundle (`tools/tedapi_v2_extractor/regen.sh`) |

`tedapi_api_version` labels are dates (`V<YYYY>_<MM>[_<DD>]`,
`pypowerwall/tedapi/api_version.py`) and code gates on ordering
(`< TEDAPIApiVersion.V2026_06`), so newer sets inherit the newer path. A new
Tesla query set gets a **new** date-labeled directory and enum member — never
mutate an existing set in place, since users pin `tedapi_api_version`.

## Which set does my change belong in?

- **Legacy-transport messages** (TEG commands such as `setIslandMode` and max
  backup, `config.send`, `firmware.request`) → `V2024_06/tedapi_combined.proto`.
  These are version-independent on the wire; even V2026_06 sessions send
  config/TEG through the legacy parser.
- **Signed-GraphQL query surface** → the `V2026_06/` set. Those files are
  extracted from Tesla's app bundle, so prefer re-extracting from a newer
  bundle over hand-editing them.
- When adding a field observed on the wire (not from a published Tesla schema),
  include a comment with its provenance and hardware-validation status — see
  `TEGAPISetIslandModeRequest` in `tedapi_combined.proto` for the pattern.

## Regenerating pb2 files

```bash
bash tools/gen_proto.sh
```

Always use the script — not bare `protoc`. It uses a dual toolchain (see its
header comments): the V2024_06/legacy set is generated with protobuf 4.25.x
gencode so it runs on the library's `protobuf>=4.25.1` runtime floor, while the
V2026_06 set uses the latest toolchain and is imported lazily, opt-in only.
Do not raise the protobuf floor in `requirements.txt`/`setup.py` to match the
newer toolchain.

Guardrails: the pre-commit hook runs the script whenever a `.proto` is staged,
and CI (`.github/workflows/check-protobuf.yml`) fails if committed pb2 files
don't match their sources.

After regenerating, run `pytest -m "not live"`. Additive field changes keep
existing messages' wire format unchanged (field numbers are the contract, not
the generated code), and hardware-validated commands have their exact
serialized bytes pinned in unit tests (e.g.
`pypowerwall/tests/unit/test_v1r_islanding.py`) — if a regeneration changes
those bytes, that's a regression, not a test to update.
