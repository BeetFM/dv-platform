# Missing Work and Tooling Inventory

This is the post-P1 repository rescan. Completed P0 guarantees are defined in
[P0 Pilot Acceptance](pilot-acceptance.md), and the broader implemented slice is
defined in [P1 Expansion Acceptance](p1-acceptance.md).

Snapshot date: 2026-07-19.

## Current Baseline

The repository now has an end-to-end local workflow for discovery, PDF/text
indexing, specialization-aware RTL analysis, evidence-backed planning,
cocotb/native/UVM/formal generation, configured execution, per-check outcomes,
coverage import/gating, review, audit, and CI status. State is schema-versioned,
atomically published, content-hashed, and bound to analyzed inputs.

The automated suite covers the Python contract plus optional real-tool
integration. Hosted CI makes the pilot Verilator, Icarus/cocotb, and open formal
paths mandatory. See the acceptance documents for exact guarantees; the items
below are the remaining gaps, not limitations hidden by a success result.

## P1 Residuals

These are the remaining requirements before claiming broad language- and
tool-independent production use.

### Semantic completeness

- Normalize full branch/case meaning, casting and sizing rules, packed aggregate
  operations, interface/modport directionality, package-qualified resolution,
  generate conditions, and assertion semantics rather than only preserving
  structured facts and evidence.
- Add expression evaluation across a matrix of configurations. Explicit bounded
  parameter sweeps now run as isolated Verilator analyses with unique plan and
  provenance identities; automatic Cartesian-product discovery and cross-point
  coverage aggregation remain open.
- Cross-check difficult SystemVerilog constructs with Slang or Surelog/UHDM and
  add compatibility fixtures for every supported Verilator release.
- Add VHDL-first entity/generic/architecture normalization rather than treating
  VHDL primarily as a generation and validation target.

### CDC, reset, and memory sign-off

- Recognize async FIFOs, pulse/toggle synchronizers, gray counters, handshake
  crossings, reconvergence, and multi-bit coherency. Linear two-flop chains now
  have fail-closed, bounded non-closing, and observable structural-proof tiers;
  the remaining schemes still require dedicated semantics and properties.
- Model reset-domain dependencies, ordered release, reset crossings, and
  recovery/removal intent.
- Infer or configure read-during-write policy, byte enables, multi-port
  arbitration, ECC/parity, and memory initialization; generate matching
  simulation reference models and scoreboards.
- Add property-specific formal assumptions, induction invariants, liveness, and
  assumption-consistency checks for these structures.

### Protocol and transaction breadth

- Add versioned schemas and executable models for AXI/APB/AHB, TileLink,
  Wishbone, interrupts, register maps, and project-specific request/response
  transactions.
- Support multiple agents/channels, ordering IDs, retries/errors, latency and
  throughput limits, scoreboards/reference models, and UVM RAL generation.
- Improve requirement extraction for tables, diagrams, cross-document
  references, freshness, contradictions across revisions, performance/power
  intent, and coverage goals. Scanned PDFs require an explicit OCR adapter.

### Production adapter validation

- Compile and execute generated UVM in at least one client-approved UVM-capable
  simulator and encode vendor compile/run switches in tested runner adapters.
- Extend native Verilog and VHDL from conservative benches to the same
  self-checking depth as the supported SystemVerilog path.
- Implement concrete simulator, formal, document, embedding, vector-store,
  reporting, and policy hooks on top of the versioned plugin-loading contract.
  The current generic contract validates explicit plugins but intentionally
  does not grant them an implicit capability.
- Define and enforce supported version ranges for simulators, formal engines,
  solvers, GHDL, and UVM validators. Verilator is currently the only enforced
  major-version policy.

## P2 Expansion

### Coverage and reporting

- Import native UCIS/vendor databases and formal coverage, preserve exclusions,
  distinguish waived/unreachable/uncovered points, and drive plan updates from
  coverage gaps. Current import supports LCOV, JSON, and Cobertura-style XML.
- Add SARIF and optional YAML exporters, schema migration tests for every public
  report, and filtering by severity, confidence, target, module, source,
  evidence state, and check outcome.
- Generate functional covergroups/bins from richer protocol and requirement
  schemas rather than only importing functional totals produced elsewhere.

### Security and governance

- Add a documented export allowlist, secret-provider abstraction, plugin trust
  policy/signature verification, sandboxed runner option, license-variable
  handling, and a threat model for repository-controlled file lists and command
  wrappers.
- Extend auditing to optional network/model providers with request purpose,
  destination, policy decision, and content-free digests.
- Define retention and deletion policy for proprietary logs, extracted PDF text,
  counterexamples, generated collateral, and audit events.

### Incrementality and scale

- Build a dependency graph across document chunks, facts, plans, generated
  modules, reviews, and imported coverage. Current RTL and vector caches avoid
  major unchanged work, but downstream invalidation remains stage-oriented.
- Benchmark multi-million-line repositories and very large Verilator XML/PDF
  inputs; set memory/runtime budgets and use streaming or indexed parsing where
  needed.
- Extend bounded concurrency to analysis, indexing, planning, generation, and
  independent formal tasks with license-aware scheduling.
- Verify reproducibility across supported operating systems and EDA versions,
  not only repeated runs on one worker.

### Documentation and distribution

- Add complete operator references for commands, RAG/index internals,
  generation backend contracts, output layout, security/privacy, and testing.
- Publish a supported OS/tool compatibility matrix and optional licensed-tool
  container guidance. Native Windows remains deferred.

## Tooling Needed for the Residual Work

| Tool or capability | Purpose |
| --- | --- |
| Slang or Surelog/UHDM | Cross-check complete SystemVerilog semantics and elaboration |
| GHDL | VHDL parsing, compile, and simulation fixtures |
| Questa, VCS, Xcelium, or Riviera-PRO | UVM execution and vendor coverage adapters |
| JasperGold, VC Formal, Questa Formal, or equivalent | Commercial formal adapter validation |
| UCIS/vendor coverage APIs | Native code/functional coverage and exclusions |
| OCR engine approved for local use | Scanned specification ingestion |
| Local embedding/vector runtime | Larger private semantic indexes |
| Profiling and benchmark fixtures | Repository-scale budgets and regression gates |

## Recommended Order

1. Validate generated UVM in one real client simulator and turn its runner into
   the reference versioned adapter.
2. Add one complete protocol/register schema with scoreboard, RAL, functional
   coverage, and formal properties end to end.
3. Add CDC/reset/memory fixtures from an external design and close each with
   structural analysis plus executable properties.
4. Add UCIS/vendor coverage ingestion and coverage-gap-to-plan feedback.
5. Complete plugin trust/export policy, then benchmark and tune the full graph
   on the first large repository.
