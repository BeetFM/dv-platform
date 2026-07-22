# Project Progress

This ledger records implementation work and validation evidence. Future
implementation updates must append an entry here.

## 2026-07-21 — Bounded synchronous memory acceptance

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

## 2026-07-21 — Stage 4 verification-depth completion

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

## 2026-07-21 — Bounded AXI4-Lite open-tool acceptance

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

## Current baseline

- P0/P1 local workflow exists: discovery, Verilator analysis, documentation
  indexing, evidence-backed planning, generation, execution, coverage, review,
  and CI status gating.
- Test-code generation exists for cocotb, formal, SystemVerilog, Verilog, VHDL,
  and UVM. Cocotb/formal and the supported protocol-backed UVM path are
  executable; several other targets remain conservative scaffolds.

## Completed semantic work

### Parameter sweeps

- Added explicit `parameter_sweeps` configuration and `--parameter-sweep` init
  arguments.
- Each elaboration point runs in an isolated work directory.
- Sweep-qualified module, plan, evidence, and provenance identities prevent
  cross-configuration result mixing.
- Validated with two real Verilator sweep points, six normalized modules, six
  plans, and cocotb generation.

### Branch and case semantics

- Normalized case selectors, labels, default branches, source locations, and
  plain-case exclusivity.
- `casez`/`casex` or incomplete case-item semantics remain unknown.
- Unknown matching semantics produce critical claims and block executable
  generation.

### Expression sizing and casting

- Normalized expression width and signedness from Verilator dtype evidence.
- Preserved literal widths and explicit cast kinds.
- Unresolved explicit casts produce critical generation claims.
- Unresolved arithmetic widths remain actionable open questions for conservative
  black-box generation.

## Validation baseline

- 317 tests pass; one optional real-tool test is skipped when unavailable.
- Ruff, formatting, mypy, package build, and dependency audit have passed in the
  current development baseline.
- Real Verilator pilot analysis passes.

## Remaining high-risk semantic gaps

- Full SystemVerilog sizing/casting rules across every operator.
- Packed aggregate operation semantics and complete interface/modport behavior.
- Package-qualified symbol resolution and generate conditions.
- Assertion and cover semantics.
- Broader CDC, reset, and memory behavior.

## Latest update — packed aggregate type facts

- Added structured member metadata for aggregate types: member dtype, width,
  signedness, packed range, and source location.
- Preserved this metadata in normalized RTL facts and plan persistence.
- Existing aggregate operations remain conservative; unsupported struct/union
  operations are not promoted to executable semantic closure.
- Added regression coverage using a packed struct fixture.
- Validation: 316 tests pass; Ruff, formatting, and mypy pass.

## Latest update — interface/modport directionality

- Added structured interface port facts: interface name, modport, and resolved
  direction.
- Persisted the facts in normalized RTL output and plan storage.
- Unresolved interface identity, modport, or direction creates a critical
  generation precondition rather than an inferred direction.
- Added an interface/modport normalization fixture.
- Validation: 317 tests pass; Ruff, formatting, and mypy pass.

## Status reconciliation — 2026-07-20

- Removed interface/modport directionality from the remaining-gap list because
  structured interface name, modport, and direction facts are implemented.
- Updated the validation baseline from 316 to 317 passing tests.

## Latest update — SystemVerilog cross-check contract

- Added a versioned `SemanticCrossChecker` contract and deterministic normalized
  fact comparator for independent frontends such as Slang or Surelog/UHDM.
- The comparator checks module/specialization identity, ports, parameters,
  hierarchy, aggregate type members, and interface/modport facts.
- Missing modules and disagreements are explicit, non-passing issues.
- Added regression tests and [semantic-cross-check.md](docs/semantic-cross-check.md).
- Local tooling check: Verilator is installed; Slang and Surelog/UHDM are not.
- Validation: 320 tests pass; focused cross-check tests, Ruff, formatting, and
  mypy pass.

