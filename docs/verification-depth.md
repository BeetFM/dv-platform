# Verification Depth

The deterministic depth layer converts normalized RTL facts into closure intent
without claiming semantics that the facts do not prove.

## Executable depth

- Each normalized control domain with a reset receives assertion/release
  reachability intent. The formal harness emits separate reset asserted and
  released covers.
- Each recognized ready/valid or request/acknowledge source receives stability
  assertions and transfer, backpressure, and recovery covers.
- Supported synchronous writes retain address bounds and post-write assertions,
  plus enable and lowest/highest legal address covers.
- Configured synchronous memory collisions emit same-address collision covers
  and `read_first`, `write_first`, or `no_change` assertions. Policies are used
  only when one read and write access expose unambiguous address/data signals in
  the formal clock domain.
- Generated run traces map these executable checks into normalized closure
  points and canonical plan status.

## Fail-closed depth

- Asynchronous reset release is planned but not executable until the domain
  model proves its release synchronizer.
- Synchronous memory reads are planned but not asserted while collision policy
  and observable read timing are unknown.
- CDC propagation fails closed when internal synchronizer stages are not
  observable. `--cdc-policy bounded` enables a separate finite-depth external
  latency task whose `bounded_pass` result remains an actionable closure gap.
- `--cdc-policy structural` requires every ordered stage to be exposed as a
  formal output and blocks generation unless an unbounded stage-by-stage proof
  can be emitted.
- Linear synchronizers retain their ordered destination-stage signal names.
  Branching or reconvergent paths are not counted as a safe linear chain.
- Unsafe CDC paths remain explicit closure blockers; they are never converted
  into assumptions.

This boundary prevents an easy proof caused by constraining away the behavior
that needs verification.

## Explicit policy

Ambiguous intent is configured with versioned `[[verification_depth]]` records:

```toml
[[verification_depth]]
kind = "memory"
module = "stream_buffer"
subject = "storage"
read_during_write = "read_first"
initialization = "unconstrained"

[[verification_depth]]
kind = "cdc"
module = "status_bridge"
subject = "status_toggle"
source_domain = "write"
destination_domain = "read"
structure = "toggle"
min_stages = "2"
max_latency_cycles = "4"
reset_compatible = "true"
```

Supported kinds are `reset`, `memory`, and `cdc`. Parameters are validated and
persisted in canonical plans; unknown parameters and invalid bounds fail
configuration. A policy states intended semantics but does not by itself prove
that RTL implements them.
