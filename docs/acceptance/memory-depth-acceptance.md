# Bounded Memory Depth Acceptance

Snapshot date: 2026-07-21.

The executable memory profile is deliberately narrow. It requires one normalized,
byte-addressable synchronous memory with known depth, address width, and element
width; one clock/reset domain; one observable synchronous read port; two observable
write requesters; per-requester byte enables and grants; a declared collision mode;
zero initialization; round-robin arbitration; and observable parity fault injection
and detection. Every configured signal is checked for direction and width before the
`memory_bounded_sram` scenario can become executable.

Generated cocotb collateral maintains a reference image of every legal address. It
checks reset initialization and recovery, low/high addresses, full and partial writes,
byte-lane preservation, declared read-during-write behavior, exclusive and alternating
grants under contention, both requesters, clean parity reads, injected parity errors,
bounded completion, and non-vacuity. Generated formal collateral proves grant
exclusivity/work conservation, two-requester round-robin behavior, collision response,
parity outcomes, and a byte-merged reference word at address zero; covers exercise
both grants, contention, both collision paths, and parity injection. Exhaustive address
initialization and high-address behavior remain simulation-qualified to keep the open
solver task bounded and reproducible.

The complete CLI path is qualified through analyze, plan, generate, run/prove,
coverage reconciliation, and strict status. Repeated generation is byte-identical.
The good DUT passes generated cocotb and formal collateral. Both backends kill eight
mutants: ignored byte enables, wrong read-during-write semantics, fixed-priority
starvation, incorrect initialization, missing parity detection, non-exclusive grants,
a discarded port-1 write, and a misaddressed read. Every executable check receives an
exact normalized result; zero or unmatched tests remain unexecuted.

The profile does not claim SECDED correction, repair/scrubbing, initialization files,
asynchronous or more-than-two-requester memories, multiple physical read ports,
independent clock domains, power-state retention, cache/coherency behavior, or physical
memory-macro timing. Those cases remain unsupported and cannot inherit this profile's
closure evidence.
