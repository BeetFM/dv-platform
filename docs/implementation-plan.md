# Implementation Plan

This document breaks the platform into implementation stages so future agents
can make progress without rediscovering product priorities. Each stage should
leave the repository in a working state with tests and documentation updated.

## Guiding Priorities

1. Local enterprise execution first.
   - The CLI is the primary product surface.
   - Source code, documentation, indexes, logs, and generated artifacts stay in
     client-controlled paths by default.
   - Network use must be explicit and auditable.

2. Evidence-backed generation before breadth.
   - Generated verification collateral must trace back to RTL facts,
     documentation chunks, or tool results.
   - Unsupported high-impact claims should block or downgrade generation.

3. Verilator AST for Verilog/SystemVerilog truth.
   - Do not build critical Verilog/SystemVerilog behavior on ad hoc text
     parsing when Verilator AST output is available.
   - Normalize AST output into internal facts before feeding agents or
     generators.

4. Documentation RAG for intent.
   - Requirements and design intent should come from semantic retrieval over
     indexed source documents.
   - Retrieved chunks must carry stable IDs and source locations.

5. Thin core, replaceable adapters.
   - The core owns models, orchestration contracts, validation, and provenance.
   - Tool integrations, vector stores, model providers, and generator backends
     should be adapter boundaries.

## Stage 0: Repository Foundation

Goal: establish the project structure, durable vocabulary, and test harness.

Status: complete.

Deliverables:

- Python package layout under `src/dv_platform`.
- Core models for projects, modules, plans, artifacts, claims, evidence,
  documentation chunks, design decisions, and CLI configuration.
- Generator backend protocol and registry.
- Initial CLI command surface.
- Architecture and implementation planning documentation.
- Unit tests for model and registry contracts.

Exit criteria:

- `PYTHONPATH=src python3 -m unittest discover -s tests` passes.
- README explains how to run tests and inspect the CLI.
- Future stages can add behavior without changing the public vocabulary
  unnecessarily.

Key decisions:

- Use standard-library-only scaffolding until specific dependencies are needed.
- Keep CLI command names stable even while command implementations are stubs.
- Model evidence as structured references, not plain strings.

## Stage 1: Local CLI Configuration and Project Discovery

Goal: make the CLI usable against a real enterprise RTL repository without
requiring generated collateral yet.

Status: started. The CLI can now write and load local TOML configuration,
normalize configured paths, discover HDL and documentation inputs, parse common
Verilog file-list flags, validate input-consuming configuration, and emit a
dry-run project manifest. Stage 1 remains open for additional enterprise
file-list conventions found in real repositories.

Deliverables:

- `dv-platform init` writes a local configuration file. Implemented.
- Config schema for repository root, work directory, output directory,
  documentation paths, RTL file lists, include paths, defines, top modules,
  Verilator executable, retrieval settings, and network policy. Implemented.
- `dv-platform analyze-rtl --dry-run` reports discovered sources and tool
  commands without executing expensive generation. Implemented.
- Deterministic repository inventory for HDL files and documentation files.
  Implemented for configured paths and direct repository walks.
- Machine-readable project manifest under the work directory. Implemented as
  `.dv-platform/project-manifest.json` by default.
- Strict and CI validation for missing RTL file lists and missing configured
  inputs. Implemented for `analyze-rtl --dry-run`.

Priorities:

- Make all paths explicit and reproducible.
- Avoid hidden network or tool execution.
- Preserve enough configuration for CI usage.

Exit criteria:

- A user can point the CLI at a repository and inspect what the platform would
  analyze.
- Tests cover config loading, path normalization, and source discovery.

Decisions:

See [ADR-0001](adr/0001-local-project-configuration.md).

- Configuration format: TOML.
- Project config location: the default config lives in the client repository
  root as `dv-platform.toml`. Generated manifests, caches, logs, indexes, and
  other machine state live under the configured work directory.
- Missing file-list behavior: interactive/local exploratory runs may walk HDL
  files directly and must emit a warning that analysis can be incomplete. CI/CD
  or strict mode must treat missing RTL file lists as an error.

