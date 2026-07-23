# Parameter-Sweep Cross-Point Acceptance

Snapshot date: 2026-07-21.

Explicit `parameter_sweeps` are analyzed in isolated work directories and retain
unique module, plan, evidence, generated-artifact, and run identities. Coverage
schema v3 groups those points by original design unit and canonical check
semantics, then reports every specialization and every semantic cross-point.

A cross-point closes only when its corresponding check closes at every configured
elaboration point. Missing plans, missing points, failed or unexecuted checks, and
stale evidence produce named gaps. `coverage` fails on an incomplete cross-point,
and `status --policy ci` reports `parameter_sweep_coverage_incomplete` rather than
allowing aggregate percentages to hide the missing configuration.

The real-tool acceptance runs WIDTH=4 and WIDTH=9 through Verilator analysis,
planning, deterministic cocotb generation, Icarus/cocotb execution, run-derived
coverage, and CI status. Unit coverage also verifies the negative case in which
one specialization is not covered. Automatic Cartesian-product discovery and
cross-project aggregation remain out of scope; every point must be explicitly
configured.
