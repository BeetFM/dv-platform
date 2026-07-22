# Pulse, toggle, and handshake synchronizer acceptance

The qualified CDC profile covers externally observable single-bit two-flop
chains governed by an explicit `verification_depth` policy. It does not infer a
scheme from signal names.

Supported structures are:

- `toggle`: both level transitions must propagate through the ordered chain and
  remain stable at the destination;
- `pulse`: the governed source pulse must be stretched for at least the number
  of synchronizer stages, observed at the destination, and return to idle;
- `handshake`: request and acknowledgement require independent qualified chains,
  bounded round-trip completion, request holding, and governed payload stability.

External asynchronous inputs, ordered stage signals, destination clock/reset,
stage count, and reset compatibility are normalized facts. Policy validation
fails closed for ambiguous paths, missing or incorrect final outputs, a short
pulse stretch, an unqualified acknowledgement path, or unknown payload signals.

Generated cocotb tests drive and observe every transition with finite timeouts.
Generated formal collateral checks every observable stage, covers rise/fall,
pulse observation/return, request observation, and handshake round trip, and
records the bounded environment assumptions used for request/payload stability.
Zero tests, unmatched symbols, or absent covers cannot close the mapped checks.

The full CLI good DUT is byte-reproducible and passes analyze, plan, generate,
simulation/formal run, coverage, and strict status. Structure-preserving mutants
for corrupted toggle, pulse, request, and acknowledgement propagation are killed
by both generated cocotb and generated formal collateral.

Reconvergent CDC, general multi-bit coherency, and schemes without a governed
structural contract remain unsupported. Async-FIFO Gray pointers are supported
only through the separate governed [async FIFO profile](async-fifo-acceptance.md).
