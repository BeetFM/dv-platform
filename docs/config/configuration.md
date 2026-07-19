# Configuration

The default project configuration file is `dv-platform.toml` in the client
repository root. This file is intended to be reviewed with the RTL project and
used by local runs and CI.

Generated state does not live in the config file location by default. Manifests,
caches, logs, indexes, plan databases, review databases, and run outputs live
under the configured work directory.

See [ADR-0001](adr/0001-local-project-configuration.md) for the accepted
configuration policy.

See [CLI Contract](cli-contract.md) for JSON output envelopes, stable error
codes, generated machine-state files, and CI usage.

## Example

```toml
[paths]
repo_root = "."
work_dir = ".dv-platform"
output_dir = "generated/dv-platform"
documentation_paths = ["docs", "specs"]
rtl_filelists = ["rtl/files.f"]
include_paths = ["rtl/include"]

[rtl]
defines = ["SIM=1", "ASSERT_ON"]
parameter_overrides = ["WIDTH=12"]
top_modules = ["top"]
verilator_executable = "verilator"

[retrieval]
index_dir = ".dv-platform/rag-index"

[policy]
allow_network = false
strict = false
ci = false

[plugins]
generator_backends = []

[[simulators]]
target = "cocotb"
name = "icarus"
command = "iverilog"

[[formal_tools]]
name = "symbiyosys"
command = "sby"
```

## Path Resolution

Relative paths are resolved from `repo_root`, except for an explicit config file
path passed on the command line, which is resolved from the current shell.

Recommended defaults:

- `repo_root = "."`
- `work_dir = ".dv-platform"`
- `output_dir = "generated/dv-platform"`
- `retrieval.index_dir = ".dv-platform/rag-index"`

The CLI should normalize paths before writing manifests so generated outputs are
reproducible and easy to audit.

## Sections

### `[paths]`

`repo_root`

The client RTL repository root. Defaults to the directory containing
`dv-platform.toml` when omitted.

`work_dir`

Local machine state directory for manifests, indexes, normalized facts, plan
databases, review databases, logs, temporary build output, and run results.

`output_dir`

Generated source artifact directory. Generated tests, harnesses, scripts, and
provenance manifests live here.

`documentation_paths`

List of documentation files or directories. Stage 3 initially supports Markdown
and plain text, with PDF extraction behind an extension point.

`rtl_filelists`

List of RTL file lists. File lists are preferred for reproducible enterprise
analysis. Interactive/local exploratory runs may walk HDL files directly when
this list is empty, but must warn that analysis may be incomplete. Strict and
CI/CD mode must treat an empty file-list set as an error.

`include_paths`

Additional RTL include directories.

### `[rtl]`

`defines`

Preprocessor defines passed to RTL tools.

`parameter_overrides`

Numeric top-level parameter overrides in `NAME=VALUE` form. Names must be unique
identifiers, values must be two-state decimal or based SystemVerilog integer
literals with digits valid for their radix, and an explicit top module is
required. Analysis passes each value to Verilator with `-G`; normalized plans
preserve the elaborated values, HDL harnesses render them on DUT instances,
VHDL scaffolds translate representable values to integers, and cocotb
compilation consumes the per-module elaborated parameter set from the execution
manifest.

`top_modules`

Top-level modules or analysis entry points.

`verilator_executable`

Verilator executable name, path, or command prefix for an enterprise wrapper.
Stage 2 standardizes on Verilator XML output from `--xml-only`.

### `[retrieval]`

`index_dir`

Local documentation retrieval index directory. Embedding and vector-store
providers are adapter-backed and must be explicitly configured when used.
Network-backed providers require `policy.allow_network = true`.

### `[policy]`

`allow_network`

When `false`, the platform must not perform network calls. Network-backed model,
embedding, retrieval, reporting, or telemetry integrations require this value to
be `true` and must remain auditable.

`strict`

When `true`, local workflows use stricter validation. Missing RTL file lists,
high-severity missing or unchecked generation preconditions, and missing
required tool configuration or required generated-code validator become errors.

`ci`

When `true`, the platform behaves as a CI/CD run. CI implies strict behavior and
produces deterministic machine-readable outputs and actionable exit codes.
`status --policy ci` additionally requires complete, current pipeline state,
artifact integrity, target validation, and run results.

### `[[simulators]]`

Simulator configuration is target-specific and project-specific. No global
client-project simulator is assumed.

Fields:

- `target`: generation target such as `cocotb`, `systemverilog`, `verilog`, or
  `uvm`
- `name`: local adapter name
- `command`: executable or wrapper command

If no simulator is configured, `generate` may still emit artifacts, but `run`
must fail with an actionable message. Strict and CI mode require explicit
simulator configuration for execution. The current CLI has no simulator
selection flag, so at most one simulator may be configured for each target.

### `[[formal_tools]]`

Formal tool configuration is explicit. SymbiYosys is the first formal adapter
for open fixture validation.

Fields:

- `name`: local adapter name such as `symbiyosys`
- `command`: executable or wrapper command, such as `sby`

Strict and CI mode require explicit formal tool configuration before formal
generation or execution. Formal runs create a run-local `.sby` that includes
the generated harness and the exact RTL sources, include paths, and defines
captured by the module execution manifest. The manifest is bound to the project
manifest digest and per-source SHA-256/size, so changed analysis inputs block a
run until regeneration. The current CLI supports one configured formal tool at
a time.

## Generated State

Recommended state layout:

```text
<work-dir>/
  project-manifest.json
  rag-index/
  verilator/
  rtl-facts/
  plans/
    plans.sqlite
    modules/
    index.md
  review/
    review.sqlite
    modules/
  runs/
    simulation/
    formal/
```

Recommended generated artifact layout:

```text
<output-dir>/
  simulation/
    <target>/
      modules/
        <module>/
  formal/
    modules/
      <module>/
```

## Current Implementation Status

The current implementation supports the core path fields, RTL file lists,
include paths, defines, numeric parameter overrides, top modules, Verilator
executable, retrieval index directory, network policy, strict mode, CI mode,
simulator entries, formal tool entries, and deterministic validation diagnostics
for input discovery and target-specific tool requirements.

Plugin, style, and provider sections are planned by the accepted architecture
decisions and should be implemented as the corresponding stages are completed.
The current implementation supports explicit generator plugin names in
`[plugins].generator_backends` through Python package entry points.
