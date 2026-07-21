"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path

from dv_platform.agent.protocols import RegisterConflict, RegisterModel
from dv_platform.analysis.claims import (
    check_clock_claim,
    check_module_ports_claim,
    check_requirement_behavior_claim,
    check_reset_claim,
)
from dv_platform.analysis.depth import build_depth_checks, validate_depth_policies
from dv_platform.analysis.docs import retrieve_chunks, retrieve_chunks_with_vectors
from dv_platform.analysis.scenarios import build_deterministic_scenarios, link_scenario_coverage
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    RTLClock,
    RTLExpression,
    RTLModule,
    RTLPort,
    RTLProtocol,
    RTLReset,
    Severity,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)


def create_initial_plan(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
    documentation_chunks: tuple[DocumentationChunk, ...] = (),
    retrieval_index_dir: Path | None = None,
    depth_policies: tuple[VerificationDepthPolicy, ...] = (),
    imported_requirements: tuple[VerificationRequirement, ...] = (),
    register_models: tuple[RegisterModel, ...] = (),
    register_conflicts: tuple[RegisterConflict, ...] = (),
    register_open_questions: tuple[str, ...] = (),
) -> VerificationPlan:
    """Create a minimal verification plan from extracted module metadata."""

    checks: list[str] = []
    requirements: list[str] = []
    assumptions: list[str] = []
    open_questions: list[str] = []
    claims: list[VerificationClaim] = []
    structured_requirements: tuple[VerificationRequirement, ...] = ()
    resolved_register_models = tuple(register_models) or module.register_models
    resolved_register_conflicts = tuple(register_conflicts) or module.register_conflicts
    requirement_conflicts: tuple[RequirementConflict, ...] = ()
    behaviors = _behaviors_from_patterns(module)

    case_blocks = tuple(
        block
        for block in module.procedural_block_details
        if any(expression.kind in {"case", "casez", "casex"} for expression in _walk_expressions(block.expressions))
    )
    for block in case_blocks:
        branches = tuple(branch for branch in block.branches if branch.kind in {"case", "casez", "casex"})
        if not branches:
            open_questions.append("A case statement was found without normalized case-item semantics.")
            claims.append(
                VerificationClaim(
                    claim_id=f"{module.name}:case-semantics",
                    scope=module.name,
                    statement="Case selector, labels, and default behavior are fully normalized.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.CRITICAL,
                    generation_precondition=True,
                    status=ClaimStatus.MISSING_EVIDENCE,
                    evidence_refs=module.ast_refs,
                )
            )
            continue
        if any(branch.condition is None or branch.mutually_exclusive is None for branch in branches):
            open_questions.append(
                "Case matching semantics are incomplete; confirm wildcard matching and branch exclusivity."
            )
            claims.append(
                VerificationClaim(
                    claim_id=f"{module.name}:case-matching-semantics",
                    scope=module.name,
                    statement="Case branch matching and exclusivity are known for executable generation.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.CRITICAL,
                    generation_precondition=True,
                    status=ClaimStatus.MISSING_EVIDENCE,
                    evidence_refs=module.ast_refs,
                )
            )
        else:
            checks.extend(
                f"Exercise normalized {branch.kind} branch at {branch.source_location or 'unknown source location'}."
                for branch in branches
            )

    semantic_expressions = tuple(
        expression
        for assignment in module.assignment_details
        for expression in _walk_expressions(assignment.expressions)
    ) + tuple(
        expression for block in module.procedural_block_details for expression in _walk_expressions(block.expressions)
    )
    for expression in semantic_expressions:
        arithmetic = expression.kind in {"add", "sub", "mul", "div", "mod", "concat", "cond"}
        cast = expression.cast_kind is not None or expression.kind in {
            "cast",
            "signed",
            "unsigned",
            "extend",
            "zext",
            "sext",
            "truncate",
        }
        if arithmetic and expression.width is None:
            open_questions.append(
                f"Expression result width is unresolved for {expression.kind} at "
                f"{expression.source_location or 'unknown source location'}; semantic closure is unavailable."
            )

    for prop in module.property_details:
        if prop.support_status == "normalized" and not prop.unsupported_operators:
            checks.append(f"Exercise {prop.kind} property {prop.name or prop.source_location or 'unnamed property'}.")
            continue
        operators = ", ".join(prop.unsupported_operators) or "incomplete property body"
        open_questions.append(
            f"Property {prop.name or prop.source_location or 'unnamed'} has unsupported semantics: {operators}."
        )
        claims.append(
            VerificationClaim(
                claim_id=f"{module.name}:property-semantics:{len(claims)}",
                scope=module.name,
                statement="Assertion and coverage temporal semantics are complete before influencing generation.",
                claim_type=ClaimType.RTL_BEHAVIOR,
                severity=Severity.CRITICAL,
                generation_precondition=True,
                status=ClaimStatus.MISSING_EVIDENCE,
                evidence_refs=module.ast_refs,
            )
        )
        if cast and (expression.width is None or expression.signed is None):
            open_questions.append(
                f"Expression sizing/casting is incomplete for {expression.kind} at "
                f"{expression.source_location or 'unknown source location'}."
            )
            claims.append(
                VerificationClaim(
                    claim_id=f"{module.name}:expression-semantics:{len(claims)}",
                    scope=module.name,
                    statement="Expression width, signedness, and cast behavior are known for executable generation.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.CRITICAL,
                    generation_precondition=True,
                    status=ClaimStatus.MISSING_EVIDENCE,
                    evidence_refs=module.ast_refs,
                )
            )

    if module.clocks:
        checks.append("Drive declared clock inputs with stable periods.")
        claims.append(
            check_clock_claim(
                VerificationClaim(
                    claim_id=f"{module.name}:clocking",
                    scope=module.name,
                    statement="The module has one or more clock inputs.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.HIGH,
                    generation_precondition=True,
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
            open_questions.append(
                "Multiple clock domains were identified; map each planned behavior to its sampling clock before executable generation."
            )
        if any(clock.confidence == "low" for clock in _plan_clocks(module)):
            open_questions.append("Confirm clock classification inferred only from signal naming.")
    else:
        open_questions.append("No clock signal was identified.")

    if module.resets:
        checks.append("Exercise reset assertion and deassertion sequencing.")
        claims.append(
            check_reset_claim(
                VerificationClaim(
                    claim_id=f"{module.name}:reset",
                    scope=module.name,
                    statement="The module has one or more reset inputs.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.MEDIUM,
                    generation_precondition=True,
                    evidence_refs=module.ast_refs,
                ),
                module,
            )
        )
        if len(module.resets) > 1:
            open_questions.append(
                "Multiple resets were identified; document domain, priority, polarity, and release ordering for each reset."
            )
        if any(reset.confidence == "low" for reset in _plan_resets(module)):
            open_questions.append("Confirm reset polarity and role inferred only from signal naming.")
    else:
        assumptions.append("Module may be combinational or resetless.")

    if module.ports:
        checks.append("Generate basic input/output connectivity checks.")
        claims.append(
            check_module_ports_claim(
                VerificationClaim(
                    claim_id=f"{module.name}:ports",
                    scope=module.name,
                    statement="The module has extracted port declarations with valid directions when available.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.MEDIUM,
                    generation_precondition=True,
                    evidence_refs=module.ast_refs,
                ),
                module,
            )
        )
    else:
        open_questions.append("No ports were extracted for this module.")

    interface_ports = tuple(port for port in module.port_details if port.data_type == "ifacerefdtype")
    if interface_ports:
        unresolved = tuple(
            port
            for port in interface_ports
            if port.interface_name is None or port.modport is None or port.interface_direction is None
        )
        if unresolved:
            open_questions.append(
                "Interface/modport directionality is unresolved for: "
                + ", ".join(port.name for port in unresolved)
                + "."
            )
            claims.append(
                VerificationClaim(
                    claim_id=f"{module.name}:interface-modport-semantics",
                    scope=module.name,
                    statement="All interface ports have resolved interface, modport, and direction facts.",
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.CRITICAL,
                    generation_precondition=True,
                    status=ClaimStatus.MISSING_EVIDENCE,
                    evidence_refs=module.ast_refs,
                )
            )
        else:
            checks.extend(
                f"Exercise interface {port.interface_name}.{port.modport} direction {port.interface_direction}."
                for port in interface_ports
            )

    for feature_index, feature in enumerate(module.semantic_features, start=1):
        unsupported_targets = tuple(target for target in targets if not feature.supports_target(target))
        if not unsupported_targets:
            continue
        feature_refs = (
            tuple(
                ref
                for ref in module.ast_refs
                if ref.locator.split("@", 1)[0].startswith(f"semantic-feature:{module.name}.{feature.kind}")
            )
            or module.ast_refs
        )
        if len(unsupported_targets) == len(targets):
            claims.append(
                VerificationClaim(
                    claim_id=f"{module.name}:semantic-feature:{feature.kind}:{feature_index}",
                    scope=module.name,
                    statement=(
                        f"Executable generation supports the extracted {feature.kind} construct for "
                        + ", ".join(str(target) for target in unsupported_targets)
                        + "."
                    ),
                    claim_type=ClaimType.RTL_STRUCTURE,
                    severity=Severity.CRITICAL,
                    generation_precondition=True,
                    status=ClaimStatus.MISSING_EVIDENCE,
                    evidence_refs=feature_refs,
                )
            )
        open_questions.append(
            f"RTL feature {feature.kind} is unsupported for {', '.join(str(target) for target in unsupported_targets)}; "
            "provide a supported adapter or constrain those targets."
        )

    checks.extend(_checks_for_protocols(module))
    checks.extend(_checks_for_protocol_models(module))
    module_depth_policies = tuple(
        policy for policy in depth_policies if policy.module in {module.name, module.original_name}
    )
    checks.extend(build_depth_checks(module, module_depth_policies))
    open_questions.extend(register_open_questions)
    claims.extend(validate_depth_policies(module, module_depth_policies))

    documentation_refs = _retrieve_documentation_refs(module, documentation_chunks, retrieval_index_dir)
    synthesized_requirements = _synthesize_requirements(module, documentation_refs) if documentation_refs else ()
    structured_requirements = _merge_imported_requirements(
        module,
        synthesized_requirements,
        imported_requirements,
    )
    if structured_requirements:
        requirement_conflicts = _find_requirement_conflicts(module, structured_requirements)
        requirements.extend(
            requirement.statement
            for requirement in structured_requirements
            if requirement.statement not in requirements
        )
        requirement_checks, requirement_claims = _requirement_driven_checks(module, structured_requirements)
        checks.extend(requirement_checks)
        claims.extend(requirement_claims)
        claims.extend(_conflict_claim(conflict) for conflict in requirement_conflicts)
        open_questions.extend(_requirement_open_questions(module, structured_requirements))
        open_questions.extend(_conflict_open_question(conflict) for conflict in requirement_conflicts)

    if documentation_refs:
        claims.append(
            VerificationClaim(
                claim_id=f"{module.name}:documentation-intent",
                scope=module.name,
                statement="Relevant design documentation was retrieved for this module.",
                claim_type=ClaimType.DOCUMENTATION_INTENT,
                severity=Severity.MEDIUM,
                status=ClaimStatus.SUPPORTED,
                evidence_refs=documentation_refs,
            )
        )
    elif documentation_chunks:
        open_questions.append("No documentation intent was retrieved for this module.")

    for check in _checks_for_behaviors(behaviors):
        if check not in checks:
            checks.append(check)

    for memory in module.memories:
        accesses = tuple(access for access in module.memory_accesses if access.memory == memory.name)
        reads = tuple(access for access in accesses if access.kind == "read")
        writes = tuple(access for access in accesses if access.kind == "write")
        if reads:
            checks.append(f"Verify reads from memory {memory.name} use the extracted address and timing contract.")
        if writes:
            checks.append(f"Verify writes to memory {memory.name} update only the selected address when enabled.")
        if reads and writes and memory.read_during_write == "unknown":
            open_questions.append(
                f"Define read-during-write behavior for memory {memory.name}; the elaborated RTL does not prove a collision policy."
            )

    for path in module.cdc_paths:
        if path.safe:
            checks.append(
                f"Verify CDC path {path.signal} from {path.source_domain} to {path.destination_domain} preserves its "
                f"{path.synchronizer_stages}-stage synchronizer."
            )
        else:
            checks.append(
                f"Review unsafe CDC path {path.signal} from {path.source_domain} to {path.destination_domain}."
            )
            open_questions.append(
                f"CDC path {path.path_id} has no proven two-stage synchronizer or compatible reset strategy."
            )

    unique_checks = tuple(dict.fromkeys(checks))
    check_details = _build_check_details(module, targets, unique_checks, structured_requirements, behaviors)

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
        cdc_paths=module.cdc_paths,
        generate_scopes=module.generate_scopes,
        imports=module.imports,
        protocols=module.protocols,
        protocol_models=module.protocol_models,
        register_models=resolved_register_models,
        register_conflicts=resolved_register_conflicts,
        property_details=module.property_details,
        depth_policies=module_depth_policies,
        requirements=tuple(requirements),
        structured_requirements=structured_requirements,
        requirement_conflicts=requirement_conflicts,
        behaviors=behaviors,
        claims=tuple(claims),
        checks=unique_checks,
        check_details=check_details,
        assumptions=tuple(assumptions),
        open_questions=tuple(open_questions),
    )
    scenarios = build_deterministic_scenarios(plan)
    linked_checks = link_scenario_coverage(plan.check_details, scenarios)
    if plan.protocol_models:
        executable_scenario_checks = {
            check_id for scenario in scenarios if scenario.executable for check_id in scenario.check_ids
        }
        linked_checks = tuple(
            replace(check, executable=check.check_id in executable_scenario_checks)
            if check.category in {"protocol", "register_access"}
            else check
            for check in linked_checks
        )
    return replace(plan, check_details=linked_checks, scenarios=scenarios)


def _build_check_details(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
    checks: tuple[str, ...],
    requirements: tuple[VerificationRequirement, ...],
    behaviors: tuple[VerificationBehavior, ...],
) -> tuple[VerificationCheck, ...]:
    """Give every human-readable check a stable identity and precise evidence."""

    details: list[VerificationCheck] = []
    for statement in checks:
        normalized = statement.lower()
        category = _check_category(normalized)
        matched_requirements = tuple(
            requirement
            for requirement in requirements
            if statement in _checks_for_requirement(module, requirement.statement.lower())
        )
        matched_behaviors = tuple(behavior for behavior in behaviors if statement in _checks_for_behaviors((behavior,)))
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    *(ref for requirement in matched_requirements for ref in requirement.evidence_refs),
                    *(ref for behavior in matched_behaviors for ref in behavior.evidence_refs),
                )
            )
        )
        if not evidence_refs:
            evidence_refs = _check_structural_evidence(module, category, normalized)
        identity = "|".join((module.name, category, " ".join(normalized.split())))
        check_id = f"{module.name}:check:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"
        details.append(
            VerificationCheck(
                check_id=check_id,
                statement=statement,
                category=category,
                executable=_check_is_executable(category, normalized, matched_requirements, matched_behaviors, targets),
                evidence_refs=evidence_refs,
            )
        )
    return tuple(details)


