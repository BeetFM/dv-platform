"""Shared structured signal rendering for generator backends."""

from __future__ import annotations

from dv_platform.agent.mappings import mappings_for
from dv_platform.core.literals import safe_sv_numeric_literal
from dv_platform.core.models import (
    ArtifactQualityRequirement,
    ArtifactTrace,
    EvidenceRef,
    RTLPort,
    RTLReset,
    VerificationPlan,
    VerificationTarget,
)


def port_names(plan: VerificationPlan) -> tuple[str, ...]:
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


def input_ports(plan: VerificationPlan, names: tuple[str, ...]) -> tuple[str, ...]:
    if plan.ports:
        return tuple(port.name for port in plan.ports if port.direction == "input")
    return tuple(name for name in names if not looks_like_output(name))


def output_ports(plan: VerificationPlan, names: tuple[str, ...]) -> tuple[str, ...]:
    if plan.ports:
        return tuple(port.name for port in plan.ports if port.direction == "output")
    return tuple(name for name in names if looks_like_output(name))


def inout_ports(plan: VerificationPlan) -> tuple[str, ...]:
    return tuple(port.name for port in plan.ports if port.direction in {"inout", "ref"})


def primary_clock_name(plan: VerificationPlan, names: tuple[str, ...]) -> str | None:
    if plan.clocks:
        return plan.clocks[0].name
    return next(
        (name for name in names if name in {"clk", "clock"} or name.endswith(("_clk", "_clock"))),
        None,
    )


def primary_reset(plan: VerificationPlan, names: tuple[str, ...]) -> RTLReset | None:
    if plan.resets:
        return plan.resets[0]
    name = next(
        (
            item
            for item in names
            if item in {"rst", "reset", "rst_n", "reset_n"} or item.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
        ),
        None,
    )
    if name is None:
        return None
    return RTLReset(name=name, direction="input", active_low=name.endswith("_n"))


def port_by_name(plan: VerificationPlan, name: str) -> RTLPort | None:
    return next((port for port in plan.ports if port.name == name), None)


def sv_declaration(port: RTLPort, variable: bool) -> str:
    kind = "logic" if variable else "wire"
    signed = " signed" if port.signed else ""
    packed_range = _packed_range(port)
    range_text = f" {packed_range}" if packed_range else ""
    return f"{kind}{signed}{range_text} {port.name};"


def verilog_declaration(port: RTLPort, variable: bool) -> str:
    kind = "reg" if variable else "wire"
    signed = " signed" if port.signed else ""
    packed_range = _packed_range(port)
    range_text = f" {packed_range}" if packed_range else ""
    return f"{kind}{signed}{range_text} {port.name};"


def vhdl_type(port: RTLPort) -> str:
    if port.width is not None and port.width > 1:
        return f"std_logic_vector({port.width - 1} downto 0)"
    return "std_logic"


def sv_parameter_clause(plan: VerificationPlan) -> str:
    """Render the analyzed elaborated parameter configuration for an HDL instance."""

    parameters = tuple(
        parameter
        for parameter in plan.parameters
        if not parameter.local and parameter.default_value is not None and safe_parameter_value(parameter.default_value)
    )
    if not parameters:
        return ""
    connections = ", ".join(f".{parameter.name}({parameter.default_value})" for parameter in parameters)
    return f" #( {connections} )"


def safe_parameter_value(value: str) -> bool:
    """Accept only numeric literals that can be rendered without code injection."""

    return safe_sv_numeric_literal(value)


def structured_quality_requirements(
    plan: VerificationPlan,
    target: str,
) -> tuple[ArtifactQualityRequirement, ...]:
    names = tuple(port.name for port in plan.ports)
    valid_directions = all(port.direction in {"input", "output", "inout", "ref"} for port in plan.ports)
    valid_widths = all(port.width is None or port.width > 0 for port in plan.ports)
    clock_names = {port.name for port in plan.ports if port.direction == "input"}
    classified_names = {clock.name for clock in plan.clocks} | {reset.name for reset in plan.resets}
    return (
        ArtifactQualityRequirement(
            requirement_id="structured_ports",
            description=f"{target} generation requires structured port metadata.",
            satisfied=bool(plan.ports),
            reason=None if plan.ports else "plan has no structured ports",
        ),
        ArtifactQualityRequirement(
            requirement_id="valid_port_shape",
            description=f"{target} generation requires unique ports with supported directions and widths.",
            satisfied=bool(plan.ports) and len(names) == len(set(names)) and valid_directions and valid_widths,
            reason="ports are missing, duplicated, or have invalid directions or widths",
        ),
        ArtifactQualityRequirement(
            requirement_id="classified_controls_are_inputs",
            description="Classified clocks and resets must resolve to structured input ports.",
            satisfied=classified_names.issubset(clock_names),
            reason="a classified clock or reset is not a structured input port",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_parameter_values",
            description=f"{target} generation requires safely renderable numeric elaborated parameters.",
            satisfied=all(
                parameter.local or parameter.default_value is None or safe_parameter_value(parameter.default_value)
                for parameter in plan.parameters
            ),
            reason="an elaborated parameter is not a supported numeric literal",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_semantic_features",
            description="Executable generation must not guess behavior for unsupported RTL semantic constructs.",
            satisfied=all(
                feature.supports_target(VerificationTarget(target.lower())) for feature in plan.semantic_features
            ),
            reason="the plan contains unsupported memory, array, case, interface, enum, struct, or union semantics",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_protocol_models",
            description="Executable protocol generation requires supported semantics and evidence.",
            satisfied=all(
                protocol.evidence_refs and not protocol.unsupported_semantics for protocol in plan.protocol_models
            ),
            reason="a protocol model is unsupported or lacks evidence",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_register_models",
            description="Executable register accesses require known offsets, valid fields, and evidence.",
            satisfied=all(
                register.offset is not None
                and register.width > 0
                and all(0 <= field.lsb <= field.msb < register.width for field in register.fields)
                and bool(register.evidence_refs)
                for register in plan.register_models
            ),
            reason="a register model has an unknown offset, invalid field, or missing evidence",
        ),
        ArtifactQualityRequirement(
            requirement_id="no_register_conflicts",
            description="Executable register generation requires resolved source conflicts.",
            satisfied=not plan.register_conflicts,
            reason="register sources disagree on one or more properties",
        ),
    )


