# Missing Work and Tooling Inventory

This document tracks what is still missing before the platform is ready for a
real enterprise pilot. It is intentionally more operational than the staged
implementation plan: each section describes the current capability, the gap, and
the software or external tools likely needed to close it.

Snapshot date: 2026-06-26.

## Current Baseline

Implemented and passing in the current repository:

- Local CLI commands: `init`, `index-docs`, `analyze-rtl`, `plan`, `generate`,
  `run`, `review`, and `status`.
- Local TOML configuration and deterministic project discovery.
- Verilator XML invocation, raw artifact/log storage, and initial normalized RTL
  facts.
- Documentation loading for Markdown, text, and reStructuredText.
- Local deterministic chunk index plus local hash-vector retrieval fallback.
- Evidence refs, claim statuses, claim gates, JSON/Markdown claim reports.
- SQLite-backed plan storage with Markdown plan views.
- Initial cocotb generation and Icarus/cocotb execution flow.
- Initial SymbiYosys-oriented formal harness generation and formal run flow.
- Conservative SystemVerilog, Verilog, VHDL, and UVM scaffold generators.
- Design review reports backed by RTL facts and failed run summaries.
- Status command for schema compatibility, generated quality metadata, run
  summaries, and configured tool availability.

Current local test status:

- `uv run python -m unittest discover -s tests` passes.
- The current checkout has no generated project state by default; `status`
  reports missing RTL facts and missing plans until the workflow is run.

## Priority Legend

- `P0`: required before a credible pilot repository workflow.
- `P1`: required before broad internal adoption.
- `P2`: useful hardening or expansion after the first pilot path is stable.

## P0 Missing Work

### End-to-End Pilot Workflow

Current state:

- Unit and fixture tests cover many isolated behaviors.
- The CLI can execute the intended command chain when inputs and tools are
  configured.

Missing:

- A realistic golden RTL repository or fixture that exercises the full workflow:
  `init -> analyze-rtl -> index-docs -> plan -> generate -> run -> review ->
  status --policy ci`.
- Regression assertions over generated files, run summaries, review findings,
  and repeated-run stability.
- A documented pilot acceptance checklist.

Likely tools:

- Existing open EDA tools: Verilator, Icarus Verilog, SymbiYosys, Yosys, and an
  SMT solver.
- CI runner with those tools installed, preferably through OSS CAD Suite for
  formal coverage.

### RTL Semantic Normalization

Current state:

- Verilator XML normalization extracts modules, ports, parameters, instances,
  assignments, procedural blocks, basic expression trees, assertions, covers,
  and simple reset/increment procedural patterns.
- Clock and reset classification is mostly name-based.

Missing:

- Richer expression and statement semantics for nested conditionals, case
  statements, arithmetic, comparisons, memories, arrays, structs, enums, packed
  types, interfaces, modports, generate blocks, packages, imports, typedefs, and
  parameters.
- Hierarchy elaboration beyond simple instance summaries.
- Source-location coverage for every normalized fact.
- Verilator version compatibility fixtures and adapters.
- Explicit confidence levels for every inferred clock, reset, behavior, and
  interface fact.

Likely tools:

- Verilator, with a documented minimum tested version.
- Additional parser/reference options for cross-checking difficult designs:
  Surelog/UHDM, Slang, or commercial simulator elaboration reports.

### Requirement and Intent Extraction

Current state:

- Documentation chunks are retrieved and converted into simple requirement
  summaries.
- The planner derives basic reset, increment, hold, and connectivity checks from
  deterministic rules.

Missing:

- Structured extraction for protocols, transactions, register behavior, error
  paths, latency, ordering, clock-domain behavior, reset sequencing, performance
  constraints, power states, debug/observability requirements, and coverage
  goals.
- Requirement deduplication, conflict detection, and traceability back to
  precise document locations.
- Open-question generation that is specific enough for RTL owners to answer.
- Requirement quality checks, including stale documentation and undocumented RTL
  behavior.

Likely tools:

- Local or enterprise-approved embedding model.
- Local vector store or SQLite-backed retrieval index.
- Optional local LLM or approved enterprise model endpoint once deterministic
  evidence gates are strong enough.
- PDF text extraction tools for specs that are not available as Markdown/text.

### Executable Generation Quality

Current state:

- Cocotb generation emits executable smoke tests for simple structured plans.
- Formal generation emits initial SymbiYosys harnesses and `.sby` scaffolds.
- Other HDL targets emit conservative scaffolds.

Missing:

