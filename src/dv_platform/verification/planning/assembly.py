# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from dv_platform.agent.protocols import RegisterConflict, RegisterModel
from dv_platform.analysis.docs import EmbeddingProvider, VectorStore
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    RequirementConflict,
    RTLModule,
    Severity,
    VerificationClaim,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)
from dv_platform.verification.depth import build_depth_checks, validate_depth_policies
from dv_platform.verification.planning.claims import (
    check_clock_claim,
    check_module_ports_claim,
    check_reset_claim,
)
from dv_platform.verification.scenarios import build_deterministic_scenarios, link_scenario_coverage


@dataclass
class _PlanState:
    checks: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    claims: list[VerificationClaim] = field(default_factory=list)
    structured_requirements: tuple[VerificationRequirement, ...] = ()
    requirement_conflicts: tuple[RequirementConflict, ...] = ()


def create_initial_plan(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
    documentation_chunks: tuple[DocumentationChunk, ...] = (),
    retrieval_index_dir: Path | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
    depth_policies: tuple[VerificationDepthPolicy, ...] = (),
    imported_requirements: tuple[VerificationRequirement, ...] = (),
    register_models: tuple[RegisterModel, ...] = (),
    register_conflicts: tuple[RegisterConflict, ...] = (),
    register_open_questions: tuple[str, ...] = (),
) -> VerificationPlan:
    """Create a verification plan through deterministic, evidence-gated phases."""

    state = _PlanState()
    resolved_register_models = tuple(register_models) or module.register_models
    resolved_register_conflicts = tuple(register_conflicts) or module.register_conflicts
    behaviors = _behaviors_from_patterns(module)
    _add_semantic_intent(module, state)
    _add_interface_intent(module, targets, state)
    module_policies, planned_cdc_paths = _add_depth_intent(module, depth_policies, register_open_questions, state)
    _add_documentation_intent(
        module,
        documentation_chunks,
        retrieval_index_dir,
        embedding_provider,
        vector_store,
        imported_requirements,
        state,
    )
    _add_behavior_intent(module, planned_cdc_paths, behaviors, resolved_register_models, state)
    return _assembled_plan(
        module,
        targets,
        module_policies,
        planned_cdc_paths,
        behaviors,
        resolved_register_models,
        resolved_register_conflicts,
        state,
    )


def _add_semantic_intent(module: RTLModule, state: _PlanState) -> None:
    _add_case_intent(module, state)
    expression, cast = _add_expression_intent(module, state)
    _add_property_intent(module, expression, cast, state)


def _add_case_intent(module: RTLModule, state: _PlanState) -> None:
    case_blocks = tuple(
        block
        for block in module.procedural_block_details
        if any(expression.kind in {"case", "casez", "casex"} for expression in _walk_expressions(block.expressions))
    )
    for block in case_blocks:
        branches = tuple(branch for branch in block.branches if branch.kind in {"case", "casez", "casex"})
        if not branches:
            state.open_questions.append("A case statement was found without normalized case-item semantics.")
            state.claims.append(
                _missing_semantic_claim(
                    module, "case-semantics", "Case selector, labels, and default behavior are fully normalized."
                )
            )
            continue
        if any(branch.condition is None or branch.mutually_exclusive is None for branch in branches):
            state.open_questions.append(
                "Case matching semantics are incomplete; confirm wildcard matching and branch exclusivity."
            )
            state.claims.append(
                _missing_semantic_claim(
                    module,
                    "case-matching-semantics",
                    "Case branch matching and exclusivity are known for executable generation.",
                )
            )
        else:
            state.checks.extend(
                f"Exercise normalized {branch.kind} branch at {branch.source_location or 'unknown source location'}."
                for branch in branches
            )


def _add_expression_intent(module: RTLModule, state: _PlanState):
    expressions = tuple(
        expression
        for assignment in module.assignment_details
        for expression in _walk_expressions(assignment.expressions)
    ) + tuple(
        expression for block in module.procedural_block_details for expression in _walk_expressions(block.expressions)
    )
    if not expressions:
        return None, None
    for expression in expressions:
        if expression.kind in {"add", "sub", "mul", "div", "mod", "concat", "cond"} and expression.width is None:
            state.open_questions.append(
                f"Expression result width is unresolved for {expression.kind} at "
                f"{expression.source_location or 'unknown source location'}; semantic closure is unavailable."
            )
        cast = expression.cast_kind is not None or expression.kind in {
            "cast",
            "signed",
            "unsigned",
            "extend",
            "zext",
            "sext",
            "truncate",
        }
    return expression, cast


