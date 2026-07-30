# Product and Interface Guide

Document type: consolidated current and historical documentation.

Purpose: Current product boundary, installation, configuration, CLI, generated state, and public workflow.

Status: current index and preserved source material. Where a historical
section conflicts with current machine evidence, use the authority order in
[Agent and Documentation Governance](agents.md).

Last consolidated: 2026-07-30.

## Current profile-selection overlay

Legacy defaults and trace identities remain unchanged. The following
extensions are selected only by their explicit profile IDs:

- `axi4-lite-two-outstanding-1.0`: up to two ordered reads and writes with
  unique sequence keys.
- `ahb-lite-incr4-1.0`: exactly four incrementing beats, including wait,
  error, and reset-interruption handling.
- `apb5-pwakeup-1.0`: explicitly mapped `PWAKEUP` behavior through setup,
  access, wait, and reset.
- UART `fractional_baud_8bit`: bounded numerator/denominator accumulation with
  unchanged 8-bit framing.
- I2C `bounded_10bit_master`: standard 10-bit prefix, second address byte, and
  repeated-start read sequence.
- SPI `bounded_dual_1_2_2_master`: explicit IO0/IO1 direction, framing,
  bit-order, and mode behavior.

Unselected extensions are never inferred from signal names.

## Source coverage

Every source below is included in full under a stable migration anchor:

