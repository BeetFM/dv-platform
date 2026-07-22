# Stage 9 VHDL and project-UVM qualification

Status: accepted on 2026-07-22.

## VHDL reset and ready/valid profile

The bounded VHDL source frontend now recognizes a paired stream only from a
complete directionally consistent `valid`, `ready`, and `data` port set in one
unambiguous clock/reset domain. Generated VHDL-2008 collateral checks observable
reset state, input acceptance, end-to-end data, output stability through
backpressure, and recovery after acceptance. The complete CLI path runs through
GHDL 4.1.0, imports exact native trace results, closes coverage, and passes the
CI status policy.

`tests/test_vhdl_ready_valid_qualification.py` passes the good project, verifies
byte reproducibility, and kills four VHDL mutants: incorrect reset, refused
input, corrupted data, and dropped valid under backpressure. Subsequent Stage 10
work added GHDL-authoritative packages, records, subtypes, arrays, generate
elaboration, and explicit architecture binding. Incomplete streams and ambiguous
or undeclared cross-language bindings remain fail-closed.

## Paired ready/valid UVM project profile

The generated UVM 1.2 project contains the interface, transaction, sequence,
sequencer, driver, monitor, expected/actual FIFO scoreboard, environment, test,
and DUT top. `vivado_xsim_project_runner` compiles those artifacts with project
RTL, elaborates the generated top, executes the named test, requires zero UVM
errors/fatals and the absence of the scoreboard's no-transaction failure, and
emits exact `DV_PLATFORM_RESULT_V1` records for every generated trace. The
normal run-summary path converts those records into validation-result v1 and
normalized coverage points, so `coverage --from-runs` and strict status close.

`tests/test_uvm_project_qualification.py` exercises both the vendor-runner
boundary and the complete CLI normalization path. Current real-tool evidence is
the checked-in AMD Vivado Simulator 2025.2 attestation at
`docs/evidence/vivado-xsim-2025.2-qualification-attestation.json`; its integrity
and binding to the current generated UVM bytes are rechecked by
`tests/test_enterprise_qualification.py`.

This Stage 9 qualification is deliberately limited to paired ready/valid UVM.
Multi-agent profile environments and RAL are now generated and contract-tested,
but additional vendor execution, VHDL/UVM mixed-language execution, and live
coverage-database APIs remain later vendor-stage work.
