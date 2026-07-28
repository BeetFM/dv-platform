# Missing Work and Tooling Inventory

Document type: current roadmap, regression register, and agent-ready backlog.

Authority: fresh repository evidence, machine contracts, the capability
matrix, and the ticket-specific source/test references in this document.

Status: current, with release-blocking P0 items.

This is the post-P1 repository rescan. Completed P0 guarantees are defined in
[P0 Pilot Acceptance](../acceptance/pilot-acceptance.md), and the broader implemented slice is
defined in [P1 Expansion Acceptance](../acceptance/p1-acceptance.md).

Last updated: 2026-07-28.

Repository rescan snapshot: 2026-07-27.

Agents must first read the [Agent Execution Guide](../agent-execution-guide.md).
Authors changing capability or acceptance claims must also follow the
[Documentation Contract](../documentation-contract.md). Historical acceptance
records establish what passed at their snapshots; they do not override a
current regression in this document.

## Current Baseline

The repository now has an end-to-end local workflow for discovery, PDF/text
indexing, specialization-aware RTL analysis, evidence-backed planning,
cocotb/native/UVM/formal generation, configured execution, per-check outcomes,
coverage import/gating, review, audit, and CI status. State is schema-versioned,
atomically published, content-hashed, and bound to analyzed inputs.

Plan schema v18 now separates typed executable scenarios from prose checks and
records renderer-backed `executable`, `scaffold`, or `unsupported` state for
each requested target. Legacy v16 scenario mappings are read conservatively as
unsupported until a fresh planning pass qualifies them through the shared
renderer registry.
Revision schema v3 stores additive operations and immutable resulting-plan
snapshots, and `generate --revision` reads the selected snapshot. Run summaries
share validation-result v1 and cannot turn a zero exit code with no measured
checks into closure. See the [capability matrix](../qualification/capability-matrix.md) for the
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

### 2026-07-27 rescan result

The latest working-tree rescan must not be represented as a passing baseline:

- `uv run python -m unittest discover -s tests` ran 585 tests in 566.755
  seconds and reported one failure and four skips. The skips were the opt-in
  live-AI provider smoke test plus three Slang tests because Slang was absent
  locally. GHDL, Icarus, Verilator, SBY, Yosys, and Z3 were installed.
- The failure is the SECDED formal good-DUT case in
  `GeneratedSecdedMemoryDepthPipelineTests`. Verilator CDC normalization treats
  synchronous top-level memory-contract inputs as unsafe `external` CDC paths,
  and fail-closed formal execution returns exit 16. See `BUG-CDC-01`.
- `scripts/checks/compatibility.py --check` fails because CLI, dataclass, and
  module fingerprints differ from the checked-in baseline.
- `scripts/checks/maintainability.py --check` fails because
  `configuration/validation.py` has 730 physical lines against a 700-line limit
  and `LiteLLMGateway.execute` has 90 code lines against a 75-line limit.
- `uv run mypy` reports two type errors in `ai/optimization.py` and
  `cli_handlers/dispatch.py`. `ruff format --check` reports eight files needing
  formatting. See `QUALITY-01`.
- Ruff lint, the secret scan, repository Markdown/CLI/schema contracts, the
  branch-policy tests, tool-policy tests, enterprise schema tests, and the Stage
  9 GA ledger check pass.

No new coverage percentage is claimed from this failing run. Release and
capability documents must continue to reference the last accepted evidence while
also exposing these current regressions.

## P1 Residuals

These are the remaining requirements before claiming broad language- and
tool-independent production use.

### Semantic completeness

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
  [compatibility matrix](../architecture/slang-compatibility-matrix.md).
- Widen the qualified GHDL version/platform matrix. Packages, records, subtypes,
  arrays, generate elaboration, explicit architecture binding, GHDL-authoritative
  VHDL-only semantics, and fail-closed mixed-language binding manifests are implemented.

### CDC, reset, and memory sign-off

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

### Protocol and transaction breadth

- Versioned AXI4, packet-complete AXI4-Stream, Wishbone B4, Avalon-MM/ST,
  burst-capable AHB, and non-coherent TileLink UL/UH transaction contracts and
  deterministic recognition are present. The capability matrix and protocol
  architecture document currently disagree on whether the bounded generated
  transaction slices are `supported` or remain `unsupported`; this must be
  reconciled by `DOC-00` before either document is used to promote a release
  claim. Existing bounded AXI4-Lite, APB4, AHB-Lite, and paired ready/valid
  qualification remains unchanged.
- Markdown tables, timing-diagram rows, register maps, cross-document evidence,
  conflicting values, performance/power intent, and coverage goals are extracted
  into evidence-addressed requirements. A governed OCR-sidecar adapter is
  connected; direct OCR engines remain deployment adapters.

### Production adapter validation

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

## P2 Expansion

### Coverage and reporting

- Extend beyond the implemented UCIS XML, LCOV, JSON, and Cobertura-style XML
  importers to native vendor databases and richer formal coverage APIs while
  preserving exclusions and governed dispositions.
