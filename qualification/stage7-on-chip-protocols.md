# Stage 7 on-chip protocol qualification

Qualified on 2026-07-22 against the `0.1.0` development lineage.

- APB4 passes generated cocotb and bounded-formal good-DUT runs and kills nine
  mutants on each backend. The same typed scenarios now generate normalized,
  self-checking native SystemVerilog and Verilog transactions; both native
  targets pass the good DUT and kill all nine mutants.
- AXI4-Lite passes generated cocotb and bounded-formal good-DUT runs and kills
  ten mutants on each backend. Native SystemVerilog and Verilog independently
  check AW/W ordering, one-outstanding limits, response hold/stability, WSTRB,
  error responses, read data, and exact result closure; both kill all ten.
- The bounded AHB-Lite single-beat slave profile passes cocotb and formal and
  kills six governed register, wait-state, response, and reset mutants on each.
- The paired ready/valid stream profile passes generated cocotb end-to-end data,
  acceptance, backpressure, stability, and recovery checks and kills refusal,
  dropped-valid, unstable-data, and corrupted-data mutants. Its formal safety
  assertions remain supported but are not included in this profile's mutation
  claim because an end-to-end formal reference model is not yet qualified.
- Every accepted run uses stable trace IDs, normalized per-check results,
  coverage import, strict CI status, bounded timeouts, and byte-reproducible
  generated artifacts. Partial interfaces and unknown clock/reset/register
  semantics remain fail-closed.

This stage does not claim full AXI, bursts, IDs, multiple outstanding
transactions, AHB bursts/interconnect, or AXI-Stream sidebands such as TLAST,
TKEEP, TID, TDEST, and TUSER.
