"""Claim status transitions and validation policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import json
from pathlib import Path

from dv_platform.core.models import ClaimStatus, EvidenceKind, EvidenceRef, Severity, VerificationClaim


class ClaimAction(StrEnum):
    """Policy action produced by claim validation."""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    ANNOTATE = "annotate"


@dataclass(frozen=True)
class ClaimValidation:
    """Policy decision for one verification claim."""

    claim: VerificationClaim
    action: ClaimAction
    reason: str


@dataclass(frozen=True)
class GenerationGate:
    """Aggregated generation-gating decision for a claim set."""

    allowed: bool
    validations: tuple[ClaimValidation, ...]
    blocked: tuple[ClaimValidation, ...]
    warnings: tuple[ClaimValidation, ...]


def with_claim_status(
    claim: VerificationClaim,
    status: ClaimStatus,
    evidence_refs: tuple[EvidenceRef, ...] | None = None,
) -> VerificationClaim:
    """Return a copy of a claim with an updated status and optional evidence."""

    if evidence_refs is None:
        return replace(claim, status=status)
    return replace(claim, status=status, evidence_refs=evidence_refs)


def check_claim_evidence(
    claim: VerificationClaim,
    evidence_kind: EvidenceKind,
    available_source_ids: tuple[str, ...] = (),
    contradicted_source_ids: tuple[str, ...] = (),
) -> VerificationClaim:
    """Check a claim against evidence refs of one kind."""

    matching_refs = tuple(ref for ref in claim.evidence_refs if ref.kind == evidence_kind)
    if not matching_refs:
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE)

    contradicted = tuple(ref for ref in matching_refs if ref.source_id in contradicted_source_ids)
    if contradicted:
        return with_claim_status(claim, ClaimStatus.CONTRADICTED, contradicted)

    if available_source_ids:
        supported_refs = tuple(ref for ref in matching_refs if ref.source_id in available_source_ids)
        if supported_refs:
            return with_claim_status(claim, ClaimStatus.SUPPORTED, supported_refs)
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, matching_refs)

    return with_claim_status(claim, ClaimStatus.SUPPORTED, matching_refs)


def check_ast_claim(
    claim: VerificationClaim,
    available_source_ids: tuple[str, ...] = (),
    contradicted_source_ids: tuple[str, ...] = (),
) -> VerificationClaim:
    """Check a claim against Verilator AST evidence refs."""

    return check_claim_evidence(
        claim,
        EvidenceKind.VERILATOR_AST,
        available_source_ids=available_source_ids,
        contradicted_source_ids=contradicted_source_ids,
    )


def check_documentation_claim(
    claim: VerificationClaim,
    available_source_ids: tuple[str, ...] = (),
    contradicted_source_ids: tuple[str, ...] = (),
) -> VerificationClaim:
    """Check a claim against documentation chunk evidence refs."""

    return check_claim_evidence(
        claim,
        EvidenceKind.DOCUMENT_CHUNK,
        available_source_ids=available_source_ids,
        contradicted_source_ids=contradicted_source_ids,
    )


def classify_claim_validation(claim: VerificationClaim, strict: bool = False) -> ClaimValidation:
    """Classify one claim according to the accepted generation-gating policy."""

    if claim.status == ClaimStatus.SUPPORTED:
        return ClaimValidation(claim=claim, action=ClaimAction.ALLOW, reason="claim is supported")

    if claim.severity == Severity.CRITICAL:
        return ClaimValidation(
            claim=claim,
            action=ClaimAction.BLOCK,
            reason=f"critical claim is {claim.status}",
        )

    if claim.severity == Severity.HIGH:
        if claim.status == ClaimStatus.CONTRADICTED:
            return ClaimValidation(
                claim=claim,
                action=ClaimAction.BLOCK,
                reason="high-severity claim is contradicted",
            )
        if strict:
            return ClaimValidation(
                claim=claim,
                action=ClaimAction.BLOCK,
                reason=f"strict mode blocks high-severity {claim.status} claims",
            )
        return ClaimValidation(
            claim=claim,
            action=ClaimAction.WARN,
            reason=f"high-severity claim is {claim.status}",
        )

    if claim.severity == Severity.MEDIUM:
        if claim.generation_precondition:
            return ClaimValidation(
                claim=claim,
                action=ClaimAction.BLOCK,
                reason=f"generation precondition is {claim.status}",
            )
        return ClaimValidation(
            claim=claim,
            action=ClaimAction.WARN,
            reason=f"medium-severity claim is {claim.status}",
        )

    if claim.status == ClaimStatus.CONTRADICTED:
        return ClaimValidation(
            claim=claim,
            action=ClaimAction.WARN,
            reason=f"{claim.severity} claim is contradicted",
        )

    return ClaimValidation(
        claim=claim,
        action=ClaimAction.ANNOTATE,
        reason=f"{claim.severity} claim is {claim.status}",
    )


def classify_claims(
    claims: tuple[VerificationClaim, ...],
    strict: bool = False,
) -> tuple[ClaimValidation, ...]:
    """Classify claims in deterministic order."""

    return tuple(classify_claim_validation(claim, strict=strict) for claim in claims)


def gate_generation(
    claims: tuple[VerificationClaim, ...],
    strict: bool = False,
) -> GenerationGate:
    """Return the generation-gating decision for a set of claims."""

    validations = classify_claims(claims, strict=strict)
    blocked = tuple(validation for validation in validations if validation.action == ClaimAction.BLOCK)
    warnings = tuple(validation for validation in validations if validation.action == ClaimAction.WARN)
    return GenerationGate(
        allowed=not blocked,
        validations=validations,
        blocked=blocked,
        warnings=warnings,
    )


def claim_report_json(gate: GenerationGate) -> str:
    """Serialize a generation gate and claim validations as JSON."""

    payload = {
        "allowed": gate.allowed,
        "blocked_count": len(gate.blocked),
        "warning_count": len(gate.warnings),
        "validations": [_validation_to_json(validation) for validation in gate.validations],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def claim_report_markdown(gate: GenerationGate) -> str:
    """Serialize a generation gate and claim validations as Markdown."""

    lines = [
        "# Claim Report",
        "",
        f"- allowed: {str(gate.allowed).lower()}",
        f"- blocked: {len(gate.blocked)}",
        f"- warnings: {len(gate.warnings)}",
        "",
        "| action | status | severity | claim | reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for validation in gate.validations:
        claim = validation.claim
        lines.append(
            "| "
            + " | ".join(
                (
                    validation.action,
                    claim.status,
                    claim.severity,
                    _escape_markdown_cell(claim.claim_id),
                    _escape_markdown_cell(validation.reason),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_claim_reports(gate: GenerationGate, output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown claim reports to a directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "claims.json"
    markdown_path = output_dir / "claims.md"
    json_path.write_text(claim_report_json(gate), encoding="utf-8")
    markdown_path.write_text(claim_report_markdown(gate), encoding="utf-8")
    return json_path, markdown_path


def _validation_to_json(validation: ClaimValidation) -> dict[str, object]:
    claim = validation.claim
    return {
        "claim_id": claim.claim_id,
        "scope": claim.scope,
        "statement": claim.statement,
        "claim_type": claim.claim_type,
        "severity": claim.severity,
        "generation_precondition": claim.generation_precondition,
        "status": claim.status,
        "action": validation.action,
        "reason": validation.reason,
        "evidence_refs": [
            {
                "kind": ref.kind,
                "source_id": ref.source_id,
                "locator": ref.locator,
                "summary": ref.summary,
            }
            for ref in claim.evidence_refs
        ],
    }


def _escape_markdown_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
