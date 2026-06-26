"""SystemVerilog generator backend."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import ArtifactKind, EvidenceRef, GeneratedArtifact, VerificationPlan, VerificationTarget


class SystemVerilogGenerator:
    """Generate conservative SystemVerilog module-level testbench scaffolds."""

    target = VerificationTarget.SYSTEMVERILOG

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        return [
            GeneratedArtifact(
                path=Path(f"tb_{module_name}.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_testbench_content(plan),
                source_plan_module=plan.module,
                provenance_refs=_unique_refs(tuple(ref for claim in plan.claims for ref in claim.evidence_refs)),
            )
        ]


def _testbench_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    tb_name = f"tb_{module_name}"
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports)
    reset_name = _reset_name(ports)
    input_ports = tuple(port for port in ports if not _looks_like_output(port))
    output_ports = tuple(port for port in ports if _looks_like_output(port))
    declarations = _signal_declarations(input_ports, output_ports)
    connections = _connections(ports)

    lines = [
        "// Generated SystemVerilog testbench scaffold for " + plan.module + ".",
        "`timescale 1ns/1ps",
        "",
        "module " + tb_name + ";",
        *("    " + declaration for declaration in declarations),
        "",
        "    " + plan.module + " dut (",
        *_comma_terminate("        ." + port + "(" + port + ")" for port in connections),
        "    );",
        "",
    ]

    if clock_name:
        lines.extend(
            [
                "    initial " + clock_name + " = 1'b0;",
                "    always #5 " + clock_name + " = ~" + clock_name + ";",
                "",
            ]
        )

    lines.extend(["    initial begin"])
    for port in input_ports:
        if port != clock_name:
            lines.append("        " + port + " = '0;")
    if reset_name:
        active = "1'b0" if reset_name.endswith("_n") else "1'b1"
        inactive = "1'b1" if reset_name.endswith("_n") else "1'b0"
        lines.extend(
            [
                "        " + reset_name + " = " + active + ";",
                "        #20;",
                "        " + reset_name + " = " + inactive + ";",
            ]
        )
    lines.extend(["        #100;", "        $finish;", "    end"])

    if plan.checks:
        lines.extend(["", "    // Planned checks:"])
        lines.extend("    // - " + check for check in plan.checks)
    if plan.requirements:
        lines.extend(["", "    // Retrieved requirements:"])
        lines.extend("    // - " + requirement for requirement in plan.requirements)

    lines.extend(["", "endmodule"])
    return "\n".join(lines) + "\n"


def _signal_declarations(input_ports: tuple[str, ...], output_ports: tuple[str, ...]) -> tuple[str, ...]:
    declarations: list[str] = []
    for port in input_ports:
        declarations.append("logic " + port + ";")
    for port in output_ports:
        declarations.append("wire " + port + ";")
    return tuple(declarations)


def _connections(ports: tuple[str, ...]) -> tuple[str, ...]:
    return ports or ("/* no extracted ports */",)


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
    return next((port for port in ports if port in {"clk", "clock"} or port.endswith(("_clk", "_clock"))), None)


def _reset_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (
            port
            for port in ports
            if port in {"rst", "reset", "rst_n", "reset_n"} or port.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
        ),
        None,
    )


def _looks_like_output(port: str) -> bool:
    return port.endswith(("_o", "_out"))


def _comma_terminate(lines: object) -> list[str]:
    values = list(lines)
    return [line + ("," if index < len(values) - 1 else "") for index, line in enumerate(values)]


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
