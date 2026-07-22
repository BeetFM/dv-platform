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
- Qualified bounded SRAM policies add a typed full-address simulation scoreboard
  and a bounded formal reference word for byte merging, two-requester round-robin
  arbitration, zero initialization, collision response, and injected parity errors.
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
output_signal = "status_sync"
min_stages = "2"
max_latency_cycles = "4"
reset_compatible = "true"
```

Supported kinds are `reset`, `memory`, `cdc`, and `formal`. Parameters are validated and
persisted in canonical plans; unknown parameters and invalid bounds fail
configuration. A policy states intended semantics but does not by itself prove
that RTL implements them.

Qualified pulse policies also require `output_signal` and
`pulse_stretch_cycles`; the stretch must be at least the normalized stage count.
Qualified handshake policies require `output_signal`, `ack_input_signal`, and
`ack_output_signal`, and may provide a comma-separated `data_signals` list whose
values are assumed stable while a request is pending. Planning promotes these
policies only when the ordered forward and reverse paths resolve uniquely.

Qualified async-FIFO policies use `structure = "async_fifo"` with the memory as
the policy subject. They require explicit `write_clock`, `write_reset`,
`write_enable`, `write_data`, `write_binary_pointer`, `write_gray_pointer`,
`write_gray_sync`, `full_signal`, and corresponding `read_*` plus
`empty_signal` mappings. Planning cross-checks those names, directions, widths,
memory accesses, domains, power-of-two depth, and both ordered pointer chains
before registering `cdc_async_fifo` as executable.

Qualified reset-domain policies require `clock`, `release_cycles`,
`asynchronous_assertion`, and `ready_signal`; optional `min_assert_cycles`,
`recovery_cycles`, and `removal_cycles` bounds govern the executable scenario.
An ordered domain also supplies `depends_on_reset`, `depends_on_ready`, and
`dependency_sync_signal`. Planning verifies distinct domains, rejects cycles,
and requires an ordered two-stage dependency-ready path before registering
`reset_domain_sequence` as executable.

Qualified bounded SRAM policies use `profile = "bounded_sram"` and require exact
clock/reset/read-port mappings, two complete write requester mappings, declared
`read_during_write`, `initialization = "zero"`, `arbitration = "round_robin"`,
`protection = "parity"`, and fault injection/error outputs. Planning cross-checks
memory shape, synchronous accesses, domain ownership, directions, address/data widths,
byte-lane widths, and unique signal identities before registering
`memory_bounded_sram` as executable.

Qualified formal policies use `profile = "bounded_response"` with exact clock,
reset, trigger, response, and invariant signal mappings. A 1–64-cycle response
bound, trigger-pulse assumption, and response-causality policy are mandatory.
The deterministic formal renderer emits the property-specific assumption,
induction state/design invariants, bounded liveness, and independent
assumption-witness/response/completion covers before registering
`formal_bounded_response` as executable.
