# AHB-Lite bounded single-beat qualification

The qualified profile is a 32-bit, single-master, single-beat AHB-Lite slave
with `HREADYOUT`, one or more fully specified registers, RW/RO/W1C fields,
`HRESP` on invalid addresses, a known clock, and an active-low or active-high
reset. Bursts, split/retry responses, protection semantics, multi-layer
interconnect, and broader AHB constructs remain unsupported.

`tests/test_ahb_lite_generated_pipeline.py` executes the full CLI pipeline. It
requires exact per-check results, coverage import, `status --policy ci`, and
byte-reproducible collateral. The good DUT passes generated cocotb and bounded
formal collateral. Both backends kill the same six mutations:

| Mutation | Cocotb | Formal |
| --- | --- | --- |
| Discarded write | killed | killed |
| Writable RO field | killed | killed |
| Broken W1C field | killed | killed |
| Missing `HRESP` | killed | killed |
| Dropped `HREADYOUT` | killed | killed |
| Incorrect reset value | killed | killed |

The fixtures are `tests/fixtures/mutations/ahb_lite_qualified_slave.sv` and
`tests/fixtures/mutations/ahb_lite_registers.json`. CI reruns the test rather
than treating this document as a substitute for current execution evidence.