- [`README.md`](#source-readmemd)
- [`docs/config/installation.md`](#source-docsconfiginstallationmd)
- [`docs/config/configuration.md`](#source-docsconfigconfigurationmd)
- [`docs/config/cli-contract.md`](#source-docsconfigcli-contractmd)

<a id="source-readmemd"></a>
## Veriforge: Agentic Digital Verification Generation Platform

Consolidated from `README.md`.

This repository implements a deterministic, local-first RTL verification
platform with optional evidence-bounded AI augmentation. Given normalized RTL
facts plus design documentation, it produces verification assets and engineering
feedback, but target depth is not uniform:

- cocotb Python test benches
- SystemVerilog and Verilog benches with a qualified native reset-result slice
- GHDL-authoritative VHDL normalization and executable protocol/reset paths
- multi-agent UVM environments, RAL, and portable licensed-simulator qualification bundles
- formal verification harnesses and properties
- per-module and per-submodule design decision notes

The exact supported/partial/scaffold/unsupported boundary is maintained in the
[Capability Matrix](verification.md#source-docsqualificationcapability-matrixmd). The platform is intended to integrate directly into enterprise engineering
environments as a local CLI tool. Source code, design documentation, retrieval
indexes, generated artifacts, and execution logs should remain inside the
client-controlled environment by default.

The goal is not just code generation. The platform should understand the design
intent well enough to produce useful tests, identify unverified behavior, and
surface implementation decisions that may be mismatched with the larger system.

<a id="source-readmemd--initial-architecture"></a>
### Initial Architecture

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

<a id="source-readmemd--repository-layout"></a>
### Repository Layout

```text
docs/
  architecture.md        Platform architecture and planned agent workflow.
  implementation-plan.md Staged implementation plan and priority decisions.
src/dv_platform/
  domain/                Stable RTL, planning, artifact, and config vocabulary.
  infrastructure/        Filesystem, process, security, sandbox, and plugins.
  configuration/         Config loading, normalization, and validation.
  rtl/                   Authoritative HDL frontend contracts and adapters.
  documentation/         Document loading, indexing, and retrieval.
  verification/          Claims, planning, protocols, and scenarios.
  generation/            Validated render contexts and package Jinja templates.
  formal/                Formal collateral and proof-specific behavior.
  execution/             Simulation, coverage, closure, and status.
  ai/                    Optional AI contracts, runtime, and augmentation.
  enterprise/            Governed enterprise adapters and evidence stores.
  cli.py                 Stable local CLI compatibility entry point.
  core/, analysis/,
  generators/, agent/    Stable import compatibility surfaces during extraction.
tests/                   Unit tests for the core platform contracts.
```

<a id="source-readmemd--development"></a>
### Development

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
uv run python scripts/checks/branch_coverage.py .dv-platform/python-coverage.json
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
[Installation](#source-docsconfiginstallationmd) for setup details, including OSS
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
Planning, feedback, and optional scenario-template synthesis use the same
bounded LiteLLM gateway. Synthesis may only select existing deterministic
templates and their declared parameter values; AI cannot create renderers,
verification source, tool commands, waivers, or executable claims.

Generate cocotb collateral from stored plans:

```bash
uv run dv-platform --repo-root /path/to/rtl-repo generate \
  --target cocotb
```

Plan schema v19 records target-specific scenario state. A scenario is
`executable` only when a renderer, semantic validator, trace mapper, and result
decoder are registered; older v16 mappings load as unsupported until re-planned.

Feedback can consume persisted run summaries and optionally request bounded,
additive AI candidates. Revision schema v3 binds the canonical plan, RTL project
manifest, parent snapshot, affected dependency set, scenario-template selections,
and required rerun targets. Generation by revision updates only affected artifacts.
`status --policy ci` remains open until provenance-matched reruns have been fed
back through `coverage --from-runs`.

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

<a id="source-readmemd--documentation"></a>
### Documentation

- [Documentation Index](README.md): audience-specific entry points,
  authority order, document classes, and the required documentation checks.
- [Agent Execution Guide](agents.md#source-docsagent-execution-guidemd): mandatory repository
  starting state, issue pickup, implementation sequence, test commands, stop
  conditions, and handoff format for coding agents.
- [Documentation Contract](agents.md#source-docsdocumentation-contractmd): required metadata,
  capability vocabulary, evidence rules, edge-case coverage, contradiction
  handling, and reusable authoring templates.
- [Current Missing Work](roadmap.md#source-docsplanningmissing-workmd): P0 regressions,
  dependency-aware issue queue, source ownership, technical implementation
  playbooks, and completion evidence. This is the current issue-state
  authority.
- [Architecture](architecture.md#source-docsarchitecturearchitecturemd): system boundary, workflow, evidence
  model, CLI expectations, Verilator AST claim-checking, and documentation RAG.
- [Refactor compatibility contract](architecture.md#source-docscompatibilitycontractmd): normalized
  import, CLI, schema, entry-point, and generated-artifact fingerprints.
- [Capability Matrix](verification.md#source-docsqualificationcapability-matrixmd): truthful target, protocol,
  execution-evidence, AI, and revision support levels.
- [Configuration](#source-docsconfigconfigurationmd): local `dv-platform.toml` schema,
  path policy, strict/CI behavior, and generated state layout.
- [CLI Contract](#source-docsconfigcli-contractmd): JSON output envelopes, error
  codes, generated machine-state files, and CI usage.
- [Installation](#source-docsconfiginstallationmd): Python package install plus required
  system tools such as Verilator and Icarus Verilog.
- [Verilator AST Extraction](architecture.md#source-docsarchitectureverilator-astmd): XML invocation, stored
  artifacts, normalized RTL facts, and evidence locator policy.
- [Evidence and Claim Model](architecture.md#source-docsarchitectureevidence-modelmd): claim statuses, evidence
  references, validation policy, generation gating, and reports.
- [P0 Pilot Acceptance](verification.md#source-docsacceptancepilot-acceptancemd): golden workflow, enforced
  correctness guarantees, quality commands, and the remaining product boundary
  at its historical snapshot.
- [P1 Expansion Acceptance](verification.md#source-docsacceptancep1-acceptancemd): specialization-aware
  semantics, per-check closure, PDF/coverage/UVM expansion, and operational
  acceptance.
- [Bounded APB4 Acceptance](verification.md#source-docsacceptanceapb4-acceptancemd): generated open-tool
  protocol/register qualification and mutation boundary.
- [Protocol Profile Contract](architecture.md#source-docsarchitectureprotocol-profilesmd): versioned broad-protocol
  transaction semantics and the fail-closed recognition boundary.
- [Bounded AXI4-Lite Acceptance](verification.md#source-docsacceptanceaxi4-lite-acceptancemd): independent
  five-channel bounded qualification, scoreboarding, and mutation boundary.
- [Feedback and Revision Acceptance](verification.md#source-docsacceptancefeedback-revision-acceptancemd):
  immutable revision lineage, affected regeneration, bounded AI selection, and
  mandatory fresh-evidence closure.
- [CDC Synchronizer Acceptance](verification.md#source-docsacceptancecdc-synchronizer-acceptancemd): governed
  pulse, toggle, round-trip handshake, coherent multi-bit payload, and bounded-rate
  Gray-counter structural and mutation qualification.
- [Async FIFO Acceptance](verification.md#source-docsacceptanceasync-fifo-acceptancemd): governed dual-clock
  storage, Gray-pointer, scoreboard, formal-property, and mutation qualification.
- [Reset/RDC Acceptance](verification.md#source-docsacceptancereset-rdc-acceptancemd): governed asynchronous
  assertion, ordered release, dependency synchronization, recovery/removal, and
  mutation qualification.
- [Bounded Memory Depth Acceptance](verification.md#source-docsacceptancememory-depth-acceptancemd): collision,
  byte-enable, two-requester arbitration, zero-initialization, and parity evidence.
- [Bounded Formal Contract Acceptance](verification.md#source-docsacceptanceformal-depth-acceptancemd):
  property-specific assumptions, induction invariants, causal bounded liveness,
  and assumption-consistency evidence.
- [Parameter-Sweep Acceptance](verification.md#source-docsacceptanceparameter-sweep-acceptancemd): isolated
  elaboration points and mandatory semantic cross-point closure.
- [VHDL Normalization Acceptance](verification.md#source-docsacceptancevhdl-normalization-acceptancemd): bounded
  VHDL-only entity, generic, architecture, process, and source-evidence facts.
- [Stage 4 Acceptance](verification.md#source-docsacceptancestage4-acceptancemd): roadmap-to-implementation
  comparison and the explicit boundary of every qualified Stage 4 profile.
- [Stage 5 Acceptance](verification.md#source-docsacceptancestage5-acceptancemd): native result contracts,
  tool ranges, generated-UVM vendor qualification, and adapter connections.
- [Implementation Plan](roadmap.md#source-docsplanningimplementation-planmd): staged delivery plan,
  priorities, decisions, and exit criteria. It is staged design history, not
  current support evidence.
- [Architecture Decision Records](architecture.md#source-docsadrreadmemd): accepted decisions for
  configuration, evidence, retrieval, planning, generation, and enterprise
  hardening.

Current warning: the 2026-07-27 rescan found a SECDED formal regression,
mandatory quality-gate failures, and documentation claim conflicts. Do not
infer a passing release from an older acceptance document or the GA ledger
alone. Resolve current state using the authority order in the
[Agent Execution Guide](agents.md#source-docsagent-execution-guidemd).

<a id="source-readmemd--post-p1-roadmap"></a>
### Post-P1 Roadmap

Bounded APB4 and AXI4-Lite remain backward-compatible qualification profiles.
Versioned broad profiles add AXI4, packet-complete AXI4-Stream, Wishbone B4,
Avalon-MM/ST, burst-capable AHB, and non-coherent TileLink UL/UH with explicit
aliases, transaction models, generated open-tool collateral, UVM contracts, and
fail-closed unsupported semantics. Clean-checkout Ubuntu scale qualification
is complete. Release-candidate promotion remains gated on independently signed
licensed-tool evidence and later enterprise-pilot acceptance.

The prioritized evidence behind this roadmap is maintained in
[Missing Work and Tooling Inventory](roadmap.md#source-docsplanningmissing-workmd).

<a id="source-docsconfiginstallationmd"></a>
## Installation

Consolidated from `docs/config/installation.md`.

The CLI is a Python package, but RTL analysis and simulation also require EDA
executables installed on the host.

<a id="source-docsconfiginstallationmd--python-package"></a>
### Python Package

Create a project-local uv environment and install the CLI package plus Python
dependencies:

```bash
uv sync
```

Run the CLI through the uv environment:

```bash
uv run dv-platform --help
```

The installed package also supports module execution:

```bash
uv run python -m dv_platform --help
```

For direct installation into an isolated environment:

```bash
python -m pip install .
dv-platform --help
```

Python package dependencies are declared in `pyproject.toml`; resolved versions
are locked in `uv.lock`.

The deterministic installation does not include an AI SDK. Install the optional
planning integration only when needed:

```bash
uv sync --extra ai
# or: python -m pip install 'dv-platform[ai]'
```

This installs LiteLLM. Provider API accounts, API billing, and credentials are
bring-your-own; consumer ChatGPT, Claude, or Gemini subscriptions and
interactive OAuth are not used by the CLI.

Live provider smoke tests are opt-in and excluded from standard test runs. Set
`DV_PLATFORM_AI_SMOKE=1` plus one or more model variables such as
`DV_PLATFORM_AI_SMOKE_OPENAI_MODEL`,
`DV_PLATFORM_AI_SMOKE_ANTHROPIC_MODEL`,
`DV_PLATFORM_AI_SMOKE_GEMINI_MODEL`,
`DV_PLATFORM_AI_SMOKE_DEEPSEEK_MODEL`,
`DV_PLATFORM_AI_SMOKE_MOONSHOT_MODEL`, or
`DV_PLATFORM_AI_SMOKE_OLLAMA_MODEL`, then run:

```bash
uv run --extra ai python -m unittest tests.test_ai_smoke
```

<a id="source-docsconfiginstallationmd--system-tools"></a>
### System Tools

Install the current simulation and RTL-analysis dependencies:

```bash
sudo apt-get install verilator iverilog yosys z3
```

Tool usage:

- `verilator`: required for `dv-platform analyze-rtl` to produce Verilator XML
- `slang`: required when `[rtl].semantic_crosscheck` is `report` or `required`;
  the qualified CI pairing is Slang 11 with Verilator 5
  RTL facts.
- `iverilog`: required for the cocotb/Icarus simulation path once generated
  cocotb tests are run.
- `sby`: required for `dv-platform run --target formal`.
- `yosys`: required by SymbiYosys for formal elaboration and proof setup.
- `z3` or another supported SMT solver: required by the SymbiYosys `smtbmc`
  engine.

Many Linux package repositories do not ship a complete, current SymbiYosys
stack. For local development, the OSS CAD Suite provides `sby`, `yosys`, and
SMT solvers in one toolchain. After extracting it, place its `bin` directory on
`PATH` before running formal commands:

```bash
export PATH="$HOME/.local/opt/oss-cad-suite/oss-cad-suite/bin:$PATH"
```

The test suite includes real-tool integration tests:

- The Verilator integration test skips when `verilator` is unavailable.
- The Slang integration test skips locally when either frontend is unavailable.
  Set `DV_PLATFORM_QUALIFIED_SLANG_CI=1` in the qualified job to make both tools
  and a passing strict cross-check mandatory.
- The SymbiYosys integration test skips unless both `sby` and `verilator` are
  available. It checks `PATH` first and then known local OSS CAD Suite
  extraction paths under `$HOME/.local/opt`.

Hosted CI additionally installs a pinned SymbiYosys source revision and treats
the formal integration test as mandatory. The explicit test step prevents a
missing hosted toolchain from being reported as a successful skip.

<a id="source-docsconfiginstallationmd--project-configuration"></a>
### Project Configuration

The default Verilator executable is:

```toml
[rtl]
verilator_executable = "verilator"
slang_executable = "slang"
semantic_crosscheck = "report"
```

For cocotb simulation with Icarus:

```toml
[[simulators]]
target = "cocotb"
name = "icarus"
command = "iverilog"
```

For formal execution with SymbiYosys:

```toml
[[formal_tools]]
name = "symbiyosys"
command = "sby"
```

<a id="source-docsconfigconfigurationmd"></a>
## Configuration

Consolidated from `docs/config/configuration.md`.

The default project configuration file is `dv-platform.toml` in the client
repository root. This file is intended to be reviewed with the RTL project and
used by local runs and CI.

Generated state does not live in the config file location by default. Manifests,
caches, logs, indexes, plan databases, review databases, and run outputs live
under the configured work directory.

See [ADR-0001](architecture.md#source-docsadr0001-local-project-configurationmd) for the accepted
configuration policy.

See [CLI Contract](#source-docsconfigcli-contractmd) for JSON output envelopes, stable error
codes, generated machine-state files, and CI usage.

<a id="source-docsconfigconfigurationmd--example"></a>
### Example

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
slang_executable = "slang"
semantic_crosscheck = "off"

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
allowed_stages = ["planning", "feedback_analysis"]
max_repair_attempts = 2
fallback = "deterministic"

[context_optimization]
stages = ["planning", "feedback_analysis", "scenario_synthesis"]
headroom_endpoint = "http://127.0.0.1:8787"
headroom_timeout_seconds = 5
code_graph_command = "code-review-graph"
code_graph_timeout_seconds = 10
code_graph_max_context_chars = 4000
code_graph_detail_level = "minimal"
code_graph_auto_update = false

[coverage]
line_minimum = 80.0
branch_minimum = 70.0
functional_minimum = 60.0

[execution]
max_parallel_modules = 4
max_process_memory_mb = 768
max_total_process_memory_mb = 4096
max_output_bytes = 1048576

[security]
audit_enabled = true
redact_patterns = ["token=[^ ]+", "LICENSE_KEY=[^ ]+"]
approved_plugin_publishers = ["Acme Verification <security@example.invalid>"]
export_roots = [".dv-platform", "generated/dv-platform"]
secret_provider = "environment"
retention_days = 30

[plugins]
generator_backends = []

[[adapter_plugins]]
kind = "report_exporter"
name = "company_report"
api_version = 1
publisher = "Acme Verification <security@example.invalid>"
package_sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

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

<a id="source-docsconfigconfigurationmd--path-resolution"></a>
### Path Resolution

Relative paths are resolved from `repo_root`, except for an explicit config file
path passed on the command line, which is resolved from the current shell.

Recommended defaults:

- `repo_root = "."`
- `work_dir = ".dv-platform"`
- `output_dir = "generated/dv-platform"`
- `retrieval.index_dir = ".dv-platform/rag-index"`

The CLI should normalize paths before writing manifests so generated outputs are
reproducible and easy to audit.

<a id="source-docsconfigconfigurationmd--sections"></a>
### Sections

<a id="source-docsconfigconfigurationmd--paths"></a>
#### `[paths]`

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

<a id="source-docsconfigconfigurationmd--rtl"></a>
#### `[rtl]`

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
required; no Cartesian product is inferred implicitly. Coverage schema v3
groups canonical check semantics across the configured points and fails closure
when any cross-point is incomplete.

For a VHDL-only project, the same numeric overrides are applied to supported
integer-like generics by the bounded VHDL source normalizer. Verilator is not
invoked. Mixed-language elaboration and required Slang cross-checking fail
closed because those bindings are not qualified.

`top_modules`

Top-level modules or analysis entry points.

`verilator_executable`

Verilator executable name, path, or command prefix for an enterprise wrapper.
Stage 2 standardizes on Verilator XML output from `--xml-only`.

`slang_executable`

Slang executable name, path, or command prefix. It is invoked only when
`semantic_crosscheck` is `report` or `required`, with the same source files,
include paths, defines, tops, and parameter overrides as Verilator.

`semantic_crosscheck`

Independent frontend policy: `off` preserves the Verilator-only workflow,
`report` records disagreements while allowing exploratory runs to continue,
and `required` fails every workflow unless the comparison passes. `report`
becomes enforcing under `--strict` or `--ci`. Enforcing modes also gate `plan`
and `generate` on the latest schema-v2 cross-check artifact.

<a id="source-docsconfigconfigurationmd--retrieval"></a>
#### `[retrieval]`

`index_dir`

Local documentation retrieval index directory. Embedding and vector-store
providers are adapter-backed and must be explicitly configured when used.
Network-backed providers require `policy.allow_network = true`.

<a id="source-docsconfigconfigurationmd--contextoptimization"></a>
#### `[context_optimization]`

AI-context optimizers are always enabled whenever an AI model is configured and
affect only enabled AI stages. They are advisory: deterministic RTL facts, RAG
evidence, schema validation, and merge gates remain authoritative. Missing local
optimizer services fall back outside CI and fail closed under CI.

`headroom_endpoint`

User prompt context is compressed through a local Headroom proxy before LiteLLM
requests. The endpoint must be local HTTP only: `localhost`, `127.0.0.1`, or
`::1`. System prompts and response schemas are not compressed. If compression
fails, times out, returns malformed data, or removes required anchors such as
module names, evidence IDs, schema markers, or untrusted-evidence boundary
tags, the original prompt is used outside CI.

`code_graph_command`

`plan --ai` requests compact source-context hints from a locally installed
`code-review-graph` MCP server. The graph output is capped by
`code_graph_max_context_chars` and added as `code_graph_context` evidence. AI
proposals may cite it, but accepted proposals must still pass the normal
evidence, signal, and deterministic merge checks.

`code_graph_auto_update`

Defaults to `false`; `plan --ai` does not build or mutate `.code-review-graph/`
unless this is explicitly enabled. Operators can run
`dv-platform context-optimize build-graph` or
`dv-platform context-optimize update-graph --base REF` to maintain graph state
outside planning.

Unchanged documentation chunks reuse their existing local vectors during a
refresh.

<a id="source-docsconfigconfigurationmd--policy"></a>
#### `[policy]`

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

<a id="source-docsconfigconfigurationmd--coverage"></a>
#### `[coverage]`

Optional `line_minimum`, `branch_minimum`, `toggle_minimum`, and
`functional_minimum` values are percentages from `0` through `100`. Use
`dv-platform coverage --input <report>` to import one or more LCOV, JSON, or
Cobertura-style XML reports. Configured metrics must be present and meet their
threshold; otherwise the coverage command and CI status fail.

<a id="source-docsconfigconfigurationmd--ai"></a>
#### `[ai]`

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

`allowed_stages` is a non-empty subset of `planning`, `scenario_synthesis`, and
`feedback_analysis`. `max_repair_attempts` is capped at two. The only supported
`fallback` is `deterministic`; automatic cross-provider routing is deliberately
not implemented. When explicitly allowed, `scenario_synthesis` can only select
and parameterize templates already present in the deterministic plan. The default
allowlist contains only planning and feedback analysis.

A live request—including HTTP to a local Ollama server—requires
`policy.allow_network = true`. The request includes normalized RTL facts,
retrieved documentation, the baseline plan, and small repository-contained HDL
snippets. This data may leave the machine. The request occurs only for explicit
`plan --ai` or `feedback --ai`; ordinary planning and feedback remain
deterministic and do not import LiteLLM.
Missing dependencies, credentials, network permission, provider errors, or
invalid output produce a reported per-module deterministic fallback. Valid
offline cache hits remain usable when network permission is disabled.

<a id="source-docsconfigconfigurationmd--execution"></a>
#### `[execution]`

`max_parallel_modules` sets bounded concurrency for `run --all`. The valid
range is 1 through 256 and the default is 1. Single-module execution and output
ordering remain deterministic. Each simulator or formal tool process is also
limited to `max_process_memory_mb` (default 768 MiB), and aggregate fan-out is
bounded by `max_total_process_memory_mb` (default 4096 MiB). Formal runs count
two child solver tasks when calculating safe fan-out. Tool stdout and stderr are
limited to `max_output_bytes` (default 1 MiB) per stream; the retained log marks
when truncation occurred.

<a id="source-docsconfigconfigurationmd--security"></a>
#### `[security]`

`audit_enabled` controls the owner-only JSONL audit file under
`<work-dir>/audit/events.jsonl`. `redact_patterns` is a list of regular
expressions replaced with `[REDACTED]` in persisted tool logs, summaries,
commands, and audit details. Configuration and patterns are trusted local
policy; disable auditing only when the repository's operating policy explicitly
requires it.

`approved_plugin_publishers` is the exact publisher identity allowlist for
third-party adapters. Each third-party `[[adapter_plugins]]` entry must also
provide that publisher and the lowercase SHA-256 of its installed distribution;
both are verified before executable code is imported. Built-in adapters are
bound to the Veriforge distribution. `export_roots` restricts report adapter
destinations after canonical path resolution. `secret_provider` currently
supports only `environment`. `retention_days` is an operator policy value from
1 through 3650; deletion remains an explicit, reviewed deployment operation.

<a id="source-docsconfigconfigurationmd--plugins-and-adapterplugins"></a>
#### `[plugins]` and `[[adapter_plugins]]`

`plugins.generator_backends` explicitly enables generator entry points from
`dv_platform.generators`. Other adapter boundaries are explicit entries with
`kind`, `name`, and `api_version`. They are loaded from
`dv_platform.<kind>` and must report the matching kind and supported API version
before mutating commands proceed. Loading a plugin does not implicitly grant a
capability; concrete subsystems must opt into that adapter contract.
API versions 1 and 2 are accepted. Version 2 additionally requires the adapter
to declare `sandbox_aware = true` and `audit_schema_version = 1`; v1 remains
supported for compatibility through the 1.x line.

<a id="source-docsconfigconfigurationmd--protocolprofiles"></a>
#### `[[protocol_profiles]]`

Profiles declaratively recognize flat `ready_valid` or `req_ack` handshakes.
`valid_suffix` and `ready_suffix` identify the control pair and
`data_suffixes` lists payload candidates in priority order. Direction determines
sink/source role. Ambiguous or incomplete matches do not invent a channel.

Production transaction profiles are separate from these legacy suffix profiles.
Their canonical schema, aliases, bounds, and fail-closed recognition rules are
documented in [Protocol Profile Contract](architecture.md#source-docsarchitectureprotocol-profilesmd).

<a id="source-docsconfigconfigurationmd--parameter-matrices-and-mixed-language-bindings"></a>
#### Parameter matrices and mixed-language bindings

`[rtl.parameter_matrix]` maps parameter names to finite value arrays.
`rtl.parameter_constraints` contains bounded comparison/boolean expressions and
`rtl.max_parameter_points` prevents accidental Cartesian explosion. Expansion
is deterministic and each point retains isolated provenance and coverage.

`rtl.cross_language_bindings` names a
[`cross-language-bindings-v1`](../schemas/rtl/cross-language-bindings-v1.schema.json)
manifest. Every cross-language instance explicitly binds parent/child units,
languages, VHDL architecture/library, ports, and generics. Duplicate,
same-language, or many-to-one bindings fail closed.

<a id="source-docsconfigconfigurationmd--simulators"></a>
#### `[[simulators]]`

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

<a id="source-docsconfigconfigurationmd--formaltools"></a>
#### `[[formal_tools]]`

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

<a id="source-docsconfigconfigurationmd--generated-state"></a>
### Generated State

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

<a id="source-docsconfigconfigurationmd--current-implementation-status"></a>
### Current Implementation Status

All sections documented above are parsed, normalized, validated, and
round-tripped by the current CLI. Built-in API-v1 entry points connect local
document/PDF and governed OCR-sidecar loading, local hash embeddings, JSON
vector storage, deterministic report manifests, regex redaction, UCIS XML,
semantic/requirements imports, and enterprise simulator/formal/analyzer
runners. Site or vendor plugins remain explicit and receive no capability
without normalized result evidence.

<a id="source-docsconfigcli-contractmd"></a>
## CLI Contract

Consolidated from `docs/config/cli-contract.md`.

This document defines the current local CLI contract for human and CI usage.
The CLI remains local-first: source files, documentation chunks, indexes,
normalized RTL facts, generated artifacts, run logs, and reports stay under
configured client-controlled paths.

<a id="source-docsconfigcli-contractmd--output-modes"></a>
### Output Modes

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
- `feedback`
- `status`

Aggregate `run --all` still uses the text output contract and writes an
aggregate summary file under the work directory.

<a id="source-docsconfigcli-contractmd--json-success-envelope"></a>
### JSON Success Envelope

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

<a id="source-docsconfigcli-contractmd--json-error-envelope"></a>
### JSON Error Envelope

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

<a id="source-docsconfigcli-contractmd--current-error-codes"></a>
### Current Error Codes

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
| `mixed_language_normalization_unsupported` | `analyze-rtl` | Verilog/SystemVerilog and VHDL sources were discovered together, but cross-language binding is not qualified. |
| `missing_simulator` | `run` | No simulator is configured for the requested simulation target. |
| `adapter_plugin_error` | mutating commands | An explicitly configured versioned adapter was missing or incompatible. |
| `plugin_load_failed` | `generate` | An explicitly enabled generator plugin was missing or invalid. |
| `simulation_execution_failed` | `run` | Simulator invocation failed before a normal summary could be written. |
| `vhdl_normalization_failed` | `analyze-rtl` | The bounded VHDL source frontend found unsupported or ambiguous entity/generic/architecture semantics. |
| `vhdl_semantic_crosscheck_unsupported` | `analyze-rtl` | Required Slang cross-checking was requested for a VHDL-only input. |
| `status_policy_failed` | `status` | `status --policy ci` found incomplete/incompatible pipeline state, missing or corrupt generated artifacts, failed/missing validation, incomplete/failed runs, or missing required tools. |
| `stale_revision` | `generate` | The selected revision has no immutable snapshot or its stored snapshot hash does not match the revision record. |
| `tool_configuration_error` | `generate`, `run` | Target-specific tool configuration is invalid. |
| `verilator_execution_failed` | `analyze-rtl` | Verilator could not be invoked. |
| `verilator_failed` | `analyze-rtl` | Verilator ran and returned a non-zero exit code. |

<a id="source-docsconfigcli-contractmd--stable-workflow"></a>
### Stable Workflow

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

`feedback --from-runs` reads persisted normalized validation results.
`feedback --ai` permits only evidence-backed additive check or coverage-goal
operations and uses deterministic fallback. `--dry-run` returns the candidate
revision without persisting it. A persisted revision contains a full immutable
plan snapshot; `generate --revision ID` rejects legacy revisions without one.

For CI, use `--ci --json` on commands whose stdout is consumed by automation.
CI implies strict behavior through configuration normalization.

`run --all` uses the same JSON envelope. Its `data` contains the target, ordered
module list, runner identity, per-module status/summary paths, aggregate summary
path, and aggregate return code.

`support-bundle` writes a JSON diagnostic below `<work-dir>/support`. It contains
product/runtime versions, configuration counts and booleans, schema/summary
status, and anonymous log size/SHA-256 records. It never embeds log content or
log paths; operators must still review the bundle before external transfer.

`purge` applies `security.retention_days` only to a fixed transient-state
allowlist. It is a dry run unless `--apply` is present, accepts reproducible
`--as-of` dates, and refuses symlinks. Its JSON result lists exact candidates.

<a id="source-docsconfigcli-contractmd--generated-machine-state"></a>
### Generated Machine State

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
| `<work-dir>/plans/revisions.sqlite` | `feedback` | Append-only revision-v3 records, explicit operation states, input hashes, dependency impact, rerun targets, lineage, and immutable snapshots. |
| `<work-dir>/plans/revision-dependencies/*.json` | `generate --revision` | Typed requirement-to-coverage dependency graph and selected affected closure. |
| `<work-dir>/plans/revision-state/*.json` | `generate --revision` | Required target generation state bound to the resulting provenance hashes. |
| `<work-dir>/plans/modules/*.plan.md` | `plan` | Human-readable plan views. |
| `<work-dir>/plans/claims/*/claims.json` | `plan` | Claim gate reports. |
| `<work-dir>/ai/cache/*.json` | `plan --ai` | Owner-only validated normalized proposals; no raw prompts, responses, or credentials. |
| `<work-dir>/ai/runs/*/*.json` | AI-enabled planning/feedback | Owner-only purpose, endpoint identity, input/output hashes, cache, validation, retry, fallback, token, and cost metadata. |
| `<output-dir>/.../provenance.json` | `generate` | Schema-v2 provenance, quality and tool-validation results, plus artifact SHA-256/size integrity metadata. |
| `<output-dir>/.../execution-manifest.json` | `generate` | Adapter, elaborated parameters, generated file/trace IDs, project-manifest digest, and exact RTL input hashes used by execution. |
| `<work-dir>/runs/**/summary.json` | `run` | Simulation/formal summaries with a common validation-result-v1 envelope and per-check evidence. |
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
independent mapped-check outcomes, failure traceability, backend tool
qualification, triage classification, and repair suggestions. Formal summaries
include separate frontend, Yosys, and solver qualifications, per-task
prove/cover state, and any discovered counterexample trace paths. Native HDL
summaries require exact versioned per-trace records; a successful process alone
is never a check result.

Generation publishes a target/module directory only after deterministic
structure and quality checks complete. SystemVerilog/Verilog generation invokes
Verilator lint, VHDL invokes GHDL when available, cocotb parses generated Python,
and formal validation is deferred to the configured proof run. Runs re-check
provenance and content hashes before invoking any configured tool.

<a id="source-docsconfigcli-contractmd--exit-codes"></a>
### Exit Codes

Current convention:

- `0`: command completed successfully.
- `1`: a simulator completed but executable test results failed validation
  (including failed/zero cocotb testcases or missing/malformed result XML), or
  imported coverage failed a configured threshold.
- `2`: CLI/configuration/input/artifact error.
- `124`: run timeout, when surfaced by simulator/formal execution summaries.
- other non-zero values: propagated tool return codes, especially from
  `analyze-rtl` when Verilator exits non-zero.

<a id="source-docsconfigcli-contractmd--plugin-loading-policy"></a>
### Plugin Loading Policy

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
