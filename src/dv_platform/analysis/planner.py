"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

from dv_platform.core.models import (
    ClaimStatus,
    RTLModule,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)


def create_initial_plan(
    module: RTLModule,
    targets: tuple[VerificationTarget, ...],
) -> VerificationPlan:
    """Create a minimal verification plan from extracted module metadata."""

    checks: list[str] = []
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

    return VerificationPlan(
        module=module.name,
        targets=targets,
        claims=tuple(claims),
        checks=tuple(checks),
        assumptions=tuple(assumptions),
        open_questions=tuple(open_questions),
    )
