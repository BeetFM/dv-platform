"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    VerificationCheck,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.generators.scenario_registry import scenario_target_support


def build_deterministic_scenarios(plan: VerificationPlan) -> tuple[VerificationScenario, ...]:
    """Build scenarios only from normalized facts; human-readable check prose is never parsed."""

    scenarios: list[VerificationScenario] = []
    for model in plan.protocol_models:
        if model.name == "APB4":
            scenarios.extend(_apb4_scenarios(plan, model))
        elif model.name == "AXI4-Lite":
            scenarios.extend(_axi4_lite_scenarios(plan, model))
        elif model.name == "AHB-Lite":
            scenarios.extend(_ahb_lite_scenarios(plan, model))
        elif model.profile_id is not None and model.profile_id.endswith("-1.0"):
            scenarios.extend(_production_protocol_scenarios(plan, model))
    scenarios.extend(_reset_scenarios(plan))
    scenarios.extend(_cdc_scenarios(plan))
    scenarios.extend(_memory_scenarios(plan))
    scenarios.extend(_formal_contract_scenarios(plan))
    scenarios.extend(_peripheral_scenarios(plan))
    return tuple(scenarios)


def _production_protocol_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    """Build common bounded transaction intent from the shared profile contract."""

    check_ids = tuple(
        check.check_id
        for check in plan.check_details
        if check.executable and ("protocol" in check.category or model.name.lower() in check.statement.lower())
    )
    if not check_ids:
        check_ids = tuple(check.check_id for check in plan.check_details if check.executable)
    profile_targets = _profile_targets(model.profile_id or "")
    target_states = tuple(
        scenario_target_support("protocol_profile_transaction", (target,))[0]
        if target in profile_targets
        else ScenarioTargetSupport(
            target,
            ScenarioTargetState.UNSUPPORTED,
            reason=f"{model.profile_id} does not declare {target.value} as a supported target",
        )
        for target in plan.targets
    )
    executable_targets = tuple(state.target for state in target_states if state.state == ScenarioTargetState.EXECUTABLE)
    complete = bool(
        model.evidence_refs
        and model.clock_domain
        and not model.unsupported_semantics
        and check_ids
        and model.signal_bindings
    )
    parameters = (
        ("profile_id", model.profile_id or ""),
        ("instance_id", model.instance_id or ""),
        ("role", model.role),
        ("bindings", json.dumps(dict(model.signal_bindings), sort_keys=True)),
        ("scoreboard_keys", json.dumps(model.scoreboard_keys)),
        ("coverage_bins", json.dumps(model.coverage_bins)),
        ("maximum_burst_length", str(model.maximum_burst_length)),
        ("maximum_outstanding", str(model.maximum_outstanding)),
    )
    scenario = VerificationScenario(
        scenario_id=_scenario_id(plan.module, "protocol-profile", model.instance_id or model.profile_id or model.name),
        kind="protocol_profile_transaction",
        stimulus=(ScenarioStimulus("protocol_profile", parameters=parameters),),
        oracle=ScenarioOracle("transaction_scoreboard", "observed transactions", "reference-model transactions"),
        completion=ScenarioCompletion("bounded_cycles", timeout_cycles=model.timeout_cycles),
        coverage_goals=(
            ScenarioCoverageGoal(
                f"{plan.module}:coverage:{model.instance_id or model.profile_id}",
                "protocol_functional",
                model.coverage_bins,
            ),
        ),
        supported_targets=executable_targets,
        target_states=target_states,
        check_ids=check_ids,
        evidence_refs=model.evidence_refs,
        executable=complete and bool(executable_targets),
    )
    if complete:
        return [scenario]
    return [
        replace(
            scenario,
            supported_targets=(),
            target_states=tuple(
                ScenarioTargetSupport(
                    target,
                    ScenarioTargetState.UNSUPPORTED,
                    reason="profile requires complete evidence, clock, bindings, checks, and supported semantics",
                )
                for target in plan.targets
            ),
            executable=False,
        )
    ]


def _profile_targets(profile_id: str) -> tuple[VerificationTarget, ...]:
    from dv_platform.agent.protocols import protocol_profile

    return protocol_profile(profile_id).supported_targets


