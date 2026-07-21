"""Verilog generator backend."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dv_platform.core.models import ArtifactKind, EvidenceRef, GeneratedArtifact, VerificationPlan, VerificationTarget
from dv_platform.generators.protocols import sv_register_accesses
from dv_platform.generators.signals import (
    artifact_trace,
    inout_ports,
    port_names,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    structured_quality_requirements,
    sv_parameter_clause,
    verilog_declaration,
)
from dv_platform.generators.signals import (
    input_ports as structured_input_ports,
)
from dv_platform.generators.signals import (
    output_ports as structured_output_ports,
)


class VerilogGenerator:
    """Generate conservative Verilog module-level testbench scaffolds."""

    target = VerificationTarget.VERILOG

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        return [
            GeneratedArtifact(
                path=Path(f"tb_{module_name}.v"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _testbench_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=provenance_refs(plan),
                quality_requirements=structured_quality_requirements(plan, "Verilog"),
                traceability=artifact_trace(plan, f"tb_{module_name}", target=self.target),
            )
        ]


def _testbench_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    tb_name = f"tb_{module_name}"
    ports = port_names(plan)
    clock_name = primary_clock_name(plan, ports)
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    input_ports = structured_input_ports(plan, ports)
    output_ports = structured_output_ports(plan, ports)
    declarations = _signal_declarations(plan, input_ports, output_ports)

    lines = [
        "// Generated Verilog testbench scaffold for " + plan.module + ".",
        "`timescale 1ns/1ps",
        "",
        "module " + tb_name + ";",
        *("    " + declaration for declaration in declarations),
        "",
        "    " + (plan.design_unit or plan.module) + sv_parameter_clause(plan) + " dut (",
        *_comma_terminate("        ." + port + "(" + port + ")" for port in ports),
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

    lines.append("    initial begin")
    for port in input_ports:
        if port != clock_name:
            lines.append("        " + port + " = 1'b0;")
    if reset_name:
        active_low = (
            reset.active_low if reset is not None and reset.active_low is not None else reset_name.endswith("_n")
        )
        active = "1'b0" if active_low else "1'b1"
        inactive = "1'b1" if active_low else "1'b0"
        lines.extend(
            [
                "        " + reset_name + " = " + active + ";",
                "        #20;",
                "        " + reset_name + " = " + inactive + ";",
            ]
        )
    lines.extend(sv_register_accesses(plan))
    lines.extend(["        #100;", "        $finish;", "    end"])

    if plan.checks:
        lines.extend(["", "    // Planned checks:"])
        lines.extend("    // - " + check for check in plan.checks)
    if plan.requirements:
        lines.extend(["", "    // Retrieved requirements:"])
        lines.extend("    // - " + requirement for requirement in plan.requirements)

    lines.extend(["", "endmodule"])
    return "\n".join(lines) + "\n"


def _signal_declarations(
    plan: VerificationPlan,
    input_ports: tuple[str, ...],
    output_ports: tuple[str, ...],
) -> tuple[str, ...]:
    if plan.ports:
        inputs = set(input_ports)
        passive = set(output_ports) | set(inout_ports(plan))
        return tuple(
            verilog_declaration(port, variable=port.name in inputs)
            for port in plan.ports
            if port.name in inputs or port.name in passive
        )
    return (
        *("reg " + port + ";" for port in input_ports),
        *("wire " + port + ";" for port in output_ports),
    )


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


def _comma_terminate(lines: Iterable[str]) -> list[str]:
    values = list(lines)
    return [line + ("," if index < len(values) - 1 else "") for index, line in enumerate(values)]


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
