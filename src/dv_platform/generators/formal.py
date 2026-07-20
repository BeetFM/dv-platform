"""Formal generator backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from xml.etree import ElementTree

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    GeneratedArtifact,
    RTLPort,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.protocols import sv_protocol_assertions
from dv_platform.generators.signals import (
    artifact_trace,
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
                traceability=artifact_trace(
                    plan,
                    f"formal_{module_name}_properties",
                    categories=("reset", "increment", "hold", "protocol", "memory"),
                ),
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
                traceability=artifact_trace(
                    plan,
                    f"formal_{module_name}_run",
                    categories=("reset", "increment", "hold", "protocol", "memory"),
                ),
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
                    traceability=artifact_trace(
                        plan,
                        f"formal_{module_name}_cdc_evidence",
                        categories=("cdc",),
                        include_nonexecutable=True,
                    ),
                )
            )
        return artifacts


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
    clock_name = alternate_clock or "dv_formal_clock" if cdc_clocks and primary_clock in cdc_clocks else primary_clock
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    reset_active_low = (
        reset.active_low
        if reset is not None and reset.active_low is not None
        else bool(reset_name and reset_name.endswith("_n"))
    )
    scalar_inputs = _input_ports(plan, ports, clock_name, reset_name)
    connected_ports = tuple(
        dict.fromkeys(
            (*(port for port in (clock_name if clock_name in ports else None, reset_name) if port), *scalar_inputs)
        )
    )
    unconnected_outputs = _output_ports(plan, ports)
    reset_zero_outputs = _reset_zero_outputs(plan, unconnected_outputs, reset_name)
    increment_checks = _increment_checks(plan, unconnected_outputs, scalar_inputs)
    hold_checks = _hold_checks(plan, unconnected_outputs, scalar_inputs)
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
                "        " + reset_name + " <= $anyseq;",
                "        c_reset_asserted: cover(" + reset_name + " == " + reset_active + ");",
                "        c_reset_released: cover(!$initstate && " + reset_name + " == " + reset_inactive + ");",
            ]
        )
        for name in scalar_inputs:
            lines.append("        " + name + " <= $anyseq;")
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
        lines.extend(sv_protocol_assertions(plan, clock_name))
        lines.extend(_memory_write_assertions(plan, reset_name, reset_inactive, clock_name))
        lines.extend(_memory_collision_assertions(plan, reset_name, reset_inactive, clock_name))
        cover_terms = [reset_name + " == " + reset_inactive, *scalar_inputs]
    else:
        for name in scalar_inputs:
            lines.append("        " + name + " <= $anyseq;")
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
        lines.extend(sv_protocol_assertions(plan, clock_name))
        lines.extend(_memory_write_assertions(plan, None, None, clock_name))
        lines.extend(_memory_collision_assertions(plan, None, None, clock_name))
        cover_terms = list(scalar_inputs)

    if cover_terms:
        lines.append("        cover(" + " && ".join(cover_terms) + ");")
    else:
        lines.append("        cover(!$initstate);")
    lines.extend(["    end", ""])
    lines.extend(_cdc_assertions(plan, resolved_cdc_evidence))
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
    options = ["prove: mode prove", "cover: mode cover"]
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
    return "\n".join(
        [
            "[tasks]",
            *tasks,
            "",
            "[options]",
            *options,
            "",
            "[engines]",
            "smtbmc z3",
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
    for index, access in enumerate(plan.memory_accesses, start=1):
        if (
            access.kind != "write"
            or not access.synchronous
            or len(access.address_signals) != 1
            or len(access.data_signals) != 1
            or not access.enable_signals
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


def _cdc_assertions(
    plan: VerificationPlan,
    evidence: tuple[_CDCPathEvidence, ...] | None = None,
) -> list[str]:
    lines: list[str] = []
    ports = set(_port_names_from_plan(plan))
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
            lines.append(f"    reg [{stage_count - 1}:0] {expected_name}{initialization};")
            lines.append(f"    reg [{stage_count - 1}:0] {valid_name}{initialization};")
            lines.append(f"    always @({event}) begin")
            if reset_active:
                lines.append(f"        if ({reset_active}) begin")
                lines.append(f"            {expected_name} <= '0;")
                lines.append(f"            {valid_name} <= '0;")
                lines.append("        end else begin")
            else:
                lines.append("        begin")
            for index in range(stage_count):
                previous = source if index == 0 else _formal_signal_ref(path.stage_signals[index - 1], ports)
                lines.append(f"            {expected_name}[{index}] <= {previous};")
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
                lines.append(
                    f"        if ({guard}) a_cdc_{label}_stage_{index}: assert({current} == {expected_name}[{index}]);"
                )
            final_stage = _formal_signal_ref(path.stage_signals[-1], ports)
            lines.append(
                f"        c_cdc_{label}_observed: cover({valid_name}[{stage_count - 1}] "
                f"&& {final_stage} == {expected_name}[{stage_count - 1}]);"
            )
            lines.append("    end")
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
        elif path.classification != "two_flop":
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


def _verilator_port_dtype(plan: VerificationPlan, port: str) -> ElementTree.Element | None:
    locator = "port:" + plan.module + "." + port
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            if ref.locator.split("@", 1)[0] != locator:
                continue
            source_path = Path(ref.source_id)
            if not source_path.is_file():
                continue
            try:
                root = ElementTree.parse(source_path).getroot()
            except ElementTree.ParseError:
                continue
            dtype_id = _verilator_port_dtype_id(root, plan.design_unit or plan.module, port)
            if dtype_id is None:
                continue
            dtype = _verilator_dtype(root, dtype_id)
            if dtype is not None:
                return dtype
    return None


def _verilator_port_dtype_id(root: ElementTree.Element, module: str, port: str) -> str | None:
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


def _verilator_dtype(root: ElementTree.Element, dtype_id: str) -> ElementTree.Element | None:
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
