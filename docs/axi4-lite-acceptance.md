# Bounded AXI4-Lite Acceptance

Snapshot date: 2026-07-21.

The bounded AXI4-Lite slave profile is supported for generated cocotb/Icarus
and formal/SymbiYosys/Yosys/Z3 collateral. A plan is executable only when
normalized evidence contains the complete AW/W/B/AR/R payload and handshake
set, correct slave-facing directions and compatible widths, an unambiguous
clock/reset with known polarity, linked stable checks, and at least one governed
register with known offset, fields, reset, WSTRB, and invalid-address behavior.

The typed `axi4_lite_single_outstanding` scenario is the only source for driver
bindings, independent channel timing, monitor/reference scoreboard state,
completion bounds, properties, covers, and trace symbols. The bounded profile
allows one read and one write outstanding at the same time. It exercises
AW-before-W, W-before-AW, same-cycle capture, simultaneous read/write progress,
B/R backpressure and payload stability, WSTRB including a zero-byte write,
valid and invalid response handling, reset recovery, and rejection of a second
outstanding AW or AR request.

The acceptance test runs the complete CLI chain:

`analyze-rtl -> plan -> generate -> run/prove -> coverage --from-runs -> status --policy ci`

The good DUT must produce a passing normalized outcome for every executable
check, reach non-vacuous channel/formal coverage, and generate byte-identical
collateral on repetition. Generated cocotb and formal backends must both reject
mutants for coupled AW/W acceptance, lost and early BVALID, unstable BRESP,
dropped RVALID, unstable RDATA/RRESP, ignored WSTRB, incorrect error responses,
and acceptance of second outstanding write or read requests.

SystemVerilog emits typed stability properties for all five channels but remains
a scaffold because native simulation has no scenario result decoder. Full AXI,
bursts, IDs, multiple outstanding transactions per direction, interconnect
ordering, protection/cache attributes, and performance guarantees are not
claimed.
