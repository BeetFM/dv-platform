"""Executable collateral for explicitly configured bounded board peripherals."""

from __future__ import annotations

from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable


def cocotb_peripheral_scenario_lines(plan: VerificationPlan) -> list[str]:
    """Render every qualified peripheral scenario as a named cocotb test."""

    lines: list[str] = []
    for scenario in plan.scenarios:
        if not scenario_is_executable(scenario, VerificationTarget.COCOTB):
            continue
        parameters = dict(scenario.stimulus[0].parameters)
        suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
        if scenario.kind == "uart_bounded":
            lines.extend(_cocotb_uart_lines(plan.module, suffix, parameters))
        elif scenario.kind == "spi_bounded":
            lines.extend(_cocotb_spi_lines(plan.module, suffix, parameters))
        elif scenario.kind == "i2c_bounded":
            lines.extend(_cocotb_i2c_lines(plan.module, suffix, parameters))
        elif scenario.kind == "gpio_timer_interrupt_bounded":
            lines.extend(_cocotb_gpio_timer_interrupt_lines(plan.module, suffix, parameters))
    return lines


def _cocotb_uart_lines(module: str, suffix: str, p: dict[str, str]) -> list[str]:
    fractional = p.get("profile") == "fractional_baud_8bit"
    numerator = int(p.get("baud_numerator", "1"))
    denominator = int(p.get("baud_denominator", p.get("clocks_per_bit", "1")))
    cpb = (denominator + numerator - 1) // numerator
    timeout = int(p["max_frame_cycles"])
    name = _safe_identifier(module)
    return [
        "",
        "",
        "@cocotb.test()",
        f"async def test_{name}_scenario_{suffix}(dut):",
        '    """Qualify bounded UART TX/RX timing, errors, and recovery."""',
        f"    p = {p!r}",
        f"    cpb = {cpb}",
        f"    baud_numerator = {numerator}",
        f"    baud_denominator = {denominator}",
        f"    fractional_baud = {fractional!r}",
        "    baud_accumulator = 0",
        f"    timeout = {timeout}",
        "    clock = getattr(dut, p['clock'])",
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    for logical in ('tx_start', 'tx_data', 'rx', 'parity_mode', 'stop_bits', 'rx_clear'):",
        "        getattr(dut, p[logical]).value = 1 if logical == 'rx' else 0",
        "    await _peripheral_reset(dut, p, clock)",
        "",
        "    async def cycles(count):",
        "        for _ in range(count):",
        "            await _sample_cycle(clock)",
        "",
        "    async def bit_cycles():",
        "        nonlocal baud_accumulator",
        "        while True:",
        "            await _sample_cycle(clock)",
        "            baud_accumulator += baud_numerator",
        "            if baud_accumulator >= baud_denominator:",
        "                baud_accumulator -= baud_denominator",
        "                return",
        "",
        "    async def pulse(logical):",
        "        getattr(dut, p[logical]).value = 1",
        "        await _sample_cycle(clock)",
        "        getattr(dut, p[logical]).value = 0",
        "",
        "    async def wait_value(logical, value):",
        "        for _ in range(timeout):",
        "            if _signal_int(dut, p[logical]) == value:",
        "                return",
        "            await _sample_cycle(clock)",
        '        raise AssertionError(f"UART timeout waiting for {logical}={value}")',
        "",
        "    def parity_bit(value, mode):",
        "        ones = sum((value >> bit) & 1 for bit in range(8))",
        "        return (ones & 1) if mode == 1 else (1 - (ones & 1))",
        "",
        "    async def check_tx(value, mode, two_stops):",
        "        getattr(dut, p['tx_data']).value = value",
        "        getattr(dut, p['parity_mode']).value = mode",
        "        getattr(dut, p['stop_bits']).value = two_stops",
        "        await pulse('tx_start')",
        "        await wait_value('tx_busy', 1)",
        "        expected = [0] + [(value >> bit) & 1 for bit in range(8)]",
        "        if mode:",
        "            expected.append(parity_bit(value, mode))",
        "        expected += [1] * (2 if two_stops else 1)",
        "        for index, bit in enumerate(expected):",
        "            if index:",
        "                await bit_cycles()",
        "            assert _signal_int(dut, p['tx']) == bit, f'UART TX bit {index} expected {bit}'",
        "            assert _signal_int(dut, p['tx_busy']) == 1, f'UART TX busy dropped at bit {index}'",
        "        await wait_value('tx_busy', 0)",
        "        assert _signal_int(dut, p['tx']) == 1, 'UART TX did not return idle high'",
        "",
        "    async def send_rx(value, mode=0, two_stops=0, bad_parity=False, bad_stop=False):",
        "        getattr(dut, p['parity_mode']).value = mode",
        "        getattr(dut, p['stop_bits']).value = two_stops",
        "        bits = [0] + [(value >> bit) & 1 for bit in range(8)]",
        "        if mode:",
        "            parity = parity_bit(value, mode)",
        "            bits.append(1 - parity if bad_parity else parity)",
        "        bits += [0 if bad_stop else 1] * (2 if two_stops else 1)",
        "        for bit in bits:",
        "            getattr(dut, p['rx']).value = bit",
        "            await bit_cycles()",
        "        getattr(dut, p['rx']).value = 1",
        "        await bit_cycles()",
        "",
        "    for value, mode, two_stops in ((0xA5, 0, 0), (0x3C, 1, 0), (0x96, 2, 1)):",
        "        await check_tx(value, mode, two_stops)",
        "",
        "    await send_rx(0x53)",
        "    await wait_value('rx_valid', 1)",
        "    assert _signal_int(dut, p['rx_data']) == 0x53, 'UART RX data ordering mismatch'",
        "    assert _signal_int(dut, p['parity_error']) == 0",
        "    assert _signal_int(dut, p['framing_error']) == 0",
        "    await pulse('rx_clear')",
        "",
        "    await send_rx(0x69, mode=1, bad_parity=True)",
        "    await wait_value('rx_valid', 1)",
        "    assert _signal_int(dut, p['parity_error']) == 1, 'UART bad parity was not reported'",
        "    await pulse('rx_clear')",
        "    await send_rx(0x33, bad_stop=True)",
        "    await wait_value('rx_valid', 1)",
        "    assert _signal_int(dut, p['framing_error']) == 1, 'UART bad stop bit was not reported'",
        "    await pulse('rx_clear')",
        "",
        "    getattr(dut, p['rx']).value = 0",
        "    for _ in range(12):",
        "        await bit_cycles()",
        "    assert _signal_int(dut, p['break_detect']) == 1, 'UART break was not detected'",
        "    getattr(dut, p['rx']).value = 1",
        "    await pulse('rx_clear')",
        "    await send_rx(0x11)",
        "    await send_rx(0x22)",
        "    assert _signal_int(dut, p['overflow']) == 1, 'UART uncleared receive overflow was not reported'",
        "",
        "    getattr(dut, p['reset']).value = 0",
        "    await cycles(2)",
        "    assert _signal_int(dut, p['tx']) == 1",
        "    assert _signal_int(dut, p['tx_busy']) == 0",
        "    assert _signal_int(dut, p['rx_valid']) == 0",
        "    getattr(dut, p['reset']).value = 1",
        "    await cycles(2)",
        "    await check_tx(0xC3, 0, 0)",
    ]