- Extend the implemented SARIF, YAML, JSON, and Markdown reports with complete
  schema migration coverage and filtering by severity, confidence, target,
  module, source, evidence state, and check outcome.
- Generate functional covergroups/bins from richer protocol and requirement
  schemas rather than only importing functional totals produced elsewhere.

### Security and governance

- The threat model, export-root allowlist, secret-provider interface, publisher
  and package-hash checks, Sigstore/enterprise-PKI trust rules, rootless-aware OCI
  sandbox contract, release signing, and bounded retention/destruction controls
  are implemented. Checked-in runtime evidence executes an unprivileged Docker
  container with network denial, read-only roots/sources, isolated output,
  dropped capabilities, no-new-privileges, resource limits, and an environment
  allowlist. Rootless Podman remains a supported deployment variant, not a release gate.
- Extend the existing content-free AI run/audit records to every optional
  network adapter with normalized request purpose, destination, and policy
  decision fields.
- The purge command safely covers transient AI, audit, log, RAG, and support
  state. Define separately approved destruction workflows for release evidence,
  counterexamples, generated customer collateral, and backups; these are
  intentionally excluded from general retention purge.

### Incrementality and scale

- The implemented dependency graph spans document chunks and normalized facts
  through requirements, checks, scenarios, symbols, artifacts, runs, coverage,
  and reviews. Revision generation is artifact-selective.
- Extend the qualified 2-million-line RTL, 128 MiB XML, and 64 MiB PDF benchmark
  beyond Ubuntu 24.04/WSL2 and tune streaming/indexed parsing if future records
  approach the enforced runtime or RSS budgets.
- Extend bounded concurrency to analysis, indexing, planning, generation, and
  independent formal tasks with license-aware scheduling.
- Verify reproducibility across supported operating systems and EDA versions,
  not only repeated runs on one worker.

### Documentation and distribution

- Operator, RAG/index, backend/output, security/privacy, testing, support,
  upgrade, and rollback references are published and checked for internal links,
  CLI examples, schema versions, and capability-state vocabulary.
- Expand the published Linux/WSL support boundary into exact distribution/kernel
  ranges and qualified licensed-tool container images. Native Windows and macOS
  remain unsupported/best-effort.

## Product Plans and Entitlement Boundary

Product direction recorded on 2026-07-28 defines two plans: **Free** and
**Enterprise**. This section is the intended plan boundary, not a claim that
entitlement enforcement, packaging separation, or board-specific verification
is implemented. `TIER-01` and `BOARD-01` are the implementation work packages.

### Current implementation state

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

### Normative plan matrix

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

### Free plan contract

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

### Enterprise plan contract

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

### Enterprise board-specific verification contract

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

## Agent-Ready Backlog

This is the implementation queue. It converts documented limits into bounded
work packages that an agent can own without silently expanding a verification
claim. The [capability matrix](../qualification/capability-matrix.md) remains
the intended release authority once its conflict with the protocol architecture
document has been resolved.

### Zero-assumption pickup index

Use this index before reading ticket prose. `Ready` means an agent can begin
without a product decision; it does not mean dependencies or required tools are
already available. The "begin with" column is the first source or command to
inspect. The ticket body and ticket-level playbook remain mandatory.

