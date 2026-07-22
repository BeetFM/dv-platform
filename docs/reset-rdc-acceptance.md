# Reset-domain and RDC acceptance

The qualified reset-domain profile is explicitly governed. A reset policy is
executable only when its reset resolves uniquely to one normalized control
domain, its configured clock and asynchronous-assertion style agree with RTL,
and its scalar ready indication is an observable output.

An optional power-sequence extension requires an observable scalar
`power_good_signal` input and distinct scalar `isolation_signal` and
`retention_signal` outputs. Missing, aliased, or directionally inconsistent
mappings fail closed. Ready remains low while power is unavailable; isolation
and retention remain asserted until the powered domain completes release.

Ordered domains additionally require `depends_on_reset`, `depends_on_ready`,
and `dependency_sync_signal`. The dependency must belong to a distinct reset
domain and its ready indication must cross through one unambiguous, ordered,
two-stage synchronizer ending at the configured dependency-sync output. Only
this policy-qualified RDC path is promoted; unrelated unsafe crossings remain
open. Self-dependencies and dependency cycles are contradicted claims.

Generated cocotb scenarios start independent clocks, assert all involved resets,
release a dependent reset while its prerequisite remains active, and prove the
dependent ready signal stays low. They then release the prerequisite, observe
its ready indication and synchronized RDC path, enforce the configured release
delay, and require bounded downstream readiness. A second phase asserts reset
between clock edges, checks immediate asynchronous clearing, applies governed
recovery/removal offsets, checks early-release exclusion, and rejects unresolved
post-reset values. Every wait is finite.

For a power-governed domain, the scenario first holds power good low and proves
ready, isolation, and retention remain safe, then applies power good and checks
the bounded release. Reset reassertion immediately restores isolation and retention.

Generated formal collateral checks asynchronous ready clearing, ordered hold,
release-delay hold, and bounded ready assertion independently in each clock
domain. It proves every observable RDC synchronizer stage and requires covers
for dependency observation and domain release. The environment assumption that
a reset release is monotonic during one proof episode is emitted explicitly;
reassertion and recovery are exercised by simulation rather than hidden inside
that assumption.

Formal power properties check the no-power hold state and require isolation and
retention to be deasserted whenever a powered domain advertises readiness.

The full CLI good DUT is byte-reproducible and closes exact per-check outcomes
through analyze, plan, generate, Icarus/cocotb or SBY/Yosys/Z3 execution,
coverage, and strict status. Both generated backends kill mutants for broken
source/destination asynchronous assertion, early source/destination release,
dependency bypass, corrupted RDC synchronization, premature isolation or
retention release, and power-good bypass.

Analog recovery/removal timing, reset-tree physical analysis, hidden
synchronizer stages, non-monotonic proof episodes, macro-specific power states,
and reset dependencies without the governed observable contract remain unsupported.