def _check_category(statement: str) -> str:
    categories = (
        ("cdc", ("cdc path", "synchronizer")),
        ("memory", ("memory ", "read-during-write")),
        (
            "protocol",
            (
                "ready/valid",
                "backpressure",
                "without corruption",
                "transfers complete",
                "ordering rules",
                "response and error behavior",
            ),
        ),
        ("reset", ("reset",)),
        ("increment", ("increment", "updates")),
        ("clock", ("clock", "period")),
        ("hold", ("remains stable", "stable")),
        ("connectivity", ("connectivity", "input/output")),
    )
    return next((category for category, terms in categories if any(term in statement for term in terms)), "general")


def _check_is_executable(
    category: str,
    statement: str,
    requirements: tuple[VerificationRequirement, ...],
    behaviors: tuple[VerificationBehavior, ...],
    targets: tuple[VerificationTarget, ...],
) -> bool:
    if category == "cdc":
        return VerificationTarget.FORMAL in targets
    if statement.startswith("cover "):
        if category == "memory":
            return VerificationTarget.FORMAL in targets
        if category in {"protocol", "reset"}:
            return bool({VerificationTarget.COCOTB, VerificationTarget.FORMAL} & set(targets))
        return False
    if behaviors or requirements:
        return category in {"reset", "increment", "hold", "protocol", "connectivity"}
    if category == "protocol":
        return "without corruption" not in statement
    if category == "memory":
        return VerificationTarget.FORMAL in targets and (
            "writes to memory" in statement or "configured memory" in statement
        )
    return False


