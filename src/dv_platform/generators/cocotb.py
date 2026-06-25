"""cocotb generator backend."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import ArtifactKind, GeneratedArtifact, VerificationPlan, VerificationTarget


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
                provenance_refs=tuple(ref for claim in plan.claims for ref in claim.evidence_refs),
            )
        ]


def _test_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
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
        "    clock = getattr(dut, 'clk', None)",
        "    if clock is not None:",
        "        cocotb.start_soon(Clock(clock, 10, units='ns').start())",
        "",
        "    reset = getattr(dut, 'rst_n', None)",
        "    if reset is not None:",
        "        reset.value = 0",
        "        await Timer(20, units='ns')",
        "        reset.value = 1",
        "",
        "    if clock is not None:",
        "        await RisingEdge(clock)",
        "    else:",
        "        await Timer(1, units='ns')",
        "",
        "    assert dut is not None",
    ]

    if plan.checks:
        lines.extend(["", "    # Planned checks represented by this smoke test:"])
        lines.extend("    # - " + check for check in plan.checks)
    if plan.requirements:
        lines.extend(["", "    # Retrieved requirements:"])
        lines.extend("    # - " + requirement for requirement in plan.requirements)

    return "\n".join(lines) + "\n"


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
