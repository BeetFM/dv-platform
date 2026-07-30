# Roadmap, Missing Work, and Progress

Document type: consolidated current and historical documentation.

Purpose: The complete active backlog, per-feature implementation and validation cards, staged plan, and progress history.

Status: current index and preserved source material. Where a historical
section conflicts with current machine evidence, use the authority order in
[Agent and Documentation Governance](agents.md).

Last consolidated: 2026-07-30.

## Current roadmap authority

The active issue inventory is [Missing Work and Tooling
Inventory](#source-docsplanningmissing-workmd). Its zero-assumption pickup
index and per-ticket cards are the current implementation authority. The
Implementation Plan and Project Progress sections are preserved historical
records and cannot close an active ticket without the evidence required by its
current card.

The 2026-07-30 repository-wide local-work audit supersedes stale pickup states
inside the preserved 2026-07-28 source snapshot. The machine catalog now
classifies all 12 maintained Markdown files and all 70 preserved source
sections, and the local task audit separates completed repository work from
external evidence and owner-decision blockers.

## Current local-work audit

This table is generated from
`qualification/policies/local-task-audit-v1.json`. `completed` means the
repository-owned implementation, tests, schemas, and documentation are
present; it does not promote a capability whose remaining blocker names
external, hosted, protected, licensed, signed, or owner-controlled evidence.

<!-- generated: local-task-audit-v1 -->
| Ticket | Local work | Remaining closure blocker |
| --- | --- | --- |
| `AI-01` | `no_authorized_local_work` | `owner_decision` |
| `AI-02` | `no_authorized_local_work` | `owner_decision` |
| `AI-03` | `completed` | `external_tool_evidence` |
| `BOARD-01` | `no_authorized_local_work` | `owner_decision` |
| `BUG-CDC-01` | `regression_closed` | `none` |
| `CDC-01` | `completed` | `external_tool_evidence` |
| `COV-01` | `completed` | `external_tool_evidence` |
| `COV-02` | `completed` | `external_tool_evidence` |
| `DOC-00` | `completed` | `none` |
| `DOC-01` | `completed` | `none` |
| `DOC-02` | `completed` | `none` |
| `DOC-03` | `completed` | `none` |
| `FORM-01` | `completed` | `external_tool_evidence` |
| `MEM-01` | `completed` | `external_tool_evidence` |
| `PERIPH-01` | `completed` | `external_tool_evidence` |
| `PHYS-01` | `no_authorized_local_work` | `owner_decision` |
| `PLAT-01` | `completed` | `hosted_or_protected_evidence` |
| `PROTO-01` | `completed` | `external_tool_evidence` |
| `PROTO-02` | `completed` | `external_tool_evidence` |
| `QUAL-01` | `regression_closed` | `none` |
| `QUALITY-01` | `regression_closed` | `none` |
| `RDC-01` | `no_authorized_local_work` | `licensed_signed_evidence` |
| `RELEASE-01` | `completed` | `hosted_or_protected_evidence` |
| `SCALE-01` | `completed` | `hosted_or_protected_evidence` |
| `SCALE-02` | `regression_closed` | `none` |
| `SEM-01` | `completed` | `external_tool_evidence` |
| `SEM-02` | `no_authorized_local_work` | `external_tool_evidence` |
| `SEM-03` | `completed` | `none` |
| `TIER-01` | `no_authorized_local_work` | `owner_decision` |
| `TOOL-01` | `completed` | `licensed_signed_evidence` |
| `UVM-01` | `completed` | `licensed_signed_evidence` |
| `VHDL-01` | `completed` | `external_tool_evidence` |
<!-- /generated: local-task-audit-v1 -->

## Source coverage

Every source below is included in full under a stable migration anchor:

- [`docs/planning/README.md`](#source-docsplanningreadmemd)
- [`docs/planning/missing-work.md`](#source-docsplanningmissing-workmd)
- [`docs/planning/implementation-plan.md`](#source-docsplanningimplementation-planmd)
- [`progress.md`](#source-progressmd)

<a id="source-docsplanningreadmemd"></a>
## Planning Index

Consolidated from `docs/planning/README.md`.

Document type: current planning index.

Authority: the classification and precedence described below.

Scope: staged roadmap history and the current implementation backlog.

Status: current.

Last reviewed: 2026-07-27.

<a id="source-docsplanningreadmemd--documents"></a>
### Documents

- [Missing Work](#source-docsplanningmissing-workmd) is the current regression register and
  agent-ready backlog. Its P0 list, dependency-aware pickup index, source
  ownership map, implementation sequence, edge-case policy, and ticket
  playbooks are actionable.
- [Implementation Plan](#source-docsplanningimplementation-planmd) is historical staged design
  context. Its stage labels record intended or accepted progress at a point in
  time and are not current release evidence.

<a id="source-docsplanningreadmemd--agent-procedure"></a>
### Agent procedure

1. Read the repository [Agent Execution Guide](agents.md#source-docsagent-execution-guidemd).
2. Read the current baseline and rescan result in Missing Work.
3. Select one row from the zero-assumption pickup index.
4. Confirm `Ready`, dependencies, required decisions, tool availability, and
   the first reproduction or inspection step.
5. Read the summary ticket and the corresponding technical playbook.
6. Execute the common completion contract and ticket-specific completion
   evidence.
7. Update ticket state, current capability docs, historical links, and exact
   evidence in the same change.
8. Use the handoff template in the Agent Execution Guide.

Do not infer issue completion from roadmap prose, a generated file, a unit test,
or process exit zero. The issue closes only when its bounded evidence and
strict-status requirements are satisfied.

<a id="source-docsplanningreadmemd--adding-work"></a>
### Adding work

Before creating a new ID, search Missing Work for the same ownership boundary.
Extend an existing ticket when the new finding has the same root cause,
dependencies, schema, and completion evidence. Create a new ticket when it has
an independent support-state transition or can be completed separately.

Every new issue must contain:

- stable ID, priority, status, and dependencies;
- current behavior and exact reproduction;
- required bounded behavior and non-goals;
- owning schemas, modules, adapters, fixtures, and docs;
- ordered implementation steps;
- edge cases with required outcomes;
- unit, integration, real-tool, mutation, closure, and compatibility evidence;
- explicit completion signal and handoff state.

Follow the [Documentation Contract](agents.md#source-docsdocumentation-contractmd) and add the
issue to the pickup index.

<a id="source-docsplanningmissing-workmd"></a>
## Missing Work and Tooling Inventory

Consolidated from `docs/planning/missing-work.md`.

Document type: current roadmap, regression register, and agent-ready backlog.

Authority: fresh repository evidence, machine contracts, the capability
matrix, and the ticket-specific source/test references in this document.

Status: current, with release-blocking P0 items.

This is the post-P1 repository rescan. Completed P0 guarantees are defined in
[P0 Pilot Acceptance](verification.md#source-docsacceptancepilot-acceptancemd), and the broader implemented slice is
defined in [P1 Expansion Acceptance](verification.md#source-docsacceptancep1-acceptancemd).

Last updated: 2026-07-28.

Repository rescan snapshot: 2026-07-28.

Agents must first read the [Agent Execution Guide](agents.md#source-docsagent-execution-guidemd).
Authors changing capability or acceptance claims must also follow the
[Documentation Contract](agents.md#source-docsdocumentation-contractmd). Historical acceptance
records establish what passed at their snapshots; they do not override a
current regression in this document.

<a id="source-docsplanningmissing-workmd--current-baseline"></a>
### Current Baseline

The repository now has an end-to-end local workflow for discovery, PDF/text
indexing, specialization-aware RTL analysis, evidence-backed planning,
cocotb/native/UVM/formal generation, configured execution, per-check outcomes,
coverage import/gating, review, audit, and CI status. State is schema-versioned,
atomically published, content-hashed, and bound to analyzed inputs.

Plan schema v19 now separates typed executable scenarios from prose checks and
records renderer-backed `executable`, `scaffold`, or `unsupported` state for
each requested target. Legacy v16 scenario mappings are read conservatively as
unsupported until a fresh planning pass qualifies them through the shared
renderer registry.
Revision schema v3 stores additive operations and immutable resulting-plan
snapshots, and `generate --revision` reads the selected snapshot. Run summaries
share validation-result v1 and cannot turn a zero exit code with no measured
checks into closure. See the [capability matrix](verification.md#source-docsqualificationcapability-matrixmd) for the
precise production boundary.

The automated suite covers the Python contract plus optional real-tool
integration. Hosted CI makes the pilot Verilator, Icarus/cocotb, and open formal
paths mandatory. See the acceptance documents for exact guarantees; the items
below are the remaining gaps, not limitations hidden by a success result.

The audited pre-roadmap baseline was 338 tests, four optional skips, and 82%
combined statement/branch coverage. The last accepted snapshot recorded 578
passing tests and, with the qualified Slang tool directory on `PATH` and
`DV_PLATFORM_QUALIFIED_SLANG_CI=1`, only the opt-in live-AI smoke test skipped.
That accepted snapshot measured 85.35% combined coverage, 88.38% statement
coverage, and 77.33% true branch coverage across 6,714 branches. CI
enforces the versioned `coverage-ratchet.json` policy: 84% combined and 75%
branch coverage globally, a 50% per-file branch floor, and stricter critical
module thresholds. Runtime, protocol contracts, AI gateway, feedback
normalization, and scenario validation now have complete branch coverage. The
qualified APB4 profile runs generated full-CLI good-DUT and nine-mutant matrices,
and the bounded AXI4-Lite profile runs generated full-CLI good-DUT and ten-mutant
matrices under both Icarus/cocotb and SBY/Yosys/Z3. The older hand-written protocol
benches have been removed. The local tool matrix
is Verilator 5.020, Slang 11.0.424, Icarus 12.0, SBY 0.67, Yosys 0.33, Z3
4.8.12, and GHDL 4.1.0. Those versions are now machine-enforced, including
independent SBY dependency probes. The qualified local Slang profile passes its
real AST fixture matrix, strict CLI pairing, and cross-frontend compatibility
matrix. The hosted real-tool job now installs GHDL, and the local GHDL 4.1.0 run
supplies the bounded VHDL execution evidence.

<a id="source-docsplanningmissing-workmd--2026-07-28-rescan-result"></a>
#### 2026-07-28 rescan result

The current working tree passes the previously failing behavioral and static
quality checks, but the rescan exposed release/qualification and optimizer
defects that a passing aggregate suite does not detect:

- `uv run python -m unittest discover -s tests` ran 585 tests in 558.676
  seconds and passed with four declared optional skips. The previously failing
  SECDED formal good-DUT/mutant path now passes, so `BUG-CDC-01` is closed and
  retained only as a regression record.
- Ruff lint/format, mypy, compatibility, maintainability, repository contracts,
  secrets, and the Stage 10 ledger command pass. The current compatibility hash
  is `ae6be4b7ea984ec3bea171b225ca1fbec346e96d330e98d6362653345b7f7d44`;
  maintainability reports 265 modules, 16 templates, 1,711 functions, zero
  cycles, and 45 duplicate blocks within policy. `QUALITY-01` is closed.
- The full suite emitted nine `ResourceWarning` process messages while nine
  `code-review-graph serve` children remained live under the test runner, then
  emitted unclosed stdin/stdout file warnings at interpreter shutdown. The
  children were launched at the configured ten-second timeout interval and
  exited only when the parent test process ended. See `AI-03`.
- The accepted Stage 10 command validates a historical ledger/evidence path
  set, while mandatory CI explicitly gates only through Stage 9 and does not
  create a contextually current Stage 10 bundle. See `QUAL-01`.
- The Stage 10 scale workflow compares two executions of the same source
  checkout and wheel, and its comparator rejects a genuinely different
  baseline commit/wheel. The wheel is hashed but not installed or executed, and
  the measured stages are generic line/XML/PDF operations rather than the
  product workflow. See `SCALE-02`.
- Release tags now resolve through the versioned channel policy, verify the
  exact tag/SHA, and require an exact successful Ubuntu Stage 10 candidate run
  before build/publication. Protected-index configuration and a real dry-run
  remain release-owner evidence work. See `RELEASE-01`.

No new coverage percentage or release acceptance is claimed from this
non-instrumented rescan. Historical Stage 6-10 records remain evidence of their
recorded snapshots; `QUAL-01` defines how they may or may not be used for a
current candidate.

The SCALE-02/QUAL-01 implementation now provides performance-v3 independent
baseline/candidate records, clean-wheel benchmark entry points, digest-bound
candidate bundles, and contextual candidate-mode gate validation. The live
acceptance transition still requires repository administration to set
`SCALE_BASELINE_REF` to a protected commit containing a previously accepted v3
baseline and to retain the resulting CI bundle as current evidence.

The 2026-07-29 Ubuntu Stage 10 run completed successfully after the workflow
was merged. WSL2 was explicitly removed from the current support claim because
no matching self-hosted runner was available; its records remain historical.
The archived Ubuntu candidate bundle is the current external qualification
evidence for the Ubuntu-only profile.

The 2026-07-29 RELEASE-01 implementation added channel policy, exact-SHA
qualification handoff, build-once manifest verification, fail-closed private
index idempotency, exact-wheel reinstall, and a signed recovery record. The
local disposable-index dry run passed absent, matching, conflicting, and
publication-failure cases and is retained in
`qualification/evidence/release-01-publication-dry-run-v1.json`. The remaining
release-blocking evidence is one protected-environment dry run against the
configured private index.

<a id="source-docsplanningmissing-workmd--p1-residuals"></a>
### P1 Residuals

These are the remaining requirements before claiming broad language- and
tool-independent production use.

<a id="source-docsplanningmissing-workmd--semantic-completeness"></a>
#### Semantic completeness

- Extend the normalized Slang/Verilator coverage beyond the implemented
  expression, case, reset-domain, property, type/interface, package-import,
  hierarchy, generate, and memory contracts. Full evaluation of every
  SystemVerilog sizing rule and temporal operator remains open and is exposed as
  a capability gap or critical generation claim.
- Bounded parameter matrices now expand deterministically as a constrained
  Cartesian product, fail before exceeding the configured point guard, and run
  as isolated analyses with unique plan, provenance, and coverage identities.
  Inferring useful parameter values without explicit project intent remains
  deliberately unsupported because it would create an ungoverned claim.
- Expand the qualified Verilator 5 / Slang 11 matrix to additional patch
  releases and large external designs. Operational CLI integration, per-sweep
  artifacts, cache identity, strict/required gates, specialization-stable
  schema-v2 comparison, inactive-generate retention, a bounded large-AST
  benchmark, and a mandatory qualified-CI profile are implemented. See the
  [compatibility matrix](architecture.md#source-docsarchitectureslang-compatibility-matrixmd).
- Widen the qualified GHDL version/platform matrix. Packages, records, subtypes,
  arrays, generate elaboration, explicit architecture binding, GHDL-authoritative
  VHDL-only semantics, and fail-closed mixed-language binding manifests are implemented.

<a id="source-docsplanningmissing-workmd--cdc-reset-and-memory-sign-off"></a>
#### CDC, reset, and memory sign-off

- Expand CDC beyond the qualified linear two-flop, pulse, toggle, round-trip
  handshake, coherent multi-bit handshake, bounded-rate general Gray-counter,
  and governed power-of-two async-FIFO/Gray-pointer profiles, including explicit
  first-word-fall-through sampling and stability. Reconvergence,
  non-power-of-two FIFOs, and hidden-stage structures still require
  dedicated semantics and properties. The Gray and coherent-payload contracts
  have passing good-DUT and killed-mutant cocotb/formal evidence.
- Expand beyond the governed reset/RDC/power profile. Unique observable reset
  domains, acyclic ordered release, two-stage dependency-ready crossings,
  power-good gating, isolation/retention sequencing, and bounded recovery/removal
  intent are qualified and mutation-tested. Physical recovery/removal timing,
  hidden reset trees, and analog constraints still require technology-specific adapters.
- Expand beyond the governed bounded SRAM profile. Parity and SECDED correction,
  double-error detection, and scrub completion are generated and mutation-qualified;
  initialization files, asynchronous or wider multi-port memories, power-state
  retention, and physical macro timing remain open.
- Expand beyond the qualified bounded-response formal contract. Property-specific
  pulse assumptions, induction invariants, causal bounded liveness, and
  assumption-witness covers are implemented; inferred environments, fairness,
  general temporal operators, and unbounded liveness remain open.

<a id="source-docsplanningmissing-workmd--protocol-and-transaction-breadth"></a>
#### Protocol and transaction breadth

- Versioned AXI4, packet-complete AXI4-Stream, Wishbone B4, Avalon-MM/ST,
  burst-capable AHB, and non-coherent TileLink UL/UH transaction contracts and
  deterministic recognition are present. The current ledger records exact
  endpoint-role and target cells conservatively as partial, with UVM remaining
  scaffold-only until vendor evidence exists. Existing
  bounded AXI4-Lite, APB4, AHB-Lite, and paired ready/valid qualification
  remains unchanged.
- Markdown tables, timing-diagram rows, register maps, cross-document evidence,
  conflicting values, performance/power intent, and coverage goals are extracted
  into evidence-addressed requirements. A governed OCR-sidecar adapter is
  connected; direct OCR engines remain deployment adapters.

<a id="source-docsplanningmissing-workmd--production-adapter-validation"></a>
#### Production adapter validation

- Expand beyond the vendor-qualified paired ready/valid UVM 1.2 project on AMD
  Vivado Simulator 2025.2. Multi-agent environments, virtual sequences,
  cross-protocol scoreboards, and RAL are generated and contract-tested; signed
  licensed execution of that richer profile and additional simulators remain open.
- Extend native VHDL beyond the qualified reset and paired ready/valid vertical slice.
  Native SystemVerilog and Verilog now close bounded APB4 and AXI4-Lite with
  exact result contracts and their complete nine- and ten-mutant matrices.
- Add vendor-native document/OCR engines, semantic embeddings/vector databases,
  report destinations, policy engines, and coverage databases beyond the
  connected and contract-tested built-in local adapters.
- Expand the enforced reference ranges beyond Verilator 5, Icarus 12, SBY
  0.67, Yosys 0.33, Z3 4.8, GHDL 4–5 eligibility, Slang 11, and exact versions
  carried by vendor UVM attestations.

<a id="source-docsplanningmissing-workmd--p2-expansion"></a>
### P2 Expansion

<a id="source-docsplanningmissing-workmd--coverage-and-reporting"></a>
#### Coverage and reporting

- Extend beyond the implemented UCIS XML, LCOV, JSON, and Cobertura-style XML
  importers to native vendor databases and richer formal coverage APIs while
  preserving exclusions and governed dispositions.
- Extend the implemented SARIF, YAML, JSON, and Markdown reports with complete
  schema migration coverage and filtering by severity, confidence, target,
  module, source, evidence state, and check outcome.
- Generate functional covergroups/bins from richer protocol and requirement
  schemas rather than only importing functional totals produced elsewhere.

<a id="source-docsplanningmissing-workmd--security-and-governance"></a>
#### Security and governance

- The threat model, export-root allowlist, secret-provider interface, publisher
  and package-hash checks, Sigstore/enterprise-PKI trust rules, rootless-aware OCI
  sandbox contract, release signing, and bounded retention/destruction controls
  are implemented. Checked-in runtime evidence executes an unprivileged Docker
  container with network denial, read-only roots/sources, isolated output,
  dropped capabilities, no-new-privileges, resource limits, and an environment
  allowlist. That record is historical until `QUAL-01` establishes candidate
  freshness/impact. Rootless Podman remains a supported deployment variant,
  not a release gate. Exact-tag validation and publication control remain open
  under `RELEASE-01`.
- Extend the existing content-free AI run/audit records to every optional
  network adapter with normalized request purpose, destination, and policy
  decision fields.
- The purge command safely covers transient AI, audit, log, RAG, and support
  state. Define separately approved destruction workflows for release evidence,
  counterexamples, generated customer collateral, and backups; these are
  intentionally excluded from general retention purge.

<a id="source-docsplanningmissing-workmd--incrementality-and-scale"></a>
#### Incrementality and scale

- The implemented dependency graph spans document chunks and normalized facts
  through requirements, checks, scenarios, symbols, artifacts, runs, coverage,
  and reviews. Revision generation is artifact-selective.
- Correct the Stage 10 2-million-line RTL, 128 MiB XML, and 64 MiB PDF
  benchmark under `SCALE-02`: current records prove same-candidate repeatability
  of proxy operations, not installed-product regression against an independent
  baseline. Only then extend the valid benchmark beyond Ubuntu 24.04/WSL2 and
  tune product parsing/indexing when records approach enforced budgets.
- Extend bounded concurrency to analysis, indexing, planning, generation, and
  independent formal tasks with license-aware scheduling.
- Verify reproducibility across supported operating systems and EDA versions,
  not only repeated runs on one worker.

<a id="source-docsplanningmissing-workmd--documentation-and-distribution"></a>
#### Documentation and distribution

- Operator, RAG/index, backend/output, security/privacy, testing, support,
  upgrade, and rollback references are published and checked for internal links,
  CLI examples, schema versions, and capability-state vocabulary. Complete
  catalog/metadata/capability/progress-transition enforcement remains open
  under `DOC-03`.
- Expand the published Linux/WSL support boundary into exact distribution/kernel
  ranges and qualified licensed-tool container images. Native Windows and macOS
  remain unsupported/best-effort.

<a id="source-docsplanningmissing-workmd--product-plans-and-entitlement-boundary"></a>
### Product Plans and Entitlement Boundary

Product direction recorded on 2026-07-28 defines two plans: **Free** and
**Enterprise**. This section is the intended plan boundary, not a claim that
entitlement enforcement, packaging separation, or board-specific verification
is implemented. `TIER-01` and `BOARD-01` are the implementation work packages.

<a id="source-docsplanningmissing-workmd--current-implementation-state"></a>
#### Current implementation state

The current package does not enforce product plans:

- `pyproject.toml` installs both `dv-platform` and `dv-enterprise` and registers
  the built-in enterprise EDA adapter entry points in the same distribution.
- There is no plan, subscription, entitlement, organization, seat, expiry, or
  capability-grant model in configuration or persisted state.
- `execution.license_tokens` limits concurrent licensed-tool jobs. It is not a
  product entitlement and must never be reused as one.
- Enterprise qualification levels such as `contract_verified`,
  `vendor_verified`, and `independently_signed` describe evidence quality. They
  do not authorize access to an Enterprise feature.
- Generic Stage 8 UART, SPI, I2C, GPIO, timer, watchdog, PWM, and interrupt
  profiles verify bounded RTL controller behavior. They do not describe a
  particular PCB, FPGA part, pinout, connector, oscillator, constraint set, or
  external component population.

Until `TIER-01` closes, documentation and UI must describe these plans as
proposed product packaging. Do not claim that the current binary securely
restricts enterprise adapters.

<a id="source-docsplanningmissing-workmd--normative-plan-matrix"></a>
#### Normative plan matrix

| Capability | Free plan | Enterprise plan |
| --- | --- | --- |
| Local RTL discovery and semantic analysis | Included for supported Verilog, SystemVerilog, and VHDL frontends and bounded semantics | Included |
| Digital verification planning | Included: evidence-backed plans, typed scenarios, review, coverage, and strict status for supported local targets | Included |
| Digital verification code generation | Included: deterministic cocotb, native Verilog/SystemVerilog/VHDL, formal, and UVM source generation where the target/profile is implemented; generation does not imply executable support | Included |
| Open digital execution | Included for qualified open tools such as Icarus/cocotb, Verilator-supported checks, and GHDL profiles | Included |
| Open formal code generation | Included: governed harnesses, properties, covers, and `.sby` projects for supported bounded profiles | Included |
| Open formal execution | Included through SymbiYosys, Yosys, and a supported solver such as Z3; tool installation remains the user's responsibility | Included |
| Generic RTL peripheral verification | Included for the bounded board-peripheral controller profiles accepted by Stage 8; this remains board-neutral digital verification | Included |
| Proprietary simulator connections | Excluded | Included through governed adapters for AMD Vivado Simulator/XSim, Siemens Questa, Synopsys VCS, Cadence Xcelium, and Aldec Riviera-PRO when the customer supplies the installation/license |
| Proprietary formal connections | Excluded | Included through governed adapters for Cadence JasperGold, Synopsys VC Formal, and Siemens Questa Formal when installed and licensed |
| Proprietary analyzer/CDC/RDC connections | Excluded | Included through governed adapters such as Synopsys VC SpyGlass and Aldec ALINT-PRO, subject to exact adapter qualification |
| Vendor coverage/result import | Open interchange formats remain available where implemented; vendor-native databases and licensed APIs are excluded | Included through qualified import adapters with stable point/check identity and provenance |
| Vendor qualification bundles and signed evidence | Excluded from the Free workflow | Included; contract/surrogate evidence must remain distinct from vendor-executed and independently signed evidence |
| Board-specific verification | Excluded; Free can verify the RTL peripheral block but not claim that it is correct for a named board | Included through a governed board manifest, board-aware generated collateral, vendor-tool execution, and board-specific closure |
| Physical/electrical sign-off | Excluded | Not automatically included. It remains delegated to qualified vendor/physical adapters under `PHYS-01`; Enterprise digital board verification must not be relabeled as SI, PI, STA, DRC, or hardware sign-off |
| AI provider behavior | No plan assignment is made here | No plan assignment is made here; `AI-01` and `AI-02` remain separate product/security decisions |

Enterprise includes every Free capability. A feature being assigned to
Enterprise does not make it supported: the selected profile, target, tool
version, entitlement, configuration, real-tool evidence, and strict closure
must all pass independently.

<a id="source-docsplanningmissing-workmd--free-plan-contract"></a>
#### Free plan contract

The Free plan must:

1. Work locally without an account, subscription lookup, network call, or
   signed product entitlement.
2. Permit analysis, planning, deterministic verification code generation,
   open-tool execution, coverage, review, and status for every profile that the
   capability ledger marks supported on a Free target.
3. Generate and execute formal verification collateral through the explicit
   `symbiyosys` adapter using `sby`, Yosys, and a supported solver. The plan must
   preserve current fail-closed assumptions, non-vacuity, counterexample,
   timeout, and per-check result behavior.
4. Allow source generation even when the user does not have a corresponding
   proprietary simulator, while labeling vendor-only execution as unavailable
   rather than implying it ran.
5. Retain generic bounded peripheral/controller verification. A UART or SPI
   profile can be supported in Free while the mapping of that controller to a
   named board remains Enterprise-only.
6. Reject Enterprise execution before tool probing, license-variable access,
   wrapper invocation, vendor bundle creation/import, or board artifact
   generation. The diagnostic must name the required capability and plan.
7. Continue to read and report historical Enterprise results after a downgrade,
   but prevent new Enterprise execution and prevent stale/missing Enterprise
   evidence from closing a workflow that still requires it.

The Free plan must not be artificially degraded by routing its open formal jobs
through an Enterprise gate. SymbiYosys/Yosys/Z3 are Free capabilities even when
they are also used as surrogate probes for enterprise adapter contracts.

<a id="source-docsplanningmissing-workmd--enterprise-plan-contract"></a>
#### Enterprise plan contract

The Enterprise plan must:

1. Include the complete Free feature set without changing generated bytes or
   verification semantics for the same inputs, versions, and capabilities.
2. Enable `dv-enterprise` adapter discovery, configuration, execution,
   qualification bundles, vendor evidence import, signature verification,
   vendor coverage import, and policy gating only after entitlement validation.
3. Connect to customer-controlled EDA installations through reviewed wrappers;
   Veriforge must not bundle vendor binaries, licenses, or proprietary
   libraries.
4. Support at least the existing adapter profile families: `vivado_xsim`,
   `questa`, `vcs`, `xcelium`, `riviera_pro`, `jaspergold`, `vc_formal`,
   `questa_formal`, `spyglass`, and `alint_pro`. Each adapter remains
   independently qualified; entitlement alone never upgrades
   `contract_verified` to vendor support.
5. Keep commands shell-free, environment-allowlisted, bounded, redacted, and
   confined to run-local paths. License server values and entitlement material
   must not appear in summaries, support bundles, or audit logs.
6. Bind Enterprise run evidence to organization, entitlement capability,
   source/configuration/plan/generated hashes, board identity when applicable,
   tool/version, wrapper identity, checks, coverage, artifacts, and signature
   level.
7. Provide board-specific digital verification through the contract below.

For terminology, "enterprise clients" means external customer-controlled EDA
tools and their site wrappers. It does not mean AI model providers, customer
tenants, or remote execution services.

<a id="source-docsplanningmissing-workmd--enterprise-board-specific-verification-contract"></a>
#### Enterprise board-specific verification contract

Board-specific verification is a distinct layer over the generic Stage 8
peripheral profiles. The first supported slice must be FPGA-oriented and must
use a versioned `enterprise-board-v1` manifest containing:

- stable board ID, board revision, manifest producer/version, source URI or
  artifact identity, and content hash;
- FPGA vendor, family, exact part, package, speed grade, and optional board-part
  identifier;
- selected RTL top, parameter/generic specialization, source/file-list identity,
  and language/mixed-language binding identity;
- oscillator/clock inputs with frequency, tolerance when known, generated-clock
  relationships, and owning constraint locators;
- reset sources, polarity, assertion/release intent, and clock-domain mapping;
- package pin, I/O bank, I/O standard, direction, pull/drive/slew policy where
  digitally checkable, connector/net name, and logical RTL port mapping;
- populated external devices and interfaces, such as UART bridge, SPI flash,
  I2C sensor/EEPROM, LEDs, buttons, switches, PMOD/FMC-style connectors, with
  exact role/profile/address/mode/bounds;
- vendor constraint files and hashes, including XDC/SDC/QSF or another
  explicitly supported format, with generated versus customer-owned provenance;
- required board checks, tests, coverage points, expected vendor reports, and
  explicit physical/electrical exclusions.

The board workflow must:

1. Import and validate the board manifest and constraints without guessing a
   board from filenames, marketing names, or installed Vivado board files.
2. Reconcile every declared board net with exactly one elaborated top-level
   port, direction, width/bit index, voltage bank, clock/reset domain, and
   peripheral profile. Missing, duplicate, contradictory, or unconnected
   required mappings block generation.
3. Generate a deterministic board harness, external-device digital models,
   board-specific tests/properties, vendor project manifest, and result/coverage
   identities. User-owned constraints remain immutable; generated supplemental
   constraints must be separate and reviewable.
4. Run board-level simulation through a qualified enterprise simulator, with
   AMD Vivado Simulator/XSim as the first vendor slice. JasperGold may execute
   board-bound formal properties when the selected semantics are supported, but
   JasperGold entitlement and qualification remain independent from Vivado.
5. Optionally run synthesis/implementation or static checks only through a new
   qualified FPGA implementation/analyzer adapter. The current
   `vivado_xsim` profile proves simulation capability, not Vivado synthesis,
   placement, routing, timing, bitstream generation, or hardware behavior.
6. Normalize every result to stable board/check/requirement/coverage IDs and
   retain tool, constraint, part, source, generated, and board-manifest
   provenance.
7. Close one legal public reference-board fixture and customer-owned pilot
   fixture with a known-good design plus pin, clock, reset, constraint,
   peripheral-mode, and external-device mutants.

Initial board-specific verification remains digital and pre-silicon. Analog
thresholds, signal/power integrity, metastability MTBF, PCB trace timing,
on-board power sequencing, thermal behavior, programming reliability, and
hardware-in-the-loop are unsupported until separate contracts and evidence are
accepted under `PHYS-01` or a future hardware-lab ticket.

<a id="source-docsplanningmissing-workmd--feature-by-feature-implementation-and-test-plans"></a>
#### Feature-by-feature implementation and test plans

The following plans are mandatory decompositions of `TIER-01` and `BOARD-01`.
An agent must complete one feature ID at a time. Completing one feature does not
promote another feature, target, adapter, board, or tool.

| Feature ID | Product feature | Owning ticket | Support transition |
| --- | --- | --- | --- |
| `FREE-DIGITAL-01` | Free local digital analysis, verification planning, code generation, open-tool execution, coverage, and status | `TIER-01` plus affected semantic/protocol tickets | Current bounded capabilities remain supported and become independently package-qualified as Free |
| `FREE-FORMAL-01` | Free formal code generation and execution through SymbiYosys/Yosys/solver | `TIER-01`, `FORM-01`, and affected depth tickets | Current bounded formal capabilities remain supported and become independently package-qualified as Free |
| `PLAN-GATE-01` | Free/Enterprise capability resolution, entitlement validation, package separation, and fail-closed gates | `TIER-01` | `unsupported` to `supported` only after all supported entry points enforce one capability authority |
| `ENT-EDA-01` | Enterprise connections to licensed simulator, formal, analyzer, and coverage tools | `TIER-01`, `TOOL-01`, `UVM-01`, and `COV-01` | Per adapter/profile/version: contract-only to vendor-qualified/independently signed |
| `ENT-BOARD-01` | Enterprise board-specific digital verification | `BOARD-01` | First exact board/revision/part/tool profile moves from unsupported to supported; all other boards remain unsupported |

<a id="source-docsplanningmissing-workmd--free-digital-01-implementation-plan"></a>
##### `FREE-DIGITAL-01` implementation plan

1. Inventory every core command, target, profile, schema, generated artifact,
   runner, result decoder, coverage importer, and strict-status rule currently
   required for the bounded digital support claim.
2. Assign `core.digital.analyze`, `core.digital.generate`, and
   `core.digital.execute.open` capability IDs at the command/target boundaries.
   These capabilities must resolve from the built-in Free plan without reading
   an entitlement.
3. Build/install the Free wheel in an isolated environment and assert its
   package files, entry points, schemas, templates, and default configuration.
   Remove accidental imports of private Enterprise implementations while
   retaining normalized Enterprise result readers.
4. Run discovery and frontend normalization for each claimed HDL/frontend
   combination. Preserve existing fail-closed unsupported semantics; product
   packaging must not broaden language support.
5. Run deterministic planning for each claimed digital profile and target.
   Confirm scenario target state comes from the renderer registry and evidence,
   not from the Free label.
6. Generate every claimed Free digital target twice from identical inputs and
   compare bytes, artifact manifests, trace IDs, and provenance.
7. Compile/elaborate and execute each target on its qualified open tool. Map
   every expected trace/check to validation-result v1; zero/unmatched output is
   `unexecuted`.
8. Import/reconcile coverage and run strict status. Every mandatory check,
   behavior, requirement, parameter point, and coverage point must close.
9. Run known-good DUTs and the complete existing mutant matrix for each claimed
   profile. Packaging changes are not allowed to reduce mutation sensitivity.
10. Run the same Free workflow from the Enterprise installation and compare
    normalized plans/generated bytes/results. The Enterprise plan may add
    capabilities but must not change Free semantics.
11. Test installation, upgrade, downgrade, and removal of the Enterprise
    package without corrupting Free state.
12. Publish a Free acceptance record with exact wheel hash, Python/platform/
    tool versions, profiles, bounds, targets, checks, mutants, skips, and
    exclusions.

`FREE-DIGITAL-01` required test coverage:

| Coverage family | Required cases |
| --- | --- |
| Repository/configuration | Empty repository; no top; one top; multiple explicit tops; missing/duplicate file-list entries; include/define ordering; path with spaces; symlink/path escape; unreadable input; valid relative roots |
| Frontend semantics | Supported Verilog/SystemVerilog/VHDL fixture; malformed source; unsupported operator/type/generate/property; ambiguous clock/reset; symbolic parameter; duplicate instance; frontend contradiction; unqualified tool version |
| Planning | No claims; supported claim; contradicted claim; missing evidence; one/multiple specializations; unsupported target; stale RTL facts; repeated planning; stable IDs/order |
| Generation | Every Free renderer; invalid identifier/width/literal; unsupported adjacent semantic; missing template; duplicate artifact path; repeat-byte determinism; stale plan/revision; read-only output; interrupted atomic publication |
| Open execution | Good DUT; each fault mutant; compile error; elaboration error; failed check; timeout; signal termination; missing executable; wrong version; empty result; unknown/duplicate/missing trace; nonzero process with decoded failures; zero process with failed checks |
| Coverage/status | Full closure; one missing point; stale run; stale generated hash; unknown/orphan point; zero denominator; excluded-only scope; expired waiver; partial parameter sweep; optional tool skipped; required tool skipped |
| Plan isolation | Free with no entitlement file; malformed Enterprise entitlement present; Enterprise package absent; Enterprise package installed; historical Enterprise evidence present; configured Enterprise CI requirement |
| Security/concurrency | Secret-like source/log text redaction; output/path escape; concurrent same artifact; cancellation during publish; bounded logs/processes; no network attempt; no enterprise plugin import or license-environment read |
| Compatibility | Read every supported legacy schema; reject newer schemas; preserve CLI/JSON envelopes; Free-to-Enterprise-to-Free state round trip |

Niche-case rule: test each claimed profile at minimum/maximum declared widths,
latencies, queue depths, outstanding limits, and parameter points. Test
cross-products where fields interact semantically; pairwise selection is
acceptable only when the omitted Cartesian combinations are proven equivalent
and that proof is recorded in the coverage ledger.

<a id="source-docsplanningmissing-workmd--free-formal-01-implementation-plan"></a>
##### `FREE-FORMAL-01` implementation plan

1. Inventory the exact bounded formal profiles and the accepted
   SymbiYosys/SBY, Yosys, and solver versions. Separate generated formal source,
   engine task construction, execution, parsing, counterexamples, formal
   coverage, and strict closure.
2. Assign Free capabilities `core.formal.generate.symbiyosys` and
   `core.formal.execute.symbiyosys`. Do not gate them through enterprise
   surrogate qualification.
3. Validate explicit formal-tool configuration, executable/version probes,
   engine/solver compatibility, timeout/bound/resource limits, and run paths.
4. Generate typed assumptions, assertions, invariants, covers, harnesses, and
   `.sby` tasks only from supported scenario semantics. Unsupported temporal
   behavior must stay unsupported.
5. Add assumption-consistency, trigger reachability, response reachability,
   completion, and other required non-vacuity covers before accepting a proof.
6. Run each required prove/cover/induction task and decode task/property
   identities into canonical checks and formal coverage points.
7. Retain bounded counterexamples and diagnostics with source/plan/generated/
   tool provenance; reject paths outside the run root and redact unsafe content.
8. Test known-good DUTs and one mutant per assumption/property/checker rule.
   Each mutant must fail the intended property, not a setup/compile precondition.
9. Exercise strict status with complete, partial, failed, timed-out, vacuous,
   malformed, stale, and unsupported results.
10. Execute the formal matrix from an isolated Free wheel without account,
    entitlement, Enterprise package, network, or vendor environment.
11. Compare Free and Enterprise execution for identical open-tool inputs and
    prove identical generated bytes/check identities/outcomes.
12. Publish formal acceptance evidence with exact tools/tasks/depths/properties/
    covers/mutants and bounded-versus-unbounded exclusions.

`FREE-FORMAL-01` required test coverage:

| Coverage family | Required cases |
| --- | --- |
| Bounds | Minimum/maximum supported response bound; bound below/above range; zero/negative/non-integer; depth exactly sufficient and one cycle insufficient |
| Clock/reset | One supported domain; missing/ambiguous clock; wrong reset polarity/style; reset never releases; multiple unsupported domains; gated/derived clock without authority |
| Assumptions | Valid environment; missing required assumption; contradictory assumptions; assumptions suppress all triggers; unconstrained input; over-constrained response; assumption witness reached/not reached |
| Properties | Safety pass/fail; invariant pass/fail; causal response; early/late/missing response; response without trigger; hold/stability rule; supported temporal boundary; unsupported operator |
| Tasks/results | Prove pass/fail/unknown; cover reached/unreached; induction base/step disagreement; timeout; killed process; solver error; malformed/empty SBY output; duplicate/unknown task; process/result contradiction |
| Counterexamples | Expected trace retained; missing trace for failure; stale trace; path escape/symlink; oversized trace/log; source/check mapping missing; redaction |
| Tool matrix | Missing `sby`; missing Yosys; missing solver; wrong executable; unsupported version; compatible qualified version; tool version changes after generation; solver selected inconsistently |
| Determinism/concurrency | Repeated harness/SBY bytes; parallel independent tasks; cancellation; one task fails while another passes; deterministic aggregate ordering; atomic summary |
| Plan isolation | No entitlement; invalid entitlement; Enterprise package absent/present; SymbiYosys used as Free execution versus Enterprise surrogate probe |

Formal feature coverage is incomplete if every assertion passes but a required
trigger/assumption/completion cover is unreachable. Such a result is vacuous
and non-closing regardless of code coverage or process exit.

<a id="source-docsplanningmissing-workmd--plan-gate-01-implementation-plan"></a>
##### `PLAN-GATE-01` implementation plan

1. Finalize the capability registry, Free/Enterprise sets, entitlement schema,
   canonical signature purpose, trust policy, time policy, and package split.
2. Implement the immutable resolver and explicit states: `free`, `enterprise`,
   `invalid`, and approved bounded `grace` if product/security authorizes it.
3. Add one central capability-check API with stable error codes and content-free
   audit events.
4. Enumerate every supported Enterprise entry point and direct public API.
   Add a test that fails when a new enterprise entry point lacks an explicit
   capability declaration.
5. Gate before package/plugin import, discovery, environment access, tool probe,
   filesystem mutation, network attempt, wrapper generation, subprocess, or
   evidence import.
6. Split/build both wheel types and test their installed contents and entry
   points instead of relying on source-tree tests.
7. Add status/support diagnostics, configuration migration, and read-only
   historical Enterprise result behavior.
8. Add upgrade/downgrade/expiry/rotation/concurrency tests.
9. Threat-model bypass through direct APIs, plugins, environment variables,
   copied state, clock manipulation, symlinks, and malformed signatures.
10. Run complete Free regression and Enterprise contract suites from installed
    artifacts.

`PLAN-GATE-01` must cover every transition:

| Start state | Event | Required resulting state/behavior |
| --- | --- | --- |
| Free | No entitlement configured | Remain Free with no warning/network |
| Free | Valid Enterprise entitlement installed | Enterprise grants become available after validation |
| Free | Invalid/untrusted entitlement installed | Entitlement state invalid; Free remains usable; Enterprise blocked |
| Enterprise | Capability-limited grant requested for missing feature | Only missing feature blocked |
| Enterprise | Entitlement expires | New Enterprise work blocked; in-flight evidence retains start grant; closure reevaluates policy |
| Enterprise | Entitlement rotates valid-to-valid | New work binds new entitlement; old evidence remains identifiable |
| Enterprise | Downgrade/remove Enterprise package | Free works; normalized history readable; configured Enterprise gates fail explicitly |
| Invalid | Entitlement repaired | Revalidate from canonical bytes/trust/time; no stale invalid/valid cache |
| Grace, if approved | Grace expires | Enterprise blocked deterministically |
| Any state | System clock or trust policy changes | Re-resolve according to signed policy and report observed cause |

For each transition test human output, JSON output, exit code, audit event,
filesystem mutations, plugin-import count, tool-probe count, environment access,
and network-call count. The latter four must remain zero for a rejected
operation.

<a id="source-docsplanningmissing-workmd--ent-eda-01-implementation-plan"></a>
##### `ENT-EDA-01` implementation plan

Complete the following sequence separately for each adapter profile and tool
version; evidence for one adapter does not cover another:

1. Declare required Enterprise capability, adapter family, languages,
   executable discovery hints, allowed wrapper contract, license-variable
   names, result formats, timeout/resource policy, and supported version range.
2. Add entitlement gating before profile discovery and environment inspection.
3. Build command arguments without a shell and validate every source/include/
   define/library/work/run/result/artifact path.
4. Execute only a site-reviewed wrapper in a bounded run directory with
   allowlisted environment and redacted bounded logs.
5. Prefer structured native results and normalize exact check/property/
   coverage IDs. Preserve unknown results but do not close them.
6. Reconcile normalized outcomes against expected plan traces, requirements,
   coverage, source/generated hashes, tool/version, and entitlement identity.
7. Add contract fixtures, open surrogate workflow where applicable, real vendor
   execution, independent signature import, and stale/tampered evidence tests.
8. Exercise good DUT plus feature-specific mutants in the real tool; a parser-
   only fixture does not qualify generated collateral.
9. Run strict policy at every qualification level and age boundary.
10. Publish one adapter/profile/version acceptance record and leave all
    unqualified versions/profiles conservative.

Every adapter must test:

- executable absent, found, wrong tool, unsupported version, version output on
  stderr, localized output, and version changing between probe and run;
- license variable absent, queue/wait, denial, expiry, feature unavailable,
  server outage, and secret redaction;
- wrapper missing, not executable, path with spaces, escaping path, symlink,
  nonzero exit, signal, timeout, partial output, oversized log, and child
  process cleanup;
- result missing, empty, malformed, newer schema, unknown field, duplicate/
  unknown/missing check, skipped/unknown state, process/result contradiction,
  and artifact hash/path mismatch;
- source/configuration/plan/generated/tool/board/entitlement provenance stale
  independently and in combinations;
- contract, surrogate, vendor, signed, expired-signature/evidence, untrusted
  signer, project-self-signature, and tampered attestation;
- simultaneous jobs below/at/above license-token budget, cancellation while
  queued/running, deterministic result collation, and no cross-run artifact or
  environment leakage.

Tool-specific niche tests are mandatory. Examples include UVM phase/transaction
non-vacuity and simulator language/library order; JasperGold app/task/property/
counterexample identity; Vivado/XSim snapshot/library/timescale/report identity;
CDC/RDC analyzer waiver/constraint/domain identity; and vendor coverage
bin/cross/exclusion/merge semantics. Record non-applicable cases with a
technical reason; do not silently omit them.

<a id="source-docsplanningmissing-workmd--ent-board-01-implementation-plan"></a>
##### `ENT-BOARD-01` implementation plan

1. Freeze one board/revision/part/constraint/tool profile and assign stable
   requirement IDs for every supported board fact and behavior.
2. Implement closed board manifest/fact schemas, models, codecs, migrations,
   provenance, and exact validation diagnostics.
3. Implement the bounded constraint parser/importer and adversarially test it
   without executing customer Tcl.
4. Reconcile board, constraint, RTL, peripheral, clock/reset, and vendor-
   resolved facts with per-fact supported/missing/contradicted/unsupported
   states.
5. Build typed board scenarios, digital external-component models, check IDs,
   coverage points, and target states for only the frozen profile.
6. Generate deterministic board harness/project/supplemental constraints and
   verify user-owned artifacts remain byte-identical.
7. Gate and execute XSim through the Enterprise adapter; add other EDA targets
   only as separate matrices.
8. Decode/reconcile board checks and coverage, then run strict status.
9. Execute good design plus one mutant per board requirement and validation
   rule.
10. Repeat generation and execution under stale, interrupted, concurrent,
    upgrade/downgrade, and invalid-entitlement conditions.
11. Run the exact installed Enterprise artifacts and retain signed vendor
    evidence where policy requires it.
12. Publish board acceptance with exact scope and physical exclusions.

`ENT-BOARD-01` full coverage requires all of these categories:

| Category | Mandatory niche cases |
| --- | --- |
| Identity/revision | Exact board; marketing alias; wrong/missing revision; same board name from another vendor; manifest producer/version drift; duplicate IDs |
| FPGA device | Wrong vendor/family/part/package/speed grade; unsupported device; board-part file drift; source/top/specialization mismatch |
| Pins/nets | Missing/duplicate pin; two ports one pin; one port two pins; vector bit swap; range direction; connector numbering; NC/reserved pin; differential pair/polarity; case sensitivity |
| I/O constraints | Missing/conflicting I/O standard; bank voltage conflict; direction mismatch; pull/drive/slew conflict; wildcard resolving zero/multiple objects; customer/generated ownership collision |
| Clocks | Exact/min/max supported frequency; wrong units; oscillator tolerance boundary; missing/duplicate clock; generated clock; PLL relationship; unrelated domains; stale clock report |
| Resets | Active-high/low; asynchronous/synchronous assertion/release; missing reset; wrong domain; reset source absent; release before clock stable |
| GPIO/tri-state | Input/output/output-enable mismatch; high-Z; external pull; button bounce model boundary; LED polarity; switch state; simultaneous updates |
| UART | TX/RX swap; baud/divisor/tolerance; parity; stop bits; idle polarity; framing/overflow; bridge reset/disconnect |
| SPI | CPOL/CPHA; CS polarity/index; MSB/LSB; width; divider; MISO/MOSI swap; flash/device mode; timeout; multiple devices/contention |
| I2C | SDA/SCL swap; open-drain drive/sample; missing pull-up intent; 7-bit address/strap conflict; ACK/NACK; repeated START; stretch; arbitration; stuck bus |
| Constraint security | Unsupported Tcl; `source`; file/process/network/environment access; command substitution; recursion; oversized input; malformed quoting; path traversal |
| Generation | Repeat bytes; invalid identifier/literal; user file immutability; supplemental overlap; path escape; interrupted/concurrent publish |
| Vendor execution | Missing/wrong/changed tool; entitlement/license states; compile/elaborate failure; empty board checks; stale report; wrong part/constraint; timeout; partial artifacts |
| Result/closure | Good DUT; each mutant; unknown/duplicate/missing point; zero denominator; stale provenance dimension; required versus optional physical gap |
| Product boundary | Free rejection before parsing; limited Enterprise grant; downgrade; historical board evidence read-only; board capability without EDA capability and inverse |

Physical, analog, implementation, and hardware-lab categories must be marked
unsupported in the initial profile and tested to ensure no digital pass
silently promotes them.

<a id="source-docsplanningmissing-workmd--agent-ready-backlog"></a>
### Agent-Ready Backlog

This is the implementation queue. It converts documented limits into bounded
work packages that an agent can own without silently expanding a verification
claim. The [capability matrix](verification.md#source-docsqualificationcapability-matrixmd) remains
the intended release authority once its conflict with the protocol architecture
document has been resolved.

<a id="source-docsplanningmissing-workmd--zero-assumption-pickup-index"></a>
#### Zero-assumption pickup index

Use this index before reading ticket prose. A `yes` value in `Ready` means an
agent can begin without a product decision; it does not mean dependencies or
required tools are already available. `no` and `blocked` are stop states, and
`closed` is retained regression history rather than pickup work. The "begin
with" column is the first source or command to inspect. The ticket body and
ticket-level playbook remain mandatory. Before editing, search for the ticket
ID's execution card (or regression/decision card) and follow that card plus the
Zero-Assumption Agent Execution Protocol in order.

| ID | Ready | Dependency or gate | Begin with | Completion signal |
| --- | --- | --- | --- | --- |
| `BUG-CDC-01` | closed | fixed before this rescan; retain as a regression record | Rerun `tests.integration.test_memory_depth_pipeline.GeneratedSecdedMemoryDepthPipelineTests.test_generated_formal_passes_good_dut_and_kills_secded_mutants` when CDC or memory ownership changes | SECDED good DUT and five mutants close; unknown/asynchronous external-input negative cases still block |
| `QUALITY-01` | closed | fixed by `f2527c8`; retain the reviewed compatibility baseline | Run compatibility, maintainability, mypy, and Ruff lint/format after public-surface or quality-sensitive changes | Every mandatory quality command passes without weakened policy or blind fingerprint replacement |
| `QUAL-01` | closed | Ubuntu Stage 10 candidate bundle passed; WSL2 is non-current | Candidate-mode `ga_gates.py`, archived Ubuntu bundle, and ledger | Contextual candidate validation passed for the merged candidate; historical WSL evidence is excluded from current gates |
| `RELEASE-01` | in progress; release blocking | Implementation complete; protected-index dry run remains; local recovery evidence retained | Inspect `.github/workflows/release.yml`, `scripts/release/release_policy.py`, `scripts/release/manifest.py`, `scripts/release/publication.py`, `qualification/evidence/release-01-publication-dry-run-v1.json`, release scripts/tests, and environment policy | Exact tag/SHA/channel checks, qualification-run identity, build-once manifest, immutable handoff, idempotent publication, signed recovery record, and exact-digest reinstall all pass |
| `SCALE-02` | closed | Ubuntu 24.04 accepted; WSL2 explicitly downgraded to historical/non-current | Candidate installed-wheel records and archived Stage 10 artifact | Independent baseline/candidate comparison passed with identical fixtures and distinct commit/package identities |
| `AI-03` | in progress | deterministic fake Headroom/MCP fixtures; lifecycle hardening underway | Inspect `src/dv_platform/ai/code_graph.py`, `src/dv_platform/ai/optimization.py`, planning preflight, context-optimizer config, and lifecycle tests | Optimizers are explicit, bounded, provenance-recorded, redirect-safe, and leave zero child processes/file descriptors on every success/failure/cancel path |
| `DOC-00` | in progress | broad protocol ledger established conservatively; remaining profile/target review | Compare `docs/verification.md` with `docs/architecture.md` and `qualification/policies/capability-ledger-v1.json` | One evidence-backed state per broad-profile target; strict status and current docs agree |
| `DOC-02` | in progress | historical snapshot metadata and contradiction contract underway | Classify each conflicting document listed in the ticket using `docs/agents.md` and the capability ledger | Current authorities agree with a machine ledger; historical snapshots are dated/linked; a deliberate contradiction test fails |
| `DOC-03` | yes; flat-layout foundation complete | preserve the seven-guide set and historical source sections; coordinate machine capability state with `DOC-02` | Inspect `scripts/checks/repository_contracts.py`, the source-coverage lists in `docs/*.md`, and the remaining-work list in this ticket | Versioned document catalog covers every maintained file and migrated source section; required metadata and command families are checked; malformed catalog/metadata/commands fail fixtures |
| `TIER-01` | partially | product direction is fixed; entitlement issuer, private package, and offline policy need owner approval | Inspect `pyproject.toml`, `src/dv_platform/enterprise/`, CLI configuration/models, plugin loading, and status policy | Free works without entitlement; every Enterprise entry point fails closed without a valid grant; plan/capability state is visible and tested |
| `BOARD-01` | contract work yes; vendor promotion no | `TIER-01`; one legal board fixture; qualified Vivado/other EDA evidence; physical scope remains gated by `PHYS-01` | Stage 8 peripheral contracts, enterprise adapters, constraints/tool profiles, and proposed `enterprise-board-v1` schema | One board/revision closes manifest, mapping, generated harness, XSim/vendor execution, exact results/coverage, and board-specific mutants |
| `SEM-01` | yes, one slice only | choose one unsupported semantic family | `src/dv_platform/rtl/semantic_manifest.py`, normalized RTL schemas, frontend cross-check fixtures | One versioned semantic slice has migration, positive/negative/ambiguity fixtures, real frontend evidence, and fail-closed target gating |
| `SEM-02` | no external semantics yet | governed mixed-language elaborator and binding manifest | Existing `cross-language-bindings-v1` schema and `analysis.bindings` validation | External elaboration manifest reaches one target; wrong/ambiguous binding cases reject without inferred mappings |
| `SEM-03` | yes if tools/design licenses available | qualified Verilator/Slang/GHDL versions and licensed external fixtures | Existing compatibility matrices and `qualification/external-designs/` | Version matrix records hashes/diagnostics/resources; unqualified versions fail closed in strict mode |
| `FORM-01` | yes, one extension only | explicit product choice among the ticket's four semantic extensions | Formal scenario model, validation, harness generation, SBY task builder, result decoder | Typed policy, deterministic proof/cover, non-vacuity witness, killed mutant, and unsupported-engine result |
| `CDC-01` | yes | select exactly one advanced CDC profile; preserve the closed `BUG-CDC-01` regression | CDC policy schema, normalized CDC facts, cocotb/formal CDC generation | Good DUT, structural negative, per-rule mutants, path classification, and non-closing ambiguity |
| `RDC-01` | no without evidence | licensed physical/reset tool and legal fixture | Qualification/adaptor contracts plus existing logical RDC profile | Imported physical findings retain rule/source/tool identity; stale evidence rejects; physical failures cannot close logically |
| `MEM-01` | yes, one behavior only | select one behavior and preserve the closed `BUG-CDC-01` SECDED regression | Memory policy/fact/scenario contracts and memory-depth pipeline tests | Policy rejection cases, good DUT, behavior mutant, exact coverage/non-vacuity, and no inferred memory intent |
| `PROTO-01` | blocked | `DOC-00`; then one profile, role, bound, and target | Broad protocol catalog, recognizer, renderer registry, decoder, and matching fixtures | Per-target good-DUT/mutation/coverage closure; every other target remains explicitly partial/scaffold/unsupported |
| `PROTO-02` | yes, one feature only | preserve current APB4/AXI4-Lite/AHB-Lite/ready-valid behavior | Existing bounded profile schema and qualification fixture for the selected protocol | Migrated contract plus good-DUT and mutant closure on each newly claimed backend |
| `PERIPH-01` | yes, one feature only | electrical behavior requires `PHYS-01` decision/evidence | Stage 8 profile and qualification tests for UART, SPI, I2C, or GPIO/timer/interrupt | Trace, scoreboard, bins, exact checks, feature mutants, and regression of the old bounded profile |
| `VHDL-01` | yes, one profile only | qualified GHDL; mixed-language work depends on `SEM-02` | Native VHDL renderer/executor and Stage 9 VHDL qualification tests | GHDL analysis/elaboration/run, good/bad fixtures, canonical trace identity, preserved VHDL source evidence |
| `UVM-01` | contract work yes; promotion no | licensed simulator and independently signed evidence for support promotion | UVM scenario/rendering contracts and enterprise qualification importer | Rich profile is self-checking; signed vendor run maps exact checks/coverage; mocks remain contract-only |
| `TOOL-01` | contract work yes; qualification no | licensed tool, legal fixture, trusted execution environment | Enterprise adapter API, sandbox policy, tool policy, result normalization | Structured adapter results, timeout/license/malformed-report failures, real signed evidence, no shell interpolation |
| `COV-01` | yes for one format | representative native database/export and version policy | Coverage-v3 schema, importer registry, closure/status policy | Imported stable points preserve exclusions/dispositions; partial/unknown/stale data cannot close |
| `COV-02` | yes for one typed intent family | selected protocol/requirement schema | Scenario coverage goals, renderer, trace/coverage ID mapping | Deterministic bins, reachable-hit and mutant-miss tests, zero-denominator/ignored-bin handling |
| `DOC-01` | yes for adapter contract | selected OCR or local retrieval implementation; network must remain explicit | Document-ingestion adapter interfaces, source locator model, RAG operations guide | Deterministic indexed chunks/locators, corrupt/encrypted/rotated/duplicate tests, no implicit network |
| `SCALE-01` | after `SCALE-02` | first establish a trustworthy installed-wheel candidate/baseline benchmark, then select one broader platform/scheduler slice | Stage 10 scale records, performance schemas/scripts, scheduler | Real product baseline remains valid; broader slice meets budgets; interruption/concurrency/cache identity are tested |
| `PLAT-01` | yes for documentation/CI slice | exact OS/kernel/container/tool tuple | Installation docs, CI matrix, platform qualification records | Published support table has exact versions, real smoke evidence, and explicit unsupported/best-effort behavior |
| `AI-01` | no | explicit product/security approval | AI boundary in README, gateway contracts, audit/security docs | Decision recorded in ADR/policy; only then implement bounded authority with deterministic validation and audit |
| `AI-02` | no | explicit product/security approval | Gateway provider selection, privacy/network policy, audit model | Decision recorded; routing/fallback cannot silently change provider, destination, model, or data policy |
| `PHYS-01` | no | explicit product boundary plus licensed physical evidence | Logical CDC/RDC/memory boundary, enterprise adapter contract, security policy | Decision defines delegated sign-off, evidence levels, stale/waiver rules, and release gating |

Pickup rules:

1. Work active P0 issues before capability expansion unless the user explicitly
   assigns a different ticket. A `closed` row is regression evidence, not an
   implementation pickup.
2. Pick one row. Do not combine unrelated IDs to manufacture a broad "cleanup".
3. Treat `no` and `blocked` as stop states unless the task explicitly resolves
   the listed dependency.
4. Read both the summary ticket and its later technical playbook before editing.
5. Use the common completion contract below in addition to the row's completion
   signal.
6. At handoff, update the row only if readiness, dependency, entry point, or
   completion state actually changed; never mark completion from generated
   collateral or unit tests alone.

<a id="source-docsplanningmissing-workmd--common-completion-contract"></a>
#### Common completion contract

Unless an item explicitly says otherwise, an implementation is complete only
when it has all of the following:

1. A versioned schema, profile, or policy that declares the new semantics and
   rejects missing, ambiguous, and out-of-range values.
2. Planning and claim-gating that retain source/evidence references and leave
   an unsupported case non-executable rather than guessing intent.
3. Deterministic generated artifacts with provenance and execution manifests.
4. Tool execution that maps measured outcomes to stable check, requirement,
   behavior, and coverage-point identities. Empty, skipped, malformed, unknown,
   or unmatched results must be non-closing.
5. Good-DUT evidence, targeted negative fixtures or killed RTL mutants, repeat
   generation, and strict CLI/CI coverage closure for every newly claimed target.
6. Updated capability matrix, acceptance document, operator documentation, and
   migration behavior for previously stored plans and run evidence.
7. A machine-readable feature coverage ledger mapping every requirement,
   supported state transition, edge case, mutant, target/tool, and exclusion to
   an exact test and result.
8. All mandatory test layers below pass. Any non-applicable layer has a
   ticket-specific technical reason and does not conceal an untested support
   claim.
9. New feature-owned validation, gating, migration, result-decoding, and status
   decision branches reach 100% branch coverage unless an independently
   reviewed structurally unreachable branch is excluded by the versioned
   coverage policy.
10. Every planned semantic mutant is killed by its intended checker/property,
    not merely by compilation, setup, an unrelated assertion, timeout, or tool
    crash.
11. Every supported requirement/check/coverage identity appears exactly once
    in closure; missing, duplicate, unknown, stale, skipped, or unexecuted
    identities prevent support promotion.
12. Real-tool evidence exists for each tool/backend claimed. Mocks, fixtures,
    surrogate tools, generated text, and parser unit tests remain useful but
    cannot replace that evidence.

An agent should split an item if it cannot identify a single profile, target,
semantic contract, and acceptance fixture set. A renderer, generated file, or
zero tool exit code is never by itself completion evidence.

<a id="source-docsplanningmissing-workmd--definition-of-full-feature-coverage"></a>
##### Definition of full feature coverage

"Full coverage" means complete coverage of the bounded feature contract, not
merely a high source-line percentage. All of these dimensions are mandatory:

| Coverage dimension | Required completion |
| --- | --- |
| Requirements | 100% of normative feature requirements and exclusions map to tests and measured results |
| State transitions | 100% of supported, rejected, failed, interrupted, stale, migration, and recovery transitions are exercised |
| Input partitions | Every valid class, invalid class, minimum/maximum boundary, just-inside/just-outside boundary, missing value, duplicate, contradiction, unknown/newer form, and readable legacy form is covered |
| Target/profile/tool | Every claimed role, target, tool/version, language, specialization, and platform has independent evidence; support does not propagate between cells |
| Result/closure | Pass, feature failure, setup failure, timeout, interruption, skipped, unknown, malformed, empty, duplicate, unmatched, stale, and unsupported outcomes are tested |
| Mutation | 100% of the feature's planned semantic mutants are killed by the intended oracle/property |
| Functional/formal coverage | Every mandatory behavior/bin/cross/property/cover/non-vacuity point is reached or failed as designed; zero denominators cannot report success |
| Security | Every new parser, path, plugin, environment, secret, process, signature, entitlement, and external-data boundary has adversarial negative coverage |
| Compatibility/migration | Every readable prior schema/state version plus newer-version rejection, upgrade, downgrade, rollback, and stale-cache behavior is covered |
| Determinism/concurrency | Repeat bytes/IDs, parallel ownership, cancellation, collision, atomic publication, and deterministic result ordering are tested |
| Source branch coverage | Feature-owned decision modules meet 100% branch coverage or carry a reviewed policy exclusion with proof that the branch is structurally unreachable |
| Documentation/operations | Commands parse, expected outputs/exits are tested, evidence paths exist, and capability language agrees with the ledger |

A feature is not fully covered when only its happy path, source lines, aggregate
coverage percentage, or one target passes. If an edge case cannot be tested or
resolved, mark that dimension `unsupported`/`partial` and keep the feature from
broader promotion.

<a id="source-docsplanningmissing-workmd--mandatory-feature-coverage-ledger"></a>
##### Mandatory feature coverage ledger

Every new feature must add a versioned `feature-coverage-v1` record or the
equivalent machine-owned ledger entry. At minimum it must contain:

```text
feature_id
profile_id and version
endpoint/role
target/backend/tool/version/platform
requirement_ids
supported and unsupported bounds
schema/model/migration owners
implementation file/symbol owners
test_case_id
test layer and fixture
input partition and parameter point
expected exit/status/check/coverage result
edge_case_id
mutant_id and intended killing check/property
real-tool evidence path/hash
source/configuration/plan/generated/run/coverage provenance
actual result and timestamp
skip/non-applicable reason
```

The ledger validator must reject:

- a requirement, edge case, state transition, mutant, or supported target with
  no test;
- duplicate test/requirement/edge/mutant identities;
- a planned test with no actual result;
- an expected failure that passed for an unrelated setup error;
- a mutant killed by the wrong check or before the target behavior executed;
- a required real-tool case backed only by a mock/surrogate;
- stale or cross-profile evidence;
- a `not_applicable` entry without a technical reason and reviewer;
- a support-state promotion while any mandatory ledger cell is open.

<a id="source-docsplanningmissing-workmd--mandatory-test-layers-for-every-feature"></a>
##### Mandatory test layers for every feature

Follow this order so failures identify the owning layer:

1. **Schema tests:** valid round trip, closed-schema unknown fields, type/range/
   enum/format boundaries, missing/duplicate identity, old-version migration,
   and newer-version rejection.
2. **Domain/model tests:** immutable invariants, canonical ordering/hashing,
   equality/identity, derived properties, and invalid in-memory construction.
3. **Configuration/validation tests:** defaults, explicit values, conflicts,
   authority, path/tool/policy checks, and exact diagnostics.
4. **Planning/claim tests:** supported, partial, contradicted, missing evidence,
   unsupported target, stale input, specialization, and deterministic IDs.
5. **Scenario tests:** stimulus, oracle, completion, timeout, assumptions,
   checks, coverage goals, and non-vacuity identities.
6. **Generation tests:** every claimed renderer, compile-valid syntax, invalid
   values, escaping, deterministic bytes, provenance, repeated generation,
   interruption, and atomic publication.
7. **Execution tests:** good behavior, feature fault, compile/elaboration/setup
   failure, tool absence/version, timeout/signal/cancellation, resource limits,
   bounded logs, and process cleanup.
8. **Decoder/result tests:** exact pass/fail mapping, empty/malformed/partial/
   unknown/duplicate/missing results, process/result contradiction, artifact
   validation, and stable trace identity.
9. **Coverage/closure tests:** hit/miss, illegal/ignore/excluded/waived/
   unreachable, zero denominator, stale/orphan points, partial parameter matrix,
   and strict status.
10. **End-to-end public workflow:** analyze, plan, generate, run, coverage,
    review/status through installed public CLIs and artifacts.
11. **Real-tool qualification:** exact qualified tool versions, good DUT,
    complete mutation/negative matrix, repeatability, and retained evidence.
12. **Security/adversarial tests:** malformed/untrusted input, path/symlink
    escape, unsafe command/environment, secret redaction, plugin/signature/
    entitlement failures, and resource exhaustion.
13. **Concurrency/recovery tests:** repeated/parallel execution, collision,
    interruption at each publication boundary, restart/recovery, and stable
    ordering.
14. **Compatibility/package/platform tests:** old state, upgrade/downgrade/
    rollback, wheel contents/entry points, supported OS/tool combinations, and
    absent optional packages.
15. **Documentation contract tests:** commands, links, schemas, feature IDs,
    capability states, evidence paths, edge-case table, and acceptance record.

<a id="source-docsplanningmissing-workmd--niche-edge-case-discovery-procedure"></a>
##### Niche edge-case discovery procedure

Before coding, the agent must:

1. Draw the feature's input partitions and state machine, including failure and
   recovery states.
2. Enumerate numeric/string/collection/time/resource boundaries using minimum,
   minimum-plus-one, nominal, maximum-minus-one, maximum, and outside-range
   values where meaningful.
3. Enumerate pairwise interactions. Use a full Cartesian matrix for interacting
   semantic fields; reduce it only with a written equivalence argument.
4. Fault-inject every external boundary: file, parser, schema, frontend, plugin,
   executable, license, entitlement, solver, simulator, result file, coverage
   database, signature, clock, timeout, process, and publication.
5. Add one semantic mutant for every rule whose accidental inversion/removal
   could let an incorrect DUT or configuration pass.
6. Fuzz bounded parsers/decoders with malformed, truncated, oversized, deeply
   nested, duplicate, unknown, encoding, quoting, and path inputs.
7. Differentially compare frontends/tools only where both are authoritative
   for the selected fact; classify legitimate differences rather than masking
   them.
8. Exercise concurrency, cancellation, stale caches/provenance, upgrades,
   downgrades, and interrupted atomic writes.
9. Review the global cross-cutting edge-case table and the ticket-specific table
   line by line. Record every case as tested, unsupported, or technically not
   applicable in the feature coverage ledger.
10. Have a reviewer inspect surviving mutants, untested branches, skipped tools,
    `not_applicable` entries, and reduced cross-products before promotion.

<a id="source-docsplanningmissing-workmd--backlog-wide-feature-coverage-index"></a>
##### Backlog-wide feature coverage index

This table supplements, but does not replace, each ticket's implementation
playbook and the 15 mandatory test layers.

| Ticket | Intended feature | Mandatory domain-specific niche coverage |
| --- | --- | --- |
| `QUAL-01` | Current, typed, commit-aware qualification enforcement | Closed-schema fields, every evidence type, missing/tampered/stale/wrong-commit/wrong-workflow/wrong-lock/wrong-tool records, impact-map boundaries, accepted-stage sequencing, skipped/cancelled/partial jobs, historical-versus-current use, exact diagnostic and exit behavior |
| `RELEASE-01` | Exact-tag tested build, signing, and publication | Alpha/beta/RC/GA/final/patch version matrix, malformed/moved/deleted tag, tag/SHA/version mismatch, absent/failed/skipped/cancelled/stale CI, artifact substitution, provenance/ref/builder mismatch, duplicate publication/rerun, environment denial, signature and private-index failures |
| `SCALE-02` | Real candidate-versus-baseline performance qualification | Actual installed-wheel product stages, independent candidate/baseline commits and wheels, identical fixtures/profile, cold/warm runs, process-isolated RSS/CPU/I/O, multiple repetitions/outliers, exact/over threshold, faster candidate, baseline promotion, runner drift, WSL absence, artifact expiry |
| `AI-03` | Safe and deterministic Headroom/code-graph optimization | Explicit enable/disable and stage policy, no-model/network-denied/cache-hit behavior, healthy/slow/hung/crashed/malformed/oversized MCP, partial frames/wrong IDs, redirect and DNS changes, environment/secret inheritance, timeout/cancel/signal, descendant cleanup, file-descriptor/process census, version/protocol/graph provenance |
| `TIER-01` | Free/Enterprise packaging and entitlement | Every plan/capability/time/trust/upgrade/downgrade transition; missing/private package combinations; pre-side-effect gates; Free/Enterprise byte equivalence; direct API/plugin bypass attempts |
| `BOARD-01` | One exact enterprise board profile | Board/revision/part/pin/clock/reset/constraint/device identity; safe constraint parsing; tri-state/open-drain; stale vendor facts; wrong-board mutants; digital-versus-physical boundary |
| `SEM-01` | One SystemVerilog semantic family | Width/signedness/context sizing, X/Z, casts, aggregate/range direction, operator precedence, generate activity, package/interface identity, source location, frontend disagreement, unsupported-neighbor mutant |
| `SEM-02` | Mixed-language elaboration | Library/case/unit/architecture selection, compile order, generic/parameter adaptation, scalar/vector/range/type/direction conversion, unresolved/duplicate binding, black boxes, cross-language clock/reset identity |
| `SEM-03` | Frontend/tool/design qualification breadth | Minimum/maximum accepted patch versions, known diagnostic/AST differences, large/deep designs, inactive generate, license/provenance, resource budgets, unqualified version, source/tool changes with stable versus changed normalized facts |
| `FORM-01` | One new formal semantic extension | Syntax/model boundaries, engine capability, assumption consistency, reachability/non-vacuity, bounded/unbounded distinction, base/step/cover outcomes, timeout/unknown, counterexample mapping, one mutant per property rule |
| `CDC-01` | One advanced CDC structure | Clock ratio/phase extremes, source event rate, pulse width, reset ordering, data stability, stage observability, branching/reconvergence, Gray transitions/wrap, FIFO full/empty boundary where applicable, structural and behavioral mutants |
| `RDC-01` | Physical reset/power evidence import | Units, corners, modes, hierarchy aliases, hidden paths, recovery/removal boundary, power-good/isolation/retention order, waiver validity, tool/constraint/netlist staleness, physical failure versus logical pass |
| `MEM-01` | One additional memory behavior | Minimum/maximum depth/width/ports, same/different address collisions, byte lanes, arbitration races/wrap, reset/init, async timing, ECC bit positions/syndromes, scrub/read/write/injection races, retention/macro delegation |
| `PROTO-01` | One broad protocol profile/role/target | Legal/illegal handshake ordering, min/max burst/size/outstanding, stalls/backpressure, response/error/retry, ID/order/wrap, sideband stability, reset mid-transaction, endpoint role, multiple instances, one mutant per rule |
| `PROTO-02` | One extension to an existing bounded protocol | Old-bound regression plus new boundary, migration, optional-signal combinations, scoreboard key collisions, simultaneous channels, timeout/recovery, feature-disabled behavior, every claimed target independently |
| `PERIPH-01` | One generic peripheral feature | UART divisor/phase/frame variants; SPI CPOL/CPHA/CS/bit order/contention; I2C START/address/ACK/stretch/arbitration/stuck bus; GPIO/timer/IRQ mask/clear/wrap/DMA/backpressure as applicable |
| `VHDL-01` | One additional native VHDL profile | Case-insensitive names, libraries/architectures/configurations, compile order, generics, constrained/unconstrained arrays, ascending/descending ranges, records/subtypes, resolved signals/multiple drivers, delta cycles, standard/version differences |
| `UVM-01` | Richer vendor-executed UVM | Phase/objection completion, zero transactions, passive/active agents, factory overrides, sequence deadlock, reset interruption, analysis fanout/copy/clone, scoreboard ordering, RAL mirror/predict races, compile/library dialect, error/fatal parsing |
| `TOOL-01` | One licensed simulator/formal adapter | Executable/version/license lifecycle, wrapper/path/environment security, timeout/signal/process cleanup, structured/partial/malformed result, unknown checks, counterexample/artifact escape, stale provenance, signed real-tool evidence |
| `COV-01` | One vendor/formal coverage import | Stable point identity, cumulative/per-run merge, duplicate import, goals/counter overflow, bins/crosses, illegal/ignore/excluded/waived/unreachable, source movement, parameter specialization, stale tool/database, zero denominator |
| `COV-02` | Generated functional coverage | Sampling event, boundary/default/transition bins, cross Cartesian size, illegal/ignore overlap, unreachable bin proof, reset sampling, duplicate IDs, known hit/miss, mutant avoiding mandatory bin, target-language compile/run |
| `DOC-01` | OCR/local retrieval adapter | Empty/corrupt/encrypted/mixed/rotated pages, encoding/language, table/diagram order, duplicate documents/pages, confidence boundaries, oversized/bomb input, timeout, source locator/bounding box, deterministic chunks, no implicit network |
| `SCALE-01` | Larger scale and scheduling after `SCALE-02` | Preserve installed-wheel independent-baseline validity; cold/warm cache, one/many modules, deep/wide AST, huge documents, CPU/memory/file/process limits, license starvation, fairness/deadlock, cancellation, cache stampede, concurrent publication, noisy worker, partial aggregate |
| `PLAT-01` | Additional deployment platform | Filesystem case/permissions/symlink/path length, drive/UNC syntax, line endings, locale/timezone, signal/process groups, executable suffix, container UID/rootless behavior, tool absence/version, reproducibility and upgrade/rollback |
| `AI-01` | Optional model-authored executable artifacts, if approved | Prompt/source injection, malformed/nondeterministic output, unsafe dependencies/commands, secret/license leakage, approval identity, sandbox/resource failure, compilation/mutation/closure, cache model/prompt/context identity |
| `AI-02` | Optional provider routing/fallback, if approved | Provider/model/destination policy, outage/rate/auth/cost limits, cross-provider data boundary, retry/fallback ordering, result disagreement, cache separation, audit/redaction, no silent provider/model change |
| `PHYS-01` | Physical-sign-off integration boundary, if approved | Units/corners/modes/libraries/netlist/constraints, black boxes, hierarchy mapping, false/multicycle paths, waivers, analog thresholds, stale layout, incomplete reports, tool disagreement, absence-of-violation not treated as pass |

For combined tickets such as `PROTO-01`/`PROTO-02` or `COV-01`/`COV-02`,
create separate feature coverage records. A shared implementation helper does
not justify a shared support result.

<a id="source-docsplanningmissing-workmd--p0-release-blockers-and-claim-reconciliation"></a>
#### P0: release blockers and claim reconciliation

<a id="source-docsplanningmissing-workmd--qual-01-make-accepted-qualification-stages-current-typed-and-mandatory"></a>
##### `QUAL-01` Make accepted qualification stages current, typed, and mandatory

**Status:** closed 2026-07-29. **Priority:** P0. **Depends on:**
`SCALE-02` for replacement performance evidence. `RELEASE-01` must consume the
resulting contextual verifier rather than reimplementing qualification logic.

**Closure evidence:** The merged Ubuntu candidate bundle passed contextual
candidate-mode validation. The active ledger now requires Ubuntu 24.04 only;
WSL2 evidence is historical and excluded from current qualification. The
implementation details below are retained as historical closure context.

**Current condition:**

- The main `quality-and-pilot` job explicitly runs
  `ga_gates.py --through-stage 9` even though the ledger and qualification
  operations document say Stages 6-10 are accepted. A unit test calls
  `enforce_through(..., 10)`, but it validates the checked-in ledger state; it
  does not produce fresh Stage 10 evidence.
- `ga_gates.py` manually validates part of the ledger and mostly treats an
  evidence path as valid when the path exists. Stage Markdown, performance
  JSON, and OCI runtime JSON do not all pass a type-specific validator in the
  gate command. Unknown schema fields and several malformed nested values are
  not governed by the packaged closed JSON schema.
- Checked-in Stage 10 records are historical. The external-design records,
  scale records, and OCI runtime record identify commits older than `HEAD`.
  This is valid historical evidence, but `ga_gates.py --through-stage 10`
  cannot distinguish it from evidence suitable for the current candidate.
- `ga_evidence.py verify` validates payload integrity and field shapes. It does
  not validate the stage range, compare the recorded commit/tree/workflow/
  lockfile against a supplied checkout, recompute artifact hashes, require
  coverage policy thresholds, or establish that tests, coverage, and artifacts
  came from one job. `generate()` accepts the last passing unittest summary in
  a concatenated log instead of rejecting multiple or contradictory runs.
- The sandbox test skips when required OCI evidence is missing. That behavior
  can turn removal of an accepted Stage 10 input into a skip instead of a direct
  test failure.
- Stage 10 scale runs are narrowly path-triggered, and WSL runs only on manual
  dispatch. Changes to shared source, dependencies, packaging, schemas, or
  benchmarked parsers can avoid the dedicated workflow.
- `.github/actionlint.yaml` exists, but no mandatory job validates workflow
  syntax or tests the semantic release/qualification matrix.

**Required architecture:** separate three concepts in machine state:

1. `historical_acceptance`: immutable evidence that established a bounded claim
   at its recorded source/tool/platform identities.
2. `candidate_validation`: evidence generated for the exact candidate commit,
   workflow, lockfile, package, profile, target, and required tools.
3. `reusable_evidence`: explicitly permitted evidence whose validity is bound
   to a versioned impact key and freshness policy, such as a licensed run that
   is not invalidated by documentation-only changes.

Presence, a payload digest, or a prior accepted status cannot automatically
convert the first category into either of the latter categories.

**Step-by-step implementation plan:**

1. Add a closed `qualification-gate-v2` policy/schema. Define every stage,
   profile, target, required evidence type, validator, required freshness mode,
   impact inputs, maximum age where applicable, required signer/trust policy,
   and minimum current-candidate checks. Reject unknown fields and duplicate
   stage/profile/evidence IDs.
2. Introduce a typed evidence-validator registry keyed by evidence type, not
   filename. At minimum register stage acceptance, GA run, external design,
   performance, OCI sandbox, vendor attestation, enterprise pilot, release
   artifact, SBOM, provenance, and signature evidence. Each validator returns
   normalized identity, status, freshness, and exact diagnostics.
3. Extend `ga_evidence.py verify` with contextual inputs:
   `--root`, `--artifacts`, `--expected-stage`, `--expected-commit`, and
   `--policy`. Recompute tracked-tree, CI workflow, lockfile, and artifact
   digests. Compare exact values and reject symlinks, path escapes, missing/
   extra artifacts, wrong stages, unknown fields, unsupported schema versions,
   and non-passing policy thresholds.
4. Replace free-form unittest-log matching with a machine result manifest
   written by the test job. Until that migration is complete, require exactly
   one final unittest summary, reject any `FAILED`, `ERROR`, traceback,
   interrupted, or additional `Ran N tests` summary, and bind the log hash into
   the evidence.
5. Add a candidate evidence bundle manifest that binds all component evidence
   by digest and records GitHub run/job/attempt, commit, ref, workflow digest,
   lockfile, built wheel/sdist, Python/platform, tools, test result, coverage,
   qualification profiles, skips, and artifact set. A component cannot be
   substituted after the bundle is created.
6. Implement a versioned impact-key builder. Hash all source, schema, template,
   fixture, package metadata, lockfile, workflow, tool-policy, and profile files
   that can affect a reusable evidence item. Store the exact path set and hash
   algorithm. A changed or newly relevant path invalidates reuse; an unknown
   path classification fails closed and requests fresh evidence.
7. Make `ga_gates.py` accept a mode: `ledger` for structural/historical
   inspection and `candidate` for release/CI. Candidate mode receives the
   bundle plus expected checkout identity, validates every required evidence
   type, resolves freshness/impact policy, and rejects historical-only records
   where current evidence is required.
8. Change the mandatory CI gate to Stage 10 candidate mode. Generate current
   test/coverage/build evidence in the same job. Download and contextually
   validate evidence from dedicated Ubuntu/WSL/vendor jobs only through exact
   workflow-run artifact IDs and expected commit/impact keys.
9. Remove skip-on-missing behavior for every evidence item declared mandatory
   by the active gate. Optional deployment tests may skip only when their
   profile is excluded from the candidate policy, and the bundle must record
   that exclusion.
10. Expand scale-workflow triggers to the impact set produced by `SCALE-02`.
    Define how WSL evidence is obtained: required self-hosted run, scheduled
    freshness record, or explicit conservative removal of WSL from the current
    candidate claim. Runner unavailability must not silently reuse invalid
    evidence.
11. Add pinned `actionlint` execution and repository tests that parse workflow
    events, path filters, dependencies, stage arguments, artifact names, and
    SHA handoff. String-presence assertions are insufficient for release
    semantics.
12. Update qualification operations, stage records, capability state, and
    acceptance documents to label historical versus current evidence. Publish
    exact commands for local candidate verification without implying that
    ledger syntax runs the product tests.

**Required edge-case behavior:**

| Case | Required resolution |
| --- | --- |
| Evidence file is absent, symlinked, malformed, empty, or newer-schema | Reject the owning stage/profile with evidence ID, validator, path, and exact reason. Never skip a mandatory record. |
| Payload digest is valid but artifact files differ | Reject contextual verification and list missing, extra, and digest-mismatched subjects. |
| Recorded commit is valid hex but not the candidate commit | Accept only as historical/reusable under an exact matching impact policy; otherwise require a new run. |
| Candidate source is unchanged but workflow, lockfile, schema, template, fixture, or tool policy changed | Invalidate every evidence type whose declared impact set contains the changed input. |
| A new source path is not classified by the impact policy | Fail closed as `impact_unknown`; do not assume it is documentation-only. |
| Multiple test summaries, an earlier failure followed by a pass, or a truncated log | Reject the test component. One passing suffix cannot erase a failed/interrupted run. |
| Tests pass but branch/global/per-file coverage policy fails | Candidate evidence is failed even if numeric coverage fields are well formed. |
| Required tool test is skipped or the job is cancelled/timed out | Record the job state and keep the profile non-closing. A rerun must replace the entire affected component, not splice results. |
| Historical evidence has no recoverable impact key | Preserve it as historical acceptance only; never use it for candidate promotion. |
| WSL/self-hosted runner is offline or queued past policy | Report deployment evidence unavailable and block only the claims that require it; never manufacture Ubuntu equivalence. |
| Workflow artifact retention expired | Require a new run or an approved immutable evidence archive with independently verified identity. |
| Pull request originates from a fork without protected evidence access | Run unprivileged open-tool checks; defer protected evidence without exposing secrets and prevent merge/promotion until required trusted jobs complete. |
| GitHub reruns only one failed job | Bind run attempt and all downloaded component IDs; reject mixed attempts unless the bundle policy explicitly permits and verifies each replacement. |

**Test plan and completion evidence:**

1. Unit-test every schema field, evidence-validator type, normalized identity,
   impact-key rule, freshness state, diagnostic, and exit code.
2. Build temporary Git repositories for exact commit, dirty tree, detached HEAD,
   shallow clone, submodule, tracked symlink, renamed path, changed workflow,
   changed lockfile, and changed artifact cases.
3. Generate valid candidate evidence, then independently mutate every bound
   dimension. Each mutation must fail for its own identity, not only a payload
   digest.
4. Test all unittest-result contradictions, coverage threshold boundaries,
   zero branches, missing per-file data, allowed optional skips, and required
   skips.
5. Test the complete Stage 6-10 matrix with historical-only, current, reusable,
   stale, mixed-run, wrong-stage, and missing-type records.
6. Test workflow contracts for push, pull request, fork, manual, schedule,
   cancellation, retry, and self-hosted runner states.
7. Run Stage 10 candidate mode against one clean exact checkout and retain the
   resulting bundle. The command must fail after changing any impact input and
   pass again only after producing the required replacement evidence.

**Acceptance evidence:** mandatory CI executes Stage 10 candidate mode;
historical Stage 10 files remain readable but cannot impersonate current
evidence; type-specific and contextual mutation tests pass; missing sandbox or
scale evidence fails directly; workflow semantics pass actionlint and contract
tests; and release can consume one immutable exact-candidate bundle.

<a id="source-docsplanningmissing-workmd--release-01-bind-every-publication-to-exact-tag-ci-and-qualification"></a>
##### `RELEASE-01` Bind every publication to exact-tag CI and qualification

**Status:** confirmed release-control defect. **Priority:** P0. **Depends on:**
`QUAL-01`. Product/release owners must define supported release channels and
the minimum gate for each before publication is enabled.

**Current implementation:** Channel policy parsing, exact tag target
verification, exact-SHA Stage 10 bundle handoff, build-once release manifest
creation/verification, fail-closed publication idempotency, exact-wheel
reinstall, and signed recovery-record generation are implemented. A protected
private-index dry run remains open; local disposable-index recovery evidence is
retained in `qualification/evidence/release-01-publication-dry-run-v1.json`.

**Current condition:**

- The release workflow requires a successful Stage 10 candidate bundle whose
  workflow run, commit SHA, and candidate artifact are all checked before
  building. Channel policy then selects the minimum ledger stage.
- The workflow is wired to a protected private-index environment, but the
  repository still needs one retained dry-run against its configured index to
  demonstrate destination responses and recovery evidence.
- Build provenance records a commit, ref, tag, lockfile, and subjects, but
  `verify_materials.py` validates several identities by shape instead of
  comparing them with `GITHUB_SHA`, repository, workflow/ref, and the exact
  checked-out lockfile.
- Package/version matching, reproducible builds, clean-wheel smoke, GitHub
  attestations, Sigstore signing, and private-index reinstall are useful
  controls, but they do not compensate for a missing exact-source quality and
  qualification gate.

**Step-by-step implementation plan:**

1. Add a versioned release-channel policy with parsed PEP 440 version, allowed
   tag pattern, channel (`development`, `alpha`, `beta`, `rc`, `ga`, `patch`),
   minimum qualification stage/profile set, destination index, approval
   environment, and whether publication is permitted. Do not hardcode one
   product version in shell `case` branches.
2. Make `scripts/release/version.py` parse and return a machine-readable
   release decision. Reject leading-zero/ambiguous/malformed versions,
   unsupported local/dev/post forms, tag/package mismatch, unapproved channel,
   and a stable or patch release whose gate is weaker than policy.
3. Choose one exact-SHA CI handoff architecture: preferably a reusable
   mandatory validation workflow called by both CI and release, or a release
   job that reruns the same commands. If prior CI artifacts are reused, query
   by immutable workflow ID and exact SHA, require a successful non-cancelled
   trusted run, and verify its `QUAL-01` candidate bundle.
4. Require the exact checkout SHA to equal the immutable tag target before any
   dependency install/build. Reject annotated/lightweight tag ambiguity, moved
   tags, a tag resolving through an unexpected object, and a checkout/ref
   mismatch.
5. Run or verify all mandatory gates: Ruff lint/format, mypy, compatibility,
   maintainability, repository contracts, secrets, Bandit, dependency audit,
   full tests with branch coverage/ratchets, required real-tool pilots,
   reproducible distributions, installed-wheel smoke, and the channel's
   contextual qualification stage.
6. Build once from the validated exact checkout. Bind source commit/tree,
   workflow, lockfile, build command/image, package metadata, wheel/sdist,
   SBOM, checksums, provenance, test/coverage evidence, and qualification
   bundle into one release manifest before attestation.
7. Extend release-material verification with expected repository, commit, ref,
   tag, workflow identity, lock digest, package name/version, builder identity,
   and exact subject set. Reject valid-looking but wrong-context provenance,
   duplicate subjects, unlisted extra distributions, and artifact substitution.
8. Pass artifacts only by immutable workflow artifact ID/digest between jobs.
   After every download, revalidate release manifest, checksums, provenance,
   attestations, and expected SHA before signing or publishing.
9. Keep signing and publishing behind the protected channel-specific
   environment. Use OIDC/trusted publishing where available; do not construct
   credential-bearing index URLs. Ensure logs, errors, and support artifacts
   cannot expose index credentials. **Implemented in the release workflow; a
   protected dry run remains to be retained.**
10. Make publication idempotency explicit. **Implemented by
    `scripts/release/publication.py` and the protected workflow.** Before upload, query the destination
    for the exact name/version and digest. A matching immutable artifact yields
    a verified no-op; a different artifact under the same version is a hard
    conflict. Never use `--skip-existing` to hide mismatches.
11. Reinstall the exact published digest, not merely the same version string,
    in a clean environment. Run both console entry points, packaged-resource
    checks, Free/Enterprise boundary checks once `TIER-01` exists, and one
    minimal end-to-end project workflow.
12. Emit a signed release record containing approvals, all run/evidence/
    artifact identities, publication destination/result, and reinstall result.
    Update the ledger only from that record; a failed or partially published
    run remains failed and requires governed recovery.

**Release edge-case matrix:**

| Case | Required resolution |
| --- | --- |
| Current `v0.1.0` tag with Stage 11-13 pending | Follow explicit channel policy. Until one exists, fail closed before build/publication. |
| `v1.0.0rc1`, `v1.0.0rc2`, `v1.0.0`, `v1.0.1`, and next-major tags | Resolve channel and gate from policy; no exact-version shell exception. Stable/patch must never use a weaker default arm. |
| Tag matches package version but points at a commit with failed/missing CI | Reject before build and report exact check/evidence state. |
| Passing CI belongs to another SHA, workflow digest, lockfile, or run attempt | Reject as stale/mismatched; do not select the latest green run by branch name. |
| Tag is moved after a run starts | Re-resolve before signing and publication; abort if target differs from the checked/attested SHA. |
| One matrix job is skipped, cancelled, timed out, or neutral | Treat mandatory validation as not passed even if an aggregate check appears green. |
| Artifact is rebuilt in a later job | Reject. Only the build-once subjects in the release manifest may proceed. |
| Provenance has valid syntax/signature but wrong repository/ref/SHA/builder | Reject contextual verification. |
| Signing succeeds but publication fails | Retain signed unpublished artifacts and failed release record; retry publication only after revalidation and approval. |
| Publication succeeds but reinstall fails | Mark release verification failed, prevent promotion to a stronger channel, and open recovery; do not overwrite the published version. |
| Version already exists with identical digest | Verify remote digest and record idempotent success without uploading replacement bytes. |
| Version already exists with different digest | Hard fail and escalate as a supply-chain conflict. |
| Fork/untrusted actor creates a tag-like ref | Protected tag/environment policy and repository identity checks must prevent credential/signing access. |

**Test plan and completion evidence:**

1. Unit-test every supported/unsupported version and tag form, channel
   transition, required stage, destination, and diagnostic.
2. Add workflow-contract fixtures for exact green SHA, wrong SHA, absent check,
   failed/skipped/cancelled matrix member, stale artifact, moved tag, rerun
   attempt, and environment rejection.
3. Mutation-test every release manifest identity and subject digest.
4. Run a non-publishing dry run through validation, build once, clean installs,
   materials, attestation verification, keyless-signature verification, and
   reinstall from a disposable test index.
5. Prove a current `v0.1.0`-shaped tag cannot bypass the declared minimum gate
   and a future patch tag cannot fall through to ledger-only validation.
6. Retain one exact-SHA dry-run release record and verify that changing source,
   workflow, lockfile, tag, package version, or any artifact causes rejection.

**Acceptance evidence:** every publishable tag channel has an explicit policy;
release is blocked before build on missing exact-SHA validation; all materials
and signatures bind the expected repository/ref/SHA/subjects; idempotency and
partial-failure recovery are tested; and no default tag branch can publish from
ledger syntax alone.

<a id="source-docsplanningmissing-workmd--scale-02-replace-the-self-comparison-benchmark-with-product-evidence"></a>
##### `SCALE-02` Replace the self-comparison benchmark with product evidence

**Status:** closed 2026-07-29 for the Ubuntu-only current claim. **Priority:** P0 for any
current performance-regression or installed-wheel scale claim. **Depends on:**
an immutable accepted baseline store, representative fixtures, and trusted
Ubuntu/WSL runners.

**Closure evidence:** The Ubuntu workflow built and installed distinct
baseline/candidate wheels, compared independent v3 records, and passed the
candidate gate. WSL2 is explicitly non-current; its prior records remain
historical. The implementation details below are retained as historical closure
context.

**Current condition:**

- `scale-qualification.yml` builds one candidate wheel, then invokes
  `dv-enterprise benchmark` twice against that same checkout and wheel, naming
  the two records `baseline` and `current`.
- `performance.py` requires schema-v2 baseline and current records to have the
  same `commit`, `wheel`, input fingerprints, tool versions, and reproducibility
  fields. It therefore rejects a real prior-release baseline with a different
  commit or wheel. The 10% comparison measures repeat-run variation, not a
  code/package regression.
- All checked-in accepted Ubuntu and WSL `baseline`/`current` pairs identify the
  same commit and wheel digest.
- `--wheel` only hashes the wheel into evidence. The workflow runs
  `uv run dv-enterprise benchmark` from the source environment; it does not
  install or execute that wheel.
- The measured stages are `rtl_scan` (newline count), `xml_parse` (generic
  element count), and `pdf_parse` (text extraction). They do not execute the
  product's RTL frontend/normalization, document indexing, planning,
  generation, persistence, status, or package entry points.
- `resource.getrusage(RUSAGE_SELF).ru_maxrss` is process-lifetime cumulative.
  All stages run in one process, so later stage memory values include earlier
  high-water marks and no child-process memory is measured.

**Step-by-step implementation plan:**

1. Define `performance-qualification-v3` with independent `baseline` and
   `candidate` identities. Require profile/case version, source commit/tree,
   package digest, fixture digest, command/stage contract, platform/runner
   class, dependencies/tools, repetition index, cold/warm state, wall/CPU time,
   process-tree peak RSS, I/O/output metrics, exit/status, and payload digest.
2. Define comparability separately from equality. Fixture/profile/stage
   semantics, platform class, architecture, Python/tool major policy, resource
   limits, and measurement method must be compatible. Baseline and candidate
   commit/package digests must normally differ and remain independently
   recorded.
3. Add immutable baseline promotion. A baseline is produced from an accepted
   release/candidate, reviewed, signed or stored in an immutable trusted
   artifact location, and referenced by ID/digest. Pull requests may read a
   baseline but cannot overwrite/promote it.
4. Build the candidate wheel once, install it into a clean isolated environment,
   and run all benchmark commands through that environment's `dv-platform`/
   `dv-enterprise`. Record the installed distribution and entry-point path and
   reject source-tree imports.
5. Replace generic proxy operations with bounded real workflows:
   frontend discovery/normalization on a representative large but legal RTL
   project; documentation ingest/index/search on XML/PDF fixtures; deterministic
   planning and one representative generation/status path; artifact/state
   persistence and reload. Keep fixture generators deterministic and record
   expected semantic/output counts so a faster no-op cannot pass.
6. Run each stage in a fresh child process or isolated worker with a fixed
   environment, timeout, CPU/memory/file/process limits, and bounded output.
   Measure wall time, user/system CPU, process-tree peak RSS, bytes read/written,
   and output size/count. Validate exact functional results before accepting
   metrics.
7. Separate repeatability from regression. Run candidate warmups plus at least
   the policy-defined repetitions; report median and a robust spread/upper
   statistic. Compare candidate statistics with the immutable baseline and
   independently reject excessive within-candidate variance.
8. Define absolute budgets as well as relative regression limits. A very slow
   baseline cannot authorize an unusable candidate, and a very fast but
   functionally incomplete candidate cannot pass.
9. Version runner classes and calibration. Record CPU model/count, memory,
   virtualization, kernel, filesystem, load/noise indicators, and CI image.
   Incompatible runner drift requests a newly approved baseline instead of
   comparing incomparable numbers.
10. Expand workflow impact triggers to all benchmark/product source,
    dependencies/lockfile, package metadata, schemas/templates, fixtures,
    policies, and workflow files. Run Ubuntu automatically. Run WSL whenever
    WSL support is claimed or retain a still-valid impact-bound WSL record under
    `QUAL-01`; otherwise downgrade the current WSL claim.
11. Publish candidate raw repetitions, normalized aggregate, comparison,
    functional result manifest, logs, and exact baseline reference as one
    evidence bundle. Add contextual validation to `QUAL-01`.
12. Migrate v2 records as historical repeatability evidence only. Do not relabel
    the same-commit pairs as historical performance-regression baselines.

**Required edge-case behavior:**

| Case | Required resolution |
| --- | --- |
| Baseline and candidate use the same commit/wheel | Permitted only for repeatability calibration, never labeled regression comparison. |
| Candidate differs only by documentation outside the impact set | Reuse may be allowed only when the versioned impact classifier proves no benchmark stage input changed. |
| Candidate is faster because a stage skipped work or emitted fewer facts/chunks/artifacts | Functional count/hash/status mismatch fails before performance comparison. |
| Candidate improves one stage but regresses another | Evaluate every mandatory metric/stage independently; aggregate speed cannot hide a stage breach. |
| Measurement is exactly, just below, or just above 10% | Use documented precision and comparison rule; exact boundary behavior must be deterministic and unit-tested. |
| Baseline metric is zero, missing, NaN, infinity, boolean, or negative | Reject evidence rather than divide, coerce, or report an infinite improvement. |
| One repetition is an outlier or runner load is high | Apply the approved robust statistic and variance/noise gate; do not delete an outlier without recording policy and raw result. |
| Baseline artifact expired or signer/trust is invalid | Require a replacement approved baseline; do not fall back to the candidate's first run. |
| Runner hardware/kernel/image changes | Classify against runner-compatibility policy; incomparable runs cannot pass or fail a code regression claim. |
| WSL runner is unavailable | Block/downgrade WSL current support while allowing independently satisfied Ubuntu claims. |
| Child process times out, is killed, exceeds limits, or leaves descendants | Fail that repetition, retain bounded diagnostics, and verify process-tree cleanup before retry. |
| Warm cache leaks between supposed cold runs | Use isolated cache/work directories and assert absence before the measured command. |
| Pull request attempts to promote its result as baseline | Deny by workflow permissions/environment and schema role; only reviewed protected-branch release evidence can promote. |

**Test plan and completion evidence:**

1. Unit-test v3 schema, comparability, every numeric boundary, statistics,
   absolute/relative budgets, variance, runner policy, and migration.
2. Build two fixture wheels/commits with a controlled delay or memory
   allocation and prove the candidate-versus-prior comparison detects the
   intended regression while same-candidate repetitions remain repeatability
   evidence.
3. Add a mutant that skips each product stage or emits incomplete results; it
   must fail functional validation before metrics can pass.
4. Verify clean-wheel execution by making source-tree import fail and checking
   the recorded executable/distribution digest.
5. Exercise cold/warm, cache contamination, parallel runner load, timeout,
   cancellation, partial artifacts, baseline expiry, incompatible runner, and
   WSL-unavailable cases.
6. Produce one Ubuntu candidate bundle against an independently created
   immutable baseline. Produce WSL evidence or mark WSL non-current. Validate
   both through `QUAL-01`.

**Acceptance evidence:** the candidate wheel, not the source environment, runs
real product stages; baseline and candidate have independent immutable
identities; functionality closes before metrics; process-tree resources and
repeatability are measured correctly; and an intentional >10% regression is
caught without poisoning or replacing the baseline.

<a id="source-docsplanningmissing-workmd--doc-00-reconcile-broad-protocol-capability-claims"></a>
##### `DOC-00` Reconcile broad-protocol capability claims

**Status:** blocking documentation defect. **Priority:** P0. **Depends on:**
maintainers reviewing the actual accepted fixtures and CI jobs.

**Current condition:** the current capability ledger and matrix now classify
the seven broad protocol profiles as `unsupported` for execution, matching the
protocol architecture. The remaining review is profile/role/target evidence
expansion and reconciliation of historical acceptance snapshots.

**Work package:**

1. Inventory each broad profile and target: AXI4, AXI4-Stream, Wishbone B4,
   Avalon-MM, Avalon-ST, burst AHB, and TileLink UL/UH.
2. For every profile, link the actual generator, execution adapter, good-DUT
   fixture, mutant fixture, CI job, result decoder, and acceptance record.
3. Classify each profile/target as `supported`, `partial`, `scaffold`, or
   `unsupported` using measured evidence, not generated files.
4. Update the capability matrix, protocol architecture, this backlog, and any
   release/acceptance text together. Add a documentation consistency test or
   machine-readable profile-state source so the contradiction cannot recur.

**Acceptance evidence:** a reviewable profile-by-target table with links to
fixtures and CI evidence; no contradictory state labels; strict status matches
the declared state. **Non-goal:** do not promote or demote a profile solely to
make the documents agree.

<a id="source-docsplanningmissing-workmd--bug-cdc-01-stop-synchronous-external-inputs-becoming-false-cdc-blockers"></a>
##### `BUG-CDC-01` Stop synchronous external inputs becoming false CDC blockers

**Status:** closed regression; retain as mandatory CDC/memory regression
coverage. **Priority:** historical P0. **Originally observed with:** Verilator
5.020, SBY 0.67, Yosys 0.33, and Z3 4.8.12.

**Historical failure:** the SECDED memory formal good-DUT pipeline failed before
it could qualify the claimed memory behavior. `_cdc_paths()` in
`rtl/verilator/hierarchy.py` places every top-level input that is not written by
the module and is not a clock/reset into a synthetic `external` source domain.
Any sequential process that reads such an input receives a `direct`, zero/one
stage, unsafe `RTLCDCPath`. For the bounded SECDED fixture this incorrectly
classifies `read_enable`, `read_address`, `inject_single_error`,
`inject_double_error`, and `scrub_enable` as unsafe CDC crossings even though
the explicit memory policy associates those interface controls with `clk`.
`formal/generation/cdc.py` correctly reported those unsafe paths as
unsupported, so `formal/execution.py` kept CDC closure false and the good DUT
exited 16. The 2026-07-28 full rescan now passes the SECDED good-DUT/mutant
pipeline. Reopen this ID only with new reproducing evidence; otherwise use the
cases below as regression requirements.

**Required semantic correction:** distinguish these concepts in normalized and
planned facts:

1. A true signal crossing from one known clock domain into another.
2. An explicitly asynchronous top-level input that requires synchronization.
3. A top-level interface input declared synchronous to a specific domain by a
   governed protocol/depth/binding contract.
4. A top-level input whose timing relationship is unknown.

Do not resolve the bug by declaring every external input safe or by disabling
fail-closed CDC handling. Unknown/asynchronous inputs must remain actionable,
while contract-bound synchronous inputs must not masquerade as synchronizer
paths.

**Completion evidence:**

1. The SECDED formal good DUT passes, all five SECDED mutants remain killed, and
   its CDC report contains no false memory-interface crossings.
2. An unknown external input read in a sequential domain still produces an open
   timing/CDC question and cannot silently close.
3. An explicitly asynchronous input without a qualified synchronizer remains an
   unsafe CDC blocker.
4. One external input used in two unrelated domains cannot be assigned to both
   through a single-clock policy.
5. Existing internal-domain CDC, reset/RDC, handshake, Gray, and async-FIFO
   qualification tests remain unchanged and passing.

<a id="source-docsplanningmissing-workmd--quality-01-restore-all-mandatory-ci-quality-gates"></a>
##### `QUALITY-01` Restore all mandatory CI quality gates

**Status:** closed by `f2527c8`; retain as a mandatory quality regression
record. **Priority:** historical P0.

**Historical failure:** the commands used by the `quality-and-pilot` CI job
failed in these areas:

- Compatibility fingerprints changed for the CLI, dataclasses, and modules.
- `configuration/validation.py` exceeds the 700-line module limit by 30 lines.
- `LiteLLMGateway.execute` exceeds the 75-code-line function limit by 15 lines.
- Mypy reports an unsafe `int(object)` conversion in `ai/optimization.py` and a
  tuple-width inference conflict for `lines` in `cli_handlers/dispatch.py`.
- Ruff formatting would change eight source/test files.

**Implemented correction/regression contract:** the gates were restored without
weakening their policies. Continue to review the public compatibility delta
against the last accepted release or baseline. Add compatibility shims or a
governed version change for intentional breaking changes. Split configuration
validation by concern while preserving public
imports. Extract AI request preparation/attempt handling from
`LiteLLMGateway.execute` without changing fallback, audit, repair, or hashing
semantics. Narrow optimizer metric input types before integer conversion and
give dispatch output a stable `tuple[str, ...]` annotation or branch-local
identity. Apply repository formatting only after behavioral patches are stable.

**Completion evidence:** compatibility, maintainability, Ruff lint/format,
mypy, unit tests, real-tool tests, branch coverage, and repository contract
checks all pass in the same clean checkout. Updating a fingerprint baseline or
adding a maintainability exception without an independently reviewed reason
does not close this item.

<a id="source-docsplanningmissing-workmd--doc-02-reconcile-stale-acceptance-and-production-readiness-claims"></a>
##### `DOC-02` Reconcile stale acceptance and production-readiness claims

**Status:** confirmed documentation-governance defect. **Priority:** P0.

**Current condition:** repository contracts now validate the versioned current
capability ledger and reject a broad-protocol state that is more permissive than
its evidence. Historical acceptance snapshots are explicitly labeled, while
the following successor links and current-state reconciliations remain:

- `architecture/protocol-profiles.md` and the current matrix now agree that
  broad profiles are contract/recognition-only and not executable.
- APB4, AXI4-Lite, Stage 5, memory, production-readiness, and VHDL sections now
  carry historical/current scope markers; final successor links and exact
  target evidence rows remain to be completed.
- Current profile-by-target evidence still needs to be expanded beyond the
  broad-protocol summary ledger, and historical index references require final
  review for successor links.

**Work package:** classify each document as historical stage evidence or current
release authority. Historical acceptance must retain its original bounded claim
but display a clear snapshot scope and link to later promotion evidence. Current
documents must be generated from, or checked against, one machine-readable
profile/target/evidence ledger. Extend `scripts/checks/repository_contracts.py`
beyond links and state-token presence so it verifies stable capability IDs,
target states, acceptance evidence paths, schema/profile versions, and current
test/evidence snapshot references across documents.

**Completion evidence:** no current document contradicts the ledger; historical
documents are explicitly time-scoped; SECDED support reflects a passing current
real-tool run; and a fixture that introduces a deliberate state contradiction
causes the repository contract check to fail.

<a id="source-docsplanningmissing-workmd--p1-local-optimizer-reliability-and-containment"></a>
#### P1: local optimizer reliability and containment

<a id="source-docsplanningmissing-workmd--ai-03-make-headroom-and-code-graph-optimization-explicit-and-leak-free"></a>
##### `AI-03` Make Headroom and code-graph optimization explicit and leak-free

**Status:** reproduced runtime/resource defect and untested security boundary.
**Priority:** P1. **Depends on:** no product decision. This ticket preserves AI
as advisory and must not expand model authority defined by `AI-01`.

**Current condition:**

- Headroom and code-graph now have independent `off`/`advisory`/`required`
  modes, defaulting to `off`; legacy enable fields migrate deterministically.
- Planning now applies common model stage/network/credential preflight before
  invoking an advisory optimizer; mode-off and ineligible calls do not launch.
- Code-graph construction and requests now close through `finally`, with
  process-group termination, bounded reap, and explicit pipe closure.
- During the 2026-07-28 full-suite rescan, nine
  `code-review-graph serve --tools ...` children remained alive under the test
  runner. They appeared at ten-second intervals with matching
  `ResourceWarning: subprocess ... is still running` messages. The warning and
  child census directly reproduce cleanup failure and add about one timeout per
  affected planning test when the executable happens to be installed.
- The client now owns a contained process group and passes a minimal
  non-sensitive environment; bounded MCP framing rejects oversized bodies.
- MCP headers and bodies are bounded under one deadline, cancellation is
  cooperative, and initialize protocol/capabilities are schema-checked.
- Planning records executable/version, protocol/capabilities, source commit,
  graph-index digest, command identity, call count, and optimizer outcome.
- Headroom uses a direct no-proxy, no-redirect opener, revalidates loopback DNS,
  and bounds content type and response size.
- Real fake-MCP regression tests cover healthy operation, wrong IDs, crashes,
  oversized and partial frames, cancellation, repeated process reaping, and
  file-descriptor census. Graph freshness/atomic auto-update policy and cache
  identity across optimizer upgrades remain before ticket closure.

**Step-by-step implementation plan:**

1. Version `ContextOptimizationConfig` behavior and add explicit independent
   modes for Headroom and code graph: `off`, `advisory`, and `required`.
   Default to `off` unless product policy explicitly chooses otherwise. Migrate
   legacy enable fields deterministically and warn/error on contradictory
   legacy/current values; never silently turn an explicit old `false` into on.
2. Move optimizer resolution behind common AI preflight. Define whether local
   optimization is allowed for each stage, network policy, CI mode, cache hit,
   deterministic fallback, and missing credential. Do not launch an optimizer
   when its output cannot be consumed.
3. Implement `CodeReviewGraphClient` as a context manager with idempotent
   `close()`. Wrap construction and all requests in `try/finally`. Close stdin
   to request EOF, terminate the process group, wait for a bounded grace period,
   kill the process group, wait again, and close every pipe on all normal,
   exception, timeout, cancellation, and partial-construction paths.
4. Start the server in a contained process group/session and track descendants.
   Use a minimal allowlisted environment that excludes model keys, secret
   provider values, license variables, index credentials, and unrelated user
   state. Define cwd, file/cache access, resource limits, and graph-write policy
   explicitly.
5. Replace ad hoc MCP framing with a bounded transport helper. Enforce maximum
   header bytes/count, decimal nonnegative `Content-Length`, maximum body bytes,
   complete-body reads under the same monotonic deadline, UTF-8/JSON object
   validation, response-ID uniqueness, bounded ignored notifications, and
   fail-closed EOF/protocol errors.
6. Negotiate and validate MCP protocol/capabilities/tool inventory. Check the
   required tools before calls. Record executable resolution, safe version,
   protocol, capability/tool-set digest, graph root/source commit/index digest,
   auto-update action, call count, duration, status, and content hash in
   content-free optimizer provenance.
7. Define graph freshness. If graph state is missing, built for another root,
   stale against relevant source, corrupted, locked, or schema-incompatible,
   advisory mode returns a bounded diagnostic and no context; required mode
   fails the AI stage. Auto-update must use isolated staging/atomic publication
   and cannot run implicitly in a read-only or deterministic test.
8. Add a no-redirect Headroom HTTP client or revalidate every redirect hop
   against the local-only policy. Reject credentials, userinfo, query/fragment,
   non-loopback DNS resolution, host changes, proxy use, unsupported content
   type/encoding, oversized/truncated/deep response, and response fields outside
   the bounded contract.
9. Decide exactly which prompt roles Headroom receives. If system/schema
   content is not required, omit it. If required, document and audit that local
   disclosure. Preserve anchor checks, add response-size/token-accounting
   consistency checks, and never persist raw prompt/response in optimizer
   metrics.
10. Make cache identity include optimizer mode/version/configuration and the
    hash of optimized context where it can affect a proposal. A cache created
    with stale graph or different optimizer output must not be reused as if the
    context were identical.
11. Extend `context-optimize status` and strict status with stable states and
    diagnostics: disabled, ready, missing, incompatible, stale, unhealthy,
    fallback, and required-failed. Status must be side-effect-free and must not
    start servers or mutate graph state.
12. Add deterministic fake Headroom and MCP fixtures and make all ordinary
    tests hermetic. Live optimizer compatibility tests require an explicit
    environment/profile and may never supply acceptance evidence for versions
    they do not record.

**Required edge-case behavior:**

| Case | Required resolution |
| --- | --- |
| No AI model, stage disallowed, network-denied provider, deterministic fallback, or usable cache hit | Start no Headroom request or MCP process unless an explicitly documented local-only stage still needs it; assert zero calls/children. |
| Optimizer is off but executable/service is installed | Ignore it completely; host installation must not change bytes, timing, tests, or status success. |
| Optimizer is advisory and missing/failed | Continue with original bounded context, record content-free reason/duration, and leave deterministic authority unchanged. |
| Optimizer is required and missing/failed | Fail the AI stage before provider call with stable error; deterministic non-AI workflow remains usable. |
| Process fails during constructor/initialize or before `self.process` is fully assigned | Partial cleanup is safe/idempotent and leaves no child or descriptor. |
| Server ignores EOF/SIGTERM, forks a descendant, or exits between poll and signal | Escalate by process group, tolerate already-exited races, wait/reap all owned processes, and report cleanup result. |
| Header is oversized/malformed/duplicate or body length is negative/huge | Abort boundedly, clean up, and return protocol error without allocating advertised size. |
| Body is partial, stalls, invalid UTF-8/JSON, wrong ID, duplicate ID, or notification flood | Enforce one request deadline and message-count bound; no blocking read may outlive it. |
| stdout closes while stderr remains active or vice versa | Cleanup both streams/process group; no thread/descriptor remains. |
| Cancellation/KeyboardInterrupt occurs during read, write, update, or close | `finally` cleanup runs; cancellation is not converted into a successful fallback. |
| Graph belongs to another repo/commit or changes during planning | Reject/stale the context and bind any accepted context to a stable graph snapshot hash. |
| Auto-update races with another planner or crashes mid-write | Use lock plus isolated atomic publication; readers see old complete or new complete graph, never partial state. |
| Configured command contains extra arguments or resolves through a symlink | Record canonical executable and safe arguments; apply allowlist/trust policy and avoid shell execution. |
| Child inherits secret/license/proxy variables | Negative test must prove they are absent unless a specifically named safe variable is approved. |
| Local Headroom redirects to external, hostname resolution changes, or proxy variables intercept | Reject before sending redirected request; use loopback connection policy and proxy-disabled transport. |
| Compressed output preserves text anchors but changes evidence-boundary structure or exceeds configured context | Reject and use/fail according to mode; validate full structural anchors and final bounded size. |

**Test plan and completion evidence:**

1. Add a fake MCP executable/server fixture for successful initialize/tool
   calls and one mode for every framing, timeout, crash, wrong-ID, descendant,
   signal, and cleanup case. Do not depend on a host-installed binary.
2. Assert process and descriptor census before/after each case, including 100
   repeated failures and concurrent planners. No count may grow.
3. Run affected tests with ResourceWarnings/unraisable exceptions captured as
   failures. Assert no `subprocess ... is still running` output and enforce a
   runtime ceiling that catches repeated ten-second fallback.
4. Add Headroom HTTP fixtures for direct local success, every redirect form,
   proxy environment, DNS/host variant, timeout, malformed/oversized/truncated
   body, status code, encoding, and anchor failure.
5. Test every mode/stage/preflight/cache/config migration combination in human
   and JSON status output, audit record, exit code, process count, network-call
   count, and generated planning-context hash.
6. Run one opt-in compatibility test against each qualified real optimizer
   version and retain version/protocol/graph provenance. Real compatibility
   evidence supplements, but does not replace, deterministic fake-boundary
   coverage.

**Acceptance evidence:** ordinary tests never discover or execute host
optimizers; every owned child/process group and pipe is reaped on every path;
timeouts and partial frames are bounded; redirects cannot leave loopback;
optimizer versions and graph identity are recorded; explicit off/advisory/
required behavior is stable; and a repeated-failure process census remains
zero-growth.

<a id="source-docsplanningmissing-workmd--p1-documentation-operability-and-enforcement"></a>
#### P1: documentation operability and enforcement

<a id="source-docsplanningmissing-workmd--doc-03-make-every-document-machine-classified-and-agent-operable"></a>
##### `DOC-03` Make every document machine-classified and agent-operable

**Status:** in progress; flat-layout/source-preservation foundation completed
2026-07-28, machine catalog and semantic enforcement still open.
**Priority:** P1.
**Depends on:** use `DOC-02`'s capability ledger rather than creating a second
source for capability state.

**Completed foundation:** the 2026-07-28 migration consolidated 70 prose
sources into six substantive guides plus `docs/README.md`. Each migrated source
is retained in full under a stable source anchor and is named in its guide's
source-coverage list. Root `README.md`, `SECURITY.md`, `CHANGELOG.md`, and
`progress.md` are compatibility pointers; the legal
`THIRD_PARTY_NOTICES.md`, runtime-required `skills/**/SKILL.md`, and test
fixtures remain in place. Machine compatibility/evidence JSON moved from
`docs/` to `qualification/`.

`scripts/checks/repository_contracts.py` now enforces:

- exactly seven top-level Markdown files under `docs/` and no nested Markdown;
- all 70 migrated source anchors and provenance labels;
- non-duplicated explicit anchors and valid local file/fragment links;
- presence of all 37 roadmap implementation/validation cards, including
  implementation or post-approval implementation, validation, and stop
  conditions;
- parser validity for recognized `dv-platform` command examples;
- capability-matrix schema strings and state vocabulary from the exact
  consolidated source section.

The GA ledger now references exact `docs/verification.md#source-*` sections,
and its validator rejects missing section anchors. Repository contracts,
qualification gates, compatibility, package build, Ruff, mypy,
maintainability, and the full 586-test suite pass after the migration.

**Remaining condition:** source coverage and links are machine-enforced, but
classification semantics are not. There is no versioned catalog/schema for
the 12 maintained physical Markdown files and 70 migrated source sections.
The checker does not yet validate class-specific metadata, authority,
supersession, snapshot scope, known issue IDs, capability/profile states,
non-`dv-platform` command families, marked negative examples, or
machine-readable progress transitions. Link-valid prose can therefore still
be semantically contradictory, and a historical section can look current
unless the reader follows the guide preamble and source status.

**Required behavior:** every maintained Markdown document must be discoverable
through one versioned catalog and have enough explicit metadata for an agent to
determine class, authority, scope, status, time boundary, successor, and known
issues without interpreting prose. CI must reject uncataloged files, stale or
invalid metadata, unresolved current-authority contradictions, and parser-
invalid command examples for governed command families.

**Remaining work package:**

1. Preserve the flat guide set and `CONSOLIDATED_GUIDES` source manifest.
   Treat a new nested Markdown file, missing source section, or reintroduced
   directory index as a regression. Add new prose to the appropriate guide and
   register any newly migrated source identity in the same change.
2. Add `schemas/documentation/document-catalog-v1.schema.json`. Define:
   `schema_version`, `documents[]`, unique repository-relative `path`,
   optional stable `anchor`/`source_id`, `document_type`, `authority`, `scope`,
   `status`, `snapshot_date` or `last_reviewed`, `supersedes`,
   `superseded_by`, `known_issues`, and optional `capability_ids`,
   `schema_ids`, `command_families`, and `evidence_paths`. Reject absolute
   paths, `..`, duplicate path/anchor/source IDs, unknown enum values, unknown
   fields, and an anchor that is absent from its physical guide.
3. Add
   `qualification/policies/document-catalog-v1.json`. Inventory the 12
   maintained physical Markdown files exactly once and add source-section
   records for all 70 preserved sources. Explicitly exclude generated
   build/output trees, `skills/**/SKILL.md`, and `tests/fixtures/**` for their
   separately governed runtime/test roles. Every catalog path must exist as a
   regular file inside the repository; every anchored record must resolve.
4. Normalize guide and source-section metadata by class using
   `docs/agents.md`. Preserve historical acceptance and progress
   text: add metadata and later-change links without rewriting the original
   accepted boundary. Classify the Project Progress source section as an
   append-only historical implementation ledger, not current issue/capability
   authority. Current authorities must name their machine contract and known
   regressions.
5. Continue refactoring `scripts/checks/repository_contracts.py` into focused
   checks for inventory/catalog, metadata, links/anchors, schemas, capability
   claims, commands, and progress transitions. Emit deterministic
   `path#anchor: field: reason` diagnostics and return nonzero for any error.
6. Extend anchor validation to GitHub-style generated anchors, including
   repeated headings, punctuation, inline code, Unicode, and explicit HTML
   anchors. The current explicit source-anchor check remains mandatory.
   External URLs remain outside the offline check unless a separate opt-in
   network checker is approved.
7. Add parser-only validation for `dv-platform` and `dv-enterprise`. For
   repository Python scripts, define a side-effect-free parser import or
   `--help` contract rather than executing documented operations. Parse logical
   multiline commands, environment-variable prefixes, redirections, and
   pipelines into safe command segments. Do not execute arbitrary Markdown
   shell text.
8. Connect the catalog's `capability_ids` to the machine-readable
   profile/target/evidence ledger from `DOC-02`. A current source section may
   describe a state only if the ID and state agree. A historical source
   section must carry its snapshot and may differ only when it links the later
   promotion/regression.
9. Validate `known_issues` against IDs in this backlog. Reject unknown IDs;
   permit closed IDs only with a retained historical annotation or a current
   reason.
10. Add machine-readable progress-entry metadata or a companion ledger with
    unique entry ID/date, affected ticket/capability IDs, transition, commit,
    commands/evidence, and supersession links. A closure transition must point
    to passing evidence; later regression must create a new transition rather
    than rewriting the historical closure.
11. Reconcile current backlog state with the newest valid progress transition.
    Reject an active issue whose latest transition is `closed` unless a newer
    evidence-backed `reopened`/`regressed` transition exists. Reject a progress
    closure for an unknown ticket and two conflicting same-order transitions.
12. Generate or check `docs/README.md` and guide source-coverage lists from
    catalog entries so new sections cannot become undiscoverable. Generated
    output must be deterministic and checked in with a `--check` mode.
13. Add unit fixtures for every failure class and run the checker in mandatory
    CI before documentation tests.

**Edge cases and required resolution:**

- Renamed or moved documents require one atomic catalog/link update; an old
  path may remain only as an explicit redirect/superseded record.
- Symlinked documents or catalog paths escaping the repository must reject.
- Paths that differ only by case must reject because checkout behavior varies
  across filesystems.
- A document with multiple capability states must map each statement to a
  stable capability/profile/target ID; a document-level default cannot mask a
  more restrictive row.
- Historical snapshots with no recoverable commit may use a date and evidence
  paths, but must state `commit: unknown`; they cannot become current evidence.
- An old section titled "Current baseline" inside `docs/roadmap.md` is historical
  by entry identity/date and must not be treated as the current repository
  baseline. Generate an unambiguous latest-status view from transitions rather
  than renaming or deleting historical prose.
- Progress entries with equal dates require a monotonic entry ID or recorded
  commit order. Files with pre-existing out-of-order prose are indexed by that
  machine order; do not infer chronology from physical position alone.
- A progress entry claiming tests passed without exact command/result identity
  can remain a historical note but cannot close a current ticket or promote a
  capability.
- If an issue was closed and later reproduces, append a `regressed` transition
  with new evidence and make it current. Never edit the original closure into
  a failure.
- Architecture documents may describe planned behavior, but must mark the
  corresponding capability `proposed`/`unsupported` and cannot use generated
  collateral as acceptance.
- Examples containing secrets, destructive commands, network publication, or
  licensed-tool invocation require the security/approval annotation defined by
  the catalog; syntax validity does not authorize execution.
- Commands with placeholders must use parser-valid representative values plus
  surrounding text explaining replacement. Choice-constrained CLI arguments
  such as targets cannot use literal `TARGET`.
- Code fences intentionally showing invalid input must carry a machine-readable
  exclusion/reason so the checker does not confuse negative examples with
  runnable commands.
- Documents created concurrently with catalog generation must fail `--check`
  until both changes are present; publication must be deterministic and atomic.

**Acceptance evidence:** all maintained physical Markdown files and all
preserved source sections are cataloged exactly once; every current/historical
record has valid class-specific metadata; governed command families are
checked; generated indexes/source lists are byte-stable; and negative fixtures
for missing metadata, duplicate paths/anchors/source IDs, path escapes, invalid
anchors, unknown issue IDs, stale capability states, conflicting/unknown/
out-of-order progress transitions, stale active ticket status, malformed
commands, and unmarked negative examples all fail with exact diagnostics.

**Non-goals:** do not perform network link crawling in mandatory offline CI; do
not rewrite historical conclusions; do not execute shell snippets to validate
them; do not create a second independent capability-state source.

<a id="source-docsplanningmissing-workmd--p1-product-plans-and-enterprise-board-verification"></a>
#### P1: product plans and enterprise board verification

<a id="source-docsplanningmissing-workmd--tier-01-implement-and-enforce-free-and-enterprise-plans"></a>
##### `TIER-01` Implement and enforce Free and Enterprise plans

**Status:** product direction specified; implementation absent. **Priority:**
P1. **Depends on:** product/security owners selecting the entitlement issuer,
signature trust roots, offline expiry/grace policy, private package index, and
upgrade/downgrade support policy.

**Current condition:** `dv-platform`, `dv-enterprise`, and all built-in
enterprise adapter entry points ship from the same wheel. Configuration can
request enterprise adapters without a product-plan check. The platform has
vendor qualification policy and licensed-job concurrency limits but no
entitlement authority. Therefore the current repository cannot reliably
distinguish a Free installation from an Enterprise installation.

**Required architecture:**

1. Define stable product capability IDs instead of scattering string checks:
   `core.digital.analyze`, `core.digital.generate`,
   `core.digital.execute.open`, `core.formal.generate.symbiyosys`,
   `core.formal.execute.symbiyosys`, `enterprise.eda.execute`,
   `enterprise.vendor.qualify`, `enterprise.vendor.coverage`, and
   `enterprise.board.verify`. The Free capability set is built into the core;
   Enterprise adds grants and must never remove a Free capability.
2. Add a closed `schemas/product/product-entitlement-v1.schema.json`. An
   Enterprise entitlement must include schema version, entitlement ID,
   organization ID, plan ID, capability grants, issue/not-before/expiry times,
   issuer/key ID, optional deployment constraints, and a signature over
   canonical bytes. Do not store vendor license values, private keys, customer
   source identities, or payment data.
3. Add immutable product-plan/entitlement domain models and a single resolver.
   No entitlement present means `free`. A valid signed Enterprise entitlement
   means `enterprise` with its exact capabilities. A configured but malformed,
   untrusted, not-yet-valid, expired, or organization-mismatched entitlement is
   `invalid`, not silently accepted or converted into a grant.
4. Keep Free offline and account-free. Entitlement verification must be local
   against installed trust material. If online refresh is later added, it must
   be optional for Free, explicitly configured for Enterprise, bounded,
   auditable, and unable to expose source or license-server data.
5. Split packaging so `dv-platform` remains the Free/core wheel and a private
   `dv-platform-enterprise` wheel/plugin supplies `dv-enterprise`, proprietary
   runner registrations, vendor qualification assets, and board workflows.
   Keep adapter protocols and normalized result schemas in core so Free can
   read historical Enterprise results. During migration, the existing bundled
   `dv-enterprise` entry point may remain only if every privileged operation
   fails before adapter/plugin loading without a grant.
6. Add a central `require_capability()` gate. Apply it before enterprise plugin
   discovery/import, tool probing, environment/license-variable inspection,
   wrapper construction, subprocess execution, qualification bundle creation,
   vendor attestation import/promotion, native vendor coverage import, board
   manifest processing, and board collateral generation.
7. Expose plan and grants in human/JSON `status`, diagnostics, support bundles,
   and a side-effect-free entitlement-inspection command. Report entitlement
   ID/issuer/time state by safe identifiers; redact signatures and deployment
   claims that are not needed for support.
8. Bind Enterprise runs and qualification records to the entitlement ID and
   capability used. Entitlement establishes access, not proof: tool
   qualification and result closure remain independent.
9. Add a governed upgrade/downgrade migration. Upgrade preserves all Free state.
   Downgrade preserves Enterprise records read-only, disables new Enterprise
   execution, removes no user artifacts automatically, and reports which
   configured CI requirements can no longer execute.
10. Add compatibility facades for public imports/CLI behavior, update
    installation/configuration/security/support/qualification docs, and add
    separate Free and Enterprise CI/package tests.

**Security and enforcement boundary:** Python code shipped to a customer cannot
be treated as tamper-proof DRM. Product gates must provide deterministic
supported-workflow enforcement, auditability, and accidental/misconfigured-use
prevention. Commercial enforcement requiring code confidentiality must rely on
private Enterprise package distribution and contracts, not obfuscated local
checks. Free/core correctness and evidence validation must remain usable even
when Enterprise code is absent.

**Edge cases and required resolution:**

- No entitlement file: resolve Free without warning or network access.
- Explicit entitlement path missing/unreadable: report `invalid_entitlement`;
  Free operations may continue, but no Enterprise operation may fall back.
- Unknown schema/plan/capability: reject before mutation or plugin import.
- Expired/not-yet-valid entitlement: use a policy-defined bounded clock skew;
  do not use filesystem modification time as validity.
- Offline grace: if approved, encode maximum grace in signed policy and report
  `grace` distinctly; never invent indefinite grace after a network failure.
- Capability-limited Enterprise grant: gate each capability independently; an
  EDA execution grant must not imply board verification or vendor promotion.
- Organization/deployment mismatch: reject without exposing another
  organization's identifiers.
- System clock moves backward/forward: preserve the observed wall-clock state
  in audit and fail closed when validity cannot be established.
- Entitlement rotates during a run: bind the resolved grant at run start;
  retain the completed evidence, but reevaluate current policy before closure
  or the next run.
- Downgrade with configured Enterprise CI gates: status must fail with
  `enterprise_capability_unavailable`, not skip those gates.
- Historical Enterprise evidence viewed in Free: allow read/report/export under
  normal path/privacy policy; do not permit replay, refresh, or promotion.
- Free SymbiYosys execution: never gate because the same executable is used as
  an enterprise surrogate probe; gate the surrogate qualification command, not
  `sby` itself.
- Direct Python import of an enterprise implementation: private packaging is
  the distribution boundary; supported public entry points still call the
  central gate.
- CI and tests: use deterministic test signers/keys only in fixtures; no real
  entitlement secret or customer grant may enter the repository.

**Acceptance evidence:**

1. A clean Free installation contains the core CLI and performs one digital
   good-DUT/mutant workflow plus one SymbiYosys good-DUT/mutant workflow without
   account/network/entitlement access.
2. Every Enterprise command family and direct supported API entry point rejects
   absent, malformed, expired, untrusted, and insufficient-capability grants
   before tool/environment/plugin access.
3. A valid test Enterprise grant enables exactly its declared adapters and
   board capability while preserving byte-identical Free generation.
4. Upgrade/downgrade tests preserve state and make current closure behavior
   explicit.
5. Separate wheel/entry-point/package-content tests prove the Free artifact does
   not register enterprise implementations.

**Non-goals:** define prices, billing, taxes, seat metering, sales contracts, or
cloud identity; weaken Free verification; treat entitlement as vendor
qualification; bundle proprietary tools or licenses.

<a id="source-docsplanningmissing-workmd--board-01-implement-enterprise-board-specific-digital-verification"></a>
##### `BOARD-01` Implement Enterprise board-specific digital verification

**Status:** bounded product contract specified; implementation absent.
**Priority:** P1. **Depends on:** `TIER-01`, one legally distributable reference
board/constraint fixture, selected vendor tools and licenses, qualified
Enterprise adapters, and `PHYS-01` for any claim beyond digital pre-silicon
verification.

**Current condition:** Stage 8 verifies generic bounded peripheral-controller
RTL. `vivado_xsim` executes one generated UVM project, and enterprise profiles
normalize vendor results. No schema or workflow identifies a board/revision,
FPGA part, package pins, XDC/SDC/QSF constraints, connectors, oscillators,
external devices, or board-specific expected behavior. The current
`vivado_xsim` profile does not authorize claims about Vivado synthesis,
implementation, timing, bitstreams, or hardware.

**Required implementation:**

1. Add closed schemas for `enterprise-board-v1` and normalized
   `board-facts-v1`. Use stable IDs for board, revision, device, net, pin,
   connector, clock, reset, external component, interface instance, constraint,
   check, and evidence locator.
2. Add immutable domain models/codecs/migrations. Canonicalize ordering and hash
   the board manifest, customer constraints, source/file list, selected top,
   specialization, generated collateral, and vendor reports independently.
3. Implement board-manifest validation under an Enterprise-only package.
   Validate exact FPGA part/package/speed grade, top, clock/reset declarations,
   one-to-one logical port/bit-to-package-pin mappings, I/O bank/standard
   compatibility facts when authoritative data exists, connectors, and
   external-device interface parameters.
4. Add constraint importers one bounded dialect at a time. Start with the
   required XDC subset for the selected reference board. Treat XDC as Tcl:
   parse only an explicit command/property/query subset or import a structured
   report from Vivado; never execute arbitrary customer constraint text in the
   Veriforge process. Preserve unsupported commands as blocking diagnostics
   when they affect claimed nets/clocks.
5. Reconcile board facts with elaborated RTL facts and Stage 8 peripheral
   contracts. A logical UART/SPI/I2C/GPIO interface must map to the declared
   board device role, exact top-level ports/bits, clock/reset, mode, address,
   width, and bounds. No matching by approximate board/port names.
6. Add typed board scenarios for pin mapping, clock/reset behavior,
   button/switch/LED GPIO behavior, UART bridge traffic, SPI flash transactions,
   I2C device address/ACK/stretch behavior, and other components explicitly
   represented by supported digital models. Scenario support remains
   target-specific.
7. Generate deterministic board harnesses, external-component models, test
   sequences, assertions/covers, supplemental constraints, vendor project
   manifests, expected check IDs, and coverage mappings. Never edit or overwrite
   customer-owned constraints.
8. Add a board execution adapter family. The first slice must run XSim against
   the exact board top/part/project manifest. Add Vivado synthesis/
   implementation/static-report support only as a separately qualified adapter
   with structured outputs. Add JasperGold board-bound formal execution only
   for supported digital properties and independently qualified tool versions.
9. Normalize tool output into board/check/requirement/coverage identities.
   Preserve unknown vendor messages/findings separately and keep missing or
   unmatched mandatory points non-closing.
10. Add a legal public reference-board fixture with immutable provenance and a
    customer-owned pilot fixture retained outside the repository. For each,
    run a good design and mutants covering wrong pin, swapped bus bits, wrong
    oscillator frequency, reset polarity, I/O direction, peripheral mode/
    address, missing pull/open-drain behavior, stale constraints, and wrong
    board revision.
11. Update plan/capability state, CLI/configuration, generated-output layout,
    operator/security/support docs, qualification ledger, and an explicit
    board-specific acceptance document.

**Minimum result points:**

- board manifest/schema/provenance valid;
- FPGA part/package/top/specialization match;
- required ports and pin mappings complete and unique;
- board clocks and resets reconcile with RTL and constraints;
- every selected external device binds to one supported interface profile;
- generated harness/project bytes reproduce;
- board simulation executes non-vacuously;
- required board checks and coverage points reconcile;
- vendor evidence satisfies configured qualification policy;
- unsupported physical/electrical checks remain explicit and non-closing only
  when the selected policy requires them.

**Edge cases and required resolution:**

- Board marketing name matches but revision differs: reject or require an
  explicit revision migration; never reuse pinout evidence automatically.
- FPGA family matches but part/package/speed grade differs: reject the vendor
  project and prior evidence.
- Two logical ports/bits claim one package pin, or one required port has two
  pins: reject the entire mapping.
- Vector indices, `[msb:lsb]` direction, connector numbering, or differential
  pair polarity are reversed: retain explicit bit/polarity identity and kill a
  dedicated mutant.
- Constraint uses wildcards/hierarchical queries that resolve differently by
  tool version: require a structured resolved-object report and bind its tool
  version/source hash.
- XDC contains arbitrary Tcl, environment reads, file I/O, or sourced scripts:
  do not execute it in-process; use bounded parsing or a sandboxed vendor
  adapter with allowlisted inputs and normalized output.
- Clock frequency conflicts among manifest, RTL parameter, XDC, and vendor
  report: preserve all values, mark contradiction, and block timing-dependent
  scenarios.
- Generated clock or PLL/MMCM relationship is unresolved: leave dependent
  checks unsupported until authoritative elaboration/vendor evidence exists.
- Reset polarity or asynchronous/synchronous release differs between board and
  RTL: block rather than insert an implicit inverter/synchronizer.
- Bidirectional/open-drain I2C or tri-state GPIO maps to a scalar input/output:
  require explicit drive-enable/sample semantics and board pull-up intent.
- External component address/mode straps conflict or two devices share an
  address without governed multiplexing: reject the affected scenario.
- I/O standard, bank voltage, differential standard, pull, drive, or slew is
  absent: report a board constraint gap. Only a qualified vendor/physical
  adapter may close compatibility with the actual part/bank.
- Customer constraints and generated supplemental constraints overlap:
  reject duplicate/conflicting ownership; generated files must never shadow
  customer declarations.
- Vendor board files change outside the manifest: hash and pin the resolved
  board-part files or avoid them in favor of explicit checked inputs.
- Vendor run succeeds with no board checks or stale reports: `unexecuted`/
  stale; process exit zero cannot close.
- Encrypted/vendor IP hides elaborated ports or behavior: require a supported
  black-box contract or leave the affected path unsupported.
- Hardware-in-the-loop, bitstream loading, cable discovery, and destructive
  programming are outside the initial ticket and require a separate authorized
  hardware-lab contract.

**Acceptance evidence:** one reference board/revision completes
`manifest -> analyze -> plan -> generate -> vendor run -> coverage -> strict
status` with exact part/constraint/tool identities; bytes reproduce; all
required checks are non-vacuous; every listed mutant is killed; invalid/unknown
constraint commands fail closed; Free rejects the same board workflow before
board or vendor adapter loading; and the acceptance record states all physical
and hardware exclusions.

**Non-goals:** infer boards from filenames; redistribute vendor board files,
device libraries, or licenses without permission; claim PCB/electrical/analog/
thermal/STA/bitstream/hardware sign-off from XSim or digital formal evidence;
make every external component/protocol supported in the first slice.

<a id="source-docsplanningmissing-workmd--p1-semantic-authority-and-language-completeness"></a>
#### P1: semantic authority and language completeness

<a id="source-docsplanningmissing-workmd--sem-01-extend-normalized-systemverilog-semantics"></a>
##### `SEM-01` Extend normalized SystemVerilog semantics

**Current boundary:** the platform does not implement the IEEE languages itself.
The local normalization is conservative and does not fully interpret all sizing,
casting, aggregate, interface/package, generate-condition, assertion, or cover
semantics. Unsupported temporal operators and semantic features must remain
critical generation gaps.

**Work package:** select one cohesive semantic slice, beginning with the
highest-frequency unsupported fixture family. Extend the semantic manifest and
normalized RTL facts with explicit support state, source locators, and frontend
identity. Update the Slang/Verilator cross-check to compare the selected facts
without overwriting authority. Add positive, negative, ambiguity, and
version-difference fixtures; then ensure strict planning/generation blocks when
the selected semantics are partial or unsupported for its target.

**Acceptance evidence:** versioned schema migration; raw frontend artifacts;
stable normalized facts; fixtures that demonstrate correct support, rejection,
and no false safe-generation target; real-tool CI on the qualified frontend
versions. **Non-goal:** claiming complete SystemVerilog support after adding a
single operator family.

<a id="source-docsplanningmissing-workmd--sem-02-qualify-mixed-language-elaboration"></a>
##### `SEM-02` Qualify mixed-language elaboration

**Current boundary:** the bounded built-in VHDL frontend is VHDL-only.
Verilog/SystemVerilog plus VHDL binding currently fails closed because names,
libraries, architectures, and port adaptations must not be guessed.

**Work package:** extend and qualify the existing
`cross-language-bindings-v1` schema and `analysis.bindings` validator instead of
creating a parallel manifest. Connect a governed manifest produced by an
elaborating frontend to `analyze-rtl`, planning, generation, execution, and
status. Retain language/library/unit identity, chosen VHDL architecture,
generic/parameter specialization, one-to-one port adaptation, source paths,
diagnostics, completeness, and producer identity. Add good-DUT examples plus
wrong-library, ambiguous-architecture, width/type/direction mismatch,
unresolved hierarchy instance, and missing-source rejection cases.

**Acceptance evidence:** an external elaborator produces the manifest; strict
import rejects incomplete/ambiguous records; a mixed-language fixture reaches
at least one governed target with exact results. **Blocker:** no in-repository
parser may invent mixed-language binding semantics.

<a id="source-docsplanningmissing-workmd--sem-03-broaden-frontend-and-external-design-qualification"></a>
##### `SEM-03` Broaden frontend and external-design qualification

**Current boundary:** qualification is limited to enumerated versions and a
bounded fixture corpus. A passing version command is insufficient to claim
equivalent parsing/elaboration behavior.

**Work package:** define the tested version ranges and compatibility policy for
Verilator, Slang, and GHDL. Add a matrix runner that records tool version,
input hash, normalized fact hash, diagnostics, elapsed time, and memory use.
Use representative externally sourced designs with license/provenance records.
Classify known version differences rather than normalizing them away.

**Acceptance evidence:** CI matrix results, stable compatibility report, and
fail-closed behavior for unqualified versions in strict mode.

<a id="source-docsplanningmissing-workmd--p1-formal-cdc-reset-and-memory-depth"></a>
#### P1: formal, CDC, reset, and memory depth

<a id="source-docsplanningmissing-workmd--form-01-add-one-formal-semantic-extension-beyond-boundedresponse"></a>
##### `FORM-01` Add one formal semantic extension beyond `bounded_response`

**Current boundary:** executable formal contracts require one normalized
clock/reset domain, explicit scalar trigger/response/invariant mappings, a
trigger-pulse and causality policy, and a 1-64 cycle response bound. Inferred
environments, fairness, general temporal synthesis, and unbounded liveness are
not supported.

**Work package:** choose exactly one extension: a declared environment
assumption, a selected temporal operator family, fairness, or unbounded
liveness. Define the syntax, clocking/reset model, vacuity rules, engine
capabilities, proof/cover strategy, timeout classification, and coverage-point
mapping. Extend plan validation, harness rendering, SBY generation/result
parsing, and report output. Add a good DUT plus mutants that prove the new
property is neither vacuous nor merely syntactically emitted.

**Acceptance evidence:** an explicit policy profile, deterministic harness/SBY
bytes, a passing proof and non-vacuity covers, a failing counterexample mutant,
and a normalized `unsupported` result for every unsupported operator/engine.
**Non-goal:** enabling arbitrary user SVA/LTL text without typed semantics.

<a id="source-docsplanningmissing-workmd--cdc-01-add-one-advanced-cdc-profile"></a>
##### `CDC-01` Add one advanced CDC profile

**Current boundary:** qualified CDC requires a declared structure and ordered,
externally observable stages. Bounded external latency remains actionable;
hidden stages, branching/reconvergence, and ungoverned multi-bit behavior do
not become safe assumptions.

**Work package:** select exactly one profile: reconvergent crossing,
non-power-of-two FIFO, hidden-stage discovery, or a new multi-bit coherency
scheme. Specify source/destination domains, reset relationship, allowed rate,
payload stability, observability, environmental assumptions, and whether proof
is structural or bounded. Extend the CDC policy schema, normalized-fact
validation, simulation stimulus/checker, formal properties/covers, and
counterexample triage.

**Acceptance evidence:** good-DUT and structural-violation fixtures; at least
one mutation per required safety rule; all path classifications and evidence
levels reported; ambiguous or partially observed paths remain closure blockers.

<a id="source-docsplanningmissing-workmd--rdc-01-integrate-physical-reset-and-power-evidence"></a>
##### `RDC-01` Integrate physical reset and power evidence

**Current boundary:** reset/RDC verifies governed logical intent but not reset
tree physical timing, analog constraints, hidden reset paths, or architecture
power sequencing.

**Work package:** choose one vendor/tool-neutral evidence contract for recovery
and removal timing, reset-tree analysis, power-good, isolation, or retention.
Build an adapter that imports source locations, rule IDs, severity, waiver
identity, tool/version metadata, and stable signal/domain identities. Keep
structural platform checks separate from physical-tool results in reports.

**Acceptance evidence:** qualified external-tool fixture; normalized failures
and stale evidence rejected; a physical violation cannot be converted into a
logical-formal pass. **Blocker:** requires a licensed tool and legal fixture.

<a id="source-docsplanningmissing-workmd--mem-01-promote-one-unsupported-memory-behavior"></a>
##### `MEM-01` Promote one unsupported memory behavior

**Current boundary:** qualified SRAM is a declared synchronous profile with one
read port, two write requesters, byte enables, declared collision/zero-init/
round-robin policy, and parity or SECDED/scrub mappings. Initialization files,
asynchronous or wider/more-port memories, retention, macro timing, and repair
remain outside that profile. The SECDED formal target's closed `BUG-CDC-01`
failure remains mandatory regression coverage; a new memory-profile expansion
must preserve its current good-DUT and mutant closure.

**Work package:** choose one behavior only. Define policy fields and input
evidence, extend memory fact extraction, validate observable signal/domain
mapping, create target-specific scoreboards/properties, and define when a check
is simulation-only, bounded formal, or delegated to a physical adapter.

**Acceptance evidence:** positive policy fixture; missing/contradictory policy
rejection; at least one behavior-specific mutant; exact coverage points and
non-vacuity evidence. **Non-goal:** inferring collision, initialization, or ECC
policy from signal names.

<a id="source-docsplanningmissing-workmd--p1-protocol-peripheral-and-target-breadth"></a>
#### P1: protocol, peripheral, and target breadth

<a id="source-docsplanningmissing-workmd--proto-01-resolve-and-qualify-broad-transaction-profiles"></a>
##### `PROTO-01` Resolve and qualify broad transaction profiles

**Status:** in progress; exact target evidence remains open. **Scope:** AXI4,
AXI4-Stream, Wishbone B4, Avalon-MM/ST, burst AHB, and TileLink UL/UH.

**Work package:** after `DOC-00`, choose one profile/endpoint role/bounded
contract at a time. Complete or validate every claimed target: recognition and
alias binding; generated stimulus/driver; monitor; reference model; scoreboard;
functional coverage; formal obligations; native/UVM collateral where claimed;
trace/result decoder; good-DUT; negative mutants; and external-design evidence.
Document ordering, burst, outstanding, response, error, sideband, and reset
limits as explicit contract fields.

**Acceptance evidence:** per-target results and mutation matrix, not a single
aggregate "protocol supported" state. An unimplemented target must be reported
as `partial`, `scaffold`, or `unsupported` even when another target passes.

<a id="source-docsplanningmissing-workmd--proto-02-extend-existing-bounded-protocol-profiles"></a>
##### `PROTO-02` Extend existing bounded protocol profiles

**Current boundary:** APB4, AXI4-Lite, AHB-Lite, and paired ready/valid are
qualified only for their declared bounded roles. Examples outside that boundary
include full AXI bursts/IDs/multiple outstanding transactions, AHB bursts and
split/retry/protection semantics, APB extensions, AXI-Stream sidebands, and
multi-channel routing.

**Work package:** choose one feature and one endpoint role. Revise the profile
schema, recognition, plan scenarios, reference model, scoreboard keys, formal
rules, coverage map, and result trace contract together. Parameterize limits
only when every value has a bounded execution and coverage strategy.

**Acceptance evidence:** existing profile behavior remains regression-tested;
new good-DUT and mutant matrices close on every newly claimed backend; existing
plans migrate conservatively. **Non-goal:** widening a profile through a prose
description without executable semantics.

Child work items are independently closable and remain `in progress`:

- `PROTO-02A`: AXI4-Lite maximum two outstanding reads and writes, with
  in-order response and unique sequence-key closure.
- `PROTO-02B`: AHB-Lite bounded `INCR4`, including beat progression,
  wait/error behavior, and reset interruption.
- `PROTO-02C`: APB5 `PWAKEUP`, explicitly mapped across setup, access, wait,
  and reset behavior.

<a id="source-docsplanningmissing-workmd--periph-01-extend-board-peripheral-profiles-one-capability-at-a-time"></a>
##### `PERIPH-01` Extend board-peripheral profiles one capability at a time

**Current boundary:** UART is bounded to 8-bit/whole-bit timing; SPI to
single-lane/single-master bounded transfers; I2C to 7-bit bounded operation;
GPIO/timer/interrupt logic to fixed widths and fixed-priority behavior.
These are board-neutral digital RTL profiles in the Free plan. They do not
prove a controller's mapping or behavior on a named PCB/FPGA board; that layer
belongs to Enterprise `BOARD-01`.
Unsupported features include fractional baud, arbitrary UART word sizes and flow
control, SPI multi-lane/multi-master/streaming/device framing, I2C 10-bit/high-
speed/SMBus/fairness/analog sign-off, and GPIO/timer DMA/capture/compare/cascaded
controllers/programmed arbitration.

**Work package:** select one device feature, define its register and signal
mapping requirements, model it in the BFM/reference implementation, add formal
safety/non-vacuity where the property is meaningful, and close it with
fault-specific mutants. Keep electrical characteristics and analog behavior in
`PHYS-01` unless a physical adapter is available.

**Acceptance evidence:** generated transaction trace, scoreboarding, coverage
bins, formal/simulation result points, and explicit regression of the current
bounded profile.

Child work items are independently closable and remain `in progress`:

- `PERIPH-01A`: bounded rational UART fractional-baud accumulation.
- `PERIPH-01B`: standard I2C 10-bit addressing and repeated-start read.
- `PERIPH-01C`: bounded single-master 1-2-2 dual-lane SPI transfers.

<a id="source-docsplanningmissing-workmd--vhdl-01-extend-native-vhdl-execution"></a>
##### `VHDL-01` Extend native VHDL execution

**Current boundary:** VHDL facts and execution are qualified only for declared
profiles and GHDL versions; mixed-language binding fails closed. Broader native
VHDL behavior and simulator diversity remain open.

**Work package:** choose one VHDL-capable profile beyond the accepted vertical
slices. Implement VHDL-specific rendering only where required, preserve entity,
architecture, generic, package, record, subtype, array, and generate evidence,
and reconcile exact result records with canonical checks.

**Acceptance evidence:** GHDL analysis/elaboration/run, known-good and
known-bad fixtures, trace identity checks, and no loss of source-language
evidence. **Non-goal:** treating a VHDL file as equivalent to SystemVerilog
without language-aware compilation and result decoding.

<a id="source-docsplanningmissing-workmd--uvm-01-qualify-richer-generated-uvm-environments"></a>
##### `UVM-01` Qualify richer generated UVM environments

**Current boundary:** UVM generation is broader than its licensed execution
evidence. Only a limited vendor-qualified profile has complete execution proof;
generated multi-agent, virtual-sequence, cross-protocol-scoreboard, and RAL
collateral is non-closing until independently executed and signed.

**Work package:** select one licensed simulator and one profile. Version the
project bridge, compile/elaborate/run commands, license assumptions, transcript
parser, error/fatal checks, non-vacuity criteria, and signature verification.
Add a reproducible vendor fixture and evidence-import test that rejects unknown
trace IDs, missing checks, bad signatures, or stale generated provenance.

**Acceptance evidence:** signed vendor execution with exact normalized outcomes
and a negative fixture that demonstrates failed/partial UVM output cannot close
coverage.

<a id="source-docsplanningmissing-workmd--p2-adapters-coverage-scale-and-deployment"></a>
#### P2: adapters, coverage, scale, and deployment

<a id="source-docsplanningmissing-workmd--tool-01-add-one-commercial-formal-or-simulation-adapter"></a>
##### `TOOL-01` Add one commercial formal or simulation adapter

**Current boundary:** commercial tools are deployment inputs; they are not
bundled or implicitly qualified. The platform must receive normalized,
traceable evidence rather than rely on process exit status.
These adapters are Enterprise-plan capabilities under `TIER-01`. A valid
Enterprise entitlement permits connection but does not qualify the tool or
close any verification result.

**Work package:** select one engine and define a versioned adapter contract for
command construction, source/include/define handling, timeout/cancellation,
license failures, result parsing, counterexample paths, tool version, and
per-check identity. Qualify it with a real tool, not a mocked log alone.

**Acceptance evidence:** good run, assertion/check failure, timeout, license
failure, malformed report, missing trace ID, and stale-provenance fixtures all
produce the correct normalized non-closing or failed state.

<a id="source-docsplanningmissing-workmd--cov-01-import-native-vendor-coverage-and-formal-coverage"></a>
##### `COV-01` Import native vendor coverage and formal coverage

**Current boundary:** normalized JSON, LCOV, Cobertura XML, UCIS XML, and
configured importer results participate in closure; unexported proprietary
databases and richer formal coverage APIs do not.

**Work package:** select one vendor format/API. Preserve coverpoint/cross/bin
identity, goal, illegal/ignore/excluded state, requirement/check/behavior links,
merge provenance, and tool version. Route imported data through the same point,
disposition, plan-reconciliation, stale/orphan, and strict-CI gates as native
data.

**Acceptance evidence:** known hit, miss, illegal bin, ignored bin, waived and
unreachable point, stale mapping, and malformed input fixtures; no importer may
directly report closure success.

<a id="source-docsplanningmissing-workmd--cov-02-generate-functional-coverage-from-typed-intent"></a>
##### `COV-02` Generate functional coverage from typed intent

**Current boundary:** the platform can reconcile/import functional totals and
point results, but richer covergroup/bin/cross generation from protocol and
requirement schemas is incomplete.

**Work package:** add versioned coverage intent to the applicable plan/profile
schema: sampling event, bins, crosses, illegal/ignore bins, target renderer,
and stable point IDs. Implement at least one target renderer and a trace mapper
that reports known hits and misses. Ensure parameter-sweep cross-points cannot
hide an uncovered specialization.

**Acceptance evidence:** deterministic generated coverage source, compile/run
on the claimed backend, known-hit and known-miss fixtures, invalid-bin-policy
rejection, and coverage closure linked to canonical checks.

<a id="source-docsplanningmissing-workmd--doc-01-add-direct-ocr-and-local-retrieval-adapters"></a>
##### `DOC-01` Add direct OCR and local retrieval adapters

**Current boundary:** an OCR-sidecar and built-in local adapters are governed;
direct OCR engines and larger semantic embedding/vector backends remain
deployment integrations.

SQLite FTS5 is now the default offline local index. Its canonical database is
atomically replaced under a bounded cross-process lock, stores deterministic
chunk/source/configuration identity, validates schema/integrity/row counts and
source replacement, rebuilds legacy JSON-only indexes, and retains JSON vector
retrieval as fallback. Concurrent publication, cancellation recovery,
corruption, symlink escape, deterministic ranking, and source-replacement
fixtures pass. Direct OCR remains outside this completed local-retrieval slice.

**Work package:** independently select an approved OCR engine and a local
embedding/vector implementation. Define file-type limits, source provenance,
content handling, confidentiality controls, index/cache identity, invalidation,
tool-version recording, error behavior, and export policy. Treat extracted text
as evidence, never as authoritative instructions.

**Acceptance evidence:** scanned-document, malformed-input, changed-source,
offline, permission-denied, and prompt-injection-like content fixtures; no raw
secret or provider content may enter audit records.

<a id="source-docsplanningmissing-workmd--scale-01-qualify-repository-scale-and-scheduling"></a>
##### `SCALE-01` Qualify repository scale and scheduling

**Current boundary:** `SCALE-02` first corrects the existing Stage 10 benchmark
and regression-evidence design. After that, the trustworthy bounded benchmark
covers one Linux/WSL-oriented profile; broader operating-system/tool-version
reproducibility and license-aware orchestration remain unqualified.

The scheduler-safety slice now uses resource-aware admission across module,
child-process, memory, and license-token limits. Results retain input order;
pre-cancel, queue cancellation, worker failure, no-oversubscription, locked
aggregate publication, stale-lock recovery, and concurrent index publication
are covered. A newly retained independent installed-wheel Ubuntu performance-v3
candidate/baseline comparison remains external CI evidence and is not claimed
by this local change.

**Work package:** do not use this breadth ticket to bypass `SCALE-02`. Once the
candidate/baseline contract is valid, publish input-size, runtime, memory,
concurrency, and cache
budgets; expand the benchmark matrix; add bounded scheduling for analysis,
indexing, planning, generation, and independent formal tasks with license and
memory constraints. Preserve deterministic ordering and cancellation behavior.

**Acceptance evidence:** measured benchmark reports in CI, budget regressions
that fail predictably, deterministic repeated outputs, and no oversubscription
of declared formal/license resources.

<a id="source-docsplanningmissing-workmd--plat-01-define-supported-deployment-platforms"></a>
##### `PLAT-01` Define supported deployment platforms

**Current boundary:** Linux/WSL is the production focus. Native Windows and
macOS are unsupported/best-effort, and exact distribution/kernel/tool-container
ranges are not yet fully qualified.

**Work package:** first publish and test exact Linux distribution, kernel,
Python, container/runtime, and EDA-tool ranges. Treat Windows and macOS as
separate product decisions, each requiring tool availability, path/process
behavior, filesystem semantics, and real-tool integration evidence.

**Acceptance evidence:** reproducible installation and strict CLI matrix for
every supported platform; unsupported platforms remain clearly labeled and do
not silently inherit production claims.

<a id="source-docsplanningmissing-workmd--productsecurity-decisions-blocked-until-explicitly-approved"></a>
#### Product/security decisions: blocked until explicitly approved

These are deliberate governance boundaries, not bugs an agent should remove.
Any implementation starts only after a product/security owner approves the
stated decision and a versioned qualification plan exists.

<a id="source-docsplanningmissing-workmd--ai-01-decide-whether-ai-may-author-executable-artifacts"></a>
##### `AI-01` Decide whether AI may author executable artifacts

**Current boundary:** AI can provide evidence-backed planning proposals, analyze
feedback, and select existing templates/parameters. It cannot author RTL,
verification source, commands, renderers, waivers, executable checks, or other
closure claims.

**Decision package:** define the permitted artifact classes, human review and
approval identity, sandboxing, source/license checks, prompt/context disclosure,
provenance, reproducibility expectations, deterministic validators, failure
ownership, and rollback/retention policy. A model-produced file must not become
an executable claim until deterministic checks and a human approval record bind
it to the plan revision.

<a id="source-docsplanningmissing-workmd--ai-02-decide-whether-to-support-multi-provider-routingfallback"></a>
##### `AI-02` Decide whether to support multi-provider routing/fallback

**Current boundary:** one configured LiteLLM model is used with bounded same-
model repair and deterministic fallback; cross-provider routing is unsupported.

**Decision package:** define eligibility order, data residency, credential
isolation, endpoint allowlists, model/version pinning, retry and cost limits,
cache keys, audit fields, outage behavior, and how proposal equivalence is
validated across models. Do not route prompts to an additional provider merely
because the first request fails.

<a id="source-docsplanningmissing-workmd--phys-01-decide-the-physical-sign-off-integration-boundary"></a>
##### `PHYS-01` Decide the physical-sign-off integration boundary

**Current boundary:** analog/mixed-signal, power intent, gate-level timing,
emulation, FPGA prototype coverage, analog electrical behavior, and physical
macro timing are not platform sign-off claims.

**Decision package:** for each desired domain, select an external tool and
define the normalized evidence needed for release: inputs, constraints,
versions, violations, waivers, source/domain identities, result retention, and
relationship to logical simulation/formal closure. A green logical run must
never mask missing physical sign-off evidence.

<a id="source-docsplanningmissing-workmd--backlog-operating-rules"></a>
### Backlog operating rules

- Work one issue ID and one selected semantic/profile slice at a time. Large
  standards must be decomposed by endpoint role, feature, target, and bounded
  parameter range.
- Do not infer parameters, environment assumptions, architecture binding,
  protocol aliases, CDC safety, memory policy, or physical constraints solely
  from names, comments, generated output, or a passing tool exit code.
- Keep unsupported, ambiguous, skipped, timed-out, malformed, unknown, and
  untraceable cases explicit and non-closing. `bounded_pass` is also actionable
  unless an accepted policy defines stronger evidence.
- Preserve old plan/revision/run readability. Migrations may downgrade unknown
  legacy semantics to `unsupported`; they must never invent support.
- Update the capability matrix, relevant acceptance document, CLI contract,
  fixtures, tests, and operator guidance in the same change that promotes an
  item. Record any external-tool qualification and license assumptions.
- Before marking an item complete, run the narrow unit/fixture suite plus the
  affected real-tool and strict-status paths. Report unavailable licensed tools
  as remaining evidence gaps, not successful validation.

<a id="source-docsplanningmissing-workmd--zero-assumption-agent-execution-protocol"></a>
### Zero-Assumption Agent Execution Protocol

Every feature and backlog ID below has an execution card. The card is the
operational order; the earlier ticket body defines required behavior and edge
cases, and the later technical playbook identifies implementation extension
points. An agent must not omit a card step merely because a generated artifact,
unit test, process exit, or aggregate percentage is green.

<a id="source-docsplanningmissing-workmd--required-work-record"></a>
#### Required work record

Before editing, create or update a ticket-owned work record in the pull request
description or governed task system with these fields:

```text
ticket_id
selected feature/profile/role/target/bounds
explicit non-goals
dependency and approval state
baseline commit and working-tree state
reproduction command/result
files/schemas/models expected to change
required tool/platform/version matrix
required good DUT, negative fixtures, and mutants
required check/trace/coverage/non-vacuity IDs
planned tests by mandatory test layer
planned evidence and acceptance-document paths
```

If any field cannot be resolved from the card and repository, stop at the
ticket's stated gate. Do not choose a product boundary, licensed tool,
customer/board fixture, signer, release channel, or physical-sign-off policy on
behalf of an owner.

<a id="source-docsplanningmissing-workmd--mandatory-implementation-order"></a>
#### Mandatory implementation order

Apply these phases to every active execution card:

1. **Freeze scope.** Record exactly one ticket and its selected bounded slice.
   Resolve dependencies and approvals. List adjacent semantics/targets that
   remain unsupported.
2. **Reproduce the baseline.** Run the public CLI or checker that demonstrates
   the gap. Capture exit code, normalized state, relevant artifact/evidence
   hashes, and strict-status result. For a new capability, add a failing
   acceptance test that proves the requested state is not yet supported.
3. **Write the contract first.** Add or amend the normative profile/policy and
   stable requirement/check/coverage IDs. Specify inputs, outputs, bounds,
   authority, failure states, and unsupported neighbors before implementation.
4. **Version data.** Update closed schemas, immutable models, codecs, canonical
   ordering/hashing, migration from every readable version, and newer-version
   rejection. Legacy unknown semantics migrate conservatively.
5. **Implement evidence and validation.** Capture facts only from approved
   authority, reconcile missing/contradicted/unsupported state, and block
   planning or execution before an unsafe inference or side effect.
6. **Implement scenarios/generation.** Add typed stimulus, oracle, completion,
   timeout, checks, coverage/non-vacuity, renderer registration, deterministic
   artifacts, traces, integrity, and provenance only for the selected slice.
7. **Implement execution/results.** Use bounded process/sandbox/adaptor APIs,
   stable tool/version identity, atomic summaries, exact result decoding, and
   fail-closed handling for empty/partial/unknown/duplicate/stale output.
8. **Integrate closure.** Reconcile every expected check, requirement,
   behavior, parameter point, and coverage point. Missing, skipped,
   unexecuted, stale, or unsupported mandatory cells remain non-closing.
9. **Add the complete fixture matrix.** Include good behavior, malformed and
   ambiguous input, unsupported neighbor, minimum/maximum and outside bounds,
   stale/migration cases, interruption/concurrency/security cases, and one
   targeted mutant per semantic rule.
10. **Update operations and claims.** Update capability/feature ledgers,
    acceptance, configuration/CLI, operator procedures, migration notes, and
    this backlog from the same evidence. Do not edit historical claims as if
    the feature had existed at that snapshot.

<a id="source-docsplanningmissing-workmd--mandatory-validation-order"></a>
#### Mandatory validation order

Run validation in this order and stop on the first failing layer:

1. **Changed-schema/model tests.** Run ticket-owned schema, codec, model, and
   migration tests including closed-schema and newer-version negatives.
2. **Changed-policy/unit tests.** Run configuration, validator, planner,
   scenario, renderer, decoder, closure, and exact-diagnostic tests affected by
   the slice.
3. **Negative/adversarial tests.** Run malformed, ambiguous, stale, path,
   secret, timeout, interruption, concurrency, duplicate/unknown identity, and
   unsupported-neighbor cases from the ticket card.
4. **Determinism tests.** Repeat generation/import/serialization and compare
   bytes, stable IDs, hashes, ordering, cache identity, and atomic output.
5. **End-to-end installed-artifact test.** Build the relevant wheel(s), install
   in clean environments, and run the public analyze/plan/generate/run/
   coverage/status or ticket-specific workflow. Source-tree imports do not
   satisfy package validation.
6. **Real-tool or external-evidence test.** Run every claimed backend/version/
   platform against the good DUT and complete targeted mutant/negative matrix.
   Contract fixtures and mocks cannot promote a real-tool claim.
7. **Feature coverage audit.** Validate the feature coverage ledger. Require
   all mandatory requirements, states, edges, targets, mutants, and results to
   be closed or explicitly non-applicable with reviewed technical reason.
8. **Source branch coverage.** Run branch coverage for changed decision modules
   and meet the ticket's 100% feature-owned branch rule plus repository
   ratchets.
9. **Repository gates.** Run Ruff lint/format, mypy, compatibility,
   maintainability, repository contracts, secrets, security/dependency checks,
   and qualification gates relevant to the ticket.
10. **Full regression.** Run `uv run python -m unittest discover -s tests` with
    every required tool installed. Review all skips and warnings; a required
    skip or leaked resource is a failure.
11. **Acceptance replay.** Re-run exact commands from the updated operator/
    acceptance document in one clean checkout and verify the retained evidence
    hashes and strict-status result.

<a id="source-docsplanningmissing-workmd--mandatory-handoff"></a>
#### Mandatory handoff

An agent may mark a card complete only when the handoff contains:

- exact changed files and schema/profile versions;
- exact commands, exits, test counts, skips, warnings, coverage, and tool
  versions;
- good-DUT and per-mutant/per-negative result identities;
- feature-coverage ledger path and validator result;
- generated/run/coverage/evidence hashes and current source identity;
- capability state before/after plus unchanged unsupported neighbors;
- migration/rollback result;
- unavailable tool, owner decision, or external evidence explicitly left open;
- acceptance/operations/documentation updates;
- no unrelated changes claimed or reverted.

If implementation is complete but required licensed, board, signer, platform,
pilot, or owner evidence is unavailable, leave the ticket `partial` or
`contract_verified`. Never promote it from unit tests or generated collateral.

<a id="source-docsplanningmissing-workmd--technical-implementation-guide"></a>
### Technical Implementation Guide

This section maps backlog items to the current codebase and supplies the
implementation sequence and edge-case policy agents should follow. Python
package paths are relative to `src/dv_platform/`; schema, test, fixture, and
documentation paths are repository-relative. The path list is a starting
ownership map, not permission to change every listed module in one patch.

<a id="source-docsplanningmissing-workmd--source-ownership-map"></a>
#### Source ownership map

| Area | Primary contracts and implementation | Primary tests and fixtures |
| --- | --- | --- |
| Semantic manifest | `schemas/rtl/dvsem-v2.schema.json`, `enterprise/semantics/contracts.py`, `enterprise/semantics/validation.py`, `verification/storage/rtl_fact_codec.py` | `tests/enterprise/test_enterprise_semantics.py`, `tests/domain/test_semantic_ir.py`, `tests/fixtures/semantic/` |
| Verilator/Slang semantics | `rtl/verilator/`, `rtl/slang/`, `analysis/semantic_crosscheck.py`, `core/tool_versions.py` | `tests/rtl/test_semantic_crosscheck.py`, `tests/integration/test_slang_integration.py`, `tests/fixtures/slang/`, `tests/fixtures/verilator/` |
| VHDL and mixed language | `schemas/rtl/cross-language-bindings-v1.schema.json`, `verification/protocols/bindings.py`, `rtl/vhdl/`, `generators/vhdl.py` | `tests/verification/test_cross_language_bindings.py`, `tests/rtl/test_vhdl_normalization.py`, `tests/integration/test_vhdl_pipeline.py` |
| Depth policy | `configuration/depth_catalog.py`, `configuration/validation.py`, `verification/depth/checks.py`, `domain/models.py` | `tests/formal/test_depth.py`, `tests/verification/test_semantic_policy_branches.py` |
| Formal scenarios | `verification/scenarios/formal.py`, `generators/scenario_registry.py`, `formal/generation/`, `formal/execution.py` | `tests/formal/test_formal_depth.py`, `tests/integration/test_formal_depth_pipeline.py`, `tests/fixtures/mutations/formal/` |
| CDC/RDC | `verification/scenarios/cdc.py`, `verification/scenarios/reset.py`, `formal/generation/cdc.py`, `formal/generation/contracts.py`, `generators/cdc.py` | `tests/formal/test_cdc_formal.py`, `tests/integration/test_cdc_schemes_pipeline.py`, `tests/integration/test_reset_domains_pipeline.py` |
| Memory | `verification/scenarios/memory.py`, `generators/memories.py`, `formal/generation/memory.py`, `formal/generation/contracts.py` | `tests/formal/test_memory_depth.py`, `tests/integration/test_memory_depth_pipeline.py`, `tests/fixtures/mutations/memory/` |
| External-input timing/CDC classification | `rtl/verilator/hierarchy.py`, `verification/planning/assembly.py`, `verification/depth/peripheral.py`, `formal/generation/cdc.py`, `formal/execution.py` | `tests/integration/test_memory_depth_pipeline.py`, `tests/verification/test_cdc_schemes.py`, `tests/formal/test_cdc_formal.py` |
| Protocol profiles | `schemas/verification/protocol-profile-v1.schema.json`, `verification/protocols/profiles.py`, `verification/protocols/recognition.py`, `verification/scenarios/profiles.py` | `tests/verification/test_production_protocol_profiles.py`, `tests/verification/test_protocol_recognition.py`, `tests/verification/test_protocol_transaction_models.py` |
| Protocol generation | `generators/protocols/cocotb.py`, `generators/protocols/formal.py`, `generators/protocols/formal_standard.py`, `generators/protocols/native.py`, `generators/protocols/vhdl.py` | `tests/generation/test_executable_protocol_generation.py`, `tests/verification/test_broad_protocol_good_dut.py`, `tests/integration/test_native_protocol_pipeline.py` |
| Peripherals | `domain/peripherals.py`, `verification/depth/peripheral.py`, `verification/scenarios/peripheral.py`, `generators/peripherals.py` | `tests/formal/test_peripheral_depth.py`, `tests/qualification/test_*_peripheral_qualification.py`, `tests/fixtures/mutations/peripheral/` |
| UVM | `generators/uvm/`, `generation/templates/uvm/`, `enterprise/evidence.py`, `enterprise/signatures.py`, `qualification_assets/runners/` | `tests/qualification/test_uvm_project_qualification.py`, `tests/enterprise/test_enterprise_qualification.py` |
| Simulation execution | `execution/simulation/process.py`, `execution/simulation/summaries.py`, `execution/simulation/__init__.py`, `cli_handlers/commands/run.py` | `tests/integration/test_run.py`, `tests/integration/test_native_pipeline.py`, protocol pipeline tests |
| Coverage | `schemas/verification/coverage-v3.schema.json`, `execution/coverage/importer.py`, `execution/coverage/loaders.py`, `execution/coverage/closure.py`, `execution/coverage/ucis.py` | `tests/execution/test_coverage.py`, `tests/execution/test_ucis.py`, `tests/execution/test_parameter_sweep_coverage.py` |
| Enterprise adapters | `enterprise/adapters.py`, `enterprise/builtin_adapters.py`, `enterprise/profiles.py`, `enterprise/qualification/` | `tests/enterprise/test_enterprise_adapters.py`, `tests/enterprise/test_builtin_adapters.py`, `tests/qualification/test_enterprise_qualification.py` |
| Product plans and entitlement | `pyproject.toml`, proposed `schemas/product/product-entitlement-v1.schema.json`, core capability registry/resolver to be added, `configuration/`, `enterprise/cli.py`, `infrastructure/plugins.py`, `execution/status/` | new `tests/product/test_entitlements.py`, Free/Enterprise wheel-content tests, CLI/API gate tests, upgrade/downgrade integration tests |
| Enterprise board verification | proposed `schemas/enterprise/enterprise-board-v1.schema.json` and `board-facts-v1.schema.json`, board domain/constraint/scenario/generator packages to be added, `domain/peripherals.py`, `verification/depth/peripheral.py`, `enterprise/adapters.py`, `enterprise/profiles.py` | new board manifest/constraint/unit tests, reference-board fixture and mutants, XSim/vendor integration tests, entitlement-negative tests |
| Qualification gates and evidence | `scripts/qualification/ga_gates.py`, `scripts/qualification/ga_evidence.py`, qualification schemas/policies/records, `.github/workflows/ci.yml`, `.github/workflows/scale-qualification.yml` | `tests/qualification/test_ga_gates.py`, `test_ga_evidence.py`, type-specific evidence tests, new contextual/impact/workflow-contract fixtures |
| Release control and materials | `.github/workflows/release.yml`, `scripts/release/`, `pyproject.toml`, qualification release policy/records to be added | `tests/repository/test_release_materials.py`, `test_packaging.py`, new version-channel, exact-SHA, provenance-context, workflow-contract, publication-recovery tests |
| Documentation/retrieval | `analysis/docs.py`, `documentation/indexing.py`, `enterprise/builtin_adapters.py` | `tests/documentation/test_docs.py`, `tests/enterprise/test_builtin_adapters.py`, `tests/fixtures/docs/` |
| AI and context optimizers | `ai/gateway.py`, `ai/model_client.py`, `ai/planning/`, `ai/feedback.py`, `ai/scenarios.py`, `ai/runtime.py`, `ai/code_graph.py`, `ai/optimization.py` | `tests/ai/`, plus deterministic fake MCP/HTTP, redirect, framing, process/descriptor cleanup, preflight, cache/provenance, and opt-in real compatibility tests |
| Scale/platform | `enterprise/benchmark.py`, `scripts/qualification/performance.py`, `.github/workflows/scale-qualification.yml`, `execution/simulation/process.py`, `cli_handlers/commands/run.py`, `core/sandbox.py`, `core/tool_versions.py` | `tests/enterprise/test_benchmark_runner.py`, `tests/qualification/test_performance_qualification.py`, new installed-wheel/candidate-baseline/functional-mutant/runner-noise tests, `tests/execution/test_sandbox.py` |
| Repository quality/public compatibility | `scripts/checks/compatibility.py`, `scripts/checks/maintainability.py`, `qualification/policies/compatibility-baseline-v1.json`, `configuration/validation.py`, `ai/gateway.py` | `.github/workflows/ci.yml`, `tests/repository/`, full unittest/mypy/Ruff checks |
| Capability/document/progress governance | `scripts/checks/repository_contracts.py`, `docs/verification.md`, `docs/verification.md`, `docs/verification.md`, root `docs/roadmap.md`, proposed document/progress catalogs | `tests/repository/test_repository_contracts.py`, deliberate capability contradiction, progress transition, stale-backlog, and inventory fixtures to be added |

<a id="source-docsplanningmissing-workmd--standard-implementation-sequence"></a>
#### Standard implementation sequence

Every implementation issue should follow this order. If a step is not
applicable, the acceptance document must say why.

1. **Establish the current state.** Reproduce the unsupported/partial behavior
   through the public CLI. Save the plan state, generated-artifact state, run
   summary, and status-policy result that demonstrate the gap.
2. **Write the bounded contract.** Specify exact inputs, outputs, endpoint role,
   clock/reset ownership, parameter ranges, timeout/bound behavior, assumptions,
   expected result points, and unsupported neighboring semantics. Avoid using a
   standard name such as "AXI" or "CDC" as the entire contract.
3. **Version the data model.** Extend the appropriate JSON schema and immutable
   dataclass/model. Add strict unknown-field handling, positive bounds, unique
   identities, deterministic ordering, and migration from every readable older
   version. New legacy fields default to `partial` or `unsupported`, never
   `supported`.
4. **Capture authoritative evidence.** Extend the elaborating frontend,
   semantic importer, explicit project configuration, or vendor adapter. Every
   fact must carry a source artifact and stable locator. Name heuristics may
   propose an open question but must not establish a critical semantic claim.
5. **Validate and gate planning.** Add deterministic validation in the
   configuration/depth/protocol layer. Produce a supported claim only when all
   required facts agree. Missing or contradictory facts must produce an
   actionable diagnostic and target-specific non-executable state.
6. **Construct typed scenarios.** Add a new scenario kind only when its
   stimulus, oracle, completion rule, coverage goals, check IDs, and evidence
   references can be represented. Register target support through
   `generators/scenario_registry.py`; do not special-case support in display
   code.
7. **Implement target renderers.** Generate only from typed scenario/policy
   data. Validate identifiers, widths, literals, file paths, and tool-language
   compatibility before rendering. Attach artifact traces and quality
   requirements to every executable symbol.
8. **Implement execution and decoding.** Construct subprocess arguments without
   a shell, enforce timeout/output/resource limits, and decode stable trace IDs
   into the common validation-result envelope. Record tool/dependency versions,
   command arguments with secrets redacted, and counterexample/result paths.
9. **Integrate closure and status.** Emit coverage/formal points for every
   executable check. Verify that missing points become `unmeasured`, unmatched
   points become stale, failures remain failed, and bounded/unsupported results
   remain actionable under strict/CI policy.
10. **Build the fixture matrix.** Include at least one known-good DUT, one
    malformed or ambiguous input, one unsupported-neighbor case, and one mutant
    for each semantic rule that could otherwise pass vacuously. Add repeated
    generation and stale-provenance cases.
11. **Run real tools.** Unit tests prove contracts; they do not qualify an EDA
    engine. Run the exact supported tool versions and retain version, command,
    input hashes, generated hashes, per-check results, coverage, and strict
    status.
12. **Update release claims.** Update the capability matrix, acceptance
    document, configuration/CLI contract, operator instructions, and this
    backlog in the same change. State target-specific support and exclusions.

<a id="source-docsplanningmissing-workmd--cross-cutting-edge-case-policy"></a>
#### Cross-cutting edge-case policy

| Edge case | Required resolution |
| --- | --- |
| Input schema is newer than the binary | Reject before mutation with the observed and maximum supported versions. Never ignore unknown semantic fields. |
| Input schema is older but readable | Migrate deterministically; mark newly introduced semantic dimensions `partial`/`unsupported`; preserve original artifact and hash. |
| Duplicate module, instance, check, trace, point, or binding identity | Reject the entire affected import/plan. Do not use first-wins or last-wins behavior. |
| Required fact is absent | Emit `missing_evidence` or target `unsupported`; identify the exact missing field/signal/source locator. |
| Two evidence sources disagree | Preserve both facts and emit a contradicted claim. A secondary frontend never silently overwrites the configured semantic authority. |
| Width, signedness, type, direction, clock, reset, or role is ambiguous | Stop profile promotion. Require an explicit alias/binding/depth/semantic manifest correction. |
| Parameter is symbolic or depends on an unevaluated generate condition | Keep the specialization unsupported unless the authoritative elaborator supplies a concrete value and identity. |
| Optional protocol signals are partially present | Accept only when the profile defines that exact optional combination; otherwise reject the binding rather than silently dropping signals. |
| Multiple protocol instances match the same canonical signature | Require explicit instance identity or one-to-one alias mapping. Never bind by approximate prefix selection. |
| A target has a renderer but no decoder or measured fixture | Mark it `scaffold` or `partial`, not executable/supported. |
| Tool exits zero but emits no expected check/trace IDs | Produce `unexecuted`; fail strict status. |
| Tool exits non-zero after producing valid failures | Preserve decoded per-check failures and process failure metadata. Do not discard useful counterexamples. |
| Tool times out or is interrupted | Write an interrupted/timed-out summary atomically, retain bounded logs, and keep all unfinished checks non-closing. |
| Tool/license/dependency is unavailable | Report a missing-tool/deployment prerequisite. A local skip is never qualification evidence. |
| Qualification ledger is structurally valid but evidence is historical, stale, wrong-impact, or wrong-candidate | Preserve historical acceptance, fail candidate promotion, and name the exact current/reusable evidence required. |
| Evidence payload digest is valid but checkout/workflow/lock/artifact context differs | Contextually recompute and reject every mismatched dimension; a self-consistent document cannot attest to another candidate. |
| Release tag has no exact-SHA successful mandatory validation or falls through an undefined channel policy | Reject before build/sign/publish. Never substitute branch-latest green CI or ledger-only validation. |
| Performance baseline and candidate use the same commit/wheel | Classify only as repeatability; require an independently produced accepted baseline for a regression claim. |
| Context optimizer is disabled, preflight-rejected, timed out, malformed, or cancelled | Start no unnecessary process; bound I/O; clean up process group/pipes in `finally`; preserve advisory fallback or required failure according to explicit mode. |
| Enterprise capability is requested without a valid grant | Reject before plugin/tool/environment access with the exact required capability. Do not skip, silently downgrade, or disable unrelated Free operations. |
| Entitlement is malformed, expired, not yet valid, untrusted, or organization-mismatched | Mark entitlement invalid and fail Enterprise operations. Preserve only safe identifiers in diagnostics; never infer validity from local file ownership or modification time. |
| Installation is downgraded from Enterprise to Free | Preserve prior Enterprise evidence read-only, block new Enterprise work, and fail any still-required Enterprise CI gate explicitly. Do not delete customer artifacts automatically. |
| Board manifest, RTL facts, constraints, and vendor-resolved objects disagree | Preserve each source and emit a contradicted board claim. No source silently overwrites another and no board run closes until required identities reconcile. |
| Constraint file contains unsupported or executable scripting | Never execute it in the core process. Parse a governed subset or use a sandboxed Enterprise vendor adapter and import structured resolved facts. |
| Output contains unknown or duplicate trace IDs | Reject result closure for the affected run and expose the unknown/duplicate IDs for triage. |
| Generated inputs or plan revision changed after a run | Mark run and coverage stale using provenance hashes; require regenerate, rerun, and re-import. |
| Formal assumptions are contradictory or eliminate all triggers | Fail non-vacuity through independent assumption-witness and reachability covers. Never count the proof as closed. |
| Formal engine cannot support the requested operator/task | Set the target/profile state to unsupported for that engine; do not weaken the property to obtain a pass. |
| Coverage denominator is zero or only exclusions remain | Report no measurable closure rather than 100 percent unless an explicit governed policy defines not-applicable behavior. |
| Waiver is expired, orphaned, conflicting, or references a stale point | Fail closure and require a new governed disposition bound to a current point. |
| Parameter sweep is only partially executed | Keep the semantic cross-point open for every missing specialization; aggregate percentages cannot mask it. |
| Paths escape the repository/export/run root or traverse symlinks unexpectedly | Reject before execution/import/export using resolved, allowlisted paths. |
| Secrets appear in commands, provider errors, or logs | Redact before persistence; audit only secret-provider identity and content-free request metadata. |
| Parallel workers publish the same artifact/run | Use isolated staging and atomic publication; one deterministic owner wins only after hash validation, otherwise fail the collision. |
| Nondeterministic tool ordering changes output bytes | Canonicalize semantic ordering before rendering/serialization; retain raw tool output separately for audit. |

<a id="source-docsplanningmissing-workmd--ticket-level-implementation-playbooks"></a>
#### Ticket-level implementation playbooks

The following steps refine the work packages above. They are intentionally
specific about extension points and the edge cases most likely to produce a
false verification claim.

<a id="source-docsplanningmissing-workmd--doc-00-technical-steps-and-edge-cases"></a>
##### `DOC-00` technical steps and edge cases

1. Enumerate `production_protocol_profiles()` in
   `verification/protocols/profiles.py`, each profile's `supported_targets`, and
   target state emitted by `verification/scenarios/profiles.py`.
2. Trace every profile/target to the selected renderer in
   `generators/protocols/`, result decoder in `execution/`, and good-DUT/mutant
   fixture. Record paths in a temporary review table committed as an acceptance
   artifact, not in an untracked note.
3. Compare that evidence with `capability-matrix.md`,
   `protocol-profiles.md`, stage acceptance records, and CI workflow commands.
4. Choose one machine-owned representation for profile-by-target qualification.
   Prefer extending the existing protocol profile catalog or a versioned
   qualification ledger, then test documentation against it.
5. Correct prose and release gates together. If evidence is incomplete, keep
   the profile target conservative until a separate implementation ticket
   closes it.

Edge cases: a renderer exists but tests only string output; tests are skipped
when tools are absent; one endpoint role passes while the inverse role does not;
one target passes while another is generated only; a broad profile passes only
within smaller bounds than its schema permits. Resolve each by recording state
at the profile, role, target, and bound level rather than assigning one global
"supported" label.

<a id="source-docsplanningmissing-workmd--bug-cdc-01-technical-steps-and-edge-cases"></a>
##### `BUG-CDC-01` technical steps and edge cases

This is a retained regression/reopen playbook, not active implementation work.
Run it when CDC/external-input ownership changes or when the named SECDED test
fails again; do not mark the ticket active without new reproducing evidence.

1. Add a focused unit fixture for `_cdc_paths()` containing one clocked process,
   one top-level input declared synchronous to that clock, one timing-unknown
   input, and one explicitly asynchronous input. Capture the current false
   `external -> domain` result before changing the model.
2. Add a typed external-input timing relationship to normalized/planned facts.
   The minimum record needs signal, relation (`synchronous`, `asynchronous`, or
   `unknown`), destination domain/clock when known, evidence source, locator,
   and declaring contract/profile/policy identity. Version RTL facts and codecs
   if this record is persisted.
3. Populate timing relationships from authoritative sources only:
   protocol-profile clock bindings, validated memory/peripheral depth policies,
   explicit semantic manifests, or explicit project configuration. Verilator
   signal use alone proves dependency, not source timing.
4. Change `rtl/verilator/hierarchy.py` so cross-domain flow and external-input
   dependency are represented separately. A known synchronous input must not
   produce an `RTLCDCPath`. An explicitly asynchronous input may produce an
   external CDC path. An unknown input must produce a timing open question or a
   distinct non-closing candidate rather than being asserted safe.
5. Reconcile policy-derived relationships in
   `verification/planning/assembly.py`. Validate that the declared policy clock
   resolves to exactly one control domain and that every governed signal is
   actually read in that domain.
6. Keep `formal/generation/cdc.py` fail-closed for real `RTLCDCPath` records.
   Do not add special signal-name exclusions to `_cdc_path_reason()`. Instead,
   ensure non-CDC synchronous relationships never enter CDC evidence.
7. Add report fields that separately list resolved synchronous external inputs
   and unresolved external timing dependencies so operators can audit why a
   signal did or did not enter CDC closure.
8. Rerun the SECDED good DUT and all mutants, the parity memory profile, every
   CDC scheme, async FIFO, reset/RDC, protocol profile, and strict-status path.

Required edge-case behavior:

| Case | Resolution |
| --- | --- |
| Governed input is read only in the policy's clock domain | Classify as synchronous interface input; exclude from CDC path generation; retain policy evidence. |
| Governed input is read in two unrelated domains | Reject the single-domain timing claim and emit a per-domain CDC/timing gap. |
| Policy names a clock that does not own the consuming process | Emit contradicted evidence; do not mark the input synchronous. |
| Input is combinationally transformed before a destination register | Propagate source timing through the combinational dependency graph while retaining the original source identity. |
| Input is captured through two or more ordered synchronizer stages | Keep it as an external asynchronous CDC path and qualify the actual stage chain. |
| Input is a fault-injection/test control used only in formal | Require the depth/formal policy to associate it with a domain or explicitly declare it unconstrained/asynchronous; do not infer safety from its name. |
| Reset or clock port appears in ordinary expression reads | Keep clock/reset ownership logic authoritative and avoid duplicate data-CDC records. |
| A protocol and memory policy assign different clocks to one signal | Emit a contradiction and block both scenarios until configuration is corrected. |
| Legacy RTL facts lack timing-relationship records | Migrate as `unknown`; require re-analysis before a strict formal run can claim closure. |

<a id="source-docsplanningmissing-workmd--quality-01-technical-steps-and-edge-cases"></a>
##### `QUALITY-01` technical steps and edge cases

This is a retained regression/reopen playbook. The listed gates currently pass;
use these steps to investigate a future failure rather than repeating the
already accepted baseline update.

1. Run every failing command independently and retain its complete output:
   compatibility, maintainability, mypy, and Ruff format. Do not combine shell
   commands in a way that returns only the last exit status.
2. For compatibility, capture the normalized current manifest with
   `scripts/checks/compatibility.py --manifest`. Compare it with the last
   released wheel/tag or an archived full manifest. The current baseline stores
   section digests, so the checker should be enhanced to retain or generate a
   field-level diff before anyone accepts new hashes.
3. Classify each CLI/dataclass/module change as additive-compatible,
   intentionally versioned, or breaking. Preserve old imports/dataclass field
   defaults/CLI aliases where the compatibility contract requires them. Update
   `qualification/policies/compatibility-baseline-v1.json` only after review of the normalized delta.
4. Split `configuration/validation.py` into concern-owned modules, for example
   input/frontend validation, execution/tool validation, security/AI validation,
   and depth-policy validation. Re-export existing public/compatibility symbols
   so callers and fingerprints do not change accidentally.
5. Refactor `LiteLLMGateway.execute` into bounded helpers for preflight and
   secret resolution, prompt optimization, one provider attempt, repair-loop
   orchestration, and result recording. Preserve attempt counts, same-model
   repair, exception mapping, optimization metrics, hashes, fallback reasons,
   and one audit record per returned result.
6. Fix `_optional_int()` in `ai/optimization.py` by narrowing accepted runtime
   values before calling `int`. Decide explicitly whether booleans, floats,
   numeric strings, NaN/infinity, negative counts, and oversized values are
   accepted; add tests for every decision.
7. Fix tuple inference in `cli_handlers/dispatch.py` with branch-local variable
   names or an explicit `tuple[str, ...]` declaration. Preserve human and JSON
   output for both context-optimizer status and graph commands.
8. Apply Ruff formatting to the eight reported files, inspect generated diffs,
   and rerun compatibility afterward because formatting should not alter public
   fingerprints.
9. Run the complete CI command sequence from `.github/workflows/ci.yml` in one
   clean checkout, including full tests and real-tool pilots.

Required edge-case behavior:

- A compatibility hash change with no archived normalized baseline is
  unresolved, not automatically intentional. Recover the prior manifest from a
  tag/wheel or add a reviewed one before replacing the digest.
- Module extraction must not create circular package dependencies; rerun the
  maintainability cycle detector after every split.
- Gateway refactoring must still produce exactly one content-free audit record
  for preflight, credential, optimizer, provider, validation, repair-exhausted,
  and accepted paths.
- Provider validation exceptions and JSON decode errors must consume repair
  attempts; transport/auth/rate-limit failures must retain their existing
  deterministic fallback category.
- Formatting changes must not be mixed with compatibility baseline updates in a
  way that obscures semantic API changes.

<a id="source-docsplanningmissing-workmd--doc-02-technical-steps-and-edge-cases"></a>
##### `DOC-02` technical steps and edge cases

1. Create a versioned capability ledger keyed by stable capability/profile ID,
   endpoint role, target, bounded parameters, state, schema/profile version,
   acceptance artifact, test fixture, required tool/version, and last passing
   evidence identity.
2. Populate the ledger from actual executable scenario target states,
   registered renderers/decoders, mutation fixtures, qualification policies,
   and retained real-tool evidence. Do not parse current prose to establish the
   initial truth without evidence review.
3. Mark each Markdown document as either `historical_snapshot` or
   `current_authority`. Historical Stage 4/5 documents retain what was true at
   that stage and link to later stage promotions; they should not be rewritten
   to pretend later capability existed earlier.
4. Generate current capability tables from the ledger or embed stable
   capability markers that `repository_contracts.py` can compare. Validate
   state, targets, bounds, profile version, and acceptance path, not merely that
   a row contains any recognized state word.
5. Reconcile broad protocols (`DOC-00`), APB4/AXI4-Lite native targets,
   SECDED/scrub memory, Stage 8 peripherals, and Stage 9/10 VHDL capabilities
   one evidence family at a time.
6. Replace manually maintained test/coverage counts in current-authority
   documents with evidence-record references or a generated snapshot. Historical
   numbers stay labeled by date and commit.
7. Add repository-contract tests with temporary documents/ledgers for unknown
   capability ID, state mismatch, missing acceptance file, stale evidence hash,
   target mismatch, and historical/current-scope misuse.

Required edge-case behavior:

- A later stage may broaden a capability without invalidating an earlier
  historical exclusion. The current authority should point to both records and
  select the later accepted state.
- A capability may be supported on cocotb but scaffolded on UVM. The ledger must
  not collapse target states.
- A future regression, including a reopened `BUG-CDC-01`, must be representable
  as `regressed` or as a blocking qualification status without erasing the last
  accepted evidence. Release policy must refuse promotion while regressed.
- An acceptance document with a passing mocked/unit path but no real-tool
  evidence cannot promote a real-tool target.
- A test count can change through added negative tests without changing product
  support. Counts are audit metadata, not capability evidence.

<a id="source-docsplanningmissing-workmd--doc-03-technical-steps-and-edge-cases"></a>
##### `DOC-03` technical steps and edge cases

1. Run `check_document_consolidation()` first and retain the seven-file guide
   set, 70-source manifest, stable source anchors, exact local links, and 37
   complete execution/validation cards as the migration baseline.
2. Implement and test the closed catalog JSON schema before writing catalog
   data. Model both a physical Markdown `path` and an optional migrated source
   `anchor`/`source_id`; reject a section that does not resolve inside its
   declared guide.
3. Populate catalog records one class at a time: current authorities,
   operations, architecture/ADRs, active roadmap, append-only progress,
   historical acceptance/stage evidence, indexes, and root compatibility/legal
   files. Run inventory and link/anchor checks after every class.
4. Add or normalize metadata without changing historical claim text. Record
   unresolved state conflicts as `known_issues` and choose the conservative
   current state. Preserve source provenance labels even after metadata is
   cataloged.
5. Continue splitting repository checking into pure functions that accept a
   root path so
   temporary fixture repositories can exercise missing, duplicate, malformed,
   escaped, stale, contradictory, nested-file, and missing-source cases.
6. Reuse actual CLI parser builders. Add side-effect-free parser access for
   `dv-enterprise` and governed Python scripts before validating their examples.
7. Parse command fences structurally. Treat pipelines/redirections as command
   composition, not a reason to skip all validation; validate only known command
   segments and never execute them.
8. Add structured progress transitions keyed by issue/capability, entry ID,
   date/commit, state, and evidence. Reconcile the latest transition with the
   active backlog and reject a stale active/closed contradiction.
9. Add a deterministic index/source-list renderer/checker. Ensure repeated
   runs produce identical bytes and sort by explicit category/order plus
   path/anchor.
10. Add CI checks and update the documentation author workflow, pull-request
   checklist, and agent handoff requirements.
11. Re-run all repository contracts and inspect the generated diff for
    accidental historical rewrites.

Edge-case resolution:

- **Catalog/document disagreement:** fail and print both values; do not select
  one silently.
- **Physical file/source-section disagreement:** fail when a source record
  points to the wrong guide, a missing anchor, duplicate anchor, or a source
  absent from the guide's source-coverage list.
- **Missing date:** current docs require `last_reviewed`; historical docs require
  `snapshot_date`; an inferred Git date is diagnostic context only.
- **Unknown issue ID:** fail until the backlog ID exists or the reference is
  removed.
- **Unknown command family:** keep text, report it as unvalidated, and require an
  explicit catalog classification before claiming command coverage.
- **Negative command example:** require an exclusion marker and reason; test
  that removing the marker makes the checker fail.
- **Historical capability mismatch:** allow only with historical status,
  snapshot identity, and a link to the current successor/regression.
- **Current capability mismatch:** fail regardless of document date or wording.
- **Progress/backlog mismatch:** select the latest machine-ordered transition,
  fail the current backlog state, and require a new closure or regression
  transition; never infer status from an old heading named "Current baseline".
- **Out-of-order progress prose:** retain physical text, use monotonic entry
  identity/commit order for machine chronology, and reject ambiguous equal
  ordering.
- **Performance:** parse/catalog all maintained Markdown within the
  maintainability budget; avoid invoking subprocesses per fence.

Required tests:

- schema round-trip and closed-schema rejection;
- complete physical-file and source-section inventory with exact-once catalog
  coverage;
- missing/duplicate/case-colliding/path-escape/symlink/path-anchor records;
- class-specific metadata and date validation;
- valid/invalid relative links and normalized anchors;
- `dv-platform`, `dv-enterprise`, maintenance, qualification, pipeline, and
  negative command examples;
- current and historical capability-state consistency;
- valid/invalid/unknown/conflicting progress transitions and stale backlog
  state;
- known/unknown backlog references;
- deterministic index output and `--check` behavior.

<a id="source-docsplanningmissing-workmd--tier-01-technical-steps-and-edge-cases"></a>
##### `TIER-01` technical steps and edge cases

1. Add failing distribution/CLI tests that prove the current wheel exposes
   `dv-enterprise` and enterprise entry points without a plan check. Record this
   as the migration baseline rather than deleting entry points first.
2. Add the entitlement schema plus a packaged copy and schema-version constant.
   Test canonical serialization, signature payload identity, unknown fields,
   duplicate capability grants, invalid times, invalid identifiers, and newer
   schema rejection.
3. Add `product/capabilities.py` for stable capability constants/plan sets and
   `product/entitlements.py` for loading, signature verification, time/
   organization/deployment validation, and immutable resolution. The rest of
   the code must consume one `ResolvedProductPlan`; it must not inspect
   entitlement JSON directly.
4. Reuse cryptographic primitives and path containment from enterprise
   qualification where appropriate, but use a distinct signature purpose and
   trust policy. Qualification signers prove test evidence; entitlement issuers
   grant product access. One role must not imply the other.
5. Add optional entitlement/trust configuration with no-entitlement Free
   defaults. Validate paths without following escaping symlinks and avoid
   reading entitlement material until configuration itself passes.
6. Add `require_capability(resolved_plan, capability, operation)` at the
   composition roots: enterprise CLI dispatch, enterprise plugin loading,
   adapter/profile probing, enterprise run/qualification/bundle/signature
   commands, native vendor coverage imports, and board commands. Place the gate
   before imports that can execute plugin module code.
7. Split package metadata and build tests. The Free wheel retains core adapter
   protocols and schemas but does not register proprietary runner or
   `dv-enterprise` implementations. The private Enterprise package registers
   those entry points against a pinned compatible core API.
8. Add plan state to status/JSON and content-free audit. Extend strict policy so
   a configured Enterprise requirement without capability is failed, while an
   unused Enterprise capability is not required for Free closure.
9. Add upgrade/downgrade migration for configuration and state. Keep historic
   run/qualification schemas readable from core; do not import Enterprise
   implementation modules merely to display normalized records.
10. Run the complete Free test matrix against the Free artifact and the
    Enterprise matrix against valid/invalid fixture grants. Verify no network
    call, license environment read, or enterprise plugin import occurs in Free
    negative tests.

Required test matrix:

| Case | Expected result |
| --- | --- |
| No entitlement, Free digital command | Executes normally |
| No entitlement, Free SymbiYosys command | Generates/runs normally when tools are installed |
| No entitlement, any Enterprise command | Stable capability-required error before enterprise side effects |
| Malformed/untrusted/expired entitlement | Enterprise blocked; Free remains usable; invalid state visible |
| Valid grant without requested capability | Only that operation rejects |
| Valid full fixture grant | Declared Enterprise operations become available, subject to normal tool/qualification checks |
| Free and Enterprise run same Free generation input | Generated bytes and plan/check identities match |
| Downgrade with historic vendor evidence | Evidence remains readable; new run/promotion blocked |
| Downgrade with Enterprise-required CI policy | Strict status fails explicitly, never skips |
| Enterprise package absent | Free imports, CLI, schemas, result readers, and status remain functional |

Implementation edge cases:

- Avoid circular imports from status into enterprise entitlement loading; core
  product resolution must be lower-level than both CLIs and adapters.
- Cache entitlement resolution only by entitlement/trust/configuration content
  hashes plus evaluation time policy. Do not retain a grant indefinitely after
  expiry or file replacement.
- Use stable error codes for missing, invalid, expired, insufficient, and
  unavailable Enterprise package states; do not expose signature bytes.
- Plugin metadata inspection must not import untrusted plugin code before the
  capability and existing publisher/package trust checks pass.
- A Free feature implemented in a shared module must not become inaccessible
  merely because that module also contains Enterprise helpers; split ownership
  rather than gating the entire module.
- Test wheel contents and installed entry points, not only source-tree imports,
  because source tests cannot prove the distribution boundary.

<a id="source-docsplanningmissing-workmd--board-01-technical-steps-and-edge-cases"></a>
##### `BOARD-01` technical steps and edge cases

1. Select one legally redistributable FPGA reference board and freeze the exact
   revision, FPGA part/package/speed grade, constraint revision, source license,
   supported onboard devices, and first vendor version. Do not start with an
   unversioned generic "Vivado board".
2. Add manifest and normalized-fact schemas/models/codecs with migration and
   canonical hashes. Keep customer source paths repository-relative or
   content-addressed and retain original constraint artifacts separately.
3. Implement an XDC subset lexer/parser for only the selected commands, such as
   bounded `set_property` and `create_clock` forms with explicit object
   references, or import a structured Vivado resolution report. Reject dynamic
   Tcl evaluation, `source`, file/network/process commands, and unresolved
   queries in required board facts.
4. Build a board reconciler that joins manifest nets/pins/clocks/resets/devices
   to normalized top-level RTL facts and constraint locators by stable identity.
   Emit `supported`, `missing`, `contradicted`, or `unsupported` per fact; never
   reduce the board to one aggregate boolean before reporting diagnostics.
5. Reuse Stage 8 peripheral contracts only after board-specific bindings pass.
   Add explicit external digital models and scenario parameters for the
   selected board devices. Unsupported device modes remain visible and
   non-executable.
6. Add board scenario/check/coverage models and target states. Generate a
   deterministic harness, supplemental constraints, simulator project manifest,
   trace IDs, and evidence manifest without modifying customer files.
7. Extend enterprise profiles with a board simulation capability and, if
   separately selected, an FPGA implementation-report capability. Do not
   overload `vivado_xsim` to claim synthesis/implementation. Gate both through
   `enterprise.board.verify` and the narrower EDA capability.
8. Build a reviewed XSim site wrapper/qualification bundle for the reference
   board. Capture tool/version, board/part/constraint/source/generated hashes,
   exact checks, coverage, return state, bounded logs, and artifacts. Add
   JasperGold only in a separate target matrix.
9. Add good-DUT and mutant pipelines through public Enterprise commands. Include
   schema errors, pin conflicts, wrong part/revision, unsupported XDC, stale
   reports, empty results, and every board-specific semantic mutant.
10. Publish an acceptance record with the exact board revision, profile bounds,
    tool versions, entitlement fixture class, checks/mutants, and exclusions.

Board-specific test fixtures must include:

- exact-good board manifest and immutable constraints;
- missing required pin and duplicate package-pin ownership;
- swapped vector bits and reversed differential polarity where applicable;
- wrong top, FPGA part, package, speed grade, and board revision;
- oscillator frequency and clock-constraint mismatch;
- reset polarity/release mismatch;
- GPIO direction/tri-state mismatch;
- UART/SPI mode and I2C address/open-drain/pull-up mismatches for selected
  devices;
- unsupported XDC command and dynamically resolved wildcard;
- customer/generated constraint ownership conflict;
- vendor report from a different source, board, part, constraint, generated
  artifact, or tool version;
- successful process with empty/unknown/duplicate board check IDs;
- Free-plan invocation proving rejection occurs before board parsing or vendor
  probing.

Do not use XSim success to assert that constraints are electrically legal or
timing closes. If synthesis/implementation report import is added, keep
simulation, elaboration, DRC, timing, CDC/RDC, and physical findings as separate
evidence families with independent required states.

<a id="source-docsplanningmissing-workmd--sem-01-technical-steps-and-edge-cases"></a>
##### `SEM-01` technical steps and edge cases

1. Add a failing semantic fixture in `tests/fixtures/slang/` or a raw Verilator
   XML fixture that isolates one operator/type/generate/property family.
2. Extend normalized types in `domain/rtl.py`/`domain/models.py` and
   `dvsem-v2.schema.json`; update `enterprise/semantics/contracts.py` and all
   RTL fact codecs.
3. Extend the authoritative normalizer in `rtl/slang/` or `rtl/verilator/`.
   Preserve expression width, signedness, cast kind, source location, enclosing
   process/property clock, and specialization identity.
4. Add the corresponding Slang/Verilator comparison rule in
   `analysis/semantic_crosscheck.py`. Classify differences as checked,
   unsupported, or contradictory.
5. Update target safety classification so only renderers capable of preserving
   the semantics can become executable.
6. Add schema migration, round-trip, good fixture, bad fixture, frontend
   disagreement, and strict-generation tests.

Edge cases and resolutions:

- Unsized literals, based literals with unknown bits, self-determined versus
  context-determined widths, signed/unsigned promotion, and truncation must use
  frontend-evaluated width/value metadata; do not reproduce IEEE rules through
  ad hoc Python arithmetic.
- Inactive generate branches must remain represented as unselected evidence so
  a successful empty comparison cannot hide them.
- Interface/modport direction must be resolved at the member and instance level;
  an interface name alone is insufficient.
- Package imports and same-named declarations must retain resolved declaration
  identity, not only display names.
- Multi-clock or disable-iff assertions require explicit clock/reset metadata;
  unsupported temporal operators remain target blockers rather than being
  dropped from the property.

<a id="source-docsplanningmissing-workmd--sem-02-technical-steps-and-edge-cases"></a>
##### `SEM-02` technical steps and edge cases

1. Extend `cross-language-bindings-v1.schema.json` only where the existing
   fields cannot represent elaborator identity, specialization, exact instance
   hierarchy, type adaptation, or completeness. Bump the schema if semantics
   change.
2. Extend `verification/protocols/bindings.py` to validate producer identity,
   exact hierarchy instance, library/unit identity, VHDL architecture, generic
   values, full required port coverage, directions, widths, and compatible
   scalar/vector types.
3. Add a configuration field for the binding manifest and load it during
   `analyze-rtl` after both language frontends have emitted normalized facts.
4. Bind the manifest hash and selected units to the project/RTL manifest.
   Planning must reject mixed-language targets without a complete validated
   binding set.
5. Teach target command construction to compile sources in the elaborator's
   required library/order without a shell. Preserve each source language and
   selected architecture in the execution manifest.
6. Add a real mixed-language compile/elaboration/run fixture and strict status
   test.

Edge cases and resolutions:

- VHDL identifiers are case-insensitive while Verilog identifiers are
  case-sensitive. Store canonical lookup identity and original display spelling
  separately.
- Multiple elaborated specializations of one unit require specialization IDs in
  bindings; reject a bare unit name that matches more than one.
- Partial port maps, duplicate destination ports, width-changing adapters, and
  resolved versus unresolved signal types require explicit adapter semantics;
  reject implicit coercion.
- A null VHDL architecture is acceptable only when the external elaborator
  records one unambiguous selected architecture.
- Generic expressions must carry evaluated type/value and source expression.
  Reject strings that have not been evaluated by the authoritative frontend.
- Binding cycles or an instance path that does not exist in normalized
  hierarchy are manifest errors, not planning open questions.

<a id="source-docsplanningmissing-workmd--sem-03-technical-steps-and-edge-cases"></a>
##### `SEM-03` technical steps and edge cases

1. Extend `core/tool_versions.py` with explicit eligible/tested ranges and
   version parsers that retain vendor suffixes.
2. Define a matrix manifest containing frontend executable, version, platform,
   fixture set, expected semantic hash or approved difference class, runtime,
   and memory budget.
3. Run each fixture through normalization and cross-check. Store raw AST/XML,
   normalized facts, diagnostics, and hashes for comparison.
4. Add external designs through `enterprise/external_design.py` with license,
   source revision, configuration, top, file list, and expected support-state
   metadata.
5. Gate strict status on the exact qualified range and required semantic
   capabilities, not only major version.

Edge cases: vendor-patched version strings, XML/AST field additions, changed
diagnostic ordering, nondeterministic source paths, and designs requiring
unsupported preprocessing must be normalized or classified explicitly. Never
update golden hashes without reviewing semantic differences.

<a id="source-docsplanningmissing-workmd--form-01-technical-steps-and-edge-cases"></a>
##### `FORM-01` technical steps and edge cases

1. Create a new profile name rather than overloading `bounded_response`. Add
   required/optional fields to `configuration/depth_catalog.py` and validation
   in `verification/depth/checks.py`.
2. Extend the plan model/codec and create a scenario builder beside
   `verification/scenarios/formal.py` with explicit stimulus, oracle,
   completion, covers, and target states.
3. Register the scenario and target support in
   `generators/scenario_registry.py`.
4. Put new property rendering in a dedicated
   `formal/generation/` module when it is not a bounded-memory concern. Add
   declarations, assumptions, assertions, covers, stable names, and traceability
   to `FormalGenerator`.
5. Extend `formal/generation/sby.py` with engine/task/mode/depth settings and
   `formal/execution.py` with result, timeout, proof-status, and counterexample
   decoding for the new task.
6. Map every property and cover to canonical check/formal-point IDs and add
   proof, cover, mutant, vacuity, malformed-result, and stale-run tests.

Edge cases and resolutions:

- Multiple clocks require an explicit multiclock semantics/profile; do not pick
  the first clock.
- Asynchronous reset assertion and release must have separately stated formal
  semantics. Do not treat reset as a synchronous enable.
- Contradictory assumptions, a trigger tied low, or a response constrained high
  must fail independent witness/causality covers.
- Unknown/X/Z simulation semantics are not automatically preserved by
  two-state formal engines; document and gate any abstraction.
- Engine `unknown`, timeout, depth exhaustion, and unsupported induction are
  distinct non-closing states.
- Fairness must be named, bounded or justified, and independently witnessed; a
  fairness assumption cannot be generated solely to make liveness pass.

<a id="source-docsplanningmissing-workmd--cdc-01-technical-steps-and-edge-cases"></a>
##### `CDC-01` technical steps and edge cases

1. Add the selected structure and required fields to the CDC depth catalog.
2. Extend normalized CDC facts only if the structure cannot be represented by
   `RTLCDCPath`; retain source/destination domains, ordered stages, fanout,
   reconvergence point, resets, and source locators.
3. Implement fail-closed policy validation in `verification/depth/checks.py`
   and scenario construction in `verification/scenarios/cdc.py`.
4. Add cocotb stimulus/checkers in `generators/cdc.py` and formal properties in
   `formal/generation/cdc.py`/`contracts.py`.
5. Extend the generated CDC evidence report and formal result normalization to
   identify each path and evidence level.
6. Add good structure, wrong-stage-order, missing-stage, reset mismatch,
   reconvergence/coherency failure, and non-vacuity mutants.

Edge cases: unrelated clocks may never produce the sampled phase relationship
seen in a short simulation; reset deassertion can create a false transition;
reconvergent bits can be individually synchronized but mutually incoherent;
Gray encodings fail at wrap or when the source advances too quickly; a hidden
stage cannot be proven through an output latency bound. Resolve these with
explicit rate/reset assumptions, structural observability requirements, and
non-closing bounded evidence. Formal proof cannot prove analog metastability;
state the digital structural contract precisely.

<a id="source-docsplanningmissing-workmd--rdc-01-technical-steps-and-edge-cases"></a>
##### `RDC-01` technical steps and edge cases

1. Define an external result schema for reset/power domains, corners, checks,
   paths, constraints, violations, waivers, and source locators.
2. Implement a governed analyzer adapter through `enterprise/adapters.py` and
   register it only through approved plugin/configuration paths.
3. Reconcile external domain/signal IDs with normalized reset/control-domain
   facts; reject unmatched or multiply matched identities.
4. Import points without allowing the adapter to set closure directly. Merge
   logical reset checks and physical results as distinct required point kinds.
5. Gate status on freshness of design, constraints, technology/library corner,
   tool version, and generated/plan provenance.

Edge cases: multiple reset sources, asynchronous assertion during a clock edge,
glitch filters, test-mode bypasses, isolation sequencing, retention save/restore,
power-off X behavior, and corner-specific violations must retain explicit mode
and corner identity. Waivers must be governed and cannot transfer automatically
between corners or changed paths.

<a id="source-docsplanningmissing-workmd--mem-01-technical-steps-and-edge-cases"></a>
##### `MEM-01` technical steps and edge cases

1. Define one new memory profile or versioned extension and its exact port,
   clock, reset, arbitration, initialization, protection, latency, and
   observability fields.
2. Extend memory/access normalization and claim validation; require concrete
   width/depth and unique read/write mappings.
3. Add a scenario in `verification/scenarios/memory.py`; implement simulation
   reference behavior in `generators/memories.py` and formal behavior in a
   dedicated `formal/generation/` module.
4. Add fault injection only through declared DUT ports or a governed bind
   mechanism. Never rely on unstable simulator hierarchy peeking.
5. Emit per-address-class, collision, arbitration, protection, and liveness
   coverage points appropriate to the bounded depth.
6. Add good-DUT and mutants for every policy branch.

Edge cases: non-power-of-two depth, out-of-range addresses, simultaneous writes
to the same word, overlapping/non-overlapping byte lanes, data width not
divisible by byte-enable width, read-during-write on each port pair, unknown
initial contents, initialization file path/hash/endianness, ECC injection into
check bits versus data bits, scrub starvation, and black-box macro behavior.
Resolve with explicit policy and reject any shape the selected reference model
cannot represent exactly.

<a id="source-docsplanningmissing-workmd--proto-01-and-proto-02-technical-steps-and-edge-cases"></a>
##### `PROTO-01` and `PROTO-02` technical steps and edge cases

1. After `DOC-00`, select one `profile_id`, endpoint role, parameter bound, and
   target. Do not work against the protocol name alone.
2. Update `ProtocolProfile` validation and catalog fields only when the current
   acceptance/completion/burst/outstanding/order/error/timeout model cannot
   express the selected feature.
3. Extend `verification/protocols/recognition.py` for exact canonical or
   explicitly aliased bindings and `verification/scenarios/profiles.py` for
   executable typed intent.
4. Implement or validate driver, monitor, reference model, scoreboard, coverage,
   formal rules, and trace decoder for the selected target in
   `generators/protocols/`.
5. Validate accepted transaction traces through
   `verification/protocols/transactions.py` and the versioned trace schema.
6. Add a good endpoint and one mutant per acceptance, completion, ordering,
   response, burst, outstanding, sideband, and reset rule in scope.
7. Run public CLI analyze/plan/generate/run/coverage/status and record exact
   target state.

Edge cases and resolutions:

- Symbolic or incompatible address/data/ID widths block binding until
  elaborated. Byte lanes must match data width.
- Multiple instances and non-standard signal names require explicit instance
  and one-to-one alias maps.
- Independent channels can arrive in any legal order; scoreboards must not
  assume AW/W, request/data, or response coupling not guaranteed by the profile.
- IDs may be reused only according to outstanding and ordering policy. Detect
  duplicate live keys and orphan responses.
- Bursts must check legal length, size, alignment, boundary, last-beat, and
  response semantics. Unsupported burst types remain explicit.
- Backpressure can be indefinite unless a configured bound exists. Separate
  safety from bounded progress and never invent a fairness assumption.
- Reset during an in-flight transaction must follow a declared flush/recovery
  policy and clear reference-model state deterministically.
- Optional sidebands, user fields, atomic/exclusive operations, retries, split
  responses, and coherency messages are unsupported unless represented in the
  selected profile version.

<a id="source-docsplanningmissing-workmd--periph-01-technical-steps-and-edge-cases"></a>
##### `PERIPH-01` technical steps and edge cases

1. Add a new peripheral contract version or optional feature block in
   `domain/peripherals.py` with exact register/signal mappings and bounds.
2. Extend validation in `verification/depth/peripheral.py` and scenario intent
   in `verification/scenarios/peripheral.py`.
3. Implement BFM/reference behavior and trace points in
   `generators/peripherals.py`; add formal safety and witness covers where a
   digital property is meaningful.
4. Add focused good-DUT and mutants under
   `tests/fixtures/mutations/peripheral/`, preserving all existing profile
   regression tests.

Required feature-specific edge cases include fractional-divisor accumulated
error and sampling phase for UART; CPOL/CPHA, chip-select gaps, word packing,
lane ordering, and contention for SPI; repeated START, address NACK, data NACK,
stretch timeout, arbitration loss, stuck bus, and 7/10-bit address distinction
for I2C; and simultaneous IRQs, mask/clear/ack ordering, timer wrap, PWM 0/100
percent duty, watchdog feed races, and DMA backpressure for subsystem profiles.
Analog voltage thresholds and rise/fall timing stay in `PHYS-01`.

<a id="source-docsplanningmissing-workmd--vhdl-01-technical-steps-and-edge-cases"></a>
##### `VHDL-01` technical steps and edge cases

1. Add the selected profile to VHDL target support only after normalized VHDL
   facts expose every required port, type, generic, architecture, and clock/reset
   mapping.
2. Extend `generators/vhdl.py` and `generators/protocols/vhdl.py` using
   type-correct literals, arrays/records, and deterministic trace records.
3. Extend GHDL command construction and result decoding; retain VHDL standard,
   work library, compile order, selected architecture, and generic overrides.
4. Add good-DUT and mutant fixtures plus exact trace reconciliation and strict
   coverage/status tests.

Edge cases: case-insensitive identifiers, overloaded operators, unresolved
versus resolved signal types, delta cycles, multiple drivers, unconstrained
arrays, ascending versus descending ranges, generic-dependent widths, multiple
architectures, package compile order, configuration declarations, and VHDL
standard differences. Use GHDL/elaborator facts as authority and reject
ambiguous source-only inference.

<a id="source-docsplanningmissing-workmd--uvm-01-technical-steps-and-edge-cases"></a>
##### `UVM-01` technical steps and edge cases

1. Select simulator/version, UVM version, profile, endpoint roles, agent count,
   and RAL scope. Pin them in a qualification contract.
2. Verify generated packages, interfaces, agents, sequences, virtual sequencer,
   scoreboards, RAL model, top, and project bridge compile together.
3. Add stable check/trace IDs to monitor/scoreboard results and require zero
   UVM errors/fatals plus non-empty expected transactions.
4. Normalize transcript and machine-readable results through an enterprise
   adapter. Bind the run to source, plan, generated hashes, tool version, and
   license environment identity.
5. Sign qualification evidence and test signature, signer policy, expiry, and
   stale-provenance rejection.

Edge cases: phase objections never dropping, sequence deadlock, factory
overrides changing component type, analysis-port fanout ordering, transaction
clone/copy errors, RAL mirror/predict races, reset during sequence, passive
agents producing no stimulus, simulator-specific package order or language
dialect, transcript truncation, license checkout failure, and a run with zero
UVM errors but zero transactions. All unfinished/empty cases remain non-closing.

<a id="source-docsplanningmissing-workmd--tool-01-technical-steps-and-edge-cases"></a>
##### `TOOL-01` technical steps and edge cases

1. Define the adapter's accepted tool/version family and machine-readable result
   contract before command construction.
2. Build arguments as a list; validate source/include/define/run paths and never
   invoke a shell. Redact credentials and license server values.
3. Execute through the bounded process/sandbox layer with timeout, output-size,
   environment allowlist, cancellation, and run-local working directory.
4. Parse native structured output where available. Map each result to an
   expected trace/check and retain unknown native results separately.
5. Emit the common validation-result envelope, logs/hashes, tool qualification,
   counterexample paths, and interrupted summary.
6. Add contract tests plus a real-tool qualification bundle.

Edge cases: license queue versus hard failure, process exit zero with failed
properties, non-zero exit with valid counterexamples, partial database write,
localized messages, tool path containing spaces, wrapper command prefixes,
counterexample paths outside the run directory, unsupported encrypted source,
and version drift. Prefer structured reports and explicit adapter error codes
over transcript keyword matching.

<a id="source-docsplanningmissing-workmd--cov-01-and-cov-02-technical-steps-and-edge-cases"></a>
##### `COV-01` and `COV-02` technical steps and edge cases

1. For import, implement `CoverageImporter.supports()` and
   `import_coverage()` in an adapter; for generation, extend typed plan/profile
   coverage intent and a target renderer.
2. Normalize into coverage-v3 metrics, points, stable IDs, goals, hits/status,
   check/requirement/behavior mappings, protocol transaction metadata, and
   dispositions.
3. Pass all data through `execution/coverage/closure.py`; plugins cannot return
   a final pass decision.
4. Merge by stable semantic identity and record source/tool/input hashes.
5. Reconcile executable plan checks, parameter sweep cross-points, and stale
   run/generated provenance before computing closure.
6. Add hit, miss, illegal, ignore, excluded, waived, unreachable, duplicate,
   malformed, stale, and partial-sweep fixtures.

Edge cases: different tools naming the same bin, duplicate imports, cumulative
versus per-run counts, goals greater than one, zero-hit illegal bins, empty
crosses, overflowed counters, source-line movement, excluded-only scopes,
conflicting dispositions, expired waivers, proof-based unreachable evidence
becoming stale, and coverage from a different specialization. Resolve through
canonical IDs and provenance; never merge solely by display name.

<a id="source-docsplanningmissing-workmd--doc-01-technical-steps-and-edge-cases"></a>
##### `DOC-01` technical steps and edge cases

1. Define adapter API/version, accepted MIME/extensions, maximum file/page/text
   sizes, timeout, language options, and local-only/network policy.
2. Run OCR in an isolated work directory and write deterministic sidecars named
   from the original document identity. Record source hash, page number,
   bounding region where available, engine/version, and extraction confidence.
3. Normalize/index chunks through `documentation/indexing.py` with stable chunk
   IDs and cache keys that include source and embedding implementation hashes.
4. Treat all extracted/retrieved text as untrusted evidence. Preserve prompt
   delimiters and never execute instructions found in documents.
5. Add purge/retention, access-control, audit, malformed-input, and offline
   behavior tests.

Edge cases: rotated/skewed pages, mixed scanned/text PDFs, duplicate headers,
tables spanning pages, diagrams without text, password-protected/corrupt PDFs,
very large images, OCR nondeterminism, low-confidence characters in register
addresses, source document replacement, embedding dimension/model changes,
index corruption, PII/secrets, and prompt injection. Resolve by retaining page
evidence/confidence, surfacing ambiguity, rebuilding invalid indexes, and never
promoting low-confidence text directly to executable intent.

<a id="source-docsplanningmissing-workmd--scale-01-technical-steps-and-edge-cases"></a>
##### `SCALE-01` technical steps and edge cases

1. Extend `enterprise/benchmark.py` with versioned corpus metadata and budgets
   for discovery, parsing, indexing, planning, generation, execution, coverage,
   wall time, peak RSS, output bytes, and cache behavior.
2. Introduce a bounded scheduler with separate CPU, memory, formal-engine, and
   license-token limits. Keep task ordering and final aggregate output
   deterministic.
3. Use isolated run/staging directories and atomic publication. Ensure
   cancellation propagates and writes interrupted summaries.
4. Measure cold/warm cache, one/many modules, large XML/PDF, parameter sweeps,
   and mixed fast/slow formal tasks.
5. Enforce regression thresholds in dedicated CI where host variance is
   controlled.

Edge cases: one task exhausting memory, file-descriptor/process limits, license
starvation, scheduler deadlock, cancellation during publish, cache stampede,
same artifact generated concurrently, a slow task blocking ordered result
publication, noisy-neighbor timing, and partial aggregate summaries. Resolve
with resource admission, bounded queues, deterministic result collation,
content-addressed caches, atomic writes, and explicit interrupted states.

<a id="source-docsplanningmissing-workmd--plat-01-technical-steps-and-edge-cases"></a>
##### `PLAT-01` technical steps and edge cases

1. Define exact OS/distribution/kernel, architecture, Python, filesystem,
   container runtime, and EDA-tool combinations.
2. Add installation, tool-probe, analyze/generate/run/coverage/status smoke
   tests on each candidate.
3. Compare generated bytes and normalized evidence across platforms. Classify
   acceptable tool-specific differences explicitly.
4. Test upgrade/rollback, permissions, sandboxing, path allowlists, signal
   handling, and support-bundle generation.
5. Promote a platform only when required real-tool paths pass; otherwise label
   it best-effort with exact exclusions.

Edge cases: case-insensitive filesystems, drive letters/UNC paths, symlink and
junction behavior, path-length limits, executable suffixes, line endings,
locale/timezone, process groups/signals, container UID mapping, rootless
runtime differences, and unavailable EDA binaries. Normalize presentation
where safe; do not hide behavioral differences.

<a id="source-docsplanningmissing-workmd--ai-01-ai-02-and-phys-01-conditional-implementation-notes"></a>
##### `AI-01`, `AI-02`, and `PHYS-01` conditional implementation notes

No implementation should begin until the decision package is approved. If
approved:

1. Version the approved capability and keep it opt-in behind explicit policy.
2. Add immutable provenance and human approval identity for every newly allowed
   action/evidence type.
3. Execute generated commands/artifacts only through deterministic validators,
   sandbox/resource controls, and the normal plan/revision/run/coverage gates.
4. Add adversarial tests before positive qualification.

AI edge cases include prompt injection in RTL/docs, source or secret disclosure,
model/provider version drift, malformed structured output, nondeterministic
code, dependency hallucination, unsafe commands, license contamination, cache
reuse across policy/model/context changes, provider outage, cost exhaustion,
and disagreement between providers. Resolve by retaining current bounded
proposal behavior as fallback, content/policy-addressed cache keys, strict
schemas, endpoint allowlists, secret indirection, no shell execution, human
approval, and deterministic compilation/verification.

Physical-sign-off edge cases include mismatched units, corners, libraries,
constraint revisions, hierarchical names, black boxes, false/multicycle paths,
mode-specific waivers, analog thresholds, and stale layout/netlist identity.
Resolve through versioned external evidence keyed to exact design,
constraints, tool, technology, mode, and corner; never translate absence of a
violation report into a pass.

<a id="source-docsplanningmissing-workmd--per-ticket-implementation-and-validation-cards"></a>
### Per-Ticket Implementation and Validation Cards

Use these cards after the Zero-Assumption Agent Execution Protocol. The
implementation list is the required ticket-specific sequence. The validation
list is additive to the mandatory validation order; it names the tests and
evidence that must be visible at handoff.

<a id="source-docsplanningmissing-workmd--product-feature-cards"></a>
#### Product feature cards

<a id="source-docsplanningmissing-workmd--free-digital-01-execution-card"></a>
##### `FREE-DIGITAL-01` execution card

**Gate and scope:** begin only after `TIER-01` defines package/capability
ownership. Freeze the existing bounded digital profile/target matrix; this card
does not broaden RTL semantics, protocols, tools, or target support.

**Implementation:**

1. Generate an inventory manifest for Free-owned commands, imports, schemas,
   templates, profiles, renderers, open-tool runners, decoders, coverage, and
   status rules. Mark each package path Free, shared-normalized, or Enterprise.
2. Add stable `core.digital.analyze`, `core.digital.generate`, and
   `core.digital.execute.open` capability declarations and map every public
   command/API to exactly one declaration.
3. Build a Free distribution that contains only Free/shared resources. Remove
   imports and entry points that load Enterprise code, profiles, license
   variables, private package state, or vendor tools.
4. Route analysis, deterministic planning, generation, execution, result
   reconciliation, coverage, and strict status through the same capability and
   provenance contracts used before packaging.
5. Add Free-to-Enterprise compatibility readers for normalized historical
   evidence without enabling new Enterprise execution.
6. Update configuration defaults, package metadata, operator docs, feature
   ledger, and acceptance with exact supported profiles/targets and exclusions.

**Validation:**

1. Add wheel-content tests that fail for every Enterprise module, entry point,
   schema, template, or dependency in the Free wheel and fail when a required
   Free resource is absent.
2. Install the Free wheel in clean Python 3.11/3.12/3.13 environments with no
   entitlement, private package, vendor variables, or network; run init,
   analyze, plan, every claimed digital generator, open-tool run, coverage, and
   strict status.
3. Run every existing claimed profile's good DUT and full mutant matrix from
   the installed Free wheel. Compare plan IDs, generated bytes, result IDs, and
   coverage with the pre-split accepted behavior.
4. Install Enterprise over Free, repeat the Free workflows, remove/downgrade
   Enterprise, and repeat again. Free outputs must remain equivalent and
   historical normalized evidence readable.
5. Instrument imports, environment reads, subprocesses, and network calls.
   Rejected/missing Enterprise state must produce zero Enterprise imports,
   vendor probes, license reads, and network attempts.
6. Run packaging, compatibility, reproducibility, full regression, and the
   `FREE-DIGITAL-01` feature-coverage validator. Retain wheel hashes and the
   complete profile/target/mutant result table.

**Stop condition:** any profile whose real open tool, decoder, exact checks, or
mutation evidence does not close remains excluded from the Free acceptance
record; packaging must not promote it.

<a id="source-docsplanningmissing-workmd--free-formal-01-execution-card"></a>
##### `FREE-FORMAL-01` execution card

**Gate and scope:** `TIER-01` must assign SymbiYosys/Yosys/approved solver to
Free. Freeze the currently qualified bounded formal profiles, tool versions,
tasks, depths, assumptions, properties, covers, and unsupported operators.

**Implementation:**

1. Inventory formal policy/scenario models, harness/SBY generation, task
   construction, execution, decoder, counterexample handling, formal coverage,
   non-vacuity, strict status, schemas, templates, and package resources.
2. Declare `core.formal.generate.symbiyosys` and
   `core.formal.execute.symbiyosys`; enforce them independently of Enterprise
   entitlement and vendor-surrogate qualification.
3. Validate exact tool/dependency versions, engine/solver compatibility,
   bounds, timeout/memory/output limits, work paths, and sandbox policy before
   generation or execution.
4. Generate assumptions/assertions/invariants/covers/harness/SBY tasks only
   from supported typed semantics and retain check/property/task/source
   provenance.
5. Decode prove/cover/induction/unknown/failure outcomes and counterexamples
   into canonical checks and formal coverage; make vacuity, missing tasks, and
   unsupported engines non-closing.
6. Package all required formal templates/schemas and document exact Free
   bounds, tool installation, exclusions, and failure triage.

**Validation:**

1. Install the Free wheel without Enterprise state and run every claimed formal
   profile's good DUT, prove/cover tasks, non-vacuity witnesses, and complete
   targeted mutants on pinned SBY/Yosys/solver versions.
2. Exercise minimum/maximum and outside bounds, missing/ambiguous clocks/resets,
   contradictory/over-constraining assumptions, unreachable triggers/covers,
   unsupported temporal operators, timeout, signal, malformed/empty output, and
   unknown/duplicate tasks.
3. Verify every mutant fails its intended property after setup succeeds; a
   compile error, unrelated assertion, timeout, or solver crash is not a kill.
4. Verify counterexample path containment, bounded size, source/check mapping,
   redaction, stale rejection, and deterministic aggregate ordering.
5. Compare Free and Enterprise runs for identical open-tool inputs: harness/SBY
   bytes, task/check IDs, results, coverage, and status must match.
6. Run installed-wheel, repeat-generation, concurrency/cancellation, branch
   coverage, full regression, and `FREE-FORMAL-01` ledger validation. Retain
   exact tool banners and per-task evidence.

**Stop condition:** a passing assertion set with an unreachable mandatory
assumption witness, trigger, response, or completion cover is vacuous and cannot
close the feature.

<a id="source-docsplanningmissing-workmd--plan-gate-01-execution-card"></a>
##### `PLAN-GATE-01` execution card

**Gate and scope:** product/security owners must approve entitlement issuer,
trust roots, time/offline/grace policy, package names, and capability catalog.
Do not implement a locally self-signed production bypass.

**Implementation:**

1. Add the closed entitlement schema, canonical signing payload, capability
   registry, Free/Enterprise sets, trust/time policy, and immutable
   `ResolvedProductPlan` with `free`, `enterprise`, `invalid`, and approved
   `grace` states.
2. Implement one loader/verifier/resolver and one central `require_capability`
   API with stable error codes and content-free audit records.
3. Enumerate all CLI commands, direct APIs, plugins, adapters, qualification,
   board, evidence-import, and status entry points; attach an explicit
   capability declaration to each.
4. Place checks before package/plugin import, environment/license/secret read,
   tool discovery, network, filesystem mutation, wrapper generation,
   subprocess, evidence import, and publication.
5. Split and build Free/Enterprise packages, define shared normalized history
   readers, and implement upgrade/downgrade/expiry/rotation/cache invalidation.
6. Expose plan/capability/entitlement state safely in human/JSON status and
   support bundles; update operator/security/licensing/migration documents.

**Validation:**

1. Unit-test canonical bytes, every schema/type/range/time/signature/trust/
   organization/capability error, old-version migration, newer-version
   rejection, key rotation, clock boundaries, and cache invalidation.
2. Add a repository test that enumerates public Enterprise entry points and
   fails if any lacks a capability declaration or reaches side effects before
   the gate.
3. Test every state transition in the `PLAN-GATE-01` table, including valid/
   invalid installation, limited grant, expiry during work, rotation,
   downgrade, repair, grace expiry, and clock/trust change.
4. For every denied path assert exit/status/audit plus zero imports, environment
   reads, network calls, filesystem mutations, tool probes, and subprocesses.
5. Attack direct API calls, copied state, malformed signatures, symlinks,
   plugin bypass, environment overrides, local clock manipulation, concurrent
   resolution, and stale valid/invalid caches.
6. Run separate clean installed Free/Enterprise suites, wheel-content and
   reproducibility checks, upgrade/downgrade rollback, full regression, and the
   capability coverage ledger.

**Stop condition:** if issuer/trust/offline policy is unresolved, implement
schema/test fixtures only and leave production Enterprise resolution disabled.

<a id="source-docsplanningmissing-workmd--ent-eda-01-execution-card"></a>
##### `ENT-EDA-01` execution card

**Gate and scope:** select exactly one adapter family/profile/tool version and
required Enterprise capability. Contract work may begin without a license;
support promotion requires legal real-tool execution and approved signature
evidence.

**Implementation:**

1. Define adapter/profile/version, languages, supported tasks, executable
   discovery, site-wrapper contract, license variable names, environment
   allowlist, inputs/results/artifacts, time/resource limits, and normalized
   check/coverage identities.
2. Add entitlement gating before adapter import/discovery, environment reads,
   tool/version/license probes, wrapper generation, or run-directory mutation.
3. Build argv without a shell; validate source/include/define/library/work/
   result/artifact paths and execute only an approved bounded wrapper.
4. Parse the tool's structured result where available; normalize exact
   check/property/bin/counterexample identities and preserve unknown output as
   non-closing diagnostics.
5. Reconcile source/config/plan/generated/tool/profile/entitlement provenance,
   expected checks, coverage, process result, and artifact hashes.
6. Add qualification bundle creation/import, independent signature/trust
   verification, freshness policy, status integration, and exact adapter
   acceptance documentation.

**Validation:**

1. Run contract fixtures for executable absent/wrong/changed, all license
   states, wrapper/path/environment failures, timeout/signal/child cleanup,
   malformed/partial/oversized output, and process/result contradictions.
2. Test unknown/duplicate/missing/skipped checks, source/counterexample path
   escape, stale provenance in every dimension, bad artifact hashes, bad/newer
   schemas, and deterministic collation.
3. Test entitlement denial before all observable side effects and concurrent
   jobs below/at/above license-token capacity, queued cancellation, and no
   cross-run leakage.
4. Run the generated good DUT and feature-specific mutant matrix in the actual
   selected licensed tool/version; verify each intended checker and coverage
   point executes non-vacuously.
5. Import independently signed evidence under the approved trust policy; reject
   self-signature, untrusted/expired signer, altered attestation, wrong
   tool/profile/version, and stale generated bytes.
6. Run installed Enterprise package, strict status, branch/full regression,
   adapter feature ledger, and publish one profile/version acceptance record.

**Stop condition:** mock or surrogate success cannot move the adapter beyond
`contract_verified`/`surrogate_verified`.

<a id="source-docsplanningmissing-workmd--ent-board-01-execution-card"></a>
##### `ENT-BOARD-01` execution card

**Gate and scope:** `TIER-01` and the selected Enterprise EDA adapter must be
ready. Freeze one legal board vendor/name/revision, exact FPGA part/package/
speed grade, constraints, tool version, digital peripheral set, and physical
exclusions.

**Implementation:**

1. Assign stable board requirement IDs and add closed board-manifest and
   board-facts schemas/models/codecs/migrations/provenance.
2. Implement a bounded non-executing constraint parser/importer and normalize
   exact pin/net/bank/I/O/clock/reset/device/source locators.
3. Reconcile board, constraints, RTL, peripherals, clocks/resets, and vendor-
   resolved facts into supported/missing/contradicted/unsupported states.
4. Build typed digital board scenarios, external-component models, checks,
   coverage, and target states only for the frozen profile.
5. Generate deterministic supplemental constraints, board harness/project, and
   manifests without modifying customer/user-owned artifacts.
6. Gate and run the selected vendor simulator/tool, decode exact board results,
   reconcile coverage/status, and publish signed profile evidence.

**Validation:**

1. Test every identity/revision/part/package/speed/pin/bank/I/O/clock/reset/
   peripheral case in the `ENT-BOARD-01` matrix, including aliases,
   case/range/vector swaps, tri-state/open-drain behavior, and wrong-board
   mutants.
2. Fuzz constraint parsing with unsupported Tcl, `source`, substitutions,
   recursion, malformed quoting, oversized input, path/process/network/
   environment attempts, and wildcard zero/multiple matches; execute none.
3. Verify deterministic bytes, user-file immutability, supplemental ownership,
   atomic interruption/concurrency, path containment, and stale board/RTL/tool/
   constraint provenance.
4. Run good design plus one targeted mutant per board requirement and
   validation rule through installed Enterprise artifacts and the exact vendor
   tool/profile.
5. Test missing/invalid/limited entitlement and mismatched board/EDA
   capabilities before parsing or side effects; test downgrade and read-only
   historical evidence.
6. Close exact results/coverage/strict status and the board feature ledger;
   acceptance must list physical, analog, implementation, and hardware-lab
   exclusions.

**Stop condition:** no evidence for one board revision, tool, or digital
peripheral may promote another board/revision/tool or physical behavior.

<a id="source-docsplanningmissing-workmd--release-quality-and-governance-cards"></a>
#### Release, quality, and governance cards

<a id="source-docsplanningmissing-workmd--qual-01-execution-card"></a>
##### `QUAL-01` execution card

**Gate and scope:** implement with `SCALE-02`; define historical, reusable, and
current-candidate evidence without changing Stage 11-13 pending state.

**Implementation:**

1. Add closed qualification-gate v2 policy/schema and typed validator registry
   for every Stage 6-13 evidence family.
2. Add contextual GA verification for expected stage/commit/tree/workflow/
   lock/artifacts/policy and a single candidate evidence bundle.
3. Replace ambiguous log parsing with one machine test-result manifest; bind
   coverage policy and artifact subjects into the bundle.
4. Add versioned impact keys/freshness rules with fail-closed unknown path
   classification.
5. Split ledger-structure and candidate-promotion modes; make accepted Stage 10
   candidate mode mandatory in CI and remove required-evidence skips.
6. Wire exact workflow artifact/run/attempt identity, WSL policy, actionlint,
   and qualification documentation.

**Validation:**

1. Run `tests.qualification.test_ga_gates`,
   `tests.qualification.test_ga_evidence`, every type-specific qualification
   test, and new contextual/impact/workflow-contract suites.
2. Mutate every schema field and commit/tree/workflow/lock/tool/artifact/
   coverage/evidence identity independently; require the exact owning
   diagnostic.
3. Test historical-only/current/reusable/stale/mixed-run/missing-type,
   multiple/contradictory test summaries, required skips, cancellation,
   reruns, fork, and expired artifacts.
4. Run actionlint and semantic workflow tests for all events/path filters/job
   dependencies/stage arguments/artifact handoffs.
5. Produce a clean exact-commit Stage 10 candidate bundle, validate it, change
   every impact input one at a time, and prove replacement evidence is required.
6. Run repository/full regression and retain the candidate bundle, validator
   output, impact manifest, and historical/current state table.

**Stop condition:** `ga_gates.py` ledger validity is never sufficient candidate
or release evidence.

<a id="source-docsplanningmissing-workmd--release-01-execution-card"></a>
##### `RELEASE-01` execution card

**Gate and scope:** release owners must approve channel/minimum-stage/
destination policy; `QUAL-01` must provide exact-candidate verification.

**Implementation:**

1. Add a parsed version-channel policy for development/alpha/beta/RC/GA/patch,
   allowed tags, minimum gates, destinations, and approvals.
2. Resolve and verify tag object/target, exact SHA, package version, channel,
   protected source, and successful exact-SHA candidate bundle before build.
3. Reuse the mandatory validation workflow or rerun every gate; never select
   branch-latest green state.
4. Build once and create one release manifest binding source/workflow/lock,
   distributions, SBOM, checksums, provenance, test/coverage, and qualification.
5. Verify exact context after every immutable artifact handoff, then attest,
   sign, approve, publish idempotently, and reinstall the exact remote digest.
6. Emit signed release/recovery state and update promotion ledger only after
   publication and reinstall pass.

**Validation:**

1. Unit-test every valid/invalid version/tag/channel including current
   `v0.1.0`, RC sequence, final, future patch, malformed, moved, and mismatched
   tags.
2. Test exact green SHA, wrong/stale SHA, missing/failed/skipped/cancelled
   matrix member, rerun attempts, fork/untrusted actor, and environment denial.
3. Mutate repository/ref/SHA/builder/lock/package/subject/artifact identities in
   release materials and attestations; contextual verification must reject.
4. Run build-once reproducibility and clean installs for all supported Python
   versions, then dry-run attest/sign/verify against a disposable test index.
5. Test matching-digest idempotent retry, conflicting remote digest, signing-
   only failure, publish failure, published-but-reinstall-failed recovery, and
   secret-free logs.
6. Retain one exact-SHA dry-run release record and prove any source/workflow/
   lock/tag/version/artifact change invalidates it.

**Stop condition:** until channel policy exists, every otherwise publishable
`v*` tag fails before build.

<a id="source-docsplanningmissing-workmd--scale-02-execution-card"></a>
##### `SCALE-02` execution card

**Gate and scope:** select one accepted immutable baseline and exact Ubuntu
runner class; WSL requires its own runner/evidence or remains non-current.

**Implementation:**

1. Add performance v3 with independent baseline/candidate identities,
   comparability policy, repetitions/statistics, functional result, process-
   tree resource metrics, runner class, and payload digest.
2. Add protected baseline promotion/storage and read-only candidate lookup.
3. Build/install the candidate wheel in an isolated environment and reject
   source-tree imports.
4. Benchmark real discovery/normalization, document ingest/index/search,
   planning, generation/persistence/status stages with deterministic semantic
   result counts/hashes.
5. Isolate stages/process trees, collect wall/CPU/RSS/I/O/output metrics, run
   warmups/repetitions, and enforce variance plus absolute/relative budgets.
6. Expand impact-triggered Ubuntu/WSL workflows, evidence bundle, `QUAL-01`
   integration, and v2 historical migration.

**Validation:**

1. Run `tests.enterprise.test_benchmark_runner`,
   `tests.qualification.test_performance_qualification`, and new v3 schema/
   comparability/statistics/runner/impact tests.
2. Build controlled baseline/candidate wheels with intentional time and memory
   regressions; catch >limit, exact limit, under limit, absolute-budget, and
   variance failures.
3. Add no-op/incomplete-output mutants for every benchmark stage and require
   functional failure before metric comparison.
4. Test cold/warm contamination, process timeout/kill/descendants, parallel
   load, outliers, zero/NaN/infinite metrics, baseline expiry/conflict, runner
   drift, artifact loss, and unauthorized promotion.
5. Produce a real installed-wheel Ubuntu comparison against an independent
   baseline and WSL evidence or explicit WSL downgrade.
6. Validate the bundle through `QUAL-01`, run full regression, and retain raw
   repetitions, aggregate, comparison, function results, and baseline digest.

**Stop condition:** two runs of the same commit/wheel remain repeatability
evidence only and can never satisfy regression qualification.

<a id="source-docsplanningmissing-workmd--ai-03-execution-card"></a>
##### `AI-03` execution card

**Gate and scope:** preserve advisory AI authority. Use deterministic fake
services; host optimizer compatibility is opt-in evidence only.

**Implementation:**

1. Add explicit `off`/`advisory`/`required` modes and deterministic legacy
   migration for Headroom and code graph independently.
2. Move optimizer invocation behind common stage/network/credential/cache
   preflight.
3. Implement managed MCP process-group/context-manager lifecycle with
   idempotent EOF/terminate/wait/kill/wait/pipe cleanup in `finally`.
4. Add bounded deadline-aware MCP framing, protocol/capability/tool
   negotiation, environment/resource allowlist, and graph freshness/atomic
   update.
5. Deny/revalidate Headroom redirects, disable proxies, enforce loopback,
   response bounds/types/anchors, and approved prompt-role disclosure.
6. Bind optimizer mode/version/config/output/graph identity to cache,
   content-free audit, status, and planning provenance.

**Validation:**

1. Extend `tests.ai.test_context_optimization` with fake MCP/HTTP fixtures for
   healthy, unavailable, timeout, crash, malformed/oversized/partial framing,
   wrong IDs, notification flood, redirect, proxy, DNS/host, and anchor cases.
2. Test all mode/stage/preflight/cache/config-migration combinations and exact
   human/JSON/audit/exit/context-hash behavior.
3. Assert zero process/descriptor growth after 100 repeated failures and
   concurrent planners; capture ResourceWarnings/unraisable exceptions as test
   failures and enforce a runtime ceiling.
4. Test secret/license/proxy environment absence, child descendants ignoring
   signals, cancellation/KeyboardInterrupt at every I/O/update/close boundary,
   and graph update races/crashes.
5. Run one explicit real-version compatibility test with protocol/tool/graph
   provenance; ordinary tests must prove installed host services are unused.
6. Run AI branch coverage, full regression, process census, and feature ledger;
   retain before/after counts and no-warning output.

**Stop condition:** any unbounded body read, redirect outside loopback, inherited
secret, live descendant, or unclosed descriptor keeps the ticket open.

<a id="source-docsplanningmissing-workmd--bug-cdc-01-regression-card"></a>
##### `BUG-CDC-01` regression card

**State:** closed. Do not change implementation unless the named regression
reproduces. Every CDC, memory, external-input timing, frontend, or formal change
must run this card.

**Validation:**

1. Run the focused SECDED formal good-DUT/five-mutant test on qualified
   Verilator/SBY/Yosys/Z3 versions.
2. Run parity/SECDED simulation, all CDC schemes, async FIFO, reset/RDC, formal
   depth, and strict-status integration tests.
3. Inspect normalized CDC output: governed synchronous memory controls must not
   appear as unsafe crossings; unknown/asynchronous and multi-domain controls
   must remain non-closing.
4. Run the legacy-fact migration, conflicting-policy clock, combinational
   propagation, synchronizer-stage, reset/clock de-duplication, and formal-only
   control cases from the technical playbook.
5. If any required case fails, append a `regressed` progress transition with
   exact command/tool/source evidence and reopen `BUG-CDC-01`; do not silently
   weaken CDC policy.

**Completion evidence:** focused and related matrices pass, five intended
mutants are killed by their properties, no required test skips, and strict
status closes the good DUT.

**Stop condition:** any failure reopens the ticket as a regression; do not
modify the implementation or claim closure from an aggregate suite until the
focused failure is reproduced and triaged.

<a id="source-docsplanningmissing-workmd--quality-01-regression-card"></a>
##### `QUALITY-01` regression card

**State:** closed. Run after public API/CLI/dataclass/module changes,
configuration/gateway refactors, dependency updates, or broad formatting.

**Validation:**

1. Run Ruff lint and format check, mypy, compatibility, maintainability, and
   repository contracts independently and retain each exit/output.
2. Compare normalized compatibility manifest with the reviewed baseline; any
   digest change requires field-level classification and shim/version decision.
3. Run gateway audit/fallback/repair and optimizer metric edge cases plus
   configuration validation/cycle/complexity tests affected by the prior fix.
4. Run branch coverage/ratchets, full tests with required tools, package build/
   reproducibility, secrets, Bandit, and dependency audit.
5. If a gate regresses, append a `regressed` transition and reopen the ticket;
   never close by raising limits, deleting tests, adding blind ignores, or
   replacing fingerprints without review.

**Completion evidence:** every mandatory command passes in one clean checkout,
compatibility delta is zero or reviewed/versioned, and full-suite skips/warnings
are acceptable and recorded.

**Stop condition:** any mandatory quality gate failure reopens the ticket; do
not suppress the gate or update a baseline before classifying the underlying
change.

<a id="source-docsplanningmissing-workmd--doc-00-execution-card"></a>
##### `DOC-00` execution card

**Gate and scope:** evidence review only; do not implement or promote protocol
behavior under this documentation ticket.

**Implementation:**

1. Enumerate every broad profile, endpoint role, bound, and target from the
   machine profile/scenario/renderer registries.
2. Trace each cell to schema/model, generator, decoder, good DUT, mutants,
   coverage, strict status, real tool, CI job, and acceptance evidence.
3. Build a review table classifying each cell supported/partial/scaffold/
   unsupported from evidence; unresolved or skipped real-tool cells take the
   conservative state.
4. Store the reviewed state in one machine capability ledger and update
   capability matrix, protocol architecture, acceptance, and roadmap from it.
5. Add consistency validation so prose cannot diverge by profile/role/target/
   bound/evidence identity.

**Validation:**

1. Run production-profile, recognition, transaction-model, generation, broad
   good-DUT, native/formal/CLI, mutation, coverage, and strict-status tests for
   every cell claimed supported.
2. Run with required tools absent and verify the claim becomes unavailable/
   non-closing rather than inheriting a generated target.
3. Seed deliberate state, target, bound, role, and evidence-path contradictions
   in fixture repositories; repository contracts must fail exactly.
4. Compare generated current docs/indexes twice for byte stability and validate
   all links/anchors/known issue IDs.
5. Retain the signed/reviewed profile-by-target table and test/evidence links;
   no code support state changes belong in this ticket.

**Stop condition:** a renderer or parser fixture without end-to-end measured
good-DUT/mutant evidence is not support.

<a id="source-docsplanningmissing-workmd--doc-02-execution-card"></a>
##### `DOC-02` execution card

**Gate and scope:** consume `DOC-00` state and current evidence; preserve all
historical snapshot wording.

**Implementation:**

1. Add/extend the machine capability/evidence ledger with profile, role,
   target, bounds, schema/profile version, current/historical state, evidence,
   tool/version, and last passing identity.
2. Classify every conflicting document current authority or historical
   snapshot; add required metadata, successor/regression links, and known IDs.
3. Reconcile broad protocols, native APB/AXI, SECDED, Stage 8 peripherals,
   VHDL, stale issue lists, and current test/evidence references one family at
   a time.
4. Generate or marker-bind current capability tables/count snapshots from the
   ledger while leaving historical numbers and conclusions time-scoped.
5. Extend repository contracts to compare exact capability IDs/states/targets/
   bounds/versions/evidence, not state words.

**Validation:**

1. Run every real-tool/good-DUT/mutant test needed to establish the chosen
   current state; mocked or skipped evidence remains conservative.
2. Add contradiction fixtures for unknown ID, state/target/bound/version
   mismatch, missing/stale evidence, current-as-historical misuse, and later
   regression without state transition.
3. Run repository contracts, generated documentation checks, link/anchor
   checks, and capability matrix/strict-status comparison.
4. Verify historical documents remain byte-identical except metadata and
   successor links; inspect the diff explicitly.
5. Retain the reconciled ledger, contradiction-test results, and current versus
   historical mapping table.

**Stop condition:** unresolved evidence selects the more conservative current
state and remains an open linked issue.

<a id="source-docsplanningmissing-workmd--doc-03-execution-card"></a>
##### `DOC-03` execution card

**Gate and scope:** use `DOC-02`'s capability ledger; do not create a second
state authority. The seven-guide consolidation, 70 preserved source sections,
link/anchor validation, and 37-card validation are complete foundations and
must remain passing.

**Implementation:**

1. Add the closed document-catalog schema and catalog all 12 maintained
   physical Markdown files plus all 70 migrated source sections exactly once,
   using `path` plus stable `anchor`/`source_id`.
2. Add class-specific metadata for authority/scope/status/date/supersession/
   issues/capabilities/schemas/commands/evidence while preserving historical
   source text and provenance.
3. Extend repository contracts with pure catalog, metadata, capability,
   command, and progress-transition checks while retaining the completed flat
   layout, source coverage, local link/anchor, and card checks.
4. Add safe parser-only validation for public CLIs/scripts and structural
   handling for multiline commands, environment prefixes, pipelines,
   redirection, placeholders, and marked negative examples.
5. Add machine progress transitions and reconcile newest valid issue state with
   this backlog; generate deterministic `docs/README.md`, guide source lists,
   and latest-status views.

**Validation:**

1. Run `tests.repository.test_repository_contracts` plus fixtures for missing/
   duplicate/case-colliding/symlink/escaped paths and anchors, wrong guide/source
   pairing, nested Markdown, metadata/date/authority/supersession errors, and
   exact-once physical/source inventory.
2. Test GitHub-style anchors, repeated headings, punctuation/code/Unicode,
   valid/invalid command families, placeholders, dangerous/network/licensed
   annotations, and negative-example exclusions.
3. Test unknown/conflicting/out-of-order progress transitions, closed-active
   mismatch, reopened regression, missing closure evidence, and old headings
   named current.
4. Run catalog/index/source-list generation twice and compare bytes; run
   repository contracts across all maintained Markdown/source sections and
   inspect historical diffs.
5. Retain catalog schema/data, generated indexes/status, negative fixture
   outputs, and coverage/maintainability results for checker modules.

**Stop condition:** an uncataloged physical file/source section, a regression
from the seven-guide/source/card baseline, or an unresolved current capability/
backlog contradiction fails mandatory CI.

<a id="source-docsplanningmissing-workmd--product-packaging-and-board-cards"></a>
#### Product packaging and board cards

<a id="source-docsplanningmissing-workmd--tier-01-execution-card"></a>
##### `TIER-01` execution card

**Gate and scope:** Free and Enterprise product direction is fixed. Owner
approval is still required for entitlement issuer/trust/offline policy, private
package names/index, and production key custody. This ticket owns
`FREE-DIGITAL-01`, `FREE-FORMAL-01`, and `PLAN-GATE-01`.

**Implementation:**

1. Freeze the capability catalog, Free/Enterprise matrix, package ownership,
   entry-point inventory, issuer/trust/time/offline policy, and migration
   boundary.
2. Add closed entitlement schema, canonical payload/signature verification,
   immutable plan resolver, stable errors/audit, and central capability gate.
3. Split Free/shared/Enterprise code and resources into independently built
   artifacts; remove private imports/entry points from Free.
4. Gate every Enterprise CLI/API/plugin/adapter/qualification/board path before
   side effects and preserve normalized historical readers on downgrade.
5. Implement status/support, installation/upgrade/downgrade/expiry/rotation,
   cache invalidation, rollback, security/licensing/operator documentation, and
   release-package policy.

**Validation:**

1. Complete every `PLAN-GATE-01` state/signature/trust/time/side-effect/
   bypass/concurrency test.
2. Complete `FREE-DIGITAL-01` and `FREE-FORMAL-01` installed-wheel good-DUT/
   mutant/open-tool matrices without entitlement or Enterprise package.
3. Run wheel/sdist content, dependency, entry-point, reproducibility, clean
   install, upgrade/downgrade/rollback, Python version, and package coexistence
   tests.
4. Enumerate every public entry point at test time and prove its capability and
   pre-side-effect gate; direct API/plugin/environment bypasses must fail.
5. Run security threat tests, full Free and Enterprise contract regressions,
   feature ledgers, compatibility, release dry run, and publish exact package/
   capability acceptance records.

**Stop condition:** unresolved production issuer/offline policy permits
non-production fixture keys only; Enterprise remains disabled for production.

<a id="source-docsplanningmissing-workmd--board-01-execution-card"></a>
##### `BOARD-01` execution card

**Gate and scope:** `TIER-01` plus one selected Enterprise EDA adapter, one
legal exact board/revision/part/constraints fixture, and approved physical
exclusions. This ticket owns `ENT-BOARD-01`.

**Implementation:**

1. Freeze board profile identity and requirement catalog, then add board
   manifest/facts/constraint schemas, models, codecs, migrations, and
   provenance.
2. Implement non-executing constraint parsing and exact board/constraint/RTL/
   peripheral/clock/reset/device reconciliation.
3. Add board scenarios, digital component models, checks/coverage, deterministic
   harness/project/supplemental constraints, and user-file ownership rules.
4. Integrate entitlement-gated vendor execution, exact result/coverage/status,
   stale evidence, signed qualification, and historical downgrade behavior.
5. Publish one board acceptance/profile and leave all other boards/revisions/
   parts/tools and physical behavior unsupported.

**Validation:**

1. Complete every `ENT-BOARD-01` identity, device, pin/net, I/O, clock/reset,
   peripheral, constraint-security, generation, vendor, closure, and product-
   boundary case.
2. Run schema/migration/fuzz/path/security tests and assert unsupported Tcl or
   customer scripting is never executed by core.
3. Run deterministic generation/user-file immutability, atomic interruption/
   concurrency, stale-provenance, entitlement capability-combination, and
   downgrade tests.
4. Run good design and one intended mutant per board requirement/rule in the
   exact vendor tool/profile from installed Enterprise artifacts.
5. Close board checks/coverage/feature ledger/strict status and retain signed
   vendor evidence, exact board fixture hashes, and physical exclusion table.

**Stop condition:** without legal real-tool board evidence, retain contract-
verified state only and do not promote the board.

<a id="source-docsplanningmissing-workmd--semantic-and-language-cards"></a>
#### Semantic and language cards

<a id="source-docsplanningmissing-workmd--sem-01-execution-card"></a>
##### `SEM-01` execution card

**Gate and scope:** select exactly one unsupported SystemVerilog semantic family
and exact operator/type/range/profile bounds. Do not combine unrelated families.

**Implementation:**

1. Add normative semantic fact shape, authority, source locator, supported/
   unknown/contradicted states, and unsupported neighboring constructs.
2. Extend Verilator and/or qualified Slang extraction plus frontend
   reconciliation for the selected family; preserve raw authoritative evidence.
3. Version RTL facts/schema/models/codecs/migrations and canonical identity.
4. Extend claim validation/planning gates so executable targets require complete
   agreed facts and unsupported/ambiguous semantics remain non-executable.
5. Extend only affected scenarios/renderers/decoders/checks/coverage and update
   compatibility/capability/acceptance matrices.

**Validation:**

1. Add positive, malformed, ambiguous, unsupported-neighbor, inactive-generate,
   minimum/maximum/outside-width, signedness/range/direction, and source-locator
   fixtures for the selected family.
2. Run Verilator/Slang real frontend fixtures and differential comparison;
   classify legitimate differences and reject unexplained disagreement.
3. Test every readable fact version, newer rejection, stale facts, repeated
   canonical bytes/IDs, and target-specific claim gates.
4. Run affected generator/tool good DUT plus one semantic mutant per rule;
   verify the intended check kills each mutant.
5. Run `tests.domain.test_semantic_ir`, RTL semantic/crosscheck tests, affected
   integration pipelines, branch/full regression, feature ledger, and updated
   acceptance.

**Stop condition:** any unresolved sizing/type/operator/frontend disagreement
keeps the selected target unsupported.

<a id="source-docsplanningmissing-workmd--sem-02-execution-card"></a>
##### `SEM-02` execution card

**Gate and scope:** requires a governed external mixed-language elaborator and
binding-manifest producer. Select one SystemVerilog/VHDL boundary, libraries,
top, target, and tool versions.

**Implementation:**

1. Extend the cross-language binding contract with exact unit/library/
   architecture/configuration/instance/specialization/source identities and
   scalar/vector/type/range/direction adaptations.
2. Implement import from one authoritative external elaborator; never infer
   compile order or bindings from filenames/names alone.
3. Validate one-to-one resolution, compile order, case/library rules,
   generic/parameter values, black boxes, clocks/resets, and conversion
   compatibility.
4. Persist/migrate binding facts and gate planning/generation on complete
   non-contradicted manifests.
5. Add target compile/elaboration/run integration and exact cross-language
   result/source provenance.

**Validation:**

1. Test missing/duplicate/ambiguous units, libraries, architectures,
   configurations, instances, tops, case collisions, compile cycles/order, and
   unresolved black boxes.
2. Test generic/parameter, scalar/vector, ascending/descending range, signed/
   unsigned/type/direction conversions and illegal/lossy mismatches.
3. Test cross-language clock/reset ownership, specialization identity, stale
   manifests, wrong source/tool version, path escape, schema migration, and
   deterministic ordering.
4. Run actual mixed-language analysis/elaboration and one observable good/bad
   fixture on the selected target; exact source/check identities must survive.
5. Run cross-language binding, VHDL/semantic/frontend, affected generator/run,
   strict status, branch/full regression, and feature-ledger validation.

**Stop condition:** without authoritative external elaboration evidence, keep
the mixed-language target unsupported; internal guesses cannot close it.

<a id="source-docsplanningmissing-workmd--sem-03-execution-card"></a>
##### `SEM-03` execution card

**Gate and scope:** select one frontend patch/version expansion or one legal
external design. Record exact tool binaries/licenses and source commit/license.

**Implementation:**

1. Define matrix cell identity, expected frontend facts/diagnostics,
   compatibility policy, resource budgets, and qualification evidence.
2. Add pinned tool acquisition/probe and legal immutable external-design
   fixture/reference.
3. Run normalization/crosscheck on representative deep/wide/package/interface/
   generate/property/memory semantics and classify differences.
4. Store version/design/source/tool/workflow/result/resource hashes in typed
   evidence and integrate strict unsupported-version policy.
5. Update compatibility matrix, tool policy, CI cell, acceptance, and evidence
   freshness/impact mapping.

**Validation:**

1. Test minimum/maximum supported and just-outside patch versions, malformed/
   localized version output, wrong executable, and version change between probe
   and run.
2. Run selected design on both authoritative frontends, compare schema facts,
   diagnostics, source locations, inactive generate, and specialization
   identity.
3. Test known tool-version differences, stale source/tool/workflow/evidence,
   license failure, timeout, memory/runtime budget, and deterministic rerun.
4. Run unqualified versions in strict mode and require fail-closed status; no
   nearby patch inherits qualification.
5. Validate external-design evidence, full related frontend regressions,
   `QUAL-01` impact/freshness, and publish one exact matrix-cell record.

**Stop condition:** unavailable license/source or unexplained normalized
difference leaves the matrix cell unqualified.

<a id="source-docsplanningmissing-workmd--vhdl-01-execution-card"></a>
##### `VHDL-01` execution card

**Gate and scope:** select one additional native VHDL profile and exact GHDL/
standard version. Mixed-language behavior requires `SEM-02`.

**Implementation:**

1. Define entity/architecture/configuration/libraries/generics/types/ranges/
   clocks/resets and scenario/check/coverage contract for the selected profile.
2. Extend VHDL normalization with source evidence and fail-closed handling for
   unconstrained/unresolved/ambiguous constructs.
3. Extend typed scenario, native VHDL renderer, compile-order/project manifest,
   GHDL analysis/elaboration/run, result decoder, and provenance.
4. Reconcile exact traces/checks/coverage/status and preserve VHDL language/
   architecture/source identity through planning and results.
5. Add schema migration, configuration/operator docs, capability and acceptance
   for only the selected profile.

**Validation:**

1. Test case-insensitive identifiers, library/architecture/configuration
   selection, compile order, generics, records/subtypes/arrays, ascending/
   descending ranges, resolved/multiple drivers, delta cycles, and standard
   differences.
2. Test malformed/ambiguous/unconstrained input, wrong architecture/library,
   missing GHDL/wrong version, compile/elaboration/run failure, timeout, empty/
   unknown result, and stale source.
3. Generate twice, compare bytes/IDs, and run syntax/elaboration from installed
   package with paths containing spaces and isolated work libraries.
4. Run good DUT and one mutant per new rule under exact GHDL; reconcile
   canonical traces/coverage/strict status.
5. Run RTL VHDL tests, `tests.integration.test_vhdl_pipeline`, qualification,
   branch/full regression, feature ledger, and acceptance.

**Stop condition:** source-only parsing without GHDL-authoritative
analysis/elaboration cannot qualify a native VHDL execution claim.

<a id="source-docsplanningmissing-workmd--formal-cdc-reset-and-memory-cards"></a>
#### Formal, CDC, reset, and memory cards

<a id="source-docsplanningmissing-workmd--form-01-execution-card"></a>
##### `FORM-01` execution card

**Gate and scope:** product/technical owner selects one extension only:
assume-guarantee, induction invariant, bounded liveness fairness, or supported
temporal operator subset, with exact engine/depth bounds.

**Implementation:**

1. Add typed formal policy/scenario fields, syntax/semantic bounds, assumptions,
   properties, invariants/covers, task/engine capability, and unsupported
   neighbors.
2. Extend validation for clocks/resets/signals, assumption consistency,
   trigger/response/completion reachability, and engine support.
3. Generate deterministic harness/properties/SBY tasks and stable check/task/
   coverage/source traces.
4. Extend execution/decoder/counterexample/formal coverage and strict handling
   for pass/fail/unknown/timeout/vacuity/unsupported engine.
5. Add migration, capability/acceptance/operator/counterexample triage docs.

**Validation:**

1. Test syntax/model/bound/clock/reset/signal/engine boundaries and
   missing/contradictory/over-constraining assumptions.
2. Exercise prove pass/fail/unknown, cover reached/unreached, base/step
   disagreement, timeout/signal/solver error, malformed/duplicate/missing tasks,
   and process/result contradictions.
3. Verify assumption witness, trigger, response, completion, and any fairness/
   invariant non-vacuity independently.
4. Run good DUT and one intended mutant per new property/assumption/checker
   rule on each claimed engine; retain exact counterexamples.
5. Run formal unit/integration, branch/full regression, deterministic bytes,
   feature ledger, strict status, and real-tool evidence.

**Stop condition:** an unsupported engine/operator or unreachable mandatory
cover remains unsupported/non-closing; never weaken the property.

<a id="source-docsplanningmissing-workmd--cdc-01-execution-card"></a>
##### `CDC-01` execution card

**Gate and scope:** select exactly one advanced CDC profile, source/destination
domains/resets, event-rate/data-stability assumptions, topology, bounds, and
structural versus behavioral evidence.

**Implementation:**

1. Add versioned CDC policy/facts for topology/stages/domains/resets/rate/
   payload/observability and exact evidence levels.
2. Extend frontend/structural classification without name-only safety
   inference; reconcile explicit external-input timing and domain ownership.
3. Add typed simulation/formal scenarios, stimulus, scoreboards, safety/
   liveness/non-vacuity properties, check/coverage identities, and target gates.
4. Generate/run/decode the selected profile and preserve path/stage/source/
   counterexample provenance.
5. Add migration, reports, strict closure, capability and acceptance while
   preserving `BUG-CDC-01`.

**Validation:**

1. Test clock ratio/phase, source event rate, pulse width, data stability,
   reset assertion/release ordering, stage count/order, branching/
   reconvergence, observability, and unknown domains.
2. Add good topology, structural negative, ambiguous/partial topology,
   unsupported-neighbor, and one simulation/formal mutant per safety/liveness
   rule.
3. Run actual asynchronous clocks and bounded formal prove/cover; verify
   non-vacuity and exact path/check/coverage identities.
4. Run every prior CDC/async FIFO/reset/memory regression including
   `BUG-CDC-01`; no safety downgrade or duplicate path.
5. Run CDC unit/integration, deterministic generation, branch/full regression,
   strict status, feature ledger, and exact tool evidence.

**Stop condition:** ambiguous or partially observed topology remains a closure
blocker even if behavioral tests happen to pass.

<a id="source-docsplanningmissing-workmd--rdc-01-execution-card"></a>
##### `RDC-01` execution card

**Gate and scope:** requires one licensed physical reset/power analysis tool,
legal fixture, exact netlist/constraints/libraries/corners/modes, and approved
evidence/signature policy. Logical RDC alone cannot qualify this ticket.

**Implementation:**

1. Define vendor-neutral physical reset/power evidence schema with rule/finding,
   hierarchy/source/domain, units/corner/mode, constraint/netlist/library,
   waiver, tool/version, and provenance.
2. Implement Enterprise-gated adapter/importer and exact hierarchy/domain
   reconciliation with logical reset/RDC facts.
3. Add evidence levels, stale/fresh/waiver policy, severity/status mapping, and
   separation between logical pass and physical result.
4. Add report/closure/release gates and independent signature/trust validation.
5. Publish one exact tool/profile/corner/mode acceptance and leave other cells
   unsupported.

**Validation:**

1. Test valid/malformed/newer records, units/corners/modes, hierarchy aliases,
   hidden/duplicate/missing paths, recovery/removal boundaries, and power-good/
   isolation/retention ordering.
2. Test stale netlist/constraints/libraries/tool/profile, expired/orphan/
   conflicting waivers, unknown rules, partial reports, timeout/license failure,
   and path/secret handling.
3. Run logical pass plus injected physical violation and prove physical failure
   remains failed/non-closing; absence of findings alone is not a pass.
4. Execute the real selected tool/fixture and import independently signed exact
   findings under approved trust.
5. Run adapter/import/closure/strict/release tests, full regression, feature
   ledger, and retain exact external evidence.

**Stop condition:** without licensed signed physical evidence, stop at schema/
contract tests and do not promote physical RDC.

<a id="source-docsplanningmissing-workmd--mem-01-execution-card"></a>
##### `MEM-01` execution card

**Gate and scope:** select one unsupported memory behavior only: initialization
file, async behavior, additional port, retention, macro timing, or repair.
Declare simulation/formal/physical evidence boundary.

**Implementation:**

1. Add policy/fact fields for selected behavior, exact memory/port/address/data/
   mask/clock/reset/power/ECC mappings, bounds, collision/arbitration, and
   authority.
2. Extend frontend/imported evidence and validation; reject ambiguous arrays,
   symbolic dimensions, unsupported port/timing combinations, or inferred
   policy.
3. Add typed scenario/reference model/properties/non-vacuity/checks/coverage and
   target-specific support.
4. Extend deterministic generation/execution/decoder/closure and physical
   delegation where required.
5. Add migration, capability/acceptance/operator docs and preserve parity/
   SECDED plus `BUG-CDC-01` regressions.

**Validation:**

1. Test minimum/maximum/outside depth/width/ports, addresses/byte lanes,
   same/different-address collisions, arbitration races/wrap, reset/init, clock/
   async boundaries, and selected behavior states.
2. Test malformed/missing/contradicted policy, unsupported macro/timing/power
   semantics, stale source/policy/generated/tool evidence, and legacy migration.
3. Run good DUT and one intended mutant per mapping/behavior/collision/
   arbitration/ECC/retention/repair rule on every claimed target.
4. Verify exact coverage/non-vacuity and process/result/counterexample behavior;
   physical-only claims require physical adapter evidence.
5. Run memory formal/unit/integration, parity/SECDED/CDC regressions,
   deterministic/full regression, feature ledger, and acceptance.

**Stop condition:** do not combine another memory behavior to make the selected
one pass; unsupported physical timing remains delegated.

<a id="source-docsplanningmissing-workmd--protocol-and-peripheral-cards"></a>
#### Protocol and peripheral cards

<a id="source-docsplanningmissing-workmd--proto-01-execution-card"></a>
##### `PROTO-01` execution card

**Gate and scope:** blocked until `DOC-00` establishes current profile states.
Then select one broad protocol, endpoint role, feature/bounds, and target only.

**Implementation:**

1. Freeze versioned transaction/profile contract: channels, role, ordering,
   bursts/outstanding, errors/retries, optional signals, reset/completion/
   timeout, scoreboard key, checks/coverage/formal obligations.
2. Extend exact recognition/binding and reject incomplete/ambiguous/multiple
   instances unless explicitly mapped.
3. Add typed driver/monitor/reference model/scenario and target-specific
   renderer/decoder/coverage/non-vacuity for the selected cell.
4. Implement exact execution/result/closure and provenance across all expected
   traces/transactions/checks.
5. Add good DUT/mutants, migration, capability/acceptance/operator docs; leave
   every unselected role/target/bound conservative.

**Validation:**

1. Test legal/illegal handshake order, min/max/outside burst/size/outstanding,
   stalls/backpressure, response/error/retry, IDs/order/wrap, sideband
   stability, reset mid-transaction, timeout/recovery, and multiple instances.
2. Test incomplete/ambiguous signature, optional-signal combinations, wrong
   role, scoreboard-key collisions, stale profile/plan/generated/results, and
   unsupported neighboring feature.
3. Run good DUT and one intended mutant per protocol rule on the exact target/
   real tool; verify transaction/check/coverage/formal non-vacuity identity.
4. Run production profile/recognition/transaction/generation/CLI/native/formal/
   coverage/strict tests and regress existing bounded protocols.
5. Validate feature ledger and docs against `DOC-00`; no other matrix cell
   changes state.

**Stop condition:** generated collateral without a decoder, good-DUT/mutation
matrix, and real target execution remains scaffold/partial.

<a id="source-docsplanningmissing-workmd--proto-02-execution-card"></a>
##### `PROTO-02` execution card

**Gate and scope:** select one feature extension to APB4, AXI4-Lite, AHB-Lite,
or paired ready/valid; preserve all previous bounded behavior and targets.

**Implementation:**

1. Version the existing profile with one optional/extended semantic, bounds,
   migration default, checks/coverage, and feature-disabled behavior.
2. Extend recognition/validation and typed transaction/scenario/reference model
   without changing old defaults.
3. Extend each newly claimed renderer/decoder independently and retain old
   trace/check identities where semantics are unchanged.
4. Add exact generation/execution/closure/provenance for the extension and
   reject unsupported combinations.
5. Update capability/acceptance/config/operator docs and profile migration.

**Validation:**

1. Run the complete prior good-DUT/mutant matrices byte/result/coverage-
   equivalently with the feature disabled.
2. Test new minimum/maximum/outside bounds, optional-signal combinations,
   simultaneous channels, ordering/key collisions, timeout/reset/recovery, and
   malformed/ambiguous binding.
3. Run feature-enabled good DUT plus one intended mutant per new rule on every
   claimed target; target cells qualify independently.
4. Test old/new schema migration, stale artifacts/results, deterministic bytes,
   and feature toggling with no cache/identity collision.
5. Run protocol unit/generation/integration/coverage/strict/full regression,
   feature ledger, and updated acceptance.

**Stop condition:** regression in any old bounded profile or target blocks the
extension even when new cases pass.

<a id="source-docsplanningmissing-workmd--periph-01-execution-card"></a>
##### `PERIPH-01` execution card

**Gate and scope:** select one UART, SPI, I2C, GPIO, timer, watchdog, PWM, IRQ,
or related digital feature. Electrical/analog behavior requires `PHYS-01`.

**Implementation:**

1. Extend one peripheral policy/profile with exact signals/directions/widths,
   clock/reset, timing/divider/range, behavior, errors, checks, and coverage.
2. Extend recognition/validation and explicit mapping; reject partial or
   ambiguous interfaces.
3. Extend typed BFM/reference/scenario and formal safety/non-vacuity only for
   the feature.
4. Extend generation/execution/decoder/closure and preserve existing profile
   defaults/IDs.
5. Add feature mutants, migration, capability/acceptance/config docs and
   physical exclusions.

**Validation:**

1. Exercise feature-specific matrix: UART frame/divisor/errors; SPI modes/CS/
   order/contention; I2C START/address/ACK/stretch/arbitration/stuck bus; GPIO/
   timer/IRQ masks/clear/wrap/priority/backpressure as applicable.
2. Test min/max/outside timing/width, reset mid-operation, timeout/recovery,
   malformed mappings, optional combinations, and electrical-only exclusions.
3. Run old bounded good-DUT/mutant matrix unchanged and new good DUT plus one
   intended mutant per rule in cocotb/formal claimed targets.
4. Verify exact traces/scoreboard/bins/crosses/non-vacuity, deterministic bytes,
   stale provenance, and strict closure.
5. Run peripheral formal/qualification/full regression, feature ledger, and
   acceptance; retain exact tool/result evidence.

**Stop condition:** analog voltage/timing/contention evidence cannot be inferred
from a digital BFM pass.

<a id="source-docsplanningmissing-workmd--uvm-adapter-and-coverage-cards"></a>
#### UVM, adapter, and coverage cards

<a id="source-docsplanningmissing-workmd--uvm-01-execution-card"></a>
##### `UVM-01` execution card

**Gate and scope:** select one richer UVM profile and one licensed simulator/
version. Contract generation may begin; support promotion requires independently
signed real-tool evidence.

**Implementation:**

1. Define typed agents/roles/transactions/sequences/scoreboards/RAL/coverage,
   phase/objection/completion/non-vacuity, reset/error behavior, checks, and
   unsupported UVM features.
2. Extend scenario/model and deterministic UVM project rendering with stable
   component/transaction/check/coverage traces.
3. Add exact compile/library/order/top/test/run wrapper profile and entitlement-
   gated licensed execution.
4. Decode structured/transcript results, transaction/phase completion, UVM
   severity, coverage, artifacts, and process status into normalized closure.
5. Add qualification bundle/signature/freshness, capability/acceptance/operator
   docs, and migration.

**Validation:**

1. Test zero/nonzero transactions, phase/objection completion, active/passive
   agents, factory overrides, sequence deadlock, reset interruption, analysis
   fanout/copy/clone, scoreboard ordering, and RAL mirror/predict races.
2. Test compile/library/dialect/top/test errors, timeout/license failure,
   warnings/errors/fatals, partial/malformed transcript/result, unknown traces,
   and process/result contradiction.
3. Generate twice and compile/run good DUT plus intended mutants in the exact
   licensed simulator; verify named test, non-vacuous transactions, scoreboard,
   coverage, and zero prohibited severities.
4. Import independently signed evidence and reject stale/tampered/wrong-tool/
   self-signed/untrusted records.
5. Run UVM generation/project/enterprise qualification, branch/full regression,
   feature ledger, strict status, and acceptance.

**Stop condition:** generated compile-looking UVM or mocked transcript remains
non-closing without licensed execution.

<a id="source-docsplanningmissing-workmd--tool-01-execution-card"></a>
##### `TOOL-01` execution card

**Gate and scope:** select one commercial simulator or formal adapter/profile/
version, legal fixture, trusted execution host, and required Enterprise
capability.

**Implementation:**

1. Define adapter API/profile, supported tasks/languages, executable/version/
   license discovery, wrapper/env/path/resource policy, native result schema,
   and normalized identities.
2. Gate before adapter import/probe; construct argv without shell and execute
   through bounded process/sandbox/run-local paths.
3. Parse structured results/counterexamples/artifacts, preserve unknowns, and
   reconcile exact expected checks plus all provenance/process state.
4. Add license-aware scheduling/cancellation, qualification bundle/import,
   independent signature/trust/freshness, and strict status.
5. Add operator/security/support/capability/acceptance for one exact adapter
   cell.

**Validation:**

1. Test absent/wrong/changed executable/version, localized output, license
   absent/queue/denied/expired/server outage, and secret redaction.
2. Test wrapper/path/symlink/environment/shell injection, timeout/signal/
   descendant cleanup, partial database/log limits, and concurrent token
   scheduling/cancellation.
3. Test structured good/fail/unknown/skipped/duplicate/missing checks, zero/
   nonzero contradictions, counterexample escape, stale provenance, and artifact
   mismatch.
4. Run good DUT and intended mutants in the actual selected tool/version and
   import independently signed evidence.
5. Run enterprise adapter/qualification/security/branch/full regression,
   feature ledger, strict status, and exact acceptance.

**Stop condition:** without real signed evidence, remain contract or surrogate
verified.

<a id="source-docsplanningmissing-workmd--cov-01-execution-card"></a>
##### `COV-01` execution card

**Gate and scope:** select one vendor coverage export/database/API or formal
coverage API and exact version/merge semantics.

**Implementation:**

1. Define importer API/profile and native-to-canonical mapping for scope/point/
   bin/cross identity, hits/goals/status, illegal/ignore/excluded state, source,
   requirements/checks/behavior, tool/run/specialization provenance.
2. Implement bounded parser/adapter and strict schema/version/path/size/
   duplicate validation.
3. Normalize into coverage v3 without assigning final pass inside the plugin.
4. Integrate stable merge, disposition/waiver/unreachable policy, plan/result/
   generated freshness, and strict closure.
5. Add migration/operator/capability/acceptance and one real native evidence
   fixture.

**Validation:**

1. Test hit/miss/goal/counter overflow, bins/crosses, illegal/ignore/excluded/
   waived/unreachable, zero denominator, empty scope, duplicate import, and
   cumulative versus per-run merge.
2. Test malformed/truncated/oversized/newer data, path/source movement,
   hierarchy aliases, parameter specialization, stale tool/database/run, and
   conflicting dispositions/expired waivers.
3. Differentially compare known native fixture totals/points with canonical
   output and deterministic repeat import/merge.
4. Run strict closure with missing/unknown/orphan/partial data and prove none
   closes; run a complete real-tool fixture that does.
5. Run execution coverage/UCIS/status/branch/full regression, feature ledger,
   and acceptance with exact tool evidence.

**Stop condition:** aggregate totals without stable canonical point identity
cannot close coverage.

<a id="source-docsplanningmissing-workmd--cov-02-execution-card"></a>
##### `COV-02` execution card

**Gate and scope:** select one typed protocol/requirement behavior family and
one or more explicitly claimed renderer targets.

**Implementation:**

1. Add typed coverage intent with stable point/bin/cross IDs, sampling event,
   goals, legal/illegal/ignore states, requirement/check/behavior links, and
   bounds.
2. Validate overlaps, duplicate/unreachable/explosive crosses, reset sampling,
   target capability, and zero-denominator behavior during planning.
3. Render target-native coverage constructs/collection and map measured native
   output back to canonical IDs.
4. Integrate expected-point reconciliation, closure, deterministic provenance,
   and feature-disabled migration.
5. Add capability/acceptance/operator docs and known hit/miss/mutant fixtures.

**Validation:**

1. Test boundary/default/transition bins, sampling timing, reset behavior,
   cross Cartesian boundaries, illegal/ignore overlap, duplicate IDs, and
   unreachable proof.
2. Compile/run generated coverage on every claimed target with a known sequence
   that hits all required points and one that intentionally misses each point.
3. Add a semantic mutant that avoids each mandatory bin/cross and verify
   closure fails for the intended identity.
4. Test zero denominator, all excluded, feature disabled, stale plan/run/
   generated mapping, deterministic bytes/IDs, and migration.
5. Run scenario/generation/coverage/strict/branch/full regression, feature
   ledger, and target-specific acceptance.

**Stop condition:** a target that renders coverage but cannot return stable
measured IDs remains partial.

<a id="source-docsplanningmissing-workmd--documentation-scale-and-platform-cards"></a>
#### Documentation, scale, and platform cards

<a id="source-docsplanningmissing-workmd--doc-01-execution-card"></a>
##### `DOC-01` execution card

**Gate and scope:** select one approved OCR engine or one local embedding/vector
implementation. Network use and confidentiality policy must be explicit.

**Implementation:**

1. Define adapter/version, MIME/extensions, size/page/text/depth/time limits,
   local/network/confidentiality/export/retention policy, and source locator/
   confidence contract.
2. Execute OCR/retrieval in an isolated bounded work area and produce
   deterministic sidecars/chunks/indexes with original source/page/region/tool/
   version hashes.
3. Normalize through indexing/retrieval adapters, treat all text as untrusted,
   and key caches on source/extractor/embedding/config identity.
4. Add invalidation/rebuild, permission/purge/audit/redaction/offline behavior,
   and planning evidence boundaries.
5. Add operator/security/privacy/capability/acceptance docs.

**Validation:**

1. Test empty/corrupt/encrypted/mixed scanned/text/rotated/skewed/multilingual
   pages, tables/diagrams/order, duplicate documents/pages, encoding and low-
   confidence register/address characters.
2. Test oversized/bomb/deep inputs, timeout/cancellation, permission denied,
   path/symlink escape, source replacement, cache/index corruption, embedding
   version/dimension change, and deterministic rebuild.
3. Test PII/secret redaction, prompt-injection-like content, offline/no-network,
   redirect/destination policy where applicable, and purge/retention.
4. Verify exact source locators/regions/confidence and stable chunk/result IDs
   on a known fixture; low confidence remains ambiguous evidence.
5. Run documentation and built-in adapter tests, branch/full regression,
   feature ledger, and acceptance with exact engine/version.

**Stop condition:** OCR/retrieved text never becomes authoritative executable
intent without normal evidence validation.

<a id="source-docsplanningmissing-workmd--scale-01-execution-card"></a>
##### `SCALE-01` execution card

**Gate and scope:** `SCALE-02` must first establish valid candidate/baseline
measurement. Select one broader platform, corpus dimension, cache mode, or
scheduler capability.

**Implementation:**

1. Extend performance v3 profile with selected corpus/workload/resource/
   concurrency/cache/license budgets and functional result contract.
2. Extend real installed-wheel benchmark stage/fixture and immutable baseline
   for the selected cell.
3. Add bounded scheduler admission for CPU/memory/process/formal/license
   resources, deterministic task/result order, cancellation, and atomic
   publication.
4. Add content-addressed cache locking/invalidation/stampede control and
   interrupted/recovery state.
5. Add CI runner/impact/freshness, operator tuning, capability/acceptance and
   evidence retention.

**Validation:**

1. Test cold/warm, one/many/deep/wide modules, huge docs, parameter sweeps,
   mixed fast/slow tasks, min/at/over every resource/license limit.
2. Test starvation/fairness/deadlock, cancellation at queue/run/publish,
   worker crash, process/file descriptor exhaustion, partial aggregate, cache
   stampede/corruption, and concurrent same-artifact publication.
3. Verify deterministic outputs/order/cache identity and no oversubscription or
   leaked tasks/processes under repeated/concurrent runs.
4. Compare installed candidate against independent baseline with controlled
   runner/noise and intentional runtime/memory regressions.
5. Run benchmark/performance/scheduler/sandbox/full regression, `QUAL-01`
   validation, feature ledger, and publish one matrix-cell record.

**Stop condition:** noisy/incomparable runner data or same-candidate
self-comparison cannot promote the selected cell.

<a id="source-docsplanningmissing-workmd--plat-01-execution-card"></a>
##### `PLAT-01` execution card

**Gate and scope:** select one exact OS/distribution/version/kernel/
architecture/Python/filesystem/container/runtime/tool tuple. Documentation-only
classification may begin; support requires real smoke/tool evidence.

**Implementation:**

1. Define platform profile, installation/package/system dependencies, support
   level, required/optional tools, filesystem/process/container behavior,
   resource limits, and exclusions.
2. Add CI/runner image and pinned dependency/tool acquisition/probes.
3. Add installed-wheel init/analyze/plan/generate/run/coverage/status/support-
   bundle smoke and byte/result comparison policy.
4. Add path/process/signal/permissions/sandbox/upgrade/rollback handling for the
   selected tuple.
5. Update support matrix, install/operator/troubleshooting, qualification and
   evidence freshness.

**Validation:**

1. Test case/permissions/symlink/junction/path length, drive/UNC where relevant,
   executable suffix, line endings, locale/timezone, signal/process group,
   container UID/rootless/network/read-only mounts, and missing tools.
2. Install wheel on every Python version claimed for the tuple and run public
   smoke plus required real EDA paths.
3. Compare generated bytes and normalized facts/results with reference
   platforms; classify legitimate differences explicitly.
4. Test clean install, upgrade, downgrade, rollback, cache/state migration,
   support bundle/redaction, and unsupported/best-effort diagnostics.
5. Run platform CI, packaging/full regression, performance where claimed,
   feature ledger, and retain exact runner/image/kernel/tool evidence.

**Stop condition:** documentation or container build alone cannot promote a
platform without real installed-artifact and required-tool results.

<a id="source-docsplanningmissing-workmd--decision-gated-cards"></a>
#### Decision-gated cards

<a id="source-docsplanningmissing-workmd--ai-01-decision-and-execution-card"></a>
##### `AI-01` decision and execution card

**Gate and scope:** no implementation of model-authored executable artifacts
until product/security owners approve a versioned decision package. Current
evidence-bounded proposals remain the fallback and authority boundary.

**Decision steps:**

1. Enumerate candidate artifact classes and explicitly prohibit everything not
   selected.
2. Define model/provider/data destination, source/license/secret handling,
   human reviewer/approval identity, sandbox, allowed dependencies/commands,
   provenance, reproducibility, retention, rollback, and liability/failure
   ownership.
3. Define deterministic validators, compilation/tool/mutation/coverage/
   non-vacuity requirements and when model output may become executable.
4. Threat-model prompt/source/doc injection, exfiltration, unsafe commands,
   license contamination, nondeterminism, cache drift, cost/resource failure,
   and approval bypass.
5. Approve/reject in ADR/policy with exact scope and acceptance matrix.

**Post-approval implementation:**

1. Add opt-in capability/policy/schema and immutable model/prompt/context/
   approval provenance; default remains disabled.
2. Generate into isolated staging only, parse through closed contracts, reject
   unsafe files/dependencies/commands, and require human approval before normal
   artifact publication.
3. Execute through sandbox/resource controls and all normal generation,
   integrity, plan/revision, run, coverage, mutation, strict-status, and release
   gates.

**Validation:**

1. Test every threat case plus malformed/nondeterministic output, provider/model
   drift, cache separation, reviewer denial/revocation, rollback, and zero
   network/side effects when disabled.
2. Run compile/good-DUT/mutation/coverage closure on every approved artifact
   class/target and retain exact model/provider/prompt/context/approval/tool
   evidence.
3. Run capability/approval bypass, sandbox/resource/path/secret/license,
   provenance/cache, branch/full regression, feature ledger, and release-policy
   tests for every approved artifact class.

**Stop condition:** absent approval keeps this ticket `no`; agents may improve
decision documentation/tests but must not add executable model authority.

<a id="source-docsplanningmissing-workmd--ai-02-decision-and-execution-card"></a>
##### `AI-02` decision and execution card

**Gate and scope:** no cross-provider routing/fallback until product/security
owners approve provider/model/destination/data/cost policy.

**Decision steps:**

1. Enumerate providers/models/regions/endpoints and allowed purpose/data class
   for each.
2. Define routing order, retry/fallback triggers, no-fallback errors, residency/
   confidentiality boundaries, credentials, quotas/cost, disagreement policy,
   cache separation, audit/redaction, and operator override.
3. Define whether provider changes require human approval and how model/version
   drift invalidates cache/evidence.
4. Threat-model outage, rate/auth/content-policy failures, malicious endpoint,
   cross-provider disclosure, silent downgrade, cost exhaustion, inconsistent
   answers, and partial audit.
5. Approve/reject in ADR/policy with exact validation matrix.

**Post-approval implementation:**

1. Add closed routing policy/schema and deterministic resolver; every result
   records actual provider/model/destination/purpose/attempt/fallback.
2. Resolve credentials by provider identity, isolate cache keys and audit, and
   enforce stage/network/data/cost policy before each request.
3. Keep same closed response validation and deterministic non-AI fallback;
   never merge or promote disagreement automatically.

**Validation:**

1. Test every route/retry/fallback/no-fallback/outage/rate/auth/cost/
   disagreement/cache/audit/redaction case with fake providers and zero secret
   leakage.
2. Run opt-in real-provider smoke per approved cell, full AI branch/regression,
   policy feature ledger, and retain content-free evidence.
3. Test disabled/unapproved routes, provider/model/destination drift,
   credential isolation, budget boundaries, cache poisoning/cross-policy reuse,
   and deterministic fallback under concurrent requests.

**Stop condition:** any silent provider/model/destination change or cross-policy
cache reuse keeps routing disabled.

<a id="source-docsplanningmissing-workmd--phys-01-decision-and-execution-card"></a>
##### `PHYS-01` decision and execution card

**Gate and scope:** no physical-sign-off claim until product owners define
delegation and licensed evidence for timing, CDC/RDC, power, memory macro, board,
or related physical domains.

**Decision steps:**

1. Select exact physical claim families and define what remains logical-only,
   delegated, or unsupported.
2. Define tools/versions, technologies/libraries/corners/modes/netlist/
   constraints, evidence levels, signer/trust, freshness, waivers, severity,
   release gates, customer confidentiality, and responsibility.
3. Define normalized finding/path/unit/hierarchy/source identity and
   reconciliation with logical checks without allowing logical pass to override
   physical failure.
4. Threat-model stale/mismatched netlist/constraints/libraries, wrong units/
   corners/modes, black boxes, false/multicycle paths, waiver abuse, partial
   reports, tool disagreement, and absence-of-findings.
5. Approve/reject in ADR/policy with exact adapter/fixture/acceptance matrix.

**Post-approval implementation:**

1. Add closed physical evidence/policy schemas, Enterprise capability gates,
   adapter/importer, signature/freshness/waiver validation, and separate
   physical closure state.
2. Reconcile exact design/hierarchy/source/domain/constraint/tool/technology/
   mode/corner identities and preserve unknown/partial/conflicting findings.
3. Integrate reports/status/release gating without translating no reported
   violation into a pass.

**Validation:**

1. Test all identity/unit/corner/mode/library/netlist/constraint/black-box/
   waiver/stale/partial/tool-disagreement cases plus logical-pass/physical-fail.
2. Execute approved licensed tools on legal good/violation fixtures, import
   independently signed evidence, run feature ledger/full regression, and
   publish exact supported cells/exclusions.
3. Test capability denial, license/tool failure, signature/trust/freshness,
   report truncation/unknown findings, waiver expiry/conflict, and release
   blocking for every selected physical claim family.

**Stop condition:** absent approved licensed evidence keeps physical capability
unsupported and blocks dependent physical promotion while preserving digital/
logical results at their bounded evidence level.

<a id="source-docsplanningmissing-workmd--tooling-needed-for-the-residual-work"></a>
### Tooling Needed for the Residual Work

| Tool or capability | Backlog items | Required use and qualification evidence |
| --- | --- | --- |
| Existing qualified Verilator/Icarus/SBY/Yosys/Z3 toolchain | closed `BUG-CDC-01` regression; future `FORM-01`, `CDC-01`, `MEM-01` | Preserve the now-passing SECDED good-DUT/five-mutant matrix and rerun it on CDC/memory/tool changes. No new license is required for that regression. |
| Last released wheel/tag and normalized compatibility manifest | closed `QUALITY-01`; `RELEASE-01` | Retain reviewed public-surface history and compare the exact candidate/tag/package/artifacts before publication. A digest-only baseline cannot explain an unreviewed change. |
| Closed qualification schemas, contextual verifier, evidence registry, and immutable CI artifact store | `QUAL-01`, `RELEASE-01` | Validate every evidence type against exact candidate and impact identities; retain bundles by immutable workflow artifact ID/digest and distinguish historical from reusable/current evidence. |
| Protected tag rules, release environments, test package index, OIDC/trusted publisher, and signature verifier | `RELEASE-01` | Exercise exact-SHA validation, build-once handoff, contextual provenance, approval, signing, idempotent publication, and exact-digest reinstall without exposing credentials. |
| Immutable accepted performance baseline store, representative large project/doc fixtures, and calibrated Ubuntu/WSL runners | `SCALE-02`, `QUAL-01` | Run the installed candidate wheel through real product stages; retain raw repetitions, process-tree metrics, functional results, runner identity, comparison, and signed baseline reference. |
| Deterministic fake Headroom HTTP and MCP stdio servers plus process/descriptor census helpers | `AI-03` | Exercise protocol, redirect, timeout, cancellation, environment, provenance, and cleanup paths without discovering host services; supplement with explicitly versioned opt-in compatibility runs. |
| Versioned capability/evidence ledger | `DOC-00`, `DOC-02` | Provide one machine-readable profile/role/target/bound/state/evidence authority and drive semantic repository-document checks. |
| Versioned document/progress catalog and parser-based documentation checker | `DOC-03` | Inventory every maintained Markdown file, classify the append-only progress ledger, enforce class/status/date/authority metadata, validate governed commands/transitions, generate indexes, and reject semantic/backlog drift. |
| Product entitlement signer/trust policy, private package index, and wheel matrix | `TIER-01` | Issue deterministic non-production test grants, verify offline signatures/time/capabilities, publish separate Free/Enterprise artifacts, and prove package/entry-point contents plus upgrade/downgrade behavior. Production issuer keys remain outside the repository. |
| Legal reference board, exact constraints, vendor FPGA installation, and customer pilot | `BOARD-01` | Qualify one board/revision/part with board-manifest and constraint provenance, XSim board-level execution, board-specific mutants, and independently governed vendor evidence. Physical and customer-confidential artifacts remain outside public fixtures. |
| Additional Slang releases, Surelog/UHDM, or an equivalent elaborating frontend | `SEM-01`, `SEM-02`, `SEM-03` | Extend the qualified SystemVerilog matrix and, for mixed-language work, emit a governed binding manifest with source locations, diagnostics, architecture selection, and specialization identity. |
| Additional GHDL releases and a VHDL-capable simulator/frontend | `SEM-02`, `SEM-03`, `VHDL-01` | Widen VHDL compile/elaboration/simulation qualification beyond the current fixture path; retain exact entity, architecture, generic, package, and result-trace evidence. |
| SymbiYosys/Yosys/Z3 upgrades and/or a commercial formal engine | `FORM-01`, `CDC-01`, `MEM-01`, `TOOL-01` | Establish engine capability, proof/cover behavior, timeout handling, counterexample extraction, and per-check result normalization for every newly claimed formal feature. |
| Questa, VCS, Xcelium, Riviera-PRO, or another licensed simulator | `UVM-01`, `TOOL-01`, `COV-01` | Execute generated collateral against a pinned tool/license environment and provide signed, provenance-bound evidence with exact trace IDs and no UVM errors/fatals. |
| Commercial CDC/RDC, static timing, power-intent, or reset-tree analyzer | `CDC-01`, `RDC-01`, `PHYS-01` | Supply stable rule IDs, source/domain mappings, severity, constraints, waivers, tool version, and retained reports. A summary-only green status is insufficient. |
| Memory model, macro characterization, or technology library fixtures | `MEM-01`, `PHYS-01` | Define observable policy and timing/corner assumptions for the selected memory extension without claiming generic macro sign-off. |
| UCIS/vendor coverage APIs and formal-coverage APIs | `COV-01`, `COV-02` | Import or generate stable point/bin/cross identity, goals, exclusions, illegal/ignore state, and requirement/check mappings through the normal closure gates. |
| Approved local OCR engine | `DOC-01` | Produce source-addressed OCR sidecars under confidentiality and malformed-document controls; preserve original document identity and extraction tool version. |
| Approved local embedding/vector runtime | `DOC-01` | Build private, invalidatable indexes with content/provenance hashes and no uncontrolled external disclosure. |
| Protocol/peripheral good-DUT and mutant fixtures | `PROTO-01`, `PROTO-02`, `PERIPH-01`, `VHDL-01` | Provide legally usable positive and targeted-negative designs, deterministic simulator/formal configuration, and expected per-check outcomes for every promoted feature. |
| Profiling hosts, CI capacity, and representative repository fixtures | `SEM-03`, `SCALE-01`, `SCALE-02`, `PLAT-01` | Measure real product runtime, process-tree memory, I/O, cache behavior, concurrency, tool versions, repeatability, and candidate-versus-independent-baseline regression within published budgets across each supported platform. |

<a id="source-docsplanningmissing-workmd--recommended-order"></a>
### Recommended Order

1. `SCALE-02` and `QUAL-01` are closed for the Ubuntu-only current claim.
   Preserve the archived Ubuntu candidate bundle and existing WSL records as
   historical evidence.
2. Implement `RELEASE-01` against the `QUAL-01` bundle. Until exact-tag policy,
   exact-SHA mandatory validation, contextual provenance, and publication
   recovery are complete, no `v*` tag should be treated as safely publishable
   merely because the workflow can build/sign it.
3. Close `AI-03` before relying on context optimization in long-lived agents or
   CI. Make optimizer use explicit and hermetic, fix cleanup/framing/redirect
   boundaries, and require zero process/file-descriptor growth under repeated
   failures.
4. Close `DOC-00` and `DOC-02` from current evidence. Preserve the more
   conservative state for release claims where broad protocol, native,
   peripheral, or VHDL documents disagree. Complete `DOC-03` against the same
   ledger so `docs/roadmap.md` closure/regression transitions cannot leave this
   roadmap stale again.
5. Implement `TIER-01` after stable capability IDs exist. Preserve the
   account-free Free open-tool workflow, split Enterprise packaging, and gate
   every enterprise adapter/qualification/board entry point before side
   effects.
6. Select a single P1 semantic or formal slice (`SEM-01`, `FORM-01`, `CDC-01`,
   `MEM-01`, or `PROTO-02`) with an available good-DUT/mutant fixture and open
   tooling. Complete its full common completion contract before starting the
   next slice.
7. In parallel only where licenses and owners allow, establish the missing
   evidence adapters: mixed-language manifest production (`SEM-02`), a licensed
   simulator/formal adapter (`TOOL-01`), and vendor coverage import (`COV-01`).
   Adapter work must not claim support for a feature it has not executed.
8. Start `BOARD-01` only after `TIER-01` gates and the selected vendor adapter
   work. Close one exact legal reference-board revision through board manifest,
   XSim/vendor execution, mutations, coverage, and strict status before adding
   more boards, devices, or physical claims.
9. Run the enterprise pilots against the exact release-candidate wheel after
   their relevant target profiles have per-check execution, provenance, coverage
   reconciliation, and strict-status evidence. Import independently signed
   licensed-tool evidence for UVM, simulator, formal, CDC/RDC, and coverage
   bundles before promotion.
10. Take `AI-01`, `AI-02`, and `PHYS-01` to product/security owners as explicit
   decisions. Keep model-authored code, cross-provider routing, and physical
   sign-off integrations fail-closed until a versioned decision package and
   acceptance plan exist.
11. Schedule P2 scale breadth beyond `SCALE-02`, platform, OCR/retrieval, and
   broader database work only
   after the selected P1 profiles are reproducible and the required external
   tool evidence can be retained in CI or a governed evidence store.

<a id="source-docsplanningimplementation-planmd"></a>
## Implementation Plan

Consolidated from `docs/planning/implementation-plan.md`.

Document type: historical roadmap and staged design record.

Authority: accepted architecture decisions and the stage definitions in this
document. This document is not current capability or release evidence.

Scope: intended implementation order, historical stage outcomes, and remaining
roadmap context.

Status: historical roadmap. Individual "implemented" or "complete" labels
describe the recorded stage outcome and may be superseded by current
regressions.

Last reviewed: 2026-07-27.

Superseded by: [Missing Work](#source-docsplanningmissing-workmd) for current issue state,
[Capability Matrix](verification.md#source-docsqualificationcapability-matrixmd) for bounded current
support claims, and the repository-level
[GA gate ledger](../qualification/policies/ga-gates-v1.json) for release
gate state.

Known issues: `BUG-CDC-01`, `QUALITY-01`, `DOC-00`, and `DOC-02`.

The P0 and P1 acceptance slices were implemented at their recorded snapshots.
Do not use an "implemented", "complete", or accepted stage label here to infer
that the current working tree passes. Read the
[Agent Execution Guide](agents.md#source-docsagent-execution-guidemd), then use
[Missing Work](#source-docsplanningmissing-workmd) for current regressions and actionable backlog.

This document breaks the platform into implementation stages so future agents
can make progress without rediscovering product priorities. Each stage should
leave the repository in a working state with tests and documentation updated.

<a id="source-docsplanningimplementation-planmd--guiding-priorities"></a>
### Guiding Priorities

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

<a id="source-docsplanningimplementation-planmd--stage-0-repository-foundation"></a>
### Stage 0: Repository Foundation

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

<a id="source-docsplanningimplementation-planmd--stage-1-local-cli-configuration-and-project-discovery"></a>
### Stage 1: Local CLI Configuration and Project Discovery

Goal: make the CLI usable against a real enterprise RTL repository without
requiring generated collateral yet.

Status: the P1 discovery/configuration slice is complete. The CLI writes and loads local TOML
configuration, normalizes configured paths, discovers HDL and documentation
inputs, parses common Verilog file-list flags, validates input-consuming
configuration, supports explicit numeric elaboration overrides, and emits the
project manifest used by dry-run and execution. Additional enterprise file-list
conventions remain post-P1 compatibility work.

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

See [ADR-0001](architecture.md#source-docsadr0001-local-project-configurationmd).

- Configuration format: TOML.
- Project config location: the default config lives in the client repository
  root as `dv-platform.toml`. Generated manifests, caches, logs, indexes, and
  other machine state live under the configured work directory.
- Missing file-list behavior: interactive/local exploratory runs may walk HDL
  files directly and must emit a warning that analysis can be incomplete. CI/CD
  or strict mode must treat missing RTL file lists as an error.

<a id="source-docsplanningimplementation-planmd--stage-2-verilator-ast-extraction-and-normalization"></a>
### Stage 2: Verilator AST Extraction and Normalization

Goal: turn Verilator AST output into internal RTL facts that can support
claim-checking.

Status: the P1 normalization slice is complete. `dv-platform analyze-rtl` runs
the configured Verilator XML command, records and gates the detected major
version, stores raw evidence/logs, and writes schema-v5 normalized facts. The
facts include structured ports/parameters/types, memory shape and access,
original/elaborated/specialized hierarchy identity and bindings, procedural
expressions and patterns, generate/import facts, control domains, structural
CDC paths, and profile-driven handshake channels. Complete language semantics
and broader version fixtures remain post-P1 work.

Deliverables:

- Verilator command builder using configured file lists, include paths, defines,
  and top modules. Implemented.
- AST artifact storage under the work directory. Implemented for raw XML files
  produced in `<work-dir>/verilator` plus stdout/stderr logs.
- Parser/normalizer for relevant AST facts:
  - modules and structured ports. Implemented for the P0 fixtures.
  - numeric elaborated parameters and unpacked memory shape. Implemented.
  - instances, original/specialized identities, and port connections.
    Implemented for resolved hierarchy nodes.
  - continuous assignments and basic expression trees. Implemented
    conservatively.
  - procedural blocks, basic expressions/patterns, and control domains.
    Implemented conservatively.
  - clocks/resets when inferable. Implemented from sensitivity evidence with
    recorded name-heuristic fallback.
  - conventional flat ready/valid protocols. Implemented.
  - assertions and covers. Summary extraction implemented; semantics remain
    open.
- Stable `EvidenceRef` locators for AST-backed facts. Implemented with legacy
  `fl` and current `loc` source-location support when available.
- `dv-platform analyze-rtl` command implementation. Implemented.

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

See [ADR-0002](architecture.md#source-docsadr0002-verilator-xml-evidencemd).

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

<a id="source-docsplanningimplementation-planmd--stage-3-documentation-ingestion-and-rag-indexing"></a>
### Stage 3: Documentation Ingestion and RAG Indexing

Goal: build a local semantic retrieval path for design intent.

Status: the P1 local retrieval slice is complete. The CLI discovers configured
Markdown, plain-text, reStructuredText, and PDF documentation; normalizes and
chunks text with stable IDs, exact offsets/page locators, and content hashes;
writes local JSON chunk and deterministic hash-vector indexes; reuses unchanged
vectors; retrieves relevant chunks; and attaches them to requirements and plans
as evidence. Concrete provider hooks, large-corpus indexing, OCR, and retrieval-
quality evaluation remain broader work.

Deliverables:

- Document loader for Markdown and plain text. Implemented, including
  reStructuredText.
- PDF-to-text extraction with page-aware evidence and fail-closed encrypted or
  image-only handling. Implemented with `pypdf`.
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

See [ADR-0003](architecture.md#source-docsadr0003-local-first-documentation-retrievalmd).

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

<a id="source-docsplanningimplementation-planmd--stage-4-claim-model-and-evidence-validation"></a>
### Stage 4: Claim Model and Evidence Validation

Goal: make agent conclusions explicit and checkable before generation.

Status: the P0 claim-gating slice is complete. Claims carry type, severity, and
generation-precondition metadata. Deterministic AST/documentation checkers,
status transitions, strict/local gates, target-specific semantic support,
requirement-conflict gates, and JSON/Markdown claim reports are implemented.
Richer semantic contradiction analysis remains broader work.

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

See [ADR-0004](architecture.md#source-docsadr0004-claim-validation-gatingmd).

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

<a id="source-docsplanningimplementation-planmd--stage-5-verification-planning"></a>
### Stage 5: Verification Planning

Goal: produce evidence-backed module-level verification plans.

Status: the P1 planning slice is complete. The CLI loads normalized RTL facts
and local retrieval indexes, generates deterministic module plans, attaches
precise evidence, evaluates claim gates, and writes schema-v7 canonical SQLite
records plus deterministic Markdown and claim-report views. Plans now retain
design-unit/specialization identity, parameters, types, memories/accesses,
hierarchy/generate facts, control domains/CDC paths, protocols, stable
categorized check records, structured behaviors, deduplicated requirements, and
conflicts. Agent-backed planning and broader executable requirement semantics
remain open.

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

See [ADR-0005](architecture.md#source-docsadr0005-sqlite-canonical-storesmd).

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

<a id="source-docsplanningimplementation-planmd--stage-6-requirements-driven-simulation-generation-and-execution-loop"></a>
### Stage 6: Requirements-Driven Simulation Generation and Execution Loop

Goal: deliver the first executable generated simulation workflow while keeping
target selection driven by client requirements and project configuration.

Status: the P1 simulation/closure slice is complete. The CLI generates evidence-backed
cocotb tests from stored plans, publishes staged module trees with hashed
provenance and source-bound execution manifests, revalidates content and
generated-to-plan traces before execution, runs through Icarus, rejects
missing/malformed/zero-test/skipped-only results, runs every generated module,
and persists independent per-check outcomes, trace coverage, triage, and
command/log/summary state. Coverage import/gating and bounded parallel
`run --all` execution are also implemented.
A golden real-tool
fixture repeats the complete workflow and requires stable outputs and clean
stale-state replacement. The expanded fixture uses a numeric parameter override,
vector ready/valid data, unpacked storage, case logic, hierarchy connections,
and end-to-end backpressure/data-integrity checks.

Deliverables:

- Initial simulation generator backend selected by requirements and config.
  Implemented for cocotb.
- Generated simulation tests for clock/reset bring-up and IO connectivity.
  Implemented for structured reset, increment, hold, vector IO, conventional
  ready/valid transfer/backpressure/data integrity, and hierarchical behavior
  in the supported P0 slice.
- Target-specific simulator configuration adapter. Implemented for cocotb with
  Icarus.
- `dv-platform generate --target <target>`. Implemented for cocotb.
- `dv-platform run` for configured simulation targets. Implemented for cocotb
  module runs and target-level `--all` runs.
- Failure summary and feedback into plans. Implemented with result counts,
  failed testcase names, log tails, artifact/provenance paths, aggregate target
  summaries, per-check outcomes and generated-symbol trace coverage,
  requirement/claim/behavior traceability,
  triage, and repair suggestions; automatic plan mutation remains deferred.

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

See [ADR-0006](architecture.md#source-docsadr0006-requirements-driven-generation-targetsmd).

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

<a id="source-docsplanningimplementation-planmd--stage-7-formal-generation-and-advanced-hdluvm-backends"></a>
### Stage 7: Formal Generation and Advanced HDL/UVM Backends

Goal: expand from requirements-driven simulation generation into formal
collateral and advanced native HDL/UVM backends.

Status: the P1 formal/native/UVM slice is complete for evidence-backed supported semantics. Formal tool configuration is modeled,
loaded from and written to `[[formal_tools]]`, and checked for strict/CI formal
target generation and execution. The CLI generates a SymbiYosys-oriented formal
harness and prove/cover `.sby` configuration with assumptions, evidence traces,
an input-bound execution manifest, and provenance; executes a run-local copy;
and persists tool version, per-task and per-check proof results,
counterexample paths, trace coverage, triage, and command/log/summary state.
Native SystemVerilog emits supported SVA properties, and a single inferred
handshake pair produces a transaction-level UVM environment. Hosted CI runs the open
formal stack as a
mandatory pilot for both the counter and a parameterized memory-backed
ready/valid buffer. Supported synchronous memory writes have formal properties;
protocol libraries, liveness, complex memories, and multi-domain properties
remain part of the broader Stage 7 scope.

Deliverables:

- Formal tool configuration plumbing. Implemented.
- Formal harness/assertion generator. Implemented for evidence-backed
  reset/increment/hold and ready/valid source-stability properties, vector
  symbolic inputs, numeric elaborated parameters, and prove/cover tasks.
- Tool-specific run script adapters. Implemented for SymbiYosys command
  execution, result parsing, trace discovery, and failed-property feedback.
- Advanced SystemVerilog test bench generator.
- Advanced Verilog test bench generator.
- VHDL test bench generator.
- Initial UVM environment generator for module-level agents.

All four native backends consume structured port/control metadata.
SystemVerilog includes supported assertions/covers; UVM emits full components
for one unambiguous sink/source handshake and a conservative scaffold otherwise.
SystemVerilog and Verilog outputs are linted by Verilator, VHDL is analyzed by
GHDL when available, and strict UVM generation fails closed while no UVM-capable
validator is configured. Multi-agent and standard-protocol behavior remains
open.

Priorities:

- Formal generation should be conservative and assumption-aware.
- UVM generation should wait until reusable agent boundaries are clear.
- Backends should share plan/evidence inputs but own language-specific emitted
  code.

Exit criteria:

- Each backend can generate at least one fixture artifact. Implemented.
- Generated artifacts include provenance refs, quality metadata, and content
  integrity fields. Implemented, including executable symbol-to-plan traces and
  source-bound execution manifests.
- Syntax or lint checks run where tools are configured. Implemented for Python,
  Verilator, GHDL, and formal execution; an open UVM validator remains missing.

Decisions:

See [ADR-0007](architecture.md#source-docsadr0007-formal-uvm-backend-boundariesmd).

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

<a id="source-docsplanningimplementation-planmd--stage-8-design-decision-reports"></a>
### Stage 8: Design Decision Reports

Goal: produce module and submodule recommendations that are useful to RTL
owners.

Status: the P1 reporting slice is complete. `dv-platform review` writes
evidence-backed SQLite, JSON, and Markdown findings for control classification,
multi-clock risk, incomplete hierarchy, memory boundaries, protocol closure,
missing assertions/covers, unsafe CDC, and current failed or incomplete runs.
Findings persist explicit confidence. Broader taxonomy/filtering, YAML, and
SARIF remain open.

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
- Evidence-backed `DesignDecision` reports. Implemented for the deterministic
  P0 taxonomy.
- `dv-platform review` command implementation. Implemented.
- Severity and confidence scoring. Implemented.

Priorities:

- Recommendations should cite AST facts, docs, or tool results.
- Avoid style-only feedback unless tied to system risk.
- Make confidence explicit.

Exit criteria:

- Reports are generated for fixture modules.
- Each recommendation has scope, rationale, severity, and evidence.
- Tests cover report serialization and evidence requirements.

Decisions:

See [ADR-0005](architecture.md#source-docsadr0005-sqlite-canonical-storesmd).

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

<a id="source-docsplanningimplementation-planmd--stage-9-enterprise-hardening"></a>
### Stage 9: Enterprise Hardening

Goal: make the CLI reliable enough for pilot use inside enterprise workflows.

Status: the P1 hardening slice is complete. Stable human/JSON envelopes and
exit codes, versioned facts/plans/provenance/execution manifests, atomic and
staged publication, digest-bound execution, stale-output cleanup, strict CI
status policy, a locked package build, dependency audit, and hosted compatibility
and real-tool gates are implemented. Owner-only audit logs, configured
redaction, RTL/vector caching, coverage gating, bounded run concurrency, and a
versioned explicit adapter-loader boundary are also implemented. Full
dependency-graph incrementality, export governance, scale budgets, concrete
enterprise adapter hooks, and broader platform compatibility remain open.

Deliverables:

- Structured logs. Implemented for deterministic command/tool/summary records
  and a redacted JSONL audit-event stream.
- JSON outputs for CI. Implemented for single-command workflows and status;
  aggregate `run --all` remains text plus a JSON file.
- Exit code policy. Implemented.
- Cache invalidation for ASTs, docs, embeddings, plans, and artifacts. Partial:
  input-fingerprint RTL caching, unchanged vector reuse, source/provenance
  freshness, and whole-stage rebuilds are implemented; dependency-graph
  incrementality remains open.
- Versioned schemas. Implemented for current canonical and execution state.
- Redaction controls. Implemented for configured persisted logs/summaries/audit;
  export allowlists and retention policy remain open.
- Performance budgets for large repositories. Open.
- Installation documentation. Implemented for the P0 open-tool path.

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

See [ADR-0008](architecture.md#source-docsadr0008-enterprise-plugins-platforms-distributionmd).

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
  target. Python 3.11, 3.12, and 3.13 are exercised by hosted compatibility
  tests, with future versions gated on dependencies and enterprise environments.
- Distribution model: ship as a Python wheel first. Add optional enterprise
  container images later for reproducible CI runners. Defer standalone binaries
  until pilot feedback shows a concrete need. Containers must not be the only
  supported path because many EDA tools require licensed host integration.

<a id="source-docsplanningimplementation-planmd--additional-documentation-needed"></a>
### Additional Documentation Needed

These documents should be added as the implementation becomes concrete:

- `docs/cli.md`: a fuller operator command reference beyond the current
  `docs/product-and-interface.md` contract and README examples.
- `docs/product-and-interface.md`: local project config schema and enterprise
  policy settings. Added.
- `docs/architecture.md`: claim types, evidence refs, status transitions, and
  blocking policy. Added.
- `docs/architecture.md`: Verilator invocation, AST normalization, supported
  facts, and version compatibility. Added.
- `docs/rag.md`: document loading, chunking, embeddings, vector store adapters,
  retrieval scoring, and privacy expectations.
- `docs/generation-backends.md`: backend interface and language-specific output
  conventions.
- `docs/output-layout.md`: work directory, generated artifact directory, cache
  layout, and report files.
- `docs/operations.md`: local execution guarantees, network policy,
  redaction, and auditability.
- `docs/testing-strategy.md`: unit, fixture, tool-integration, generated-code,
  and end-to-end tests.
- `docs/roadmap.md`: implementation gaps, pilot-readiness work, and
  software/tool dependencies still needed. Added.
- `docs/product-and-interface.md`: Python package installation and required
  system tools. Added.
- `docs/architecture.md`: architecture decision records for major irreversible choices.
  Initial accepted ADRs have been added for the stage decisions resolved so far.

<a id="source-progressmd"></a>
## Project Progress

Consolidated from `progress.md`.

This ledger records implementation work and validation evidence. Add future
entries immediately below this preamble in descending date order; never rewrite
an older entry to change its historical result.

### 2026-07-29 — Ubuntu Stage 10 closure and WSL downgrade

- The merged Stage 10 workflow produced a passing Ubuntu 24.04 installed-wheel
  candidate/baseline comparison and contextual candidate evidence bundle.
- `SCALE-02` and `QUAL-01` are closed for the Ubuntu-only current platform
  claim. WSL2 is explicitly non-current because its self-hosted runner was not
  available; prior WSL records remain historical evidence.
- The next release-blocking item is `RELEASE-01`.

### 2026-07-29 — RELEASE-01 foundation

- Added versioned development/alpha/beta/RC/GA/patch channel policy and
  exact tag/package/SHA validation before dependency installation.
- Added exact Stage 10 qualification-run verification and a build-once release
  manifest binding source, workflow, lockfile, package version, and subjects.
- Publication idempotency, protected release approval, signed recovery state,
  and exact remote-digest reinstall remain the next closure work.

<a id="source-progressmd--2026-07-28-documentation-consolidation"></a>
### 2026-07-28 — Documentation consolidation

- Consolidated 70 human-documentation sources into the seven-file flat set
  under `docs/`: `README.md`, `product-and-interface.md`, `architecture.md`,
  `verification.md`, `operations.md`, `agents.md`, and `roadmap.md`.
- Preserved every migrated source under a stable `source-*` anchor with a
  source-coverage entry and provenance label. The complete Missing Work,
  Implementation Plan, and Project Progress texts are retained in this guide;
  all 37 product/backlog cards retain implementation or post-approval
  implementation, validation, and stop conditions.
- Replaced conventional root `README.md`, `SECURITY.md`, `CHANGELOG.md`, and
  `progress.md` with compatibility pointers. Retained
  `THIRD_PARTY_NOTICES.md`, skill manifests, and fixtures in their
  distribution/runtime-required locations.
- Moved the compatibility baseline and Vivado XSim attestation from `docs/`
  into `qualification/`; updated code, tests, prose, and the GA ledger. GA
  evidence references now target exact consolidated source anchors and the
  validator rejects a missing anchor.
- Extended repository contracts to reject nested documentation Markdown,
  missing source sections/provenance, duplicate or broken anchors, invalid
  links, stale capability schema/state rows, and missing/incomplete roadmap
  cards.
- Validation passed: repository contracts over 12 maintained Markdown files,
  GA ledger, accepted compatibility fingerprint, maintainability (265 modules,
  16 templates, 1,711 functions, zero cycles, 45 duplicate blocks), Ruff lint
  and format, mypy over 265 source files, source/wheel package build, focused
  documentation/qualification tests (31), and the full suite (586 tests, four
  expected optional skips).
- The suite reproduced the already-open `AI-03` optimizer subprocess and
  descriptor `ResourceWarning` symptoms. No test failed, and this migration
  does not claim that issue closed.
- `DOC-03` remains in progress: the flat-layout/source-preservation foundation
  is complete, but the versioned catalog, class metadata, broader command
  parsing, capability reconciliation, and machine progress transitions remain
  required by its updated card.

<a id="source-progressmd--2026-07-27-local-residual-closure-and-evidence-gate-normalization"></a>
### 2026-07-27 — Local residual closure and evidence-gate normalization

- Refactored AI context-optimization execution into a fail-safe repair
  structure and split long methods to satisfy maintainability limits.
- Consolidated depth-parameter validation helpers to reduce code duplication and
  keep bounded-integer/boolean checks centrally shared.
- Updated compatibility baseline fingerprint and contract counts after the
  refactor, preserving executable and schema compatibility guarantees.
- Updated AI/validation dispatch behavior for safer context-optimization reporting
  and resilient code-graph invocation payload handling.
- Closed the local regression gap from `BUG-CDC-01` by restoring the SECDED
  bounded-memory formal closure through explicit CDC intent handling.
- QUALITY gates are now locally green: ruff, formatting, mypy, compatibility,
  maintainability, repository contracts, and related quality checks pass.
- Integration-level checks validate:
  - full local CLI and execution workflows (`uv run python -m unittest discover -s tests.integration -v`);
  - context-optimization behavior (`uv run python -m unittest tests.ai.test_context_optimization -v`);
  - AI/validation quality (`uv run ruff check src tests scripts`, `uv run ruff format --check src tests scripts`,
    `uv run mypy`, `uv run python scripts/checks/compatibility.py --check`,
    `uv run python scripts/checks/maintainability.py --check`).
- GA ledger integrity remains valid through Stage 10; Stage 11 remains pending
  for all vendor profiles until fresh independently-signed attestations are
  present.

<a id="source-progressmd--2026-07-23-repository-wide-concern-based-reorganization"></a>
### 2026-07-23 — Repository-wide concern-based reorganization

- Reorganized implementation, tests, documentation, scripts, schemas,
  qualification records, templates, packaged qualification assets, and mutation
  fixtures into concern-based subdirectories.
- Preserved documented Python compatibility surfaces, console and plugin entry
  points, flat packaged schema resource names, schema identifiers, rendered
  artifact bytes, and the compatibility fingerprint
  `84339d5238944755db7abb1d00620e8a7395fb3df0aa8e501a180992ff04876d`.
- Expanded ignore policy for nested runtime state, local stores, editor and
  environment files, Python tool caches, and common EDA outputs while retaining
  source JSON and XML files.
- Validation: 580 tests pass with four expected optional skips. Ruff, formatting,
  mypy, compatibility, maintainability, repository-contract, GA-gate, secret,
  package-build, clean-wheel smoke, coverage, and branch-ratchet checks pass.

<a id="source-progressmd--2026-07-21-bounded-synchronous-memory-acceptance"></a>
### 2026-07-21 — Bounded synchronous memory acceptance

- Added fail-closed policy validation for one known synchronous memory, exact
  clock/reset/read mappings, two byte-enabled write requesters, collision behavior,
  zero initialization, round-robin arbitration, and parity injection/detection.
- Added a typed `memory_bounded_sram` scenario and complete cocotb/formal renderer,
  validator, trace, and result-decoder registration.
- Generated cocotb now scoreboards every legal address, byte-lane merging, low/high
  boundaries, collisions, both grants, contention fairness, initialization/recovery,
  and clean/injected parity outcomes.
- Generated formal now checks exclusive/work-conserving grants, consecutive-contention
  round robin, declared collision behavior, a byte-merged bounded reference word,
  initialization, parity outcomes, and non-vacuity covers.
- The good DUT passes repeated deterministic full-CLI runs. Generated cocotb and formal
  collateral kill eight mutants spanning byte enables, collisions, starvation,
  initialization, parity, grant exclusivity, discarded writes, and read addressing.
- SECDED correction, repair/scrubbing, initialization files, asynchronous or wider
  multi-port memories, power retention, and physical macro timing remain unsupported.

<a id="source-progressmd--2026-07-21-stage-4-verification-depth-completion"></a>
### 2026-07-21 — Stage 4 verification-depth completion

- Added a governed bounded-response formal profile with exact signal/domain
  validation, a property-specific trigger assumption, response causality,
  induction state/design invariants, bounded liveness, and non-vacuity covers.
  The real formal pipeline passes the good DUT and kills missing, late,
  invariant-breaking, and non-causal response mutants.
- Advanced coverage to schema v3 with explicit parameter-sweep grouping and
  semantic cross-points. A real WIDTH=4/WIDTH=9 Verilator/Icarus/cocotb pipeline
  closes every point; an incomplete specialization fails coverage and CI status.
- Advanced RTL facts to schema v10 and added a bounded VHDL-only source frontend.
  It normalizes entities, integer-like generics and sweeps, constrained scalar/vector
  ports, one unambiguous architecture, clock/reset processes, concurrent assignments,
  and VHDL source evidence without invoking Verilator.
- Added fail-closed boundaries for unknown generics, unresolved/unconstrained types,
  ambiguous architectures, mixed-language binding, and required Slang cross-checking.
- Added acceptance documents that compare all seven Stage 4 roadmap items against
  implementation and test evidence. GHDL execution remains a later-stage target.
- Final verification: 462 tests pass with four expected optional skips. Ruff,
  formatting, mypy, package build, dependency audit, and every coverage ratchet
  pass. Combined coverage is 86.15%, statement coverage is 89.07%, and true
  branch coverage is 78.10% across 5,146 branches.

<a id="source-progressmd--2026-07-21-bounded-axi4-lite-open-tool-acceptance"></a>
### 2026-07-21 — Bounded AXI4-Lite open-tool acceptance

- Required the complete AW/W/B/AR/R payload and handshake signature, consistent
  slave directions and widths, and unambiguous clock/reset evidence before a
  scenario can be executable. Renderer registrations are now downgraded per
  scenario when required scoreboard evidence is absent.
- Added typed generated cocotb driver, monitor, register reference model,
  independent AW/W capture, one-read/one-write outstanding and concurrent
  progress checks, bounded completion, five-channel coverage, response
  backpressure stability, WSTRB, error/invalid-address, and reset-recovery tests.
- Added typed formal state, independent read/write address tracking, AR-time
  read snapshots, register scoreboarding, all-channel stability and bounded
  response properties, no-extra-response/no-second-request properties, and
  ordering/backpressure/error covers. Bounded Z3 tasks use deterministic
  unrolling to stay within the configured process-memory budget.
- Added SystemVerilog AW/W/B/AR/R payload-stability assertions while retaining
  native execution as a scaffold without a normalized result decoder.
- Replaced the hand-written AXI mutation pilot with full generated CLI matrices.
  The good DUT passes and repeated generation is byte-identical; generated
  cocotb and formal collateral kill ten mutants covering AW/W coupling, lost
  and early BVALID, unstable BRESP, dropped RVALID, unstable RDATA/RRESP,
  ignored WSTRB, wrong error responses, and second outstanding AW/AR requests.
- Full AXI, bursts, IDs, and more than one outstanding transaction per direction
  remain explicitly unsupported.
- Validation: 415 tests pass with four expected optional skips; Ruff, formatting,
  and mypy pass. Combined coverage is 85.63%, statement coverage is 88.69%, and
  branch coverage is 77.04% across 4,500 branches; every coverage ratchet passes.

<a id="source-progressmd--current-baseline"></a>
### Current baseline

- P0/P1 local workflow exists: discovery, Verilator analysis, documentation
  indexing, evidence-backed planning, generation, execution, coverage, review,
  and CI status gating.
- Test-code generation exists for cocotb, formal, SystemVerilog, Verilog, VHDL,
  and UVM. Cocotb/formal and the supported protocol-backed UVM path are
  executable; several other targets remain conservative scaffolds.

<a id="source-progressmd--completed-semantic-work"></a>
### Completed semantic work

<a id="source-progressmd--parameter-sweeps"></a>
#### Parameter sweeps

- Added explicit `parameter_sweeps` configuration and `--parameter-sweep` init
  arguments.
- Each elaboration point runs in an isolated work directory.
- Sweep-qualified module, plan, evidence, and provenance identities prevent
  cross-configuration result mixing.
- Validated with two real Verilator sweep points, six normalized modules, six
  plans, and cocotb generation.

<a id="source-progressmd--branch-and-case-semantics"></a>
#### Branch and case semantics

- Normalized case selectors, labels, default branches, source locations, and
  plain-case exclusivity.
- `casez`/`casex` or incomplete case-item semantics remain unknown.
- Unknown matching semantics produce critical claims and block executable
  generation.

<a id="source-progressmd--expression-sizing-and-casting"></a>
#### Expression sizing and casting

- Normalized expression width and signedness from Verilator dtype evidence.
- Preserved literal widths and explicit cast kinds.
- Unresolved explicit casts produce critical generation claims.
- Unresolved arithmetic widths remain actionable open questions for conservative
  black-box generation.

<a id="source-progressmd--validation-baseline"></a>
### Validation baseline

- 317 tests pass; one optional real-tool test is skipped when unavailable.
- Ruff, formatting, mypy, package build, and dependency audit have passed in the
  current development baseline.
- Real Verilator pilot analysis passes.

<a id="source-progressmd--remaining-high-risk-semantic-gaps"></a>
### Remaining high-risk semantic gaps

- Full SystemVerilog sizing/casting rules across every operator.
- Packed aggregate operation semantics and complete interface/modport behavior.
- Package-qualified symbol resolution and generate conditions.
- Assertion and cover semantics.
- Broader CDC, reset, and memory behavior.

<a id="source-progressmd--latest-update-packed-aggregate-type-facts"></a>
### Latest update — packed aggregate type facts

- Added structured member metadata for aggregate types: member dtype, width,
  signedness, packed range, and source location.
- Preserved this metadata in normalized RTL facts and plan persistence.
- Existing aggregate operations remain conservative; unsupported struct/union
  operations are not promoted to executable semantic closure.
- Added regression coverage using a packed struct fixture.
- Validation: 316 tests pass; Ruff, formatting, and mypy pass.

<a id="source-progressmd--latest-update-interfacemodport-directionality"></a>
### Latest update — interface/modport directionality

- Added structured interface port facts: interface name, modport, and resolved
  direction.
- Persisted the facts in normalized RTL output and plan storage.
- Unresolved interface identity, modport, or direction creates a critical
  generation precondition rather than an inferred direction.
- Added an interface/modport normalization fixture.
- Validation: 317 tests pass; Ruff, formatting, and mypy pass.

<a id="source-progressmd--status-reconciliation-2026-07-20"></a>
### Status reconciliation — 2026-07-20

- Removed interface/modport directionality from the remaining-gap list because
  structured interface name, modport, and direction facts are implemented.
- Updated the validation baseline from 316 to 317 passing tests.

<a id="source-progressmd--latest-update-systemverilog-cross-check-contract"></a>
### Latest update — SystemVerilog cross-check contract

- Added a versioned `SemanticCrossChecker` contract and deterministic normalized
  fact comparator for independent frontends such as Slang or Surelog/UHDM.
- The comparator checks module/specialization identity, ports, parameters,
  hierarchy, aggregate type members, and interface/modport facts.
- Missing modules and disagreements are explicit, non-passing issues.
- Added regression tests and [semantic-cross-check.md](architecture.md#source-docsarchitecturesemantic-cross-checkmd).
- Local tooling check: Verilator is installed; Slang and Surelog/UHDM are not.
- Validation: 320 tests pass; focused cross-check tests, Ruff, formatting, and
  mypy pass.

<a id="source-progressmd--latest-update-slang-connection"></a>
### Latest update — Slang connection

- Added `SlangAnalyzer`, a real Slang AST-JSON frontend adapter with explicit
  executable configuration, SystemVerilog standard selection, include paths,
  defines, top-module selection, parameter overrides, source locations, and
  detailed type output.
- Normalized Slang instance bodies into `RTLModule` facts covering module
  identity, ports, scalar/packed widths, signedness, parameters, and hierarchy
  instances. Scalar widths are normalized to one bit for cross-frontend
  comparison.
- Executed the locally built Slang 11.0.424 binary against the pilot RTL and
  compared its three modules with Verilator facts: 3 modules checked, 0 issues,
  comparison passed.
- Added AST normalization regression coverage and updated the residual-work
  ledger to distinguish the working structural adapter from open behavioral,
  assertion, interface, generate, aggregate-type, and compatibility coverage.
- Validation: 321 tests pass; one optional real-tool test is skipped; Ruff,
  formatting, and mypy pass.

<a id="source-progressmd--latest-update-slang-procedural-and-assignment-facts"></a>
### Latest update — Slang procedural and assignment facts

- Extended Slang normalization to capture continuous assignments, left/right
  signal references, procedural block kinds, source locations, and referenced
  signals.
- Extended the normalized cross-check to compare assignment shape and
  procedural-block presence in addition to ports, parameters, hierarchy, and
  types. Parameter constants are excluded from signal-reference comparisons.
- Re-ran the real pilot comparison with Slang 11.0.424: 3 modules checked,
  0 issues, comparison passed.
- Added regression coverage for Slang assignment normalization and updated
  the semantic cross-check documentation.
- Validation: 321 tests pass; one optional real-tool test is skipped; Ruff,
  formatting, and mypy pass.

<a id="source-progressmd--2026-07-20-staged-slang-production-integration"></a>
### 2026-07-20 — Staged Slang production integration

<a id="source-progressmd--stage-1-workflow-integration"></a>
#### Stage 1 — workflow integration

- Added `slang_executable` and `semantic_crosscheck = "off" | "report" |
  "required"` to configuration, validation, deterministic TOML output, and
  `init` options. The backward-compatible default is `off`.
- `analyze-rtl` now invokes Slang with the same discovered files, includes,
  defines, tops, and parameter overrides as Verilator for ordinary and sweep
  runs. Each sweep remains isolated.
- Persisted Slang AST, redacted stdout/stderr, diagnostics, detected version,
  exact command, point comparison, and aggregate comparison under
  `.dv-platform`.
- Added Slang policy/version to manifests and cache fingerprints. Passing and
  report-only results can be cached; enforcing workflows re-check the cached
  status. Stale AST output is removed before invocation.
- `report` continues exploratory analysis but enforces under strict/CI;
  `required` always enforces. `plan` and `generate` enforce the same trust gate.

<a id="source-progressmd--stage-2-comparison-contract"></a>
#### Stage 2 — comparison contract

- Advanced the cross-check API and artifact schema to version 2 with run
  identity, frontend metadata, capability coverage, status, unsupported
  capabilities, specialization identity, source locations, and AST evidence.
- Pair modules by original design unit and canonical parameter specialization,
  independent of insertion order. Multiple Slang `InstanceBody` records are
  retained and ambiguous duplicates fail closed.
- Canonicalized ordering, scalar widths, constants, ranges, operation names,
  and tool-specific type identity. Only declared capabilities compare; a
  missing capability required by primary facts is an error.
- Added `EvidenceKind.SLANG_AST`.

<a id="source-progressmd--stages-36-semantic-facts"></a>
#### Stages 3–6 — semantic facts

- Added recursive Slang expression normalization, continuous/procedural
  assignments, conditional/case branches, event-derived control domains, and
  explicit expression width/signedness/range/cast facts.
- Added structured `RTLProperty` facts and plan persistence. Incomplete temporal
  operators produce critical generation-precondition claims.
- Extended type/interface/import mapping, aggregate member and array dimension
  facts, instance bindings/connections, generate conditions/selection/iteration,
  and unpacked-memory dimensions.
- Extended cross-check signatures for expressions, branches, domains,
  properties, types, interfaces, imports, hierarchy, generate scopes, and
  memories. Unsupported constructs remain explicit capability gaps and never
  supplement Verilator facts.
- Advanced RTL facts to schema 8 and plans to schema 14 with backward-readable
  defaults.

<a id="source-progressmd--stage-7-qualification"></a>
#### Stage 7 — qualification

- Qualified strict version policy for Verilator major 5 with Slang major 11.
  Local real-tool testing skips when Slang is absent; setting
  `DV_PLATFORM_QUALIFIED_SLANG_CI=1` makes tool availability and the real strict
  CLI pairing mandatory.
- Added regression coverage for off/report/required behavior, strict generation
  gates, successful dual execution, cache hits, missing executables, invalid
  JSON, compilation failures, stale output, path quoting, mismatches,
  specialization ordering, repeated specializations, capability gaps, and
  structured semantic mapping.
- Reconciled semantic-cross-check, configuration, installation, CLI artifact,
  and remaining-work documentation.
- Validation: 332 tests pass; two real-tool tests skip locally because optional
  tools are unavailable. Ruff lint and format checks pass, mypy passes across
  60 source files, source/wheel builds pass, and `pip-audit` reports no known
  third-party vulnerabilities (the local package is not published on PyPI).

<a id="source-progressmd--2026-07-20-qualification-audit-and-semantic-closure"></a>
### 2026-07-20 — Qualification audit and semantic closure

This entry supersedes the validation and completeness claim immediately above.
The first implementation used presence-based capabilities and heuristic AST
node names; real Slang 11 JSON showed that properties, package types,
interfaces, memories, branches, and repeated hierarchy could be omitted while
appearing successful. Those gaps are now closed as follows.

<a id="source-progressmd--stage-1"></a>
#### Stage 1

- Revalidated ordinary and parameter-sweep execution, command parity,
  artifacts, cache identity, `off`/`report`/`required` behavior, strict/CI
  enforcement, and downstream plan/generation gates.
- Required runs now require the entire qualified profile rather than only
  capabilities for which a non-empty fact list happened to exist.

<a id="source-progressmd--stage-2"></a>
#### Stage 2

- Capability declarations now describe frontend support independently of
  construct presence. Unsupported AST nodes withdraw a capability with a
  source-located reason, so an incomplete empty view cannot pass.
- Canonical specialization values ignore frontend literal spelling and retain
  every distinct parameter specialization. Repeated generated instances use
  stable hierarchical names instead of insertion order.
- Replaced recursive whole-document tuple construction with an iterative walk.

<a id="source-progressmd--stage-3"></a>
#### Stage 3

- Qualified real Slang nodes for literals, references, element/range selects,
  concatenation, replication, calls, unary/binary operations, implicit and
  explicit conversions, conditional expressions, procedural assignments,
  `if`, plain/wildcard cases, and source/type metadata.
- Verilator normalization now retains procedural assignments, `if` branches,
  `casez`/`casex` evidence, repeated generated instances, and nested
  sensitivity controls. Real fixtures cover synchronous and asynchronous reset
  domains.

<a id="source-progressmd--stage-4"></a>
#### Stage 4

- Qualified immediate assert/cover and concurrent assert/cover facts, including
  clocking, edge, `disable iff`, implication, sequence delay, labels, and
  support state. Unsupported property nodes withdraw property capability and
  still create critical planning claims.
- Verilator 5's rejection or lowering-away of temporal structure is an expected
  fail-closed compatibility outcome, not a passing empty property set.

<a id="source-progressmd--stage-5"></a>
#### Stage 5

- Added recursive layout resolution for enums, nested packed structs/unions,
  signed members, bit offsets, packed/unpacked dimensions, package aliases,
  interface arrays, multiple modports, and modport member directions.
- Added the new layout fields to RTL facts and plan persistence; RTL facts are
  schema 9 and plans are schema 15.

<a id="source-progressmd--stage-6"></a>
#### Stage 6

- Preserved instance parameter bindings, port directions/connections,
  hierarchical generate iteration identity, source conditions, selected state,
  unpacked memory layout, and synchronous read/write address/data/enable facts.
- Slang omits inactive generate branches from elaborated JSON. A conservative
  source inventory now retains those scopes as `selected=false`; complex
  conditions fail the generate capability instead of disappearing.

<a id="source-progressmd--stage-7"></a>
#### Stage 7

- Added a real Slang 11 semantic fixture matrix and real Verilator 5 / Slang 11
  compatibility matrix covering successful agreement, precise disagreements,
  frontend compilation failure, missing/invalid output, path quoting, cache,
  sweeps, and interrupted/nonzero runs.
- Hosted quality CI downloads the official Slang 11.0 x86-64 artifact, verifies
  SHA-256, and makes the qualified profile mandatory with
  `DV_PLATFORM_QUALIFIED_SLANG_CI=1`.
- Added an iterative large-AST qualification benchmark with 5-second and
  64-MiB limits and documented expected matrix outcomes.

Validation after the audit: **338 tests pass** with the real Verilator 5.020 /
Slang 11.0 matrix enabled; one opt-in live AI smoke test is skipped. Ruff lint
and format checks pass, branch coverage is 84% (above the configured 80% gate),
mypy passes across 60 source files, source and wheel builds pass, and
`pip-audit` reports no known dependency vulnerabilities.

<a id="source-progressmd--2026-07-20-roadmap-stages-0-and-1-closure"></a>
### 2026-07-20 — Roadmap Stages 0 and 1 closure

Stage 0 is complete. Planning and generation now share one renderer registry;
plan schema v17 records target-specific executable/scaffold/unsupported states
and reads v16 scenarios fail-closed. Planning uses the common bounded LiteLLM
gateway; at this closure point `scenario_synthesis` was still inactive. Target-specific traces no
longer leak across backends, and hosted CI covers Python 3.11–3.13, Slang 11,
Icarus/cocotb, SBY/Yosys/Z3, build, dependency audit, and schema migrations.

Stage 1 is complete for the bounded APB4 slave profile. Complete normalized APB
facts and governed register semantics produce typed transfer/register scenarios;
those scenarios are the sole source for generated cocotb and formal bindings,
models, properties, covers, trace symbols, and timeouts. Generated full-CLI
qualification covers reset, setup/access ordering, waits, stable controls and
responses, read/write completion, PSTRB, RW/RO/W1C fields, reset values, invalid
addresses, and PSLVERR. The good DUT closes every executable check, zero or
unmatched execution remains non-closing, repeated output is byte-identical, and
both Icarus/cocotb and bounded SBY/Yosys/Z3 collateral kill all nine required
mutants. The former hand-written APB mutation bench has been removed.

Validation: **406 tests pass with four expected skips**. Ruff lint/format and
mypy pass; combined coverage is 85.38%, statement coverage 88.44%, and branch
coverage 76.77% across 4,390 branches, with every ratchet passing. The next
roadmap item is the bounded AXI4-Lite vertical slice.

<a id="source-progressmd--2026-07-21-roadmap-stages-2-and-3-closure"></a>
### 2026-07-21 — Roadmap Stages 2 and 3 closure

Stage 2 is complete for the one-read/one-write-outstanding AXI4-Lite slave
profile. Typed generated cocotb and formal collateral independently captures AW
and W, models all five channels, checks bounded completion and response
stability, applies WSTRB/error/reset semantics, rejects a second outstanding
request, and covers request ordering and response backpressure. Full-CLI good
DUT and ten-mutant matrices use only generated collateral; full AXI remains
unsupported.

Stage 3 is complete. Revision schema v3 binds canonical-plan, project-manifest,
and parent-snapshot hashes; records explicit proposal states, selected template
parameters, affected checks/scenarios/artifacts, and required rerun targets; and
requires an explicit fork when inputs change. A typed dependency graph drives
artifact-selective regeneration while preserving unrelated bytes. Every
affected provenance is invalidated, and CI status stays open through generation,
provenance-matched rerun, and coverage rebuilt from the exact fresh summaries.
Coverage reconciliation understands checks in immutable revision snapshots.

Planning, feedback, and opt-in scenario-template selection now use the common
one-model LiteLLM gateway and owner-only audit contract. Synthesis is restricted
to existing deterministic template IDs and declared values; malformed or
invented selections receive at most two same-model repairs and then deterministic
fallback.

Validation: **424 tests pass with four expected skips**. Ruff lint/format and
mypy pass; combined coverage is 85.74%, statement coverage 88.72%, and branch
coverage 77.36% across 4,642 branches, with every ratchet passing. Source and
wheel builds pass, and `pip-audit` reports no known dependency vulnerabilities.

<a id="source-progressmd--2026-07-21-roadmap-stage-4-structure-qualification"></a>
### 2026-07-21 — Roadmap Stage 4 structure qualification

Stage 4 item 1 qualifies governed pulse, toggle, and round-trip handshake
synchronizers with generated cocotb/formal good-DUT and four-mutant matrices.

Stage 4 item 2 qualifies power-of-two asynchronous FIFOs and their Gray-coded
pointers. RTL normalization retains deeply nested memory read destinations;
planning cross-checks one write and one read in distinct domains, exact
data/pointer widths, observable mappings, and both ordered Gray synchronizers.
Generated cocotb owns a bounded queue scoreboard, full/empty blocking,
wraparound, unequal-clock, reset-recovery, encoding, and transition checks.
Generated formal owns vector stage histories, reset, pointer encoding,
increment/hold, flag-equation, and reachability properties. Seven simulation
mutants and five formally claimed structural/status mutants are killed using
only generated full-CLI collateral. Reset/RDC qualification is the next Stage 4
item; Stage 4 as a whole is not yet closed.

Stage 4 item 3 qualifies governed reset domains and reset-domain crossings.
Policies bind each reset to one normalized clock domain, observable ready output,
release/recovery/removal bounds, and an optional acyclic prerequisite whose
ready indication must traverse an ordered two-stage synchronizer. Generated
cocotb and formal collateral close exact per-check outcomes for the good DUT and
kill six asynchronous-assertion, early-release, dependency-bypass, and RDC
mutants. Physical reset timing and architectural power sequencing remain
unsupported. Memory structure depth is the next Stage 4 item.

<a id="source-progressmd--2026-07-21-roadmap-stage-5-target-and-adapter-implementation"></a>
### 2026-07-21 — Roadmap Stage 5 target and adapter implementation

Native SystemVerilog and Verilog now compile manifest-bound RTL and generated
benches through Icarus and require exact versioned per-trace outcomes. The
qualified reset-to-constant slice closes through run, coverage, and CI status;
missing, stale, duplicate, partial, malformed, zero, or failed results remain
non-closing. VHDL now emits type-correct observable reset checks and has the
same fail-closed decoder behind a VHDL-2008 GHDL analyze/elaborate/run wrapper.

Tool qualification records the actual backend instead of the Python wrapper.
CI enforces Verilator 5, Icarus 12, SBY 0.67, Yosys 0.33, Z3 4.8, and GHDL 4–5;
formal summaries qualify Yosys and Z3 independently. A generated-UVM vendor
bundle now carries byte-stable `UvmGenerator` output, a loopback DUT, fixture
hashes, and mandatory `QUAL-UVM-001`. Attestation import rejects missing,
failed, or tampered evidence. UVM remains a scaffold until a licensed host
returns that evidence.

The built-in adapter matrix is connected through API-v1 entry points: local
text/PDF and OCR-sidecar loaders, local hash embeddings, JSON vector storage,
deterministic report manifests, regex redaction, UCIS XML, governed semantic and
requirements imports, and enterprise simulator/formal/analyzer runners.
Indexing and planning use configured retrieval adapters directly. Enterprise
and native exit codes cannot close a check without normalized traceability.

Integrated validation passes **477 tests with four expected optional skips**.
The final coverage, formatting, typing, package, and dependency gates are
recorded in [Stage 5 Acceptance](verification.md#source-docsacceptancestage5-acceptancemd).

<a id="source-progressmd--2026-07-21-ghdl-41-stage-5-qualification-closure"></a>
### 2026-07-21 — GHDL 4.1 Stage 5 qualification closure

The installed GHDL 4.1.0 backend now passes a generated VHDL-2008 observable
reset pipeline through analyze, plan, generate, syntax validation, elaboration,
execution, normalized per-check reconciliation, coverage, and CI status. GHDL
report prefixes are decoded without relaxing exact trace identity, simulations
have a deterministic stop time, and zero/malformed/unmatched results remain
non-closing.

Real GHDL validation also exposed and closed two portability/reproducibility
defects: vector comparisons now use target-range aggregates, and specialization
names are normalized to legal VHDL basic identifiers without consecutive
underscores. Syntax-only validation no longer records a random temporary work
path, so repeated parameter-sweep generation remains byte-identical. The hosted
real-tool job installs GHDL explicitly. Full verification passes 477 tests with
four expected optional skips, 86.17% combined coverage, 89.07% statement
coverage, and 78.18% branch coverage across 5,274 branches. Licensed UVM
attestation is the remaining external Stage 5 evidence gap.

<a id="source-progressmd--2026-07-21-vivado-simulator-uvm-qualification-and-stage-5-closure"></a>
### 2026-07-21 — Vivado Simulator UVM qualification and Stage 5 closure

AMD Vivado Simulator 2025.2 is now a versioned `vivado_xsim` enterprise profile
and simulator-runner entry point. Its generated-UVM qualification bundle includes
a standalone XSim wrapper supporting both native installations and Windows
Vivado invoked from WSL. The wrapper uses XSim's precompiled UVM 1.2 library,
applies explicit time-unit/precision overrides, and requires reference completion,
the named generated test, UVM phase completion, and zero UVM errors/fatals.

The exact Veriforge-generated ready/valid environment compiled, elaborated, and
ran 16 scoreboard transactions on the installed Vivado 2025.2. The bundle emitted
normalized passing `QUAL-SIM-001` and `QUAL-UVM-001` checks, and the resulting
tamper-evident attestation imported as `vendor_verified`. That sanitized evidence
is checked in and re-imported by tests, binding qualification to the current
generated bytes. Paired ready/valid UVM generation is therefore qualified;
fallback scaffolds, multi-agent environments, RAL, richer transactions, and
project-level UVM coverage integration remain outside the accepted subset.

This closes the final external Stage 5 evidence requirement. Stage 5 is accepted
for its bounded native, vendor-UVM, tool-range, normalized-result, and adapter
profiles without promoting the explicitly broader targets. Final verification
passes 480 tests with four expected optional skips, every coverage ratchet,
Ruff, formatting, mypy, package build, and dependency audit. Combined coverage
is 86.23%, statement coverage is 89.13%, and branch coverage is 78.25% across
5,302 branches.

<a id="source-progressmd--2026-07-22-broad-ga-staging-foundation-closure-and-ahb-lite-qualification"></a>
### 2026-07-22 — Broad-GA staging, foundation closure, and AHB-Lite qualification

- Split broad GA into sequential, machine-enforced Stages 6–12 with a
  schema-validated evidence ledger. Release-candidate and final tags cannot pass
  their workflow unless the required earlier stages and profiles are accepted.
- Closed Stage 6 with plugin publisher/hash trust, export roots, secret providers,
  retention and purge controls, malformed XML/PDF limits, SQLite backup/restore,
  security/support/licensing documentation, deterministic SBOM/checksum/SLSA
  material, reproducible builds, and clean-wheel release checks.
- Qualified the bounded 32-bit, single-master, single-beat AHB-Lite slave profile.
  Generated cocotb and bounded-formal collateral pass the good DUT and kill six
  mutations covering discarded writes, writable RO state, broken W1C behavior,
  missing error response, dropped wait state, and incorrect reset state.
- Added a fail-closed performance evidence schema and comparator for Ubuntu/WSL,
  multi-million-line RTL, large XML/PDF inputs, stage runtime, peak memory, and
  regressions above 10%. Scale measurements remain a Stage 9 evidence gate.
- Full instrumented verification passes 500 tests with four expected optional
  skips. Combined coverage is 86.15%, statement coverage is 89.08%, and true
  branch coverage is 78.15% across 5,468 branches; all ratchets, Ruff, mypy,
  repository/security checks, builds, reproducibility, and dependency audit pass.
- Stage 7 remains active for native SystemVerilog/Verilog APB4 and AXI4-Lite
  mutation closure. Stages 8–12 remain gated on VHDL/UVM, semantic/scale/platform,
  fresh vendor, enterprise-pilot, and signed promotion evidence respectively.

<a id="source-progressmd--2026-07-22-stage-7-on-chip-buses-and-streams-closure"></a>
### 2026-07-22 — Stage 7 on-chip buses and streams closure

- Promoted typed APB4 and AXI4-Lite scenarios from native scaffold state to
  executable SystemVerilog and Verilog renderers with portable transaction
  tasks, register scoreboards, bounded waits, response stability, strobe/error
  checks, AXI independent-channel ordering, and outstanding-request limits.
- Native APB4 passes the good DUT and kills nine mutants on each native target;
  native AXI4-Lite passes the good DUT and kills ten mutants on each target.
  Generated results use exact trace reconciliation and close coverage/CI status.
- Added a paired ready/valid qualification fixture and generated-cocotb matrix
  covering acceptance, data integrity, backpressure stability, and recovery;
  refusal, dropped-valid, unstable-data, and corrupt-data mutants are killed.
- Retained the bounded AHB-Lite cocotb/formal qualification, completing the
  Stage 7 APB4, AXI4-Lite, AHB-Lite, and paired-stream gate.
- The focused protocol regression passes 83 tests. The full instrumented suite
  passes 503 tests with four expected optional skips; combined coverage is
  86.09%, statement coverage is 89.03%, and true branch coverage is 78.06%
  across 5,506 branches. Every versioned coverage ratchet and static gate passes.
- Stage 7 is accepted and Stage 8 board-peripheral work is now active. The GA
  ledger has been expanded through Stage 13 so peripheral qualification cannot
  be bypassed by later language, vendor, pilot, or release evidence.

<a id="source-progressmd--2026-07-22-stage-8-board-peripheral-closure"></a>
### 2026-07-22 — Stage 8 board-peripheral closure

- Added strict, explicitly mapped depth profiles for an 8-bit UART controller,
  four-mode 8-bit SPI master, open-drain 7-bit I2C master, and a bounded
  GPIO/timer/watchdog/PWM/interrupt-controller subsystem. Incomplete directions,
  widths, domains, resets, parameters, or signal mappings fail closed.
- Generated cocotb BFMs, reference checks, coverage identities, timeouts, and
  formal safety/non-vacuity collateral for all four profiles. The I2C BFM models
  wired-AND drive-low/sample behavior, repeated START, ACK/NACK, stretching, and
  arbitration loss.
- Full CLI good-DUT paths close analyze, plan, generation, simulation, coverage,
  and strict status. Formal prove/cover paths pass on SBY/Yosys/Z3.
- Killed all 37 declared mutations: UART 10/10, SPI 9/9, I2C 8/8, and the
  combined GPIO subsystem 10/10. Generated UART bytes are reproducible.
- Full instrumented verification passes 515 tests with four expected optional
  skips. Combined coverage is 86.23%, statement coverage is 89.14%, and true
  branch coverage is 78.31% across 5,598 branches; all coverage ratchets, Ruff,
  formatting, mypy, repository-contract, and Stage 8 ledger gates pass.
- Stage 8 is accepted and Stage 9 VHDL/project-UVM closure is now active.

<a id="source-progressmd--2026-07-22-stage-9-vhdl-and-project-uvm-closure"></a>
### 2026-07-22 — Stage 9 VHDL and project-UVM closure

- Extended bounded VHDL normalization with fail-closed, directionally complete
  paired ready/valid recognition. Generated VHDL-2008 checks cover reset,
  acceptance, data integrity, backpressure stability, and recovery.
- The GHDL project path passes the good VHDL design, kills four mutations, closes
  exact native results and normalized coverage/status, and regenerates identical
  bytes.
- Added a generated-project Vivado Simulator runner that compiles interface,
  package, project RTL, and top in order; requires the named UVM test, zero
  errors/fatals, and a non-vacuous scoreboard; and emits exact per-trace results.
- The UVM CLI run path now closes validation-result v1 and normalized coverage.
  The checked-in Vivado Simulator 2025.2 attestation remains integrity-valid and
  bound to the current generated ready/valid UVM artifacts.
- Full instrumented verification passes 519 tests with four expected skips.
  Combined coverage is 86.22%, statement coverage is 89.14%, and true branch
  coverage is 78.27% across 5,634 branches. Static, ledger, secret, package, and
  coverage-ratchet gates pass.
- Stage 9 is accepted and Stage 10 semantic/scale/platform qualification is active.

<a id="source-progressmd--2026-07-22-broad-protocol-release-candidate-implementation"></a>
### 2026-07-22 — Broad-protocol release-candidate implementation

- Added versioned production profiles and fail-closed recognition for full AXI4,
  packet-complete AXI4-Stream, Wishbone B4, Avalon-MM/ST, burst-capable AHB, and
  non-coherent TileLink UL/UH, including aliases, roles, multiple instances,
  bounded bursts/outstanding transactions, ordering, errors, scoreboards,
  coverage bins, formal obligations, and exact traces.
- Added shared transaction/reference models and generated cocotb, formal,
  SystemVerilog, Verilog, declared VHDL, and multi-agent UVM/RAL collateral.
  Broad good-DUT CLI/native/formal runs pass; AXI4-Stream closes open-tool and
  VHDL packet mutations.
- Extended VHDL normalization through GHDL-authoritative packages, records,
  subtypes, arrays, generates, explicit architecture binding, and fail-closed
  cross-language manifests. Added bounded Cartesian parameter matrices with
  isolated provenance and coverage identities.
- Added SECDED correction, double-error detection, and scrub completion to the
  bounded SRAM profile; the good DUT and five mutants close under cocotb and
  formal.
- Added signed-plugin trust policies, rootless OCI sandbox contracts,
  license-aware scheduling, benchmark/evidence codecs, external-design and pilot
  schemas, backup/migration/governed destruction, and hardened release workflows
  with SBOM, checksums, SLSA provenance, signature verification, and private-index
  reinstall.
- Ran AMD Vivado Simulator 2025.2 through the WSL bridge against both the current
  ready/valid project and the portable generated-UVM qualification bundle. The
  current bundle compiles, elaborates, compares 16 transactions, reports zero
  UVM warnings/errors/fatals, and refreshes the byte-bound tamper-evident
  attestation. Independent signature is still required for the Stage 11 gate.
- Full verification passes 574 tests with four declared optional skips. Coverage
  is 85.31% combined, 88.35% statement, and 77.30% branch across 6,704 branches;
  all file/global ratchets pass. Ruff, formatting, mypy, repository/GA contracts,
  secret scanning, Bandit, dependency audit, reproducible builds, `twine check`,
  release-material verification, and installed-wheel smoke tests on Python
  3.11/3.12/3.13 pass.
- Exact 2-million-line RTL, 128 MiB XML, and 64 MiB PDF baseline/current pairs
  pass from the same clean commit and wheel on WSL2 and a native Ubuntu 24.04.4
  KVM guest. Both platform pairs remain within the 10% runtime/RSS gate. Stage 10
  is accepted; Stage 11 independently signed licensed-tool evidence is active.

<a id="source-progressmd--advanced-local-closure-after-stage-10"></a>
#### Advanced local closure after Stage 10

- Qualified explicit multi-bit handshake coherency and bounded-rate standalone
  Gray-counter CDC profiles. Generated cocotb and formal collateral passes the
  good DUT and kills corrupted-payload and non-Gray mutants.
- Extended reset/RDC depth with observable power-good, isolation, and retention
  sequencing. The combined generated matrix now kills nine reset, dependency,
  power, isolation, and retention mutants in cocotb and formal.
- Added RTL acceptance/completion mutants for AXI4, Wishbone B4, Avalon-MM,
  Avalon-ST, AHB, and TileLink; every broad profile now has hardware mutation
  evidence in addition to typed trace-model negatives.
- Added commit- and image-bound OCI runtime qualification. The checked probe
  verifies an unprivileged UID, network denial, read-only root/source mounts,
  isolated writable output, dropped capabilities, no-new-privileges, resource
  limits, and strict environment forwarding against Ubuntu 24.04.
- Expanded generated UVM functional coverage with bounded backpressure bins,
  protocol-specific burst/response/mask/routing/packet coverpoints, and governed
  cross coverage sampled by the generated monitors.
- Qualified explicit first-word-fall-through asynchronous FIFO intent. Cocotb
  samples the visible word before dequeue and kills a corrupt-head mutant;
  formal checks visible-head stability when neither endpoint advances and adds
  a non-vacuous show-ahead cover. Registered-read compatibility remains the
  default unless the policy opts into FWFT.
- Re-ran AMD Vivado Simulator/XSim 2025.2 build 6299465 through the WSL bridge
  against a fresh generated-UVM qualification bundle and a normal CLI-generated
  ready/valid UVM project. Both runs passed with zero UVM warnings, errors, or
  fatals; the project reconciled all three exact trace IDs and closed CI coverage.
  Wrapper-backed simulator summaries now classify the captured XSim banner as
  the configured `vivado_xsim` tool, allowing strict status to enforce the
  tested 2025.2 range instead of misclassifying the Python bridge executable.
