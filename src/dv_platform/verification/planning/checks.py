# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

import hashlib
import re

from dv_platform.agent.protocols import RegisterModel
from dv_platform.core.models import (
    ClaimType,
    EvidenceRef,
    RTLClock,
    RTLModule,
    RTLPort,
    RTLProtocol,
    RTLReset,
    Severity,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationRequirement,
    VerificationTarget,
)
from dv_platform.verification.planning.claims import (
    check_requirement_behavior_claim,
)


def _build_check_details(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
    checks: tuple[str, ...],
    requirements: tuple[VerificationRequirement, ...],
    behaviors: tuple[VerificationBehavior, ...],
    register_models: tuple[RegisterModel, ...] = (),
) -> tuple[VerificationCheck, ...]:
    """Give every human-readable check a stable identity and precise evidence."""

    details: list[VerificationCheck] = []
    observable_outputs = {port.name for port in module.port_details if port.direction == "output"}
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
            evidence_refs = _check_structural_evidence(module, category, normalized, register_models)
        identity = "|".join((module.name, category, " ".join(normalized.split())))
        check_id = f"{module.name}:check:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"
        details.append(
            VerificationCheck(
                check_id=check_id,
                statement=statement,
                category=category,
                executable=_check_is_executable(
                    category,
                    normalized,
                    matched_requirements,
                    matched_behaviors,
                    targets,
                    all(behavior.target in observable_outputs for behavior in matched_behaviors),
                ),
                evidence_refs=evidence_refs,
            )
        )
    return tuple(details)


def _check_category(statement: str) -> str:
    categories = (
        ("cdc", ("cdc path", "synchronizer")),
        ("formal", ("formal contract", "assumption consistency", "induction invariant")),
        ("memory", ("memory ", "read-during-write")),
        ("register_access", ("apb4 register", "axi4-lite register")),
        (
            "protocol",
            (
                "ready/valid",
                "backpressure",
                "without corruption",
                "transfers complete",
                "ordering rules",
                "response and error behavior",
                "uart ",
                "spi ",
                "i2c ",
                "gpio ",
                "timer ",
                "watchdog ",
                "pwm ",
                "interrupt controller ",
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
    observable_behaviors: bool = True,
) -> bool:
    if behaviors and not observable_behaviors:
        return False
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


def _check_structural_evidence(
    module: RTLModule,
    category: str,
    statement: str,
    register_models: tuple[RegisterModel, ...] = (),
) -> tuple[EvidenceRef, ...]:
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
    if category == "register_access":
        return tuple(
            ref for register in register_models if register.name.lower() in statement for ref in register.evidence_refs
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
