"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    Severity,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.analysis.docs import retrieve_chunks


def create_initial_plan(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
    documentation_chunks: tuple[DocumentationChunk, ...] = (),
) -> VerificationPlan:
    """Create a minimal verification plan from extracted module metadata."""

    checks: list[str] = []
    requirements: list[str] = []
    assumptions: list[str] = []
    open_questions: list[str] = []
    claims: list[VerificationClaim] = []

    if module.clocks:
        checks.append("Drive declared clock inputs with stable periods.")
        claims.append(
            VerificationClaim(
                claim_id=f"{module.name}:clocking",
                scope=module.name,
                statement="The module has one or more clock inputs.",
                claim_type=ClaimType.RTL_STRUCTURE,
                severity=Severity.HIGH,
                generation_precondition=True,
                status=ClaimStatus.SUPPORTED if module.ast_refs else ClaimStatus.UNCHECKED,
                evidence_refs=module.ast_refs,
            )
        )
    else:
        open_questions.append("No clock signal was identified.")

    if module.resets:
        checks.append("Exercise reset assertion and deassertion sequencing.")
        claims.append(
            VerificationClaim(
                claim_id=f"{module.name}:reset",
                scope=module.name,
                statement="The module has one or more reset inputs.",
                claim_type=ClaimType.RTL_STRUCTURE,
                severity=Severity.MEDIUM,
                generation_precondition=True,
                status=ClaimStatus.SUPPORTED if module.ast_refs else ClaimStatus.UNCHECKED,
                evidence_refs=module.ast_refs,
            )
        )
    else:
        assumptions.append("Module may be combinational or resetless.")

    if module.ports:
        checks.append("Generate basic input/output connectivity checks.")
    else:
        open_questions.append("No ports were extracted for this module.")

    documentation_refs = _retrieve_documentation_refs(module, documentation_chunks)
    if documentation_refs:
        requirements.extend(ref.summary or ref.locator for ref in documentation_refs)
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

    return VerificationPlan(
        module=module.name,
        targets=targets,
        requirements=tuple(requirements),
        claims=tuple(claims),
        checks=tuple(checks),
        assumptions=tuple(assumptions),
        open_questions=tuple(open_questions),
    )


def _retrieve_documentation_refs(
    module: RTLModule,
    documentation_chunks: tuple[DocumentationChunk, ...],
) -> tuple[EvidenceRef, ...]:
    if not documentation_chunks:
        return ()

    query = " ".join((module.name, *module.ports, *module.parameters, *module.instances))
    results = retrieve_chunks(query, documentation_chunks, limit=3)
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


def _requirement_summary(text: str, max_chars: int = 160) -> str:
    summary = " ".join(text.split())
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."