def _peripheral_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    """Build scenarios only for validated, explicitly mapped peripheral policies."""

    kinds = {"uart", "spi", "i2c", "gpio_timer_interrupt"}
    supported = {
        (claim.claim_id.split(":depth-policy:", 1)[1].split(":", 1)[0], claim.claim_id.rsplit(":", 1)[-1])
        for claim in plan.claims
        if claim.status == ClaimStatus.SUPPORTED and ":depth-policy:" in claim.claim_id
    }
    bins = {
        "uart": (
            "tx",
            "rx",
            "baud-timing",
            "even-parity",
            "odd-parity",
            "two-stop",
            "framing-error",
            "break",
            "overflow",
            "reset-recovery",
        ),
        "spi": (
            "mode-0",
            "mode-1",
            "mode-2",
            "mode-3",
            "cs-setup-hold",
            "msb-first",
            "lsb-first",
            "back-to-back",
        ),
        "i2c": (
            "open-drain",
            "start",
            "stop",
            "repeated-start",
            "ack",
            "nack",
            "clock-stretch",
            "arbitration-loss",
            "recovery",
        ),
        "gpio_timer_interrupt": (
            "gpio-direction",
            "masked-write",
            "edge-interrupt",
            "level-interrupt",
            "timer-prescale",
            "timer-rollover",
            "watchdog-feed-timeout",
            "pwm-boundaries",
            "interrupt-mask-clear-priority",
            "simultaneous-sources",
        ),
    }
    completion = {
        "uart": ("tx_busy", "0"),
        "spi": ("done", "1"),
        "i2c": ("done", "1"),
        "gpio_timer_interrupt": (None, None),
    }
    oracle = {
        "uart": ("serial_scoreboard", "rx_data"),
        "spi": ("serial_scoreboard", "rx_data"),
        "i2c": ("open_drain_bus_scoreboard", "ack_error"),
        "gpio_timer_interrupt": ("peripheral_reference_models", "interrupt_pending"),
    }
    scenarios: list[VerificationScenario] = []
    for policy in plan.depth_policies:
        if policy.kind not in kinds or (policy.kind, policy.subject) not in supported:
            continue
        check_ids = tuple(
            check.check_id
            for check in plan.check_details
            if check.category == "protocol" and policy.subject.lower() in check.statement.lower()
        )
        if not check_ids:
            continue
        scenario_kind = f"{policy.kind}_bounded"
        target_states = _qualified_target_states(
            scenario_kind,
            plan.targets,
            True,
            f"{policy.kind} scenario lacks a validated profile or stable checks",
        )
        targets = _executable_targets(target_states)
        completion_name, completion_value = completion[policy.kind]
        actual_name = oracle[policy.kind][1]
        parameters = tuple(sorted({**dict(policy.parameters), "subject": policy.subject}.items()))
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, scenario_kind, policy.subject),
                kind=scenario_kind,
                stimulus=(ScenarioStimulus(f"{policy.kind}_profile", parameters=parameters),),
                oracle=ScenarioOracle(
                    oracle[policy.kind][0],
                    policy.parameter(actual_name),
                    "bounded profile reference behavior",
                ),
                completion=ScenarioCompletion(
                    "bounded_cycles",
                    policy.parameter(completion_name) if completion_name else None,
                    completion_value,
                    int(
                        policy.parameter(
                            {
                                "uart": "max_frame_cycles",
                                "spi": "max_transfer_cycles",
                                "i2c": "max_transfer_cycles",
                                "gpio_timer_interrupt": "max_event_cycles",
                            }[policy.kind]
                        )
                        or "256"
                    ),
                ),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:{policy.kind}:{policy.subject}",
                        policy.kind,
                        bins[policy.kind],
                    ),
                ),
                supported_targets=targets,
                target_states=target_states,
                check_ids=check_ids,
                evidence_refs=(
                    EvidenceRef(
                        EvidenceKind.CONFIGURATION,
                        "dv-platform.toml",
                        f"verification_depth:{policy.kind}/{plan.module}/{policy.subject}",
                        f"Qualified bounded {policy.kind} signal and behavior mapping.",
                    ),
                ),
                executable=bool(targets),
            )
        )
    return scenarios


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


