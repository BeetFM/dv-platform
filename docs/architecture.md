# Architecture

## Product Boundary

The platform accepts an RTL repository and design documentation, then produces
verification collateral and design feedback. It should support exploratory use
on incomplete designs and stricter use in continuous integration.

The primary deployment target is a local CLI installed inside enterprise
engineering environments. By default, the CLI should read source repositories,
build retrieval indexes, run RTL tools, generate collateral, and store logs
without moving proprietary design material outside the client-controlled
environment.

Inputs:

- RTL sources: SystemVerilog, Verilog, and VHDL.
- Documentation: Markdown, text, PDFs converted to text, specifications, and
  module notes.
- Build metadata: file lists, simulator configuration, defines, include paths,
  constraints, and target top modules.
- Local policy/configuration: allowed tools, output roots, model endpoints,
  retrieval settings, and privacy/export controls.

Outputs:

- Generated cocotb test benches.
- Generated SystemVerilog, UVM, VHDL, and Verilog verification code.
- Formal harnesses, assumptions, assertions, covers, and run scripts.
- Verification plans and coverage intent.
- Design decision reports with module-scoped recommendations.

## Agent Workflow

The platform should use agents as specialized workers around a deterministic
core. The core owns data models, provenance, artifact routing, and validation.

1. Repository ingestion
   - Build a source inventory.
   - Detect HDL languages, file lists, packages, include paths, and top modules.
   - Preserve provenance for every source and documentation excerpt.

2. RTL analysis
   - For Verilog/SystemVerilog, invoke Verilator and consume its AST output as
     the primary structural source of truth.
   - Extract module/entity names, elaborated parameters/generics, ports,
     memories, clocks, resets, block-level control domains, interfaces,
     structured child connections, recognized protocols, and hierarchy.
   - Identify observable behaviors from code structure and documentation.

3. Documentation retrieval
   - Chunk design documentation and attach stable source identifiers.
   - Build a local semantic retrieval index for RAG.
   - Retrieve relevant documentation chunks for each module, interface, and
     behavior under analysis.

4. Claim-checking
   - Represent agent conclusions as claims.
   - Check RTL claims against Verilator AST evidence.
   - Check intent claims against retrieved documentation chunks.
   - Mark claims as supported, contradicted, missing evidence, or unchecked.

5. Requirement synthesis
   - Convert retrieved design documentation into structured requirements.
   - Link requirements to modules, interfaces, registers, transactions, and
     error cases.

6. Verification planning
   - Decide which behaviors need simulation tests, formal properties, or both.
   - Emit a plan with target languages, tool assumptions, missing information,
     and expected checks.
   - Attach claim-check and RAG evidence to every planned check.

7. Artifact generation
   - Generate language-specific test benches through backend adapters.
   - Keep generated files traceable to plan items and source requirements.
   - Bind executable files to the exact analyzed RTL input hashes through a
     per-module execution manifest.

8. Execution and feedback
   - Run available simulators/formal tools when configured.
   - Summarize failures, coverage gaps, and regeneration opportunities.
   - Expand generated traces into pass/fail/unexecuted outcomes per mapped
     check ID, then link failures through requirements, claims, behaviors, and
     evidence.

9. Design review
   - Produce per-module and per-submodule design decisions.
   - Classify recommendations by severity, confidence, and affected system
     concern such as timing, reset strategy, CDC, configurability, or area.

## Core Principles

- Python is the orchestration language.
- The enterprise integration surface is a local CLI first, with other
  integrations layered on top.
- Verilator AST evidence is the source of truth for Verilog/SystemVerilog
  structural claims.
- Documentation-derived intent must come through semantic retrieval with
  source-backed chunks.
- Generated HDL should be backend-owned, not hand-assembled in planner code.
- Every artifact should carry provenance back to the requirement or source that
  caused it to exist.
- Executable compilation must consume a validated source manifest rather than
  rediscovering or guessing its input set at run time.
- Agent output must be validated by deterministic checks before writing files.
- Missing design intent should be represented explicitly instead of guessed
  silently.

## Local CLI

The CLI should be suitable for enterprise use:

- Runs inside the client repository or CI worker.
- Accepts explicit source, documentation, output, and configuration paths.
- Supports offline/local model and embedding endpoints when required.
- Keeps generated indexes and artifacts under client-selected output roots.
- Emits machine-readable reports for CI and human-readable summaries for local
  review.
- Avoids hidden network access; network behavior should be configured and
  auditable.

Initial commands:

| Command | Purpose |
| --- | --- |
| `init` | Create a local project configuration file. |
| `index-docs` | Build or refresh the semantic documentation index. |
| `analyze-rtl` | Run RTL ingestion and Verilator AST extraction. |
| `plan` | Generate module verification plans with evidence references. |
| `generate` | Emit selected verification collateral. |
| `run` | Execute configured simulation/formal tools. |
| `coverage` | Import, merge, report, and gate local coverage reports. |
| `review` | Produce design decision reports. |
| `status` | Report schema/tool/pipeline/coverage state and enforce CI policy. |

## Claim-Check With Verilator AST

For Verilog/SystemVerilog, the platform should not rely on approximate text
parsing when a Verilator AST is available. The intended flow is:

1. Invoke Verilator with the enterprise project's include paths, defines, file
   lists, and top module settings.
2. Persist the AST output under the local work directory.
3. Normalize AST nodes into stable internal facts such as modules, ports,
   elaborated parameters, memory shape, original/specialized instances and port
   connections, assignments, always blocks, control domains, recognized
   protocols, assertions, and hierarchy.
4. Convert agent conclusions into `VerificationClaim` records.
5. Resolve each RTL claim to one or more AST-backed `EvidenceRef` records.
6. Block or downgrade generated artifacts whose critical claims are unsupported.

## Documentation RAG

Documentation inputs should be handled through semantic retrieval:

1. Load documentation from configured paths.
2. Chunk documents with stable IDs and source offsets.
3. Embed chunks using the configured local or enterprise-approved provider.
4. Store vectors in a local index under the work directory.
5. Retrieve chunks by module, signal, register, interface, behavior, and failure
   mode.
6. Attach retrieved chunk IDs to requirements, verification plans, generated
   artifacts, and design decision reports.

## Generation Targets

The initial target matrix:

| Target | Purpose |
| --- | --- |
| `cocotb` | Python-driven simulation tests and quick bring-up. |
| `systemverilog` | Native SystemVerilog test benches and assertions. |
| `uvm` | Scalable constrained-random environments and reusable agents. |
| `vhdl` | Native VHDL test benches for VHDL-first projects. |
| `verilog` | Simple legacy-compatible test benches. |
| `formal` | Harnesses, assumptions, assertions, covers, and scripts. |

## Early Non-Goals

- Replacing human verification planning.
- Guaranteeing completeness without executable feedback.
- Assuming a single simulator or formal tool.
- Committing to one LLM or agent framework in core data structures.
