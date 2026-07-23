# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

from dataclasses import replace

from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)


def _reset_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    check_ids = _check_ids(plan, "reset")
    if not check_ids:
        return []
    result: list[VerificationScenario] = []
    policies = {
        policy.subject: policy
        for policy in plan.depth_policies
        if policy.kind == "reset"
        and any(
            claim.claim_id.endswith(f":depth-policy:reset:{policy.subject}") and claim.status == ClaimStatus.SUPPORTED
            for claim in plan.claims
        )
    }
    for reset in plan.resets:
        policy = policies.get(reset.name)
        if policy is not None:
            domain = next((item for item in plan.control_domains if item.reset == reset.name), None)
            ready = policy.parameter("ready_signal")
            mapped_checks = tuple(
                check.check_id
                for check in plan.check_details
                if check.category == "reset" and reset.name.lower() in check.statement.lower()
            )
            if domain is not None and ready and mapped_checks:
                kind = "reset_domain_sequence"
                target_states = _qualified_target_states(
                    kind,
                    plan.targets,
                    True,
                    "reset-domain scenario lacks a qualified policy, observable ready signal, or mapped check",
                )
                targets = _executable_targets(target_states)
                parameters = tuple(
                    sorted(
                        {
                            **dict(policy.parameters),
                            "reset": reset.name,
                            "clock": domain.clock,
                            "reset_active_low": str(reset.active_low).lower(),
                        }.items()
                    )
                )
                dependency_reset = policy.parameter("depends_on_reset")
                if dependency_reset:
                    dependency_domain = next(
                        (item for item in plan.control_domains if item.reset == dependency_reset), None
                    )
                    dependency_detail = next((item for item in plan.resets if item.name == dependency_reset), None)
                    if dependency_domain is None or dependency_detail is None:
                        continue
                    parameters = tuple(
                        sorted(
                            (
                                *parameters,
                                ("dependency_clock", dependency_domain.clock),
                                ("dependency_reset_active_low", str(dependency_detail.active_low).lower()),
                            )
                        )
                    )
                evidence = tuple(
                    dict.fromkeys(
                        (
                            *(
                                ref
                                for claim in plan.claims
                                if claim.claim_id.endswith((":reset", f":depth-policy:reset:{reset.name}"))
                                for ref in claim.evidence_refs
                            ),
                            EvidenceRef(
                                EvidenceKind.CONFIGURATION,
                                "dv-platform.toml",
                                f"verification_depth:reset/{plan.module}/{reset.name}",
                                "Qualified reset-domain release and dependency intent.",
                            ),
                        )
                    )
                )
                result.append(
                    VerificationScenario(
                        scenario_id=_scenario_id(plan.module, kind, reset.name),
                        kind=kind,
                        stimulus=(
                            ScenarioStimulus("reset_domain_profile", parameters=parameters),
                            ScenarioStimulus("asynchronous_assert", reset.name),
                            ScenarioStimulus("clocked_release", reset.name),
                        ),
                        oracle=ScenarioOracle("reset_ready", ready, "1"),
                        completion=ScenarioCompletion(
                            "bounded_cycles",
                            ready,
                            "1",
                            int(policy.parameter("release_cycles") or "2")
                            + int(policy.parameter("recovery_cycles") or "1")
                            + (10 if policy.parameter("depends_on_reset") else 6),
                        ),
                        coverage_goals=(
                            ScenarioCoverageGoal(
                                f"{plan.module}:coverage:reset-domain:{reset.name}",
                                "reset_domain",
                                (
                                    "async-assert",
                                    "clocked-release",
                                    "ordered-release",
                                    *(
                                        ("power-good-hold", "isolation", "retention")
                                        if policy.parameter("power_good_signal")
                                        else ()
                                    ),
                                    "recovery",
                                    "removal",
                                    "non-vacuous",
                                ),
                            ),
                        ),
                        supported_targets=targets,
                        target_states=target_states,
                        check_ids=mapped_checks,
                        evidence_refs=evidence,
                        executable=bool(targets),
                    )
                )
                continue
        reset_behaviors = tuple(
            behavior
            for behavior in plan.behaviors
            if behavior.kind == "reset_to_constant" and behavior.control == reset.name and behavior.value is not None
        )
        mapped_reset_checks = tuple(
            check.check_id
            for check in plan.check_details
            if check.category == "reset"
            and any(behavior.target.lower() in check.statement.lower() for behavior in reset_behaviors)
        )
        target_states = _qualified_target_states(
            "reset_sequence",
            plan.targets,
            bool(reset_behaviors and mapped_reset_checks),
            "native reset execution requires a normalized reset-to-constant behavior and mapped check",
        )
        observable_ports = {port.name for port in plan.ports}
        if VerificationTarget.VHDL in plan.targets and not all(
            behavior.target in observable_ports for behavior in reset_behaviors
        ):
            target_states = tuple(
                replace(
                    support,
                    state=ScenarioTargetState.SCAFFOLD,
                    reason="VHDL reset execution requires every checked target to be an observable entity port",
                )
                if support.target == VerificationTarget.VHDL and support.state == ScenarioTargetState.EXECUTABLE
                else support
                for support in target_states
            )
        targets = _executable_targets(target_states)
        asserted = "0" if reset.active_low else "1"
        deasserted = "1" if reset.active_low else "0"
        evidence = tuple(
            ref for claim in plan.claims if claim.claim_id.endswith(":reset") for ref in claim.evidence_refs
        )
        result.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, "reset_sequence", reset.name),
                kind="reset_sequence",
                stimulus=(
                    ScenarioStimulus("drive", reset.name, asserted),
                    ScenarioStimulus("hold_cycles", parameters=(("cycles", "2"),)),
                    ScenarioStimulus("drive", reset.name, deasserted),
                ),
                oracle=ScenarioOracle(
                    "reset_behavior",
                    reset_behaviors[0].target if reset_behaviors else None,
                    reset_behaviors[0].value if reset_behaviors else None,
                ),
                completion=ScenarioCompletion("cycles", timeout_cycles=8),
                coverage_goals=(ScenarioCoverageGoal(f"{plan.module}:coverage:reset:{reset.name}", "reset_sequence"),),
                supported_targets=targets,
                target_states=target_states,
                check_ids=mapped_reset_checks or check_ids,
                evidence_refs=evidence,
                executable=(
                    reset.active_low is not None
                    and bool(targets)
                    and bool(evidence)
                    and bool(reset_behaviors)
                    and bool(mapped_reset_checks)
                ),
            )
        )
    return result