def link_scenario_coverage(
    checks: tuple[VerificationCheck, ...], scenarios: tuple[VerificationScenario, ...]
) -> tuple[VerificationCheck, ...]:
    """Attach each scenario coverage point to its linked stable checks."""

    goals_by_check: dict[str, list[str]] = {}
    executable_checks: set[str] = set()
    for scenario in scenarios:
        goal_ids = [goal.goal_id for goal in scenario.coverage_goals]
        for check_id in scenario.check_ids:
            goals_by_check.setdefault(check_id, []).extend(goal_ids)
            if scenario.executable and scenario.supported_targets:
                executable_checks.add(check_id)
    return tuple(
        replace(
            check,
            coverage_point_ids=tuple(
                dict.fromkeys((*check.coverage_point_ids, *goals_by_check.get(check.check_id, ())))
            ),
            executable=(check.executable and check.category != "cdc") or check.check_id in executable_checks,
        )
        for check in checks
    )


def _cdc_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    scenarios: list[VerificationScenario] = []
    policies = {policy.subject: policy for policy in plan.depth_policies if policy.kind == "cdc"}
    scenarios.extend(_async_fifo_scenarios(plan, tuple(policies.values())))
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


def validate_scenario(plan: VerificationPlan, scenario: VerificationScenario) -> tuple[str, ...]:
    """Return deterministic semantic diagnostics that prevent unsafe execution."""

    diagnostics: list[str] = []
    if not scenario.scenario_id or not scenario.kind:
        diagnostics.append("scenario identity and kind are required")
    if not scenario.stimulus:
        diagnostics.append("scenario has no typed stimulus")
    if not scenario.coverage_goals:
        diagnostics.append("scenario has no coverage goal")
    if scenario.completion.timeout_cycles <= 0:
        diagnostics.append("scenario completion timeout must be positive")
    if not scenario.check_ids:
        diagnostics.append("scenario is not linked to a stable check")
    known_checks = {check.check_id for check in plan.check_details}
    known_requirements = {requirement.requirement_id for requirement in plan.structured_requirements}
    unknown_checks = set(scenario.check_ids) - known_checks
    unknown_requirements = set(scenario.requirement_ids) - known_requirements
    if unknown_checks:
        diagnostics.append("scenario references unknown checks: " + ", ".join(sorted(unknown_checks)))
    if unknown_requirements:
        diagnostics.append("scenario references unknown requirements: " + ", ".join(sorted(unknown_requirements)))
    port_names = {port.name for port in plan.ports}
    signals = {
        *(item.signal for item in scenario.stimulus if item.signal),
        *((scenario.oracle.actual,) if scenario.oracle.actual else ()),
        *((scenario.completion.signal,) if scenario.completion.signal else ()),
    }
    unknown_signals = signals - port_names
    if unknown_signals:
        diagnostics.append("scenario references unknown signals: " + ", ".join(sorted(unknown_signals)))
    registered_states = scenario_target_support(scenario.kind, plan.targets)
    if len(scenario.target_states) != len(registered_states) or any(
        actual.target != registered.target
        or actual.renderer_id != registered.renderer_id
        or (actual.state == ScenarioTargetState.EXECUTABLE and registered.state != ScenarioTargetState.EXECUTABLE)
        or (registered.state != ScenarioTargetState.EXECUTABLE and actual.state != registered.state)
        or (
            registered.state == ScenarioTargetState.EXECUTABLE
            and actual.state != registered.state
            and not actual.reason
        )
        for actual, registered in zip(scenario.target_states, registered_states, strict=False)
    ):
        diagnostics.append("scenario target states do not conservatively match the renderer registry")
    executable_targets = tuple(
        support.target for support in scenario.target_states if support.state == ScenarioTargetState.EXECUTABLE
    )
    if scenario.supported_targets != executable_targets:
        diagnostics.append("scenario supported targets do not match qualified executable target states")
    if scenario.executable and not executable_targets:
        diagnostics.append("scenario is executable without a complete renderer contract")
    if not scenario.evidence_refs:
        diagnostics.append("scenario has no normalized evidence")
    return tuple(diagnostics)