def semantic_features_supported(plan: VerificationPlan, target: str) -> bool:
    """Return whether every extracted construct is safe for a generation target."""

    resolved = VerificationTarget(target.lower())
    return all(feature.supports_target(resolved) for feature in plan.semantic_features)


def provenance_refs(plan: VerificationPlan) -> tuple[EvidenceRef, ...]:
    return tuple(
        dict.fromkeys(
            (
                *(ref for check in plan.check_details for ref in check.evidence_refs),
                *(ref for requirement in plan.structured_requirements for ref in requirement.evidence_refs),
                *(ref for behavior in plan.behaviors for ref in behavior.evidence_refs),
                *(ref for claim in plan.claims for ref in claim.evidence_refs),
                *(ref for protocol in plan.protocols for ref in protocol.evidence_refs),
                *(ref for protocol in plan.protocol_models for ref in protocol.evidence_refs),
                *(ref for register in plan.register_models for ref in register.evidence_refs),
                *(ref for access in plan.memory_accesses for ref in access.evidence_refs),
                *(ref for path in plan.cdc_paths for ref in path.evidence_refs),
            )
        )
    )


def artifact_trace(
    plan: VerificationPlan,
    generated_symbol: str,
    *,
    categories: tuple[str, ...] | None = None,
    include_nonexecutable: bool = False,
) -> tuple[ArtifactTrace, ...]:
    """Build a deterministic executable-to-plan trace for a generated symbol."""

    selected_checks = tuple(
        (index, check)
        for index, check in enumerate(plan.check_details, start=1)
        if (check.executable or include_nonexecutable) and (categories is None or check.category in categories)
    )
    check_indexes = tuple(index for index, _check in selected_checks)
    check_ids = tuple(check.check_id for _index, check in selected_checks)
    refs = tuple(dict.fromkeys(ref for _index, check in selected_checks for ref in check.evidence_refs))
    if not plan.check_details:
        check_indexes = tuple(range(1, len(plan.checks) + 1))
        refs = provenance_refs(plan)
    requirement_ids = tuple(
        requirement.requirement_id
        for requirement in plan.structured_requirements
        if not refs or any(ref in refs for ref in requirement.evidence_refs)
    )
    behavior_ids = tuple(
        behavior.behavior_id
        for behavior in plan.behaviors
        if not refs or any(ref in refs for ref in behavior.evidence_refs)
    )
    claim_ids = tuple(
        claim.claim_id for claim in plan.claims if not refs or any(ref in refs for ref in claim.evidence_refs)
    )
    protocol_ids = tuple(protocol.name for protocol in plan.protocol_models) + tuple(
        protocol.protocol_id for protocol in plan.protocols
    )
    register_ids = tuple(register.name for register in plan.register_models)
    if not refs:
        refs = provenance_refs(plan)
    return (
        ArtifactTrace(
            trace_id=f"{plan.module}:{generated_symbol}",
            generated_symbol=generated_symbol,
            check_indexes=check_indexes,
            check_ids=check_ids,
            requirement_ids=requirement_ids,
            behavior_ids=behavior_ids,
            claim_ids=claim_ids,
            protocol_ids=protocol_ids,
            register_ids=register_ids,
            evidence_refs=refs,
        ),
    )


def protocol_mapping_header(plan: VerificationPlan, target: VerificationTarget) -> str:
    """Render non-executable mapping intent consumed consistently by every backend."""

    if not plan.protocol_models and not plan.register_models:
        return ""
    if target == VerificationTarget.COCOTB:
        marker = "#"
    elif target == VerificationTarget.VHDL:
        marker = "--"
    else:
        marker = "//"
    lines = [f"{marker} Deterministic protocol/register mappings for {target.value}."]
    for protocol in plan.protocol_models:
        status = (
            "non-executable: " + "; ".join(protocol.unsupported_semantics)
            if protocol.unsupported_semantics
            else "mapped"
        )
        mappings = mappings_for(protocol.name, target)
        template = mappings[0].template if mappings else "unsupported_protocol_mapping"
        lines.append(
            f"{marker} protocol={protocol.name} version={protocol.version} template={template} status={status}"
        )
    for register in plan.register_models:
        mappings = mappings_for("register", target)
        template = mappings[0].template if mappings else "unsupported_register_mapping"
        lines.append(
            f"{marker} register={register.name} offset={register.offset} width={register.width} template={template}"
        )
    return "\n".join(lines) + "\n\n"


def looks_like_output(name: str) -> bool:
    return name.endswith(("_o", "_out"))


def _packed_range(port: RTLPort) -> str | None:
    if port.width is not None and port.width > 1:
        return f"[{port.width - 1}:0]"
    if port.packed_range and "\n" not in port.packed_range and ";" not in port.packed_range:
        return port.packed_range
    return None