## Stage 2: Verilator AST Extraction and Normalization

Goal: turn Verilator AST output into internal RTL facts that can support
claim-checking.

Status: started. `dv-platform analyze-rtl` can now run the configured Verilator
XML command, record the detected Verilator version, store logs, discover raw XML
artifacts, normalize conservative RTL facts, write normalized RTL facts JSON,
and emit machine-readable failure summaries. Stage 2 remains open for richer
expression/body normalization and version compatibility fixtures.

Deliverables:

- Verilator command builder using configured file lists, include paths, defines,
  and top modules. Implemented.
- AST artifact storage under the work directory. Implemented for raw XML files
  produced in `<work-dir>/verilator` plus stdout/stderr logs.
- Parser/normalizer for relevant AST facts:
  - modules. Initial implementation.
  - ports. Initial implementation.
  - parameters. Initial implementation.
  - instances. Initial implementation.
  - hierarchy. Initial implementation through instance summaries.
  - continuous assignments. Initial summary implementation.
  - procedural blocks. Initial summary implementation.
  - clocks/resets when inferable. Initial name-based implementation.
  - assertions and covers. Initial summary implementation.
- Stable `EvidenceRef` locators for AST-backed facts. Initial fact-level
  implementation with Verilator `fl` source locations when available.
- `dv-platform analyze-rtl` command implementation. Initial implementation.

Priorities:

- Normalize only the facts needed by planning and early generators.
- Keep raw AST files available for debugging.
- Treat inferred clocks/resets as claims with evidence, not unquestioned truth.

Exit criteria:

- The CLI can analyze a small Verilog/SystemVerilog fixture through Verilator.
- Extracted modules become `RTLModule` records with AST evidence refs.
- Tests cover command construction, AST normalization fixtures, and optional
  real-Verilator integration when Verilator is installed.

Decisions:

See [ADR-0002](adr/0002-verilator-xml-evidence.md).

- Verilator AST format: standardize on Verilator XML output generated with
  `--xml-only`. Raw XML artifacts are persisted under the work directory and
  treated as source evidence artifacts for Verilog/SystemVerilog RTL structure.
- Verilator version policy: Stage 2 supports a documented minimum Verilator
  version and records the detected Verilator version with AST artifacts.
  Version-specific compatibility adapters are deferred until fixture evidence
  shows incompatible XML shapes.
- Normalized storage policy: store raw Verilator XML unchanged and write a
  separate normalized RTL facts JSON containing only platform-owned facts needed
  by planning, claim-checking, and early generators. The normalized schema must
  include stable evidence locators back to the raw AST artifact.

## Stage 3: Documentation Ingestion and RAG Indexing

Goal: build a local semantic retrieval path for design intent.

Status: started. The CLI can now discover configured Markdown, plain-text, and
reStructuredText documentation; load and normalize document text; chunk documents
with stable IDs, offsets, and content hashes; write a local JSON chunk index
under the retrieval index directory; perform deterministic lexical retrieval;
and attach retrieved documentation chunks to initial verification plans as
evidence.

Deliverables:

- Document loader for Markdown and plain text. Implemented, including
  reStructuredText.
- Extension point for PDF-to-text extraction.
- Chunking with stable chunk IDs, source paths, offsets, and content hashes.
  Implemented.
- Embedding provider adapter interface.
- Local vector index adapter interface.
- `dv-platform index-docs` command implementation. Initial local JSON index
  implementation.
- Retrieval API that returns `DocumentationChunk` plus scores and source refs.
  Initial lexical retrieval implementation.

Priorities:

- Keep proprietary docs local by default.
- Make embedding and vector-store providers replaceable.
- Store enough metadata to audit why a requirement or test was generated.

Exit criteria:

- The CLI can index local docs and retrieve chunks for a module/query.
  Implemented for lexical retrieval.
- Tests cover chunking stability and retrieval adapter contracts. Implemented
  for the local JSON index.
- RAG evidence can be attached to requirements and verification plans.
  Implemented for initial deterministic plans.

Decisions:

See [ADR-0003](adr/0003-local-first-documentation-retrieval.md).

