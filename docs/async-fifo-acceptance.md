# Async FIFO and Gray-pointer acceptance

The qualified async-FIFO profile is an explicitly governed, bounded open-tool
profile. It is executable only when the configured storage resolves to one
power-of-two unpacked memory with known element/address widths, one synchronous
write access, one synchronous read access, distinct normalized clock/reset
domains, observable data/control/status ports, depth-sized binary and Gray
pointers, and two ordered Gray-pointer synchronizer chains.

The policy is a mapping contract, not evidence by itself. Planning rejects a
missing or ambiguous access, same-clock configuration, conflicting access
domain, incorrect data/pointer width, incomplete signal mapping, short or
ambiguous synchronizer, and non-power-of-two depth. Independent FIFO reset
domains are permitted only for the two policy-qualified Gray crossings; this
does not promote unrelated unsafe crossings.

Generated cocotb collateral owns the driver, monitor, reference queue, and
timeouts. It fills and drains the FIFO, observes `full` and `empty`, checks that
a full write is rejected, compares every read against write order, crosses the
pointer wrap boundary, runs unequal concurrent clocks, checks reset recovery,
and validates binary-to-Gray encoding and one-bit Gray transitions. All loops
are finitely bounded and the scenario owns explicit non-vacuity bins.

Generated formal collateral uses vector-width stage histories for both pointer
crossings and emits reset, binary/Gray encoding, one-bit transition, accepted
increment, blocked hold, full-equation, and empty-equation assertions. Separate
write, read, full, empty, and synchronized-propagation covers must be reachable.
The harness tracks each asynchronous clock/reset event independently instead of
using a single-clock `$past` approximation.

The full CLI good DUT is byte-reproducible and closes exact per-check outcomes
through analyze, plan, generate, Icarus/cocotb or SBY/Yosys/Z3 execution,
coverage, and strict status. Generated cocotb kills mutants for misaddressed
writes, ignored full, incorrect empty, non-Gray write pointers, corrupted Gray
synchronization, misaddressed reads, and broken wraparound. Generated formal
kills the five structural/status mutants it claims; memory ordering/address
mutants remain simulation-scoreboard qualifications and are not described as
formal proofs.

Non-power-of-two FIFOs, multiple read/write ports, show-ahead/FWFT semantics,
arbitrated or multi-port storage, ECC/parity, standalone multi-bit coherency,
reconvergence, and schemes without this exact governed contract remain
unsupported.