def _add_property_intent(module: RTLModule, expression, cast, state: _PlanState) -> None:
    for prop in module.property_details:
        if prop.support_status == "normalized" and not prop.unsupported_operators:
            state.checks.append(
                f"Exercise {prop.kind} property {prop.name or prop.source_location or 'unnamed property'}."
            )
            continue
        operators = ", ".join(prop.unsupported_operators) or "incomplete property body"
        state.open_questions.append(
            f"Property {prop.name or prop.source_location or 'unnamed'} has unsupported semantics: {operators}."
        )
        state.claims.append(
            VerificationClaim(
                claim_id=f"{module.name}:property-semantics:{len(state.claims)}",
                scope=module.name,
                statement="Assertion and coverage temporal semantics are complete before influencing generation.",
                claim_type=ClaimType.RTL_BEHAVIOR,
                severity=Severity.CRITICAL,
                generation_precondition=True,
                status=ClaimStatus.MISSING_EVIDENCE,
                evidence_refs=module.ast_refs,
            )
        )
        if expression is None:
            raise UnboundLocalError("cannot access local variable 'expression' where it is not associated with a value")
        if cast and (expression.width is None or expression.signed is None):
            state.open_questions.append(
                f"Expression sizing/casting is incomplete for {expression.kind} at "
                f"{expression.source_location or 'unknown source location'}."
            )
            state.claims.append(
                _missing_semantic_claim(
                    module,
                    f"expression-semantics:{len(state.claims)}",
                    "Expression width, signedness, and cast behavior are known for executable generation.",
                )
            )


def _missing_semantic_claim(module: RTLModule, suffix: str, statement: str) -> VerificationClaim:
    return VerificationClaim(
        claim_id=f"{module.name}:{suffix}",
        scope=module.name,
        statement=statement,
        claim_type=ClaimType.RTL_STRUCTURE,
        severity=Severity.CRITICAL,
        generation_precondition=True,
        status=ClaimStatus.MISSING_EVIDENCE,
        evidence_refs=module.ast_refs,
    )


def _add_interface_intent(module: RTLModule, targets: tuple[VerificationTarget, ...], state: _PlanState) -> None:
    _add_clock_reset_port_intent(module, targets, state)
    interface_ports = tuple(port for port in module.port_details if port.data_type == "ifacerefdtype")
    unresolved = tuple(
        port
        for port in interface_ports
        if port.interface_name is None or port.modport is None or port.interface_direction is None
    )
    if unresolved:
        state.open_questions.append(
            "Interface/modport directionality is unresolved for: " + ", ".join(port.name for port in unresolved) + "."
        )
        state.claims.append(
            _missing_semantic_claim(
                module,
                "interface-modport-semantics",
                "All interface ports have resolved interface, modport, and direction facts.",
            )
        )
    else:
        state.checks.extend(
            f"Exercise interface {port.interface_name}.{port.modport} direction {port.interface_direction}."
            for port in interface_ports
        )
    for index, feature in enumerate(module.semantic_features, start=1):
        unsupported = tuple(target for target in targets if not feature.supports_target(target))
        if not unsupported:
            continue
        refs = (
            tuple(
                ref
                for ref in module.ast_refs
                if ref.locator.split("@", 1)[0].startswith(f"semantic-feature:{module.name}.{feature.kind}")
            )
            or module.ast_refs
        )
        if len(unsupported) == len(targets):
            claim = _missing_semantic_claim(
                module,
                f"semantic-feature:{feature.kind}:{index}",
                f"Executable generation supports the extracted {feature.kind} construct for "
                + ", ".join(str(target) for target in unsupported)
                + ".",
            )
            state.claims.append(replace(claim, evidence_refs=refs))
        state.open_questions.append(
            f"RTL feature {feature.kind} is unsupported for {', '.join(str(target) for target in unsupported)}; "
            "provide a supported adapter or constrain those targets."
        )


def _add_clock_reset_port_intent(module, targets, state) -> None:
    if module.clocks:
        state.checks.append("Drive declared clock inputs with stable periods.")
        state.claims.append(
            check_clock_claim(
                VerificationClaim(
                    f"{module.name}:clocking",
                    module.name,
                    "The module has one or more clock inputs.",
                    ClaimType.RTL_STRUCTURE,
                    Severity.HIGH,
                    True,
                    evidence_refs=module.ast_refs,
                ),
                module,
            )
        )
        if len(module.clocks) > 1 and (
            any(target != VerificationTarget.COCOTB for target in targets)
            or not module.control_domains
            or any(
                block.domain_id is None for block in module.procedural_block_details if block.kind not in {"alwayscomb"}
            )
        ):
            state.open_questions.append(
                "Multiple clock domains were identified; map each planned behavior to its sampling clock before executable generation."
            )
        if any(clock.confidence == "low" for clock in _plan_clocks(module)):
            state.open_questions.append("Confirm clock classification inferred only from signal naming.")
    else:
        state.open_questions.append("No clock signal was identified.")
    _add_reset_port_intent(module, state)


