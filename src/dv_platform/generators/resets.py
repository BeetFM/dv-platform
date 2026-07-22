"""Deterministic cocotb renderers for qualified reset-domain scenarios."""

from __future__ import annotations

import re

from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable


def cocotb_reset_scenario_lines(plan: VerificationPlan) -> tuple[str, ...]:
    scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind == "reset_domain_sequence" and scenario_is_executable(scenario, VerificationTarget.COCOTB)
    )
    if not scenarios:
        return ()
    module = _safe_identifier(plan.module)
    lines: list[str] = []
    for scenario in scenarios:
        profile = dict(scenario.stimulus[0].parameters)
        suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
        name = f"test_{module}_scenario_{suffix}"
        reset_active = 0 if profile["reset_active_low"] == "true" else 1
        reset_inactive = 1 - reset_active
        recovery_cycles = int(profile.get("recovery_cycles", "1"))
        removal_cycles = int(profile.get("removal_cycles", "1"))
        release_cycles = max(int(profile.get("release_cycles", "2")), recovery_cycles, removal_cycles)
        min_assert = int(profile.get("min_assert_cycles", "2"))
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
                f"    ready = getattr(dut, {profile['ready_signal']!r})",
                f"    reset.value = {reset_active}",
            )
        )
        dependency_reset = profile.get("depends_on_reset", "")
        if dependency_reset:
            dependency_active = 0 if profile["dependency_reset_active_low"] == "true" else 1
            dependency_inactive = 1 - dependency_active
            lines.extend(
                (
                    f"    dependency_clock = getattr(dut, {profile['dependency_clock']!r})",
                    "    cocotb.start_soon(Clock(dependency_clock, 14, unit='ns').start())",
                    f"    dependency_reset = getattr(dut, {dependency_reset!r})",
                    f"    dependency_ready = getattr(dut, {profile['depends_on_ready']!r})",
                    f"    dependency_sync = getattr(dut, {profile['dependency_sync_signal']!r})",
                    f"    dependency_reset.value = {dependency_active}",
                )
            )
        lines.extend(
            (
                f"    for _ in range({min_assert}):",
                "        await RisingEdge(clock)",
                "    await Timer(1, unit='ps')",
                "    assert int(ready.value) == 0, 'ready was not held inactive during reset'",
                f"    reset.value = {reset_inactive}",
            )
        )
        if dependency_reset:
            lines.extend(
                (
                    f"    for _ in range({release_cycles + 2}):",
                    "        await RisingEdge(clock)",
                    "        await Timer(1, unit='ps')",
                    "        assert int(ready.value) == 0, 'dependent domain released before its dependency'",
                    f"    dependency_reset.value = {dependency_inactive}",
                    f"    assert await _reset_wait_value(dependency_ready, dependency_clock, 1, {timeout}), 'dependency did not release'",
                    f"    assert await _reset_wait_value(dependency_sync, clock, 1, {timeout}), 'reset-domain dependency did not synchronize'",
                    f"    for index in range({release_cycles}):",
                    "        await RisingEdge(clock)",
                    "        await Timer(1, unit='ps')",
                    f"        if index < {release_cycles - 1}:",
                    "            assert int(ready.value) == 0, 'dependent domain released before its governed delay'",
                )
            )
        lines.extend(
            (
                f"    assert await _reset_wait_value(ready, clock, 1, {timeout}), 'domain did not complete bounded release'",
                "    assert _reset_resolvable(ready), 'ready became unresolved after release'",
                f"    await Timer({recovery_cycles}, unit='ns')",
                f"    reset.value = {reset_active}",
                "    await Timer(1, unit='ps')",
                "    assert int(ready.value) == 0, 'asynchronous reset assertion did not immediately clear ready'",
                f"    for _ in range({min_assert}):",
                "        await RisingEdge(clock)",
                f"    await Timer({removal_cycles}, unit='ns')",
                f"    reset.value = {reset_inactive}",
                *(
                    (
                        f"    assert await _reset_wait_value(dependency_sync, clock, 1, {timeout}), 'RDC did not recover after reset'",
                    )
                    if dependency_reset
                    else ()
                ),
                f"    for index in range({release_cycles}):",
                "        await RisingEdge(clock)",
                "        await Timer(1, unit='ps')",
                f"        if index < {release_cycles - 1}:",
                "            assert int(ready.value) == 0, 'reset removal released the domain too early'",
                f"    assert await _reset_wait_value(ready, clock, 1, {timeout}), 'domain did not recover after reset removal'",
                "    assert _reset_resolvable(ready), 'ready became unresolved during recovery'",
            )
        )
    lines.extend(
        (
            "",
            "",
            "async def _reset_wait_value(signal, clock, expected, cycles):",
            "    for _ in range(cycles):",
            "        await RisingEdge(clock)",
            "        await Timer(1, unit='ps')",
            "        if int(signal.value) == expected:",
            "            return True",
            "    return False",
            "",
            "",
            "def _reset_resolvable(signal):",
            "    value = signal.value",
            "    return not hasattr(value, 'is_resolvable') or value.is_resolvable",
        )
    )
    return tuple(lines)


def _safe_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return "generated" if not identifier else f"n_{identifier}" if identifier[0].isdigit() else identifier