def _check_structural_evidence(module: RTLModule, category: str, statement: str) -> tuple[EvidenceRef, ...]:
    if category == "cdc":
        return tuple(ref for path in module.cdc_paths if path.signal.lower() in statement for ref in path.evidence_refs)
    if category == "memory":
        return tuple(
            ref
            for access in module.memory_accesses
            if access.memory.lower() in statement
            for ref in access.evidence_refs
        )
    if category == "protocol":
        return tuple(
            ref for protocol in module.protocols if protocol.name.lower() in statement for ref in protocol.evidence_refs
        ) + tuple(
            ref
            for protocol in module.protocol_models
            if protocol.name.lower() in statement
            for ref in protocol.evidence_refs
        )
    return module.ast_refs


def _plan_ports(module: RTLModule) -> tuple[RTLPort, ...]:
    if module.port_details:
        return module.port_details
    return tuple(RTLPort(name=port, direction="unknown") for port in module.ports)


def _plan_clocks(module: RTLModule) -> tuple[RTLClock, ...]:
    if module.clock_details:
        return module.clock_details
    return tuple(RTLClock(name=name, direction="input") for name in module.clocks)


def _plan_resets(module: RTLModule) -> tuple[RTLReset, ...]:
    if module.reset_details:
        return module.reset_details
    return tuple(RTLReset(name=name, direction="input", active_low=name.endswith("_n")) for name in module.resets)