| ID | Ready | Dependency or gate | Begin with | Completion signal |
| --- | --- | --- | --- | --- |
| `BUG-CDC-01` | yes | none; highest-priority code defect | Reproduce `tests.integration.test_memory_depth_pipeline.GeneratedSecdedMemoryDepthPipelineTests.test_generated_formal_passes_good_dut_and_kills_secded_mutants`; inspect `src/dv_platform/rtl/verilator/hierarchy.py::_cdc_paths` | SECDED good DUT and five mutants close; unknown/asynchronous external-input negative cases still block |
| `QUALITY-01` | yes | preserve unrelated user changes; review compatibility deltas | Run compatibility, maintainability, mypy, Ruff lint/format, then inspect the exact failures listed in the ticket | Every mandatory quality command and affected test passes without weakened policy or blind fingerprint replacement |
| `DOC-00` | yes, evidence review | actual profile fixtures and CI evidence | Compare `docs/qualification/capability-matrix.md` with `docs/architecture/protocol-profiles.md` profile by profile and target by target | One evidence-backed state per broad-profile target; strict status and current docs agree |
| `DOC-02` | partially | `BUG-CDC-01` for current SECDED state; `DOC-00` for broad protocols | Classify each conflicting document listed in the ticket using `docs/documentation-contract.md` | Current authorities agree with a machine ledger; historical snapshots are dated/linked; a deliberate contradiction test fails |
| `DOC-03` | yes | preserve historical wording; coordinate machine capability state with `DOC-02` | Inspect `scripts/checks/repository_contracts.py`; inventory every root, `docs/`, and `qualification/` Markdown file | Versioned document catalog covers every file; required metadata and command families are checked; malformed catalog/metadata/commands fail fixtures |
| `TIER-01` | partially | product direction is fixed; entitlement issuer, private package, and offline policy need owner approval | Inspect `pyproject.toml`, `src/dv_platform/enterprise/`, CLI configuration/models, plugin loading, and status policy | Free works without entitlement; every Enterprise entry point fails closed without a valid grant; plan/capability state is visible and tested |
| `BOARD-01` | contract work yes; vendor promotion no | `TIER-01`; one legal board fixture; qualified Vivado/other EDA evidence; physical scope remains gated by `PHYS-01` | Stage 8 peripheral contracts, enterprise adapters, constraints/tool profiles, and proposed `enterprise-board-v1` schema | One board/revision closes manifest, mapping, generated harness, XSim/vendor execution, exact results/coverage, and board-specific mutants |
| `SEM-01` | yes, one slice only | choose one unsupported semantic family | `src/dv_platform/rtl/semantic_manifest.py`, normalized RTL schemas, frontend cross-check fixtures | One versioned semantic slice has migration, positive/negative/ambiguity fixtures, real frontend evidence, and fail-closed target gating |
| `SEM-02` | no external semantics yet | governed mixed-language elaborator and binding manifest | Existing `cross-language-bindings-v1` schema and `analysis.bindings` validation | External elaboration manifest reaches one target; wrong/ambiguous binding cases reject without inferred mappings |
| `SEM-03` | yes if tools/design licenses available | qualified Verilator/Slang/GHDL versions and licensed external fixtures | Existing compatibility matrices and `qualification/external-designs/` | Version matrix records hashes/diagnostics/resources; unqualified versions fail closed in strict mode |
| `FORM-01` | yes, one extension only | explicit product choice among the ticket's four semantic extensions | Formal scenario model, validation, harness generation, SBY task builder, result decoder | Typed policy, deterministic proof/cover, non-vacuity witness, killed mutant, and unsupported-engine result |
| `CDC-01` | yes after `BUG-CDC-01` | select exactly one advanced CDC profile | CDC policy schema, normalized CDC facts, cocotb/formal CDC generation | Good DUT, structural negative, per-rule mutants, path classification, and non-closing ambiguity |
| `RDC-01` | no without evidence | licensed physical/reset tool and legal fixture | Qualification/adaptor contracts plus existing logical RDC profile | Imported physical findings retain rule/source/tool identity; stale evidence rejects; physical failures cannot close logically |
| `MEM-01` | blocked | close or explicitly downgrade `BUG-CDC-01`; select one behavior | Memory policy/fact/scenario contracts and memory-depth pipeline tests | Policy rejection cases, good DUT, behavior mutant, exact coverage/non-vacuity, and no inferred memory intent |
| `PROTO-01` | blocked | `DOC-00`; then one profile, role, bound, and target | Broad protocol catalog, recognizer, renderer registry, decoder, and matching fixtures | Per-target good-DUT/mutation/coverage closure; every other target remains explicitly partial/scaffold/unsupported |
| `PROTO-02` | yes, one feature only | preserve current APB4/AXI4-Lite/AHB-Lite/ready-valid behavior | Existing bounded profile schema and qualification fixture for the selected protocol | Migrated contract plus good-DUT and mutant closure on each newly claimed backend |
| `PERIPH-01` | yes, one feature only | electrical behavior requires `PHYS-01` decision/evidence | Stage 8 profile and qualification tests for UART, SPI, I2C, or GPIO/timer/interrupt | Trace, scoreboard, bins, exact checks, feature mutants, and regression of the old bounded profile |
| `VHDL-01` | yes, one profile only | qualified GHDL; mixed-language work depends on `SEM-02` | Native VHDL renderer/executor and Stage 9 VHDL qualification tests | GHDL analysis/elaboration/run, good/bad fixtures, canonical trace identity, preserved VHDL source evidence |
| `UVM-01` | contract work yes; promotion no | licensed simulator and independently signed evidence for support promotion | UVM scenario/rendering contracts and enterprise qualification importer | Rich profile is self-checking; signed vendor run maps exact checks/coverage; mocks remain contract-only |
| `TOOL-01` | contract work yes; qualification no | licensed tool, legal fixture, trusted execution environment | Enterprise adapter API, sandbox policy, tool policy, result normalization | Structured adapter results, timeout/license/malformed-report failures, real signed evidence, no shell interpolation |
| `COV-01` | yes for one format | representative native database/export and version policy | Coverage-v3 schema, importer registry, closure/status policy | Imported stable points preserve exclusions/dispositions; partial/unknown/stale data cannot close |
| `COV-02` | yes for one typed intent family | selected protocol/requirement schema | Scenario coverage goals, renderer, trace/coverage ID mapping | Deterministic bins, reachable-hit and mutant-miss tests, zero-denominator/ignored-bin handling |
| `DOC-01` | yes for adapter contract | selected OCR or local retrieval implementation; network must remain explicit | Document-ingestion adapter interfaces, source locator model, RAG operations guide | Deterministic indexed chunks/locators, corrupt/encrypted/rotated/duplicate tests, no implicit network |
| `SCALE-01` | yes for one platform/scheduler slice | representative benchmark and resource budget | Stage 10 scale records, performance schemas/scripts, scheduler | Repeated measured record meets budgets; interruption/concurrency/cache identity are tested |
| `PLAT-01` | yes for documentation/CI slice | exact OS/kernel/container/tool tuple | Installation docs, CI matrix, platform qualification records | Published support table has exact versions, real smoke evidence, and explicit unsupported/best-effort behavior |
| `AI-01` | no | explicit product/security approval | AI boundary in README, gateway contracts, audit/security docs | Decision recorded in ADR/policy; only then implement bounded authority with deterministic validation and audit |
| `AI-02` | no | explicit product/security approval | Gateway provider selection, privacy/network policy, audit model | Decision recorded; routing/fallback cannot silently change provider, destination, model, or data policy |
| `PHYS-01` | no | explicit product boundary plus licensed physical evidence | Logical CDC/RDC/memory boundary, enterprise adapter contract, security policy | Decision defines delegated sign-off, evidence levels, stale/waiver rules, and release gating |

