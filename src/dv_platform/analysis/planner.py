"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLPort,
    Severity,
    VerificationBehavior,
    VerificationClaim,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)
from dv_platform.analysis.claims import (
    check_clock_claim,
    check_module_ports_claim,
    check_requirement_behavior_claim,
    check_requirement_signal_refs_claim,
    check_reset_claim,
)
from dv_platform.analysis.docs import retrieve_chunks, retrieve_chunks_with_vectors


def create_initial_plan(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
    documentation_chunks: tuple[DocumentationChunk, ...] = (),
    retrieval_index_dir: Path | None = None,
) -> VerificationPlan:
    """Create a minimal verification plan from extracted module metadata."""

    checks: list[str] = []
    requirements: list[str] = []
    assumptions: list[str] = []
    open_questions: list[str] = []
    claims: list[VerificationClaim] = []
    structured_requirements: tuple[VerificationRequirement, ...] = ()
    behaviors = _behaviors_from_patterns(module)

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

    documentation_refs = _retrieve_documentation_refs(module, documentation_chunks, retrieval_index_dir)
    if documentation_refs:
        structured_requirements = _synthesize_requirements(module, documentation_refs)
        requirements.extend(requirement.statement for requirement in structured_requirements)
        requirement_checks, requirement_claims = _requirement_driven_checks(module, structured_requirements)
        checks.extend(requirement_checks)
        claims.extend(requirement_claims)
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

    return VerificationPlan(
        module=module.name,
        targets=targets,
        ports=_plan_ports(module),
        requirements=tuple(requirements),
        structured_requirements=structured_requirements,
        behaviors=behaviors,
        claims=tuple(claims),
        checks=tuple(checks),
        assumptions=tuple(assumptions),
        open_questions=tuple(open_questions),
    )


def _plan_ports(module: RTLModule) -> tuple[RTLPort, ...]:
    if module.port_details:
        return module.port_details
    return tuple(RTLPort(name=port, direction="unknown") for port in module.ports)


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
        locator = f"chunk:{chunk.chunk_id}"
        if chunk.start_offset is not None and chunk.end_offset is not None:
            locator = f"{locator}@{chunk.start_offset}:{chunk.end_offset}"
        refs.append(
            EvidenceRef(
                kind=EvidenceKind.DOCUMENT_CHUNK,
                source_id=str(chunk.source),
                locator=locator,
                summary=_requirement_summary(chunk.text),
            )
        )
    return tuple(refs)


def _synthesize_requirements(
    module: RTLModule,
    documentation_refs: tuple[EvidenceRef, ...],
) -> tuple[VerificationRequirement, ...]:
    requirements: list[VerificationRequirement] = []
    for index, ref in enumerate(documentation_refs, start=1):
        statement = ref.summary or ref.locator
        requirements.append(
            VerificationRequirement(
                requirement_id=f"{module.name}:docreq:{index}",
                scope=module.name,
                statement=statement,
                evidence_refs=(ref,),
            )
        )
    return tuple(requirements)


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
    procedure_refs = tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].startswith(f"procedure:{module.name}."))
    return procedure_refs or module.ast_refs


def _checks_for_behaviors(behaviors: tuple[VerificationBehavior, ...]) -> tuple[str, ...]:
    checks: list[str] = []
    for behavior in behaviors:
        if behavior.kind == "reset_to_constant" and behavior.control and behavior.value is not None:
            checks.append(f"Verify RTL reset pattern drives {behavior.target} to {behavior.value} when {behavior.control} is active.")
        elif behavior.kind == "increment" and behavior.control:
            checks.append(f"Verify RTL increment pattern updates {behavior.target} when {behavior.control} is asserted.")
    return tuple(checks)


def _checks_for_requirement(module: RTLModule, statement: str) -> tuple[str, ...]:
    checks: list[str] = []
    output_ports = _matching_ports(module, statement, suffixes=("_o", "_out"))
    input_ports = _matching_ports(module, statement, suffixes=("_i", "_in"))
    reset_names = tuple(reset for reset in module.resets if reset.lower() in statement)

    if output_ports and reset_names and _mentions_any(statement, ("clear", "clears", "cleared", "zero", "reset")):
        for output in output_ports:
            for reset in reset_names:
                checks.append(f"Verify {reset} drives {output} to its documented reset value.")

    if output_ports and input_ports and _mentions_any(statement, ("increment", "increments", "increase", "increases")):
        for output in output_ports:
            for input_name in input_ports:
                checks.append(f"Verify {output} increments when {input_name} is asserted.")

    if output_ports and input_ports and _mentions_any(statement, ("hold", "holds", "stable", "unchanged")):
        for output in output_ports:
            for input_name in input_ports:
                checks.append(f"Verify {output} remains stable when {input_name} is inactive.")

    return tuple(checks)


def _matching_ports(module: RTLModule, statement: str, suffixes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(port for port in module.ports if port.lower() in statement and port.endswith(suffixes))


def _mentions_any(statement: str, terms: tuple[str, ...]) -> bool:
    return any(term in statement for term in terms)


def _requirement_summary(text: str, max_chars: int = 160) -> str:
    summary = " ".join(text.split())
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."