## Latest update — Slang connection

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

## Latest update — Slang procedural and assignment facts

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

## 2026-07-20 — Staged Slang production integration

### Stage 1 — workflow integration

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

### Stage 2 — comparison contract

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

### Stages 3–6 — semantic facts

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

### Stage 7 — qualification

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

## 2026-07-20 — Qualification audit and semantic closure

This entry supersedes the validation and completeness claim immediately above.
The first implementation used presence-based capabilities and heuristic AST
node names; real Slang 11 JSON showed that properties, package types,
interfaces, memories, branches, and repeated hierarchy could be omitted while
appearing successful. Those gaps are now closed as follows.

### Stage 1

- Revalidated ordinary and parameter-sweep execution, command parity,
  artifacts, cache identity, `off`/`report`/`required` behavior, strict/CI
  enforcement, and downstream plan/generation gates.
- Required runs now require the entire qualified profile rather than only
  capabilities for which a non-empty fact list happened to exist.

### Stage 2

- Capability declarations now describe frontend support independently of
  construct presence. Unsupported AST nodes withdraw a capability with a
  source-located reason, so an incomplete empty view cannot pass.
- Canonical specialization values ignore frontend literal spelling and retain
  every distinct parameter specialization. Repeated generated instances use
  stable hierarchical names instead of insertion order.
- Replaced recursive whole-document tuple construction with an iterative walk.

### Stage 3

- Qualified real Slang nodes for literals, references, element/range selects,
  concatenation, replication, calls, unary/binary operations, implicit and
  explicit conversions, conditional expressions, procedural assignments,
  `if`, plain/wildcard cases, and source/type metadata.
- Verilator normalization now retains procedural assignments, `if` branches,
  `casez`/`casex` evidence, repeated generated instances, and nested
  sensitivity controls. Real fixtures cover synchronous and asynchronous reset
  domains.

### Stage 4

- Qualified immediate assert/cover and concurrent assert/cover facts, including
  clocking, edge, `disable iff`, implication, sequence delay, labels, and
  support state. Unsupported property nodes withdraw property capability and
  still create critical planning claims.
- Verilator 5's rejection or lowering-away of temporal structure is an expected
  fail-closed compatibility outcome, not a passing empty property set.

### Stage 5

- Added recursive layout resolution for enums, nested packed structs/unions,
  signed members, bit offsets, packed/unpacked dimensions, package aliases,
  interface arrays, multiple modports, and modport member directions.
- Added the new layout fields to RTL facts and plan persistence; RTL facts are
  schema 9 and plans are schema 15.

### Stage 6

- Preserved instance parameter bindings, port directions/connections,
  hierarchical generate iteration identity, source conditions, selected state,
  unpacked memory layout, and synchronous read/write address/data/enable facts.
- Slang omits inactive generate branches from elaborated JSON. A conservative
  source inventory now retains those scopes as `selected=false`; complex
  conditions fail the generate capability instead of disappearing.

### Stage 7

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

## 2026-07-20 — Roadmap Stages 0 and 1 closure

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

## 2026-07-21 — Roadmap Stages 2 and 3 closure

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

## 2026-07-21 — Roadmap Stage 4 structure qualification

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

## 2026-07-21 — Roadmap Stage 5 target and adapter implementation

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
recorded in [Stage 5 Acceptance](docs/stage5-acceptance.md).

## 2026-07-21 — GHDL 4.1 Stage 5 qualification closure

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

## 2026-07-21 — Vivado Simulator UVM qualification and Stage 5 closure

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

## 2026-07-22 — Broad-GA staging, foundation closure, and AHB-Lite qualification

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

## 2026-07-22 — Stage 7 on-chip buses and streams closure

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

## 2026-07-22 — Stage 8 board-peripheral closure

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

## 2026-07-22 — Stage 9 VHDL and project-UVM closure

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

## 2026-07-22 — Broad-protocol release-candidate implementation

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

### Advanced local closure after Stage 10

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
