# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Formal generator backend."""

from __future__ import annotations

from dv_platform.core.models import (
    ArtifactQualityRequirement,
    RTLPort,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.scenario_registry import scenario_is_executable
from dv_platform.generators.signals import (
    primary_clock_name,
    primary_reset,
    safe_parameter_value,
)

_BOUNDED_SCENARIO_PREFIXES = (
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


def _sby_content(
    plan: VerificationPlan,
    *,
    bounded_cdc: bool = False,
    multiclock: bool = False,
    cdc_bmc_depth: int = 20,
) -> str:
    presentation = _sby_presentation(
        plan,
        bounded_cdc=bounded_cdc,
        multiclock=multiclock,
        cdc_bmc_depth=cdc_bmc_depth,
    )
    presentation["_plan"] = plan
    presentation["header"] = ""
    return render_target("formal", presentation)


def _sby_presentation(
    plan: VerificationPlan,
    *,
    bounded_cdc: bool = False,
    multiclock: bool = False,
    cdc_bmc_depth: int = 20,
) -> dict[str, object]:
    module_name = _safe_identifier(plan.module)
    harness_name = f"formal_{module_name}"
    depth = _proof_depth(plan)
    tasks = ["prove", "cover"]
    executable_scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind.startswith(_BOUNDED_SCENARIO_PREFIXES)
        and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    )
    bounded_protocol = bool(executable_scenarios)
    if executable_scenarios:
        depth = _bounded_scenario_depth(executable_scenarios, depth)
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
    return {
        "artifact_kind": "sby",
        "tasks": tasks,
        "options": options,
        "engines": engines,
        "script": script,
        "harness_name": harness_name,
        "harness_file": f"formal_{module_name}.sv",
    }


def _bounded_scenario_depth(
    executable_scenarios: tuple[VerificationScenario, ...],
    configured_depth: int,
) -> int:
    scenario_depth = max(scenario.completion.timeout_cycles + 2 for scenario in executable_scenarios)
    if all(scenario.kind.startswith("memory_") for scenario in executable_scenarios):
        minimum_depth = 6
    elif all(scenario.kind.startswith("axi4_lite_") for scenario in executable_scenarios):
        minimum_depth = 7
    else:
        minimum_depth = 10
    # Keep the open-source lane within its governed 20-cycle proof horizon.
    # Longer configured timeouts remain exercised dynamically and can be
    # promoted by an imported vendor proof; generated local assertions retain
    # the same bounded horizon instead of becoming vacuous.
    return max(minimum_depth, min(configured_depth, scenario_depth))


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
    formal_assumption_checks = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind == "formal_assumption" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
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
        or formal_contract_checks
        or formal_assumption_checks
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
