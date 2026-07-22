"""Deterministic cocotb renderer for the qualified bounded SRAM profile."""

from __future__ import annotations

import re

from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable


def cocotb_memory_scenario_lines(plan: VerificationPlan) -> tuple[str, ...]:
    """Render scoreboard-driven memory scenarios from typed policy parameters."""

    scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind == "memory_bounded_sram" and scenario_is_executable(scenario, VerificationTarget.COCOTB)
    )
    if not scenarios:
        return ()
    module = _safe_identifier(plan.module)
    lines: list[str] = []
    for scenario in scenarios:
        profile = dict(scenario.stimulus[0].parameters)
        suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
        name = f"test_{module}_scenario_{suffix}"
        depth = int(profile["depth"])
        width = int(profile["data_width"])
        lanes = int(profile["byte_lanes"])
        mask = (1 << width) - 1
        lane_mask = (1 << lanes) - 1
        active = 0 if profile["reset_active_low"] == "true" else 1
        collision = profile["read_during_write"]
        protection = profile.get("protection", "parity")
        timeout = scenario.completion.timeout_cycles
        lines.extend(
            (
                "",
                "",
                "@cocotb.test()",
                f"async def {name}(dut):",
                f"    clock = getattr(dut, {profile['clock']!r})",
                "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
                f"    reset = getattr(dut, {profile['reset']!r})",
                f"    read_enable = getattr(dut, {profile['read_enable']!r})",
                f"    read_address = getattr(dut, {profile['read_address']!r})",
                f"    read_data = getattr(dut, {profile['read_data']!r})",
                *(
                    (
                        f"    inject_error = getattr(dut, {profile['inject_error']!r})",
                        f"    parity_error = getattr(dut, {profile['error_signal']!r})",
                    )
                    if protection == "parity"
                    else (
                        f"    inject_single_error = getattr(dut, {profile['inject_single_error']!r})",
                        f"    inject_double_error = getattr(dut, {profile['inject_double_error']!r})",
                        f"    scrub_enable = getattr(dut, {profile['scrub_enable']!r})",
                        f"    scrub_done = getattr(dut, {profile['scrub_done']!r})",
                        f"    corrected_error = getattr(dut, {profile['corrected_error_signal']!r})",
                        f"    uncorrectable_error = getattr(dut, {profile['uncorrectable_error_signal']!r})",
                        "    parity_error = corrected_error",
                    )
                ),
                "    ports = (",
                "        ("
                f"getattr(dut, {profile['port0_request']!r}), getattr(dut, {profile['port0_write_enable']!r}), "
                f"getattr(dut, {profile['port0_address']!r}), getattr(dut, {profile['port0_write_data']!r}), "
                f"getattr(dut, {profile['port0_byte_enable']!r}), getattr(dut, {profile['port0_grant']!r})),",
                "        ("
                f"getattr(dut, {profile['port1_request']!r}), getattr(dut, {profile['port1_write_enable']!r}), "
                f"getattr(dut, {profile['port1_address']!r}), getattr(dut, {profile['port1_write_data']!r}), "
                f"getattr(dut, {profile['port1_byte_enable']!r}), getattr(dut, {profile['port1_grant']!r})),",
                "    )",
                "    read_enable.value = 0",
                "    read_address.value = 0",
                *(
                    ("    inject_error.value = 0",)
                    if protection == "parity"
                    else (
                        "    inject_single_error.value = 0",
                        "    inject_double_error.value = 0",
                        "    scrub_enable.value = 0",
                    )
                ),
                "    for request, write_enable, address, data, byte_enable, _grant in ports:",
                "        request.value = 0",
                "        write_enable.value = 0",
                "        address.value = 0",
                "        data.value = 0",
                "        byte_enable.value = 0",
                f"    reset.value = {active}",
                "    await RisingEdge(clock)",
                "    await RisingEdge(clock)",
                f"    reset.value = {1 - active}",
                "    await RisingEdge(clock)",
                f"    for address in range({depth}):",
                "        actual, error = await _memory_read(clock, read_enable, read_address, read_data, parity_error, address)",
                "        assert actual == 0, f'memory address {address} did not initialize to zero'",
                "        assert error == 0, 'clean initialized memory raised parity error'",
                "    scoreboard = [0] * " + str(depth),
                f"    await _memory_write(clock, ports[0], 1, {0xA55A & mask}, {lane_mask}, {timeout})",
                f"    scoreboard[1] = {0xA55A & mask}",
                "    actual, error = await _memory_read(clock, read_enable, read_address, read_data, parity_error, 1)",
                "    assert actual == scoreboard[1] and error == 0, 'full-word write/read failed'",
                f"    await _memory_write(clock, ports[1], 1, {0x003C & mask}, 1, {timeout})",
                "    scoreboard[1] = (scoreboard[1] & ~0xff) | 0x3c",
                "    actual, _ = await _memory_read(clock, read_enable, read_address, read_data, parity_error, 1)",
                "    assert actual == scoreboard[1], 'low byte-enable merge failed'",
                f"    await _memory_write(clock, ports[0], 1, {0xC700 & mask}, {2 if lanes > 1 else 1}, {timeout})",
                (
                    "    scoreboard[1] = (scoreboard[1] & 0xff) | 0xc700"
                    if lanes > 1
                    else f"    scoreboard[1] = {0xC700 & mask}"
                ),
                "    actual, _ = await _memory_read(clock, read_enable, read_address, read_data, parity_error, 1)",
                "    assert actual == scoreboard[1], 'upper byte-enable merge failed'",
                f"    await _memory_write(clock, ports[1], {depth - 1}, {0x5AA5 & mask}, {lane_mask}, {timeout})",
                f"    scoreboard[{depth - 1}] = {0x5AA5 & mask}",
                f"    actual, _ = await _memory_read(clock, read_enable, read_address, read_data, parity_error, {depth - 1})",
                f"    assert actual == scoreboard[{depth - 1}], 'highest legal address failed'",
                "    previous_output = int(read_data.value)",
                "    old_value = scoreboard[2]",
                f"    collision_value = {0x369C & mask}",
                "    read_enable.value = 1",
                "    read_address.value = 2",
                "    request, write_enable, address, data, byte_enable, grant = ports[0]",
                "    request.value = 1",
                "    write_enable.value = 1",
                "    address.value = 2",
                "    data.value = collision_value",
                f"    byte_enable.value = {lane_mask}",
                "    await Timer(1, unit='ps')",
                "    assert int(grant.value) == 1, 'collision write was not granted'",
                "    await RisingEdge(clock)",
                "    await Timer(1, unit='ps')",
                "    collision_result = int(read_data.value)",
                "    request.value = 0",
                "    write_enable.value = 0",
                "    read_enable.value = 0",
                "    scoreboard[2] = collision_value",
                f"    expected_collision = {{'read_first': old_value, 'write_first': collision_value, 'no_change': previous_output}}[{collision!r}]",
                "    assert collision_result == expected_collision, 'read-during-write policy mismatch'",
                "    for index, port in enumerate(ports):",
                "        request, write_enable, address, data, byte_enable, _grant = port",
                "        request.value = 1",
                "        write_enable.value = 1",
                "        address.value = 3 + index",
                "        data.value = 0x1111 * (index + 1)",
                f"        byte_enable.value = {lane_mask}",
                "    winners = []",
                "    for _ in range(2):",
                "        await Timer(1, unit='ps')",
                "        grants = [int(port[5].value) for port in ports]",
                "        assert sum(grants) == 1, 'arbitration grants were not one-hot'",
                "        winners.append(grants.index(1))",
                "        await RisingEdge(clock)",
                "        await Timer(1, unit='ps')",
                "    assert set(winners) == {0, 1}, 'round-robin arbitration starved a requester'",
                "    for port in ports:",
                "        port[0].value = 0",
                "        port[1].value = 0",
                "    for index in range(2):",
                "        actual, error = await _memory_read(clock, read_enable, read_address, read_data, parity_error, 3 + index)",
                "        assert actual == 0x1111 * (index + 1) and error == 0, 'arbitrated write was lost'",
                *(
                    (
                        "    inject_error.value = 1",
                        "    _actual, error = await _memory_read(clock, read_enable, read_address, read_data, parity_error, 1)",
                        "    inject_error.value = 0",
                        "    assert error == 1, 'injected single-bit parity error was not detected'",
                    )
                    if protection == "parity"
                    else (
                        "    inject_single_error.value = 1",
                        "    actual, corrected = await _memory_read(clock, read_enable, read_address, read_data, corrected_error, 1)",
                        "    assert actual == scoreboard[1] and corrected == 1 and int(uncorrectable_error.value) == 0, 'single-bit SECDED correction failed'",
                        "    inject_single_error.value = 0",
                        "    inject_double_error.value = 1",
                        "    _actual, _corrected = await _memory_read(clock, read_enable, read_address, read_data, corrected_error, 1)",
                        "    assert int(uncorrectable_error.value) == 1, 'double-bit SECDED error was not detected'",
                        "    inject_double_error.value = 0",
                        "    inject_single_error.value = 1",
                        "    scrub_enable.value = 1",
                        "    actual, corrected = await _memory_read(clock, read_enable, read_address, read_data, corrected_error, 1)",
                        "    assert actual == scoreboard[1] and corrected == 1 and int(scrub_done.value) == 1, 'SECDED scrub did not repair the selected word'",
                        "    inject_single_error.value = 0",
                        "    scrub_enable.value = 0",
                    )
                ),
                f"    reset.value = {active}",
                "    await RisingEdge(clock)",
                f"    reset.value = {1 - active}",
                "    await RisingEdge(clock)",
                "    for address in (0, 1, " + str(depth - 1) + "):",
                "        actual, error = await _memory_read(clock, read_enable, read_address, read_data, parity_error, address)",
                "        assert actual == 0 and error == 0, 'memory did not reinitialize after reset'",
            )
        )
    lines.extend(
        (
            "",
            "",
            "async def _memory_write(clock, port, address_value, data_value, byte_mask, timeout):",
            "    request, write_enable, address, data, byte_enable, grant = port",
            "    request.value = 1",
            "    write_enable.value = 1",
            "    address.value = address_value",
            "    data.value = data_value",
            "    byte_enable.value = byte_mask",
            "    for _ in range(timeout):",
            "        await Timer(1, unit='ps')",
            "        if int(grant.value):",
            "            await RisingEdge(clock)",
            "            await Timer(1, unit='ps')",
            "            request.value = 0",
            "            write_enable.value = 0",
            "            return",
            "        await RisingEdge(clock)",
            "    request.value = 0",
            "    write_enable.value = 0",
            "    raise AssertionError('memory write arbitration timed out')",
            "",
            "",
            "async def _memory_read(clock, enable, address, data, error, address_value):",
            "    enable.value = 1",
            "    address.value = address_value",
            "    await RisingEdge(clock)",
            "    await Timer(1, unit='ps')",
            "    enable.value = 0",
            "    return int(data.value), int(error.value)",
        )
    )
    return tuple(lines)


def _safe_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return "generated" if not identifier else f"n_{identifier}" if identifier[0].isdigit() else identifier
