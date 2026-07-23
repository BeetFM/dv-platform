# Stage 8 board-peripheral qualification

Status: accepted on 2026-07-22.

Stage 8 qualifies four explicit controller/subsystem profiles. A profile is
executable only when every governed signal is mapped to a unique normalized
port with the required direction and width, the clock/reset domain is known,
and all bounded numeric parameters are valid. Missing or ambiguous semantics
remain unsupported rather than falling back to name-based stimulus.

## Qualified profiles

| Profile | Executable contract | Mutation closure |
| --- | --- | --- |
| UART `bounded_controller` | 8-bit TX/RX; configurable parity and one/two stop bits; exact baud timing; idle, framing, parity, break, overflow, and clear behavior | 10/10: divisor, TX/RX order, parity, stop count, idle level, and four receive-error paths |
| SPI `bounded_master` | 8-bit master transfers; CPOL/CPHA modes 0–3; MSB/LSB-first; chip-select framing; divider, edge, receive, done, and timeout checks | 9/9: CPOL, CPHA, select, both bit orders, receive order, trailing edge, divider, and completion |
| I2C `bounded_7bit_master` | Wired-AND open-drain BFM; 7-bit address; write and combined read; START, STOP, repeated START, ACK/NACK, bounded stretch, arbitration loss, and timeout | 8/8: START, STOP, repeated START, NACK, stretch, arbitration, write serialization, and read data |
| GPIO/timer/interrupt `bounded_subsystem` | 4-bit GPIO direction, masked write/set/clear, edge/level interrupts; 8-bit prescaled periodic timer; watchdog feed/IRQ/reset; PWM period/duty/polarity; 4-source fixed-priority masked interrupt controller | 10/10: direction, mask, set, GPIO IRQ, timer compare, watchdog feed/reset, PWM rollover, priority, and interrupt-valid |

Each good DUT passes the complete `analyze-rtl -> plan -> generate -> run ->
coverage -> status --policy ci` cocotb/Icarus path. Generated formal safety and
non-vacuity collateral also passes SBY/Yosys/Z3 for every profile. UART output
is regenerated twice and compared byte-for-byte; the common deterministic
generator/provenance contract covers the other profiles.

## Evidence and reproducibility

- Contract recognition and fail-closed tests:
  `tests/formal/test_peripheral_depth.py`
- End-to-end and mutation suites:
  `tests/qualification/test_uart_peripheral_qualification.py`,
  `tests/qualification/test_spi_peripheral_qualification.py`,
  `tests/qualification/test_i2c_peripheral_qualification.py`, and
  `tests/qualification/test_gpio_timer_interrupt_qualification.py`
- Versioned mutation RTL:
  `tests/fixtures/mutations/*_bounded_qualified.sv` and
  `tests/fixtures/mutations/peripheral/gpio_timer_interrupt_qualified.sv`

The accepted local tools are Verilator 5.020, Icarus 12.0, cocotb, SBY 0.67,
Yosys 0.33, and Z3 4.8.12. CI repeats the available real-tool paths.

## Explicit exclusions

This milestone does not claim arbitrary UART word sizes or fractional baud
generators; SPI multi-lane, multi-master, or continuous streaming; I2C 10-bit
addressing, high-speed modes, multi-controller fairness, SMBus, or analog
electrical behavior; or general-purpose timer capture/compare/DMA and arbitrary
interrupt arbitration. Those capabilities require separate versioned profiles
and qualification evidence.
