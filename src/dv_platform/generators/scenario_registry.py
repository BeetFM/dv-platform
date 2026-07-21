"""Authoritative registry for deterministic scenario renderer capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field

from dv_platform.core.models import (
    ScenarioTargetState,
    ScenarioTargetSupport,
    VerificationScenario,
    VerificationTarget,
)


@dataclass(frozen=True)
class ScenarioRendererRegistration:
    """One scenario/target implementation and all contracts needed for closure."""

    kind: str
    target: VerificationTarget
    state: ScenarioTargetState
    renderer_id: str | None = None
    validator_id: str | None = None
    trace_mapper_id: str | None = None
    result_decoder_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        contracts = (self.renderer_id, self.validator_id, self.trace_mapper_id, self.result_decoder_id)
        if self.state == ScenarioTargetState.EXECUTABLE and not all(contracts):
            raise ValueError("Executable scenario registrations require renderer, validator, trace, and decoder IDs")
        if self.state != ScenarioTargetState.EXECUTABLE and not self.reason:
            raise ValueError("Non-executable scenario registrations require a reason")

    def support(self) -> ScenarioTargetSupport:
        return ScenarioTargetSupport(self.target, self.state, self.renderer_id, self.reason)


@dataclass
class ScenarioRendererRegistry:
    """Shared planning/generation source of truth for scenario capabilities."""

    _registrations: dict[tuple[str, VerificationTarget], ScenarioRendererRegistration] = field(default_factory=dict)

    def register(self, registration: ScenarioRendererRegistration) -> None:
        key = (registration.kind, registration.target)
        if key in self._registrations:
            raise ValueError(f"Scenario renderer is already registered for {registration.kind}/{registration.target}")
        self._registrations[key] = registration

    def get(self, kind: str, target: VerificationTarget) -> ScenarioRendererRegistration:
        registration = self._registrations.get((kind, target))
        if registration is not None:
            return registration
        return ScenarioRendererRegistration(
            kind,
            target,
            ScenarioTargetState.UNSUPPORTED,
            reason=f"no deterministic {target.value} renderer is registered for {kind}",
        )

    def supports(self, kind: str, targets: tuple[VerificationTarget, ...]) -> tuple[ScenarioTargetSupport, ...]:
        return tuple(self.get(kind, target).support() for target in targets)


def _built_in_registry() -> ScenarioRendererRegistry:
    registry = ScenarioRendererRegistry()
    for kind in ("apb4_transfer", "apb4_register_access"):
        registry.register(
            ScenarioRendererRegistration(
                kind,
                VerificationTarget.COCOTB,
                ScenarioTargetState.EXECUTABLE,
                renderer_id="cocotb.apb4_scenario.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id="cocotb.junit_symbol_trace.v1",
                result_decoder_id="cocotb.junit_result.v1",
            )
        )
        for target, renderer in (
            (VerificationTarget.SYSTEMVERILOG, "systemverilog.apb4_assertions.v1"),
            (VerificationTarget.FORMAL, "formal.apb4_assertions.v1"),
        ):
            registry.register(
                ScenarioRendererRegistration(
                    kind,
                    target,
                    ScenarioTargetState.SCAFFOLD,
                    renderer_id=renderer,
                    reason="renderer has no scenario-specific trace mapping and normalized result decoder",
                )
            )
    for target, renderer in (
        (VerificationTarget.COCOTB, "cocotb.axi4_lite_probe.v1"),
        (VerificationTarget.SYSTEMVERILOG, "systemverilog.axi4_lite_assertions.v1"),
        (VerificationTarget.FORMAL, "formal.axi4_lite_assertions.v1"),
    ):
        registry.register(
            ScenarioRendererRegistration(
                "axi4_lite_single_outstanding",
                target,
                ScenarioTargetState.SCAFFOLD,
                renderer_id=renderer,
                reason="independent-channel scoreboard and scenario-specific result mapping are not implemented",
            )
        )
    for target, renderer in (
        (VerificationTarget.COCOTB, "cocotb.reset_smoke.v1"),
        (VerificationTarget.SYSTEMVERILOG, "systemverilog.reset_smoke.v1"),
        (VerificationTarget.FORMAL, "formal.reset_properties.v1"),
    ):
        registry.register(
            ScenarioRendererRegistration(
                "reset_sequence",
                target,
                ScenarioTargetState.SCAFFOLD,
                renderer_id=renderer,
                reason="reset collateral is not emitted and decoded as an independent named scenario",
            )
        )
    return registry


SCENARIO_RENDERERS = _built_in_registry()


def scenario_target_support(kind: str, targets: tuple[VerificationTarget, ...]) -> tuple[ScenarioTargetSupport, ...]:
    """Resolve support from registered renderer contracts only."""

    return SCENARIO_RENDERERS.supports(kind, targets)


def scenario_is_executable(scenario: VerificationScenario, target: VerificationTarget) -> bool:
    """Require the plan claim to match the current complete renderer contract."""

    registration = SCENARIO_RENDERERS.get(scenario.kind, target)
    declared = next((item for item in scenario.target_states if item.target == target), None)
    return bool(
        scenario.executable
        and target in scenario.supported_targets
        and registration.state == ScenarioTargetState.EXECUTABLE
        and declared == registration.support()
    )