def _cocotb_spi_lines(module: str, suffix: str, p: dict[str, str]) -> list[str]:
    name = _safe_identifier(module)
    return [
        "",
        "",
        "@cocotb.test()",
        f"async def test_{name}_scenario_{suffix}(dut):",
        '    """Qualify SPI modes, chip select, and both bit orders."""',
        f"    p = {p!r}",
        "    clock = getattr(dut, p['clock'])",
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    for logical in ('start', 'tx_data', 'miso', 'mode', 'lsb_first'):",
        "        getattr(dut, p[logical]).value = 0",
        "    await _peripheral_reset(dut, p, clock)",
        "    word_bits = int(p['word_bits'])",
        "    timeout = int(p['max_transfer_cycles'])",
        "    dual = p.get('profile') == 'bounded_dual_1_2_2_master'",
        "    serial_out = p['io0_out'] if dual else p['mosi']",
        "    serial_in = p['io1_in'] if dual else p['miso']",
        "",
        "    async def transfer(mode, lsb_first, tx_value, rx_value):",
        "        getattr(dut, p['mode']).value = mode",
        "        getattr(dut, p['lsb_first']).value = lsb_first",
        "        getattr(dut, p['tx_data']).value = tx_value",
        "        idle = (mode >> 1) & 1",
        "        first_rx_index = 0 if lsb_first else word_bits - 1",
        "        getattr(dut, serial_in).value = (rx_value >> first_rx_index) & 1",
        "        await _sample_cycle(clock)",
        "        assert _signal_int(dut, p['sclk']) == idle",
        "        assert _signal_int(dut, p['cs_n']) == 1",
        "        getattr(dut, p['start']).value = 1",
        "        await _sample_cycle(clock)",
        "        assert _signal_int(dut, p['done']) == 0, 'SPI done asserted before any serial edge'",
        "        getattr(dut, p['start']).value = 0",
        "        observed = []",
        "        previous = _signal_int(dut, p['sclk'])",
        "        previous_cs = _signal_int(dut, p['cs_n'])",
        "        rx_index = 0 if (mode & 1) else 1",
        "        cycles_since_edge = 0",
        "        for _ in range(timeout):",
        "            await _sample_cycle(clock)",
        "            cycles_since_edge += 1",
        "            current = _signal_int(dut, p['sclk'])",
        "            cs = _signal_int(dut, p['cs_n'])",
        "            if (cs == 0 or previous_cs == 0) and current != previous:",
        "                assert cycles_since_edge == int(p['clock_divider']), 'SPI clock divider mismatch'",
        "                cycles_since_edge = 0",
        "                leading = previous == idle and current != idle",
        "                sample_edge = leading if (mode & 1) == 0 else not leading",
        "                if sample_edge:",
        "                    observed.append(_signal_int(dut, serial_out))",
        "                else:",
        "                    if rx_index < word_bits:",
        "                        bit_index = rx_index if lsb_first else word_bits - 1 - rx_index",
        "                        getattr(dut, serial_in).value = (rx_value >> bit_index) & 1",
        "                        rx_index += 1",
        "            previous = current",
        "            previous_cs = cs",
        "            if _signal_int(dut, p['done']) == 1:",
        "                break",
        "        else:",
        "            raise AssertionError('SPI transfer timed out')",
        "        expected = [(tx_value >> (bit if lsb_first else word_bits - 1 - bit)) & 1 for bit in range(word_bits)]",
        "        assert observed == expected, f'SPI sampled MOSI {observed}, expected {expected}'",
        "        assert _signal_int(dut, p['rx_data']) == rx_value",
        "        await _sample_cycle(clock)",
        "        assert _signal_int(dut, p['cs_n']) == 1, 'SPI CS did not deassert after the final edge'",
        "        assert _signal_int(dut, p['sclk']) == idle, 'SPI clock did not return to CPOL'",
        "        if dual:",
        "            assert _signal_int(dut, p['io0_output_enable']) in (0, 1)",
        "            assert _signal_int(dut, p['io1_output_enable']) in (0, 1)",
        "",
        "    for mode in range(4):",
        "        await transfer(mode, 0, 0xA6, 0x3C)",
        "        await transfer(mode, 1, 0x69, 0xC3)",
    ]


