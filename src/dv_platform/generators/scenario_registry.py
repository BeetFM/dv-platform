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
    for target in VerificationTarget:
        executable = target in {
            VerificationTarget.COCOTB,
            VerificationTarget.FORMAL,
            VerificationTarget.SYSTEMVERILOG,
            VerificationTarget.VERILOG,
            VerificationTarget.VHDL,
        }
        registry.register(
            ScenarioRendererRegistration(
                "protocol_profile_transaction",
                target,
                ScenarioTargetState.EXECUTABLE if executable else ScenarioTargetState.SCAFFOLD,
                renderer_id=f"{target.value}.protocol_profile.v1",
                validator_id="scenario.semantic.v1" if executable else None,
                trace_mapper_id=(
                    "cocotb.junit_symbol_trace.v1"
                    if target == VerificationTarget.COCOTB
                    else "formal.scenario_trace.v1"
                    if target == VerificationTarget.FORMAL
                    else "native.result_trace.v1"
                    if executable and target != VerificationTarget.VHDL
                    else "vhdl.native_result_trace.v1"
                    if target == VerificationTarget.VHDL
                    else None
                ),
                result_decoder_id=(
                    "cocotb.junit_result.v1"
                    if target == VerificationTarget.COCOTB
                    else "formal.sby_task_result.v1"
                    if target == VerificationTarget.FORMAL
                    else "native.result.v1"
                    if executable and target != VerificationTarget.VHDL
                    else "vhdl.native_result.v1"
                    if target == VerificationTarget.VHDL
                    else None
                ),
                reason=(
                    None
                    if executable
                    else "profile contract is emitted, but exact target-specific execution is not yet qualified"
                ),
            )
        )
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
        registry.register(
            ScenarioRendererRegistration(
                kind,
                VerificationTarget.FORMAL,
                ScenarioTargetState.EXECUTABLE,
                renderer_id="formal.apb4_scenario.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id="formal.scenario_trace.v1",
                result_decoder_id="formal.sby_task_result.v1",
            )
        )
        for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
            registry.register(
                ScenarioRendererRegistration(
                    kind,
                    target,
                    ScenarioTargetState.EXECUTABLE,
                    renderer_id=f"{target.value}.apb4_native.v1",
                    validator_id="scenario.semantic.v1",
                    trace_mapper_id="native.result_trace.v1",
                    result_decoder_id="native.result.v1",
                )
            )
    registry.register(
        ScenarioRendererRegistration(
            "axi4_lite_single_outstanding",
            VerificationTarget.COCOTB,
            ScenarioTargetState.EXECUTABLE,
            renderer_id="cocotb.axi4_lite_scenario.v1",
            validator_id="scenario.semantic.v1",
            trace_mapper_id="cocotb.junit_symbol_trace.v1",
            result_decoder_id="cocotb.junit_result.v1",
        )
    )
    registry.register(
        ScenarioRendererRegistration(
            "ahb_lite_single_beat",
            VerificationTarget.COCOTB,
            ScenarioTargetState.EXECUTABLE,
            renderer_id="cocotb.ahb_lite_single_beat.v1",
            validator_id="scenario.semantic.v1",
            trace_mapper_id="cocotb.junit_symbol_trace.v1",
            result_decoder_id="cocotb.junit_result.v1",
        )
    )
    registry.register(
        ScenarioRendererRegistration(
            "ahb_lite_single_beat",
            VerificationTarget.FORMAL,
            ScenarioTargetState.EXECUTABLE,
            renderer_id="formal.ahb_lite_single_beat.v1",
            validator_id="scenario.semantic.v1",
            trace_mapper_id="formal.scenario_trace.v1",
            result_decoder_id="formal.sby_task_result.v1",
        )
    )
    for kind in ("cdc_two_flop", "cdc_pulse", "cdc_toggle", "cdc_handshake", "cdc_async_fifo"):
        registry.register(
            ScenarioRendererRegistration(
                kind,
                VerificationTarget.COCOTB,
                ScenarioTargetState.EXECUTABLE,
                renderer_id=f"cocotb.{kind}.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id="cocotb.junit_symbol_trace.v1",
                result_decoder_id="cocotb.junit_result.v1",
            )
        )
        registry.register(
            ScenarioRendererRegistration(
                kind,
                VerificationTarget.FORMAL,
                ScenarioTargetState.EXECUTABLE,
                renderer_id=f"formal.{kind}.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id="formal.scenario_trace.v1",
                result_decoder_id="formal.sby_task_result.v1",
            )
        )
    for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
        registry.register(
            ScenarioRendererRegistration(
                "axi4_lite_single_outstanding",
                target,
                ScenarioTargetState.EXECUTABLE,
                renderer_id=f"{target.value}.axi4_lite_native.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id="native.result_trace.v1",
                result_decoder_id="native.result.v1",
            )
        )
    registry.register(
        ScenarioRendererRegistration(
            "axi4_lite_single_outstanding",
            VerificationTarget.FORMAL,
            ScenarioTargetState.EXECUTABLE,
            renderer_id="formal.axi4_lite_scenario.v1",
            validator_id="scenario.semantic.v1",
            trace_mapper_id="formal.scenario_trace.v1",
            result_decoder_id="formal.sby_task_result.v1",
        )
    )
    for target, renderer in (
        (VerificationTarget.COCOTB, "cocotb.reset_smoke.v1"),
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
    for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG, VerificationTarget.VHDL):
        registry.register(
            ScenarioRendererRegistration(
                "reset_sequence",
                target,
                ScenarioTargetState.EXECUTABLE,
                renderer_id=f"{target.value}.reset_behavior.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id="native.result_trace.v1",
                result_decoder_id="native.result.v1",
            )
        )
    for target in (VerificationTarget.COCOTB, VerificationTarget.FORMAL):
        for kind in ("uart_bounded", "spi_bounded", "i2c_bounded", "gpio_timer_interrupt_bounded"):
            registry.register(
                ScenarioRendererRegistration(
                    kind,
                    target,
                    ScenarioTargetState.EXECUTABLE,
                    renderer_id=f"{target.value}.{kind}.v1",
                    validator_id="scenario.semantic.v1",
                    trace_mapper_id=(
                        "cocotb.junit_symbol_trace.v1"
                        if target == VerificationTarget.COCOTB
                        else "formal.scenario_trace.v1"
                    ),
                    result_decoder_id=(
                        "cocotb.junit_result.v1" if target == VerificationTarget.COCOTB else "formal.sby_task_result.v1"
                    ),
                )
            )
        registry.register(
            ScenarioRendererRegistration(
                "reset_domain_sequence",
                target,
                ScenarioTargetState.EXECUTABLE,
                renderer_id=f"{target.value}.reset_domain_sequence.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id=(
                    "cocotb.junit_symbol_trace.v1"
                    if target == VerificationTarget.COCOTB
                    else "formal.scenario_trace.v1"
                ),
                result_decoder_id=(
                    "cocotb.junit_result.v1" if target == VerificationTarget.COCOTB else "formal.sby_task_result.v1"
                ),
            )
        )
        registry.register(
            ScenarioRendererRegistration(
                "memory_bounded_sram",
                target,
                ScenarioTargetState.EXECUTABLE,
                renderer_id=f"{target.value}.memory_bounded_sram.v1",
                validator_id="scenario.semantic.v1",
                trace_mapper_id=(
                    "cocotb.junit_symbol_trace.v1"
                    if target == VerificationTarget.COCOTB
                    else "formal.scenario_trace.v1"
                ),
                result_decoder_id=(
                    "cocotb.junit_result.v1" if target == VerificationTarget.COCOTB else "formal.sby_task_result.v1"
                ),
            )
        )
    registry.register(
        ScenarioRendererRegistration(
            "formal_bounded_response",
            VerificationTarget.FORMAL,
            ScenarioTargetState.EXECUTABLE,
            renderer_id="formal.bounded_response.v1",
            validator_id="scenario.semantic.v1",
            trace_mapper_id="formal.scenario_trace.v1",
            result_decoder_id="formal.sby_task_result.v1",
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
