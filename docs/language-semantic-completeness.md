# Language semantic completeness

dv-platform does not claim to implement the IEEE SystemVerilog, Verilog, or VHDL
languages itself. Production semantic authority belongs to an elaborating language
frontend. The `semantic_manifest` adapter imports that frontend's normalized output,
checks it against schema v2, archives the exact manifest and SHA-256 digest, and writes
canonical RTL facts consumed by `dv-platform plan`.

For exploratory VHDL-only projects, the built-in bounded source frontend can
normalize one unambiguous entity/generic/architecture profile without claiming
full IEEE elaboration. Unsupported interface types, architecture binding, and
mixed-language inputs fail closed. Strict language-completeness authority still
requires a complete governed semantic manifest; the bounded frontend does not
replace that contract.

## Supported standards

- SystemVerilog: IEEE 1800-2005, 2009, 2012, 2017, and 2023.
- Verilog: IEEE 1364-1995, 2001, and 2005.
- VHDL: IEEE 1076-1987, 1993, 2000, 2002, 2008, and 2019.

The manifest schema is [dvsem-v2.schema.json](../schemas/dvsem-v2.schema.json).
Each design unit identifies its language, standard, kind, source, normalized facts,
diagnostics, and completeness ledger.

## Completeness contract

Every design unit declares one state for every semantic dimension:

- lexical preprocessing and compilation-unit/library behavior
- design units, declarations, types, expressions, statements, and subprograms
- hierarchy, elaboration, parameters/generics, ports, and generate constructs
- packages/imports, interfaces/modports, and classes/randomization
- assignments, processes, memories, assertions, and functional coverage
- timing/specify semantics, foreign interfaces, attributes/pragmas, and file I/O
- clocks/resets, CDC, and protocol interpretation

Allowed states are `complete`, `partial`, `unsupported`, and `not_applicable`. Strict
import accepts only `complete` and `not_applicable`. Schema v0/v1 manifests migrate to
v2, but every newly introduced dimension becomes `partial`; migration never invents
semantic support.

## Import flow

Configure the adapter:

```toml
[[adapter_plugins]]
kind = "semantic_importer"
name = "semantic_manifest"
api_version = 1
```

Import and plan:

```console
dv-enterprise --config dv-platform.toml import-semantics --input build/top.dvsem.json --strict
dv-platform --config dv-platform.toml plan --target formal
dv-platform --config dv-platform.toml status --policy ci
```

Unknown fields, unsupported standards/unit kinds, source paths outside the repository,
missing sources, duplicate identities, dangling memory/domain references, invalid safe
CDC chains, malformed recursive expressions, and error diagnostics fail strict import.
The primary CI status includes the semantic completeness result.
