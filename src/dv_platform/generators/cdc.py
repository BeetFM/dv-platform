"""Deterministic cocotb renderers for qualified CDC scenario templates."""

from __future__ import annotations

import re

from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable


def cocotb_cdc_scenario_lines(plan: VerificationPlan) -> tuple[str, ...]:
    scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind in {"cdc_two_flop", "cdc_pulse", "cdc_toggle", "cdc_handshake", "cdc_async_fifo"}
        and scenario_is_executable(scenario, VerificationTarget.COCOTB)
    )
    if not scenarios:
        return ()
    module = _safe_identifier(plan.module)
    lines: list[str] = []
    for scenario in scenarios:
        profile = dict(scenario.stimulus[0].parameters)
        suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
        name = f"test_{module}_scenario_{suffix}"
        if scenario.kind == "cdc_async_fifo":
            lines.extend(_async_fifo_lines(module, scenario.scenario_id, profile, scenario.completion.timeout_cycles))
            continue
        clock = profile["clock"]
        reset = profile.get("reset", "")
        active_low = profile.get("reset_active_low", "false") == "true"
        source = profile["source_signal"]
        output = profile["output_signal"]
        timeout = int(profile.get("max_latency_cycles", scenario.completion.timeout_cycles))
        lines.extend(
            (
                "",
                "",
                "@cocotb.test()",
                f"async def {name}(dut):",
                f"    clock = getattr(dut, {clock!r})",
                "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
                f"    source = getattr(dut, {source!r})",
                f"    observed = getattr(dut, {output!r})",
                "    source.value = 0",
            )
        )
        if scenario.kind == "cdc_handshake":
            ack_input = profile["ack_input_signal"]
            ack_clock = profile["ack_clock"]
            lines.extend(
                (
                    f"    ack_clock = getattr(dut, {ack_clock!r})",
                    "    cocotb.start_soon(Clock(ack_clock, 14, unit='ns').start())",
                    f"    ack_input = getattr(dut, {ack_input!r})",
                    "    ack_input.value = 0",
                )
            )
        if reset:
            active = 0 if active_low else 1
            inactive = 1 - active
            lines.extend(
                (
                    f"    reset = getattr(dut, {reset!r})",
                    f"    reset.value = {active}",
                    "    await RisingEdge(clock)",
                    "    await RisingEdge(clock)",
                    f"    reset.value = {inactive}",
                    "    await RisingEdge(clock)",
                )
            )
        else:
            lines.append("    await RisingEdge(clock)")
        if scenario.kind in {"cdc_two_flop", "cdc_toggle"}:
            lines.extend(
                (
                    "    source.value = 1",
                    f"    assert await _cdc_wait_value(observed, clock, 1, {timeout}), 'toggle rise did not propagate'",
                    "    assert await _cdc_stable_value(observed, clock, 1, 2), 'toggle rise was not stable'",
                    "    source.value = 0",
                    f"    assert await _cdc_wait_value(observed, clock, 0, {timeout}), 'toggle fall did not propagate'",
                    "    assert await _cdc_stable_value(observed, clock, 0, 2), 'toggle fall was not stable'",
                )
            )
        elif scenario.kind == "cdc_pulse":
            stretch = int(profile["pulse_stretch_cycles"])
            lines.extend(
                (
                    "    source.value = 1",
                    f"    for _ in range({stretch}):",
                    "        await RisingEdge(clock)",
                    "    source.value = 0",
                    f"    assert await _cdc_wait_value(observed, clock, 1, {timeout}), 'stretched pulse was not observed'",
                    f"    assert await _cdc_wait_value(observed, clock, 0, {timeout + stretch}), 'pulse output did not return idle'",
                    "    assert await _cdc_stable_value(observed, clock, 0, 2), 'pulse idle was not stable'",
                )
            )
        else:
            ack_output = profile["ack_output_signal"]
            lines.extend(
                (
                    f"    ack_output = getattr(dut, {ack_output!r})",
                    "    source.value = 1",
                    f"    assert await _cdc_wait_value(observed, clock, 1, {timeout}), 'request did not cross'",
                    "    assert await _cdc_stable_value(observed, clock, 1, 2), 'request was not held'",
                    "    ack_input.value = 1",
                    f"    assert await _cdc_wait_value(ack_output, clock, 1, {timeout}), 'acknowledgement did not return'",
                    "    assert await _cdc_stable_value(ack_output, ack_clock, 1, 2), 'acknowledgement was not held'",
                    "    source.value = 0",
                    f"    assert await _cdc_wait_value(observed, clock, 0, {timeout}), 'request did not clear'",
                    "    ack_input.value = 0",
                    f"    assert await _cdc_wait_value(ack_output, clock, 0, {timeout}), 'acknowledgement did not clear'",
                )
            )
    lines.extend(
        (
            "",
            "",
            "async def _cdc_wait_value(signal, clock, expected, cycles):",
            "    for _ in range(cycles):",
            "        await RisingEdge(clock)",
            "        await Timer(1, unit='ps')",
            "        if int(signal.value) == expected:",
            "            return True",
            "    return False",
            "",
            "",
            "async def _cdc_stable_value(signal, clock, expected, cycles):",
            "    for _ in range(cycles):",
            "        await RisingEdge(clock)",
            "        await Timer(1, unit='ps')",
            "        if int(signal.value) != expected:",
            "            return False",
            "    return True",
            "",
            "",
            "def _cdc_onehot0(value):",
            "    return value == 0 or (value & (value - 1)) == 0",
        )
    )
    return tuple(lines)


