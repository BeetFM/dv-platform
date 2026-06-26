"""Claim status transitions and validation policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import json
from pathlib import Path
import re

from dv_platform.core.models import ClaimStatus, EvidenceKind, EvidenceRef, RTLModule, Severity, VerificationClaim, VerificationRequirement


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


def check_module_ports_claim(claim: VerificationClaim, module: RTLModule) -> VerificationClaim:
    """Check that extracted module ports have RTL evidence and valid directions when available."""

    if not module.ports:
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE)

    port_refs = _port_evidence_refs(module)
    if module.port_details:
        known_detail_names = {port.name for port in module.port_details}
        if any(port not in known_detail_names for port in module.ports):
            return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, port_refs or claim.evidence_refs)
        invalid_directions = tuple(
            port for port in module.port_details if port.direction not in {"input", "output", "inout", "ref"}
        )
        if invalid_directions:
            return with_claim_status(claim, ClaimStatus.CONTRADICTED, port_refs or claim.evidence_refs)
        return _supported_if_evidence(claim, port_refs)

    return _supported_if_evidence(claim, claim.evidence_refs or module.ast_refs)


def check_port_claim(
    claim: VerificationClaim,
    module: RTLModule,
    port_name: str,
    direction: str | None = None,
    width: int | None = None,
) -> VerificationClaim:
    """Check one port claim against structured RTL port facts."""

    detail = next((port for port in module.port_details if port.name == port_name), None)
    refs = _port_evidence_refs(module, port_name) or claim.evidence_refs
    if detail is None:
        if port_name in module.ports and direction is None and width is None:
            return _supported_if_evidence(claim, refs or module.ast_refs)
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, refs)
    if direction is not None and detail.direction != direction:
        return with_claim_status(claim, ClaimStatus.CONTRADICTED, refs)
    if width is not None and detail.width != width:
        return with_claim_status(claim, ClaimStatus.CONTRADICTED, refs)
    return _supported_if_evidence(claim, refs)


def check_clock_claim(claim: VerificationClaim, module: RTLModule, clock_name: str | None = None) -> VerificationClaim:
    """Check that one or more clock inputs are classified from RTL facts."""

    clocks = tuple(clock for clock in module.clock_details if clock_name is None or clock.name == clock_name)
    if clocks:
        if any(clock.direction != "input" for clock in clocks):
            return with_claim_status(claim, ClaimStatus.CONTRADICTED, _port_evidence_refs(module, clock_name))
        refs = tuple(ref for clock in clocks for ref in _port_evidence_refs(module, clock.name))
        return _supported_if_evidence(claim, refs or claim.evidence_refs)

    if clock_name is None and module.clocks:
        return _supported_if_evidence(claim, claim.evidence_refs or module.ast_refs)
    if clock_name is not None and clock_name in module.clocks:
        return _supported_if_evidence(claim, _port_evidence_refs(module, clock_name) or claim.evidence_refs or module.ast_refs)
    return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, claim.evidence_refs)


def check_reset_claim(
    claim: VerificationClaim,
    module: RTLModule,
    reset_name: str | None = None,
    active_low: bool | None = None,
) -> VerificationClaim:
    """Check that one or more reset inputs are classified from RTL facts."""

    resets = tuple(reset for reset in module.reset_details if reset_name is None or reset.name == reset_name)
    if resets:
        if any(reset.direction != "input" for reset in resets):
            return with_claim_status(claim, ClaimStatus.CONTRADICTED, _port_evidence_refs(module, reset_name))
        if active_low is not None and any(reset.active_low != active_low for reset in resets):
            return with_claim_status(claim, ClaimStatus.CONTRADICTED, _port_evidence_refs(module, reset_name))
        refs = tuple(ref for reset in resets for ref in _port_evidence_refs(module, reset.name))
        return _supported_if_evidence(claim, refs or claim.evidence_refs)

    if reset_name is None and module.resets:
        return _supported_if_evidence(claim, claim.evidence_refs or module.ast_refs)
    if reset_name is not None and reset_name in module.resets:
        return _supported_if_evidence(claim, _port_evidence_refs(module, reset_name) or claim.evidence_refs or module.ast_refs)
    return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, claim.evidence_refs)


def check_requirement_signal_refs_claim(
    claim: VerificationClaim,
    requirement: VerificationRequirement,
    module: RTLModule,
) -> VerificationClaim:
    """Check that signal-like requirement references resolve to known module interface signals."""

    known_signals = set(module.ports) | set(module.clocks) | set(module.resets)
    referenced_signals = _referenced_known_signal_tokens(requirement.statement, known_signals)
    if not referenced_signals:
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, requirement.evidence_refs or claim.evidence_refs)

    refs = tuple(ref for signal in referenced_signals for ref in _port_evidence_refs(module, signal))
    if refs:
        return with_claim_status(claim, ClaimStatus.SUPPORTED, _unique_refs((*requirement.evidence_refs, *refs)))
    if module.ast_refs:
        return with_claim_status(claim, ClaimStatus.SUPPORTED, _unique_refs((*requirement.evidence_refs, *module.ast_refs)))
    return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, requirement.evidence_refs or claim.evidence_refs)


def check_requirement_behavior_claim(
    claim: VerificationClaim,
    requirement: VerificationRequirement,
    module: RTLModule,
) -> VerificationClaim:
    """Check requirement behavior against detected procedural RTL patterns when applicable."""

    statement = requirement.statement.lower()
    if _mentions_any(statement, ("clear", "clears", "cleared", "reset", "zero")):
        matched = _matching_patterns(module, "reset_to_constant", requirement.statement)
        if matched:
            return with_claim_status(claim, ClaimStatus.SUPPORTED, _unique_refs((*requirement.evidence_refs, *_pattern_refs(module))))
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, requirement.evidence_refs or claim.evidence_refs)

    if _mentions_any(statement, ("increment", "increments", "increase", "increases")):
        matched = _matching_patterns(module, "increment", requirement.statement)
        if matched:
            return with_claim_status(claim, ClaimStatus.SUPPORTED, _unique_refs((*requirement.evidence_refs, *_pattern_refs(module))))
        return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE, requirement.evidence_refs or claim.evidence_refs)

    return check_requirement_signal_refs_claim(claim, requirement, module)


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


def _supported_if_evidence(claim: VerificationClaim, evidence_refs: tuple[EvidenceRef, ...]) -> VerificationClaim:
    if evidence_refs:
        return with_claim_status(claim, ClaimStatus.SUPPORTED, evidence_refs)
    return with_claim_status(claim, ClaimStatus.MISSING_EVIDENCE)


def _port_evidence_refs(module: RTLModule, port_name: str | None = None) -> tuple[EvidenceRef, ...]:
    prefix = f"port:{module.name}."
    refs: list[EvidenceRef] = []
    for ref in module.ast_refs:
        locator = ref.locator.split("@", 1)[0]
        if port_name is None:
            if locator.startswith(prefix):
                refs.append(ref)
        elif locator == f"{prefix}{port_name}":
            refs.append(ref)
    return tuple(refs)


def _referenced_known_signal_tokens(statement: str, known_signals: set[str]) -> tuple[str, ...]:
    tokens = tuple(match.group(0) for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", statement))
    return tuple(signal for signal in sorted(known_signals) if signal in tokens)


def _matching_patterns(module: RTLModule, kind: str, statement: str) -> tuple[object, ...]:
    tokens = set(match.group(0) for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", statement))
    patterns = tuple(pattern for block in module.procedural_block_details for pattern in block.patterns if pattern.kind == kind)
    return tuple(
        pattern
        for pattern in patterns
        if pattern.target in tokens and (pattern.control is None or pattern.control in tokens)
    )


def _pattern_refs(module: RTLModule) -> tuple[EvidenceRef, ...]:
    procedure_refs = tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].startswith(f"procedure:{module.name}."))
    return procedure_refs or module.ast_refs


def _mentions_any(statement: str, terms: tuple[str, ...]) -> bool:
    return any(term in statement for term in terms)


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _escape_markdown_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
