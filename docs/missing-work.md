# Missing Work and Tooling Inventory

This document is the post-P0 repository gap assessment. It distinguishes the
completed, intentionally narrow pilot contract from work still needed for broad
internal adoption and enterprise sign-off. Each section describes the current
capability, the gap, and the software or external tools likely needed to close
it.

Snapshot date: 2026-07-19.

## Current Baseline

Implemented and passing in the current repository:

- Local CLI commands: `init`, `index-docs`, `analyze-rtl`, `plan`, `generate`,
  `run`, `review`, and `status`.
- Local TOML configuration, deterministic project discovery, and exclusion of
  work/output/cache trees from fallback RTL discovery.
- Verilator XML invocation, tested-major compatibility gating, raw artifact/log
  storage, normalized elaborated parameters/memories/hierarchy/control domains,
  ready/valid channels, source locations, and target-specific fail-closed
  semantic-feature classification.
- Documentation loading for Markdown, text, and reStructuredText.
- Local deterministic chunk index plus local hash-vector retrieval fallback.
- Evidence refs, claim statuses, claim gates, structured and deduplicated
  requirements, precise document offsets, conflict gates, and JSON/Markdown
  claim reports.
- SQLite-backed plan storage with deterministic Markdown/claim views and stale
  view cleanup.
- Cocotb generation and Icarus/cocotb execution for scalar/vector controls,
  reset/increment/hold, multiple mapped clocks, and conventional ready/valid
  transfer/backpressure/data integrity.
- SymbiYosys formal harness generation with reset assumptions, vector symbolic
  inputs, numeric elaborated parameters, counter and ready/valid safety
  properties, prove/cover tasks, trace discovery, executable-symbol coverage,
  and formal run feedback.
- Structured port/clock/reset-aware SystemVerilog, Verilog, VHDL, UVM, cocotb,
  and formal generators, with target quality requirements.
- Design review reports backed by RTL facts and failed run summaries.
- Atomic state publication, staged module replacement, stale artifact cleanup,
  content-hashed artifact provenance, and execution manifests bound to the
  current source inputs.
- Status command with fail-closed CI checks for schema currency, non-empty
  facts/plans, planned output completeness, artifact integrity, generator tool
  validation, executable traceability, execution-manifest/source currency, run
  completeness/coverage/results, and configured tool availability.
- A repeatable golden pilot fixture plus GitHub Actions gates for Python 3.11,
  3.12, and 3.13, lint, format, typing, branch coverage, packaging, dependency
  audit, Verilator analysis/lint, Icarus/cocotb execution, and mandatory
  SymbiYosys/Yosys/Z3 proof execution.

Current local test status:

- `uv run python -m unittest discover -s tests` passes 200 tests, including
  real-tool integration when the corresponding EDA tools are installed.
- Branch coverage is 86%, above the enforced 80% project threshold.
- The current checkout has no generated project state by default; `status`
  reports missing RTL facts and missing plans until the workflow is run.

## Priority Legend

- `P0`: required before a credible pilot repository workflow.
- `P1`: required before broad internal adoption.
- `P2`: useful hardening or expansion after the first pilot path is stable.

## P0 Status: Complete for the Documented Acceptance Slice

P0 is complete against `docs/pilot-acceptance.md`. The boundary is intentionally
fail-closed: unsupported semantics or ambiguous control domains prevent
generation rather than silently broadening the claim of support. The following
subsections record the implemented P0 guarantees and the exact limitations that
move forward as P1 work.

### End-to-End Pilot Workflow

Current state:

- The realistic fixture in `tests/fixtures/pilot` executes the complete strict
  cocotb workflow from initialization through CI policy status.
- Regression assertions cover real Verilator analysis, real Icarus/cocotb
  execution, generated files, run summaries, review findings, stale-state
  cleanup, and repeated-run stability.
- `docs/pilot-acceptance.md` defines the acceptance checklist and supported
  scope.
- Hosted CI installs a pinned SymbiYosys revision plus Yosys and Z3 and executes
  the real formal integration class in an explicit mandatory step.
- CI therefore cannot satisfy formal P0 by skipping for a missing tool.

