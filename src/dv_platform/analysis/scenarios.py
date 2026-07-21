"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    VerificationCheck,
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
    scenarios.extend(_reset_scenarios(plan))
    return tuple(scenarios)


def link_scenario_coverage(
    checks: tuple[VerificationCheck, ...], scenarios: tuple[VerificationScenario, ...]
) -> tuple[VerificationCheck, ...]:
    """Attach each scenario coverage point to its linked stable checks."""

    goals_by_check: dict[str, list[str]] = {}
    for scenario in scenarios:
        goal_ids = [goal.goal_id for goal in scenario.coverage_goals]
        for check_id in scenario.check_ids:
            goals_by_check.setdefault(check_id, []).extend(goal_ids)
    return tuple(
        replace(
            check,
            coverage_point_ids=tuple(
                dict.fromkeys((*check.coverage_point_ids, *goals_by_check.get(check.check_id, ())))
            ),
        )
        for check in checks
    )


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
    if scenario.target_states != registered_states:
        diagnostics.append("scenario target states do not match the renderer registry")
    executable_targets = tuple(
        support.target for support in scenario.target_states if support.state == ScenarioTargetState.EXECUTABLE
    )
    if scenario.supported_targets != executable_targets:
        diagnostics.append("scenario supported targets do not match executable renderer registrations")
    if scenario.executable and not executable_targets:
        diagnostics.append("scenario is executable without a complete renderer contract")
    if not scenario.evidence_refs:
        diagnostics.append("scenario has no normalized evidence")
    return tuple(diagnostics)


def _apb4_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    bindings = dict(model.signal_bindings)
    required = ("psel", "penable", "pwrite", "paddr", "pwdata", "prdata", "pready", "pstrb", "pslverr")
    missing = tuple(name for name in required if name not in bindings)
    check_ids = _check_ids(plan, "protocol")
    requirement_ids = _requirement_ids(plan, ("protocol", "register", "reset"))
    target_states = _target_states("apb4_transfer", plan.targets)
    targets = _executable_targets(target_states)
    scenario = VerificationScenario(
        scenario_id=_scenario_id(plan.module, "apb4_transfer", "bus"),
        kind="apb4_transfer",
        stimulus=(
            ScenarioStimulus("drive", bindings.get("psel"), "1"),
            ScenarioStimulus("drive", bindings.get("penable"), "0"),
            ScenarioStimulus("drive", bindings.get("pwrite"), "0"),
            ScenarioStimulus("next_cycle"),
            ScenarioStimulus("drive", bindings.get("penable"), "1"),
        ),
        oracle=ScenarioOracle("handshake", bindings.get("pready"), "1", "access_phase"),
        completion=ScenarioCompletion("signal", bindings.get("pready"), "1", 32),
        coverage_goals=(ScenarioCoverageGoal(f"{plan.module}:coverage:apb4-transfer", "protocol_transfer"),),
        supported_targets=targets,
        target_states=target_states,
        requirement_ids=requirement_ids,
        check_ids=check_ids,
        evidence_refs=model.evidence_refs,
        executable=not missing and not model.unsupported_semantics and bool(check_ids) and bool(targets),
    )
    scenarios = [scenario]
    for register in plan.register_models:
        register_target_states = _target_states("apb4_register_access", plan.targets)
        register_targets = _executable_targets(register_target_states)
        known_fields = bool(register.fields) and all(
            field.access.lower() in {"rw", "ro", "w1c"} for field in register.fields
        )
        known_behavior = (
            register.offset is not None
            and register.source != "unknown"
            and register.byte_enable_behavior != "unknown"
            and register.invalid_address_behavior != "unknown"
            and known_fields
        )
        register_checks = tuple(dict.fromkeys((*check_ids, *_check_ids(plan, "register_access"))))
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, "apb4_register_access", register.name),
                kind="apb4_register_access",
                stimulus=(
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
                        tuple(field.access.lower() for field in register.fields),
                    ),
                ),
                supported_targets=register_targets,
                target_states=register_target_states,
                requirement_ids=requirement_ids,
                check_ids=register_checks,
                evidence_refs=tuple(dict.fromkeys((*model.evidence_refs, *register.evidence_refs))),
                executable=bool(scenario.executable and known_behavior and register_checks and register_targets),
            )
        )
    return scenarios


def _axi4_lite_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    bindings = dict(model.signal_bindings)
    required = (
        "awvalid",
        "awready",
        "wvalid",
        "wready",
        "bvalid",
        "bready",
        "arvalid",
        "arready",
        "rvalid",
        "rready",
    )
    checks = _check_ids(plan, "protocol")
    target_states = _target_states("axi4_lite_single_outstanding", plan.targets)
    targets = _executable_targets(target_states)
    return [
        VerificationScenario(
            scenario_id=_scenario_id(plan.module, "axi4_lite_single_outstanding", "bus"),
            kind="axi4_lite_single_outstanding",
            stimulus=(
                ScenarioStimulus("axi_write", parameters=(("outstanding", "1"),)),
                ScenarioStimulus("axi_read", parameters=(("outstanding", "1"),)),
                ScenarioStimulus("backpressure", parameters=(("channels", "B,R"),)),
            ),
            oracle=ScenarioOracle("in_order_response", expected="one response per accepted request"),
            completion=ScenarioCompletion("bounded_responses", timeout_cycles=64),
            coverage_goals=(
                ScenarioCoverageGoal(
                    f"{plan.module}:coverage:axi4-lite-ordering", "cross", ("AW-before-W", "W-before-AW", "same-cycle")
                ),
            ),
            supported_targets=targets,
            target_states=target_states,
            requirement_ids=_requirement_ids(plan, ("protocol", "register")),
            check_ids=checks,
            evidence_refs=model.evidence_refs,
            executable=all(name in bindings for name in required)
            and not model.unsupported_semantics
            and bool(checks)
            and bool(targets),
        )
    ]


def _reset_scenarios(plan: VerificationPlan) -> list[VerificationScenario]:
    check_ids = _check_ids(plan, "reset")
    if not check_ids:
        return []
    result: list[VerificationScenario] = []
    for reset in plan.resets:
        target_states = _target_states("reset_sequence", plan.targets)
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
                oracle=ScenarioOracle("reset_observed", reset.name, deasserted),
                completion=ScenarioCompletion("cycles", timeout_cycles=8),
                coverage_goals=(ScenarioCoverageGoal(f"{plan.module}:coverage:reset:{reset.name}", "reset_sequence"),),
                supported_targets=targets,
                target_states=target_states,
                check_ids=check_ids,
                evidence_refs=evidence,
                executable=reset.active_low is not None and bool(targets) and bool(evidence),
            )
        )
    return result


def _target_states(kind: str, targets: tuple[VerificationTarget, ...]) -> tuple[ScenarioTargetSupport, ...]:
    return scenario_target_support(kind, targets)


def _executable_targets(states: tuple[ScenarioTargetSupport, ...]) -> tuple[VerificationTarget, ...]:
    return tuple(item.target for item in states if item.state == ScenarioTargetState.EXECUTABLE)


def _check_ids(plan: VerificationPlan, category: str) -> tuple[str, ...]:
    return tuple(check.check_id for check in plan.check_details if check.category == category)


def _requirement_ids(plan: VerificationPlan, categories: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(req.requirement_id for req in plan.structured_requirements if req.category in categories)


def _scenario_id(module: str, kind: str, subject: str) -> str:
    digest = hashlib.sha256(f"{module}|{kind}|{subject}".encode()).hexdigest()[:12]
    return f"{module}:scenario:{digest}"