def _cocotb_i2c_lines(module: str, suffix: str, p: dict[str, str]) -> list[str]:
    name = _safe_identifier(module)
    return [
        "",
        "",
        "@cocotb.test()",
        f"async def test_{name}_scenario_{suffix}(dut):",
        '    """Qualify open-drain I2C transactions, stretching, NACK, and arbitration."""',
        f"    p = {p!r}",
        "    clock = getattr(dut, p['clock'])",
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    for logical in ('start', 'read', 'repeated_start', 'address', 'write_data'):",
        "        getattr(dut, p[logical]).value = 0",
        "    getattr(dut, p['sda_in']).value = 1",
        "    getattr(dut, p['scl_in']).value = 1",
        "    await _peripheral_reset(dut, p, clock)",
        "    timeout = int(p['max_transfer_cycles'])",
        "    ten_bit = p.get('profile') == 'bounded_10bit_master'",
        "    test_address = 0x2A5 if ten_bit else 0x52",
        "",
        "    async def launch(read=False, repeated=False):",
        "        getattr(dut, p['read']).value = int(read)",
        "        getattr(dut, p['repeated_start']).value = int(repeated)",
        "        getattr(dut, p['address']).value = test_address",
        "        getattr(dut, p['write_data']).value = 0xA5",
        "        getattr(dut, p['start']).value = 1",
        "        await _sample_cycle(clock)",
        "        getattr(dut, p['start']).value = 0",
        "",
        "    async def run_bus(*, nack=False, stretch=0, arbitrate=False, repeated=False):",
        "        await launch(read=repeated, repeated=repeated)",
        "        start_count = 0",
        "        saw_stop = False",
        "        previous_sda = previous_scl = 1",
        "        previous_master_scl = 1",
        "        high_bits = 0",
        "        segment_edges = 0",
        "        stretched = 0",
        "        stretch_active = False",
        "        stretch_used = False",
        "        arbitration_injected = False",
        "        captured = []",
        "        address_bits = 16 if ten_bit else 8",
        "        expected_capture_count = address_bits if (nack or repeated) else address_bits + 8",
        "        slave_read_data = 0x3C",
        "        ack_holding = False",
        "        read_bit_holding = False",
        "        read_bit_value = 1",
        "        arbitration_seen = False",
        "        for _ in range(timeout):",
        "            master_sda = 0 if _signal_int(dut, p['sda_drive_low']) else 1",
        "            master_scl = 0 if _signal_int(dut, p['scl_drive_low']) else 1",
        "            if stretch and not stretch_used and previous_master_scl == 0 and master_scl == 1 and high_bits >= 2:",
        "                stretch_active = True",
        "                stretch_used = True",
        "            slave_scl = 0 if stretch_active else 1",
        "            if stretch_active:",
        "                stretched += 1",
        "                if stretched >= stretch:",
        "                    stretch_active = False",
        "            slave_sda = 1",
        "            if not master_scl:",
        "                ack_holding = False",
        "                read_bit_holding = False",
        "            ack_edge = (segment_edges % 9 == 8) if ten_bit else (segment_edges == (10 if (repeated and start_count >= 2) else (8 if segment_edges < 9 else 17)))",
        "            if master_scl and previous_scl == 0 and ack_edge:",
        "                ack_holding = True",
        "            if ack_holding:",
        "                slave_sda = 1 if nack else 0",
        "            if repeated and master_scl and previous_scl == 0 and 11 <= segment_edges < 19:",
        "                read_bit_holding = True",
        "                read_bit_value = (slave_read_data >> (18 - segment_edges)) & 1",
        "            if read_bit_holding:",
        "                slave_sda = read_bit_value",
        "            if arbitrate and master_scl and segment_edges >= 1 and master_sda == 1 and not arbitration_injected:",
        "                slave_sda = 0",
        "                arbitration_injected = True",
        "            bus_sda = master_sda & slave_sda",
        "            bus_scl = master_scl & slave_scl",
        "            getattr(dut, p['sda_in']).value = bus_sda",
        "            getattr(dut, p['scl_in']).value = bus_scl",
        "            if previous_sda == 1 and bus_sda == 0 and bus_scl == 1:",
        "                if repeated and start_count == 1:",
        "                    captured = captured[:address_bits]",
        "                    segment_edges = 0",
        "                start_count += 1",
        "            if previous_sda == 0 and bus_sda == 1 and bus_scl == 1:",
        "                saw_stop = True",
        "            if previous_scl == 0 and bus_scl == 1:",
        "                capture_edge = (segment_edges % 9 < 8) if ten_bit else (segment_edges < 8 or (not repeated and 9 <= segment_edges < 17))",
        "                if len(captured) < expected_capture_count and capture_edge:",
        "                    captured.append(master_sda)",
        "                high_bits += 1",
        "                segment_edges += 1",
        "            previous_sda, previous_scl = bus_sda, bus_scl",
        "            previous_master_scl = master_scl",
        "            await _sample_cycle(clock)",
        "            assert _signal_int(dut, p['sda_drive_low']) in (0, 1)",
        "            assert _signal_int(dut, p['scl_drive_low']) in (0, 1)",
        "            if _signal_int(dut, p['done']) or _signal_int(dut, p['arbitration_lost']):",
        "                arbitration_seen = bool(_signal_int(dut, p['arbitration_lost']))",
        "                break",
        "        if previous_sda == 0 and not _signal_int(dut, p['sda_drive_low']) and not _signal_int(dut, p['scl_drive_low']):",
        "            saw_stop = True",
        "        getattr(dut, p['sda_in']).value = 1",
        "        getattr(dut, p['scl_in']).value = 1",
        "        await _sample_cycle(clock)",
        "        assert start_count >= (2 if repeated else 1), 'I2C START/repeated START was not observed'",
        "        if not arbitrate:",
        "            assert saw_stop, 'I2C STOP was not observed'",
        "            prefix_write = 0xF0 | ((test_address >> 7) & 0x06)",
        "            address_bytes = (prefix_write, test_address & 0xFF) if ten_bit else (test_address << 1,)",
        "            address_write = [((byte >> bit) & 1) for byte in address_bytes for bit in range(7, -1, -1)]",
        "            expected = address_write",
        "            if repeated:",
        "                assert captured[:address_bits] == address_write, 'I2C repeated transaction address mismatch'",
        "            elif not nack:",
        "                expected += [(0xA5 >> bit) & 1 for bit in range(7, -1, -1)]",
        "            if not repeated:",
        "                assert captured == expected, f'I2C serialized bits {captured}, expected {expected}'",
        "        return stretched, arbitration_seen",
        "",
        "    getattr(dut, p['sda_in']).value = 0",
        "    getattr(dut, p['scl_in']).value = 1",
        "    await launch()",
        "    await _sample_cycle(clock)",
        "    assert _signal_int(dut, p['busy']) == 0, 'I2C controller started while bus was busy'",
        "    assert _signal_int(dut, p['sda_drive_low']) == 0",
        "    getattr(dut, p['sda_in']).value = 1",
        "",
        "    stretched, _ = await run_bus(stretch=3)",
        "    assert stretched >= 3, 'I2C controller ignored clock stretching'",
        "    assert _signal_int(dut, p['ack_error']) == 0",
        "    await run_bus(nack=True)",
        "    assert _signal_int(dut, p['ack_error']) == 1, 'I2C NACK was not reported'",
        "    _, arbitration_seen = await run_bus(arbitrate=True)",
        "    assert arbitration_seen, 'I2C arbitration loss was not reported'",
        "    await run_bus(repeated=True)",
        "    assert _signal_int(dut, p['read_valid']) == 1, f\"I2C read did not complete: ack={_signal_int(dut, p['ack_error'])} arbitration={_signal_int(dut, p['arbitration_lost'])} busy={_signal_int(dut, p['busy'])} done={_signal_int(dut, p['done'])}\"",
        "    assert _signal_int(dut, p['read_data']) == 0x3C, f\"I2C read data mismatch: {_signal_int(dut, p['read_data']):#x}\"",
        "    getattr(dut, p['reset']).value = 0",
        "    await _sample_cycle(clock)",
        "    assert _signal_int(dut, p['sda_drive_low']) == 0",
        "    assert _signal_int(dut, p['scl_drive_low']) == 0",
    ]


