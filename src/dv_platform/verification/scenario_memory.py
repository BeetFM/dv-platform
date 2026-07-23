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


def _memory_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    """Build executable intent only for the qualified bounded SRAM profile."""

    supported_subjects = {
        claim.claim_id.rsplit(":", 1)[-1]
        for claim in plan.claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:memory:" in claim.claim_id
    }
    memories = {memory.name: memory for memory in plan.memories}
    scenarios: list[VerificationScenario] = []
    for policy in plan.depth_policies:
        if (
            policy.kind != "memory"
            or policy.parameter("profile") != "bounded_sram"
            or policy.subject not in supported_subjects
            or policy.subject not in memories
        ):
            continue
        memory = memories[policy.subject]
        if memory.depth is None or memory.element_width is None:
            continue
        domain = next(
            (
                item
                for item in plan.control_domains
                if item.clock == policy.parameter("clock") and item.reset == policy.parameter("reset")
            ),
            None,
        )
        if domain is None:
            continue
        check_ids = tuple(
            check.check_id
            for check in plan.check_details
            if check.category == "memory" and policy.subject.lower() in check.statement.lower()
        )
        if not check_ids:
            continue
        kind = "memory_bounded_sram"
        target_states = _qualified_target_states(
            kind,
            plan.targets,
            True,
            "memory lacks the qualified bounded SRAM policy or normalized synchronous accesses",
        )
        targets = _executable_targets(target_states)
        parameters = tuple(
            sorted(
                {
                    **dict(policy.parameters),
                    "memory": policy.subject,
                    "depth": str(memory.depth),
                    "data_width": str(memory.element_width),
                    "byte_lanes": str(memory.element_width // 8),
                    "reset_active_low": str(domain.reset_active_low).lower(),
                }.items()
            )
        )
        config_ref = EvidenceRef(
            EvidenceKind.CONFIGURATION,
            "dv-platform.toml",
            f"verification_depth:memory/{plan.module}/{policy.subject}",
            "Qualified bounded SRAM intent.",
        )
        protection_bins = (
            ("single-error-corrected", "double-error-detected", "scrub-repair")
            if policy.parameter("protection") == "secded"
            else ("parity-clean", "parity-error")
        )
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, kind, policy.subject),
                kind=kind,
                stimulus=(ScenarioStimulus("bounded_sram_profile", parameters=parameters),),
                oracle=ScenarioOracle("memory_scoreboard", policy.parameter("read_data"), "reference contents"),
                completion=ScenarioCompletion(
                    "bounded_cycles",
                    policy.parameter("port0_grant"),
                    "1",
                    int(policy.parameter("max_latency_cycles") or "16"),
                ),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:bounded-sram:{policy.subject}",
                        "memory",
                        (
                            "zero-initialization",
                            "low-address",
                            "high-address",
                            "byte-lane-merge",
                            "read-during-write",
                            "port0-grant",
                            "port1-grant",
                            "simultaneous-request",
                            "round-robin",
                            *protection_bins,
                            "reset-recovery",
                            "non-vacuous",
                        ),
                    ),
                ),
                supported_targets=targets,
                target_states=target_states,
                check_ids=check_ids,
                evidence_refs=(config_ref,),
                executable=bool(targets),
            )
        )
    return scenarios
