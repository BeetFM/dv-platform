"""cocotb generator backend."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    GeneratedArtifact,
    RTLPort,
    RTLProtocol,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.cdc import cocotb_cdc_scenario_lines
from dv_platform.generators.memories import cocotb_memory_scenario_lines
from dv_platform.generators.protocols import (
    cocotb_apb4_scenario_lines,
    cocotb_axi4_lite_scenario_lines,
    cocotb_protocol_lines,
)
from dv_platform.generators.resets import cocotb_reset_scenario_lines
from dv_platform.generators.scenario_registry import scenario_is_executable
from dv_platform.generators.signals import (
    artifact_trace,
    artifact_trace_for_scenario,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    safe_parameter_value,
)


class CocotbGenerator:
    """Generate evidence-backed cocotb checks from a verification plan."""

    target = VerificationTarget.COCOTB

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        traces = list(
            artifact_trace(
                plan,
                f"test_{module_name}_smoke",
                target=self.target,
                categories=("reset", "increment", "hold", "connectivity"),
            )
        )
        if _paired_ready_valid(plan) is not None:
            traces.extend(
                artifact_trace(plan, f"test_{module_name}_ready_valid", target=self.target, categories=("protocol",))
            )
        for scenario in plan.scenarios:
            if scenario_is_executable(scenario, VerificationTarget.COCOTB):
                traces.extend(
                    artifact_trace_for_scenario(
                        plan,
                        scenario,
                        f"test_{module_name}_scenario_{scenario.scenario_id.rsplit(':', 1)[-1].replace('-', '_')}",
                    )
                )
        return [
            GeneratedArtifact(
                path=Path("test_" + _safe_identifier(plan.module) + ".py"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _test_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=provenance_refs(plan),
                quality_requirements=_quality_requirements(plan),
                traceability=tuple(traces),
            )
        ]


def _test_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = _port_names_from_plan(plan)
    clock_name = (
        primary_clock_name(plan, ports)
        or (plan.protocol_models[0].clock_domain if plan.protocol_models else None)
        or "clk"
    )
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else "rst_n"
    active_low = reset.active_low if reset is not None and reset.active_low is not None else reset_name.endswith("_n")
    reset_active_value = 0 if active_low else 1
    reset_inactive_value = 1 - reset_active_value
    secondary_resets = tuple(
        (
            item.name,
            0 if (item.active_low if item.active_low is not None else item.name.endswith("_n")) else 1,
        )
        for item in plan.resets
        if item.name != reset_name
    )
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
    driven_inputs = _driven_input_ports(plan, ports, clock_name, reset_name)
    output_ports = _output_ports(plan, ports)
    reset_zero_outputs = _reset_zero_outputs(plan, output_ports, reset_name)
    increment_checks = _increment_checks(plan, output_ports, scalar_inputs)
    hold_checks = _hold_checks(plan, output_ports, scalar_inputs)
    lines = [
        '"""Generated cocotb smoke tests for ' + plan.module + '."""',
        "",
        "import cocotb",
        "from cocotb.clock import Clock",
        "from cocotb.triggers import RisingEdge, Timer",
        "",
        "",
        "@cocotb.test()",
        "async def test_" + module_name + "_smoke(dut):",
        '    """Run initial generated checks from the verification plan."""',
        "    clock = _maybe_signal(dut, " + repr(clock_name) + ")",
        "    if clock is not None:",
        "        cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "",
    ]

    for index, other_clock in enumerate((clock.name for clock in plan.clocks if clock.name != clock_name), start=1):
        lines.extend(
            [
                "    other_clock = _maybe_signal(dut, " + repr(other_clock) + ")",
                "    if other_clock is not None:",
                f"        cocotb.start_soon(Clock(other_clock, {10 + index * 4}, unit='ns').start())",
                "",
            ]
        )

    if driven_inputs:
        lines.extend(
            [
                "    for name in " + repr(driven_inputs) + ":",
                "        _drive_if_present(dut, name, 0)",
                "",
            ]
        )

    lines.extend(
        [
            "    for name, active in " + repr(secondary_resets) + ":",
            "        _drive_if_present(dut, name, active)",
            "",
            "    reset = _maybe_signal(dut, " + repr(reset_name) + ")",
            "    if reset is not None:",
            "        reset.value = " + str(reset_active_value),
            "        reset_clocks = []",
            "        for name in " + repr(_clock_names(plan, clock_name)) + ":",
            "            reset_clock = _maybe_signal(dut, name)",
            "            if reset_clock is not None:",
            "                reset_clocks.append(reset_clock)",
            "        if reset_clocks:",
            "            for reset_clock in reset_clocks:",
            "                await RisingEdge(reset_clock)",
            "            await Timer(1, unit='ps')",
            "        else:",
            "            await Timer(20, unit='ns')",
            *("        _assert_signal_int(dut, " + repr(output) + ", 0)" for output in reset_zero_outputs),
            "        reset.value = " + str(reset_inactive_value),
            "        for name, active in " + repr(secondary_resets) + ":",
            "            _drive_if_present(dut, name, 1 - active)",
            "",
        ]
    )

    if scalar_inputs:
        lines.extend(
            [
                "    for name in " + repr(scalar_inputs) + ":",
                "        _drive_if_present(dut, name, 1)",
                "",
            ]
        )

    for output_name, input_name in increment_checks:
        sampling_clock = _behavior_clock(plan, "increment", output_name, input_name, clock_name)
        lines.extend(
            [
                "    _drive_if_present(dut, " + repr(input_name) + ", 1)",
                "    before = _signal_int(dut, " + repr(output_name) + ")",
                "    sampling_clock = _maybe_signal(dut, " + repr(sampling_clock) + ")",
                "    if sampling_clock is None:",
                "        sampling_clock = clock",
                "    if sampling_clock is not None:",
                "        await RisingEdge(sampling_clock)",
                "        await Timer(1, unit='ps')",
                "    else:",
                "        await Timer(1, unit='ns')",
                "    after = _signal_int(dut, " + repr(output_name) + ")",
                "    if before is not None and after is not None:",
                "        assert after == before + 1, "
                + repr(output_name + " did not increment when " + input_name + " was asserted")
                + "",
                "",
            ]
        )

    for output_name, input_name in hold_checks:
        sampling_clock = _behavior_clock(plan, "hold", output_name, input_name, clock_name)
        lines.extend(
            [
                "    _drive_if_present(dut, " + repr(input_name) + ", 0)",
                "    before = _signal_int(dut, " + repr(output_name) + ")",
                "    sampling_clock = _maybe_signal(dut, " + repr(sampling_clock) + ")",
                "    if sampling_clock is None:",
                "        sampling_clock = clock",
                "    if sampling_clock is not None:",
                "        await RisingEdge(sampling_clock)",
                "        await Timer(1, unit='ps')",
                "    else:",
                "        await Timer(1, unit='ns')",
                "    after = _signal_int(dut, " + repr(output_name) + ")",
                "    if before is not None and after is not None:",
                "        assert after == before, "
                + repr(output_name + " changed when " + input_name + " was inactive")
                + "",
                "",
            ]
        )

    lines.extend(
        [
            "    if clock is not None:",
            "        await RisingEdge(clock)",
            "    else:",
            "        await Timer(1, unit='ns')",
            "",
            "    assert dut is not None",
        ]
    )

    if output_ports:
        lines.extend(
            [
                "",
                "    for name in " + repr(output_ports) + ":",
                "        _assert_resolvable(dut, name)",
            ]
        )

    if plan.checks:
        lines.extend(["", "    # Planned checks represented by this smoke test:"])
        lines.extend("    # - " + check for check in plan.checks)
    if plan.requirements:
        lines.extend(["", "    # Retrieved requirements:"])
        lines.extend("    # - " + requirement for requirement in plan.requirements)

    protocol_lines = _ready_valid_test_lines(
        plan,
        module_name,
        clock_name,
        reset_name,
        reset_active_value,
        reset_inactive_value,
        driven_inputs,
    )
    if protocol_lines:
        lines.extend(("", "", *protocol_lines))
    mapped_protocol_lines = cocotb_protocol_lines(plan, clock_name)
    if mapped_protocol_lines:
        lines.extend(mapped_protocol_lines)
    apb4_lines = cocotb_apb4_scenario_lines(plan, clock_name)
    if apb4_lines:
        lines.extend(apb4_lines)
    axi4_lite_lines = cocotb_axi4_lite_scenario_lines(plan, clock_name)
    if axi4_lite_lines:
        lines.extend(axi4_lite_lines)
    cdc_lines = cocotb_cdc_scenario_lines(plan)
    if cdc_lines:
        lines.extend(cdc_lines)
    reset_lines = cocotb_reset_scenario_lines(plan)
    if reset_lines:
        lines.extend(reset_lines)
    memory_lines = cocotb_memory_scenario_lines(plan)
    if memory_lines:
        lines.extend(memory_lines)

    lines.extend(
        [
            "",
            "",
            "def _maybe_signal(dut, name):",
            "    return getattr(dut, name, None)",
            "",
            "",
            "def _drive_if_present(dut, name, value):",
            "    signal = _maybe_signal(dut, name)",
            "    if signal is not None:",
            "        signal.value = value",
            "",
            "",
            "def _signal_int(dut, name):",
            "    signal = _maybe_signal(dut, name)",
            "    if signal is None:",
            "        return None",
            "    value = signal.value",
            "    if hasattr(value, 'is_resolvable') and not value.is_resolvable:",
            "        return None",
            "    try:",
            "        return int(value)",
            "    except (TypeError, ValueError):",
            "        return None",
            "",
            "",
            "def _assert_signal_int(dut, name, expected):",
            "    actual = _signal_int(dut, name)",
            "    if actual is not None:",
            "        assert actual == expected, f'{name} expected {expected}, got {actual}'",
            "",
            "",
            "def _assert_resolvable(dut, name):",
            "    signal = _maybe_signal(dut, name)",
            "    if signal is not None and hasattr(signal.value, 'is_resolvable'):",
            "        assert signal.value.is_resolvable, f'{name} is unresolved: {signal.value}'",
            "",
            "",
            "async def _sample_cycle(clock):",
            "    await RisingEdge(clock)",
            "    await Timer(1, unit='ps')",
        ]
    )

    return "\n".join(lines) + "\n"


def _port_names_from_plan(plan: VerificationPlan) -> tuple[str, ...]:
    if plan.ports:
        return tuple(port.name for port in plan.ports)
    ports: list[str] = []
    prefix = f"port:{plan.module}."
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            locator = ref.locator.split("@", 1)[0]
            if locator.startswith(prefix):
                ports.append(locator.removeprefix(prefix))
    return tuple(dict.fromkeys(ports))


def _structured_ports(plan: VerificationPlan) -> dict[str, RTLPort]:
    return {port.name: port for port in plan.ports}


def _scalar_input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str,
) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        control_ports = {item.name for item in plan.clocks} | {item.name for item in plan.resets}
        control_ports.update((clock_name, reset_name))
        return tuple(
            port.name
            for port in plan.ports
            if port.direction == "input" and port.name not in control_ports and port.width in (None, 1)
        )
    return tuple(port for port in ports if _looks_like_scalar_input(port) and port not in {clock_name, reset_name})


def _driven_input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str,
) -> tuple[str, ...]:
    if plan.ports:
        excluded = {clock.name for clock in plan.clocks} | {reset.name for reset in plan.resets}
        excluded.update((clock_name, reset_name))
        return tuple(port.name for port in plan.ports if port.direction == "input" and port.name not in excluded)
    return _scalar_input_ports(plan, ports, clock_name, reset_name)


def _output_ports(plan: VerificationPlan, ports: tuple[str, ...]) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        return tuple(port.name for port in plan.ports if port.direction == "output")
    return tuple(port for port in ports if _looks_like_output(port))


def _clock_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (port for port in ports if port in {"clk", "clock"} or port.endswith("_clk") or port.endswith("_clock")), None
    )


def _reset_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (
            port
            for port in ports
            if port in {"rst", "reset", "rst_n", "reset_n"} or port.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
        ),
        None,
    )


def _looks_like_scalar_input(port: str) -> bool:
    if port.endswith(("_o", "_out")):
        return False
    return port.endswith(("_i", "_in")) or port in {"enable", "en", "valid", "ready", "start", "clear", "load"}


def _looks_like_output(port: str) -> bool:
    return port.endswith(("_o", "_out"))


def _reset_zero_outputs(plan: VerificationPlan, output_ports: tuple[str, ...], reset_name: str) -> tuple[str, ...]:
    behavior_outputs = tuple(
        behavior.target
        for behavior in plan.behaviors
        if behavior.kind == "reset_to_constant"
        and behavior.target in output_ports
        and behavior.control == reset_name
        and _is_zero_value(behavior.value)
    )
    text = _plan_intent_text(plan)
    if reset_name.lower() not in text:
        return tuple(dict.fromkeys(behavior_outputs))
    reset_terms = ("clear", "clears", "cleared", "zero", "reset value")
    text_outputs = (
        tuple(output for output in output_ports if output.lower() in text)
        if any(term in text for term in reset_terms)
        else ()
    )
    return tuple(dict.fromkeys((*behavior_outputs, *text_outputs)))


def _increment_checks(
    plan: VerificationPlan,
    output_ports: tuple[str, ...],
    scalar_inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    behavior_checks = tuple(
        (behavior.target, behavior.control)
        for behavior in plan.behaviors
        if behavior.kind == "increment" and behavior.target in output_ports and behavior.control in scalar_inputs
    )
    increment_requirements = tuple(
        requirement.statement for requirement in plan.structured_requirements if requirement.category == "increment"
    )
    fallback_intent = (
        plan.requirements
        if plan.requirements
        else ()
        if any(behavior.kind == "increment" for behavior in plan.behaviors)
        else plan.checks
    )
    text = " ".join(increment_requirements or fallback_intent).lower()
    if not any(term in text for term in ("increment", "increments", "increase", "increases")):
        return tuple(dict.fromkeys(behavior_checks))
    text_checks = tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in text and input_name.lower() in text
    )
    return tuple(dict.fromkeys((*behavior_checks, *text_checks)))


def _hold_checks(
    plan: VerificationPlan,
    output_ports: tuple[str, ...],
    scalar_inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    hold_requirements = tuple(
        requirement.statement for requirement in plan.structured_requirements if requirement.category == "hold"
    )
    if plan.structured_requirements and not hold_requirements:
        return ()
    text = " ".join(hold_requirements).lower() if hold_requirements else _plan_intent_text(plan)
    if not any(term in text for term in ("hold", "holds", "stable", "unchanged", "remains stable")):
        return ()
    return tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in text and input_name.lower() in text
    )


def _plan_intent_text(plan: VerificationPlan) -> str:
    return " ".join((*plan.checks, *plan.requirements)).lower()


def _clock_names(plan: VerificationPlan, primary: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((primary, *(clock.name for clock in plan.clocks))))


def _behavior_clock(
    plan: VerificationPlan,
    kind: str,
    target: str,
    control: str,
    fallback: str,
) -> str:
    behavior = next(
        (
            item
            for item in plan.behaviors
            if item.kind == kind and item.target == target and item.control == control and item.domain_id is not None
        ),
        None,
    )
    if behavior is None:
        return fallback
    domain = next((item for item in plan.control_domains if item.domain_id == behavior.domain_id), None)
    return domain.clock if domain is not None else fallback


def _paired_ready_valid(plan: VerificationPlan) -> tuple[RTLProtocol, RTLProtocol] | None:
    sinks = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "sink" and protocol.data is not None
    )
    sources = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source" and protocol.data is not None
    )
    if len(sinks) != 1 or len(sources) != 1:
        return None
    sink, source = sinks[0], sources[0]
    if sink.clock and source.clock and sink.clock != source.clock:
        return None
    return sink, source


def _ready_valid_test_lines(
    plan: VerificationPlan,
    module_name: str,
    clock_name: str,
    reset_name: str,
    reset_active_value: int,
    reset_inactive_value: int,
    driven_inputs: tuple[str, ...],
) -> list[str]:
    pair = _paired_ready_valid(plan)
    if pair is None:
        return []
    sink, source = pair
    protocol_clock = sink.clock or source.clock or clock_name
    width = sink.data_width or source.data_width or 8
    pattern = 0xA5 & ((1 << min(width, 63)) - 1)
    if pattern == 0:
        pattern = 1
    latency = max(
        (
            int(requirement.expected_value.split()[0])
            for requirement in plan.structured_requirements
            if requirement.category == "latency"
            and requirement.expected_value is not None
            and requirement.expected_value.split()[0].isdigit()
        ),
        default=8,
    )
    timeout_cycles = max(8, latency + 4)
    return [
        "@cocotb.test()",
        f"async def test_{module_name}_ready_valid(dut):",
        '    """Check a backed-up end-to-end ready/valid transfer."""',
        "    clock = _maybe_signal(dut, " + repr(protocol_clock) + ")",
        "    assert clock is not None, " + repr(f"ready/valid channel requires clock {protocol_clock}"),
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    for name in " + repr(driven_inputs) + ":",
        "        _drive_if_present(dut, name, 0)",
        "    reset = _maybe_signal(dut, " + repr(reset_name) + ")",
        "    if reset is not None:",
        "        reset.value = " + str(reset_active_value),
        "        await _sample_cycle(clock)",
        "        reset.value = " + str(reset_inactive_value),
        "        await _sample_cycle(clock)",
        "    _drive_if_present(dut, " + repr(source.ready) + ", 0)",
        "    _drive_if_present(dut, " + repr(sink.data) + ", " + str(pattern) + ")",
        "    _drive_if_present(dut, " + repr(sink.valid) + ", 1)",
        "    accepted = False",
        "    for _ in range(" + str(timeout_cycles) + "):",
        "        ready_before_edge = _signal_int(dut, " + repr(sink.ready) + ")",
        "        await _sample_cycle(clock)",
        "        if ready_before_edge == 1:",
        "            accepted = True",
        "            break",
        "    assert accepted, " + repr(f"{sink.name} did not accept a transfer") + "",
        "    _drive_if_present(dut, " + repr(sink.valid) + ", 0)",
        "    observed = False",
        "    for _ in range(" + str(timeout_cycles) + "):",
        "        if _signal_int(dut, " + repr(source.valid) + ") == 1:",
        "            observed = True",
        "            break",
        "        await _sample_cycle(clock)",
        "    assert observed, " + repr(f"{source.name} did not produce the accepted transfer") + "",
        "    held_data = _signal_int(dut, " + repr(source.data) + ")",
        "    assert held_data == " + str(pattern) + ", " + repr(f"{source.data} corrupted transferred data") + "",
        "    await _sample_cycle(clock)",
        "    assert _signal_int(dut, "
        + repr(source.valid)
        + ") == 1, "
        + repr(f"{source.valid} dropped under backpressure"),
        "    assert _signal_int(dut, "
        + repr(source.data)
        + ") == held_data, "
        + repr(f"{source.data} changed under backpressure"),
        "    _drive_if_present(dut, " + repr(source.ready) + ", 1)",
        "    await _sample_cycle(clock)",
        "",
    ]


def _quality_requirements(plan: VerificationPlan) -> tuple[ArtifactQualityRequirement, ...]:
    ports = _port_names_from_plan(plan)
    clock_name = primary_clock_name(plan, ports) or "clk"
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else "rst_n"
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
    output_ports = _output_ports(plan, ports)
    reset_checks = _reset_zero_outputs(plan, output_ports, reset_name)
    increment_checks = _increment_checks(plan, output_ports, scalar_inputs)
    hold_checks = _hold_checks(plan, output_ports, scalar_inputs)
    protocol_pair = _paired_ready_valid(plan)
    has_async_fifo_scenario = any(
        scenario.kind == "cdc_async_fifo" and scenario_is_executable(scenario, VerificationTarget.COCOTB)
        for scenario in plan.scenarios
    )
    has_reset_domain_scenario = any(
        scenario.kind == "reset_domain_sequence" and scenario_is_executable(scenario, VerificationTarget.COCOTB)
        for scenario in plan.scenarios
    )
    has_sequential_checks = bool(increment_checks or hold_checks or protocol_pair)
    has_backed_checks = bool(reset_checks or increment_checks or hold_checks or protocol_pair)
    has_backed_connectivity = bool(plan.ports) and any(
        str(claim.status) == "supported" and any(ref.kind == "verilator_ast" for ref in claim.evidence_refs)
        for claim in plan.claims
    )
    port_names = tuple(port.name for port in plan.ports)
    directions = {port.direction for port in plan.ports}
    return (
        ArtifactQualityRequirement(
            requirement_id="structured_ports",
            description="Executable cocotb checks require structured port metadata.",
            satisfied=bool(plan.ports),
            reason=None if plan.ports else "plan has no structured ports",
        ),
        ArtifactQualityRequirement(
            requirement_id="unambiguous_port_directions",
            description="Executable cocotb checks require unique input/output port directions.",
            satisfied=bool(plan.ports)
            and len(set(port_names)) == len(port_names)
            and {"input", "output"}.issubset(directions)
            and all(port.direction in {"input", "output", "inout", "ref"} for port in plan.ports),
            reason="ports are missing, duplicated, or lack valid directions",
        ),
        ArtifactQualityRequirement(
            requirement_id="backed_executable_checks",
            description="Executable cocotb artifact must contain checks backed by plan behaviors or requirements.",
            satisfied=(has_backed_checks and bool(plan.behaviors or plan.structured_requirements))
            or has_backed_connectivity,
            reason="no executable check is backed by structured behavior, requirement, or port evidence",
        ),
        ArtifactQualityRequirement(
            requirement_id="clock_for_sequential_checks",
            description="Sequential cocotb checks require a known clock input.",
            satisfied=not has_sequential_checks
            or any(port.name == clock_name and port.direction == "input" for port in plan.ports),
            reason="increment/hold checks were generated without a structured clock input",
        ),
        ArtifactQualityRequirement(
            requirement_id="unambiguous_control_domains",
            description="Generated sequential cocotb checks require an explicit behavior or protocol clock domain.",
            satisfied=not has_sequential_checks
            or has_async_fifo_scenario
            or has_reset_domain_scenario
            or (len(plan.clocks) <= 1 and len(plan.resets) <= 1)
            or (
                bool(plan.control_domains)
                and len(plan.resets) <= 1
                and all(behavior.domain_id is not None for behavior in plan.behaviors)
                and all(protocol.clock is not None for protocol in plan.protocols)
            ),
            reason="multi-clock or multi-reset behavior lacks explicit domain mapping",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_parameter_values",
            description="Cocotb generation requires safely renderable numeric elaborated parameters.",
            satisfied=all(
                parameter.local or parameter.default_value is None or safe_parameter_value(parameter.default_value)
                for parameter in plan.parameters
            ),
            reason="an elaborated parameter is not a supported numeric literal",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_semantic_features",
            description="Executable cocotb checks must not guess unsupported RTL semantics.",
            satisfied=all(feature.supports_target(VerificationTarget.COCOTB) for feature in plan.semantic_features),
            reason="the plan contains unsupported semantic features",
        ),
    )


def _is_zero_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.lower().replace("_", "")
    if normalized in {"0", "'0", "1'b0", "1'h0", "1'd0"}:
        return True
    if "'" in normalized:
        return normalized.rsplit("'", 1)[-1].lstrip("s").lstrip("bhd") == "0"
    return False


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
