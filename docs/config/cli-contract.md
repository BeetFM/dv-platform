# CLI Contract

This document defines the current local CLI contract for human and CI usage.
The CLI remains local-first: source files, documentation chunks, indexes,
normalized RTL facts, generated artifacts, run logs, and reports stay under
configured client-controlled paths.

## Output Modes

By default, commands emit human-readable `key=value` lines. This is intended for
interactive use and simple shell inspection.

Use `--json` for machine-readable output:

```bash
dv-platform --repo-root /path/to/repo --json plan --target cocotb
```

JSON output is a single object written to stdout. Supported commands:

- `init`
- `index-docs`
- `analyze-rtl`
- `plan`
- `generate`
- `run` for single-module runs
- `coverage`
- `review`
- `status`

Aggregate `run --all` still uses the text output contract and writes an
aggregate summary file under the work directory.

## JSON Success Envelope

Successful JSON responses use this envelope:

```json
{
  "ok": true,
  "command": "generate",
  "data": {}
}
```

The `data` object is command-specific. Paths are serialized as strings.
Counters are serialized as numbers. Lists such as generated artifact paths are
serialized as JSON arrays.

## JSON Error Envelope

Failed JSON responses use this envelope:

```json
{
  "ok": false,
  "command": "plan",
  "error": {
    "code": "missing_rtl_facts",
    "message": "RTL facts are missing; run analyze-rtl first: ..."
  }
}
```

Some errors include additional fields:

```json
{
  "ok": false,
  "command": "generate",
  "error": {
    "code": "claim_gate_blocked",
    "message": "Generation blocked by claim gate for modules: fifo"
  },
  "data": {
    "blocked_modules": ["fifo"]
  }
}
```

Configuration errors may include diagnostics:

```json
{
  "ok": false,
  "command": "analyze-rtl",
  "error": {
    "code": "configuration_error",
    "message": "RTL analysis configuration is invalid."
  },
  "diagnostics": [
    {
      "severity": "error",
      "message": "No RTL file lists configured; walking repository HDL files directly may be incomplete."
    }
  ]
}
```

## Current Error Codes

| Code | Command | Meaning |
| --- | --- | --- |
| `ai_preflight_failed` | `plan` | AI configuration, flags, module selection, or module count is invalid before provider calls. |
| `artifact_write_failed` | `generate` | Generated artifact validation or writing failed. |
| `claim_gate_blocked` | `generate` | Stored plans contain blocked claim gates. |
| `configuration_error` | `analyze-rtl` | Input-consuming configuration is invalid. |
| `coverage_gate_failed` | `coverage` | At least one configured coverage threshold was not met. |
| `coverage_import_failed` | `coverage` | A coverage report was missing, malformed, or unsupported. |
| `discovery_failed` | `analyze-rtl` | Repository discovery or file-list parsing failed. |
| `formal_execution_failed` | `run` | Formal tool invocation failed before a normal summary could be written. |
| `index_failed` | `index-docs` | Documentation indexing failed. |
| `invalid_module` | `run` | The requested module is empty or unsafe as a filesystem component. |
| `invalid_plans` | `generate` | Stored plans exist but cannot be read by this CLI version. |
| `invalid_rtl_facts` | `plan`, `review` | RTL facts exist but cannot be read by this CLI version. |
| `invalid_timeout` | `run` | The timeout is zero or negative. |
| `missing_formal_tool` | `run` | No formal tool is configured for a formal run. |
| `missing_generator` | `generate` | No generator is registered for the requested target. |
| `missing_plans` | `generate` | Plan database is missing; run `plan` first. |
| `missing_rtl_facts` | `plan`, `review` | Normalized RTL facts are missing; run `analyze-rtl` first. |
| `missing_simulator` | `run` | No simulator is configured for the requested simulation target. |
| `adapter_plugin_error` | mutating commands | An explicitly configured versioned adapter was missing or incompatible. |
| `plugin_load_failed` | `generate` | An explicitly enabled generator plugin was missing or invalid. |
| `simulation_execution_failed` | `run` | Simulator invocation failed before a normal summary could be written. |
| `status_policy_failed` | `status` | `status --policy ci` found incomplete/incompatible pipeline state, missing or corrupt generated artifacts, failed/missing validation, incomplete/failed runs, or missing required tools. |
| `tool_configuration_error` | `generate`, `run` | Target-specific tool configuration is invalid. |
| `verilator_execution_failed` | `analyze-rtl` | Verilator could not be invoked. |
| `verilator_failed` | `analyze-rtl` | Verilator ran and returned a non-zero exit code. |

## Stable Workflow

The production-oriented command sequence is:

```bash
dv-platform --repo-root /path/to/repo init \
  --documentation-path docs \
  --rtl-filelist rtl/files.f \
  --top-module top \
  --parameter WIDTH=12

dv-platform --repo-root /path/to/repo analyze-rtl
dv-platform --repo-root /path/to/repo index-docs
dv-platform --repo-root /path/to/repo plan --target cocotb --target formal
dv-platform --repo-root /path/to/repo generate --target cocotb
dv-platform --repo-root /path/to/repo generate --target formal
dv-platform --repo-root /path/to/repo run --target cocotb --module top
dv-platform --repo-root /path/to/repo coverage --input build/coverage.info
dv-platform --repo-root /path/to/repo review
dv-platform --repo-root /path/to/repo status
```

Optional AI planning uses `plan --ai`. Repeat `--module NAME` to limit which
modules are disclosed to and augmented by the configured model; deterministic
plans are still regenerated for every normalized module. `--ai-refresh`
bypasses validated proposal caches. Preflight configuration, unknown-module,
and module-limit failures use `ai_preflight_failed` and exit `2`. Once preflight
succeeds, module-level dependency, credential, network, provider, timeout,
rate-limit, authentication, and response failures are reported as fallbacks and
the command exits successfully with deterministic plans intact.

