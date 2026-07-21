# Veriforge: Agentic Digital Verification Generation Platform

This repository implements a deterministic, local-first RTL verification
platform with optional evidence-bounded AI augmentation. Given normalized RTL
facts plus design documentation, it produces verification assets and engineering
feedback, but target depth is not uniform:

- cocotb Python test benches
- SystemVerilog assertions and a conservative bench
- UVM, VHDL, and Verilog scaffolds that remain fail-closed until qualified
- formal verification harnesses and properties
- per-module and per-submodule design decision notes

The exact supported/partial/scaffold/unsupported boundary is maintained in the
[Capability Matrix](docs/capability-matrix.md). The platform is intended to integrate directly into enterprise engineering
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
- `RTLModule`: module-level ports, elaborated parameters, memories, hierarchy
  connections, control domains, protocols, and documentation evidence.
- `VerificationPlan`: generated strategy for simulation and formal work.
- `VerificationScenario`: typed stimulus, oracle, bounded completion, coverage,
  target support, and requirement/check/evidence links.
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

Create the project-local uv environment, including development quality tools:

```bash
uv sync --all-groups --frozen
```

Run tests through the uv environment:

```bash
uv run python -m unittest discover -s tests
```

Run the complete local P0 quality gate:

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv run coverage json -o .dv-platform/python-coverage.json
uv run python scripts/check_branch_coverage.py .dv-platform/python-coverage.json
uv build --out-dir .dv-platform/package-check
uv run pip-audit --skip-editable
```

The ratchet policy in `coverage-ratchet.json` enforces 84% combined coverage,
75% true branch coverage globally, at least 50% branch coverage for every
branch-bearing source file, and higher floors for critical planning, scenario,
revision, coverage, generation, and run modules.

The full local workflow uses host EDA tools in addition to Python packages:
`verilator` for RTL fact extraction, `iverilog` for the Icarus/cocotb path, and
`sby`, `yosys`, plus an SMT solver such as `z3` for formal runs. Real-tool tests
skip locally when their executables are unavailable; hosted CI makes the
simulation and formal pilots mandatory. See
[Installation](docs/config/installation.md) for setup details, including OSS
CAD Suite usage for SymbiYosys.

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
  --top-module top \
  --parameter WIDTH=12
```

`--parameter NAME=VALUE` is repeatable and accepts validated two-state
SystemVerilog integer elaboration overrides. Values are recorded in facts,
plans, generated DUT instances, execution manifests, and cocotb builds.

For explicit parameter elaboration points, use one `--parameter-sweep` per
point during initialization. Each point is analyzed in an isolated work
directory and receives a unique sweep-qualified identity:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo init \
  --rtl-filelist rtl/files.f \
  --top-module top \
  --parameter-sweep WIDTH=8,DEPTH=2 \
  --parameter-sweep WIDTH=16,DEPTH=4
```

Sweep points are intentionally explicit; the platform does not infer a
Cartesian product. `parameter_sweeps` and `parameter_overrides` cannot be used
together.

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

Optionally augment deterministic plans with a bring-your-own-key LiteLLM model.
AI planning is additive: invalid or unavailable model output falls back to the
unchanged deterministic module plan, and generation still uses the normal claim
gates.

```bash
uv sync --extra ai
export ANTHROPIC_API_KEY=...
uv run dv-platform --repo-root /path/to/rtl-repo plan --ai \
  --module top --target cocotb
```

AI requests can disclose bounded RTL snippets and retrieved documentation to
the configured endpoint. They require both explicit `plan --ai` and
`policy.allow_network = true`; a validated cache hit may be reused offline.
Planning and feedback use the same bounded LiteLLM gateway. Scenario synthesis
is reserved but inactive; AI cannot create renderers or verification source.

Generate cocotb collateral from stored plans:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo generate \
  --target cocotb
```

Plan schema v17 records target-specific scenario state. A scenario is
`executable` only when a renderer, semantic validator, trace mapper, and result
decoder are registered; older v16 mappings load as unsupported until re-planned.

Feedback can consume persisted run summaries and optionally request a bounded,
additive AI candidate. Accepted operations are stored as immutable plan snapshots;
generation by revision reads the selected snapshot rather than the canonical plan.

```bash
uv run dv-platform --repo-root /path/to/rtl-repo feedback \
  --module top --from-runs --ai --dry-run
uv run dv-platform --repo-root /path/to/rtl-repo generate \
  --target cocotb --revision rev-...
```

Generate formal collateral from stored plans:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo generate \
  --target formal
```

CDC formal generation defaults to `--cdc-policy fail-closed`. Use
`--cdc-policy bounded --cdc-bmc-depth 20` for an explicitly non-closing external
latency check, or `--cdc-policy structural` when every synchronizer stage is
exposed as a formal output and must receive an unbounded stage-by-stage proof.

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

Import and gate simulator or functional coverage reports:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo coverage \
  --input build/coverage.info \
  --input build/functional-coverage.json
```

Supported inputs are LCOV, JSON, and Cobertura-style XML. Configure line,
branch, toggle, or functional thresholds in `dv-platform.toml`; imported results
then participate in `status --policy ci`.

## Documentation

- [Architecture](docs/architecture.md): system boundary, workflow, evidence
  model, CLI expectations, Verilator AST claim-checking, and documentation RAG.
- [Capability Matrix](docs/capability-matrix.md): truthful target, protocol,
  execution-evidence, AI, and revision support levels.
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
- [Missing Work and Tooling Inventory](docs/missing-work.md): implementation
  gaps, pilot-readiness work, and software/tool dependencies still needed.
- [P0 Pilot Acceptance](docs/pilot-acceptance.md): golden workflow, enforced
  correctness guarantees, quality commands, and the remaining product boundary.
- [P1 Expansion Acceptance](docs/p1-acceptance.md): specialization-aware
  semantics, per-check closure, PDF/coverage/UVM expansion, and operational
  acceptance.
- [Implementation Plan](docs/implementation-plan.md): staged delivery plan,
  priorities, decisions, and exit criteria for future implementation agents.
- [Architecture Decision Records](docs/adr/README.md): accepted decisions for
  configuration, evidence, retrieval, planning, generation, and enterprise
  hardening.

## Post-P1 Roadmap

1. Complete and mutation-qualify the APB4 open-tool vertical slice.
2. Complete the bounded one-outstanding-read/write AXI4-Lite slice.
3. Close dependency-based feedback regeneration and mandatory rerun evidence.
4. Qualify UVM in one licensed simulator and deepen VHDL-first semantics.
5. Complete remaining adapter hooks, plugin trust/export governance, full
   dependency-graph incrementality, and repository-scale benchmarks.

The prioritized evidence behind this roadmap is maintained in
[Missing Work and Tooling Inventory](docs/missing-work.md).