Pickup rules:

1. Work P0 issues before capability expansion unless the user explicitly assigns
   a different ticket.
2. Pick one row. Do not combine unrelated IDs to manufacture a broad "cleanup".
3. Treat `no` and `blocked` as stop states unless the task explicitly resolves
   the listed dependency.
4. Read both the summary ticket and its later technical playbook before editing.
5. Use the common completion contract below in addition to the row's completion
   signal.
6. At handoff, update the row only if readiness, dependency, entry point, or
   completion state actually changed; never mark completion from generated
   collateral or unit tests alone.

### Common completion contract

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

An agent should split an item if it cannot identify a single profile, target,
semantic contract, and acceptance fixture set. A renderer, generated file, or
zero tool exit code is never by itself completion evidence.

### P0: release blockers and claim reconciliation

#### `DOC-00` Reconcile broad-protocol capability claims

**Status:** blocking documentation defect. **Priority:** P0. **Depends on:**
maintainers reviewing the actual accepted fixtures and CI jobs.

**Current condition:** [the capability matrix](../qualification/capability-matrix.md)
labels bounded broad-protocol transaction contracts as supported, while
[the protocol architecture](../architecture/protocol-profiles.md) says their
drivers, monitors, scoreboards, properties, decoders, mutation matrices, and
external-design evidence remain required before execution can move beyond
`unsupported`. The two documents cannot both describe the same release state.

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

#### `BUG-CDC-01` Stop synchronous external inputs becoming false CDC blockers

**Status:** reproduced release-blocking defect. **Priority:** P0. **Observed
with:** Verilator 5.020, SBY 0.67, Yosys 0.33, and Z3 4.8.12.

**Current condition:** the SECDED memory formal good-DUT pipeline fails before
it can qualify the claimed memory behavior. `_cdc_paths()` in
`rtl/verilator/hierarchy.py` places every top-level input that is not written by
the module and is not a clock/reset into a synthetic `external` source domain.
Any sequential process that reads such an input receives a `direct`, zero/one
stage, unsafe `RTLCDCPath`. For the bounded SECDED fixture this incorrectly
classifies `read_enable`, `read_address`, `inject_single_error`,
`inject_double_error`, and `scrub_enable` as unsafe CDC crossings even though
the explicit memory policy associates those interface controls with `clk`.
`formal/generation/cdc.py` correctly reports those unsafe paths as unsupported,
so `formal/execution.py` keeps CDC closure false and the good DUT exits 16.

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

#### `QUALITY-01` Restore all mandatory CI quality gates

**Status:** reproduced release-blocking quality regression. **Priority:** P0.

**Current condition:** the same commands used by the `quality-and-pilot` CI job
currently fail in four areas:

- Compatibility fingerprints changed for the CLI, dataclasses, and modules.
- `configuration/validation.py` exceeds the 700-line module limit by 30 lines.
- `LiteLLMGateway.execute` exceeds the 75-code-line function limit by 15 lines.
- Mypy reports an unsafe `int(object)` conversion in `ai/optimization.py` and a
  tuple-width inference conflict for `lines` in `cli_handlers/dispatch.py`.
- Ruff formatting would change eight source/test files.

**Work package:** restore these gates without weakening their policies. Review
the public compatibility delta against the last accepted release or baseline;
add compatibility shims or a governed version change for intentional breaking
changes. Split configuration validation by concern while preserving public
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

#### `DOC-02` Reconcile stale acceptance and production-readiness claims

**Status:** confirmed documentation-governance defect. **Priority:** P0.

**Current condition:** repository link/schema checks pass while multiple
documents make incompatible semantic claims:

- `architecture/protocol-profiles.md` says broad profiles are not executable;
  the capability matrix says their bounded generated transaction contracts are
  supported.
- APB4 and AXI4-Lite acceptance documents say native SystemVerilog remains a
  scaffold; the capability matrix says native SystemVerilog and Verilog are
  qualified for both bounded profiles.
- `stage5-acceptance.md` says native execution is reset-only and explicitly
  excludes APB4/AXI4-Lite, while later acceptance and the matrix claim more.