def _retrieve_documentation_refs(
    module: RTLModule,
    documentation_chunks: tuple[DocumentationChunk, ...],
    retrieval_index_dir: Path | None = None,
) -> tuple[EvidenceRef, ...]:
    if not documentation_chunks:
        return ()

    query = " ".join((module.name, *module.ports, *module.parameters, *module.instances))
    results = (
        retrieve_chunks_with_vectors(query, documentation_chunks, retrieval_index_dir, limit=3)
        if retrieval_index_dir is not None
        else retrieve_chunks(query, documentation_chunks, limit=3)
    )
    refs: list[EvidenceRef] = []
    for result in results:
        chunk = result.chunk
        query_terms = (module.name, *module.ports, *module.parameters, *module.instances)
        sentences = _relevant_requirement_sentences(chunk.text, query_terms)
        if not sentences:
            sentences = ((_requirement_summary(chunk.text, query_terms=query_terms), 0, len(chunk.text)),)
        for sentence, local_start, local_end in sentences:
            absolute_start = (chunk.start_offset or 0) + local_start
            absolute_end = (chunk.start_offset or 0) + local_end
            refs.append(
                EvidenceRef(
                    kind=EvidenceKind.DOCUMENT_CHUNK,
                    source_id=str(chunk.source),
                    locator=(
                        f"chunk:{chunk.chunk_id}@{absolute_start}:{absolute_end}"
                        + (f"#{chunk.source_locator}" if chunk.source_locator else "")
                    ),
                    summary=sentence,
                )
            )
    return tuple(refs)


