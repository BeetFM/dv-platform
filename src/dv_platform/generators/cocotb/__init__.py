"""cocotb generator backend."""

# ruff: noqa: F401

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    GeneratedArtifact,
    RTLPort,
    RTLProtocol,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generation.rendering import render_target
from dv_platform.generators.cdc import cocotb_cdc_scenario_lines
from dv_platform.generators.cocotb.support import (
    _behavior_clock,
    _clock_name,
    _clock_names,
    _driven_input_ports,
    _hold_checks,
    _increment_checks,
    _is_zero_value,
    _looks_like_output,
    _looks_like_scalar_input,
    _output_ports,
    _paired_ready_valid,
    _plan_intent_text,
    _port_names_from_plan,
    _quality_requirements,
    _ready_valid_test_lines,
    _reset_name,
    _reset_zero_outputs,
    _safe_identifier,
    _scalar_input_ports,
    _structured_ports,
)
from dv_platform.generators.memories import cocotb_memory_scenario_lines
from dv_platform.generators.peripherals import (
    cocotb_peripheral_helper_lines,
    cocotb_peripheral_scenario_lines,
    peripheral_mapped_outputs,
)
from dv_platform.generators.protocols import (
    cocotb_ahb_lite_scenario_lines,
    cocotb_apb4_scenario_lines,
    cocotb_axi4_lite_scenario_lines,
    cocotb_profile_scenario_lines,
    cocotb_protocol_lines,
)
from dv_platform.generators.resets import cocotb_reset_scenario_lines
from dv_platform.generators.scenario_registry import scenario_is_executable
from dv_platform.generators.signals import (
    artifact_trace,
    artifact_trace_for_scenario,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    safe_parameter_value,
)