- `memory-depth-acceptance.md` says SECDED correction/scrub are unsupported; the
  matrix claims cocotb/formal SECDED mutation closure. The current
  `BUG-CDC-01` failure means this claim must be revalidated, not merely edited.
- `verification-production-readiness.md` says board peripherals remain Stage 8
  work even though `qualification/stages/stage8-board-peripherals.md` is
  accepted.
- `vhdl-normalization-acceptance.md` says packages, records, subtypes, and
  generate elaboration remain open; Stage 9 records those as subsequent Stage
  10 additions.

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

### P1: documentation operability and enforcement

#### `DOC-03` Make every document machine-classified and agent-operable

**Status:** confirmed documentation infrastructure gap. **Priority:** P1.
**Depends on:** use `DOC-02`'s capability ledger rather than creating a second
source for capability state.

**Current condition:** the 2026-07-27 metadata scan found 44 Markdown files
under `docs/` and `qualification/` without an explicit document type, status,
snapshot date, or last-reviewed date in their first 16 lines. The central
[Documentation Contract](../documentation-contract.md), [Documentation
Index](../README.md), [Agent Execution Guide](../agent-execution-guide.md), and
directory indexes now explain how to interpret them, but this classification
is not machine-enforced.

`scripts/checks/repository_contracts.py` currently:

- scans root `*.md` and `docs/**/*.md`, but omits
  `qualification/**/*.md`;
- validates relative link existence but not duplicate/missing catalog entries,
  anchors, authority, supersession, snapshot scope, or known issue IDs;
- parses `dv-platform` examples, but does not parse `dv-enterprise`, repository
  maintenance scripts, qualification scripts, or commands containing pipes;
- checks schema filename/constant agreement and three schema strings in the
  capability matrix, but not the schema/profile version named by each document;
- accepts a capability row when any cell starts with a recognized state token;
  it does not compare profile IDs, targets, states, evidence paths, or snapshot
  identities across current documents.

This means link-valid prose can remain contradictory, a historical record can
look current, and an invalid non-`dv-platform` command can pass CI. The
incomplete performance command found during this rescan is an example; it was
corrected in `qualification/README.md`, but the checker would not have caught
it.

**Required behavior:** every maintained Markdown document must be discoverable
through one versioned catalog and have enough explicit metadata for an agent to
determine class, authority, scope, status, time boundary, successor, and known
issues without interpreting prose. CI must reject uncataloged files, stale or
invalid metadata, unresolved current-authority contradictions, and parser-
invalid command examples for governed command families.

**Work package:**

1. Add `schemas/documentation/document-catalog-v1.schema.json`. Define:
   `schema_version`, `documents[]`, unique repository-relative `path`,
   `document_type`, `authority`, `scope`, `status`, `snapshot_date` or
   `last_reviewed`, `supersedes`, `superseded_by`, `known_issues`, and optional
   `capability_ids`, `schema_ids`, `command_families`, and `evidence_paths`.
   Reject absolute paths, `..`, duplicate paths/IDs, unknown enum values, and
   unknown fields.
2. Add `docs/document-catalog-v1.json` and inventory root README files,
   `docs/**/*.md`, and `qualification/**/*.md`. Explicitly exclude generated
   build/output trees. Every maintained Markdown path must appear exactly once,
   and every catalog path must exist as a regular file inside the repository.
3. Migrate document headers by class using
   `docs/documentation-contract.md`. Preserve historical acceptance semantics:
   add metadata and later-change links without rewriting the original accepted
   boundary. Current authorities must name their machine contract and known
   regressions.
4. Refactor `scripts/checks/repository_contracts.py` into focused checks for
   inventory/catalog, metadata, links/anchors, schemas, capability claims, and
   commands. Include `qualification/**/*.md`; emit deterministic
   `path: field: reason` diagnostics and return nonzero for any error.
5. Validate local anchors after GitHub-style heading normalization, including
   repeated headings, punctuation, inline code, Unicode, and explicit HTML
   anchors. External URLs remain outside the offline check unless a separate
   opt-in network checker is approved.
6. Add parser-only validation for `dv-platform` and `dv-enterprise`. For
   repository Python scripts, define a side-effect-free parser import or
   `--help` contract rather than executing documented operations. Parse logical
   multiline commands, environment-variable prefixes, redirections, and
   pipelines into safe command segments. Do not execute arbitrary Markdown
   shell text.
7. Connect the catalog's `capability_ids` to the machine-readable
   profile/target/evidence ledger from `DOC-02`. A current document may describe
   a state only if the ID and state agree. A historical document must carry its
   snapshot and may differ only when it links the later promotion/regression.
8. Validate `known_issues` against IDs in this backlog. Reject unknown IDs;
   permit closed IDs only with a retained historical annotation or a current
   reason.
9. Generate or check the main documentation index and directory indexes from
   catalog entries so new files cannot become undiscoverable. Generated output
   must be deterministic and checked in with a `--check` mode.
10. Add unit fixtures for every failure class and run the checker in mandatory
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