def _merge_imported_requirements(
    module: RTLModule,
    synthesized: tuple[VerificationRequirement, ...],
    imported: tuple[VerificationRequirement, ...],
) -> tuple[VerificationRequirement, ...]:
    scopes = {
        "*",
        "all",
        "global",
        module.name,
        module.original_name or module.name,
        module.elaborated_name or module.name,
    }
    merged = {requirement.requirement_id: requirement for requirement in synthesized}
    for requirement in imported:
        if requirement.scope not in scopes:
            continue
        existing = merged.get(requirement.requirement_id)
        if existing is not None and existing.statement != requirement.statement:
            raise ValueError(
                f"Requirement ID collision for {requirement.requirement_id}: governed and synthesized statements differ"
            )
        merged[requirement.requirement_id] = requirement
    return tuple(merged.values())


def _synthesize_requirements(
    module: RTLModule,
    documentation_refs: tuple[EvidenceRef, ...],
) -> tuple[VerificationRequirement, ...]:
    grouped: dict[str, tuple[str, list[EvidenceRef]]] = {}
    for ref in documentation_refs:
        statement = " ".join((ref.summary or ref.locator).split())
        canonical = _canonical_requirement(statement)
        if not canonical:
            continue
        existing = grouped.get(canonical)
        if existing is None:
            grouped[canonical] = (statement, [ref])
        elif ref not in existing[1]:
            existing[1].append(ref)

    requirements: list[VerificationRequirement] = []
    for canonical, (statement, refs) in sorted(grouped.items()):
        normalized_statement = statement.lower()
        category = (
            "protocol"
            if any(
                protocol.valid.lower() in normalized_statement and protocol.ready.lower() in normalized_statement
                for protocol in module.protocols
            )
            else _requirement_category(statement)
        )
        signals = tuple(port for port in module.ports if _contains_term(statement.lower(), port.lower()))
        expected_value = _requirement_expected_value(statement, category)
        condition = _requirement_condition(module, statement)
        identity = "|".join((module.name, category, ",".join(signals), canonical))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        requirements.append(
            VerificationRequirement(
                requirement_id=f"{module.name}:docreq:{digest}",
                scope=module.name,
                statement=statement,
                category=category,
                signals=signals,
                expected_value=expected_value,
                condition=condition,
                confidence="deterministic" if category != "general" and signals else "lexical",
                evidence_refs=tuple(refs),
            )
        )
    return tuple(requirements)


def _find_requirement_conflicts(
    module: RTLModule,
    requirements: tuple[VerificationRequirement, ...],
) -> tuple[RequirementConflict, ...]:
    conflicts: list[RequirementConflict] = []
    for index, left in enumerate(requirements):
        for right in requirements[index + 1 :]:
            if left.category == "general" or left.category != right.category:
                continue
            if not set(left.signals) or set(left.signals) != set(right.signals):
                continue
            if left.condition != right.condition:
                continue
            if left.expected_value is None or right.expected_value is None:
                continue
            if left.expected_value == right.expected_value:
                continue
            requirement_ids = tuple(sorted((left.requirement_id, right.requirement_id)))
            digest = hashlib.sha256("|".join(requirement_ids).encode("utf-8")).hexdigest()[:12]
            conflicts.append(
                RequirementConflict(
                    conflict_id=f"{module.name}:conflict:{digest}",
                    scope=module.name,
                    requirement_ids=requirement_ids,
                    reason=(
                        f"Conflicting {left.category} values for {', '.join(left.signals)}"
                        f" under {left.condition or 'the same condition'}: "
                        f"{left.expected_value} versus {right.expected_value}."
                    ),
                    evidence_refs=tuple(dict.fromkeys((*left.evidence_refs, *right.evidence_refs))),
                )
            )
    return tuple(conflicts)


