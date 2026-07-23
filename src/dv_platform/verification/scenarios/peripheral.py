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
