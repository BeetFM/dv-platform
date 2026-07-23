# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    VerificationPlan,
    VerificationScenario,
)


def _formal_contract_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    supported = {
        claim.claim_id.rsplit(":", 1)[-1]
        for claim in plan.claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:formal:" in claim.claim_id
    }
    scenarios: list[VerificationScenario] = []
    for policy in plan.depth_policies:
        if (
            policy.kind != "formal"
            or policy.parameter("profile") != "bounded_response"
            or policy.subject not in supported
        ):
            continue
        check_ids = tuple(
            check.check_id
            for check in plan.check_details
            if check.category == "formal" and policy.subject.lower() in check.statement.lower()
        )
        if not check_ids:
            continue
        kind = "formal_bounded_response"
        target_states = _qualified_target_states(
            kind,
            plan.targets,
            True,
            "formal contract lacks a qualified bounded-response policy or mapped checks",
        )
        targets = _executable_targets(target_states)
        parameters = tuple(sorted({**dict(policy.parameters), "contract": policy.subject}.items()))
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, kind, policy.subject),
                kind=kind,
                stimulus=(ScenarioStimulus("formal_contract_profile", parameters=parameters),),
                oracle=ScenarioOracle("bounded_response", policy.parameter("response_signal"), "causal response"),
                completion=ScenarioCompletion(
                    "bounded_cycles",
                    policy.parameter("response_signal"),
                    "1",
                    int(policy.parameter("max_latency_cycles") or "4"),
                ),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:formal-contract:{policy.subject}",
                        "formal",
                        (
                            "assumption-witness",
                            "trigger",
                            "response",
                            "bounded-liveness",
                            "causality",
                            "induction-invariant",
                            "non-vacuous",
                        ),
                    ),
                ),
                supported_targets=targets,
                target_states=target_states,
                check_ids=check_ids,
                evidence_refs=(
                    EvidenceRef(
                        EvidenceKind.CONFIGURATION,
                        "dv-platform.toml",
                        f"verification_depth:formal/{plan.module}/{policy.subject}",
                        "Qualified bounded-response formal intent.",
                    ),
                ),
                executable=bool(targets),
            )
        )
    return scenarios
