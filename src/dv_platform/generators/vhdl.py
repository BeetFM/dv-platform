"""VHDL generator backend."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    EvidenceRef,
    GeneratedArtifact,
    RTLParameter,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.signals import (
    artifact_trace,
    inout_ports,
    port_by_name,
    port_names,
    primary_clock_name,
    primary_reset,
    provenance_refs,
    structured_quality_requirements,
    vhdl_type,
)
from dv_platform.generators.signals import (
    input_ports as structured_input_ports,
)
from dv_platform.generators.signals import (
    output_ports as structured_output_ports,
)


class VhdlGenerator:
    """Generate conservative VHDL module-level testbench scaffolds."""

    target = VerificationTarget.VHDL

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        return [
            GeneratedArtifact(
                path=Path(f"tb_{module_name}.vhd"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_testbench_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=provenance_refs(plan),
                quality_requirements=_quality_requirements(plan),
                traceability=artifact_trace(plan, f"tb_{module_name}"),
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
    parameter_mappings = tuple(
        f"            {parameter.name} => {_vhdl_parameter_value(parameter)}"
        for parameter in plan.parameters
        if not parameter.local and parameter.default_value is not None and _vhdl_parameter_value(parameter) is not None
    )

    lines = [
        "-- Generated VHDL testbench scaffold for " + plan.module + ".",
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "",
        "entity " + tb_name + " is",
        "end entity;",
        "",
        "architecture sim of " + tb_name + " is",
        *(_signal_declaration(plan, port, initialize=True) for port in input_ports),
        *(_signal_declaration(plan, port, initialize=False) for port in output_ports),
        *(_signal_declaration(plan, port, initialize=False) for port in inout_ports(plan)),
        "begin",
        "    dut: entity work." + (plan.design_unit or plan.module),
        *(
            (
                "        generic map (",
                *_comma_terminate(parameter_mappings),
                "        )",
            )
            if parameter_mappings
            else ()
        ),
        "        port map (",
        *_comma_terminate("            " + port + " => " + port for port in ports),
        "        );",
        "",
    ]

    if clock_name:
        lines.extend(
            [
                "    clk_process: process",
                "    begin",
                "        " + clock_name + " <= '0';",
                "        wait for 5 ns;",
                "        " + clock_name + " <= '1';",
                "        wait for 5 ns;",
                "    end process;",
                "",
            ]
        )

    lines.extend(["    stimulus: process", "    begin"])
    if reset_name:
        active_low = (
            reset.active_low if reset is not None and reset.active_low is not None else reset_name.endswith("_n")
        )
        active = "'0'" if active_low else "'1'"
        inactive = "'1'" if active_low else "'0'"
        lines.extend(
            [
                "        " + reset_name + " <= " + active + ";",
                "        wait for 20 ns;",
                "        " + reset_name + " <= " + inactive + ";",
            ]
        )
    lines.extend(["        wait for 100 ns;", "        wait;", "    end process;"])

    if plan.checks:
        lines.extend(["", "    -- Planned checks:"])
        lines.extend("    -- - " + check for check in plan.checks)
    if plan.requirements:
        lines.extend(["", "    -- Retrieved requirements:"])
        lines.extend("    -- - " + requirement for requirement in plan.requirements)

    lines.extend(["end architecture;"])
    return "\n".join(lines) + "\n"


def _signal_declaration(plan: VerificationPlan, name: str, initialize: bool) -> str:
    port = port_by_name(plan, name)
    signal_type = vhdl_type(port) if port is not None else "std_logic"
    initial = ""
    if initialize:
        initial = " := (others => '0')" if port is not None and port.width is not None and port.width > 1 else " := '0'"
    return f"    signal {name} : {signal_type}{initial};"


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


def _vhdl_parameter_value(parameter: RTLParameter) -> str | None:
    if parameter.default_value is None:
        return None
    converted = sv_numeric_literal_to_int(
        parameter.default_value,
        width=parameter.width,
        signed=parameter.signed,
    )
    return str(converted) if converted is not None else None


def _quality_requirements(plan: VerificationPlan) -> tuple[ArtifactQualityRequirement, ...]:
    requirements = structured_quality_requirements(plan, "VHDL")
    parameters_supported = all(
        parameter.local or parameter.default_value is None or _vhdl_parameter_value(parameter) is not None
        for parameter in plan.parameters
    )
    return tuple(
        replace(
            requirement,
            satisfied=parameters_supported,
            reason=None if parameters_supported else "an elaborated parameter cannot be represented as a VHDL integer",
        )
        if requirement.requirement_id == "supported_parameter_values"
        else requirement
        for requirement in requirements
    )
