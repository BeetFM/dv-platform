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
Verilog file-list flags, and emit a dry-run project manifest. Stage 1 remains
open for stricter schema validation and any additional enterprise file-list
conventions found in real repositories.

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

Priorities:

- Make all paths explicit and reproducible.
- Avoid hidden network or tool execution.
- Preserve enough configuration for CI usage.

Exit criteria:

- A user can point the CLI at a repository and inspect what the platform would
  analyze.
- Tests cover config loading, path normalization, and source discovery.

Open decisions:

- Configuration format: TOML is likely best for local CLI ergonomics.
- Whether project config should live in the client repo, the work directory, or
  both.
- How strict to be when no file list is present.

## Stage 2: Verilator AST Extraction and Normalization

Goal: turn Verilator AST output into internal RTL facts that can support
claim-checking.

Deliverables:

- Verilator command builder using configured file lists, include paths, defines,
  and top modules.
- AST artifact storage under the work directory.
- Parser/normalizer for relevant AST facts:
  - modules
  - ports
  - parameters
  - instances
  - hierarchy
  - continuous assignments
  - procedural blocks
  - clocks/resets when inferable
  - assertions and covers
- Stable `EvidenceRef` locators for AST-backed facts.
- `dv-platform analyze-rtl` command implementation.

Priorities:

- Normalize only the facts needed by planning and early generators.
- Keep raw AST files available for debugging.
- Treat inferred clocks/resets as claims with evidence, not unquestioned truth.

Exit criteria:

- The CLI can analyze a small Verilog/SystemVerilog fixture through Verilator.
- Extracted modules become `RTLModule` records with AST evidence refs.
- Tests cover command construction and AST normalization fixtures.

Open decisions:

- Which Verilator AST output format to standardize on.
- Whether to support multiple Verilator versions through compatibility layers.
- How much AST detail to store in internal JSON versus recomputing from raw AST.

## Stage 3: Documentation Ingestion and RAG Indexing

Goal: build a local semantic retrieval path for design intent.

Deliverables:

- Document loader for Markdown and plain text.
- Extension point for PDF-to-text extraction.
- Chunking with stable chunk IDs, source paths, and offsets.
- Embedding provider adapter interface.
- Local vector index adapter interface.
- `dv-platform index-docs` command implementation.
- Retrieval API that returns `DocumentationChunk` plus scores and source refs.

Priorities:

- Keep proprietary docs local by default.
- Make embedding and vector-store providers replaceable.
- Store enough metadata to audit why a requirement or test was generated.

Exit criteria:

- The CLI can index local docs and retrieve chunks for a module/query.
- Tests cover chunking stability and retrieval adapter contracts.
- RAG evidence can be attached to requirements and verification plans.

Open decisions:

- Default local embedding backend.
- Default vector store.
- How to handle very large documentation corpora incrementally.

## Stage 4: Claim Model and Evidence Validation

Goal: make agent conclusions explicit and checkable before generation.

Deliverables:

- Claim types for RTL structure, behavior, documentation intent, planned checks,
  and design recommendations.
- Claim-checker interfaces for AST-backed and documentation-backed evidence.
- Status transitions: unchecked, supported, contradicted, missing evidence.
- Validation policy for generation:
  - critical unsupported claims block generation
  - lower-confidence claims are emitted with warnings
  - missing documentation produces open questions
- Human-readable and JSON claim reports.

Priorities:

- Prefer conservative behavior over confident unsupported generation.
- Keep claim status deterministic and explainable.
- Make unsupported assumptions visible in CLI output.

Exit criteria:

- Verification plans include claims and evidence refs.
- Tests cover supported, contradicted, missing-evidence, and unchecked cases.
- The CLI can emit a claim report for a small fixture.

Open decisions:

- Severity thresholds for blocking generation.
- Whether claim contradiction requires exact evidence mismatch or can use
  heuristic conflict detection.

## Stage 5: Verification Planning

Goal: produce evidence-backed module-level verification plans.

Deliverables:

- Requirement synthesis from retrieved documentation chunks.
- Module plan generator using AST facts, documentation chunks, and claim status.
- Plan schema with checks, assumptions, open questions, targets, and evidence.
- Target selection for cocotb, SystemVerilog, UVM, VHDL, Verilog, and formal.
- `dv-platform plan` command implementation.

Priorities:

- Start with deterministic planning rules before introducing complex agents.
- Make missing intent explicit.
- Keep plans stable enough for review and regression tests.

Exit criteria:

- A small RTL fixture plus docs produces a readable and machine-readable plan.
- Plans cite both AST evidence and documentation chunks where available.
- Tests cover clock/reset checks, combinational modules, and missing docs.

Open decisions:

- Plan output format and file layout.
- Whether plans are regenerated wholesale or patched incrementally.

## Stage 6: Cocotb Generation and Execution Loop

Goal: deliver the first executable generated verification workflow.

Deliverables:

- cocotb generator backend.
- Generated tests for clock/reset bring-up and simple IO connectivity.
- Simulator configuration adapter.
- `dv-platform generate --target cocotb`.
- `dv-platform run` for configured cocotb simulations.
- Failure summary and feedback into plans.

Priorities:

- Generate small, readable tests.
- Keep generated code traceable to plan items and evidence.
- Validate generated Python before writing or running.

Exit criteria:

- Generated cocotb tests run on a fixture design.
- Failures are summarized with source plan and evidence context.
- Tests cover generator output shape and run command construction.

Open decisions:

- Simulator defaults.
- Output directory layout for generated tests and Makefiles/scripts.

## Stage 7: Formal and Native HDL Test Bench Generation

Goal: expand from cocotb into formal and native HDL collateral.

Deliverables:

- Formal harness/assertion generator.
- SystemVerilog test bench generator.
- Verilog test bench generator.
- VHDL test bench generator.
- Initial UVM environment generator for module-level agents.
- Tool-specific run script adapters.

Priorities:

- Formal generation should be conservative and assumption-aware.
- UVM generation should wait until reusable agent boundaries are clear.
- Backends should share plan/evidence inputs but own language-specific emitted
  code.

Exit criteria:

- Each backend can generate at least one fixture artifact.
- Generated artifacts include provenance refs.
- Syntax or lint checks run where tools are configured.

Open decisions:

- First supported formal tool.
- Minimum useful UVM output shape.
- How much test bench style customization belongs in config.

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

Open decisions:

- Report format for enterprise integration: JSON, Markdown, SARIF, or all three.
- Whether low-confidence recommendations should be hidden by default.

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

Open decisions:

- Plugin model for customer-specific tools and style guides.
- Supported operating systems and Python versions.
- Whether to ship as wheel, container, standalone binary, or all three.

## Additional Documentation Needed

These documents should be added as the implementation becomes concrete:

- `docs/cli.md`: command reference, configuration format, exit codes, and
  examples.
- `docs/configuration.md`: local project config schema and enterprise policy
  settings.
- `docs/evidence-model.md`: claim types, evidence refs, status transitions, and
  blocking policy.
- `docs/verilator-ast.md`: Verilator invocation, AST normalization, supported
  facts, and version compatibility.
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
- `docs/adr/`: architecture decision records for major irreversible choices.
