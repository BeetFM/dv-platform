# Veriforge: Agentic Digital Verification Generation Platform

This repository is the foundation for an agentic verification platform for RTL
development. Given RTL source plus design documentation, the platform will
produce verification assets and engineering feedback:

- cocotb Python test benches
- SystemVerilog and UVM test benches
- VHDL and Verilog test benches
- formal verification harnesses and properties
- per-module and per-submodule design decision notes

The platform is intended to integrate directly into enterprise engineering
environments as a local CLI tool. Source code, design documentation, retrieval
indexes, generated artifacts, and execution logs should remain inside the
client-controlled environment by default.

The goal is not just code generation. The platform should understand the design
intent well enough to produce useful tests, identify unverified behavior, and
surface implementation decisions that may be mismatched with the larger system.

## Initial Architecture

The first version is organized around a small set of durable concepts:

- `RTLProject`: source files, documentation, top-level modules, constraints, and
  preferred verification targets.
- `RTLModule`: module-level metadata, ports, parameters, clocks, resets, and
  documentation excerpts.
- `VerificationPlan`: generated strategy for simulation and formal work.
- `GeneratedArtifact`: emitted test benches, harnesses, assertions, scripts, and
  reports.
- `DesignDecision`: recommendations or risks tied to a module, submodule, or
  system-level concern.
- `VerificationClaim`: a statement about design intent, RTL behavior, a planned
  check, or a design recommendation.
- `EvidenceRef`: a traceable pointer to either Verilator AST evidence or
  documentation retrieved through RAG.

Generation backends are intentionally pluggable. The Python core should own
analysis, planning, artifact routing, and orchestration. Language-specific
generators should be isolated adapters.

For Verilog/SystemVerilog RTL, the platform should use claim-checking against
the Verilator AST instead of trusting generated natural-language analysis by
itself. Documentation inputs should be indexed for semantic retrieval, with RAG
results attached to requirements, plans, and generated artifacts as evidence.

## Repository Layout

```text
docs/
  architecture.md        Platform architecture and planned agent workflow.
  implementation-plan.md Staged implementation plan and priority decisions.
src/dv_platform/
  cli.py                 Local enterprise CLI entry point.
  core/                  Shared data models and orchestration contracts.
  analysis/              RTL and documentation analysis entry points.
  generators/            Code generation interfaces and target adapters.
tests/                   Unit tests for the core platform contracts.
```

## Development

Create the project-local uv environment:

```bash
uv sync
```

Run tests through the uv environment:

```bash
uv run python -m unittest discover -s tests
```

The full local workflow uses host EDA tools in addition to Python packages:
`verilator` for RTL fact extraction, `iverilog` for the Icarus/cocotb path, and
`sby`, `yosys`, plus an SMT solver such as `z3` for formal runs. The optional
real-tool integration tests skip automatically when those executables are not
available. See [Installation](docs/config/installation.md) for setup details,
including OSS CAD Suite usage for SymbiYosys.

The CLI can be invoked locally with:

```bash
uv run dv-platform --help
```

The package also supports module execution:

```bash
uv run python -m dv_platform --help
```

Initialize a local project configuration:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo init \
  --documentation-path docs \
  --rtl-filelist rtl/files.f \
  --include-path rtl/include \
  --top-module top
```

Inspect the discovered inputs and the Verilator command that would be used in a
future RTL analysis pass:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo analyze-rtl --dry-run
```

Index local design documentation:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo index-docs
```

Generate initial verification plans after RTL facts and documentation chunks are
available:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo plan \
  --target cocotb
```

Generate cocotb collateral from stored plans:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo generate \
  --target cocotb
```

Generate initial formal collateral from stored plans:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo generate \
  --target formal
```

Check configured simulation execution:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo run \
  --target cocotb \
  --module top
```

Run configured formal execution:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo run \
  --target formal \
  --module top
```

Run every generated module for a target:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo run \
  --target cocotb \
  --all
```

## Documentation

- [Architecture](docs/architecture.md): system boundary, workflow, evidence
  model, CLI expectations, Verilator AST claim-checking, and documentation RAG.
- [Configuration](docs/config/configuration.md): local `dv-platform.toml` schema,
  path policy, strict/CI behavior, and generated state layout.
- [CLI Contract](docs/config/cli-contract.md): JSON output envelopes, error
  codes, generated machine-state files, and CI usage.
- [Installation](docs/config/installation.md): Python package install plus required
  system tools such as Verilator and Icarus Verilog.
- [Verilator AST Extraction](docs/verilator-ast.md): XML invocation, stored
  artifacts, normalized RTL facts, and evidence locator policy.
- [Evidence and Claim Model](docs/evidence-model.md): claim statuses, evidence
  references, validation policy, generation gating, and reports.
- [Implementation Plan](docs/implementation-plan.md): staged delivery plan,
  priorities, decisions, and exit criteria for future implementation agents.
- [Architecture Decision Records](docs/adr/README.md): accepted decisions for
  configuration, evidence, retrieval, planning, generation, and enterprise
  hardening.

## Near-Term Roadmap

1. Parse repository manifests and RTL file inventories.
2. Build a local CLI workflow for enterprise repositories.
3. Extract Verilog/SystemVerilog metadata through Verilator AST output.
4. Claim-check RTL-derived assertions against Verilator AST evidence.
5. Index documentation for local semantic retrieval and RAG.
6. Ingest design documentation into structured requirements.
7. Generate a verification plan per module.
8. Emit cocotb smoke tests for clock/reset and simple transaction behavior.
9. Add SystemVerilog/UVM, VHDL, Verilog, and formal generation backends.
10. Run generated tests and feed failures back into planning.