- Default embedding backend: define an embedding provider interface, but do not
  require a network or heavyweight model by default. Stage 3 starts with
  deterministic document loading, stable chunking, and lexical retrieval as the
  local fallback. Embedding providers must be explicitly configured, and network
  providers require `allow_network = true`.
- Default vector store: use a local file-backed adapter boundary under the work
  directory first. Exact persistence can be JSON, SQLite, or another
  standard-library-friendly local format during implementation, but vector-store
  behavior must remain replaceable behind an adapter.
- Large corpus handling: index incrementally using stable document IDs, chunk
  IDs, content hashes, and deterministic stale-chunk removal. Re-index changed
  documents only, with a future full-rebuild option.
- Vector compression: treat quantized vector storage, including
  TurboQuant-style compression, as an adapter-level optimization. Do not make it
  mandatory or default until baseline retrieval quality fixtures exist and
  compressed retrieval can be compared against uncompressed vectors.

## Stage 4: Claim Model and Evidence Validation

Goal: make agent conclusions explicit and checkable before generation.

Status: started. Claims now carry type, severity, and generation-precondition
metadata. Deterministic AST/documentation evidence checkers, status transition
helpers, generation gating, and JSON/Markdown claim reports are implemented.

Deliverables:

- Claim types for RTL structure, behavior, documentation intent, planned checks,
  and design recommendations. Implemented.
- Claim-checker interfaces for AST-backed and documentation-backed evidence.
  Initial deterministic implementation.
- Status transitions: unchecked, supported, contradicted, missing evidence.
  Implemented.
- Validation policy for generation:
  - critical unsupported claims block generation. Implemented.
  - lower-confidence claims are emitted with warnings. Implemented.
  - missing documentation produces open questions. Implemented in initial
    planning.
- Human-readable and JSON claim reports. Implemented.

Priorities:

- Prefer conservative behavior over confident unsupported generation.
- Keep claim status deterministic and explainable.
- Make unsupported assumptions visible in CLI output.

Exit criteria:

- Verification plans include claims and evidence refs. Implemented for initial
  plans.
- Tests cover supported, contradicted, missing-evidence, and unchecked cases.
  Implemented.
- The CLI can emit a claim report for a small fixture.

Decisions:

See [ADR-0004](adr/0004-claim-validation-gating.md).

- Severity thresholds for blocking generation: critical claims block generation
  when missing evidence, contradicted, or unchecked. High-severity contradicted
  claims block generation; high-severity missing or unchecked claims warn during
  local exploratory use and block in strict/CI mode. Medium claims warn by
  default, but may block when they are explicit generation preconditions. Low
  and info claims are annotated or warned without blocking by default.
- Generation preconditions: claims that directly affect executable generated
  behavior are treated as preconditions. Critical preconditions must be
  supported before generation. Missing documentation intent should produce open
  questions instead of invented requirements.
- Contradiction policy: automatic `contradicted` status requires deterministic
  evidence mismatch. Heuristic or confidence-based conflicts are represented as
  warnings, open questions, or suspected conflicts, and must not automatically
  block generation without explicit evidence.
- Strict/CI mode: strict and CI workflows upgrade high-severity missing or
  unchecked claims to errors while preserving deterministic contradiction
  requirements.

## Stage 5: Verification Planning

Goal: produce evidence-backed module-level verification plans.

Status: started. The CLI can now load normalized RTL facts and the local
documentation index, generate initial deterministic module plans, attach
documentation evidence, evaluate claim gates, write canonical SQLite plan
records, and produce Markdown plan and claim-report views.

Deliverables:

- Requirement synthesis from retrieved documentation chunks. Initial
  implementation.
- Module plan generator using AST facts, documentation chunks, and claim status.
  Initial deterministic implementation.
- Plan schema with checks, assumptions, open questions, targets, and evidence.
  Implemented in the core model and SQLite/Markdown outputs.
- Target selection for cocotb, SystemVerilog, UVM, VHDL, Verilog, and formal.
  Implemented through repeated `--target`.
- `dv-platform plan` command implementation. Initial implementation.