### RTL Semantic Normalization

Current state:

- Verilator XML normalization extracts modules, structured ports, numeric
  elaborated parameter values, unpacked memory shape, original/elaborated child
  identity, child port connections, assignments, procedural blocks, basic
  expression trees, assertions, covers, and conservative reset/increment
  procedural patterns.
- Sequential sensitivity trees provide clock/reset inference and reset polarity
  for common asynchronous-reset shapes; conservative name heuristics are the
  fallback and the classification method is recorded.
- Source locations support both legacy and current Verilator XML location
  encodings, and the source file is mapped out of the XML file table.
- Verilator major version 5 is the explicit tested range; strict analysis and CI
  reject unknown or unsupported majors.
- Procedural blocks map to explicit clock/reset domains. Conventional flat
  ready/valid channel roles, data widths, clocks, resets, and evidence are
  normalized.
- Semantic-feature safety is target-specific. Internal case statements and
  unpacked memories are accepted by the exercised black-box/native/formal
  paths; enums, structs/unions, interfaces/modports, and unsupported target
  combinations still block generation.

P0 boundary:

- Only numeric top-parameter overrides for a single elaborated configuration,
  memory shape (not complete access semantics), conventional flat ready/valid
  naming, and mapped procedural domains covered by the golden fixtures are
  supported. Sweeps, mixed specializations, interfaces, and broader semantics
  move to P1.

### Requirement and Intent Extraction

Current state:

- Documentation chunks are retrieved and converted into simple requirement
  summaries.
- The planner derives reset, increment, hold, connectivity, and structured
  ready/valid transfer/backpressure/data-integrity checks from deterministic
  rules.
- Requirement IDs are stable, duplicates merge all evidence, exact sentence
  byte offsets are retained, and contradictory expected values for the same
  condition create a critical generation-blocking claim.
- Categories cover reset, increment, hold, latency, error, ordering,
  performance, power, debug, coverage, protocol, connectivity, and general
  intent. Only the deterministic simple-behavior subset becomes executable
  checks; the rest produces explicit open questions instead of invented logic.

P0 boundary:

- Configurable protocol libraries, multi-channel scoreboards, register models,
  and broad natural-language quality analysis remain P1. P0 now covers the
  conventional single sink/source ready/valid pattern, not comprehensive
  language understanding.

### Executable Generation Quality

Current state:

- Cocotb generation emits executable evidence-backed tests for reset,
  increment, hold, vector IO, conventional ready/valid transfer, bounded
  observation, backpressure stability, and end-to-end data integrity. It can
  start every classified clock and uses protocol/domain mappings for the
  expanded pilot.
- Formal generation emits SymbiYosys harnesses and prove/cover `.sby`
  configurations.
- All built-in generators consume structured direction, width, signedness,
  clock, reset, and polarity facts instead of requiring suffix conventions.
- Cocotb uses Python AST validation. SystemVerilog and Verilog use real
  Verilator lint. VHDL uses GHDL when available. Formal validation is completed
  by execution. Validation results are recorded in provenance and strict mode
  rejects a missing required validator.
- Every executable artifact carries target quality requirements; generation
  rejects missing or failed requirements before publishing the module tree.
- Every module has an execution manifest containing adapter identity,
  elaborated parameter values, generated files and trace IDs, project-manifest
  digest, source hashes/sizes, include paths, defines, and tops. Runtime
  compilation consumes that manifest.
- Every executable generated symbol maps to plan check indexes, requirement,
  behavior, and claim IDs, plus evidence refs. Publication and CI reject missing
  traceability.
- Unmapped multiple clocks/resets and target-unsupported semantic features fail
  generation quality checks.

P0 boundary:

- Memory-specific scoreboards, interfaces, parameter sweeps/mixed
  specializations, CDC correctness, reset-domain sequencing, general protocol
  transactions, UVM validation, and configurable style profiles remain P1.

### Formal Flow Completion

Current state:

- Formal tool configuration exists.
- SymbiYosys harnesses constrain reset at initialization and release, emit
  evidence-backed reset/increment/hold and ready/valid source-stability
  properties, support vector symbolic inputs and numeric parameterized DUT
  instances, derive bounded depth from supported latency intent, and require
  both prove and cover tasks.
- Formal runs fail on an unknown result even when the process exits zero, retain
  tool versions and discovered VCD/FST/Yosys witness/SMT traces, refuse to let a
  passing base case mask an unknown induction result, and map failures to
  generated symbols and plan intent for review.

P0 boundary:

- Assumption consistency proofs, protocol properties beyond ready/valid safety,
  multi-clock harnesses, generic memory correctness, interfaces,
  unreachable-state invariant synthesis, unbounded liveness, and richer
  property-specific counterexample mapping remain P1.

### Run Feedback Loop

Current state:

- Simulation and formal run summaries are persisted.
- Run failures map through artifact traces to checks, claims, requirements,
  behaviors, evidence, and generated source artifacts.
- Summaries expose pass/fail/unexecuted generated-symbol trace coverage, triage
  categories, and deterministic repair suggestions. Review ignores stale
  summaries, cites failure evidence, and surfaces incomplete trace execution.

P0 boundary:

- The implemented metric is generated-symbol execution coverage with mappings
  back to verification-plan records. Independent outcome attribution for every
  mapped check/property, simulator code/functional coverage, and automated plan
  mutation/repair remain P1.

## P1 Missing Work

The fresh post-P0 rescan found the following gaps in priority order. The first
three are the largest constraints on applying the platform to a design outside
the golden slice.

### 1. Semantic and Hierarchy Expansion

Missing:

- Complete normalized statement semantics for nested branch polarity, case item
  meaning, arithmetic/comparisons, memory reads/writes and collision policy,
  structs/unions, enums, packed types, interfaces/modports, generate blocks,
  packages, imports, and typedefs.
- Multiple specializations of one source module, parameter expressions/sweeps,
  generate-aware hierarchy graphs, and per-instance plan identities.
- CDC intent, synchronizer recognition, reset sequencing, and cross-domain
  confidence/behavior checks beyond the current per-block domain mapping.
- Compatibility fixtures for additional Verilator minor releases and a
  cross-check parser for constructs Verilator XML does not normalize cleanly.

Likely tools:

- Verilator plus Slang or Surelog/UHDM for semantic cross-checking.
- Commercial elaboration reports where a pilot repository already licenses
  them.

### 2. Protocol and Requirement Semantics

Missing:

- Protocol schemas beyond conventional flat ready/valid, multi-channel
  transactions/scoreboards, register behavior, error paths, latency,
  ordering, clock-domain behavior, reset sequences, performance limits, power
  states, debug intent, and coverage goals that can drive executable checks.
- Documentation freshness and undocumented-RTL quality analysis.
- PDF specification ingestion and scalable semantic retrieval.

Likely tools:

- Local/enterprise-approved embedding and model runtimes, after deterministic
  evidence gates.
- PDF extraction and a larger local vector index.

### 3. Execution Depth and Coverage Closure

Missing:

- Generated memory models/scoreboards, interfaces, parameter sweeps, complex
  combinational logic, configurable protocols, CDC, and reset-domain sequences.
- Stronger formal assumption consistency, invariant generation for
  unreachable-state induction, broader protocol properties, liveness, and
  per-property counterexample attribution.
- Check/property-level outcome accounting. Current traces prove that generated
  executable symbols ran and retain their plan mappings; they do not report an
  independent result for every check ID mapped to a symbol.
- Simulator line/toggle/branch and functional coverage import, merging, goals,
  exclusions, and coverage-gap-driven planning.
- Declarative generation style profiles for naming, headers, timescale, reset
  convention, simulator/tool preference, verbosity, and output naming.

Likely tools:

- Simulator coverage APIs/formats and formal coverage reports.
- GHDL, Verible/svlint, and a UVM-capable compiler as backends expand.

### UVM and Native HDL Backends

Current state:

- SystemVerilog, Verilog, VHDL, and UVM generators exist as conservative
  scaffolds.

Missing:

- Real UVM agents, sequence items, sequencers, drivers, monitors, scoreboards,
  environments, tests, virtual interfaces, configuration database usage,
  compile/run file lists, and simulator-specific switches.
- Transaction and protocol inference from documentation or configuration.
- Native SystemVerilog assertions and functional coverage from plan checks.
- VHDL-first entity/generic/architecture awareness.
- Verilog-compatible output that avoids SystemVerilog-only constructs.

Likely tools:

- One or more commercial or enterprise simulators for UVM validation: Questa,
  VCS, Xcelium, Riviera-PRO, or a client-approved equivalent.
- GHDL for open VHDL validation.
- Verilator or Slang for open SystemVerilog syntax validation where applicable.

### Plugin and Adapter Boundaries

Current state:

- Generator plugins can be loaded explicitly through Python entry points.

Missing:

- Plugin boundaries for simulator runners, formal runners, documentation
  loaders, embedding providers, vector stores, style profiles, report exporters,
  redaction policies, and enterprise tool integrations.
- Versioned adapter contracts and compatibility tests.
- Plugin security rules and audit output.

Likely tools:

- Python packaging entry points.
- Internal package index or wheel distribution path for enterprise-local
  plugins.

### Enterprise Reporting

Current state:

- Plans and review findings use SQLite as canonical stores.
- Markdown and JSON reports exist for plans, claims, reviews, status, and run
  summaries.

Missing:

- YAML export for pipeline artifacts and human review.
- SARIF export for findings that map cleanly to source locations and rules.
- Report filtering by severity, confidence, target, module, source file, and
  evidence status.
- Stable report schemas and schema migration tests.

Likely tools:

- Standard-library JSON/SQLite is sufficient for the canonical path.
- Optional YAML dependency, such as PyYAML or `ruamel.yaml`, if YAML export is
  added.

### Cache Invalidation and Reproducibility

Current state:

- Outputs are deterministic in many unit-tested cases.
- Schema versions exist for RTL facts and plans.
- Executable modules bind project-manifest and HDL-source digests, run summaries
  bind provenance digests, and the golden workflow checks stable repeated hashes
  plus stale-output removal.

Missing:

- Dependency-graph invalidation across documentation chunks, vectors, plans, and
  review reports; current commands are deterministic but primarily rebuild by
  stage.
- Compatibility policy for simulator, SymbiYosys, Yosys, solver, GHDL, and
  validator versions. Versions are recorded where invoked, but only Verilator
  has an enforced tested-major range in application policy.
- Rebuild policies for partial versus full regeneration.
- Reproducibility checks across platforms and EDA tool versions, beyond the
  repeated same-runner pilot assertion.

Likely tools:

- No new mandatory tools; this is primarily implementation work.
- CI storage of generated state artifacts for comparison.

### Security, Privacy, and Export Controls

Current state:

- Network access is disabled by default and controlled by config.
- Local work/output directories are explicit.

Missing:

- Structured audit logs for network/model calls.
- Redaction controls for source snippets, logs, generated reports, and exported
  artifacts.
- Explicit policy for which files may leave the repo/work directory.
- Secrets handling for model endpoints or commercial tool licenses.
- Threat model for repository-local plugin code and generated run scripts.

Likely tools:

- No mandatory external tools.
- Optional secret-management integration in enterprise environments.

## P2 Missing Work

### Documentation

Missing or incomplete documents:

- `docs/cli.md`: full command reference, examples, exit codes, and JSON
  envelopes.
- `docs/rag.md`: document loading, chunking, embeddings, vector stores,
  retrieval scoring, and privacy expectations.
- `docs/generation-backends.md`: backend contracts and output conventions.
- `docs/output-layout.md`: work directory, generated artifact directory, cache
  layout, and report files.
- `docs/security-and-privacy.md`: local execution guarantees, network policy,
  redaction, and auditability.
- `docs/testing-strategy.md`: unit, fixture, tool-integration, generated-code,
  and end-to-end tests.

### Performance and Scale

Missing:

- Large repository benchmarks.
- File-list parsing for more enterprise conventions.
- Incremental indexing and stale-chunk removal under large documentation sets.
- Memory and runtime budgets for Verilator XML parsing, plan generation, and
  retrieval.