def _async_fifo_lines(
    module: str,
    scenario_id: str,
    profile: dict[str, str],
    timeout: int,
) -> tuple[str, ...]:
    suffix = scenario_id.rsplit(":", 1)[-1].replace("-", "_")
    name = f"test_{module}_scenario_{suffix}"
    depth = int(profile["depth"])
    data_mask = (1 << int(profile["data_width"])) - 1
    write_active = 0 if profile.get("write_reset_active_low") == "true" else 1
    read_active = 0 if profile.get("read_reset_active_low") == "true" else 1
    return (
        "",
        "",
        "@cocotb.test()",
        f"async def {name}(dut):",
        f"    wclk = getattr(dut, {profile['write_clock']!r})",
        f"    rclk = getattr(dut, {profile['read_clock']!r})",
        "    cocotb.start_soon(Clock(wclk, 10, unit='ns').start())",
        "    cocotb.start_soon(Clock(rclk, 14, unit='ns').start())",
        f"    wrst = getattr(dut, {profile['write_reset']!r})",
        f"    rrst = getattr(dut, {profile['read_reset']!r})",
        f"    wen = getattr(dut, {profile['write_enable']!r})",
        f"    wdata = getattr(dut, {profile['write_data']!r})",
        f"    full = getattr(dut, {profile['full_signal']!r})",
        f"    ren = getattr(dut, {profile['read_enable']!r})",
        f"    rdata = getattr(dut, {profile['read_data']!r})",
        f"    empty = getattr(dut, {profile['empty_signal']!r})",
        f"    wbin = getattr(dut, {profile['write_binary_pointer']!r})",
        f"    wgray = getattr(dut, {profile['write_gray_pointer']!r})",
        f"    rbin = getattr(dut, {profile['read_binary_pointer']!r})",
        f"    rgray = getattr(dut, {profile['read_gray_pointer']!r})",
        "    wen.value = 0",
        "    ren.value = 0",
        "    wdata.value = 0",
        f"    wrst.value = {write_active}",
        f"    rrst.value = {read_active}",
        "    for _ in range(3):",
        "        await RisingEdge(wclk)",
        "    for _ in range(3):",
        "        await RisingEdge(rclk)",
        f"    wrst.value = {1 - write_active}",
        f"    rrst.value = {1 - read_active}",
        "    await RisingEdge(wclk)",
        "    await RisingEdge(rclk)",
        "    await Timer(1, unit='ps')",
        "    assert int(empty.value) == 1 and int(full.value) == 0, 'FIFO reset flags are incorrect'",
        "    scoreboard = []",
        "    previous_wgray = int(wgray.value)",
        "    previous_rgray = int(rgray.value)",
        f"    for value in range({depth}):",
        f"        accepted = await _async_fifo_write(wclk, wen, wdata, full, value & {data_mask}, {timeout})",
        "        assert accepted, 'FIFO write did not complete before full'",
        f"        scoreboard.append(value & {data_mask})",
        "        current_wgray = int(wgray.value)",
        "        assert current_wgray == (int(wbin.value) ^ (int(wbin.value) >> 1)), 'write pointer is not Gray encoded'",
        "        assert _cdc_onehot0(current_wgray ^ previous_wgray), 'write Gray pointer changed by more than one bit'",
        "        previous_wgray = current_wgray",
        f"    assert await _cdc_wait_value(full, wclk, 1, {timeout}), 'FIFO never asserted full'",
        "    blocked_wbin = int(wbin.value)",
        "    wen.value = 1",
        f"    wdata.value = {data_mask}",
        "    await RisingEdge(wclk)",
        "    await Timer(1, unit='ps')",
        "    wen.value = 0",
        "    assert int(wbin.value) == blocked_wbin, 'write pointer advanced while full'",
        f"    for _ in range({depth}):",
        f"        actual = await _async_fifo_read(rclk, ren, rdata, empty, {timeout})",
        "        assert actual is not None, 'FIFO read timed out'",
        "        expected = scoreboard.pop(0)",
        "        assert actual == expected, f'FIFO ordering mismatch: expected {expected}, got {actual}'",
        "        current_rgray = int(rgray.value)",
        "        assert current_rgray == (int(rbin.value) ^ (int(rbin.value) >> 1)), 'read pointer is not Gray encoded'",
        "        assert _cdc_onehot0(current_rgray ^ previous_rgray), 'read Gray pointer changed by more than one bit'",
        "        previous_rgray = current_rgray",
        f"    assert await _cdc_wait_value(empty, rclk, 1, {timeout}), 'FIFO never returned empty'",
        f"    for value in range({depth + 2}):",
        f"        accepted = await _async_fifo_write(wclk, wen, wdata, full, (value + 17) & {data_mask}, {timeout})",
        "        assert accepted, 'wraparound write timed out'",
        f"        actual = await _async_fifo_read(rclk, ren, rdata, empty, {timeout})",
        f"        assert actual == ((value + 17) & {data_mask}), 'wraparound/concurrent-clock ordering failed'",
        "    accepted = await _async_fifo_write(wclk, wen, wdata, full, 90 & " + str(data_mask) + f", {timeout})",
        "    assert accepted",
        f"    wrst.value = {write_active}",
        f"    rrst.value = {read_active}",
        "    await RisingEdge(wclk)",
        "    await RisingEdge(rclk)",
        f"    wrst.value = {1 - write_active}",
        f"    rrst.value = {1 - read_active}",
        "    await RisingEdge(wclk)",
        "    await RisingEdge(rclk)",
        "    await Timer(1, unit='ps')",
        "    assert int(empty.value) == 1 and int(full.value) == 0, 'FIFO did not recover from reset'",
        f"    assert await _async_fifo_write(wclk, wen, wdata, full, 165 & {data_mask}, {timeout})",
        f"    assert await _async_fifo_read(rclk, ren, rdata, empty, {timeout}) == (165 & {data_mask})",
        "",
        "",
        "async def _async_fifo_write(clock, enable, data, full, value, timeout):",
        "    for _ in range(timeout):",
        "        if int(full.value) == 0:",
        "            data.value = value",
        "            enable.value = 1",
        "            await RisingEdge(clock)",
        "            await Timer(1, unit='ps')",
        "            enable.value = 0",
        "            return True",
        "        await RisingEdge(clock)",
        "        await Timer(1, unit='ps')",
        "    enable.value = 0",
        "    return False",
        "",
        "",
        "async def _async_fifo_read(clock, enable, data, empty, timeout):",
        "    for _ in range(timeout):",
        "        if int(empty.value) == 0:",
        "            enable.value = 1",
        "            await RisingEdge(clock)",
        "            await Timer(1, unit='ps')",
        "            enable.value = 0",
        "            return int(data.value)",
        "        await RisingEdge(clock)",
        "        await Timer(1, unit='ps')",
        "    enable.value = 0",
        "    return None",
    )


def _safe_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return "generated" if not identifier else f"n_{identifier}" if identifier[0].isdigit() else identifier