Priorities:

- Start with deterministic planning rules before introducing complex agents.
- Make missing intent explicit.
- Keep plans stable enough for review and regression tests.

Exit criteria:

- A small RTL fixture plus docs produces a readable and machine-readable plan.
  Implemented.
- Plans cite both AST evidence and documentation chunks where available.
  Implemented for initial deterministic plans.
- Tests cover clock/reset checks, combinational modules, and missing docs.
  Implemented for initial planning and CLI workflow coverage.

Decisions:

See [ADR-0005](adr/0005-sqlite-canonical-stores.md).

- Plan output format and file layout: use SQLite as the canonical machine
  store for generated verification plans, with derived Markdown files for human
  review. SQLite is a single local file, efficient for indexed reads and
  partial updates, available through the Python standard library, and suitable
  for CI artifacts. Generators and CI consume the SQLite plan database; humans
  read generated Markdown views.
- Plan storage layout: store canonical plans under
  `<work-dir>/plans/plans.sqlite`, derived review files under
  `<work-dir>/plans/modules/<module>.plan.md`, and a generated summary/index
  view under `<work-dir>/plans/index.md` or equivalent exported report. Avoid
  wall-clock timestamps in canonical plan records unless explicitly needed;
  prefer input hashes, schema versions, and tool versions for reproducibility.
- Regeneration policy: regenerate complete module plans from current normalized
  RTL facts, documentation chunks, and claim state. Do not patch generated
  plans incrementally in Stage 5. Preserve future human edits separately through
  overrides or annotations rather than inside generated plan records.

## Stage 6: Requirements-Driven Simulation Generation and Execution Loop

Goal: deliver the first executable generated simulation workflow while keeping
target selection driven by client requirements and project configuration.

Status: started. The CLI can now generate initial cocotb smoke tests from
stored verification plans, write generated artifacts under the Stage 6 output
layout, emit provenance manifests, run generated cocotb tests through the
cocotb/Icarus runner, validate generated cocotb artifacts before writing or
running them, run every generated module for a target, and persist
command/log/summary run state.

Deliverables:

- Initial simulation generator backend selected by requirements and config.
  Implemented for cocotb.
- Generated simulation tests for clock/reset bring-up and simple IO
  connectivity. Initial cocotb smoke implementation.
- Target-specific simulator configuration adapter. Implemented for cocotb with
  Icarus.
- `dv-platform generate --target <target>`. Implemented for cocotb.
- `dv-platform run` for configured simulation targets. Implemented for cocotb
  module runs and target-level `--all` runs.
- Failure summary and feedback into plans. Initial run summary artifacts
  implemented with result counts, failed testcase names, log tails,
  artifact/provenance paths, and aggregate target summaries; plan mutation
  remains deferred.

Priorities:

- Generate small, readable tests.
- Keep generated code traceable to plan items and evidence.
- Validate generated collateral before writing or running.

Exit criteria:

- Generated simulation tests run on a fixture design. Verified with
  Verilator/Icarus when installed.
- Failures are summarized with source plan and evidence context. Implemented
  in command/log/summary JSON with cocotb result parsing and log tails.
- Tests cover generator output shape and run command construction. Implemented
  for generated artifacts, provenance manifests, missing simulator config,
  validation failures, richer summaries, and aggregate `--all` runs.

Decisions:

See [ADR-0006](adr/0006-requirements-driven-generation-targets.md).

- Target selection policy: generation targets are selected from client
  requirements, verification plans, and project configuration. Cocotb may be
  the first implemented backend because it is fast to validate, but the
  architecture must support cocotb, SystemVerilog, standard Verilog, and UVM
  simulation targets without assuming cocotb as the product direction. Formal
  remains a separate target path because properties, assumptions, and proof
  execution have different validation rules.
- Simulator policy: simulator configuration is target-specific and
  project-specific. If no simulator is configured, `generate` may still emit
  artifacts, but `run` fails with an actionable message. Strict/CI mode
  requires explicit simulator configuration. Lightweight open tools may be used
  as fixture defaults for tests and examples, but no global simulator is
  assumed for client projects.
