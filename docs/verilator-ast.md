# Verilator AST Extraction

Stage 2 uses Verilator XML as the evidence source for Verilog and
SystemVerilog RTL structure.

## Invocation

`dv-platform analyze-rtl` builds a Verilator command from the normalized project
configuration and discovered inventory:

```text
<verilator_executable> --xml-only --Mdir <work-dir>/verilator \
  -I<include-path> -D<define> --top-module <top> <rtl-files>
```

`verilator_executable` may be an executable name, path, or command prefix for a
client wrapper. It is parsed as shell-like arguments with `shlex.split`; the CLI
does not invoke a shell.

Before running XML extraction, the platform also invokes:

```text
<verilator_executable> --version
```

The first output line is recorded as the detected Verilator version. Major
version 5 is the current tested compatibility range. Strict analysis rejects an
unparseable version or another major, and `status --policy ci` rejects stored
facts that were not produced by that tested range.

## Stored Artifacts

The current implementation writes:

- raw Verilator XML files under `<work-dir>/verilator/`
- detected version text at `<work-dir>/verilator/verilator-version.txt`
- stdout log at `<work-dir>/logs/verilator.stdout.log`
- stderr log at `<work-dir>/logs/verilator.stderr.log`
- normalized RTL facts at `<work-dir>/rtl-facts/modules.json`
- failure summary at `<work-dir>/runs/analyze-rtl/verilator-failure.json` when
  Verilator returns a non-zero exit code

`analyze-rtl --dry-run` stops after discovery, manifest writing, validation, and
command construction. It does not invoke Verilator.

## Normalized Facts

`modules.json` currently contains:

- `schema_version`
- `verilator_version`
- per-module:
  - `name`
  - `ports`
  - `port_details` with direction, width, signedness, packed range, type, and
    source location
  - `parameters`
  - `parameter_details` with elaborated value, type, width, signedness,
    local-parameter status, and source location
  - `memories` with element width and unpacked depth when resolvable
  - `clocks`
  - `clock_details` with edge, classification source, and evidence
    confidence
  - `resets`
  - `reset_details` with active level, synchronous/asynchronous classification,
    classification source, and evidence
    confidence
  - `semantic_features` with source location, detector confidence, global
    support, and target-specific safe generation targets
  - `instances`
  - `instance_details` with original/elaborated child module identity and
    structured port connection expressions/signal references
  - `continuous_assignments`
  - `procedural_blocks`
  - `procedural_block_details` with normalized expressions, conservative
    patterns, and control-domain identity
  - `control_domains` with clock/reset edges, reset polarity, and asynchronous
    reset classification
  - `protocols` for conventional flat ready/valid channels
  - `assertions`
  - `covers`
  - `ast_refs`

Clock and reset detection is intentionally conservative. For common sequential
blocks with multiple sensitivity edges, the normalizer uses the sensitivity
tree and first reset conditional to identify the reset, polarity, and clock.
Name heuristics are retained as a fallback, and each detail records whether it
came from sensitivity evidence or a name heuristic. Inferred controls are
treated as evidence-backed claims by later planning code, not as unquestioned
truth.

## Evidence Locators

`ast_refs` point back to the raw XML source artifact. Locators use stable
category/key strings and include legacy `fl` or current `loc` Verilator
source-location attributes when available:

```text
module:simple_counter@a,1,1,15,10
port:simple_counter.clk@a,4,17,4,20
parameter:simple_counter.WIDTH@a,2,19,2,24
instance:simple_counter.u_limit@a,8,5,8,17
```

The module's `source` field is resolved from Verilator's XML file table. The
`source_id` on evidence remains the raw XML file path. The `locator` format is
platform-owned and may be extended with richer XML paths as more fixtures are
added, but it should remain deterministic for unchanged inputs.

## Current Limitations

The normalizer is intentionally broad but still conservative. It recognizes common XML tag
and attribute patterns for modules, ports, parameters, instances, assignments,
procedural blocks, assertions, covers, simple sequential behaviors, and control
sensitivity. It also extracts numeric elaborated parameters, unpacked memory
shape, child connections, block-level domains, and flat ready/valid channels.
Semantic feature safety is evaluated per generation target rather than by a
single global allow decision. It does not yet fully normalize:

- expression trees
- statement bodies
- nested statements and rich expression semantics
- memory access semantics, structs/unions, enums, interfaces/modports, or
  package/type relationships
- parameter expressions, sweeps, or multiple specializations of one source
  module in one plan set
- generate-aware complete hierarchy graphs
- assertion and cover semantics
- CDC semantics, cross-domain behavior, or reset sequencing across domains
- Verilator-version-specific XML shapes outside the current fixtures

Those should be added fixture by fixture, with raw XML preserved so normalized
facts can be regenerated as the schema becomes richer.
