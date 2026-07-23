# P1 Expansion Acceptance

This document defines the broader internal-adoption slice implemented after the
P0 pilot. The scope is evidence-backed and fail-closed: a normalized fact is not
the same as a proof of correctness, and generators still refuse inputs whose
semantics cannot be represented safely.

Snapshot date: 2026-07-19.

## Accepted Capabilities

### Semantic identity and hierarchy

- Every plan has a stable plan identity separate from the original RTL design
  unit, elaborated design unit, and specialization ID.
- Verilator normalization recognizes multiple elaborated specializations of one
  original module. Specializations receive deterministic identities, instance
  parameter bindings, and hierarchy links to the corresponding plan identity.
- Facts and plans preserve structured ports, parameters, types, memories,
  memory accesses, generate scopes, packages/imports, instances, assignments,
  procedures, control domains, assertions, covers, and protocols.
- Memory accesses record read/write direction, address/data/enable signals,
  synchronous behavior, domain, source location, and evidence. Unknown
  read-during-write policy remains explicit.
- Cross-domain signal flow records source/destination domains, inferred
  synchronizer stages, reset compatibility, structural classification, and
  evidence. Unproven crossings create critical review findings.

### Protocol and requirement semantics

- Built-in flat ready/valid recognition remains available. Project-defined
  `ready_valid` and `req_ack` naming profiles can map different suffixes and
  payload names without code changes.
- Markdown, text, reStructuredText, and PDF specifications are indexed. PDF
  evidence includes page locators; encrypted or image-only PDFs fail with an
  actionable error instead of silently indexing empty text.
- Requirements, claims, behaviors, checks, and generated symbols have stable
  IDs and evidence references. Each check records its category and whether it
  is executable.

### Generation, execution, and closure

- Cocotb and formal execution expand generated trace records into independent
  pass/fail/unexecuted outcomes for every mapped check ID.
- Formal summaries retain prove/cover task status. Generated formal collateral
  includes reset/state-transition and handshake properties plus supported
  synchronous-memory write/address properties.
- Native SystemVerilog emits evidence-backed assertions and covers for supported
  behaviors and protocols.
- A single inferred sink/source handshake pair produces a UVM transaction,
  sequence, sequencer, driver, monitor, FIFO scoreboard, environment, test,
  virtual interface, config-db wiring, and DUT top. Ambiguous transaction
  boundaries continue to produce a conservative scaffold with open questions.
- `dv-platform coverage` imports and merges LCOV, JSON, and Cobertura-style XML,
  computes line/branch/toggle/functional metrics when supplied, applies project
  thresholds, reports module gaps, and feeds `status --policy ci`.

### Operations and extension boundaries

- RTL analysis has input-fingerprint caching and `--force` invalidation.
- Documentation indexing reuses embeddings for unchanged chunks.
- `run --all` uses bounded module-level concurrency configured by
  `execution.max_parallel_modules` while preserving deterministic summaries.
- Explicit adapter entry points use the versioned `dv_platform.<kind>` contract;
  kind and API mismatches fail before a mutating command runs.
- Mutating commands and tool runs append local owner-only audit events.
  Configured regular expressions redact command, log, summary, and audit text.
- Status reports schema compatibility, current generated/run state, imported
  coverage, and CI policy failures without invoking external tools.

## Acceptance Gate

The P1 slice is accepted when these commands pass:

```bash
uv sync --all-groups --frozen
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run coverage json -o .dv-platform/python-coverage.json
uv run python scripts/checks/branch_coverage.py .dv-platform/python-coverage.json
uv build --out-dir .dv-platform/package-check
uv run pip-audit --skip-editable
```

Where installed, the integration suite additionally exercises Verilator XML,
Verilator lint, Icarus/cocotb, and SymbiYosys/Yosys/Z3 prove and cover tasks.
Hosted CI keeps those real-tool gates mandatory.

## Deliberate Boundary

This acceptance does not claim complete SystemVerilog or UVM semantics. The
normalizer is a conservative Verilator-XML interpretation, CDC recognition is
structural rather than sign-off analysis, and memory collision behavior remains
unknown unless evidenced. Parameter sweeps, generic multi-agent UVM,
register-model generation, asynchronous FIFO proofs, UCIS databases, commercial
tool adapters, and repository-scale benchmarks remain later work. The current
residual inventory is maintained in [Missing Work](../planning/missing-work.md).