class CocotbGenerator:
    """Generate evidence-backed cocotb checks from a verification plan."""

    target = VerificationTarget.COCOTB

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        traces = list(
            artifact_trace(
                plan,
                f"test_{module_name}_smoke",
                target=self.target,
                categories=("reset", "increment", "hold", "connectivity"),
            )
        )
        if _paired_ready_valid(plan) is not None:
            traces.extend(
                artifact_trace(plan, f"test_{module_name}_ready_valid", target=self.target, categories=("protocol",))
            )
        for scenario in plan.scenarios:
            if scenario_is_executable(scenario, VerificationTarget.COCOTB):
                traces.extend(
                    artifact_trace_for_scenario(
                        plan,
                        scenario,
                        f"test_{module_name}_scenario_{scenario.scenario_id.rsplit(':', 1)[-1].replace('-', '_')}",
                    )
                )
        return [
            GeneratedArtifact(
                path=Path("test_" + _safe_identifier(plan.module) + ".py"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_test_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=provenance_refs(plan),
                quality_requirements=_quality_requirements(plan),
                traceability=tuple(traces),
            )
        ]


def _test_content(plan: VerificationPlan) -> str:
    presentation = _cocotb_presentation(plan)
    return render_target("cocotb", presentation)  # type: ignore[arg-type]


def _cocotb_presentation(plan: VerificationPlan) -> dict[str, object]:
    module_name = _safe_identifier(plan.module)
    ports = _port_names_from_plan(plan)
    clock_name = (
        primary_clock_name(plan, ports)
        or (plan.protocol_models[0].clock_domain if plan.protocol_models else None)
        or "clk"
    )
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else "rst_n"
    active_low = reset.active_low if reset is not None and reset.active_low is not None else reset_name.endswith("_n")
    reset_active_value = 0 if active_low else 1
    reset_inactive_value = 1 - reset_active_value
    secondary_resets = tuple(
        (
            item.name,
            0 if (item.active_low if item.active_low is not None else item.name.endswith("_n")) else 1,
        )
        for item in plan.resets
        if item.name != reset_name
    )
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
    driven_inputs = _driven_input_ports(plan, ports, clock_name, reset_name)
    output_ports = _output_ports(plan, ports)
    generic_outputs = tuple(port for port in output_ports if port not in peripheral_mapped_outputs(plan))
    reset_zero_outputs = _reset_zero_outputs(plan, generic_outputs, reset_name)
    increment_checks = _increment_checks(plan, generic_outputs, scalar_inputs)
    hold_checks = _hold_checks(plan, generic_outputs, scalar_inputs)
    scenario_lines: list[str] = []
    _append_scenario_lines(
        scenario_lines,
        plan,
        module_name,
        clock_name,
        reset_name,
        reset_active_value,
        reset_inactive_value,
        driven_inputs,
    )
    presentation = {
        "_plan": plan,
        "protocol_header": protocol_mapping_header(plan, VerificationTarget.COCOTB),
        "module": plan.module,
        "module_name": module_name,
        "needs_protocol_import": any(scenario.kind == "protocol_profile_transaction" for scenario in plan.scenarios),
        "clock_name": repr(clock_name),
        "other_clocks": tuple(
            {"name": repr(item.name), "period": 10 + index * 4}
            for index, item in enumerate(
                (clock for clock in plan.clocks if clock.name != clock_name),
                start=1,
            )
        ),
        "driven_inputs": repr(driven_inputs),
        "secondary_resets": repr(secondary_resets),
        "reset_name": repr(reset_name),
        "reset_active_value": reset_active_value,
        "reset_inactive_value": reset_inactive_value,
        "reset_clocks": repr(_clock_names(plan, clock_name)),
        "reset_zero_outputs": tuple(repr(output) for output in reset_zero_outputs),
        "scalar_inputs": repr(scalar_inputs),
        **_cocotb_check_context(plan, clock_name, increment_checks, hold_checks),
        "output_ports": repr(output_ports),
        "has_output_ports": bool(output_ports),
        "checks": plan.checks,
        "requirements": plan.requirements,
        "scenario_lines": scenario_lines,
    }
    return presentation


def _cocotb_check_context(
    plan: VerificationPlan,
    clock_name: str,
    increment_checks: tuple[tuple[str, str], ...],
    hold_checks: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    return {
        "increment_checks": tuple(
            {
                "input": repr(input_name),
                "output": repr(output_name),
                "clock": repr(_behavior_clock(plan, "increment", output_name, input_name, clock_name)),
                "message": repr(output_name + " did not increment when " + input_name + " was asserted"),
            }
            for output_name, input_name in increment_checks
        ),
        "hold_checks": tuple(
            {
                "input": repr(input_name),
                "output": repr(output_name),
                "clock": repr(_behavior_clock(plan, "hold", output_name, input_name, clock_name)),
                "message": repr(output_name + " changed when " + input_name + " was inactive"),
            }
            for output_name, input_name in hold_checks
        ),
    }


def _append_scenario_lines(
    lines: list[str],
    plan: VerificationPlan,
    module_name: str,
    clock_name: str,
    reset_name: str,
    reset_active_value: int,
    reset_inactive_value: int,
    driven_inputs: tuple[str, ...],
) -> None:
    ready_valid = _ready_valid_test_lines(
        plan,
        module_name,
        clock_name,
        reset_name,
        reset_active_value,
        reset_inactive_value,
        driven_inputs,
    )
    if ready_valid:
        lines.extend(("", "", *ready_valid))
    sections = (
        cocotb_protocol_lines(plan, clock_name),
        cocotb_apb4_scenario_lines(plan, clock_name),
        cocotb_axi4_lite_scenario_lines(plan, clock_name),
        cocotb_ahb_lite_scenario_lines(plan, clock_name),
        cocotb_profile_scenario_lines(plan, clock_name),
        cocotb_cdc_scenario_lines(plan),
        cocotb_reset_scenario_lines(plan),
        cocotb_memory_scenario_lines(plan),
    )
    for section in sections:
        lines.extend(section)
    peripheral = cocotb_peripheral_scenario_lines(plan)
    if peripheral:
        lines.extend(peripheral)
        lines.extend(cocotb_peripheral_helper_lines())