def _conflict_claim(conflict: RequirementConflict) -> VerificationClaim:
    return VerificationClaim(
        claim_id=f"{conflict.conflict_id}:resolution",
        scope=conflict.scope,
        statement=conflict.reason,
        claim_type=ClaimType.DOCUMENTATION_INTENT,
        severity=Severity.CRITICAL,
        generation_precondition=True,
        status=ClaimStatus.CONTRADICTED,
        evidence_refs=conflict.evidence_refs,
    )


def _conflict_open_question(conflict: RequirementConflict) -> str:
    identifiers = " and ".join(conflict.requirement_ids)
    return f"Resolve {identifiers}: {conflict.reason} Which documented value is authoritative?"


def _requirement_open_questions(
    module: RTLModule,
    requirements: tuple[VerificationRequirement, ...],
) -> tuple[str, ...]:
    questions: list[str] = []
    supported_categories = {"reset", "increment", "hold", "connectivity", "protocol"}
    for requirement in requirements:
        if _checks_for_requirement(module, requirement.statement.lower()):
            continue
        if requirement.category in supported_categories:
            detail = "identify the observable input, output, and expected value"
        else:
            detail = "define observable signals, timing, and pass/fail behavior"
        questions.append(
            f"Requirement {requirement.requirement_id} ({requirement.category}) has no executable check; {detail}."
        )
    return tuple(questions)


def _requirement_driven_checks(
    module: RTLModule,
    requirements: tuple[VerificationRequirement, ...],
) -> tuple[tuple[str, ...], tuple[VerificationClaim, ...]]:
    checks: list[str] = []
    claims: list[VerificationClaim] = []
    for requirement in requirements:
        statement = requirement.statement.lower()
        matched_checks = _checks_for_requirement(module, statement)
        for check in matched_checks:
            if check not in checks:
                checks.append(check)
        if matched_checks:
            claims.append(
                check_requirement_behavior_claim(
                    VerificationClaim(
                        claim_id=f"{requirement.requirement_id}:planned-check",
                        scope=module.name,
                        statement=f"Requirement {requirement.requirement_id} has planned verification checks over known RTL signals.",
                        claim_type=ClaimType.PLANNED_CHECK,
                        severity=Severity.MEDIUM,
                        generation_precondition=True,
                        evidence_refs=requirement.evidence_refs,
                    ),
                    requirement,
                    module,
                )
            )
    return tuple(checks), tuple(claims)


def _behaviors_from_patterns(module: RTLModule) -> tuple[VerificationBehavior, ...]:
    behaviors: list[VerificationBehavior] = []
    seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
    for block_index, block in enumerate(module.procedural_block_details, start=1):
        refs = _behavior_evidence_refs(module, block.name)
        for pattern_index, pattern in enumerate(block.patterns, start=1):
            key = (pattern.kind, pattern.target, pattern.control, pattern.value, pattern.source)
            if key in seen:
                continue
            seen.add(key)
            behaviors.append(
                VerificationBehavior(
                    behavior_id=f"{module.name}:behavior:{block_index}:{pattern_index}",
                    scope=module.name,
                    kind=pattern.kind,
                    target=pattern.target,
                    control=pattern.control,
                    value=pattern.value,
                    source=pattern.source,
                    domain_id=block.domain_id,
                    confidence=pattern.confidence,
                    evidence_refs=refs,
                )
            )
    return tuple(behaviors)


def _behavior_evidence_refs(module: RTLModule, block_name: str | None) -> tuple[EvidenceRef, ...]:
    if block_name:
        locator = f"procedure:{module.name}.{block_name}"
        matching_refs = tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0] == locator)
        if matching_refs:
            return matching_refs
    procedure_refs = tuple(
        ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].startswith(f"procedure:{module.name}.")
    )
    return procedure_refs or module.ast_refs


def _checks_for_behaviors(behaviors: tuple[VerificationBehavior, ...]) -> tuple[str, ...]:
    checks: list[str] = []
    for behavior in behaviors:
        if behavior.kind == "reset_to_constant" and behavior.control and behavior.value is not None:
            checks.append(
                f"Verify RTL reset pattern drives {behavior.target} to {behavior.value} when {behavior.control} is active."
            )
        elif behavior.kind == "increment" and behavior.control:
            checks.append(
                f"Verify RTL increment pattern updates {behavior.target} when {behavior.control} is asserted."
            )
    return tuple(checks)


