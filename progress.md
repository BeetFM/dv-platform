# Project Progress

This ledger records implementation work and validation evidence. Future
implementation updates must append an entry here.

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
- Added regression tests and [semantic-cross-check.md](semantic-cross-check.md).
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