def _add_reset_port_intent(module, state) -> None:
    if module.resets:
        state.checks.append("Exercise reset assertion and deassertion sequencing.")
        state.claims.append(
            check_reset_claim(
                VerificationClaim(
                    f"{module.name}:reset",
                    module.name,
                    "The module has one or more reset inputs.",
                    ClaimType.RTL_STRUCTURE,
                    Severity.MEDIUM,
                    True,
                    evidence_refs=module.ast_refs,
                ),
                module,
            )
        )
        if len(module.resets) > 1:
            state.open_questions.append(
                "Multiple resets were identified; document domain, priority, polarity, and release ordering for each reset."
            )
        if any(reset.confidence == "low" for reset in _plan_resets(module)):
            state.open_questions.append("Confirm reset polarity and role inferred only from signal naming.")
    else:
        state.assumptions.append("Module may be combinational or resetless.")
    if module.ports:
        state.checks.append("Generate basic input/output connectivity checks.")
        state.claims.append(
            check_module_ports_claim(
                VerificationClaim(
                    f"{module.name}:ports",
                    module.name,
                    "The module has extracted port declarations with valid directions when available.",
                    ClaimType.RTL_STRUCTURE,
                    Severity.MEDIUM,
                    True,
                    evidence_refs=module.ast_refs,
                ),
                module,
            )
        )
    else:
        state.open_questions.append("No ports were extracted for this module.")


def _add_depth_intent(module, depth_policies, register_questions, state):
    state.checks.extend(_checks_for_protocols(module))
    state.checks.extend(_checks_for_protocol_models(module))
    policies = tuple(policy for policy in depth_policies if policy.module in {module.name, module.original_name})
    state.checks.extend(build_depth_checks(module, policies))
    state.open_questions.extend(register_questions)
    depth_claims = validate_depth_policies(module, policies)
    state.claims.extend(depth_claims)
    supported_cdc = {
        claim.claim_id.rsplit(":", 1)[-1]
        for claim in depth_claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:cdc:" in claim.claim_id
    }
    supported_reset = {
        claim.claim_id.rsplit(":", 1)[-1]
        for claim in depth_claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:reset:" in claim.claim_id
    }
    structures = {
        policy.subject: policy.parameter("structure") or "two_flop"
        for policy in policies
        if policy.kind == "cdc" and policy.subject in supported_cdc
    }
    fifo_signals = {
        signal
        for policy in policies
        if policy.kind == "cdc" and policy.subject in supported_cdc and policy.parameter("structure") == "async_fifo"
        for signal in (policy.parameter("write_gray_pointer"), policy.parameter("read_gray_pointer"))
        if signal
    }
    reset_dependencies = {
        signal
        for policy in policies
        if policy.kind == "reset"
        and policy.subject in supported_reset
        and (signal := policy.parameter("depends_on_ready"))
    }
    structures.update({signal: "gray" for signal in fifo_signals})
    governed = fifo_signals | reset_dependencies
    paths = tuple(
        replace(
            path,
            classification=structures.get(path.signal, path.classification),
            safe=True if path.signal in governed else path.safe,
            reset_compatible=None if path.signal in governed else path.reset_compatible,
        )
        for path in module.cdc_paths
    )
    return policies, paths


def _add_documentation_intent(
    module,
    documentation_chunks,
    retrieval_index_dir,
    embedding_provider,
    vector_store,
    imported_requirements,
    state,
) -> None:
    refs = _retrieve_documentation_refs(
        module, documentation_chunks, retrieval_index_dir, embedding_provider, vector_store
    )
    synthesized = _synthesize_requirements(module, refs) if refs else ()
    state.structured_requirements = _merge_imported_requirements(module, synthesized, imported_requirements)
    if state.structured_requirements:
        state.requirement_conflicts = _find_requirement_conflicts(module, state.structured_requirements)
        state.requirements.extend(
            requirement.statement
            for requirement in state.structured_requirements
            if requirement.statement not in state.requirements
        )
        checks, claims = _requirement_driven_checks(module, state.structured_requirements)
        state.checks.extend(checks)
        state.claims.extend(claims)
        state.claims.extend(_conflict_claim(conflict) for conflict in state.requirement_conflicts)
        state.open_questions.extend(_requirement_open_questions(module, state.structured_requirements))
        state.open_questions.extend(_conflict_open_question(conflict) for conflict in state.requirement_conflicts)
    if refs:
        state.claims.append(
            VerificationClaim(
                f"{module.name}:documentation-intent",
                module.name,
                "Relevant design documentation was retrieved for this module.",
                ClaimType.DOCUMENTATION_INTENT,
                Severity.MEDIUM,
                status=ClaimStatus.SUPPORTED,
                evidence_refs=refs,
            )
        )
    elif documentation_chunks:
        state.open_questions.append("No documentation intent was retrieved for this module.")