def _checks_for_requirement(module: RTLModule, statement: str) -> tuple[str, ...]:
    checks: list[str] = []
    output_ports = _matching_ports(module, statement, suffixes=("_o", "_out"))
    input_ports = _matching_ports(module, statement, suffixes=("_i", "_in"))
    reset_names = tuple(reset for reset in module.resets if reset.lower() in statement)
    matched_protocols = tuple(
        protocol
        for protocol in module.protocols
        if protocol.valid.lower() in statement and protocol.ready.lower() in statement
    )

    if output_ports and reset_names and _mentions_any(statement, ("clear", "clears", "cleared", "zero", "reset")):
        for output in output_ports:
            for reset in reset_names:
                checks.append(f"Verify {reset} drives {output} to its documented reset value.")

    if output_ports and input_ports and _mentions_any(statement, ("increment", "increments", "increase", "increases")):
        for output in output_ports:
            for input_name in input_ports:
                checks.append(f"Verify {output} increments when {input_name} is asserted.")

    if (
        not matched_protocols
        and output_ports
        and input_ports
        and _mentions_any(statement, ("hold", "holds", "stable", "unchanged"))
    ):
        for output in output_ports:
            for input_name in input_ports:
                checks.append(f"Verify {output} remains stable when {input_name} is inactive.")

    for protocol in matched_protocols:
        checks.append(_protocol_transfer_check(protocol))
        if protocol.role == "source" and protocol.data is not None:
            checks.append(
                f"Verify {protocol.valid} and {protocol.data} remain stable while {protocol.ready} applies backpressure."
            )

    return tuple(checks)


def _checks_for_protocols(module: RTLModule) -> tuple[str, ...]:
    checks: list[str] = []
    for protocol in module.protocols:
        checks.append(_protocol_transfer_check(protocol))
        if protocol.role == "source" and protocol.data is not None:
            checks.append(
                f"Verify {protocol.valid} and {protocol.data} remain stable while {protocol.ready} applies backpressure."
            )
    sinks = tuple(protocol for protocol in module.protocols if protocol.role == "sink" and protocol.data is not None)
    sources = tuple(
        protocol for protocol in module.protocols if protocol.role == "source" and protocol.data is not None
    )
    if len(sinks) == 1 and len(sources) == 1:
        checks.append(f"Verify accepted {sinks[0].name} data is observed on {sources[0].name} without corruption.")
    return tuple(checks)


def _checks_for_protocol_models(module: RTLModule) -> tuple[str, ...]:
    checks: list[str] = []
    for protocol in module.protocol_models:
        checks.append(f"Verify {protocol.name} transfers complete only under the documented transfer condition.")
        if protocol.ordering_rules:
            checks.append(f"Verify {protocol.name} ordering rules are preserved under wait states and backpressure.")
        if protocol.error_behavior != "unknown":
            checks.append(f"Verify {protocol.name} response and error behavior follows {protocol.error_behavior}.")
    return tuple(checks)


def _protocol_transfer_check(protocol: RTLProtocol) -> str:
    label = "ready/valid" if protocol.kind == "ready_valid" else "request/acknowledge"
    return (
        f"Verify {protocol.name} {label} transfers occur only when {protocol.valid} and {protocol.ready} are asserted."
    )


def _matching_ports(module: RTLModule, statement: str, suffixes: tuple[str, ...]) -> tuple[str, ...]:
    direction = "output" if suffixes == ("_o", "_out") else "input"
    if module.port_details:
        return tuple(
            port.name for port in module.port_details if port.direction == direction and port.name.lower() in statement
        )
    return tuple(port for port in module.ports if port.lower() in statement and port.endswith(suffixes))


def _mentions_any(statement: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(statement, term) for term in terms)


def _contains_term(statement: str, term: str) -> bool:
    if " " in term:
        return term in statement
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", statement) is not None