def _apb4_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    required = ("psel", "penable", "pwrite", "paddr", "pwdata", "prdata", "pready", "pstrb", "pslverr")
    missing = tuple(name for name in required if name not in bindings)
    direction_mismatches = tuple(
        name
        for name in required
        if directions.get(name) != ("output" if name in {"prdata", "pready", "pslverr"} else "input")
    )
    reset = next((item for item in plan.resets if item.name == model.reset_domain), None)
    known_registers = tuple(
        register
        for register in plan.register_models
        if register.offset is not None
        and register.source != "unknown"
        and register.byte_enable_behavior != "unknown"
        and register.invalid_address_behavior != "unknown"
        and register.fields
        and all(
            field.access.lower() in {"rw", "ro", "w1c"} and field.reset_value is not None for field in register.fields
        )
    )
    valid_address = min((register.offset for register in known_registers if register.offset is not None), default=0)
    invalid_address = max(
        (register.offset + max(1, register.width // 8) for register in known_registers if register.offset is not None),
        default=4,
    )
    profile_parameters = tuple(
        sorted(
            (
                *((f"binding.{name}", actual) for name, actual in bindings.items()),
                ("clock", model.clock_domain or ""),
                ("reset", model.reset_domain or ""),
                ("reset_active_low", str(reset.active_low).lower() if reset and reset.active_low is not None else ""),
                ("valid_address", str(valid_address)),
                ("invalid_address", str(invalid_address)),
            )
        )
    )
    check_ids = tuple(dict.fromkeys((*_check_ids(plan, "protocol"), *_check_ids(plan, "reset"))))
    requirement_ids = _requirement_ids(plan, ("protocol", "register", "reset"))
    apb_ready = (
        not missing
        and not direction_mismatches
        and not model.unsupported_semantics
        and model.clock_domain is not None
        and reset is not None
        and reset.active_low is not None
        and bool(known_registers)
        and bool(check_ids)
    )
    target_states = _qualified_target_states(
        "apb4_transfer",
        plan.targets,
        apb_ready,
        "scenario lacks complete APB signal, reset, check, or register scoreboard evidence",
    )
    targets = _executable_targets(target_states)
    scenario = VerificationScenario(
        scenario_id=_scenario_id(plan.module, "apb4_transfer", "bus"),
        kind="apb4_transfer",
        stimulus=(
            ScenarioStimulus("apb4_profile", parameters=profile_parameters),
            ScenarioStimulus("reset", model.reset_domain, parameters=(("cycles", "2"),)),
            ScenarioStimulus("drive", bindings.get("psel"), "1"),
            ScenarioStimulus("drive", bindings.get("penable"), "0"),
            ScenarioStimulus("drive", bindings.get("pwrite"), "0"),
            ScenarioStimulus("next_cycle"),
            ScenarioStimulus("drive", bindings.get("penable"), "1"),
        ),
        oracle=ScenarioOracle("handshake", bindings.get("pready"), "1", "access_phase"),
        completion=ScenarioCompletion("signal", bindings.get("pready"), "1", 32),
        coverage_goals=(
            ScenarioCoverageGoal(
                f"{plan.module}:coverage:apb4-transfer",
                "protocol_transfer",
                (
                    "reset",
                    "setup",
                    "access",
                    "wait-state",
                    "read-completion",
                    "write-completion",
                    "invalid-address",
                    "pslverr",
                ),
            ),
        ),
        supported_targets=targets,
        target_states=target_states,
        requirement_ids=requirement_ids,
        check_ids=check_ids,
        evidence_refs=model.evidence_refs,
        executable=apb_ready and bool(targets),
    )
    scenarios = [scenario]
    for register in plan.register_models:
        known_behavior = register in known_registers
        register_checks = tuple(dict.fromkeys((*check_ids, *_register_check_ids(plan, register.name))))
        register_ready = apb_ready and known_behavior and bool(register_checks)
        register_target_states = _qualified_target_states(
            "apb4_register_access",
            plan.targets,
            register_ready,
            f"register {register.name} lacks complete APB scoreboard evidence or linked checks",
        )
        register_targets = _executable_targets(register_target_states)
        register_spec = json.dumps(
            {
                "byte_enable_behavior": register.byte_enable_behavior,
                "fields": [
                    {
                        "access": field.access.lower(),
                        "lsb": field.lsb,
                        "msb": field.msb,
                        "name": field.name,
                        "reset": field.reset_value,
                    }
                    for field in register.fields
                ],
                "invalid_address_behavior": register.invalid_address_behavior,
                "name": register.name,
                "offset": register.offset,
                "width": register.width,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, "apb4_register_access", register.name),
                kind="apb4_register_access",
                stimulus=(
                    ScenarioStimulus("apb4_profile", parameters=profile_parameters),
                    ScenarioStimulus("register_spec", parameters=(("json", register_spec),)),
                    ScenarioStimulus("reset", model.reset_domain, parameters=(("cycles", "2"),)),
                    ScenarioStimulus(
                        "apb_write",
                        parameters=(("register", register.name), ("offset", str(register.offset or 0))),
                    ),
                    ScenarioStimulus(
                        "apb_read",
                        parameters=(("register", register.name), ("offset", str(register.offset or 0))),
                    ),
                ),
                oracle=ScenarioOracle("register_model", bindings.get("prdata"), register.name),
                completion=ScenarioCompletion("signal", bindings.get("pready"), "1", 32),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:register:{register.name}",
                        "register_access",
                        tuple(
                            dict.fromkeys(
                                (
                                    "reset-value",
                                    "read-completion",
                                    "write-completion",
                                    "pstrb",
                                    *(field.access.lower() for field in register.fields),
                                )
                            )
                        ),
                    ),
                ),
                supported_targets=register_targets,
                target_states=register_target_states,
                requirement_ids=requirement_ids,
                check_ids=register_checks,
                evidence_refs=tuple(dict.fromkeys((*model.evidence_refs, *register.evidence_refs))),
                executable=bool(register_ready and register_targets),
            )
        )
    return scenarios