- Robust generation for buses, vectors, memories, interfaces, parameters,
  multiple clocks, multiple resets, active-high/active-low reset variants,
  combinational modules, and modules without suffix-based port naming.
- Generated compile/run manifests for every target.
- Syntax/lint validation before writing generated SystemVerilog, Verilog, VHDL,
  UVM, and formal artifacts.
- Target-specific quality gates equivalent to the cocotb/formal gates.
- Style profiles for naming, headers, timescale, reset conventions, simulator
  preferences, UVM verbosity, and output naming.

Likely tools:

- Icarus Verilog and `vvp` for the current cocotb path.
- Verilator lint for SystemVerilog syntax and structural checks.
- GHDL for VHDL syntax and simulation validation.
- Verible, Slang, or svlint for SystemVerilog/UVM syntax and style validation.

### Formal Flow Completion

Current state:

- Formal tool configuration exists.
- Initial SymbiYosys-oriented harnesses and `.sby` files can be generated.
- Formal runs produce command/log/summary state when tools are configured.

Missing:

- Strong assumption generation and assumption validation.
- Property generation beyond reset/increment/hold-like patterns.
- Harnesses that handle parameters, memories, interfaces, multi-clock designs,
  unreachable states, bounded proof depth selection, covers, and liveness-like
  checks.
- Counterexample trace discovery and review output.
- Formal result feedback into plans.

Likely tools:

- `sby`.
- `yosys`.
- `z3`, Boolector, Bitwuzla, or another SymbiYosys-compatible SMT solver.
- OSS CAD Suite is the simplest development path for the open formal stack.

### Run Feedback Loop

Current state:

- Simulation and formal run summaries are persisted.
- Failed runs can appear in design review output.

Missing:

- Automatic mapping from failed testcase/property back to plan checks, claims,
  requirements, and generated source lines.
- Regeneration or repair suggestions based on failed runs.
- Coverage collection and coverage-gap reporting.
- Triage classification for generation bug versus RTL bug versus missing
  requirement.

Likely tools:

- cocotb JUnit output, simulator logs, and waveform/trace artifacts.
- Coverage tooling from configured simulators or formal tools.
- Optional waveform viewers such as GTKWave for manual debugging, though not a
  core dependency.

## P1 Missing Work

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

Missing:

- Input hashing and invalidation across RTL facts, documentation chunks,
  vectors, plans, generated artifacts, runs, and review reports.
- Tool-version tracking beyond initial Verilator recording.
- Rebuild policies for partial versus full regeneration.
- Reproducibility checks across repeated runs on unchanged inputs.

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
- Pilot workflow guide using a realistic fixture repository.

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
| Python 3.11 or 3.12 | Primary supported runtime for development and pilot use | Available through project environment |
| `uv` | Environment sync and local command execution | Present: `uv 0.11.17` |
| `cocotb` | Python simulation tests generated by the cocotb backend | Declared in `pyproject.toml` |
| `hatchling` | Package build backend | Declared in `pyproject.toml` build system |

The package metadata currently allows Python 3.13 as well. Pilot support should
explicitly test the Python versions used by target enterprise environments.

### Required for Current Verilog/SystemVerilog Analysis and Simulation

| Tool | Needed for | Current local status |
| --- | --- | --- |
| `verilator` | `analyze-rtl`, Verilator XML facts, optional lint checks | Present: Verilator 5.020 |
| `iverilog` | Current cocotb/Icarus run path | Present: Icarus Verilog 12.0 |
| `vvp` | Icarus simulation runtime | Usually installed with `iverilog`; should be checked in CI |

### Required for Current Formal Path

| Tool | Needed for | Current local status |
| --- | --- | --- |
| `sby` | SymbiYosys formal command execution | Missing from `PATH` |
| `yosys` | Formal elaboration and proof setup through SymbiYosys | Missing from `PATH` |
| `z3` or compatible SMT solver | `smtbmc` proofs | Missing from `PATH` |
| OSS CAD Suite | Convenient bundle for `sby`, `yosys`, and solvers | Not detected on `PATH` |

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

## Immediate Next Steps

1. Install or expose the formal stack: `sby`, `yosys`, and `z3` or use OSS CAD
   Suite.
2. Add a realistic golden pilot fixture and make the full CLI workflow pass in
   CI.
3. Expand RTL normalization fixtures before adding more generator logic.
4. Tighten generation quality gates for all backends, starting with
   SystemVerilog and formal.
5. Add the missing operator docs for CLI usage, output layout, generation
   backends, retrieval, security, and testing strategy.