def _relevant_requirement_sentences(
    text: str,
    query_terms: tuple[str, ...],
    limit: int = 5,
) -> tuple[tuple[str, int, int], ...]:
    candidates: list[tuple[int, int, str, int, int]] = []
    normalized_terms = tuple(term.lower() for term in query_terms if term)
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+|\n\s*\n", text):
        raw = text[start : match.start()]
        stripped = raw.strip()
        if stripped:
            local_start = start + len(raw) - len(raw.lstrip())
            local_end = local_start + len(stripped)
            score = sum(1 for term in normalized_terms if _contains_term(stripped.lower(), term))
            candidates.append((score, len(candidates), stripped, local_start, local_end))
        start = match.end()
    raw = text[start:]
    stripped = raw.strip()
    if stripped:
        local_start = start + len(raw) - len(raw.lstrip())
        candidates.append(
            (
                sum(1 for term in normalized_terms if _contains_term(stripped.lower(), term)),
                len(candidates),
                stripped,
                local_start,
                local_start + len(stripped),
            )
        )
    relevant = [candidate for candidate in candidates if candidate[0] > 0]
    maximum_score = max((candidate[0] for candidate in relevant), default=0)
    threshold = max(1, maximum_score - 1)
    relevant = [candidate for candidate in relevant if candidate[0] >= threshold]
    selected = sorted(sorted(relevant, key=lambda item: (-item[0], item[1]))[:limit], key=lambda item: item[1])
    return tuple((sentence, local_start, local_end) for _score, _index, sentence, local_start, local_end in selected)


def _walk_expressions(expressions: tuple[RTLExpression, ...]) -> tuple[RTLExpression, ...]:
    return tuple(expression for root in expressions for expression in (root, *_walk_expressions(root.children)))


def _canonical_requirement(statement: str) -> str:
    normalized = statement.lower().replace("’", "'")
    normalized = re.sub(r"\b(?:the\s+)?(?:module|design|dut)\b", " ", normalized)
    normalized = re.sub(r"\b(?:shall|must|should|will)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9_']+", " ", normalized)
    return " ".join(normalized.split())


def _requirement_category(statement: str) -> str:
    normalized = statement.lower()
    categories = (
        ("reset", ("reset", "resets", "clear", "clears", "cleared", "active-high", "active-low")),
        ("increment", ("increment", "increments", "increase", "increases")),
        ("hold", ("hold", "holds", "stable", "unchanged")),
        ("latency", ("latency", "cycle", "cycles", "within")),
        ("error", ("error", "fault", "invalid", "overflow", "underflow")),
        ("ordering", ("order", "ordering", "before", "after")),
        ("performance", ("throughput", "bandwidth", "performance")),
        ("power", ("power", "sleep", "retention", "isolation")),
        ("debug", ("debug", "observe", "observable", "trace")),
        ("coverage", ("coverage", "coverpoint", "cross")),
        ("protocol", ("protocol", "transaction", "transfer", "handshake", "valid", "ready", "backpressure")),
        ("connectivity", ("connect", "route", "forward", "mirror", "reflect", "wrapper")),
    )
    return next((category for category, terms in categories if _mentions_any(normalized, terms)), "general")


def _requirement_expected_value(statement: str, category: str) -> str | None:
    normalized = statement.lower().replace("’", "'")
    if category == "reset":
        match = re.search(
            r"(?:to|value(?:\s+of)?|becomes?)\s+(zero|one|0|1|'0|'1|\d+'[s]?[bhd][0-9a-f_xz]+)",
            normalized,
        )
        if match:
            value = match.group(1)
            return {"zero": "0", "one": "1", "'0": "0", "'1": "1"}.get(value, value)
        if "active-high" in normalized or "active high" in normalized:
            return "active_high"
        if "active-low" in normalized or "active low" in normalized:
            return "active_low"
    if category == "latency":
        match = re.search(r"(?:within|after|latency(?:\s+of)?|in)\s+(\d+)\s+cycles?", normalized)
        if match:
            return f"{match.group(1)} cycles"
    if category == "increment":
        match = re.search(r"(?:increment|increase)(?:s|ed)?(?:\s+\w+){0,2}\s+by\s+(\d+)", normalized)
        return match.group(1) if match else "1"
    if category == "hold":
        return "stable"
    return None


def _requirement_condition(module: RTLModule, statement: str) -> str | None:
    normalized = statement.lower()
    candidates = (*module.resets, *(port.name for port in module.port_details if port.direction == "input"))
    return next((name for name in dict.fromkeys(candidates) if _contains_term(normalized, name.lower())), None)


def _requirement_summary(
    text: str,
    query_terms: tuple[str, ...] = (),
    max_chars: int = 500,
) -> str:
    sentences = tuple(sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n\s*\n", text) if sentence.strip())
    normalized_terms = tuple(term.lower() for term in query_terms if term)
    scored = tuple(
        (index, sentence, sum(1 for term in normalized_terms if term in sentence.lower()))
        for index, sentence in enumerate(sentences)
    )
    maximum_score = max((score for _index, _sentence, score in scored), default=0)
    threshold = max(1, maximum_score - 1)
    selected_indexes = sorted(index for index, _sentence, score in scored if score >= threshold)[:3]
    summary = " ".join(sentences[index] for index in selected_indexes) if selected_indexes else " ".join(text.split())
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."