def _cocotb_gpio_timer_interrupt_lines(module: str, suffix: str, p: dict[str, str]) -> list[str]:
    name = _safe_identifier(module)
    return [
        "",
        "",
        "@cocotb.test()",
        f"async def test_{name}_scenario_{suffix}(dut):",
        '    """Qualify GPIO, timer, watchdog, PWM, and interrupt-controller behavior."""',
        f"    p = {p!r}",
        "    clock = getattr(dut, p['clock'])",
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    driven = ('gpio_input','gpio_write','gpio_write_data','gpio_write_mask','gpio_set','gpio_clear',",
        "              'gpio_direction','gpio_rise_enable','gpio_fall_enable','gpio_level_enable','gpio_irq_clear',",
        "              'timer_enable','timer_prescaler','timer_compare','timer_periodic','timer_irq_clear',",
        "              'watchdog_enable','watchdog_feed','watchdog_timeout','pwm_enable','pwm_period','pwm_duty',",
        "              'pwm_polarity','interrupt_sources','interrupt_mask','interrupt_clear','interrupt_ack')",
        "    for logical in driven:",
        "        getattr(dut, p[logical]).value = 0",
        "    await _peripheral_reset(dut, p, clock)",
        "",
        "    async def cycle(count=1):",
        "        for _ in range(count):",
        "            await _sample_cycle(clock)",
        "",
        "    getattr(dut, p['gpio_direction']).value = 0b1010",
        "    await cycle()",
        "    assert _signal_int(dut, p['gpio_output_enable']) == 0b1010",
        "    getattr(dut, p['gpio_write_data']).value = 0b1111",
        "    getattr(dut, p['gpio_write_mask']).value = 0b0101",
        "    getattr(dut, p['gpio_write']).value = 1",
        "    await cycle()",
        "    getattr(dut, p['gpio_write']).value = 0",
        "    assert _signal_int(dut, p['gpio_output']) == 0b0101",
        "    getattr(dut, p['gpio_set']).value = 0b1000",
        "    await cycle()",
        "    getattr(dut, p['gpio_set']).value = 0",
        "    getattr(dut, p['gpio_clear']).value = 0b0001",
        "    await cycle()",
        "    getattr(dut, p['gpio_clear']).value = 0",
        "    assert _signal_int(dut, p['gpio_output']) == 0b1100",
        "",
        "    getattr(dut, p['gpio_rise_enable']).value = 1",
        "    getattr(dut, p['gpio_fall_enable']).value = 2",
        "    getattr(dut, p['gpio_level_enable']).value = 4",
        "    getattr(dut, p['gpio_input']).value = 0",
        "    await cycle()",
        "    getattr(dut, p['gpio_input']).value = 0b0111",
        "    await cycle()",
        "    getattr(dut, p['gpio_input']).value = 0b0101",
        "    await cycle()",
        "    assert _signal_int(dut, p['gpio_irq_pending']) & 0b0111 == 0b0111",
        "    getattr(dut, p['gpio_irq_clear']).value = 0b0011",
        "    await cycle()",
        "    assert _signal_int(dut, p['gpio_irq_pending']) & 0b0011 == 0",
        "",
        "    getattr(dut, p['timer_prescaler']).value = 1",
        "    getattr(dut, p['timer_compare']).value = 3",
        "    getattr(dut, p['timer_periodic']).value = 1",
        "    getattr(dut, p['timer_enable']).value = 1",
        "    await cycle(8)",
        "    assert _signal_int(dut, p['timer_irq']) == 1, 'timer compare did not interrupt'",
        "    assert _signal_int(dut, p['timer_count']) < 3, 'periodic timer did not roll over'",
        "    getattr(dut, p['timer_irq_clear']).value = 1",
        "    await cycle()",
        "    getattr(dut, p['timer_irq_clear']).value = 0",
        "",
        "    getattr(dut, p['watchdog_timeout']).value = 4",
        "    getattr(dut, p['watchdog_enable']).value = 1",
        "    await cycle(2)",
        "    getattr(dut, p['watchdog_feed']).value = 1",
        "    await cycle()",
        "    getattr(dut, p['watchdog_feed']).value = 0",
        "    await cycle(3)",
        "    assert _signal_int(dut, p['watchdog_reset']) == 0, 'watchdog fired despite feed'",
        "    await cycle(3)",
        "    assert _signal_int(dut, p['watchdog_irq']) == 1",
        "    assert _signal_int(dut, p['watchdog_reset']) == 1",
        "",
        "    getattr(dut, p['pwm_period']).value = 4",
        "    getattr(dut, p['pwm_duty']).value = 2",
        "    getattr(dut, p['pwm_enable']).value = 1",
        "    samples = []",
        "    for _ in range(8):",
        "        await cycle()",
        "        samples.append(_signal_int(dut, p['pwm_output']))",
        "    assert 0 in samples and 1 in samples, 'PWM did not produce bounded duty cycle'",
        "    assert sum(samples) == 4, f'PWM duty/rollover mismatch: {samples}'",
        "    getattr(dut, p['pwm_duty']).value = 4",
        "    getattr(dut, p['pwm_polarity']).value = 1",
        "    await cycle()",
        "    inverted = _signal_int(dut, p['pwm_output'])",
        "    getattr(dut, p['pwm_polarity']).value = 0",
        "    await cycle()",
        "    assert inverted != _signal_int(dut, p['pwm_output']), 'PWM polarity had no effect'",
        "",
        "    getattr(dut, p['interrupt_sources']).value = 0b1110",
        "    getattr(dut, p['interrupt_mask']).value = 0b1010",
        "    await cycle()",
        "    assert _signal_int(dut, p['interrupt_pending']) & 0b1010 == 0b1010",
        "    assert _signal_int(dut, p['interrupt_valid']) == 1",
        "    assert _signal_int(dut, p['interrupt_active']) == 1, 'fixed-low priority selected wrong source'",
        "    getattr(dut, p['interrupt_sources']).value = 0b1000",
        "    getattr(dut, p['interrupt_clear']).value = 0b0010",
        "    getattr(dut, p['interrupt_ack']).value = 1",
        "    await cycle()",
        "    assert _signal_int(dut, p['interrupt_active']) == 3, 'interrupt clear did not expose next source'",
    ]


def cocotb_peripheral_helper_lines() -> list[str]:
    """Return helpers shared by all generated peripheral tests."""

    return [
        "",
        "",
        "async def _peripheral_reset(dut, profile, clock):",
        "    reset = getattr(dut, profile['reset'])",
        "    reset.value = 0",
        "    await _sample_cycle(clock)",
        "    await _sample_cycle(clock)",
        "    reset.value = 1",
        "    await _sample_cycle(clock)",
    ]


def formal_peripheral_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    """Return outputs that must be connected for executable peripheral properties."""

    signals: list[str] = []
    output_names = {port.name for port in plan.ports if port.direction == "output"}
    for scenario in plan.scenarios:
        if not scenario_is_executable(scenario, VerificationTarget.FORMAL) or not scenario.kind.endswith("_bounded"):
            continue
        parameters = dict(scenario.stimulus[0].parameters)
        signals.extend(value for value in parameters.values() if value in output_names)
    return tuple(dict.fromkeys(signals))


def peripheral_mapped_outputs(plan: VerificationPlan) -> tuple[str, ...]:
    """Return explicitly mapped peripheral output ports for generic-check exclusion."""

    output_names = {port.name for port in plan.ports if port.direction == "output"}
    kinds = {"uart", "spi", "i2c", "gpio_timer_interrupt"}
    return tuple(
        dict.fromkeys(
            value
            for policy in plan.depth_policies
            if policy.kind in kinds
            for _name, value in policy.parameters
            if value in output_names
        )
    )


def formal_peripheral_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
) -> list[str]:
    """Emit bounded signal-level safety properties and non-vacuity covers."""

    lines: list[str] = []
    for index, scenario in enumerate(plan.scenarios, start=1):
        if not scenario_is_executable(scenario, VerificationTarget.FORMAL):
            continue
        p = dict(scenario.stimulus[0].parameters)
        if scenario.kind == "uart_bounded":
            tx, busy, start = p["tx"], p["tx_busy"], p["tx_start"]
            rx_valid = p["rx_valid"]
            guard = _formal_guard(reset_name, reset_inactive)
            lines.extend(
                (
                    f"        a_uart_{index}_idle_high: assert({busy} || {tx});",
                    f"        if (!$initstate{guard} && !$past({busy}) && {busy}) begin",
                    f"            a_uart_{index}_start_low: assert(!{tx});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({rx_valid}) && !$past({p['rx_clear']})) begin",
                    f"            a_uart_{index}_rx_sticky: assert({rx_valid} || {p['overflow']});",
                    "        end",
                    f"        a_uart_{index}_exclusive_errors: assert(!({p['parity_error']} && {p['framing_error']}));",
                    f"        c_uart_{index}_tx: cover({start} && !{busy});",
                    f"        c_uart_{index}_busy: cover({busy} && !{tx});",
                    f"        c_uart_{index}_rx_stimulus: cover(!{p['rx']});",
                    f"        c_uart_{index}_break_stimulus: cover(!$initstate && !$past({p['rx']}) && !{p['rx']});",
                    f"        c_uart_{index}_clear_stimulus: cover({p['rx_clear']});",
                )
            )
            if p.get("profile") == "fractional_baud_8bit":
                lines.extend(
                    (
                        f"        a_uart_{index}_fractional_bounds: "
                        f"assert({int(p['baud_numerator'])} < {int(p['baud_denominator'])});",
                        f"        c_uart_{index}_fractional_frame: cover({start} && !{busy});",
                    )
                )
        elif scenario.kind == "spi_bounded":
            busy, cs_n, sclk, mode = p["busy"], p["cs_n"], p["sclk"], p["mode"]
            guard = _formal_guard(reset_name, reset_inactive)
            lines.extend(
                (
                    f"        a_spi_{index}_idle_cs: assert({busy} || {cs_n});",
                    f"        a_spi_{index}_active_cs: assert(!{busy} || !{cs_n});",
                    f"        if (!$initstate && !{busy}) begin",
                    f"            a_spi_{index}_idle_cpol: assert({sclk} == $past({mode}[1]));",
                    "        end",
                    f"        if ({busy}) assume($stable({mode}) && $stable({p['lsb_first']}) && $stable({p['tx_data']}));",
                    f"        if (!$initstate{guard} && {p['done']}) begin",
                    f"            a_spi_{index}_done_after_busy: assert($past({busy}));",
                    "        end",
                    f"        c_spi_{index}_mode0: cover({p['start']} && {mode} == 0);",
                    f"        c_spi_{index}_mode1: cover({p['start']} && {mode} == 1);",
                    f"        c_spi_{index}_mode2: cover({p['start']} && {mode} == 2);",
                    f"        c_spi_{index}_mode3: cover({p['start']} && {mode} == 3);",
                    f"        c_spi_{index}_lsb: cover({busy} && {p['lsb_first']});",
                )
            )
            if p.get("profile") == "bounded_dual_1_2_2_master":
                lines.extend(
                    (
                        f"        a_spi_{index}_dual_io0_direction: assert(!{busy} || {p['io0_output_enable']});",
                        f"        a_spi_{index}_dual_no_contention: "
                        f"assert(!({p['io0_output_enable']} && {p['io1_output_enable']}));",
                        f"        c_spi_{index}_dual_turnaround: "
                        f"cover(!$initstate && $past({p['io1_output_enable']}) != {p['io1_output_enable']});",
                    )
                )
        elif scenario.kind == "i2c_bounded":
            busy = p["busy"]
            guard = _formal_guard(reset_name, reset_inactive)
            lines.extend(
                (
                    f"        if ({p['sda_drive_low']}) assume(!{p['sda_in']});",
                    f"        if ({p['scl_drive_low']}) assume(!{p['scl_in']});",
                    f"        if (!$initstate{guard} && !{p['scl_drive_low']} && !{p['scl_in']} && $past({busy} && !{p['scl_drive_low']} && !{p['scl_in']})) begin",
                    f"            a_i2c_{index}_stretch_holds_sda: assert({p['sda_drive_low']} == $past({p['sda_drive_low']}));",
                    "        end",
                    f"        if (!$initstate{guard} && $past({busy} && !{p['sda_drive_low']} && !{p['sda_in']} && {p['scl_in']})) begin",
                    f"            a_i2c_{index}_arbitration: assert({p['arbitration_lost']} || !{busy});",
                    "        end",
                    f"        a_i2c_{index}_lost_releases_bus: assert(!{p['arbitration_lost']} || (!{p['sda_drive_low']} && !{p['scl_drive_low']}));",
                    f"        c_i2c_{index}_start: cover({p['start']} && !{busy});",
                    f"        c_i2c_{index}_stretch: cover({busy} && !{p['scl_drive_low']} && !{p['scl_in']});",
                    f"        c_i2c_{index}_nack_stimulus: cover({busy} && !{p['sda_in']} && {p['scl_in']});",
                    f"        c_i2c_{index}_arbitration: cover({p['arbitration_lost']});",
                )
            )
            if p.get("profile") == "bounded_10bit_master":
                lines.extend(
                    (
                        f"        if ({p['start']}) assume({p['address']} >= 10'h100);",
                        f"        c_i2c_{index}_10bit_repeated_start: "
                        f"cover({p['start']} && {p['read']} && {p['repeated_start']});",
                    )
                )
        elif scenario.kind == "gpio_timer_interrupt_bounded":
            guard = _formal_guard(reset_name, reset_inactive)
            lines.extend(
                (
                    f"        a_gpio_{index}_direction: assert({p['gpio_output_enable']} == {p['gpio_direction']});",
                    f"        if (!$initstate{guard} && $past({p['gpio_write']} && !|{p['gpio_set']} && !|{p['gpio_clear']})) begin",
                    f"            a_gpio_{index}_masked_write: assert((({p['gpio_output']} ^ $past({p['gpio_write_data']})) & $past({p['gpio_write_mask']})) == 0);",
                    "        end",
                    f"        if (!$initstate && {p['timer_irq']} && !$past({p['timer_irq']})) begin",
                    f"            a_timer_{index}_irq_at_compare: assert($past({p['timer_enable']}) && (($past({p['timer_count']}) + 1'b1) >= $past({p['timer_compare']})));",
                    "        end",
                    f"        a_watchdog_{index}_reset_has_irq: assert(!{p['watchdog_reset']} || {p['watchdog_irq']});",
                    f"        a_pwm_{index}_disabled_idle: assert({p['pwm_enable']} || ({p['pwm_output']} == {p['pwm_polarity']}));",
                    f"        a_interrupt_{index}_masked_pending: assert(({p['interrupt_pending']} & ~{p['interrupt_mask']}) == 0);",
                    f"        if ({p['interrupt_valid']}) assume($stable({p['interrupt_mask']}));",
                    f"        a_interrupt_{index}_valid: assert({p['interrupt_valid']} == (|{p['interrupt_pending']}));",
                    f"        c_gpio_{index}_write: cover({p['gpio_write']} && |{p['gpio_write_mask']});",
                    f"        c_timer_{index}_irq: cover({p['timer_irq']});",
                    f"        c_watchdog_{index}_reset: cover({p['watchdog_reset']});",
                    f"        c_pwm_{index}_both: cover(!$initstate && $past({p['pwm_output']}) != {p['pwm_output']});",
                    f"        c_interrupt_{index}_simultaneous: cover($countones({p['interrupt_pending']}) > 1);",
                )
            )
    return lines


def _formal_guard(reset_name: str | None, reset_inactive: str | None) -> str:
    if reset_name and reset_inactive:
        return f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
    return ""


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
