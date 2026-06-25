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

The first output line is recorded as the detected Verilator version.

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
  - `parameters`
  - `clocks`
  - `resets`
  - `instances`
  - `continuous_assignments`
  - `procedural_blocks`
  - `assertions`
  - `covers`
  - `ast_refs`

Clock and reset detection is intentionally conservative and name-based at this
stage. Inferred clocks and resets are treated as evidence-backed claims by later
planning code, not as unquestioned truth.

## Evidence Locators

`ast_refs` point back to the raw XML source artifact. Locators use stable
category/key strings and include Verilator `fl` source-location attributes when
available:

```text
module:simple_counter@a,1,1,15,10
port:simple_counter.clk@a,4,17,4,20
parameter:simple_counter.WIDTH@a,2,19,2,24
instance:simple_counter.u_limit@a,8,5,8,17
```

The `source_id` is the raw XML file path. The `locator` format is platform-owned
and may be extended with richer XML paths as more fixtures are added, but it
should remain deterministic for unchanged inputs.

## Current Limitations

The normalizer is intentionally broad but shallow. It recognizes common XML tag
and attribute patterns for modules, ports, parameters, instances, assignments,
procedural blocks, assertions, and covers. It does not yet fully normalize:

- expression trees
- statement bodies
- data types and packed dimensions
- parameter values
- complete hierarchy graphs
- assertion and cover semantics
- Verilator-version-specific XML shape differences

Those should be added fixture by fixture, with raw XML preserved so normalized
facts can be regenerated as the schema becomes richer.