def _add_behavior_intent(module, planned_cdc_paths, behaviors, register_models, state) -> None:
    for check in _checks_for_behaviors(behaviors):
        if check not in state.checks:
            state.checks.append(check)
    for memory in module.memories:
        accesses = tuple(access for access in module.memory_accesses if access.memory == memory.name)
        reads = tuple(access for access in accesses if access.kind == "read")
        writes = tuple(access for access in accesses if access.kind == "write")
        if reads:
            state.checks.append(
                f"Verify reads from memory {memory.name} use the extracted address and timing contract."
            )
        if writes:
            state.checks.append(f"Verify writes to memory {memory.name} update only the selected address when enabled.")
        if reads and writes and memory.read_during_write == "unknown":
            state.open_questions.append(
                f"Define read-during-write behavior for memory {memory.name}; the elaborated RTL does not prove a collision policy."
            )
    for path in planned_cdc_paths:
        if path.safe:
            state.checks.append(
                f"Verify CDC path {path.signal} from {path.source_domain} to {path.destination_domain} preserves its "
                f"{path.synchronizer_stages}-stage synchronizer."
            )
        else:
            state.checks.append(
                f"Review unsafe CDC path {path.signal} from {path.source_domain} to {path.destination_domain}."
            )
            state.open_questions.append(
                f"CDC path {path.path_id} has no proven two-stage synchronizer or compatible reset strategy."
            )
    protocols = tuple(
        protocol.name for protocol in module.protocol_models if protocol.name in {"APB4", "AXI4-Lite", "AHB-Lite"}
    )
    state.checks.extend(
        f"Verify {protocol} register {register.name} reset, RW/RO/W1C fields, byte strobes, and error behavior."
        for protocol in protocols
        for register in register_models
    )


def _assembled_plan(
    module,
    targets,
    policies,
    planned_cdc_paths,
    behaviors,
    register_models,
    register_conflicts,
    state,
):
    unique_checks = tuple(dict.fromkeys(state.checks))
    check_details = _build_check_details(
        module, targets, unique_checks, state.structured_requirements, behaviors, register_models
    )
    plan = VerificationPlan(
        module=module.name,
        targets=targets,
        design_unit=module.original_name or module.name,
        elaborated_design_unit=module.elaborated_name,
        specialization_id=module.specialization_id,
        design_unit_kind=module.design_unit_kind,
        ports=_plan_ports(module),
        clocks=_plan_clocks(module),
        resets=_plan_resets(module),
        semantic_features=module.semantic_features,
        parameters=module.parameter_details,
        memories=module.memories,
        memory_accesses=module.memory_accesses,
        type_details=module.type_details,
        instances=module.instance_details,
        control_domains=module.control_domains,
        cdc_paths=planned_cdc_paths,
        generate_scopes=module.generate_scopes,
        imports=module.imports,
        protocols=module.protocols,
        protocol_models=module.protocol_models,
        register_models=register_models,
        register_conflicts=register_conflicts,
        property_details=module.property_details,
        depth_policies=policies,
        requirements=tuple(state.requirements),
        structured_requirements=state.structured_requirements,
        requirement_conflicts=state.requirement_conflicts,
        behaviors=behaviors,
        claims=tuple(state.claims),
        checks=unique_checks,
        check_details=check_details,
        assumptions=tuple(state.assumptions),
        open_questions=tuple(state.open_questions),
    )
    scenarios = build_deterministic_scenarios(plan)
    linked_checks = link_scenario_coverage(plan.check_details, scenarios)
    if plan.protocol_models:
        executable = {check_id for scenario in scenarios if scenario.executable for check_id in scenario.check_ids}
        linked_checks = tuple(
            replace(check, executable=check.check_id in executable)
            if check.category in {"protocol", "register_access", "reset"}
            else check
            for check in linked_checks
        )
    return replace(plan, check_details=linked_checks, scenarios=scenarios)
