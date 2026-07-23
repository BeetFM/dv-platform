# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

import json
from dataclasses import replace

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.verification.planning.targets import scenario_target_support


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
