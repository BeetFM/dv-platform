"""Bounded, explicitly mapped board-peripheral verification contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeripheralSignal:
    """One required logical signal in a bounded peripheral profile."""

    name: str
    direction: str
    width: int | str = 1


@dataclass(frozen=True)
class PeripheralContract:
    """The fail-closed signal and parameter contract for one profile."""

    kind: str
    profile: str
    signals: tuple[PeripheralSignal, ...]
    integer_parameters: tuple[tuple[str, int, int], ...] = ()
    enum_parameters: tuple[tuple[str, tuple[str, ...]], ...] = ()


PERIPHERAL_CONTRACTS: dict[str, PeripheralContract] = {
    "uart": PeripheralContract(
        "uart",
        "bounded_controller",
        (
            PeripheralSignal("clock", "input"),
            PeripheralSignal("reset", "input"),
            PeripheralSignal("tx_start", "input"),
            PeripheralSignal("tx_data", "input", "data_bits"),
            PeripheralSignal("tx", "output"),
            PeripheralSignal("tx_busy", "output"),
            PeripheralSignal("rx", "input"),
            PeripheralSignal("rx_data", "output", "data_bits"),
            PeripheralSignal("rx_valid", "output"),
            PeripheralSignal("parity_mode", "input", 2),
            PeripheralSignal("stop_bits", "input"),
            PeripheralSignal("parity_error", "output"),
            PeripheralSignal("framing_error", "output"),
            PeripheralSignal("break_detect", "output"),
            PeripheralSignal("overflow", "output"),
            PeripheralSignal("rx_clear", "input"),
        ),
        (("data_bits", 8, 8), ("clocks_per_bit", 4, 64), ("max_frame_cycles", 32, 4096)),
    ),
    "spi": PeripheralContract(
        "spi",
        "bounded_master",
        (
            PeripheralSignal("clock", "input"),
            PeripheralSignal("reset", "input"),
            PeripheralSignal("start", "input"),
            PeripheralSignal("tx_data", "input", "word_bits"),
            PeripheralSignal("rx_data", "output", "word_bits"),
            PeripheralSignal("busy", "output"),
            PeripheralSignal("done", "output"),
            PeripheralSignal("sclk", "output"),
            PeripheralSignal("mosi", "output"),
            PeripheralSignal("miso", "input"),
            PeripheralSignal("cs_n", "output"),
            PeripheralSignal("mode", "input", 2),
            PeripheralSignal("lsb_first", "input"),
        ),
        (("word_bits", 8, 16), ("clock_divider", 2, 32), ("max_transfer_cycles", 32, 2048)),
    ),
    "i2c": PeripheralContract(
        "i2c",
        "bounded_7bit_master",
        (
            PeripheralSignal("clock", "input"),
            PeripheralSignal("reset", "input"),
            PeripheralSignal("start", "input"),
            PeripheralSignal("read", "input"),
            PeripheralSignal("repeated_start", "input"),
            PeripheralSignal("address", "input", 7),
            PeripheralSignal("write_data", "input", 8),
            PeripheralSignal("read_data", "output", 8),
            PeripheralSignal("read_valid", "output"),
            PeripheralSignal("busy", "output"),
            PeripheralSignal("done", "output"),
            PeripheralSignal("ack_error", "output"),
            PeripheralSignal("arbitration_lost", "output"),
            PeripheralSignal("sda_drive_low", "output"),
            PeripheralSignal("sda_in", "input"),
            PeripheralSignal("scl_drive_low", "output"),
            PeripheralSignal("scl_in", "input"),
        ),
        (("clock_divider", 2, 32), ("max_stretch_cycles", 1, 256), ("max_transfer_cycles", 64, 4096)),
    ),
    "gpio_timer_interrupt": PeripheralContract(
        "gpio_timer_interrupt",
        "bounded_subsystem",
        (
            PeripheralSignal("clock", "input"),
            PeripheralSignal("reset", "input"),
            PeripheralSignal("gpio_input", "input", "width"),
            PeripheralSignal("gpio_output", "output", "width"),
            PeripheralSignal("gpio_output_enable", "output", "width"),
            PeripheralSignal("gpio_write", "input"),
            PeripheralSignal("gpio_write_data", "input", "width"),
            PeripheralSignal("gpio_write_mask", "input", "width"),
            PeripheralSignal("gpio_set", "input", "width"),
            PeripheralSignal("gpio_clear", "input", "width"),
            PeripheralSignal("gpio_direction", "input", "width"),
            PeripheralSignal("gpio_rise_enable", "input", "width"),
            PeripheralSignal("gpio_fall_enable", "input", "width"),
            PeripheralSignal("gpio_level_enable", "input", "width"),
            PeripheralSignal("gpio_irq_pending", "output", "width"),
            PeripheralSignal("gpio_irq_clear", "input", "width"),
            PeripheralSignal("timer_enable", "input"),
            PeripheralSignal("timer_prescaler", "input", 8),
            PeripheralSignal("timer_compare", "input", "counter_width"),
            PeripheralSignal("timer_periodic", "input"),
            PeripheralSignal("timer_count", "output", "counter_width"),
            PeripheralSignal("timer_irq", "output"),
            PeripheralSignal("timer_irq_clear", "input"),
            PeripheralSignal("watchdog_enable", "input"),
            PeripheralSignal("watchdog_feed", "input"),
            PeripheralSignal("watchdog_timeout", "input", "counter_width"),
            PeripheralSignal("watchdog_irq", "output"),
            PeripheralSignal("watchdog_reset", "output"),
            PeripheralSignal("pwm_enable", "input"),
            PeripheralSignal("pwm_period", "input", "counter_width"),
            PeripheralSignal("pwm_duty", "input", "counter_width"),
            PeripheralSignal("pwm_polarity", "input"),
            PeripheralSignal("pwm_output", "output"),
            PeripheralSignal("interrupt_sources", "input", "irq_sources"),
            PeripheralSignal("interrupt_mask", "input", "irq_sources"),
            PeripheralSignal("interrupt_clear", "input", "irq_sources"),
            PeripheralSignal("interrupt_pending", "output", "irq_sources"),
            PeripheralSignal("interrupt_ack", "input"),
            PeripheralSignal("interrupt_active", "output", "irq_index_width"),
            PeripheralSignal("interrupt_valid", "output"),
        ),
        (("width", 2, 32), ("counter_width", 4, 32), ("irq_sources", 2, 32), ("max_event_cycles", 8, 4096)),
        (("priority", ("fixed_low",)),),
    ),
}

PERIPHERAL_PROFILE_CONTRACTS: dict[tuple[str, str], PeripheralContract] = {
    **{(kind, contract.profile): contract for kind, contract in PERIPHERAL_CONTRACTS.items()},
    (
        "uart",
        "fractional_baud_8bit",
    ): PeripheralContract(
        "uart",
        "fractional_baud_8bit",
        PERIPHERAL_CONTRACTS["uart"].signals,
        (
            ("data_bits", 8, 8),
            ("baud_numerator", 1, 65535),
            ("baud_denominator", 2, 65535),
            ("max_frame_cycles", 32, 65536),
        ),
    ),
    (
        "i2c",
        "bounded_10bit_master",
    ): PeripheralContract(
        "i2c",
        "bounded_10bit_master",
        tuple(
            PeripheralSignal(signal.name, signal.direction, 10 if signal.name == "address" else signal.width)
            for signal in PERIPHERAL_CONTRACTS["i2c"].signals
        ),
        PERIPHERAL_CONTRACTS["i2c"].integer_parameters,
    ),
    (
        "spi",
        "bounded_dual_1_2_2_master",
    ): PeripheralContract(
        "spi",
        "bounded_dual_1_2_2_master",
        tuple(signal for signal in PERIPHERAL_CONTRACTS["spi"].signals if signal.name not in {"mosi", "miso"})
        + (
            PeripheralSignal("io0_out", "output"),
            PeripheralSignal("io0_in", "input"),
            PeripheralSignal("io0_output_enable", "output"),
            PeripheralSignal("io1_out", "output"),
            PeripheralSignal("io1_in", "input"),
            PeripheralSignal("io1_output_enable", "output"),
        ),
        PERIPHERAL_CONTRACTS["spi"].integer_parameters,
        (("bit_order", ("msb_first", "lsb_first")),),
    ),
}


def peripheral_parameter_names(contract: PeripheralContract) -> set[str]:
    """Return every permitted parameter key for a peripheral policy."""

    return {
        "profile",
        *(signal.name for signal in contract.signals),
        *(name for name, _minimum, _maximum in contract.integer_parameters),
        *(name for name, _values in contract.enum_parameters),
    }


for _value in tuple(globals().values()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.core.peripherals"
del _value
