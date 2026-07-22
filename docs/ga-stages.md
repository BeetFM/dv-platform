# Broad-GA stages

Stages 6 through 13 are sequential acceptance milestones. Engineering may
overlap, but a later stage cannot be accepted while an earlier stage is open.
The machine-readable source of gate status is
`qualification/ga-gates-v1.json`; prose documents may explain but never
override it.

| Stage | Milestone | Acceptance boundary |
| --- | --- | --- |
| 6 | GA foundation and security closure | Repository-controlled security, migration, release, fuzz, and reproducibility gates pass. |
| 7 | On-chip buses and streams | APB4, AXI4-Lite, bounded AHB-Lite, and paired ready/valid pass exact-check and mutation closure on every claimed target. |
| 8 | Board-peripheral protocols | UART, SPI, I2C, GPIO, timer/watchdog/PWM, and interrupt-controller profiles pass executable and mutation closure. |
| 9 | VHDL and project-level UVM closure | GHDL reset/ready-valid and paired ready/valid UVM project coverage close. |
| 10 | Semantic, scale, and platform qualification | Two unrelated designs, scale budgets, Ubuntu 24.04, and WSL2 pass. |
| 11 | Vendor adapter qualification | XSim, JasperGold, and SpyGlass have current vendor evidence. |
| 12 | Release candidate and enterprise pilots | Two pilots validate the signed `1.0.0rc1` lineage. |
| 13 | GA promotion | The metadata-only `1.0.0` promotion and final supply-chain checks pass. |

Versions remain `0.1.x`/Alpha through Stage 11. Stage 12 cuts
`1.0.0rc1` before the pilots; only Stage 13 may publish `1.0.0` with a
production classifier.

Stages 6–9 are accepted. Stage 10 is the active milestone; later stages remain
blocked by the sequential gate even when preparatory implementation exists.