- Parallel execution policy for module-level analysis, generation, and runs.

Likely tools:

- No mandatory tools.
- Optional profiling tools such as `py-spy` or `cProfile`.

### Distribution

Current state:

- The project builds as a Python package/wheel.

Missing:

- Pilot installation guide for CI runners.
- Optional enterprise container images with EDA tools preinstalled where license
  constraints allow it.
- Compatibility matrix for Linux, macOS development, and WSL.
- Native Windows policy remains deferred.

Likely tools:

- Python build tooling already declared through `hatchling`.
- Docker or Podman if container images become a pilot requirement.

## Software and Tooling Inventory

### Required for Core Development

| Tool | Needed for | Current local status |
| --- | --- | --- |
| Python 3.11, 3.12, or 3.13 | Supported runtime for development and pilot use | Enforced by the CI compatibility matrix |
| `uv` | Environment sync and local command execution | Present: `uv 0.11.17` |
| `cocotb` | Python simulation tests generated by the cocotb backend | Declared in `pyproject.toml` |
| `hatchling` | Package build backend | Declared in `pyproject.toml` build system |

The selected enterprise pilot should still pin one of the tested minor versions
and retain the lockfile-based install gate.

### Required for Current Verilog/SystemVerilog Analysis and Simulation

| Tool | Needed for | Current local status |
| --- | --- | --- |
| `verilator` | `analyze-rtl`, Verilator XML facts, generated HDL lint | Installed in the real-tool CI job |
| `iverilog` | Current cocotb/Icarus run path | Installed in the real-tool CI job |
| `vvp` | Icarus simulation runtime | Installed with `iverilog` and exercised by the golden workflow |

### Required for Current Formal Path

| Tool | Needed for | Current local status |
| --- | --- | --- |
| `sby` | SymbiYosys formal command execution | Pinned source revision installed by hosted CI; local OSS CAD Suite auto-discovered |
| `yosys` | Formal elaboration and proof setup through SymbiYosys | Installed by hosted CI; bundled by local OSS CAD Suite |
| `z3` or compatible SMT solver | `smtbmc` proofs | Installed by hosted CI; bundled by local OSS CAD Suite |
| OSS CAD Suite | Convenient local bundle for `sby`, `yosys`, and solvers | Supported local development path, not required by hosted CI |

### Likely Needed for Backend Expansion

| Tool | Needed for |
| --- | --- |
| GHDL | VHDL syntax checks and VHDL simulation fixtures |
| Verible or svlint | SystemVerilog/UVM syntax and style validation |
| Slang | SystemVerilog parsing and semantic cross-checks |
| Surelog/UHDM | More complete SystemVerilog and elaboration data for difficult designs |
| Questa, VCS, Xcelium, or Riviera-PRO | Enterprise UVM and simulator adapter validation |
| JasperGold, VC Formal, Questa Formal, or similar | Commercial formal adapter validation |

### Likely Needed for Documentation and Retrieval Expansion

| Tool or library | Needed for |
| --- | --- |
| `pdftotext` from Poppler, `pypdf`, or `pdfminer.six` | PDF specification ingestion |
| Local embedding model runtime | Semantic retrieval without network export |
| FAISS, hnswlib, SQLite vector extension, or equivalent | Larger local vector indexes |
| Enterprise-approved model endpoint client | Optional agent-backed requirement extraction and planning |

## Recommended Next Steps

1. Run the completed P0 workflow against the first external pilot and retain the
   fail-closed semantic-feature report as the scope input for P1.
2. Add a generate-heavy external fixture with interfaces/modports and two
   differently specialized instances; use it to define per-instance plan IDs.
3. Generalize ready/valid into declarative protocol schemas and scoreboards
   before generating UVM components.
4. Add CDC/reset-sequencing analysis and formal invariant support before
   claiming multi-domain correctness.
5. Add simulator code/functional coverage ingestion and coverage-gap planning.
6. Version the runner/provider plugin contracts and complete the operator,
   security, reporting, and scale documentation.
