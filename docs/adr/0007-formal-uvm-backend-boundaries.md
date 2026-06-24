# 0007: Formal and UVM Backend Boundaries

## Status

Accepted

## Context

Formal verification and UVM environments require stronger assumptions than
simple smoke tests. Poorly inferred assumptions or fake transaction models can
create misleading collateral and maintenance debt.

## Decision

SymbiYosys is the first formal tool adapter for open fixture validation.
Commercial formal tools are added later as adapters. Formal generation emits a
harness, assumptions, assertions/covers, `.sby` configuration, and a provenance
manifest. Client project execution requires explicit formal tool configuration,
and strict/CI mode requires explicit formal tool configuration.

UVM generation starts as an evidence-backed module-level scaffold only when
interface and transaction boundaries are clear. A useful scaffold includes a
package, interface, transaction item when inferable or configured, sequencer,
driver, monitor, scoreboard stub, env, test, top-level harness, compile/run
file list, and provenance manifest.

If transaction semantics are missing, the UVM backend emits a skeletal harness
with open questions instead of pretending a constrained-random environment is
supported. Missing transaction intent blocks advanced UVM generation in
strict/CI mode.

Test bench style customization is declarative config only. Core generators may
support naming, reset conventions, clock defaults, timescale, naming style,
output naming, tool preferences, header/license text, pragmas, and UVM
verbosity defaults. Arbitrary templates and code-snippet injection are not
supported in the core generator initially.

## Consequences

Formal and UVM output remain conservative and evidence-backed. Customer-specific
generation is directed toward future plugins or adapters instead of unsafe core
template expansion.