- Output directory layout: generated simulation source lives under
  `<output-dir>/simulation/<target>/modules/<module>/`. Runtime state, logs,
  temporary build products, and failure summaries live under
  `<work-dir>/runs/simulation/<target>/<module>/`. Each generated
  target/module directory includes a provenance manifest tying files back to
  plan IDs, claim IDs, and evidence refs.

## Stage 7: Formal Generation and Advanced HDL/UVM Backends

Goal: expand from requirements-driven simulation generation into formal
collateral and advanced native HDL/UVM backends.

Status: started. Formal tool configuration is now modeled, loaded from and
written to `[[formal_tools]]`, and checked for strict/CI formal target
generation and execution. The CLI can generate an initial SymbiYosys-oriented
formal harness and `.sby` scaffold with provenance, validate generated formal
artifacts, create a run-local `.sby` from the project manifest, execute the
configured formal tool, and persist command/log/summary run state.

Deliverables:

- Formal tool configuration plumbing. Implemented.
- Formal harness/assertion generator. Initial SymbiYosys-oriented scaffold
  implemented.
- Tool-specific run script adapters. Implemented for initial SymbiYosys command
  execution.
- Advanced SystemVerilog test bench generator.
- Advanced Verilog test bench generator.
- VHDL test bench generator.
- Initial UVM environment generator for module-level agents.

Priorities:

- Formal generation should be conservative and assumption-aware.
- UVM generation should wait until reusable agent boundaries are clear.
- Backends should share plan/evidence inputs but own language-specific emitted
  code.

Exit criteria:

- Each backend can generate at least one fixture artifact. Implemented for
  initial formal generation.
- Generated artifacts include provenance refs. Implemented for initial formal
  generation.
- Syntax or lint checks run where tools are configured. Implemented as initial
  formal tool command execution with run summaries.

Decisions:

See [ADR-0007](adr/0007-formal-uvm-backend-boundaries.md).

- First supported formal tool: SymbiYosys is the first formal tool adapter for
  open fixture validation. Commercial formal tools are added later as adapters.
  Formal generation must emit a harness, assumptions, assertions/covers, `.sby`
  configuration, and a provenance manifest. Client project execution requires
  explicit formal tool configuration, and strict/CI mode requires explicit
  formal tool configuration.
- Minimum useful UVM output shape: UVM generation starts as an evidence-backed
  module-level scaffold only when interface and transaction boundaries are clear.
  A useful scaffold includes package, interface, transaction item when
  inferable or configured, sequencer, driver, monitor, scoreboard stub, env,
  test, top-level harness, compile/run file list, and provenance manifest. If
  transaction semantics are missing, emit a skeletal harness with open questions
  instead of pretending a constrained-random environment is supported. Missing
  transaction intent blocks advanced UVM generation in strict/CI mode.
- Test bench style customization: use declarative style profiles in config for
  naming, reset conventions, clock defaults, timescale, package/module naming,
  output naming, simulator/tool preferences, header/license text, lint/formal
  pragmas, and UVM verbosity defaults. Do not support arbitrary templates or
  code-snippet injection in the core generator initially. Backend adapters own
  emitted code structure; customer-specific generation belongs in future
  plugins or adapters.

## Stage 8: Design Decision Reports

Goal: produce module and submodule recommendations that are useful to RTL
owners.

Deliverables:

- Design decision taxonomy:
  - reset strategy
  - clocking and CDC
  - interface consistency
  - parameterization
  - state encoding
  - error handling
  - observability and debug
  - synthesis/timing risk
  - verification risk
- Evidence-backed `DesignDecision` reports.
- `dv-platform review` command implementation.
- Severity and confidence scoring.

Priorities:

- Recommendations should cite AST facts, docs, or tool results.
- Avoid style-only feedback unless tied to system risk.
- Make confidence explicit.

Exit criteria:

- Reports are generated for fixture modules.
- Each recommendation has scope, rationale, severity, and evidence.
- Tests cover report serialization and evidence requirements.

Decisions:

See [ADR-0005](adr/0005-sqlite-canonical-stores.md).