**Acceptance evidence:** all maintained Markdown files are cataloged exactly
once; every current/historical document has valid class-specific metadata;
`qualification/**/*.md` and governed command families are checked; generated
indexes are byte-stable; and negative fixtures for missing metadata, duplicate
paths, path escapes, invalid anchors, unknown issue IDs, stale capability
states, malformed commands, and unmarked negative examples all fail with exact
diagnostics.

**Non-goals:** do not perform network link crawling in mandatory offline CI; do
not rewrite historical conclusions; do not execute shell snippets to validate
them; do not create a second independent capability-state source.

### P1: product plans and enterprise board verification

#### `TIER-01` Implement and enforce Free and Enterprise plans

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

#### `BOARD-01` Implement Enterprise board-specific digital verification

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

### P1: semantic authority and language completeness

#### `SEM-01` Extend normalized SystemVerilog semantics

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

#### `SEM-02` Qualify mixed-language elaboration

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

#### `SEM-03` Broaden frontend and external-design qualification

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

### P1: formal, CDC, reset, and memory depth

#### `FORM-01` Add one formal semantic extension beyond `bounded_response`

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

#### `CDC-01` Add one advanced CDC profile

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

#### `RDC-01` Integrate physical reset and power evidence

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

#### `MEM-01` Promote one unsupported memory behavior

**Current boundary:** qualified SRAM is a declared synchronous profile with one
read port, two write requesters, byte enables, declared collision/zero-init/
round-robin policy, and parity or SECDED/scrub mappings. Initialization files,
asynchronous or wider/more-port memories, retention, macro timing, and repair
remain outside that profile. The SECDED formal target is currently regressed by
`BUG-CDC-01`; do not begin a new memory-profile expansion until the existing
claim passes again or is explicitly downgraded.

**Work package:** choose one behavior only. Define policy fields and input
evidence, extend memory fact extraction, validate observable signal/domain
mapping, create target-specific scoreboards/properties, and define when a check
is simulation-only, bounded formal, or delegated to a physical adapter.

**Acceptance evidence:** positive policy fixture; missing/contradictory policy
rejection; at least one behavior-specific mutant; exact coverage points and
non-vacuity evidence. **Non-goal:** inferring collision, initialization, or ECC
policy from signal names.

### P1: protocol, peripheral, and target breadth

#### `PROTO-01` Resolve and qualify broad transaction profiles

**Status:** blocked by `DOC-00` for exact current state. **Scope:** AXI4,
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

#### `PROTO-02` Extend existing bounded protocol profiles

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

#### `PERIPH-01` Extend board-peripheral profiles one capability at a time

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

#### `VHDL-01` Extend native VHDL execution

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

#### `UVM-01` Qualify richer generated UVM environments

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

### P2: adapters, coverage, scale, and deployment

#### `TOOL-01` Add one commercial formal or simulation adapter

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

#### `COV-01` Import native vendor coverage and formal coverage

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

#### `COV-02` Generate functional coverage from typed intent

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

#### `DOC-01` Add direct OCR and local retrieval adapters

**Current boundary:** an OCR-sidecar and built-in local adapters are governed;
direct OCR engines and larger semantic embedding/vector backends remain
deployment integrations.

**Work package:** independently select an approved OCR engine and a local
embedding/vector implementation. Define file-type limits, source provenance,
content handling, confidentiality controls, index/cache identity, invalidation,
tool-version recording, error behavior, and export policy. Treat extracted text
as evidence, never as authoritative instructions.

**Acceptance evidence:** scanned-document, malformed-input, changed-source,
offline, permission-denied, and prompt-injection-like content fixtures; no raw
secret or provider content may enter audit records.

#### `SCALE-01` Qualify repository scale and scheduling

**Current boundary:** a bounded benchmark exists for one Linux/WSL-oriented
environment. Broader operating-system/tool-version reproducibility and
license-aware orchestration remain unqualified.

**Work package:** publish input-size, runtime, memory, concurrency, and cache
budgets; expand the benchmark matrix; add bounded scheduling for analysis,
indexing, planning, generation, and independent formal tasks with license and
memory constraints. Preserve deterministic ordering and cancellation behavior.

**Acceptance evidence:** measured benchmark reports in CI, budget regressions
that fail predictably, deterministic repeated outputs, and no oversubscription
of declared formal/license resources.

#### `PLAT-01` Define supported deployment platforms

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

### Product/security decisions: blocked until explicitly approved

These are deliberate governance boundaries, not bugs an agent should remove.
Any implementation starts only after a product/security owner approves the
stated decision and a versioned qualification plan exists.

#### `AI-01` Decide whether AI may author executable artifacts

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

#### `AI-02` Decide whether to support multi-provider routing/fallback

**Current boundary:** one configured LiteLLM model is used with bounded same-
model repair and deterministic fallback; cross-provider routing is unsupported.

**Decision package:** define eligibility order, data residency, credential
isolation, endpoint allowlists, model/version pinning, retry and cost limits,
cache keys, audit fields, outage behavior, and how proposal equivalence is
validated across models. Do not route prompts to an additional provider merely
because the first request fails.

#### `PHYS-01` Decide the physical-sign-off integration boundary

