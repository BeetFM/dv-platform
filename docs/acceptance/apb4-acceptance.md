# Bounded APB4 Acceptance

Snapshot date: 2026-07-20.

The bounded APB4 slave profile is supported for generated cocotb/Icarus and
formal/SymbiYosys/Yosys/Z3 collateral. A plan is executable only when the
normalized interface has the complete APB4 signal set, correct slave-facing
directions and widths, an unambiguous clock/reset with known polarity, and at
least one governed register whose offset, fields, reset values, byte-enable
behavior, and invalid-address behavior are known.

Typed `apb4_transfer` and `apb4_register_access` scenarios are the only source
for driver bindings, monitor and reference-model intent, assertions, covers,
trace symbols, and completion bounds. SystemVerilog native execution remains a
scaffold because it has no normalized per-scenario result decoder.

The acceptance test runs the complete CLI chain:

`analyze-rtl -> plan -> generate -> run -> coverage --from-runs -> status --policy ci`

The good DUT must pass every executable check with non-vacuous normalized
outcomes, and repeated deterministic generation must be byte-identical. Both
generated backends must reject mutants for discarded writes, ignored PSTRB,
writable RO fields, broken W1C behavior, missing PSLVERR, premature or dropped
PREADY, unstable wait-state responses, and incorrect reset values.

The qualification boundary is deliberately narrow: one APB4 slave, governed
RW/RO/W1C register semantics, byte strobes, invalid-address errors, and bounded
completion. Multi-slave fabrics, bridges, protection policy, low-power behavior,
and native simulator result normalization are not claimed.
