# P0 Pilot Acceptance

The P0 acceptance path proves that dv-platform can take a small but realistic
SystemVerilog design from source discovery through a strict, evidence-backed,
executable verification result without accepting stale or unverifiable state.

## Supported Acceptance Slice

The golden fixture under `tests/fixtures/pilot` contains:

- a parameterized vector counter;
- a top-level `WIDTH=12` elaboration override propagated into generated and
  executed collateral;
- a two-entry ready/valid stream buffer with vector data, unpacked storage,
  pointer wrap, and simultaneous push/pop case logic;
- a clock named `phase`, so clock discovery cannot depend on a `clk` suffix;
- an active-high reset named `clear_n`, so reset polarity cannot be guessed
  from its name;
- a hierarchical wrapper with structured child port connections and both
  original and elaborated child identities; and
- module-specific documentation for reset, increment, hold, connectivity,
  ready/valid transfer, latency, backpressure stability, and data integrity.

The simulation acceptance workflow runs:

```text
init --ci
  -> analyze-rtl
  -> index-docs
  -> plan --target cocotb
  -> generate --target cocotb
  -> run --target cocotb --all
  -> review
  -> status --policy ci
```

The same workflow is then repeated without input changes. The regression test
requires stable hashes for normalized RTL facts, retrieval indexes, plans,
claim reports, review reports, generated tests, and provenance manifests. It
also injects stale plan and generated files and verifies that regeneration
removes them.

The formal acceptance workflows analyze both a documented counter and the
memory-backed ready/valid buffer, generate their assumptions, assertions, cover
tasks, execution manifests, and traceability, and then require both the
SymbiYosys `prove` and `cover` tasks to pass. The stream proof checks that valid
and data remain stable under backpressure with a 12-bit elaborated parameter
configuration. Hosted CI
installs a pinned SymbiYosys revision with Yosys and Z3 and executes this test as
a mandatory step; it cannot pass by taking the local missing-tool skip.

## Acceptance Checks

A change satisfies the P0 pilot gate when all of the following pass:

```bash
uv sync --all-groups --frozen
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run coverage run -m unittest discover -s tests
uv run coverage report
uv build --out-dir .dv-platform/package-check
uv run pip-audit --skip-editable
```

Verilator and Icarus Verilog must be installed for the golden workflow. The
real-tool tests verify both cocotb execution and Verilator lint of generated
SystemVerilog. SymbiYosys, Yosys, and Z3 are mandatory in the hosted quality
job; the formal integration test may skip only in local environments without
that toolchain.

CI enforces Python 3.11, 3.12, and 3.13 compatibility. Its quality job installs
the open simulation and formal toolchains and executes the real-tool pilots in
addition to lint, format, typing, branch coverage, package build, and dependency
audit gates.

## Correctness Guarantees in This Slice

- Work and output trees are excluded from fallback RTL discovery.
- Module-derived paths reject absolute paths, traversal, and path separators.
- Canonical text/JSON outputs use atomic replacement; generated module trees
  are staged and replaced as a unit.
- Regeneration removes stale module directories, stale module files, stale plan
  views, and stale claim views.
- Provenance schema v2 records the SHA-256 and byte size of every artifact.
- Runs reject missing, malformed, or tampered provenance and artifacts.
- Every generated module contains an execution manifest binding the adapter,
  generated file set, plan traces, project manifest digest, and SHA-256/size of
  every RTL input. Runs and CI status reject a changed input or manifest.
- Executable artifacts must map generated symbols back to plan checks,
  requirement IDs, behavior IDs, claim IDs, and evidence references. Missing
  traceability blocks publication.
- Run summaries are bound to the exact provenance SHA-256; regeneration makes
  earlier results stale, and CI requires a new matching run.
- Cocotb runs reject a missing result file, malformed result XML, zero executed
  testcases, failed testcases, and timeouts.
- `status --policy ci` requires current, non-empty RTL facts and plans; all
  planned outputs; artifact quality and integrity; required generator tool
  validation; no unexpected or unsafe generated roots; run results for
  executable generated targets; and configured tools unless
  `--no-require-tools` is explicit.
- CI accepts only the tested Verilator major version and records actual tool
  versions in analysis, validation, and run state.
- Generated HDL uses structured port direction, width, signedness, clock, reset,
  and reset-polarity facts where available. Verilator sensitivity information
  takes precedence over naming heuristics for sequential clock/reset inference.
- RTL facts and plans retain elaborated parameter values, memory shape,
  original and specialized child module identity, structured instance port
  connections, per-procedural-block control domains, and ready/valid channels.
- Clock/reset confidence and semantic feature support are target-specific.
  Case and internal memory constructs are accepted for the exercised black-box
  simulation/native/formal paths; constructs outside a target's support still
  fail closed.
- Requirements are deterministically categorized and deduplicated, retain exact
  document sentence offsets, and block generation when equivalent conditions
  prescribe conflicting values.
- Cocotb and formal summaries expose generated-symbol trace coverage, failed
  traces, triage classification, and repair suggestions through plan mappings.
  A passing tool result with an unexecuted generated symbol does not satisfy CI
  policy; per-check outcome attribution remains outside this slice.
- Formal reset assumptions constrain initialization and release, proof depth is
  selected from supported latency intent, prove and cover tasks are both run,
  ready/valid source stability is asserted, vector inputs are symbolic, and
  counterexample trace paths are retained when the tool emits them.

## Boundaries After P0

This acceptance slice is deliberately narrower than full enterprise sign-off.
It supports explicit numeric top-parameter overrides for one elaborated
configuration using validated two-state SystemVerilog integer literals, not
parameter sweeps or multiple differently specialized copies of one source
module. Ready/valid inference covers conventional flat signal
names and one sink/source end-to-end pair; it is not a generic protocol library.
Multiple mapped clocks can be driven by cocotb, but CDC correctness, reset
sequencing across domains, interfaces/modports, complete SystemVerilog
semantics, production UVM environments, simulator code/functional coverage
closure, and commercial adapters remain open. UVM has no open compile validator
in the current adapter set, VHDL validation requires GHDL, and formal support is
limited to single-domain safety properties. These are explicit post-P0 gaps,
not silent assumptions.