**Current boundary:** analog/mixed-signal, power intent, gate-level timing,
emulation, FPGA prototype coverage, analog electrical behavior, and physical
macro timing are not platform sign-off claims.

**Decision package:** for each desired domain, select an external tool and
define the normalized evidence needed for release: inputs, constraints,
versions, violations, waivers, source/domain identities, result retention, and
relationship to logical simulation/formal closure. A green logical run must
never mask missing physical sign-off evidence.

## Backlog operating rules

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

## Technical Implementation Guide

This section maps backlog items to the current codebase and supplies the
implementation sequence and edge-case policy agents should follow. Python
package paths are relative to `src/dv_platform/`; schema, test, fixture, and
documentation paths are repository-relative. The path list is a starting
ownership map, not permission to change every listed module in one patch.

### Source ownership map

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
| Documentation/retrieval | `analysis/docs.py`, `documentation/indexing.py`, `enterprise/builtin_adapters.py` | `tests/documentation/test_docs.py`, `tests/enterprise/test_builtin_adapters.py`, `tests/fixtures/docs/` |
| AI | `ai/gateway.py`, `ai/model_client.py`, `ai/planning/`, `ai/feedback.py`, `ai/scenarios.py`, `ai/runtime.py` | `tests/ai/`, especially proposal, gateway, smoke, and context-optimization tests |
| Scale/platform | `enterprise/benchmark.py`, `execution/simulation/process.py`, `cli_handlers/commands/run.py`, `core/sandbox.py`, `core/tool_versions.py` | `tests/enterprise/test_benchmark_runner.py`, `tests/execution/test_sandbox.py`, `tests/infrastructure/test_tool_versions.py` |
| Repository quality/public compatibility | `scripts/checks/compatibility.py`, `scripts/checks/maintainability.py`, `docs/compatibility/baseline.json`, `configuration/validation.py`, `ai/gateway.py` | `.github/workflows/ci.yml`, `tests/repository/`, full unittest/mypy/Ruff checks |
| Capability documentation governance | `scripts/checks/repository_contracts.py`, `docs/qualification/capability-matrix.md`, `docs/acceptance/`, `qualification/stages/` | `tests/repository/test_repository_contracts.py`, deliberate contradiction fixtures to be added |

### Standard implementation sequence

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

### Cross-cutting edge-case policy

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

### Ticket-level implementation playbooks

The following steps refine the work packages above. They are intentionally
specific about extension points and the edge cases most likely to produce a
false verification claim.

#### `DOC-00` technical steps and edge cases

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

#### `BUG-CDC-01` technical steps and edge cases

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

#### `QUALITY-01` technical steps and edge cases

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
   `docs/compatibility/baseline.json` only after review of the normalized delta.
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

#### `DOC-02` technical steps and edge cases

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
- A current regression such as `BUG-CDC-01` must be representable as
  `regressed` or as a blocking qualification status without erasing the last
  accepted evidence. Release policy must refuse promotion while regressed.
- An acceptance document with a passing mocked/unit path but no real-tool
  evidence cannot promote a real-tool target.
- A test count can change through added negative tests without changing product
  support. Counts are audit metadata, not capability evidence.

#### `DOC-03` technical steps and edge cases

1. Capture the current document inventory with root, `docs/**/*.md`, and
   `qualification/**/*.md` included. Save expected exclusions in code rather
   than relying on shell globs that silently omit a new tree.
2. Implement and test the catalog JSON schema before writing the catalog. Use a
   closed schema and stable enums from the Documentation Contract.
3. Populate catalog records one document class at a time: current authorities,
   operations, architecture, ADRs, roadmap, historical acceptance, stage
   evidence, then indexes. Run link checks after every class.
4. Add metadata to documents without changing historical claim text. Record
   unresolved state conflicts as `known_issues` and choose the conservative
   current state.
5. Split repository checking into pure functions that accept a root path so
   temporary fixture repositories can exercise missing, duplicate, malformed,
   escaped, stale, and contradictory cases.
6. Reuse actual CLI parser builders. Add side-effect-free parser access for
   `dv-enterprise` and governed Python scripts before validating their examples.
7. Parse command fences structurally. Treat pipelines/redirections as command
   composition, not a reason to skip all validation; validate only known command
   segments and never execute them.
8. Add a deterministic index renderer/checker. Ensure repeated runs produce
   identical bytes and sort by explicit category/order plus path.
9. Add CI checks and update the documentation author workflow, pull-request
   checklist, and agent handoff requirements.
10. Re-run all repository contracts and inspect the generated diff for
    accidental historical rewrites.

Edge-case resolution:

- **Catalog/document disagreement:** fail and print both values; do not select
  one silently.
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
- **Performance:** parse/catalog all maintained Markdown within the
  maintainability budget; avoid invoking subprocesses per fence.

Required tests:

- schema round-trip and closed-schema rejection;
- complete inventory and exact-once catalog coverage;
- missing/duplicate/case-colliding/path-escape/symlink records;
- class-specific metadata and date validation;
- valid/invalid relative links and normalized anchors;
- `dv-platform`, `dv-enterprise`, maintenance, qualification, pipeline, and
  negative command examples;
