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
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationScenario,
)


def _cdc_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    scenarios: list[VerificationScenario] = []
    policies = {policy.subject: policy for policy in plan.depth_policies if policy.kind == "cdc"}
    scenarios.extend(_async_fifo_scenarios(plan, tuple(policies.values())))
    scenarios.extend(_reconvergent_cdc_scenarios(plan, tuple(policies.values())))
    for path in plan.cdc_paths:
        if (
            path.classification
            not in {
                "two_flop",
                "pulse",
                "toggle",
                "gray",
                "handshake",
                "multi_bit_handshake",
            }
            or not path.safe
        ):
            continue
        policy = policies.get(path.signal)
        if policy is None or not path.stage_signals:
            continue
        output = policy.parameter("output_signal")
        if output != path.stage_signals[-1]:
            continue
        domain = next((item for item in plan.control_domains if item.domain_id == path.destination_domain), None)
        if domain is None or not domain.clock:
            continue
        check_ids = tuple(
            check.check_id
            for check in plan.check_details
            if check.category == "cdc"
            and (
                path.signal.lower() in check.statement.lower()
                or (
                    policy.parameter("structure") in {"handshake", "multi_bit_handshake"}
                    and (policy.parameter("ack_input_signal") or "").lower() in check.statement.lower()
                )
            )
        )
        if not check_ids:
            continue
        structure = policy.parameter("structure") or path.classification
        kind = f"cdc_{structure}"
        target_states = _qualified_target_states(
            kind,
            plan.targets,
            True,
            f"{structure} CDC structure lacks a qualified policy or observable path",
        )
        targets = _executable_targets(target_states)
        parameters = tuple(
            sorted(
                {
                    **dict(policy.parameters),
                    "clock": domain.clock,
                    "reset": domain.reset or "",
                    "reset_active_low": str(domain.reset_active_low).lower(),
                    "source_signal": path.signal,
                    "output_signal": output,
                    "stages": str(path.synchronizer_stages),
                    **(
                        {
                            "data_width": str(
                                next(
                                    port.width
                                    for port in plan.ports
                                    if port.name == path.signal and port.width is not None
                                )
                            )
                        }
                        if structure == "gray"
                        and any(port.name == path.signal and port.width is not None for port in plan.ports)
                        else {}
                    ),
                }.items()
            )
        )
        if structure in {"handshake", "multi_bit_handshake"}:
            ack_input = policy.parameter("ack_input_signal")
            ack_path = next((item for item in plan.cdc_paths if item.signal == ack_input), None)
            ack_domain = next(
                (
                    item
                    for item in plan.control_domains
                    if ack_path is not None and item.domain_id == ack_path.destination_domain
                ),
                None,
            )
            if ack_path is None or ack_domain is None or not ack_domain.clock:
                continue
            parameters = tuple(sorted((*parameters, ("ack_clock", ack_domain.clock))))
        config_ref = EvidenceRef(
            EvidenceKind.CONFIGURATION,
            "dv-platform.toml",
            f"verification_depth:cdc/{plan.module}/{path.signal}",
            f"Qualified {structure} CDC intent.",
        )
        stimulus = [ScenarioStimulus("cdc_profile", parameters=parameters), ScenarioStimulus("drive", path.signal)]
        if structure in {"handshake", "multi_bit_handshake"}:
            stimulus.append(ScenarioStimulus("drive", policy.parameter("ack_input_signal")))
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, kind, path.signal),
                kind=kind,
                stimulus=tuple(stimulus),
                oracle=ScenarioOracle(
                    structure, output, "coherent payload" if structure == "multi_bit_handshake" else "propagated"
                ),
                completion=ScenarioCompletion(
                    "bounded_cycles",
                    output,
                    "1",
                    int(policy.parameter("max_latency_cycles") or str(path.synchronizer_stages + 2)),
                ),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:cdc:{path.signal}",
                        "cdc",
                        ("request", "propagated", "returned-idle", "non-vacuous"),
                    ),
                ),
                supported_targets=targets,
                target_states=target_states,
                check_ids=check_ids,
                evidence_refs=tuple(dict.fromkeys((*path.evidence_refs, config_ref))),
                executable=bool(targets),
            )
        )
    return scenarios


