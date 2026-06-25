"""cocotb generator backend."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import ArtifactKind, EvidenceRef, GeneratedArtifact, VerificationPlan, VerificationTarget


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
                provenance_refs=_unique_refs(tuple(ref for claim in plan.claims for ref in claim.evidence_refs)),
            )
        ]


def _test_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports) or "clk"
    reset_name = _reset_name(ports) or "rst_n"
    reset_active_value = 0 if reset_name.endswith("_n") else 1
    reset_inactive_value = 1 - reset_active_value
    scalar_inputs = tuple(port for port in ports if _looks_like_scalar_input(port) and port not in {clock_name, reset_name})
    output_ports = tuple(port for port in ports if _looks_like_output(port))
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
            "        await Timer(20, unit='ns')",
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
            "def _assert_resolvable(dut, name):",
            "    signal = _maybe_signal(dut, name)",
            "    if signal is not None and hasattr(signal.value, 'is_resolvable'):",
            "        assert signal.value.is_resolvable, f'{name} is unresolved: {signal.value}'",
        ]
    )

    return "\n".join(lines) + "\n"


def _port_names_from_plan(plan: VerificationPlan) -> tuple[str, ...]:
    ports: list[str] = []
    prefix = f"port:{plan.module}."
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            locator = ref.locator.split("@", 1)[0]
            if locator.startswith(prefix):
                ports.append(locator.removeprefix(prefix))
    return tuple(dict.fromkeys(ports))


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


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
