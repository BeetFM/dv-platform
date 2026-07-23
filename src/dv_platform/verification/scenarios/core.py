# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from dv_platform.core.models import (
    ScenarioTargetState,
    ScenarioTargetSupport,
    VerificationCheck,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.verification.target_support import scenario_target_support


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
    diagnostics.extend(_validate_scenario_targets(plan, scenario))
    if not scenario.evidence_refs:
        diagnostics.append("scenario has no normalized evidence")
    return tuple(diagnostics)


def _validate_scenario_targets(plan: VerificationPlan, scenario: VerificationScenario) -> tuple[str, ...]:
    diagnostics: list[str] = []
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
    return tuple(diagnostics)


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
