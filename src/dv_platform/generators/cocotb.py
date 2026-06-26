"""cocotb generator backend."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    EvidenceRef,
    GeneratedArtifact,
    VerificationPlan,
    VerificationTarget,
)


class CocotbGenerator:
    """Generate initial cocotb smoke tests from a verification plan."""

    target = VerificationTarget.COCOTB

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        return [
            GeneratedArtifact(
                path=Path("test_" + _safe_identifier(plan.module) + ".py"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_test_content(plan),
                source_plan_module=plan.module,
                provenance_refs=_unique_refs(
                    (
                        *tuple(ref for behavior in plan.behaviors for ref in behavior.evidence_refs),
                        *tuple(ref for claim in plan.claims for ref in claim.evidence_refs),
                    )
                ),
                quality_requirements=_quality_requirements(plan),
            )
        ]


def _test_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports) or "clk"
    reset_name = _reset_name(ports) or "rst_n"
    reset_active_value = 0 if reset_name.endswith("_n") else 1
    reset_inactive_value = 1 - reset_active_value
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
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

    if scalar_inputs:
        lines.extend(
            [
                "    for name in " + repr(scalar_inputs) + ":",
                "        _drive_if_present(dut, name, 0)",
                "",
            ]
        )

    lines.extend(
        [
            "    reset = _maybe_signal(dut, " + repr(reset_name) + ")",
            "    if reset is not None:",
            "        reset.value = " + str(reset_active_value),
            "        if clock is not None:",
            "            await RisingEdge(clock)",
            "        else:",
            "            await Timer(20, unit='ns')",
            *("        _assert_signal_int(dut, " + repr(output) + ", 0)" for output in reset_zero_outputs),
            "        reset.value = " + str(reset_inactive_value),
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
        lines.extend(
            [
                "    _drive_if_present(dut, " + repr(input_name) + ", 1)",
                "    before = _signal_int(dut, " + repr(output_name) + ")",
                "    if clock is not None:",
                "        await RisingEdge(clock)",
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
        lines.extend(
            [
                "    _drive_if_present(dut, " + repr(input_name) + ", 0)",
                "    before = _signal_int(dut, " + repr(output_name) + ")",
                "    if clock is not None:",
                "        await RisingEdge(clock)",
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


def _structured_ports(plan: VerificationPlan) -> dict[str, object]:
    return {port.name: port for port in plan.ports}


def _scalar_input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str,
) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        return tuple(
            port.name
            for port in plan.ports
            if port.direction == "input"
            and port.name not in {clock_name, reset_name}
            and port.width in (None, 1)
        )
    return tuple(port for port in ports if _looks_like_scalar_input(port) and port not in {clock_name, reset_name})


def _output_ports(plan: VerificationPlan, ports: tuple[str, ...]) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        return tuple(port.name for port in plan.ports if port.direction == "output")
    return tuple(port for port in ports if _looks_like_output(port))


def _clock_name(ports: tuple[str, ...]) -> str | None:
    return next((port for port in ports if port in {"clk", "clock"} or port.endswith("_clk") or port.endswith("_clock")), None)


def _reset_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (
            port
            for port in ports
            if port in {"rst", "reset", "rst_n", "reset_n"}
            or port.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
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
        if behavior.kind == "increment"
        and behavior.target in output_ports
        and behavior.control in scalar_inputs
    )
    text = _plan_intent_text(plan)
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
    text = _plan_intent_text(plan)
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


def _quality_requirements(plan: VerificationPlan) -> tuple[ArtifactQualityRequirement, ...]:
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports) or "clk"
    reset_name = _reset_name(ports) or "rst_n"
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
    output_ports = _output_ports(plan, ports)
    reset_checks = _reset_zero_outputs(plan, output_ports, reset_name)
    increment_checks = _increment_checks(plan, output_ports, scalar_inputs)
    hold_checks = _hold_checks(plan, output_ports, scalar_inputs)
    has_sequential_checks = bool(increment_checks or hold_checks)
    has_backed_checks = bool(reset_checks or increment_checks or hold_checks)
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
            satisfied=has_backed_checks and bool(plan.behaviors or plan.structured_requirements),
            reason="no reset/increment/hold check is backed by structured behavior or requirement evidence",
        ),
        ArtifactQualityRequirement(
            requirement_id="clock_for_sequential_checks",
            description="Sequential cocotb checks require a known clock input.",
            satisfied=not has_sequential_checks or any(port.name == clock_name and port.direction == "input" for port in plan.ports),
            reason="increment/hold checks were generated without a structured clock input",
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


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