For CI, use `--ci --json` on commands whose stdout is consumed by automation.
CI implies strict behavior through configuration normalization.

## Generated Machine State

Important machine-readable files:

| File | Producer | Purpose |
| --- | --- | --- |
| `<work-dir>/project-manifest.json` | `analyze-rtl` | Discovered sources, parameter overrides, both frontend commands, and Slang policy/version. |
| `<work-dir>/rtl-facts/modules.json` | `analyze-rtl` | Normalized RTL facts. |
| `<work-dir>/rtl-facts/summary.json` | `analyze-rtl` | Compact RTL facts summary. |
| `<work-dir>/rag-index/chunks.json` | `index-docs` | Documentation chunks. |
| `<work-dir>/rag-index/vectors.json` | `index-docs` | Local deterministic vector index. |
| `<work-dir>/rtl-facts/cache.json` | `analyze-rtl` | Input fingerprint used to skip unchanged analysis; `--force` bypasses it. |
| `<work-dir>/slang/ast.json` | `analyze-rtl` | Slang AST JSON for the ordinary elaboration point. |
| `<work-dir>/slang/{slang-command.json,slang-version.txt,diagnostics.json}` | `analyze-rtl` | Auditable Slang invocation, version, and diagnostics. |
| `<work-dir>/slang/logs/*.log` | `analyze-rtl` | Redacted Slang stdout and stderr. |
| `<work-dir>/semantic-crosscheck/result.json` | `analyze-rtl` | Aggregate schema-v2 status, capabilities, frontend metadata, evidence, and per-field issues. |
| `<work-dir>/sweeps/<identity>/slang/crosscheck.json` | `analyze-rtl` | Independent result for one parameter-sweep point. |
| `<work-dir>/plans/plans.sqlite` | `plan` | Canonical verification plans. |
| `<work-dir>/plans/modules/*.plan.md` | `plan` | Human-readable plan views. |
| `<work-dir>/plans/claims/*/claims.json` | `plan` | Claim gate reports. |
| `<work-dir>/ai/cache/*.json` | `plan --ai` | Owner-only validated normalized proposals; no raw prompts, responses, or credentials. |
| `<work-dir>/ai/runs/*/*.json` | `plan --ai` | Owner-only per-module model/cache/error provenance and token/cost metadata. |
| `<output-dir>/.../provenance.json` | `generate` | Schema-v2 provenance, quality and tool-validation results, plus artifact SHA-256/size integrity metadata. |
| `<output-dir>/.../execution-manifest.json` | `generate` | Adapter, elaborated parameters, generated file/trace IDs, project-manifest digest, and exact RTL input hashes used by execution. |
| `<work-dir>/runs/**/summary.json` | `run` | Simulation/formal execution summaries. |
| `<work-dir>/coverage/summary.json` | `coverage` | Merged metrics, gates, and module gaps. |
| `<work-dir>/audit/events.jsonl` | mutating commands and tool runs | Owner-only redacted local audit events. |
| `<work-dir>/review/review.sqlite` | `review` | Canonical design review findings. |
| `<work-dir>/review/review.json` | `review` | Machine-readable review report. |
| `<work-dir>/review/review.md` | `review` | Human-readable review report. |

The `status` command reads the files above and reports schema compatibility,
configured tool availability, planned/generated target completeness, generated
artifact quality and content integrity, generator tool-validation state, and
execution-manifest/source currency, traceability completeness, run
completeness/results, and imported coverage gates. It does not invoke configured
simulators or formal tools.

Use `status --policy ci` to turn incompatible local state into exit code `2`.
Global `--ci status` also enables CI policy mode. CI policy requires current,
non-empty RTL facts and plans, every planned output, valid artifact provenance
and hashes, required generator validation, and a passing run summary for every
generated executable target. Add `--no-require-tools` only when a job should
skip executable availability checks; all state and result checks remain active.
Run summaries carry the generated provenance SHA-256, so a result from an older
generation cannot satisfy the current CI policy.

Executable run summaries also include generated-to-plan traceability,
independent mapped-check outcomes, failure traceability, tool version, triage
classification, and repair suggestions. Formal summaries include per-task
prove/cover state and any discovered counterexample trace paths.

Generation publishes a target/module directory only after deterministic
structure and quality checks complete. SystemVerilog/Verilog generation invokes
Verilator lint, VHDL invokes GHDL when available, cocotb parses generated Python,
and formal validation is deferred to the configured proof run. Runs re-check
provenance and content hashes before invoking any configured tool.

## Exit Codes

Current convention:

- `0`: command completed successfully.
- `1`: a simulator completed but executable test results failed validation
  (including failed/zero cocotb testcases or missing/malformed result XML), or
  imported coverage failed a configured threshold.
- `2`: CLI/configuration/input/artifact error.
- `124`: run timeout, when surfaced by simulator/formal execution summaries.
- other non-zero values: propagated tool return codes, especially from
  `analyze-rtl` when Verilator exits non-zero.

## Plugin Loading Policy

Generator plugins are loaded only when explicitly enabled in configuration:

```toml
[plugins]
generator_backends = ["company_uvm"]
```

The entry-point group is `dv_platform.generators`. The CLI does not auto-load
repository-local executable code.

Other explicitly configured adapters use `dv_platform.<kind>` entry-point
groups and API version 1. Kind/API mismatches or missing configured entry points
fail before a mutating command continues. The loader is a compatibility and
trust boundary; subsystem-specific hooks must still be implemented by the
adapter kind.
