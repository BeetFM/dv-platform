# CDC synchronizer acceptance

The qualified CDC profile covers externally observable two-flop chains governed
by an explicit `verification_depth` policy. It does not infer a scheme from
signal names.

Supported structures are:

- `toggle`: both level transitions propagate through the ordered chain and
  remain stable at the destination;
- `pulse`: the source pulse is stretched for at least the synchronizer depth,
  observed at the destination, and returns to idle;
- `handshake`: request and acknowledgement use independent qualified chains,
  bounded round-trip completion, request holding, and payload stability;
- `multi_bit_handshake`: paired input and destination-observation payloads have
  equal known widths and are sampled and compared as one coherent transfer;
- `gray`: an observable multi-bit Gray counter is checked under the explicit
  `max_source_steps_per_destination = 1` environment bound required for a
  one-bit observed-transition guarantee.

External inputs, ordered stage signals, destination clock/reset, stage count,
and reset compatibility are normalized facts. Policy validation fails closed
for ambiguous paths, missing or incorrect outputs, short pulse stretch,
unqualified acknowledgement paths, mismatched payloads, unknown widths, or an
unbounded Gray source rate.

Generated cocotb tests drive and observe every transition with finite timeouts.
Generated formal collateral checks every observable stage, covers rise/fall,
pulse observation/return, request observation, handshake round trip, sampled
payload coherency, and Gray transitions, and records the bounded environment
assumptions. Zero tests, unmatched symbols, or absent covers cannot close the
mapped checks.

The full CLI good DUT is byte-reproducible and passes analyze, plan, generate,
simulation/formal run, coverage, and strict status. Structure-preserving mutants
for corrupted toggle, pulse, request, acknowledgement, coherent payload, and
Gray propagation are killed by both generated cocotb and formal collateral.

Reconvergent CDC, unconstrained multi-bit buses, and schemes without a governed
structural contract remain unsupported. Async-FIFO Gray pointers are supported
through the separate governed [async FIFO profile](async-fifo-acceptance.md).
