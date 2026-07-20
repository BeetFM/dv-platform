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
parameter_sweeps = [["WIDTH=8", "DEPTH=2"], ["WIDTH=16", "DEPTH=4"]]
top_modules = ["top"]
verilator_executable = "verilator"

[retrieval]
index_dir = ".dv-platform/rag-index"

[policy]
allow_network = false
strict = false
ci = false

[ai]
model = "anthropic/claude-model-id"
api_key_env = "ANTHROPIC_API_KEY"
api_base = ""
api_version = ""
timeout_seconds = 60
max_retries = 2
max_output_tokens = 4096
max_context_chars = 32000
max_modules_per_run = 20
cache = true

[coverage]
line_minimum = 80.0
branch_minimum = 70.0
functional_minimum = 60.0

[execution]
max_parallel_modules = 4

[security]
audit_enabled = true
redact_patterns = ["token=[^ ]+", "LICENSE_KEY=[^ ]+"]

[plugins]
generator_backends = []

[[adapter_plugins]]
kind = "report_exporter"
name = "company_report"
api_version = 1

[[protocol_profiles]]
name = "company_req_ack"
kind = "req_ack"
valid_suffix = "_req"
ready_suffix = "_ack"
data_suffixes = ["_payload", "_data"]

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

List of documentation files or directories. Markdown, plain text,
reStructuredText, and PDF are supported. Extracted PDF chunks retain page
locators. Encrypted PDFs require a password-aware adapter, and scanned PDFs
require OCR before indexing.

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

`parameter_sweeps`

Explicit, bounded elaboration points. Each nested array is one independent set
of `NAME=VALUE` overrides. It is mutually exclusive with `parameter_overrides`.
Each point runs in its own work directory and receives a unique sweep-qualified
module, plan, evidence, and provenance identity. An explicit top module is
required; no Cartesian product is inferred implicitly.

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

Unchanged documentation chunks reuse their existing local vectors during a
refresh.

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

### `[coverage]`

Optional `line_minimum`, `branch_minimum`, `toggle_minimum`, and
`functional_minimum` values are percentages from `0` through `100`. Use
`dv-platform coverage --input <report>` to import one or more LCOV, JSON, or
Cobertura-style XML reports. Configured metrics must be present and meet their
threshold; otherwise the coverage command and CI status fail.

### `[ai]`

The optional planning model is selected with an arbitrary LiteLLM model string;
there is no platform-maintained provider registry. Examples include
`openai/<model-id>`, `anthropic/<model-id>`, `gemini/<model-id>`,
`deepseek/<model-id>`, `moonshot/<model-id>`, and
`ollama_chat/<model-id>`. `api_key_env` names an environment variable resolved
only when a live request is made. Omit it for provider-native credentials such
as Google ADC or for an unauthenticated local endpoint. Secret values must not
be placed in the TOML file or in `api_base`.

`api_base` and `api_version` are optional custom-provider settings. The timeout,
retry, output, context, and module limits bound each run; no more than 20 modules
may be selected for AI augmentation. One model is used for the whole run, with
no cross-provider fallback. `cache` stores only locally validated normalized
proposals below `<work-dir>/ai/cache` and never stores prompts, raw provider
responses, or credentials.

A live request—including HTTP to a local Ollama server—requires
`policy.allow_network = true`. The request includes normalized RTL facts,
retrieved documentation, the baseline plan, and small repository-contained HDL
snippets. This data may leave the machine. The request occurs only for explicit
`plan --ai`; ordinary `plan` remains deterministic and does not import LiteLLM.
Missing dependencies, credentials, network permission, provider errors, or
invalid output produce a reported per-module deterministic fallback. Valid
offline cache hits remain usable when network permission is disabled.

### `[execution]`

`max_parallel_modules` sets bounded concurrency for `run --all`. The valid
range is 1 through 256 and the default is 1. Single-module execution and output
ordering remain deterministic.

### `[security]`

`audit_enabled` controls the owner-only JSONL audit file under
`<work-dir>/audit/events.jsonl`. `redact_patterns` is a list of regular
expressions replaced with `[REDACTED]` in persisted tool logs, summaries,
commands, and audit details. Configuration and patterns are trusted local
policy; disable auditing only when the repository's operating policy explicitly
requires it.

### `[plugins]` and `[[adapter_plugins]]`

`plugins.generator_backends` explicitly enables generator entry points from
`dv_platform.generators`. Other adapter boundaries are explicit entries with
`kind`, `name`, and `api_version`. They are loaded from
`dv_platform.<kind>` and must report the matching kind and supported API version
before mutating commands proceed. Loading a plugin does not implicitly grant a
capability; concrete subsystems must opt into that adapter contract.

### `[[protocol_profiles]]`

Profiles declaratively recognize flat `ready_valid` or `req_ack` handshakes.
`valid_suffix` and `ready_suffix` identify the control pair and
`data_suffixes` lists payload candidates in priority order. Direction determines
sink/source role. Ambiguous or incomplete matches do not invent a channel.

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
  audit/
    events.jsonl
  coverage/
    summary.json
  verilator/
  rtl-facts/
  plans/
    plans.sqlite
    modules/
    index.md
  ai/
    cache/
    runs/
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

All sections documented above are parsed, normalized, validated, and
round-tripped by the current CLI. The generic adapter contract currently
provides explicit discovery and compatibility gating; concrete enterprise
provider/runner/exporter behavior remains an extension implementation.