- Report format for enterprise integration: use SQLite as the canonical report
  store under `<work-dir>/review/review.sqlite`. Generate Markdown as the
  primary human review output. Export YAML and JSON for CI/CD and automation:
  YAML is optimized for human-readable pipeline artifacts and policy review,
  while JSON remains the strict machine/API export. Export SARIF only for
  findings that map cleanly to source locations and rule concepts; do not force
  architecture-level recommendations into SARIF when the mapping is weak.
- Low-confidence recommendations: retain all findings in the canonical SQLite
  store, but hide low-confidence and unknown-confidence findings from default
  Markdown/YAML/JSON reports unless severity is high or critical. High and
  critical findings may surface with lower confidence, but must be clearly
  labeled with confidence and evidence status. Findings without evidence must
  not be presented as firm recommendations.

## Stage 9: Enterprise Hardening

Goal: make the CLI reliable enough for pilot use inside enterprise workflows.

Deliverables:

- Structured logs.
- JSON outputs for CI.
- Exit code policy.
- Cache invalidation for ASTs, docs, embeddings, plans, and artifacts.
- Versioned schemas.
- Redaction/export controls.
- Performance budgets for large repositories.
- Installation documentation.

Priorities:

- Deterministic behavior in CI.
- Clear failure modes.
- No accidental data movement.
- Repeatable generated outputs.

Exit criteria:

- Pilot repository can run `init`, `index-docs`, `analyze-rtl`, `plan`,
  `generate`, `run`, and `review`.
- Outputs are stable across repeated runs with unchanged inputs.
- Failure modes produce actionable CLI messages and machine-readable reports.

Decisions:

See [ADR-0008](adr/0008-enterprise-plugins-platforms-distribution.md).

- Plugin model for customer-specific tools and style guides: use Python package
  entry points first, with plugins explicitly enabled in project config. Core
  defines stable adapter interfaces for generators, simulator/formal runners,
  documentation loaders, embedding providers, vector stores, style profiles,
  and report exporters. Do not auto-load arbitrary repository-local executable
  code by default. Enterprise-local plugins can be distributed internally as
  wheels; a restricted local plugin directory may be considered later only with
  explicit config.
- Supported operating systems and Python versions: Linux is the primary
  supported OS. macOS is supported for local development on a best-effort basis.
  Windows support is through WSL initially; native Windows is not a Stage 9
  target. Python 3.11 and 3.12 are the initial supported versions, with newer
  versions revisited after dependencies and enterprise environments stabilize.
- Distribution model: ship as a Python wheel first. Add optional enterprise
  container images later for reproducible CI runners. Defer standalone binaries
  until pilot feedback shows a concrete need. Containers must not be the only
  supported path because many EDA tools require licensed host integration.

## Additional Documentation Needed

These documents should be added as the implementation becomes concrete:

- `docs/cli.md`: command reference, configuration format, exit codes, and
  examples.
- `docs/configuration.md`: local project config schema and enterprise policy
  settings. Added.
- `docs/evidence-model.md`: claim types, evidence refs, status transitions, and
  blocking policy. Added.
- `docs/verilator-ast.md`: Verilator invocation, AST normalization, supported
  facts, and version compatibility. Added.
- `docs/rag.md`: document loading, chunking, embeddings, vector store adapters,
  retrieval scoring, and privacy expectations.
- `docs/generation-backends.md`: backend interface and language-specific output
  conventions.
- `docs/output-layout.md`: work directory, generated artifact directory, cache
  layout, and report files.
- `docs/security-and-privacy.md`: local execution guarantees, network policy,
  redaction, and auditability.
- `docs/testing-strategy.md`: unit, fixture, tool-integration, generated-code,
  and end-to-end tests.
- `docs/missing-work.md`: implementation gaps, pilot-readiness work, and
  software/tool dependencies still needed. Added.
- `docs/installation.md`: Python package installation and required system
  tools. Added.
- `docs/adr/`: architecture decision records for major irreversible choices.
  Initial accepted ADRs have been added for the stage decisions resolved so far.