- current and historical capability-state consistency;
- known/unknown backlog references;
- deterministic index output and `--check` behavior.

#### `TIER-01` technical steps and edge cases

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

#### `BOARD-01` technical steps and edge cases

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

#### `SEM-01` technical steps and edge cases

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

#### `SEM-02` technical steps and edge cases

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

#### `SEM-03` technical steps and edge cases

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

#### `FORM-01` technical steps and edge cases

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

#### `CDC-01` technical steps and edge cases

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

#### `RDC-01` technical steps and edge cases

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

#### `MEM-01` technical steps and edge cases

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

#### `PROTO-01` and `PROTO-02` technical steps and edge cases

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

#### `PERIPH-01` technical steps and edge cases

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

#### `VHDL-01` technical steps and edge cases

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

#### `UVM-01` technical steps and edge cases

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

#### `TOOL-01` technical steps and edge cases

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

#### `COV-01` and `COV-02` technical steps and edge cases

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

#### `DOC-01` technical steps and edge cases

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

#### `SCALE-01` technical steps and edge cases

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

#### `PLAT-01` technical steps and edge cases

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

#### `AI-01`, `AI-02`, and `PHYS-01` conditional implementation notes

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

## Tooling Needed for the Residual Work

| Tool or capability | Backlog items | Required use and qualification evidence |
| --- | --- | --- |
| Existing qualified Verilator/Icarus/SBY/Yosys/Z3 toolchain | `BUG-CDC-01`, `QUALITY-01` | Reproduce and close the current SECDED formal regression on the exact accepted versions; retain the full good-DUT/mutant summaries and strict-status evidence. No new license is required. |
| Last released wheel/tag and normalized compatibility manifest | `QUALITY-01` | Identify the exact CLI/dataclass/module compatibility delta before restoring or intentionally versioning the public contract. A digest-only baseline cannot explain the change. |
| Versioned capability/evidence ledger | `DOC-00`, `DOC-02` | Provide one machine-readable profile/role/target/bound/state/evidence authority and drive semantic repository-document checks. |
| Versioned document catalog and parser-based documentation checker | `DOC-03` | Inventory every maintained Markdown file, enforce class/status/date/authority metadata, validate governed command families without execution, generate indexes deterministically, and reject semantic drift against the capability ledger. |
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
| Profiling hosts, CI capacity, and representative repository fixtures | `SEM-03`, `SCALE-01`, `PLAT-01` | Measure runtime, memory, cache behavior, concurrency, tool versions, and reproducibility within published budgets across each supported platform. |

## Recommended Order

1. Fix `BUG-CDC-01` first and rerun the SECDED good-DUT/mutant formal matrix.
   Until that passes, the current formal SECDED claim is regressed and must not
   be used as fresh release evidence.
2. Restore `QUALITY-01` in the same release-blocking tranche. Review
   compatibility changes before updating fingerprints, refactor the two
   maintainability violations, fix both mypy errors, format the reported files,
   and require one clean full CI-equivalent run.
3. Close `DOC-00` and `DOC-02` from actual post-fix evidence. Preserve the more
   conservative state for release claims where broad protocol, native,
   SECDED, peripheral, or VHDL documents disagree.
4. Implement `TIER-01` after stable capability IDs exist. Preserve the
   account-free Free open-tool workflow, split Enterprise packaging, and gate
   every enterprise adapter/qualification/board entry point before side
   effects. In parallel, complete `DOC-03` against the same capability ledger.
5. Select a single P1 semantic or formal slice (`SEM-01`, `FORM-01`, `CDC-01`,
   `MEM-01`, or `PROTO-02`) with an available good-DUT/mutant fixture and open
   tooling. Complete its full common completion contract before starting the
   next slice.
6. In parallel only where licenses and owners allow, establish the missing
   evidence adapters: mixed-language manifest production (`SEM-02`), a licensed
   simulator/formal adapter (`TOOL-01`), and vendor coverage import (`COV-01`).
   Adapter work must not claim support for a feature it has not executed.
7. Start `BOARD-01` only after `TIER-01` gates and the selected vendor adapter
   work. Close one exact legal reference-board revision through board manifest,
   XSim/vendor execution, mutations, coverage, and strict status before adding
   more boards, devices, or physical claims.
8. Run the enterprise pilots against the exact release-candidate wheel after
   their relevant target profiles have per-check execution, provenance, coverage
   reconciliation, and strict-status evidence. Import independently signed
   licensed-tool evidence for UVM, simulator, formal, CDC/RDC, and coverage
   bundles before promotion.
9. Take `AI-01`, `AI-02`, and `PHYS-01` to product/security owners as explicit
   decisions. Keep model-authored code, cross-provider routing, and physical
   sign-off integrations fail-closed until a versioned decision package and
   acceptance plan exist.
10. Schedule P2 scale, platform, OCR/retrieval, and broader database work only
   after the selected P1 profiles are reproducible and the required external
   tool evidence can be retained in CI or a governed evidence store.
