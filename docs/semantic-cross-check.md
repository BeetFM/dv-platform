# SystemVerilog semantic cross-checking

Verilator remains authoritative. Slang is an independent cross-checker: its
facts never overwrite or supplement normalized Verilator facts. It affects
trust through explicit comparison results and policy gates.

## Configuration and policy

```toml
[rtl]
verilator_executable = "verilator"
slang_executable = "slang"
semantic_crosscheck = "report" # off | report | required
```

`analyze-rtl` gives both frontends the same files, include directories, defines,
top modules, and parameter overrides. Each parameter-sweep point is executed and
compared independently.

- `off`: Verilator-only compatibility mode.
- `report`: persist issues and continue an exploratory run. Strict and CI runs
  fail on unavailable, incomplete, or disagreeing required capabilities.
- `required`: fail every workflow unless the aggregate result passes.

`plan` and `generate` re-check the latest result when policy is enforcing, so a
failed or missing cross-check cannot be bypassed by using stale Verilator facts.

## Versioned contract

Schema/API version 2 records:

- run and specialization identity;
- frontend names, versions, commands, and AST artifact paths;
- checked, unsupported, and required capabilities;
- aggregate status and checked modules;
- per-field issues with severity, canonical values, source locations, and
  Verilator/Slang AST evidence references.

Specializations pair by original design unit and canonical non-local parameter
values. Slang `InstanceBody` records are never collapsed by name or insertion
order. Tool IDs, ordering, scalar widths, constants, ranges, and operation names
are removed or canonicalized before comparison.

Capabilities are fail-closed. Capability support describes the normalizer
profile, not whether a particular design happened to contain a fact. All
qualified capabilities are required when cross-checking is enabled; an unknown
node withdraws its affected capability with a source-located reason. This
distinguishes an empty fact set from a mapper that silently dropped facts.

## Semantic coverage

The normalized model and comparator cover structural identity, ports,
parameters, specializations, types and aggregate members, interfaces/modports,
instances and connections, assignments, expression trees, branches,
clock/reset domains, structured properties, imports, generate scopes, and
unpacked memories. Expression facts retain width, signedness, packed range,
cast kind, and source location. Property facts retain immediate/concurrent kind,
clocking, disable condition, body, support status, and unsupported temporal
operators.

The Slang mapper is qualified against real Slang 11 JSON for expressions,
wildcard cases, synchronous and asynchronous resets, immediate and concurrent
properties, delays, enum and nested aggregate types, interface arrays and
modports, package imports, parameterized hierarchy, generate loops and
conditions, and synchronous memories. It marks incomplete constructs as
capability gaps. A conservative source inventory retains inactive generate
branches that the elaborated JSON omits. Verilator facts remain the source used
by planning and generation. Unsupported property temporal operators create
critical generation-precondition claims.

## Artifacts

Ordinary runs write:

- `.dv-platform/slang/ast.json`;
- command, version, diagnostics, stdout, and stderr under
  `.dv-platform/slang/`;
- `.dv-platform/slang/crosscheck.json` for the point result;
- `.dv-platform/semantic-crosscheck/result.json` for the aggregate.

Sweep artifacts use `.dv-platform/sweeps/<identity>/slang/`. Slang configuration
and detected version participate in the RTL cache fingerprint.

## Qualified compatibility profile

The current strict compatibility window is Verilator major 5 with Slang major
11. Local integration tests skip when Slang is absent. A qualified CI job sets
`DV_PLATFORM_QUALIFIED_SLANG_CI=1`, which makes tool availability and a real
strict CLI cross-check mandatory.

The parsed document is traversed iteratively, and a qualification benchmark
enforces a five-second / 64-MiB budget on the repository's synthetic large-AST
fixture. See [Slang compatibility matrix](slang-compatibility-matrix.md) for the
expected pass and fail-closed outcomes.