def _reconvergent_cdc_scenarios(
    plan: VerificationPlan, policies: tuple[VerificationDepthPolicy, ...]
) -> list[VerificationScenario]:
    supported_subjects = {
        claim.claim_id.rsplit(":", 1)[-1]
        for claim in plan.claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:cdc:" in claim.claim_id
    }
    scenarios: list[VerificationScenario] = []
    for policy in policies:
        if policy.parameter("structure") != "two_branch_reconvergent" or policy.subject not in supported_subjects:
            continue
        destination = next(
            (domain for domain in plan.control_domains if domain.domain_id == policy.parameter("destination_domain")),
            None,
        )
        if destination is None or not destination.clock:
            continue
        check_ids = tuple(
            check.check_id
            for check in plan.check_details
            if check.category == "cdc"
            and (
                policy.subject.lower() in check.statement.lower()
                or (policy.parameter("reconvergence_signal") or "").lower() in check.statement.lower()
            )
        )
        if not check_ids:
            continue
        kind = "cdc_two_branch_reconvergent"
        target_states = _qualified_target_states(
            kind,
            plan.targets,
            True,
            "reconvergent CDC lacks two qualified branches and a bounded observable destination",
        )
        targets = _executable_targets(target_states)
        parameters = tuple(
            sorted(
                {
                    **dict(policy.parameters),
                    "clock": destination.clock,
                    "reset": destination.reset or "",
                    "reset_active_low": str(destination.reset_active_low).lower(),
                }.items()
            )
        )
        config_ref = EvidenceRef(
            EvidenceKind.CONFIGURATION,
            "dv-platform.toml",
            f"verification_depth:cdc/{plan.module}/{policy.subject}",
            "Qualified bounded two-branch reconvergent CDC intent.",
        )
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, kind, policy.subject),
                kind=kind,
                stimulus=(
                    ScenarioStimulus("reconvergent_cdc_profile", parameters=parameters),
                    ScenarioStimulus("drive_coherent", policy.parameter("branch0_signal")),
                    ScenarioStimulus("drive_coherent", policy.parameter("branch1_signal")),
                ),
                oracle=ScenarioOracle(
                    "coherent_reconvergence",
                    policy.parameter("reconvergence_signal"),
                    "coherent source sample",
                ),
                completion=ScenarioCompletion(
                    "bounded_cycles",
                    policy.parameter("reconvergence_signal"),
                    "1",
                    int(policy.parameter("coherent_arrival_bound") or "1"),
                ),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:cdc-reconvergent:{policy.subject}",
                        "cdc",
                        (
                            "branch0-arrival",
                            "branch1-arrival",
                            "coherent-arrival",
                            "bounded-destination-sample",
                            "returned-idle",
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


def _async_fifo_scenarios(
    plan: VerificationPlan, policies: tuple[VerificationDepthPolicy, ...]
) -> list[VerificationScenario]:
    scenarios: list[VerificationScenario] = []
    supported_subjects = {
        claim.claim_id.rsplit(":", 1)[-1]
        for claim in plan.claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:cdc:" in claim.claim_id
    }
    memories = {memory.name: memory for memory in plan.memories}
    domains = {domain.clock: domain for domain in plan.control_domains}
    for policy in policies:
        if policy.parameter("structure") != "async_fifo":
            continue
        if policy.subject not in supported_subjects or policy.subject not in memories:
            continue
        memory = memories[policy.subject]
        write_domain = domains.get(policy.parameter("write_clock") or "")
        read_domain = domains.get(policy.parameter("read_clock") or "")
        if write_domain is None or read_domain is None or memory.depth is None or memory.element_width is None:
            continue
        check_ids = tuple(
            check.check_id
            for check in plan.check_details
            if (
                policy.subject.lower() in check.statement.lower()
                or any(
                    (policy.parameter(name) or "").lower() in check.statement.lower()
                    for name in ("write_gray_pointer", "read_gray_pointer")
                )
            )
            and check.category in {"cdc", "memory"}
        )
        if not check_ids:
            continue
        kind = "cdc_async_fifo"
        target_states = _qualified_target_states(
            kind,
            plan.targets,
            True,
            "async FIFO structure lacks a qualified policy or normalized dual-clock memory",
        )
        targets = _executable_targets(target_states)
        parameters = tuple(
            sorted(
                {
                    **dict(policy.parameters),
                    "memory": policy.subject,
                    "depth": str(memory.depth),
                    "data_width": str(memory.element_width),
                    "write_reset_active_low": str(write_domain.reset_active_low).lower(),
                    "read_reset_active_low": str(read_domain.reset_active_low).lower(),
                }.items()
            )
        )
        config_ref = EvidenceRef(
            EvidenceKind.CONFIGURATION,
            "dv-platform.toml",
            f"verification_depth:cdc/{plan.module}/{policy.subject}",
            "Qualified async FIFO and Gray-pointer intent.",
        )
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, kind, policy.subject),
                kind=kind,
                stimulus=(
                    ScenarioStimulus("async_fifo_profile", parameters=parameters),
                    ScenarioStimulus("write_sequence", policy.parameter("write_data")),
                    ScenarioStimulus("read_sequence", policy.parameter("read_data")),
                ),
                oracle=ScenarioOracle("fifo_scoreboard", policy.parameter("read_data"), "write order"),
                completion=ScenarioCompletion(
                    "bounded_cycles",
                    policy.parameter("empty_signal"),
                    "1",
                    int(policy.parameter("max_latency_cycles") or str(memory.depth * 8)),
                ),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:async-fifo:{policy.subject}",
                        "async_fifo",
                        (
                            "write",
                            "read",
                            "full",
                            "empty",
                            "wraparound",
                            "concurrent-clocks",
                            "reset-recovery",
                            "gray-one-bit",
                            *(
                                ("first-word-fall-through",)
                                if policy.parameter("first_word_fall_through") == "true"
                                else ()
                            ),
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