def _axi4_lite_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    required = (
        "awaddr",
        "awvalid",
        "awready",
        "wdata",
        "wstrb",
        "wvalid",
        "wready",
        "bresp",
        "bvalid",
        "bready",
        "araddr",
        "arvalid",
        "arready",
        "rdata",
        "rresp",
        "rvalid",
        "rready",
    )
    slave_outputs = {"awready", "wready", "bresp", "bvalid", "arready", "rdata", "rresp", "rvalid"}
    direction_mismatches = tuple(
        name for name in required if directions.get(name) != ("output" if name in slave_outputs else "input")
    )
    reset = next((item for item in plan.resets if item.name == model.reset_domain), None)
    known_registers = tuple(
        register
        for register in plan.register_models
        if register.offset is not None
        and register.source != "unknown"
        and register.byte_enable_behavior != "unknown"
        and register.invalid_address_behavior != "unknown"
        and register.fields
        and all(
            field.access.lower() in {"rw", "ro", "w1c"} and field.reset_value is not None for field in register.fields
        )
    )
    valid_address = min((register.offset for register in known_registers if register.offset is not None), default=0)
    invalid_address = max(
        (register.offset + max(1, register.width // 8) for register in known_registers if register.offset is not None),
        default=4,
    )
    profile = tuple(
        sorted(
            (
                *((f"binding.{name}", actual) for name, actual in bindings.items()),
                ("clock", model.clock_domain or ""),
                ("reset", model.reset_domain or ""),
                ("reset_active_low", str(reset.active_low).lower() if reset and reset.active_low is not None else ""),
                ("valid_address", str(valid_address)),
                ("invalid_address", str(invalid_address)),
            )
        )
    )
    register_stimuli = tuple(
        ScenarioStimulus(
            "register_spec",
            parameters=(
                (
                    "json",
                    json.dumps(
                        {
                            "byte_enable_behavior": register.byte_enable_behavior,
                            "fields": [
                                {
                                    "access": field.access.lower(),
                                    "lsb": field.lsb,
                                    "msb": field.msb,
                                    "name": field.name,
                                    "reset": field.reset_value,
                                }
                                for field in register.fields
                            ],
                            "invalid_address_behavior": register.invalid_address_behavior,
                            "name": register.name,
                            "offset": register.offset,
                            "width": register.width,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            ),
        )
        for register in known_registers
    )
    checks = tuple(
        dict.fromkeys((*_check_ids(plan, "protocol"), *_check_ids(plan, "reset"), *_check_ids(plan, "register_access")))
    )
    axi_ready = (
        all(name in bindings for name in required)
        and not direction_mismatches
        and not model.unsupported_semantics
        and model.clock_domain is not None
        and reset is not None
        and reset.active_low is not None
        and bool(known_registers)
        and bool(checks)
    )
    target_states = _qualified_target_states(
        "axi4_lite_single_outstanding",
        plan.targets,
        axi_ready,
        "scenario lacks complete AXI4-Lite signal, reset, check, or register scoreboard evidence",
    )
    targets = _executable_targets(target_states)
    return [
        VerificationScenario(
            scenario_id=_scenario_id(plan.module, "axi4_lite_single_outstanding", "bus"),
            kind="axi4_lite_single_outstanding",
            stimulus=(
                ScenarioStimulus("axi4_lite_profile", parameters=profile),
                *register_stimuli,
                ScenarioStimulus("axi_write", parameters=(("outstanding", "1"), ("orders", "AW-W,W-AW,same"))),
                ScenarioStimulus("axi_read", parameters=(("outstanding", "1"),)),
                ScenarioStimulus("backpressure", parameters=(("channels", "B,R"),)),
            ),
            oracle=ScenarioOracle("in_order_response", expected="one response per accepted request"),
            completion=ScenarioCompletion("bounded_responses", timeout_cycles=4),
            coverage_goals=(
                ScenarioCoverageGoal(
                    f"{plan.module}:coverage:axi4-lite-ordering",
                    "cross",
                    (
                        "reset",
                        "AW-before-W",
                        "W-before-AW",
                        "same-cycle",
                        "B-backpressure",
                        "R-backpressure",
                        "WSTRB",
                        "invalid-address",
                        "BRESP-error",
                        "RRESP-error",
                    ),
                ),
            ),
            supported_targets=targets,
            target_states=target_states,
            requirement_ids=_requirement_ids(plan, ("protocol", "register")),
            check_ids=checks,
            evidence_refs=model.evidence_refs,
            executable=axi_ready and bool(targets),
        )
    ]


def _ahb_lite_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    """Build the fail-closed, single-beat AHB-Lite slave profile."""

    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    required = ("haddr", "htrans", "hwrite", "hready", "hreadyout", "hresp", "hsel", "hwdata", "hrdata")
    slave_outputs = {"hreadyout", "hresp", "hrdata"}
    direction_mismatches = tuple(
        name for name in required if directions.get(name) != ("output" if name in slave_outputs else "input")
    )
    reset = next((item for item in plan.resets if item.name == model.reset_domain), None)
    known_registers = tuple(
        register
        for register in plan.register_models
        if register.offset is not None
        and register.source != "unknown"
        and register.invalid_address_behavior != "unknown"
        and register.fields
        and all(
            field.access.lower() in {"rw", "ro", "w1c"} and field.reset_value is not None for field in register.fields
        )
    )
    valid_address = min((register.offset for register in known_registers if register.offset is not None), default=0)
    invalid_address = max(
        (register.offset + max(1, register.width // 8) for register in known_registers if register.offset is not None),
        default=4,
    )
    profile = tuple(
        sorted(
            (
                *((f"binding.{name}", actual) for name, actual in bindings.items()),
                ("clock", model.clock_domain or ""),
                ("reset", model.reset_domain or ""),
                ("reset_active_low", str(reset.active_low).lower() if reset and reset.active_low is not None else ""),
                ("valid_address", str(valid_address)),
                ("invalid_address", str(invalid_address)),
            )
        )
    )
    register_stimuli = tuple(
        ScenarioStimulus(
            "register_spec",
            parameters=(
                (
                    "json",
                    json.dumps(
                        {
                            "fields": [
                                {
                                    "access": field.access.lower(),
                                    "lsb": field.lsb,
                                    "msb": field.msb,
                                    "name": field.name,
                                    "reset": field.reset_value,
                                }
                                for field in register.fields
                            ],
                            "invalid_address_behavior": register.invalid_address_behavior,
                            "name": register.name,
                            "offset": register.offset,
                            "width": register.width,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            ),
        )
        for register in known_registers
    )
    checks = tuple(
        dict.fromkeys((*_check_ids(plan, "protocol"), *_check_ids(plan, "reset"), *_check_ids(plan, "register_access")))
    )
    ready = (
        all(name in bindings for name in required)
        and not direction_mismatches
        and not model.unsupported_semantics
        and model.clock_domain is not None
        and reset is not None
        and reset.active_low is not None
        and bool(known_registers)
        and bool(checks)
    )
    target_states = _qualified_target_states(
        "ahb_lite_single_beat",
        plan.targets,
        ready,
        "scenario lacks complete AHB-Lite signal, reset, check, or register scoreboard evidence",
    )
    targets = _executable_targets(target_states)
    return [
        VerificationScenario(
            scenario_id=_scenario_id(plan.module, "ahb_lite_single_beat", "bus"),
            kind="ahb_lite_single_beat",
            stimulus=(
                ScenarioStimulus("ahb_lite_profile", parameters=profile),
                *register_stimuli,
                ScenarioStimulus("ahb_read", parameters=(("address", str(valid_address)),)),
                ScenarioStimulus("ahb_write", parameters=(("address", str(valid_address)),)),
                ScenarioStimulus("ahb_idle"),
            ),
            oracle=ScenarioOracle("single_beat_register_model", bindings.get("hrdata"), "mapped register state"),
            completion=ScenarioCompletion("signal", bindings.get("hreadyout"), "1", 16),
            coverage_goals=(
                ScenarioCoverageGoal(
                    f"{plan.module}:coverage:ahb-lite-single-beat",
                    "protocol_transfer",
                    (
                        "reset",
                        "idle",
                        "read-completion",
                        "write-completion",
                        "wait-state",
                        "stable-control",
                        "invalid-address",
                        "hresp-error",
                        "reset-recovery",
                    ),
                ),
            ),
            supported_targets=targets,
            target_states=target_states,
            requirement_ids=_requirement_ids(plan, ("protocol", "register", "reset")),
            check_ids=checks,
            evidence_refs=tuple(
                dict.fromkeys(
                    (*model.evidence_refs, *(ref for register in known_registers for ref in register.evidence_refs))
                )
            ),
            executable=ready and bool(targets),
        )
    ]


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


def _target_states(kind: str, targets: tuple[VerificationTarget, ...]) -> tuple[ScenarioTargetSupport, ...]:
    return scenario_target_support(kind, targets)


def _qualified_target_states(
    kind: str,
    targets: tuple[VerificationTarget, ...],
    ready: bool,
    reason: str,
) -> tuple[ScenarioTargetSupport, ...]:
    registered = _target_states(kind, targets)
    if ready:
        return registered
    return tuple(
        replace(item, state=ScenarioTargetState.SCAFFOLD, reason=reason)
        if item.state == ScenarioTargetState.EXECUTABLE
        else item
        for item in registered
    )


def _executable_targets(states: tuple[ScenarioTargetSupport, ...]) -> tuple[VerificationTarget, ...]:
    return tuple(item.target for item in states if item.state == ScenarioTargetState.EXECUTABLE)


def _check_ids(plan: VerificationPlan, category: str) -> tuple[str, ...]:
    return tuple(check.check_id for check in plan.check_details if check.category == category)


def _register_check_ids(plan: VerificationPlan, register_name: str) -> tuple[str, ...]:
    normalized = register_name.lower()
    return tuple(
        check.check_id
        for check in plan.check_details
        if check.category == "register_access" and normalized in check.statement.lower()
    )


def _requirement_ids(plan: VerificationPlan, categories: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(req.requirement_id for req in plan.structured_requirements if req.category in categories)


def _scenario_id(module: str, kind: str, subject: str) -> str:
    digest = hashlib.sha256(f"{module}|{kind}|{subject}".encode()).hexdigest()[:12]
    return f"{module}:scenario:{digest}"
