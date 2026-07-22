"""Formal generator backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import parse

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    ArtifactTrace,
    GeneratedArtifact,
    RTLCDCPath,
    RTLPort,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.peripherals import (
    formal_peripheral_assertions,
    formal_peripheral_output_signals,
    peripheral_mapped_outputs,
)
from dv_platform.generators.protocols import (
    formal_ahb_lite_assertions,
    formal_ahb_lite_declarations,
    formal_apb4_assertions,
    formal_apb4_declarations,
    formal_axi4_lite_assertions,
    formal_axi4_lite_declarations,
    formal_profile_assertions,
    formal_profile_declarations,
)
from dv_platform.generators.scenario_registry import scenario_is_executable
from dv_platform.generators.signals import (
    artifact_trace,
    artifact_trace_for_scenario,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    safe_parameter_value,
    sv_parameter_clause,
)


class CDCProofPolicy(StrEnum):
    """Permitted evidence levels for generated CDC properties."""

    FAIL_CLOSED = "fail-closed"
    BOUNDED = "bounded"
    STRUCTURAL = "structural"


@dataclass(frozen=True)
class _CDCPathEvidence:
    path_id: str
    signal: str
    evidence_level: str
    closure_eligible: bool
    task: str | None
    clock: str | None
    observed_stages: tuple[str, ...]
    hidden_stages: tuple[str, ...]
    latency_cycles: int
    bound_steps: int | None
    reason: str | None


class FormalGenerator:
    """Generate evidence-backed SymbiYosys collateral from a plan."""

    target = VerificationTarget.FORMAL

    def __init__(
        self,
        cdc_policy: CDCProofPolicy | str = CDCProofPolicy.FAIL_CLOSED,
        cdc_bmc_depth: int = 20,
    ) -> None:
        self.cdc_policy = CDCProofPolicy(cdc_policy)
        if cdc_bmc_depth <= 0:
            raise ValueError("CDC BMC depth must be greater than zero")
        self.cdc_bmc_depth = cdc_bmc_depth

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        refs = provenance_refs(plan)
        module_name = _safe_identifier(plan.module)
        cdc_evidence = _cdc_evidence(plan, self.cdc_policy, self.cdc_bmc_depth)
        if self.cdc_policy == CDCProofPolicy.STRUCTURAL:
            unsupported = tuple(item for item in cdc_evidence if item.evidence_level == "unsupported")
            if unsupported:
                details = "; ".join(f"{item.path_id}: {item.reason}" for item in unsupported)
                raise ValueError(f"Structural CDC policy requirements are not met: {details}")
        artifacts = [
            GeneratedArtifact(
                path=Path(f"formal_{module_name}.sv"),
                kind=ArtifactKind.FORMAL_HARNESS,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _harness_content(plan, cdc_evidence),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=_quality_requirements(plan, cdc_evidence),
                traceability=_formal_traceability(plan, f"formal_{module_name}_properties"),
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}.sby"),
                kind=ArtifactKind.RUN_SCRIPT,
                target=self.target,
                content=_sby_mapping_header(plan)
                + _sby_content(
                    plan,
                    bounded_cdc=any(item.evidence_level == "bounded" for item in cdc_evidence),
                    multiclock=any(item.evidence_level in {"bounded", "structural"} for item in cdc_evidence),
                    cdc_bmc_depth=self.cdc_bmc_depth,
                ),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=_quality_requirements(plan, cdc_evidence),
                traceability=_formal_traceability(plan, f"formal_{module_name}_run"),
            ),
        ]
        if plan.cdc_paths:
            artifacts.append(
                GeneratedArtifact(
                    path=Path(f"formal_{module_name}_cdc.json"),
                    kind=ArtifactKind.REPORT,
                    target=self.target,
                    content=_cdc_report_content(plan, self.cdc_policy, self.cdc_bmc_depth, cdc_evidence),
                    source_plan_module=plan.module,
                    design_unit=plan.design_unit or plan.module,
                    elaborated_design_unit=plan.elaborated_design_unit,
                    specialization_id=plan.specialization_id,
                    elaborated_parameters=plan.parameters,
                    provenance_refs=refs,
                    traceability=_cdc_report_traceability(plan, f"formal_{module_name}_cdc_evidence"),
                )
            )
        return artifacts


def _formal_traceability(plan: VerificationPlan, fallback_symbol: str) -> tuple[ArtifactTrace, ...]:
    scenario_traces = tuple(
        trace
        for scenario in plan.scenarios
        if scenario.kind.startswith(
            ("apb4_", "axi4_lite_", "cdc_", "reset_domain_", "uart_", "spi_", "i2c_", "gpio_timer_interrupt_")
        )
        and scenario_is_executable(scenario, VerificationTarget.FORMAL)
        for trace in artifact_trace_for_scenario(
            plan,
            scenario,
            f"formal_{_safe_identifier(plan.module)}_scenario_{scenario.scenario_id.rsplit(':', 1)[-1]}",
        )
    )
    fallback_traces = artifact_trace(
        plan,
        fallback_symbol,
        target=VerificationTarget.FORMAL,
        categories=("reset", "increment", "hold", "protocol", "memory", "cdc", "formal"),
    )
    return tuple({trace.trace_id: trace for trace in (*scenario_traces, *fallback_traces)}.values())


def _cdc_report_traceability(plan: VerificationPlan, symbol: str) -> tuple[ArtifactTrace, ...]:
    traces = artifact_trace(
        plan,
        symbol,
        target=VerificationTarget.FORMAL,
        categories=("cdc",),
    )
    return tuple(trace for trace in traces if trace.check_ids)


def _sby_mapping_header(plan: VerificationPlan) -> str:
    if not plan.protocol_models and not plan.register_models:
        return ""
    lines = ["# Deterministic protocol/register mappings for formal."]
    lines.extend(f"# protocol={protocol.name}" for protocol in plan.protocol_models)
    lines.extend(f"# register={register.name}" for register in plan.register_models)
    return "\n".join(lines) + "\n\n"


def _harness_content(
    plan: VerificationPlan,
    cdc_evidence: tuple[_CDCPathEvidence, ...] | None = None,
) -> str:
    module_name = _safe_identifier(plan.module)
    harness_name = f"formal_{module_name}"
    ports = _port_names_from_plan(plan)
    resolved_cdc_evidence = cdc_evidence or _cdc_evidence(plan, CDCProofPolicy.FAIL_CLOSED, 20)
    cdc_clocks = {
        item.clock
        for item in resolved_cdc_evidence
        if item.evidence_level in {"structural", "bounded"} and item.clock in ports
    }
    primary_clock = (
        primary_clock_name(plan, ports)
        or (plan.protocol_models[0].clock_domain if plan.protocol_models else None)
        or "clk"
    )
    alternate_clock = next(
        (
            port
            for port in ports
            if port not in cdc_clocks
            and any(clock.name == port and clock.direction == "input" for clock in plan.clocks)
        ),
        None,
    )
    has_reset_domain_scenarios = any(
        scenario.kind == "reset_domain_sequence" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
        for scenario in plan.scenarios
    )
    clock_name = (
        "dv_formal_clock"
        if has_reset_domain_scenarios
        else alternate_clock or "dv_formal_clock"
        if cdc_clocks and primary_clock in cdc_clocks
        else primary_clock
    )
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    reset_active_low = (
        reset.active_low
        if reset is not None and reset.active_low is not None
        else bool(reset_name and reset_name.endswith("_n"))
    )
    qualified_reset_values = {
        policy.subject: ("1'b1" if policy.subject.endswith("_n") else "1'b0")
        for policy in plan.depth_policies
        if policy.kind == "reset"
        and any(
            scenario.kind == "reset_domain_sequence"
            and dict(scenario.stimulus[0].parameters).get("reset") == policy.subject
            and scenario_is_executable(scenario, VerificationTarget.FORMAL)
            for scenario in plan.scenarios
        )
    }
    scalar_inputs = _input_ports(plan, ports, clock_name, reset_name)
    connected_ports = tuple(
        dict.fromkeys(
            (*(port for port in (clock_name if clock_name in ports else None, reset_name) if port), *scalar_inputs)
        )
    )
    unconnected_outputs = _output_ports(plan, ports)
    generic_outputs = tuple(port for port in unconnected_outputs if port not in peripheral_mapped_outputs(plan))
    reset_zero_outputs = _reset_zero_outputs(plan, generic_outputs, reset_name)
    increment_checks = _increment_checks(plan, generic_outputs, scalar_inputs)
    hold_checks = _hold_checks(plan, generic_outputs, scalar_inputs)
    checked_outputs = tuple(
        dict.fromkeys(
            (
                *reset_zero_outputs,
                *(output for output, _input in increment_checks),
                *(output for output, _input in hold_checks),
                *(
                    signal
                    for protocol in plan.protocols
                    if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source"
                    for signal in (protocol.valid, protocol.data)
                    if signal is not None
                ),
                *(stage for path in plan.cdc_paths for stage in path.stage_signals if stage in unconnected_outputs),
                *(_async_fifo_output_signals(plan)),
                *(_reset_domain_output_signals(plan)),
                *(_bounded_sram_output_signals(plan)),
                *(_formal_contract_output_signals(plan)),
                *(formal_peripheral_output_signals(plan)),
                *(
                    actual
                    for protocol in plan.protocol_models
                    for canonical, actual in protocol.signal_bindings
                    if dict(protocol.signal_directions).get(canonical) == "output"
                ),
            )
        )
    )
    output_declarations = _output_wire_declarations(plan, checked_outputs)

    lines = [
        "// Generated formal harness for " + plan.module + ".",
        "`default_nettype none",
        "",
        "module " + harness_name + ";",
        "    (* gclk *) reg " + clock_name + ";",
    ]
    if reset_name:
        reset_initial = "1'b0" if reset_active_low else "1'b1"
        lines.append("    reg " + reset_name + " = " + reset_initial + ";")
    input_declarations = _input_reg_declarations(plan, scalar_inputs)
    for name in scalar_inputs:
        lines.append("    " + input_declarations.get(name, "reg " + name) + " = '0;")
    for name in checked_outputs:
        lines.append("    " + output_declarations.get(name, "wire " + name) + ";")
    lines.extend(formal_apb4_declarations(plan))
    lines.extend(formal_axi4_lite_declarations(plan))
    lines.extend(formal_ahb_lite_declarations(plan))
    lines.extend(formal_profile_declarations(plan))
    lines.extend(_bounded_sram_declarations(plan))
    lines.extend(_formal_contract_declarations(plan))

    parameter_clause = sv_parameter_clause(plan)
    lines.extend(["", "    " + (plan.design_unit or plan.module) + parameter_clause + " dut ("])
    port_connections = ["        ." + name + "(" + name + ")" for name in connected_ports]
    port_connections.extend(
        "        ." + name + "(" + name + ")" if name in checked_outputs else "        ." + name + "()"
        for name in unconnected_outputs
    )
    lines.extend(_comma_terminate(port_connections))
    lines.extend(["    );", ""])

    lines.extend(["    always @(posedge " + clock_name + ") begin"])
    if reset_name:
        reset_active = "1'b0" if reset_active_low else "1'b1"
        reset_inactive = "1'b1" if reset_active_low else "1'b0"
        lines.extend(
            [
                "        if ($initstate) begin",
                "            assume(" + reset_name + " == " + reset_active + ");",
                "        end else begin",
                "            assume(" + reset_name + " == " + reset_inactive + ");",
                "        end",
                "        " + reset_name + " <= " + qualified_reset_values.get(reset_name, "$anyseq") + ";",
                "        c_reset_asserted: cover(" + reset_name + " == " + reset_active + ");",
                "        c_reset_released: cover(!$initstate && " + reset_name + " == " + reset_inactive + ");",
            ]
        )
        for name in scalar_inputs:
            lines.append("        " + name + " <= " + qualified_reset_values.get(name, "$anyseq") + ";")
        for name in reset_zero_outputs:
            lines.extend(
                [
                    "        if (!$initstate && $past(" + reset_name + " == " + reset_active + ")) begin",
                    "            assert(" + name + " == '0);",
                    "        end",
                ]
            )
        for output_name, input_name in increment_checks:
            lines.extend(
                [
                    "        if (!$initstate && $past("
                    + reset_name
                    + " == "
                    + reset_inactive
                    + ") && "
                    + reset_name
                    + " == "
                    + reset_inactive
                    + " && $past("
                    + input_name
                    + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + ") + 1'b1);",
                    "        end",
                ]
            )
        for output_name, input_name in hold_checks:
            lines.extend(
                [
                    "        if (!$initstate && $past("
                    + reset_name
                    + " == "
                    + reset_inactive
                    + ") && "
                    + reset_name
                    + " == "
                    + reset_inactive
                    + " && !$past("
                    + input_name
                    + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + "));",
                    "        end",
                ]
            )
        lines.extend(_ready_valid_assertions(plan, reset_name, reset_inactive))
        lines.extend(formal_apb4_assertions(plan, reset_name, reset_active, reset_inactive))
        lines.extend(formal_axi4_lite_assertions(plan, reset_name, reset_active, reset_inactive))
        lines.extend(formal_ahb_lite_assertions(plan, reset_name, reset_active, reset_inactive))
        lines.extend(formal_profile_assertions(plan, reset_name, reset_active))
        lines.extend(_memory_write_assertions(plan, reset_name, reset_inactive, clock_name))
        lines.extend(_memory_collision_assertions(plan, reset_name, reset_inactive, clock_name))
        lines.extend(_bounded_sram_assertions(plan, reset_name, reset_active, reset_inactive, clock_name))
        lines.extend(_formal_contract_assertions(plan, reset_name, reset_active, reset_inactive, clock_name))
        lines.extend(formal_peripheral_assertions(plan, reset_name, reset_active, reset_inactive))
        cover_expression = reset_name + " == " + reset_inactive
        if scalar_inputs:
            joined_inputs = " || ".join(scalar_inputs)
            cover_expression += " && " + (f"({joined_inputs})" if len(scalar_inputs) > 1 else joined_inputs)
    else:
        for name in scalar_inputs:
            lines.append("        " + name + " <= " + qualified_reset_values.get(name, "$anyseq") + ";")
        for output_name, input_name in increment_checks:
            lines.extend(
                [
                    "        if (!$initstate && $past(" + input_name + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + ") + 1'b1);",
                    "        end",
                ]
            )
        for output_name, input_name in hold_checks:
            lines.extend(
                [
                    "        if (!$initstate && !$past(" + input_name + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + "));",
                    "        end",
                ]
            )
        lines.extend(_ready_valid_assertions(plan, None, None))
        lines.extend(formal_apb4_assertions(plan, None, None, None))
        lines.extend(formal_ahb_lite_assertions(plan, None, None, None))
        lines.extend(formal_profile_assertions(plan, None, None))
        lines.extend(_memory_write_assertions(plan, None, None, clock_name))
        lines.extend(_memory_collision_assertions(plan, None, None, clock_name))
        lines.extend(_bounded_sram_assertions(plan, None, None, None, clock_name))
        lines.extend(_formal_contract_assertions(plan, None, None, None, clock_name))
        lines.extend(formal_peripheral_assertions(plan, None, None, None))
        cover_expression = " || ".join(scalar_inputs) if scalar_inputs else "!$initstate"

    lines.append("        cover(" + cover_expression + ");")
    lines.extend(["    end", ""])
    lines.extend(_cdc_assertions(plan, resolved_cdc_evidence))
    lines.extend(_async_fifo_assertions(plan))
    lines.extend(_reset_domain_assertions(plan))
    lines.extend(["", "endmodule", "`default_nettype wire"])
    return "\n".join(lines) + "\n"


def _sby_content(
    plan: VerificationPlan,
    *,
    bounded_cdc: bool = False,
    multiclock: bool = False,
    cdc_bmc_depth: int = 20,
) -> str:
    module_name = _safe_identifier(plan.module)
    harness_name = f"formal_{module_name}"
    depth = _proof_depth(plan)
    tasks = ["prove", "cover"]
    bounded_protocol = any(
        scenario.kind.startswith(
            (
                "apb4_",
                "axi4_lite_",
                "ahb_lite_",
                "cdc_",
                "reset_domain_",
                "memory_",
                "uart_",
                "spi_",
                "i2c_",
                "gpio_timer_interrupt_",
                "protocol_profile_",
            )
        )
        and scenario_is_executable(scenario, VerificationTarget.FORMAL)
        for scenario in plan.scenarios
    )
    if bounded_protocol:
        executable_protocol_scenarios = tuple(
            scenario
            for scenario in plan.scenarios
            if scenario.kind.startswith(
                (
                    "apb4_",
                    "axi4_lite_",
                    "ahb_lite_",
                    "cdc_",
                    "reset_domain_",
                    "memory_",
                    "uart_",
                    "spi_",
                    "i2c_",
                    "gpio_timer_interrupt_",
                    "protocol_profile_",
                )
            )
            and scenario_is_executable(scenario, VerificationTarget.FORMAL)
        )
        scenario_depth = max(scenario.completion.timeout_cycles + 2 for scenario in executable_protocol_scenarios)
        if all(scenario.kind.startswith("memory_") for scenario in executable_protocol_scenarios):
            minimum_depth = 6
        elif all(scenario.kind.startswith("axi4_lite_") for scenario in executable_protocol_scenarios):
            minimum_depth = 7
        else:
            minimum_depth = 10
        # Keep the open-source lane within its governed 20-cycle proof horizon.
        # Longer configured timeouts remain exercised dynamically and can be
        # promoted by an imported vendor proof; the generated local assertions
        # use the same bounded horizon rather than becoming vacuous.
        depth = max(minimum_depth, min(depth, scenario_depth))
    options = [f"prove: mode {'bmc' if bounded_protocol else 'prove'}", "cover: mode cover"]
    if bounded_protocol:
        options.extend((f"prove: depth {depth}", f"cover: depth {depth}"))
    if multiclock:
        options.append("multiclock on")
    script = [f"read -formal formal_{module_name}.sv"]
    if bounded_cdc:
        tasks.append("cdc_bmc")
        options.extend(
            (
                "cdc_bmc: mode bmc",
                f"prove: depth {depth}",
                f"cover: depth {depth}",
                f"cdc_bmc: depth {cdc_bmc_depth}",
            )
        )
        script = [
            f"prove: read -formal formal_{module_name}.sv",
            f"cover: read -formal formal_{module_name}.sv",
            f"cdc_bmc: read -formal -D DV_CDC_BOUNDED formal_{module_name}.sv",
        ]
    else:
        options.append(f"depth {depth}")
    engines = ("smtbmc --nopresat --unroll z3" if bounded_protocol else "smtbmc z3",)
    return "\n".join(
        [
            "[tasks]",
            *tasks,
            "",
            "[options]",
            *options,
            "",
            "[engines]",
            *engines,
            "",
            "[script]",
            *script,
            "# RTL source files are supplied by the formal runner from the execution manifest.",
            f"prep -top {harness_name}",
            "",
            "[files]",
            f"formal_{module_name}.sv",
            "",
        ]
    )


def _proof_depth(plan: VerificationPlan) -> int:
    latency_cycles = [
        int(requirement.expected_value.split()[0])
        for requirement in plan.structured_requirements
        if requirement.category == "latency"
        and requirement.expected_value is not None
        and requirement.expected_value.split()[0].isdigit()
    ]
    return max((20, *(cycle + 5 for cycle in latency_cycles)))


def _quality_requirements(
    plan: VerificationPlan,
    cdc_evidence: tuple[_CDCPathEvidence, ...] = (),
) -> tuple[ArtifactQualityRequirement, ...]:
    ports = _port_names_from_plan(plan)
    clock_name = primary_clock_name(plan, ports) or "clk"
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
    output_ports = _output_ports(plan, ports)
    reset_checks = _reset_zero_outputs(plan, output_ports, reset_name)
    increment_checks = _increment_checks(plan, output_ports, scalar_inputs)
    hold_checks = _hold_checks(plan, output_ports, scalar_inputs)
    protocol_checks = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source"
    )
    has_mapped_protocols = bool(plan.protocol_models)
    memory_checks = tuple(
        access
        for access in plan.memory_accesses
        if access.kind == "write"
        and access.synchronous
        and len(access.address_signals) == 1
        and len(access.data_signals) == 1
        and bool(access.enable_signals)
    )
    memory_collision_checks = tuple(
        policy
        for policy in plan.depth_policies
        if policy.kind == "memory"
        and policy.parameter("read_during_write") in {"read_first", "write_first", "no_change"}
    )
    formal_contract_checks = _qualified_formal_contract_policies(plan)
    has_sequential_checks = bool(increment_checks or hold_checks or protocol_checks or has_mapped_protocols)
    has_cdc_checks = any(item.evidence_level in {"structural", "bounded"} for item in cdc_evidence)
    has_backed_checks = bool(
        reset_checks
        or increment_checks
        or hold_checks
        or protocol_checks
        or has_mapped_protocols
        or memory_checks
        or memory_collision_checks
        or formal_contract_checks
        or has_cdc_checks
    )
    port_names = tuple(port.name for port in plan.ports)
    directions = {port.direction for port in plan.ports}
    return (
        ArtifactQualityRequirement(
            requirement_id="structured_ports",
            description="Executable formal harnesses require structured port metadata.",
            satisfied=bool(plan.ports),
            reason=None if plan.ports else "plan has no structured ports",
        ),
        ArtifactQualityRequirement(
            requirement_id="unambiguous_port_directions",
            description="Executable formal harnesses require unique input/output port directions.",
            satisfied=bool(plan.ports)
            and len(set(port_names)) == len(port_names)
            and {"input", "output"}.issubset(directions)
            and all(port.direction in {"input", "output", "inout", "ref"} for port in plan.ports),
            reason="ports are missing, duplicated, or lack valid directions",
        ),
        ArtifactQualityRequirement(
            requirement_id="backed_executable_checks",
            description="Executable formal harness must contain assertions backed by plan behaviors or requirements.",
            satisfied=has_backed_checks
            and bool(plan.behaviors or plan.structured_requirements or has_mapped_protocols),
            reason="no reset, state-transition, or protocol assertion is backed by structured evidence",
        ),
        ArtifactQualityRequirement(
            requirement_id="clock_for_sequential_checks",
            description="Sequential formal assertions require a known clock input.",
            satisfied=not has_sequential_checks
            or any(port.name == clock_name and port.direction == "input" for port in plan.ports),
            reason="increment/hold assertions were generated without a structured clock input",
        ),
        ArtifactQualityRequirement(
            requirement_id="resolved_register_protocol_sources",
            description="Formal protocol/register properties require resolved, evidenced source models.",
            satisfied=(
                not plan.register_conflicts
                and all(register.offset is not None and register.evidence_refs for register in plan.register_models)
                and all(
                    protocol.evidence_refs and not protocol.unsupported_semantics for protocol in plan.protocol_models
                )
            ),
            reason="protocol/register sources are incomplete or conflicting",
        ),
        ArtifactQualityRequirement(
            requirement_id="unambiguous_control_domains",
            description="Non-CDC sequential properties require an unambiguous classified clock and reset domain.",
            satisfied=not has_sequential_checks or (len(plan.clocks) <= 1 and len(plan.resets) <= 1),
            reason="non-CDC sequential behavior lacks an explicit property-to-domain mapping",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_parameter_values",
            description="Formal generation requires safely renderable numeric elaborated parameters.",
            satisfied=all(
                parameter.local or parameter.default_value is None or safe_parameter_value(parameter.default_value)
                for parameter in plan.parameters
            ),
            reason="an elaborated parameter is not a supported numeric literal",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_semantic_features",
            description="Formal generation must not guess unsupported RTL semantics.",
            satisfied=all(feature.supports_target(VerificationTarget.FORMAL) for feature in plan.semantic_features),
            reason="the plan contains unsupported semantic features",
        ),
    )


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


def _input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str | None,
) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        excluded = {clock_name}
        if reset_name:
            excluded.add(reset_name)
        return tuple(port.name for port in plan.ports if port.direction == "input" and port.name not in excluded)
    return tuple(port for port in ports if _looks_like_scalar_input(port) and port != clock_name and port != reset_name)


def _scalar_input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str | None,
) -> tuple[str, ...]:
    """Compatibility alias retained for existing generator helper tests."""

    return _input_ports(plan, ports, clock_name, reset_name)


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


def _reset_active_low(reset_name: str) -> bool:
    return reset_name.endswith("_n")


def _reset_zero_outputs(
    plan: VerificationPlan, output_ports: tuple[str, ...], reset_name: str | None
) -> tuple[str, ...]:
    if not reset_name:
        return ()
    behavior_outputs = tuple(
        behavior.target
        for behavior in plan.behaviors
        if behavior.kind == "reset_to_constant"
        and behavior.target in output_ports
        and behavior.control == reset_name
        and _is_zero_value(behavior.value)
    )
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text:
        return tuple(dict.fromkeys(behavior_outputs))
    reset_terms = (reset_name.lower(), "reset", "rst", "clear", "clears", "cleared", "zero")
    if not any(term in requirement_text for term in reset_terms):
        return tuple(dict.fromkeys(behavior_outputs))
    text_outputs = tuple(port for port in output_ports if port.lower() in requirement_text)
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
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text or not any(
        term in requirement_text for term in ("increment", "increments", "increase", "increases")
    ):
        return tuple(dict.fromkeys(behavior_checks))
    text_checks = tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in requirement_text and input_name.lower() in requirement_text
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
    requirement_text = " ".join(hold_requirements or plan.requirements).lower()
    if not requirement_text:
        return ()
    hold_terms = ("hold", "holds", "stable", "unchanged")
    inactive_terms = ("low", "deassert", "deasserted", "false", "0")
    if not any(term in requirement_text for term in hold_terms) or not any(
        term in requirement_text for term in inactive_terms
    ):
        return ()
    return tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in requirement_text and input_name.lower() in requirement_text
    )


def _output_wire_declarations(plan: VerificationPlan, ports: tuple[str, ...]) -> dict[str, str]:
    return {port: _output_wire_declaration(plan, port) for port in ports}


def _input_reg_declarations(plan: VerificationPlan, ports: tuple[str, ...]) -> dict[str, str]:
    declarations: dict[str, str] = {}
    structured = _structured_ports(plan)
    for name in ports:
        port = structured.get(name)
        if port is None:
            declarations[name] = "reg " + name
            continue
        signed = " signed" if port.signed else ""
        packed_range = f" [{port.width - 1}:0]" if port.width is not None and port.width > 1 else ""
        declarations[name] = "reg" + signed + packed_range + " " + name
    return declarations


def _memory_write_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    lines: list[str] = []
    memories = {memory.name: memory for memory in plan.memories}
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    ports = {port.name for port in plan.ports}
    for index, access in enumerate(plan.memory_accesses, start=1):
        if (
            access.kind != "write"
            or not access.synchronous
            or len(access.address_signals) != 1
            or len(access.data_signals) != 1
            or not access.enable_signals
            or access.address_signals[0] not in ports
            or access.data_signals[0] not in ports
            or any(signal not in ports for signal in access.enable_signals)
        ):
            continue
        domain = domains.get(access.domain_id or "")
        if domain is not None and domain.clock != clock_name:
            continue
        memory = memories.get(access.memory)
        if memory is None:
            continue
        address = access.address_signals[0]
        data = access.data_signals[0]
        enable = " && ".join(access.enable_signals)
        reset_guard = (
            f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
            if reset_name and reset_inactive
            else ""
        )
        if memory.depth is not None:
            lines.append(f"        a_memory_address_{index}: assume(!({enable}) || ({address} < {memory.depth}));")
        lines.extend(
            (
                f"        if (!$initstate{reset_guard} && $past({enable})) begin",
                f"            a_memory_write_{index}: assert(dut.{memory.name}[$past({address})] == $past({data}));",
                "        end",
                f"        c_memory_write_{index}: cover({enable});",
                f"        c_memory_low_address_{index}: cover(({enable}) && ({address} == 0));",
                *(
                    [f"        c_memory_high_address_{index}: cover(({enable}) && ({address} == {memory.depth - 1}));"]
                    if memory.depth is not None and memory.depth > 1
                    else []
                ),
            )
        )
    return lines


def _ready_valid_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
) -> list[str]:
    lines: list[str] = []
    for index, protocol in enumerate(plan.protocols, start=1):
        if protocol.kind not in {"ready_valid", "req_ack"} or protocol.role != "source":
            continue
        antecedent = f"$past({protocol.valid} && !{protocol.ready})"
        current_guard = ""
        if reset_name is not None and reset_inactive is not None:
            antecedent = f"$past({reset_name} == {reset_inactive} && {protocol.valid} && !{protocol.ready})"
            current_guard = f" && {reset_name} == {reset_inactive}"
        lines.extend(
            [
                f"        if (!$initstate && {antecedent}{current_guard}) begin",
                f"            assert({protocol.valid});",
                *(
                    [f"            assert({protocol.data} == $past({protocol.data}));"]
                    if protocol.data is not None
                    else []
                ),
                "        end",
                f"        c_protocol_transfer_{index}: cover({protocol.valid} && {protocol.ready});",
                f"        c_protocol_backpressure_{index}: cover({protocol.valid} && !{protocol.ready});",
                f"        c_protocol_recovery_{index}: cover(!$initstate && $past({protocol.valid} && !{protocol.ready}) && {protocol.valid} && {protocol.ready});",
            ]
        )
    return lines


def _memory_collision_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    lines: list[str] = []
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    ports = {port.name for port in plan.ports}
    for policy_index, policy in enumerate(plan.depth_policies, start=1):
        collision = policy.parameter("read_during_write")
        if policy.kind != "memory" or collision not in {"read_first", "write_first", "no_change"}:
            continue
        if policy.parameter("profile") == "bounded_sram":
            continue
        reads = tuple(
            access
            for access in plan.memory_accesses
            if access.memory == policy.subject
            and access.kind == "read"
            and access.synchronous
            and len(access.address_signals) == 1
            and len(access.data_signals) == 1
        )
        writes = tuple(
            access
            for access in plan.memory_accesses
            if access.memory == policy.subject
            and access.kind == "write"
            and access.synchronous
            and len(access.address_signals) == 1
            and len(access.data_signals) == 1
        )
        if policy.parameter("profile") == "bounded_sram":
            configured_read = policy.parameter("read_data")
            reads = tuple(read for read in reads if configured_read in read.data_signals)
        for pair_index, (read, write) in enumerate(((r, w) for r in reads for w in writes), start=1):
            read_domain = domains.get(read.domain_id or "")
            write_domain = domains.get(write.domain_id or "")
            if (read_domain is not None and read_domain.clock != clock_name) or (
                write_domain is not None and write_domain.clock != clock_name
            ):
                continue
            read_address = _formal_signal_ref(read.address_signals[0], ports)
            write_address = _formal_signal_ref(write.address_signals[0], ports)
            read_data = _formal_signal_ref(read.data_signals[0], ports)
            write_data = _formal_signal_ref(write.data_signals[0], ports)
            read_enable = " && ".join(_formal_signal_ref(signal, ports) for signal in read.enable_signals) or "1'b1"
            write_enable = " && ".join(_formal_signal_ref(signal, ports) for signal in write.enable_signals) or "1'b1"
            reset_guard = (
                f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
                if reset_name and reset_inactive
                else ""
            )
            simultaneous = f"({read_enable}) && ({write_enable}) && ({read_address} == {write_address})"
            if collision == "read_first":
                expected = f"$past(dut.{policy.subject}[{read_address}])"
            elif collision == "write_first":
                expected = f"$past({write_data})"
            else:
                expected = f"$past({read_data})"
            label = f"{policy_index}_{pair_index}"
            lines.extend(
                (
                    f"        if (!$initstate{reset_guard} && $past({simultaneous})) begin",
                    f"            a_memory_collision_{label}: assert({read_data} == {expected});",
                    "        end",
                    f"        c_memory_collision_{label}: cover({simultaneous});",
                )
            )
    return lines


def _bounded_sram_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    """Emit the complete property set for qualified bounded SRAM scenarios."""

    executable = {
        dict(scenario.stimulus[0].parameters).get("memory")
        for scenario in plan.scenarios
        if scenario.kind == "memory_bounded_sram" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    memories = {memory.name: memory for memory in plan.memories}
    lines: list[str] = []
    for index, policy in enumerate(
        (item for item in plan.depth_policies if item.kind == "memory" and item.subject in executable),
        start=1,
    ):
        memory = memories.get(policy.subject)
        if memory is None or memory.depth is None or memory.element_width is None:
            continue
        if policy.parameter("clock") != clock_name:
            continue
        p = dict(policy.parameters)
        req0, req1 = p["port0_request"], p["port1_request"]
        we0, we1 = p["port0_write_enable"], p["port1_write_enable"]
        grant0, grant1 = p["port0_grant"], p["port1_grant"]
        addr0, addr1 = p["port0_address"], p["port1_address"]
        data0, data1 = p["port0_write_data"], p["port1_write_data"]
        be0, be1 = p["port0_byte_enable"], p["port1_byte_enable"]
        read_enable = p["read_enable"]
        protection = p.get("protection", "parity")
        guard = (
            f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
            if reset_name and reset_inactive
            else ""
        )
        lines.extend(
            (
                f"        a_memory_{index}_exclusive_grant: assert(!({grant0} && {grant1}));",
                f"        a_memory_{index}_grant0_request: assert(!{grant0} || ({req0} && {we0}));",
                f"        a_memory_{index}_grant1_request: assert(!{grant1} || ({req1} && {we1}));",
                f"        a_memory_{index}_work_conserving: assert(!({req0} && {we0}) || !({req1} && {we1}) || ({grant0} ^ {grant1}));",
                f"        if (!$initstate{guard} && ({req0} && {we0} && {req1} && {we1}) && $past({req0} && {we0} && {req1} && {we1} && {grant0})) begin",
                f"            a_memory_{index}_round_robin_1: assert({grant1});",
                "        end",
                f"        if (!$initstate{guard} && ({req0} && {we0} && {req1} && {we1}) && $past({req0} && {we0} && {req1} && {we1} && {grant1})) begin",
                f"            a_memory_{index}_round_robin_0: assert({grant0});",
                "        end",
                f"        c_memory_{index}_port0_grant: cover({grant0});",
                f"        c_memory_{index}_port1_grant: cover({grant1});",
                f"        c_memory_{index}_contention: cover({req0} && {we0} && {req1} && {we1});",
            )
        )
        read_address = p["read_address"]
        read_data = p["read_data"]
        byte_lanes = memory.element_width // 8
        mask0 = "{" + ", ".join(f"{{8{{{be0}[{lane}]}}}}" for lane in reversed(range(byte_lanes))) + "}"
        mask1 = "{" + ", ".join(f"{{8{{{be1}[{lane}]}}}}" for lane in reversed(range(byte_lanes))) + "}"
        model = f"dv_memory_{index}_model"
        expected = f"dv_memory_{index}_expected"
        valid = f"dv_memory_{index}_expected_valid"
        if reset_name and reset_active:
            lines.append(f"        if ({reset_name} == {reset_active}) begin")
            lines.append(f"            {model} <= '0;")
            lines.extend((f"            {expected} <= '0;", f"            {valid} <= 1'b0;", "        end else begin"))
        else:
            lines.append("        begin")
        lines.extend(
            (
                f"            if ({valid}) a_memory_{index}_scoreboard: assert({read_data} == {expected});",
                f"            {valid} <= {read_enable} && ({read_address} == '0);",
                f"            if ({read_enable}) begin",
            )
        )
        collision0 = f"{grant0} && ({read_address} == {addr0})"
        collision1 = f"{grant1} && ({read_address} == {addr1})"
        model_read = model
        if p["read_during_write"] == "write_first":
            lines.extend(
                (
                    f"                if ({collision1}) {expected} <= ({model_read} & ~({mask1})) | ({data1} & {mask1});",
                    f"                else if ({collision0}) {expected} <= ({model_read} & ~({mask0})) | ({data0} & {mask0});",
                    f"                else {expected} <= {model_read};",
                )
            )
        elif p["read_during_write"] == "no_change":
            lines.extend(
                (
                    f"                if ({collision0} || {collision1}) {expected} <= {read_data};",
                    f"                else {expected} <= {model_read};",
                )
            )
        else:
            lines.append(f"                {expected} <= {model_read};")
        lines.extend(
            (
                "            end",
                f"            if ({grant0} && ({addr0} == '0)) {model} <= ({model} & ~({mask0})) | ({data0} & {mask0});",
                f"            if ({grant1} && ({addr1} == '0)) {model} <= ({model} & ~({mask1})) | ({data1} & {mask1});",
                "        end",
                f"        c_memory_{index}_port0_collision: cover({read_enable} && {collision0});",
                f"        c_memory_{index}_port1_collision: cover({read_enable} && {collision1});",
            )
        )
        if protection == "parity":
            inject_error, error_signal = p["inject_error"], p["error_signal"]
            lines.extend(
                (
                    f"        if (!$initstate{guard} && $past({read_enable} && {inject_error})) begin",
                    f"            a_memory_{index}_parity_detect: assert({error_signal});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && !{inject_error})) begin",
                    f"            a_memory_{index}_parity_clean: assert(!{error_signal});",
                    "        end",
                    f"        c_memory_{index}_parity_error: cover({read_enable} && {inject_error});",
                )
            )
        else:
            single = p["inject_single_error"]
            double = p["inject_double_error"]
            corrected = p["corrected_error_signal"]
            uncorrectable = p["uncorrectable_error_signal"]
            scrub_enable = p["scrub_enable"]
            scrub_done = p["scrub_done"]
            lines.extend(
                (
                    f"        a_memory_{index}_injection_exclusive: assume(!({single} && {double}));",
                    f"        if (!$initstate{guard} && $past({read_enable} && {single})) begin",
                    f"            a_memory_{index}_secded_correct: assert({corrected} && !{uncorrectable});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && {double})) begin",
                    f"            a_memory_{index}_secded_double_detect: assert({uncorrectable});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && {single} && {scrub_enable})) begin",
                    f"            a_memory_{index}_secded_scrub: assert({scrub_done});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && !{single} && !{double})) begin",
                    f"            a_memory_{index}_secded_clean: assert(!{corrected} && !{uncorrectable});",
                    "        end",
                    f"        c_memory_{index}_secded_single: cover({read_enable} && {single});",
                    f"        c_memory_{index}_secded_double: cover({read_enable} && {double});",
                    f"        c_memory_{index}_secded_scrub: cover({read_enable} && {single} && {scrub_enable});",
                )
            )
    return lines


def _qualified_formal_contract_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    subjects = {
        dict(scenario.stimulus[0].parameters).get("contract")
        for scenario in plan.scenarios
        if scenario.kind == "formal_bounded_response" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    return tuple(policy for policy in plan.depth_policies if policy.kind == "formal" and policy.subject in subjects)


def _formal_contract_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    return tuple(
        dict.fromkeys(
            signal
            for policy in _qualified_formal_contract_policies(plan)
            for name in ("response_signal", "invariant_signal")
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _formal_contract_declarations(plan: VerificationPlan) -> list[str]:
    lines: list[str] = []
    for index, _policy in enumerate(_qualified_formal_contract_policies(plan), start=1):
        lines.extend(
            (
                f"    reg dv_formal_contract_{index}_pending = 1'b0;",
                f"    reg [7:0] dv_formal_contract_{index}_age = '0;",
            )
        )
    return lines


def _formal_contract_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    lines: list[str] = []
    for index, policy in enumerate(_qualified_formal_contract_policies(plan), start=1):
        if policy.parameter("clock") != clock_name:
            continue
        trigger = policy.parameter("trigger_signal") or ""
        response = policy.parameter("response_signal") or ""
        invariant = policy.parameter("invariant_signal") or ""
        bound = int(policy.parameter("max_latency_cycles") or "4")
        pending = f"dv_formal_contract_{index}_pending"
        age = f"dv_formal_contract_{index}_age"
        active_test = f"{reset_name} == {reset_active}" if reset_name and reset_active else "1'b0"
        inactive_guard = f" && {reset_name} == {reset_inactive}" if reset_name and reset_inactive else ""
        lines.extend(
            (
                f"        if (!$initstate{inactive_guard}) a_formal_contract_{index}_trigger_pulse: assume(!({trigger} && $past({trigger})));",
                f"        if ({active_test}) begin",
                f"            {pending} <= 1'b0;",
                f"            {age} <= '0;",
                "        end else begin",
                f"            a_formal_contract_{index}_invariant: assert({invariant});",
                f"            a_formal_contract_{index}_induction_state: assert(!{pending} || ({age} < {bound}));",
                f"            a_formal_contract_{index}_causality: assert(!{response} || {pending} || {trigger});",
                f"            if ({pending} && ({age} >= {bound - 1}))",
                f"                a_formal_contract_{index}_bounded_liveness: assert({response});",
                f"            if ({trigger}) begin",
                f"                {pending} <= 1'b1;",
                f"                {age} <= '0;",
                f"            end else if ({pending} && {response}) begin",
                f"                {pending} <= 1'b0;",
                f"                {age} <= '0;",
                f"            end else if ({pending}) begin",
                f"                {age} <= {age} + 1'b1;",
                "            end",
                f"            c_formal_contract_{index}_assumption_witness: cover({trigger} && !$past({trigger}));",
                f"            c_formal_contract_{index}_response: cover({response});",
                f"            c_formal_contract_{index}_completed: cover({pending} && {response});",
                "        end",
            )
        )
    return lines


def _async_fifo_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    return tuple(
        policy
        for policy in plan.depth_policies
        if policy.kind == "cdc" and policy.parameter("structure") == "async_fifo"
    )


def _qualified_reset_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    executable_subjects = {
        dict(scenario.stimulus[0].parameters).get("reset")
        for scenario in plan.scenarios
        if scenario.kind == "reset_domain_sequence" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    return tuple(
        policy for policy in plan.depth_policies if policy.kind == "reset" and policy.subject in executable_subjects
    )


def _reset_domain_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    return tuple(
        dict.fromkeys(
            signal
            for policy in _qualified_reset_policies(plan)
            for name in (
                "ready_signal",
                "depends_on_ready",
                "dependency_sync_signal",
                "isolation_signal",
                "retention_signal",
            )
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _reset_domain_assertions(plan: VerificationPlan) -> list[str]:
    lines: list[str] = []
    ports = set(_port_names_from_plan(plan))
    for index, policy in enumerate(_qualified_reset_policies(plan), start=1):
        reset = policy.subject
        clock = policy.parameter("clock")
        ready = policy.parameter("ready_signal")
        if reset not in ports or clock not in ports or ready not in ports:
            continue
        active_low = reset.endswith("_n")
        reset_active = f"!{reset}" if active_low else reset
        release_cycles = max(
            int(policy.parameter("release_cycles") or "2"),
            int(policy.parameter("recovery_cycles") or "1"),
            int(policy.parameter("removal_cycles") or "1"),
        )
        dependency_sync = policy.parameter("dependency_sync_signal")
        dependency_guard = dependency_sync if dependency_sync in ports else "1'b1"
        power_good = policy.parameter("power_good_signal")
        isolation = policy.parameter("isolation_signal")
        retention = policy.parameter("retention_signal")
        power_guard = power_good if power_good in ports else "1'b1"
        sequence_guard = f"({dependency_guard}) && ({power_guard})"
        ordered_hold_guard = (
            f"!({dependency_guard}) || (!$initstate && $past(!{power_good}))"
            if power_good in ports
            else f"!({dependency_guard})"
        )
        lines.extend(
            (
                "",
                f"    reg [7:0] reset_domain_{index}_release_count = '0;",
                "    always @(*) begin",
                f"        if ({reset_active}) a_reset_domain_{index}_async_assert: assert(!{ready});",
                *(
                    (
                        f"        if ({ready} && {power_good}) a_reset_domain_{index}_power_release: assert(!{isolation} && !{retention});",
                    )
                    if power_good in ports and isolation in ports and retention in ports
                    else ()
                ),
                "    end",
                f"    always @(posedge {clock}) begin",
                *(
                    (
                        f"        if (!$initstate && $past(!{power_good})) a_reset_domain_{index}_power_hold: assert(!{ready} && {isolation} && {retention});",
                    )
                    if power_good in ports and isolation in ports and retention in ports
                    else ()
                ),
                f"        if (!$initstate && $past(!({reset_active}))) a_reset_domain_{index}_monotonic_release: assume(!({reset_active}));",
                f"        if ({reset_active}) begin",
                f"            reset_domain_{index}_release_count <= '0;",
                "        end else if (!$initstate) begin",
                f"            if (!({sequence_guard})) begin",
                f"                reset_domain_{index}_release_count <= '0;",
                f"                if ({ordered_hold_guard}) a_reset_domain_{index}_ordered_hold: assert(!{ready});",
                "            end else begin",
                f"                if (reset_domain_{index}_release_count < {release_cycles + 1})",
                f"                    reset_domain_{index}_release_count <= reset_domain_{index}_release_count + 1'b1;",
                f"                if (reset_domain_{index}_release_count < {release_cycles})",
                f"                    a_reset_domain_{index}_release_hold: assert(!{ready});",
                f"                else if (reset_domain_{index}_release_count >= {release_cycles + 1})",
                f"                    a_reset_domain_{index}_bounded_release: assert({ready});",
                "            end",
                f"            c_reset_domain_{index}_dependency_seen: cover({sequence_guard});",
                f"            c_reset_domain_{index}_released: cover({ready});",
                "        end",
                "    end",
            )
        )
    return lines


def _qualified_bounded_sram_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    subjects = {
        dict(scenario.stimulus[0].parameters).get("memory")
        for scenario in plan.scenarios
        if scenario.kind == "memory_bounded_sram" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    return tuple(policy for policy in plan.depth_policies if policy.kind == "memory" and policy.subject in subjects)


def _bounded_sram_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    names = (
        "read_data",
        "port0_grant",
        "port1_grant",
        "error_signal",
        "corrected_error_signal",
        "uncorrectable_error_signal",
        "scrub_done",
    )
    return tuple(
        dict.fromkeys(
            signal
            for policy in _qualified_bounded_sram_policies(plan)
            for name in names
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _bounded_sram_declarations(plan: VerificationPlan) -> list[str]:
    memories = {memory.name: memory for memory in plan.memories}
    lines: list[str] = []
    for index, policy in enumerate(_qualified_bounded_sram_policies(plan), start=1):
        memory = memories.get(policy.subject)
        if memory is None or memory.depth is None or memory.element_width is None:
            continue
        lines.extend(
            (
                f"    reg [{memory.element_width - 1}:0] dv_memory_{index}_model = '0;",
                f"    reg [{memory.element_width - 1}:0] dv_memory_{index}_expected = '0;",
                f"    reg dv_memory_{index}_expected_valid = 1'b0;",
            )
        )
    return lines


def _async_fifo_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    names = (
        "write_binary_pointer",
        "write_gray_pointer",
        "write_gray_sync",
        "full_signal",
        "read_data",
        "read_binary_pointer",
        "read_gray_pointer",
        "read_gray_sync",
        "empty_signal",
    )
    return tuple(
        dict.fromkeys(
            signal
            for policy in _async_fifo_policies(plan)
            for name in names
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _async_fifo_assertions(plan: VerificationPlan) -> list[str]:
    lines: list[str] = []
    memories = {memory.name: memory for memory in plan.memories}
    ports = set(_port_names_from_plan(plan))
    for index, policy in enumerate(_async_fifo_policies(plan), start=1):
        memory = memories.get(policy.subject)
        if memory is None or memory.address_width is None or memory.element_width is None:
            continue
        required = {
            name: policy.parameter(name)
            for name in (
                "write_clock",
                "write_reset",
                "write_enable",
                "write_binary_pointer",
                "write_gray_pointer",
                "write_gray_sync",
                "full_signal",
                "read_clock",
                "read_reset",
                "read_enable",
                "read_data",
                "read_binary_pointer",
                "read_gray_pointer",
                "read_gray_sync",
                "empty_signal",
            )
        }
        if any(signal not in ports for signal in required.values()):
            continue
        signal = {name: _formal_signal_ref(value or "", ports) for name, value in required.items()}
        pointer_width = memory.address_width + 1
        w_reset_active = (
            f"!{signal['write_reset']}"
            if (policy.parameter("write_reset") or "").endswith("_n")
            else signal["write_reset"]
        )
        r_reset_active = (
            f"!{signal['read_reset']}"
            if (policy.parameter("read_reset") or "").endswith("_n")
            else signal["read_reset"]
        )
        w_reset_edge = (
            f"negedge {signal['write_reset']}"
            if (policy.parameter("write_reset") or "").endswith("_n")
            else f"posedge {signal['write_reset']}"
        )
        r_reset_edge = (
            f"negedge {signal['read_reset']}"
            if (policy.parameter("read_reset") or "").endswith("_n")
            else f"posedge {signal['read_reset']}"
        )
        inverted_read = (
            f"{{~{signal['read_gray_sync']}[{pointer_width - 1}:{pointer_width - 2}], "
            f"{signal['read_gray_sync']}[{pointer_width - 3}:0]}}"
            if pointer_width > 2
            else f"~{signal['read_gray_sync']}"
        )
        lines.extend(
            (
                "",
                f"    reg async_fifo_{index}_write_valid = 1'b0;",
                f"    reg async_fifo_{index}_write_accept = 1'b0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_write_pointer = '0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_write_gray = '0;",
                f"    reg async_fifo_{index}_read_valid = 1'b0;",
                f"    reg async_fifo_{index}_read_accept = 1'b0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_read_pointer = '0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_read_gray = '0;",
                *(
                    (
                        f"    reg async_fifo_{index}_read_empty = 1'b1;",
                        f"    reg async_fifo_{index}_read_enable = 1'b0;",
                        f"    reg [{memory.element_width - 1}:0] async_fifo_{index}_read_data = '0;",
                        f"    reg [{pointer_width - 1}:0] async_fifo_{index}_read_write_pointer = '0;",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                "",
                f"    always @(posedge {signal['write_clock']} or {w_reset_edge}) begin",
                f"        if ({w_reset_active}) begin",
                f"            a_async_fifo_{index}_write_reset: assert({signal['write_binary_pointer']} == '0 && {signal['write_gray_pointer']} == '0 && !{signal['full_signal']});",
                f"            async_fifo_{index}_write_valid <= 1'b0;",
                "        end else if (!$initstate) begin",
                f"            a_async_fifo_{index}_write_gray_encoding: assert({signal['write_gray_pointer']} == (({signal['write_binary_pointer']} >> 1) ^ {signal['write_binary_pointer']}));",
                f"            a_async_fifo_{index}_full_equation: assert({signal['full_signal']} == ({signal['write_gray_pointer']} == {inverted_read}));",
                f"            if (async_fifo_{index}_write_valid && async_fifo_{index}_write_accept) begin",
                f"                a_async_fifo_{index}_write_increment: assert({signal['write_binary_pointer']} == async_fifo_{index}_write_pointer + 1'b1);",
                f"                a_async_fifo_{index}_write_gray_one_bit: assert((({signal['write_gray_pointer']} ^ async_fifo_{index}_write_gray) & (({signal['write_gray_pointer']} ^ async_fifo_{index}_write_gray) - 1'b1)) == '0);",
                f"            end else if (async_fifo_{index}_write_valid) begin",
                f"                a_async_fifo_{index}_write_hold: assert({signal['write_binary_pointer']} == async_fifo_{index}_write_pointer);",
                "            end",
                f"            c_async_fifo_{index}_write: cover({signal['write_enable']} && !{signal['full_signal']});",
                f"            c_async_fifo_{index}_full: cover({signal['full_signal']});",
                f"            async_fifo_{index}_write_valid <= 1'b1;",
                f"            async_fifo_{index}_write_accept <= {signal['write_enable']} && !{signal['full_signal']};",
                f"            async_fifo_{index}_write_pointer <= {signal['write_binary_pointer']};",
                f"            async_fifo_{index}_write_gray <= {signal['write_gray_pointer']};",
                "        end",
                "    end",
                "",
                f"    always @(posedge {signal['read_clock']} or {r_reset_edge}) begin",
                f"        if ({r_reset_active}) begin",
                f"            a_async_fifo_{index}_read_reset: assert({signal['read_binary_pointer']} == '0 && {signal['read_gray_pointer']} == '0 && {signal['empty_signal']});",
                f"            async_fifo_{index}_read_valid <= 1'b0;",
                *(
                    (
                        f"            async_fifo_{index}_read_empty <= 1'b1;",
                        f"            async_fifo_{index}_read_enable <= 1'b0;",
                        f"            async_fifo_{index}_read_data <= '0;",
                        f"            async_fifo_{index}_read_write_pointer <= '0;",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                "        end else if (!$initstate) begin",
                f"            a_async_fifo_{index}_read_gray_encoding: assert({signal['read_gray_pointer']} == (({signal['read_binary_pointer']} >> 1) ^ {signal['read_binary_pointer']}));",
                f"            a_async_fifo_{index}_empty_equation: assert({signal['empty_signal']} == ({signal['read_gray_pointer']} == {signal['write_gray_sync']}));",
                *(
                    (
                        f"            if (async_fifo_{index}_read_valid && !async_fifo_{index}_read_empty && !async_fifo_{index}_read_enable && {signal['write_binary_pointer']} == async_fifo_{index}_read_write_pointer) a_async_fifo_{index}_fwft_stable: assert({signal['read_data']} == async_fifo_{index}_read_data);",
                        f"            c_async_fifo_{index}_fwft_visible: cover(!{signal['empty_signal']} && !{signal['read_enable']});",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                f"            if (async_fifo_{index}_read_valid && async_fifo_{index}_read_accept) begin",
                f"                a_async_fifo_{index}_read_increment: assert({signal['read_binary_pointer']} == async_fifo_{index}_read_pointer + 1'b1);",
                f"                a_async_fifo_{index}_read_gray_one_bit: assert((({signal['read_gray_pointer']} ^ async_fifo_{index}_read_gray) & (({signal['read_gray_pointer']} ^ async_fifo_{index}_read_gray) - 1'b1)) == '0);",
                f"            end else if (async_fifo_{index}_read_valid) begin",
                f"                a_async_fifo_{index}_read_hold: assert({signal['read_binary_pointer']} == async_fifo_{index}_read_pointer);",
                "            end",
                f"            c_async_fifo_{index}_read: cover({signal['read_enable']} && !{signal['empty_signal']});",
                f"            c_async_fifo_{index}_empty: cover({signal['empty_signal']});",
                f"            async_fifo_{index}_read_valid <= 1'b1;",
                f"            async_fifo_{index}_read_accept <= {signal['read_enable']} && !{signal['empty_signal']};",
                f"            async_fifo_{index}_read_pointer <= {signal['read_binary_pointer']};",
                f"            async_fifo_{index}_read_gray <= {signal['read_gray_pointer']};",
                *(
                    (
                        f"            async_fifo_{index}_read_empty <= {signal['empty_signal']};",
                        f"            async_fifo_{index}_read_enable <= {signal['read_enable']};",
                        f"            async_fifo_{index}_read_data <= {signal['read_data']};",
                        f"            async_fifo_{index}_read_write_pointer <= {signal['write_binary_pointer']};",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                "        end",
                "    end",
            )
        )
    return lines


def _cdc_assertions(
    plan: VerificationPlan,
    evidence: tuple[_CDCPathEvidence, ...] | None = None,
) -> list[str]:
    lines: list[str] = []
    ports = set(_port_names_from_plan(plan))
    port_widths = {port.name: port.width or 1 for port in plan.ports}
    evidence_by_id = {item.path_id: item for item in (evidence or _cdc_evidence(plan, CDCProofPolicy.FAIL_CLOSED, 20))}
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    for path in plan.cdc_paths:
        path_evidence = evidence_by_id.get(path.path_id)
        if path_evidence is None or path_evidence.evidence_level == "unsupported":
            continue
        domain = domains.get(path.destination_domain)
        if domain is None or not domain.clock:
            continue
        clock = _formal_signal_ref(domain.clock, ports)
        label = _safe_identifier(path.path_id)
        source = _formal_signal_ref(path.signal, ports)
        edge = "negedge" if domain.clock_edge == "neg" else "posedge"
        reset = _formal_signal_ref(domain.reset, ports) if domain.reset else None
        reset_active = f"!{reset}" if reset and domain.reset_active_low else reset
        reset_inactive = reset if reset and domain.reset_active_low else f"!{reset}" if reset else None
        reset_edge = "negedge" if domain.reset_active_low else "posedge"
        event = f"{edge} {clock}" + (f" or {reset_edge} {reset}" if reset else "")
        initialization = "" if reset else " = '0"
        if path_evidence.evidence_level == "structural":
            stage_count = path.synchronizer_stages
            expected_name = f"cdc_{label}_expected"
            valid_name = f"cdc_{label}_valid"
            signal_width = port_widths.get(path.signal, 1)
            if signal_width == 1:
                lines.append(f"    reg [{stage_count - 1}:0] {expected_name}{initialization};")
            else:
                lines.extend(
                    f"    reg [{signal_width - 1}:0] {expected_name}_{index}{initialization};"
                    for index in range(stage_count)
                )
            lines.append(f"    reg [{stage_count - 1}:0] {valid_name}{initialization};")
            lines.append(f"    always @({event}) begin")
            if reset_active:
                lines.append(f"        if ({reset_active}) begin")
                if signal_width == 1:
                    lines.append(f"            {expected_name} <= '0;")
                else:
                    lines.extend(f"            {expected_name}_{index} <= '0;" for index in range(stage_count))
                lines.append(f"            {valid_name} <= '0;")
                lines.append("        end else begin")
            else:
                lines.append("        begin")
            for index in range(stage_count):
                previous = source if index == 0 else _formal_signal_ref(path.stage_signals[index - 1], ports)
                expected = f"{expected_name}[{index}]" if signal_width == 1 else f"{expected_name}_{index}"
                lines.append(f"            {expected} <= {previous};")
                validity = "1'b1" if index == 0 else f"{valid_name}[{index - 1}]"
                lines.append(f"            {valid_name}[{index}] <= {validity};")
            lines.append("        end")
            lines.append("    end")
            lines.append("    always @(*) begin")
            for index, stage in enumerate(path.stage_signals):
                current = _formal_signal_ref(stage, ports)
                guard = f"{valid_name}[{index}]"
                if reset_inactive:
                    guard += f" && {reset_inactive}"
                expected = f"{expected_name}[{index}]" if signal_width == 1 else f"{expected_name}_{index}"
                lines.append(f"        if ({guard}) a_cdc_{label}_stage_{index}: assert({current} == {expected});")
            final_stage = _formal_signal_ref(path.stage_signals[-1], ports)
            final_expected = (
                f"{expected_name}[{stage_count - 1}]" if signal_width == 1 else f"{expected_name}_{stage_count - 1}"
            )
            lines.append(
                f"        c_cdc_{label}_observed: cover({valid_name}[{stage_count - 1}] "
                f"&& {final_stage} == {final_expected});"
            )
            lines.append("    end")
            lines.extend(_cdc_scheme_assertions(plan, path, clock, edge, reset_inactive, ports))
            continue

        maximum_latency = path.synchronizer_stages
        history_name = f"cdc_{label}_history"
        valid_name = f"cdc_{label}_valid"
        lines.append("`ifdef DV_CDC_BOUNDED")
        lines.append(f"    reg [{maximum_latency - 1}:0] {history_name}{initialization};")
        lines.append(f"    reg [{maximum_latency - 1}:0] {valid_name}{initialization};")
        lines.append(f"    always @({event}) begin")
        if reset_active:
            lines.append(f"        if ({reset_active}) begin")
            lines.append(f"            {history_name} <= '0;")
            lines.append(f"            {valid_name} <= '0;")
            lines.append("        end else begin")
        else:
            lines.append("        begin")
        lines.append(f"            {history_name}[0] <= {source};")
        lines.append(f"            {valid_name}[0] <= 1'b1;")
        for index in range(1, maximum_latency):
            lines.append(f"            {history_name}[{index}] <= {history_name}[{index - 1}];")
            lines.append(f"            {valid_name}[{index}] <= {valid_name}[{index - 1}];")
        final_index = maximum_latency - 1
        final_stage = _formal_signal_ref(path.stage_signals[-1], ports)
        lines.append("        end")
        lines.append("    end")
        lines.append("    always @(*) begin")
        bounded_guard = f"{valid_name}[{final_index}]"
        if reset_inactive:
            bounded_guard += f" && {reset_inactive}"
        lines.append(
            f"        if ({bounded_guard}) "
            f"a_cdc_{label}_bounded: assert({final_stage} == {history_name}[{final_index}]);"
        )
        lines.append(
            f"        c_cdc_{label}_observed: cover({valid_name}[{final_index}] "
            f"&& {final_stage} == {history_name}[{final_index}]);"
        )
        lines.append("    end")
        lines.append("`endif")
        lines.extend(_cdc_scheme_assertions(plan, path, clock, edge, reset_inactive, ports))
    return lines


def _cdc_scheme_assertions(
    plan: VerificationPlan,
    path: RTLCDCPath,
    clock: str,
    edge: str,
    reset_inactive: str | None,
    ports: set[str],
) -> list[str]:
    policy = next(
        (
            item
            for item in plan.depth_policies
            if item.kind == "cdc"
            and item.subject == path.signal
            and item.parameter("structure") in {"pulse", "toggle", "gray", "handshake", "multi_bit_handshake"}
        ),
        None,
    )
    if policy is None:
        return []
    structure = policy.parameter("structure") or path.classification
    label = _safe_identifier(path.path_id)
    source = _formal_signal_ref(path.signal, ports)
    output = _formal_signal_ref(path.stage_signals[-1], ports)
    if structure == "gray":
        width = next((port.width for port in plan.ports if port.name == path.signal), None)
        if width is None or width < 2:
            return []
        source_sample = f"cdc_{label}_gray_source_sample"
        output_sample = f"cdc_{label}_gray_output_sample"
        reset_active = f"!({reset_inactive})" if reset_inactive else None
        lines = [
            f"    reg [{width - 1}:0] {source_sample} = '0;",
            f"    reg [{width - 1}:0] {output_sample} = '0;",
            f"    always @({edge} {clock}) begin",
        ]
        if reset_active:
            lines.extend(
                (
                    f"        if ({reset_active}) begin",
                    f"            a_cdc_{label}_gray_reset_source: assume({source} == '0);",
                    f"            {source_sample} <= '0;",
                    f"            {output_sample} <= '0;",
                    "        end else begin",
                )
            )
        else:
            lines.append("        begin")
        lines.extend(
            (
                f"            a_cdc_{label}_gray_source_one_bit: assume((({source} ^ {source_sample}) & (({source} ^ {source_sample}) - 1'b1)) == '0);",
                f"            a_cdc_{label}_gray_one_bit: assert((({output} ^ {output_sample}) & (({output} ^ {output_sample}) - 1'b1)) == '0);",
                f"            c_cdc_{label}_gray_changed: cover({output} != {output_sample});",
                f"            {source_sample} <= {source};",
                f"            {output_sample} <= {output};",
                "        end",
                "    end",
            )
        )
        return lines
    if structure == "multi_bit_handshake":
        ack_input = _formal_signal_ref(policy.parameter("ack_input_signal") or "", ports)
        ack_output = _formal_signal_ref(policy.parameter("ack_output_signal") or "", ports)
        data_signals = tuple(filter(None, (policy.parameter("data_signals") or "").split(",")))
        observed_signals = tuple(filter(None, (policy.parameter("observed_data_signals") or "").split(",")))
        valid = f"cdc_{label}_payload_valid"
        reset_active = f"!({reset_inactive})" if reset_inactive else None
        lines = [f"    reg {valid} = 1'b0;"]
        expected_names: list[str] = []
        for index, signal in enumerate(data_signals):
            width = next((port.width for port in plan.ports if port.name == signal), None)
            if width is None:
                return []
            expected = f"cdc_{label}_payload_expected_{index}"
            expected_names.append(expected)
            lines.append(f"    reg [{width - 1}:0] {expected} = '0;")
        lines.append(f"    always @({edge} {clock}) begin")
        if reset_active:
            lines.extend(
                (f"        if ({reset_active}) begin", f"            {valid} <= 1'b0;", "        end else begin")
            )
        else:
            lines.append("        begin")
        lines.extend(
            (
                f"            if (!$initstate && $past({source}) && !$past({ack_output})) "
                f"a_cdc_{label}_request_held: assume({source});",
            )
        )
        for index, signal in enumerate(data_signals):
            reference = _formal_signal_ref(signal, ports)
            lines.append(
                f"            if (!$initstate && $past({source}) && !$past({ack_output})) "
                f"a_cdc_{label}_data_stable_{index}: assume({reference} == $past({reference}));"
            )
            observed = _formal_signal_ref(observed_signals[index], ports)
            lines.append(
                f"            if ({valid}) a_cdc_{label}_payload_coherent_{index}: "
                f"assert({observed} == {expected_names[index]});"
            )
            lines.append(f"            if ({output}) {expected_names[index]} <= {reference};")
        lines.extend(
            (
                f"            {valid} <= {output};",
                f"            c_cdc_{label}_request_seen: cover({output});",
                f"            c_cdc_{label}_round_trip: cover({output} && {ack_input} && {ack_output});",
                "        end",
                "    end",
            )
        )
        return lines
    guard = f" && {reset_inactive}" if reset_inactive else ""
    lines = [f"    always @({edge} {clock}) begin", f"        if (!$initstate{guard}) begin"]
    if structure == "toggle":
        lines.extend(
            (
                f"            c_cdc_{label}_toggle_rise: cover(!$past({output}) && {output});",
                f"            c_cdc_{label}_toggle_fall: cover($past({output}) && !{output});",
            )
        )
    elif structure == "pulse":
        lines.extend(
            (
                f"            c_cdc_{label}_pulse_observed: cover({output} && !$past({output}));",
                f"            c_cdc_{label}_pulse_returned: cover(!{output} && $past({output}));",
            )
        )
    else:
        ack_input = _formal_signal_ref(policy.parameter("ack_input_signal") or "", ports)
        ack_output = _formal_signal_ref(policy.parameter("ack_output_signal") or "", ports)
        data_signals = tuple(filter(None, (policy.parameter("data_signals") or "").split(",")))
        lines.append(
            f"            if ($past({source}) && !$past({ack_output})) a_cdc_{label}_request_held: assume({source});"
        )
        for index, signal in enumerate(data_signals):
            reference = _formal_signal_ref(signal, ports)
            lines.append(
                f"            if ($past({source}) && !$past({ack_output})) "
                f"a_cdc_{label}_data_stable_{index}: assume({reference} == $past({reference}));"
            )
        lines.extend(
            (
                f"            c_cdc_{label}_request_seen: cover({output});",
                f"            c_cdc_{label}_round_trip: cover({output} && {ack_input} && {ack_output});",
            )
        )
    lines.extend(("        end", "    end"))
    return lines


def _cdc_evidence(
    plan: VerificationPlan,
    policy: CDCProofPolicy,
    bmc_depth: int,
) -> tuple[_CDCPathEvidence, ...]:
    ports = set(_port_names_from_plan(plan))
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    evidence: list[_CDCPathEvidence] = []
    for path in plan.cdc_paths:
        observed = tuple(stage for stage in path.stage_signals if stage in ports)
        hidden = tuple(stage for stage in path.stage_signals if stage not in ports)
        domain = domains.get(path.destination_domain)
        reason: str | None = None
        if not path.safe:
            reason = "RTL analysis did not classify the crossing as safe"
        elif path.classification not in {
            "two_flop",
            "pulse",
            "toggle",
            "gray",
            "handshake",
            "multi_bit_handshake",
        }:
            reason = f"unsupported CDC classification {path.classification!r}"
        elif path.synchronizer_stages < 2 or len(path.stage_signals) != path.synchronizer_stages:
            reason = "synchronizer stage metadata is incomplete or inconsistent"
        elif path.reset_compatible is False:
            reason = "source and destination reset strategies are incompatible"
        elif domain is None or not domain.clock:
            reason = "destination control domain has no classified clock"
        elif domain.clock not in ports:
            reason = "destination clock is not an observable input port"
        elif path.signal not in ports:
            reason = "CDC source signal is not an observable port"

        level = "unsupported"
        task: str | None = None
        closure_eligible = False
        bound_steps: int | None = None
        if reason is None and not hidden:
            level = "structural"
            task = "prove"
            closure_eligible = True
        elif reason is None and policy == CDCProofPolicy.BOUNDED:
            if not path.stage_signals or path.stage_signals[-1] not in ports:
                reason = "final synchronizer stage is not an observable output port"
            elif bmc_depth < path.synchronizer_stages + 1:
                reason = f"CDC BMC depth {bmc_depth} is below the minimum {path.synchronizer_stages + 1} steps"
            else:
                level = "bounded"
                task = "cdc_bmc"
                bound_steps = bmc_depth
                reason = "internal synchronizer stages are hidden; only external latency is checked"
        elif reason is None:
            reason = "internal synchronizer stages are hidden; select bounded policy or expose formal stage ports"

        evidence.append(
            _CDCPathEvidence(
                path_id=path.path_id,
                signal=path.signal,
                evidence_level=level,
                closure_eligible=closure_eligible,
                task=task,
                clock=domain.clock if domain is not None else None,
                observed_stages=observed,
                hidden_stages=hidden,
                latency_cycles=path.synchronizer_stages,
                bound_steps=bound_steps,
                reason=reason,
            )
        )
    return tuple(evidence)


def _cdc_report_content(
    plan: VerificationPlan,
    policy: CDCProofPolicy,
    bmc_depth: int,
    evidence: tuple[_CDCPathEvidence, ...],
) -> str:
    payload = {
        "schema_version": 1,
        "module": plan.module,
        "policy": str(policy),
        "bounded_depth": bmc_depth,
        "paths": [
            {
                "path_id": item.path_id,
                "signal": item.signal,
                "evidence_level": item.evidence_level,
                "closure_eligible": item.closure_eligible,
                "formal_task": item.task,
                "clock": item.clock,
                "observed_stages": list(item.observed_stages),
                "hidden_stages": list(item.hidden_stages),
                "latency_cycles": item.latency_cycles,
                "bound_steps": item.bound_steps,
                "reason": item.reason,
            }
            for item in evidence
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _formal_signal_ref(signal: str, ports: set[str]) -> str:
    safe = _safe_identifier(signal)
    return safe if signal in ports else f"dut.{safe}"


def _output_wire_declaration(plan: VerificationPlan, port: str) -> str:
    planned_port = _structured_ports(plan).get(port)
    if planned_port is not None:
        signed = " signed" if planned_port.signed else ""
        if planned_port.width is not None and planned_port.width > 1:
            return "wire" + signed + " [" + str(planned_port.width - 1) + ":0] " + port
        if planned_port.packed_range and _safe_packed_range(planned_port.packed_range):
            return "wire" + signed + " " + planned_port.packed_range + " " + port
        return "wire" + signed + " " + port
    dtype = _verilator_port_dtype(plan, port)
    if dtype is None:
        return "wire " + port
    left = dtype.attrib.get("left")
    right = dtype.attrib.get("right")
    signed = " signed" if dtype.attrib.get("signed") == "true" else ""
    if left is not None and right is not None and _safe_sv_bound(left) and _safe_sv_bound(right):
        return "wire" + signed + " [" + left + ":" + right + "] " + port
    return "wire" + signed + " " + port


def _verilator_port_dtype(plan: VerificationPlan, port: str) -> Element | None:
    locator = "port:" + plan.module + "." + port
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            if ref.locator.split("@", 1)[0] != locator:
                continue
            source_path = Path(ref.source_id)
            if not source_path.is_file():
                continue
            try:
                root = parse(source_path).getroot()
            except ParseError:
                continue
            if root is None:
                continue
            dtype_id = _verilator_port_dtype_id(root, plan.design_unit or plan.module, port)
            if dtype_id is None:
                continue
            dtype = _verilator_dtype(root, dtype_id)
            if dtype is not None:
                return dtype
    return None


def _verilator_port_dtype_id(root: Element, module: str, port: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) != "module":
            continue
        if (element.attrib.get("origName") or element.attrib.get("name")) != module:
            continue
        for child in element:
            if _local_name(child.tag) != "var":
                continue
            if (child.attrib.get("origName") or child.attrib.get("name")) == port:
                return child.attrib.get("dtype_id")
    return None


def _verilator_dtype(root: Element, dtype_id: str) -> Element | None:
    for element in root.iter():
        if element.attrib.get("id") == dtype_id and _local_name(element.tag).endswith("dtype"):
            return element
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_sv_bound(value: str) -> bool:
    return value.isdecimal()


def _safe_packed_range(value: str) -> bool:
    if not value.startswith("[") or not value.endswith("]") or ":" not in value:
        return False
    left, right = value.strip("[]").split(":", 1)
    return _safe_sv_bound(left.strip()) and _safe_sv_bound(right.strip())


def _is_zero_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.lower().replace("_", "")
    if normalized in {"0", "'0", "1'b0", "1'h0", "1'd0"}:
        return True
    if "'" in normalized:
        return normalized.rsplit("'", 1)[-1].lstrip("s").lstrip("bhd") == "0"
    return False


def _looks_like_scalar_input(port: str) -> bool:
    if port.endswith(("_o", "_out")):
        return False
    return port.endswith(("_i", "_in")) or port in {"enable", "en", "valid", "ready", "start", "clear", "load"}


def _looks_like_output(port: str) -> bool:
    return port.endswith(("_o", "_out"))


def _comma_terminate(lines: list[str]) -> list[str]:
    return [line + ("," if index < len(lines) - 1 else "") for index, line in enumerate(lines)]


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
