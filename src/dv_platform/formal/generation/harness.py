# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Formal generator backend."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactTrace,
    GeneratedArtifact,
    RTLReset,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generation.rendering import render_target
from dv_platform.generators.peripherals import (
    formal_peripheral_assertions,
    formal_peripheral_output_signals,
    peripheral_mapped_outputs,
)
from dv_platform.generators.protocols import (
    formal_ahb_lite_assertions,
    formal_ahb_lite_declarations,
    formal_apb4_assertions,
    formal_apb4_declarations,
    formal_axi4_lite_assertions,
    formal_axi4_lite_declarations,
    formal_profile_assertions,
    formal_profile_declarations,
)
from dv_platform.generators.scenario_registry import scenario_is_executable
from dv_platform.generators.signals import (
    artifact_trace,
    artifact_trace_for_scenario,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    sv_parameter_clause,
)


class CDCProofPolicy(StrEnum):
    """Permitted evidence levels for generated CDC properties."""

    FAIL_CLOSED = "fail-closed"
    BOUNDED = "bounded"
    STRUCTURAL = "structural"


@dataclass(frozen=True)
class _CDCPathEvidence:
    path_id: str
    signal: str
    evidence_level: str
    closure_eligible: bool
    task: str | None
    clock: str | None
    observed_stages: tuple[str, ...]
    hidden_stages: tuple[str, ...]
    latency_cycles: int
    bound_steps: int | None
    reason: str | None


@dataclass(frozen=True)
class _HarnessFacts:
    module_name: str
    ports: tuple[str, ...]
    cdc_evidence: tuple[_CDCPathEvidence, ...]
    clock_name: str
    reset_name: str | None
    reset_active_low: bool
    qualified_reset_values: dict[str, str]
    scalar_inputs: tuple[str, ...]
    connected_ports: tuple[str, ...]
    unconnected_outputs: tuple[str, ...]
    reset_zero_outputs: tuple[str, ...]
    increment_checks: tuple[tuple[str, str], ...]
    hold_checks: tuple[tuple[str, str], ...]
    checked_outputs: tuple[str, ...]


class FormalGenerator:
    """Generate evidence-backed SymbiYosys collateral from a plan."""

    target = VerificationTarget.FORMAL

    def __init__(
        self,
        cdc_policy: CDCProofPolicy | str = CDCProofPolicy.FAIL_CLOSED,
        cdc_bmc_depth: int = 20,
    ) -> None:
        self.cdc_policy = CDCProofPolicy(cdc_policy)
        if cdc_bmc_depth <= 0:
            raise ValueError("CDC BMC depth must be greater than zero")
        self.cdc_bmc_depth = cdc_bmc_depth

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        refs = provenance_refs(plan)
        module_name = _safe_identifier(plan.module)
        cdc_evidence = _cdc_evidence(plan, self.cdc_policy, self.cdc_bmc_depth)
        if self.cdc_policy == CDCProofPolicy.STRUCTURAL:
            unsupported = tuple(item for item in cdc_evidence if item.evidence_level == "unsupported")
            if unsupported:
                details = "; ".join(f"{item.path_id}: {item.reason}" for item in unsupported)
                raise ValueError(f"Structural CDC policy requirements are not met: {details}")
        harness_presentation = _harness_presentation(plan, cdc_evidence)
        harness_presentation["_plan"] = plan
        harness_presentation["header"] = protocol_mapping_header(plan, self.target)
        sby_presentation = _sby_presentation(
            plan,
            bounded_cdc=any(item.evidence_level == "bounded" for item in cdc_evidence),
            multiclock=any(item.evidence_level in {"bounded", "structural"} for item in cdc_evidence),
            cdc_bmc_depth=self.cdc_bmc_depth,
        )
        sby_presentation["_plan"] = plan
        sby_presentation["header"] = _sby_mapping_header(plan)
        artifacts = [
            GeneratedArtifact(
                path=Path(f"formal_{module_name}.sv"),
                kind=ArtifactKind.FORMAL_HARNESS,
                target=self.target,
                content=render_target("formal", harness_presentation),  # type: ignore[arg-type]
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=_quality_requirements(plan, cdc_evidence),
                traceability=_formal_traceability(plan, f"formal_{module_name}_properties"),
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}.sby"),
                kind=ArtifactKind.RUN_SCRIPT,
                target=self.target,
                content=render_target("formal", sby_presentation),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=_quality_requirements(plan, cdc_evidence),
                traceability=_formal_traceability(plan, f"formal_{module_name}_run"),
            ),
        ]
        if plan.cdc_paths:
            report_presentation = {
                "_plan": plan,
                "artifact_kind": "report",
                "header": "",
                "payload": _cdc_report_payload(plan, self.cdc_policy, self.cdc_bmc_depth, cdc_evidence),
            }
            artifacts.append(
                GeneratedArtifact(
                    path=Path(f"formal_{module_name}_cdc.json"),
                    kind=ArtifactKind.REPORT,
                    target=self.target,
                    content=render_target("formal", report_presentation),  # type: ignore[arg-type]
                    source_plan_module=plan.module,
                    design_unit=plan.design_unit or plan.module,
                    elaborated_design_unit=plan.elaborated_design_unit,
                    specialization_id=plan.specialization_id,
                    elaborated_parameters=plan.parameters,
                    provenance_refs=refs,
                    traceability=_cdc_report_traceability(plan, f"formal_{module_name}_cdc_evidence"),
                )
            )
        return artifacts


def _formal_traceability(plan: VerificationPlan, fallback_symbol: str) -> tuple[ArtifactTrace, ...]:
    scenario_traces = tuple(
        trace
        for scenario in plan.scenarios
        if scenario.kind.startswith(
            ("apb4_", "axi4_lite_", "cdc_", "reset_domain_", "uart_", "spi_", "i2c_", "gpio_timer_interrupt_")
        )
        and scenario_is_executable(scenario, VerificationTarget.FORMAL)
        for trace in artifact_trace_for_scenario(
            plan,
            scenario,
            f"formal_{_safe_identifier(plan.module)}_scenario_{scenario.scenario_id.rsplit(':', 1)[-1]}",
        )
    )
    fallback_traces = artifact_trace(
        plan,
        fallback_symbol,
        target=VerificationTarget.FORMAL,
        categories=("reset", "increment", "hold", "protocol", "memory", "cdc", "formal"),
    )
    return tuple({trace.trace_id: trace for trace in (*scenario_traces, *fallback_traces)}.values())


def _cdc_report_traceability(plan: VerificationPlan, symbol: str) -> tuple[ArtifactTrace, ...]:
    traces = artifact_trace(
        plan,
        symbol,
        target=VerificationTarget.FORMAL,
        categories=("cdc",),
    )
    return tuple(trace for trace in traces if trace.check_ids)


def _sby_mapping_header(plan: VerificationPlan) -> str:
    if not plan.protocol_models and not plan.register_models:
        return ""
    lines = ["# Deterministic protocol/register mappings for formal."]
    lines.extend(f"# protocol={protocol.name}" for protocol in plan.protocol_models)
    lines.extend(f"# register={register.name}" for register in plan.register_models)
    return "\n".join(lines) + "\n\n"


def _harness_clock_name(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    evidence: tuple[_CDCPathEvidence, ...],
) -> str:
    cdc_clocks = {
        item.clock for item in evidence if item.evidence_level in {"structural", "bounded"} and item.clock in ports
    }
    primary = (
        primary_clock_name(plan, ports)
        or (plan.protocol_models[0].clock_domain if plan.protocol_models else None)
        or "clk"
    )
    alternate = next(
        (
            port
            for port in ports
            if port not in cdc_clocks
            and any(clock.name == port and clock.direction == "input" for clock in plan.clocks)
        ),
        None,
    )
    has_reset_scenarios = any(
        scenario.kind == "reset_domain_sequence" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
        for scenario in plan.scenarios
    )
    if has_reset_scenarios:
        return "dv_formal_clock"
    if cdc_clocks and primary in cdc_clocks:
        return alternate or "dv_formal_clock"
    return primary


def _qualified_reset_values(plan: VerificationPlan) -> dict[str, str]:
    return {
        policy.subject: ("1'b1" if policy.subject.endswith("_n") else "1'b0")
        for policy in plan.depth_policies
        if policy.kind == "reset"
        and any(
            scenario.kind == "reset_domain_sequence"
            and dict(scenario.stimulus[0].parameters).get("reset") == policy.subject
            and scenario_is_executable(scenario, VerificationTarget.FORMAL)
            for scenario in plan.scenarios
        )
    }


def _checked_outputs(
    plan: VerificationPlan,
    unconnected_outputs: tuple[str, ...],
    reset_zero_outputs: tuple[str, ...],
    increment_checks: tuple[tuple[str, str], ...],
    hold_checks: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *reset_zero_outputs,
                *(output for output, _input in increment_checks),
                *(output for output, _input in hold_checks),
                *(
                    signal
                    for protocol in plan.protocols
                    if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source"
                    for signal in (protocol.valid, protocol.data)
                    if signal is not None
                ),
                *(stage for path in plan.cdc_paths for stage in path.stage_signals if stage in unconnected_outputs),
                *(_async_fifo_output_signals(plan)),
                *(_reset_domain_output_signals(plan)),
                *(_bounded_sram_output_signals(plan)),
                *(_formal_contract_output_signals(plan)),
                *(formal_peripheral_output_signals(plan)),
                *(
                    actual
                    for protocol in plan.protocol_models
                    for canonical, actual in protocol.signal_bindings
                    if dict(protocol.signal_directions).get(canonical) == "output"
                ),
            )
        )
    )


def _reset_is_active_low(reset: RTLReset | None, reset_name: str | None) -> bool:
    if reset is not None and reset.active_low is not None:
        return reset.active_low
    return bool(reset_name and reset_name.endswith("_n"))


def _harness_declarations(
    clock_name: str,
    reset_name: str | None,
    reset_active_low: bool,
    scalar_inputs: tuple[str, ...],
    checked_outputs: tuple[str, ...],
    input_declarations: dict[str, str],
    output_declarations: dict[str, str],
) -> list[str]:
    lines = ["    (* gclk *) reg " + clock_name + ";"]
    if reset_name:
        reset_initial = "1'b0" if reset_active_low else "1'b1"
        lines.append("    reg " + reset_name + " = " + reset_initial + ";")
    lines.extend("    " + input_declarations.get(name, "reg " + name) + " = '0;" for name in scalar_inputs)
    lines.extend("    " + output_declarations.get(name, "wire " + name) + ";" for name in checked_outputs)
    return lines


def _harness_content(
    plan: VerificationPlan,
    cdc_evidence: tuple[_CDCPathEvidence, ...] | None = None,
) -> str:
    presentation = _harness_presentation(plan, cdc_evidence)
    presentation["_plan"] = plan
    presentation["header"] = ""
    return render_target("formal", presentation)  # type: ignore[arg-type]


def _harness_presentation(
    plan: VerificationPlan,
    cdc_evidence: tuple[_CDCPathEvidence, ...] | None = None,
) -> dict[str, object]:
    facts = _harness_facts(plan, cdc_evidence)
    declarations, port_connections = _harness_structure(plan, facts)
    if facts.reset_name:
        clock_body, cover_expression = _reset_clock_body(plan, facts)
    else:
        clock_body, cover_expression = _unreset_clock_body(plan, facts)
    clock_body.append("        cover(" + cover_expression + ");")
    trailing_assertions = [
        *_cdc_assertions(plan, facts.cdc_evidence),
        *_async_fifo_assertions(plan),
        *_reset_domain_assertions(plan),
    ]
    return {
        "artifact_kind": "harness",
        "module": plan.module,
        "harness_name": f"formal_{facts.module_name}",
        "declarations": declarations,
        "design_unit": plan.design_unit or plan.module,
        "parameter_clause": sv_parameter_clause(plan),
        "connections": _comma_terminate(port_connections),
        "clock_name": facts.clock_name,
        "clock_body": clock_body,
        "trailing_assertions": trailing_assertions,
    }


def _harness_facts(
    plan: VerificationPlan,
    cdc_evidence: tuple[_CDCPathEvidence, ...] | None,
) -> _HarnessFacts:
    ports = _port_names_from_plan(plan)
    resolved_cdc_evidence = cdc_evidence or _cdc_evidence(plan, CDCProofPolicy.FAIL_CLOSED, 20)
    clock_name = _harness_clock_name(plan, ports, resolved_cdc_evidence)
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    reset_active_low = _reset_is_active_low(reset, reset_name)
    qualified_reset_values = _qualified_reset_values(plan)
    scalar_inputs = _input_ports(plan, ports, clock_name, reset_name)
    connected_ports = tuple(
        dict.fromkeys(
            (*(port for port in (clock_name if clock_name in ports else None, reset_name) if port), *scalar_inputs)
        )
    )
    unconnected_outputs = _output_ports(plan, ports)
    generic_outputs = tuple(port for port in unconnected_outputs if port not in peripheral_mapped_outputs(plan))
    reset_zero_outputs = _reset_zero_outputs(plan, generic_outputs, reset_name)
    increment_checks = _increment_checks(plan, generic_outputs, scalar_inputs)
    hold_checks = _hold_checks(plan, generic_outputs, scalar_inputs)
    checked_outputs = _checked_outputs(
        plan,
        unconnected_outputs,
        reset_zero_outputs,
        increment_checks,
        hold_checks,
    )
    return _HarnessFacts(
        _safe_identifier(plan.module),
        ports,
        resolved_cdc_evidence,
        clock_name,
        reset_name,
        reset_active_low,
        qualified_reset_values,
        scalar_inputs,
        connected_ports,
        unconnected_outputs,
        reset_zero_outputs,
        increment_checks,
        hold_checks,
        checked_outputs,
    )


def _harness_structure(
    plan: VerificationPlan,
    facts: _HarnessFacts,
) -> tuple[list[str], list[str]]:
    input_declarations = _input_reg_declarations(plan, facts.scalar_inputs)
    output_declarations = _output_wire_declarations(plan, facts.checked_outputs)
    declarations = _harness_declarations(
        facts.clock_name,
        facts.reset_name,
        facts.reset_active_low,
        facts.scalar_inputs,
        facts.checked_outputs,
        input_declarations,
        output_declarations,
    )
    declarations.extend(formal_apb4_declarations(plan))
    declarations.extend(formal_axi4_lite_declarations(plan))
    declarations.extend(formal_ahb_lite_declarations(plan))
    declarations.extend(formal_profile_declarations(plan))
    declarations.extend(_bounded_sram_declarations(plan))
    declarations.extend(_formal_contract_declarations(plan))
    port_connections = ["        ." + name + "(" + name + ")" for name in facts.connected_ports]
    port_connections.extend(
        "        ." + name + "(" + name + ")" if name in facts.checked_outputs else "        ." + name + "()"
        for name in facts.unconnected_outputs
    )
    return declarations, port_connections


def _reset_clock_body(
    plan: VerificationPlan,
    facts: _HarnessFacts,
) -> tuple[list[str], str]:
    reset_name = facts.reset_name
    assert reset_name is not None
    reset_active = "1'b0" if facts.reset_active_low else "1'b1"
    reset_inactive = "1'b1" if facts.reset_active_low else "1'b0"
    clock_body: list[str] = []
    clock_body.extend(
        [
            "        if ($initstate) begin",
            "            assume(" + reset_name + " == " + reset_active + ");",
            "        end else begin",
            "            assume(" + reset_name + " == " + reset_inactive + ");",
            "        end",
            "        " + reset_name + " <= " + facts.qualified_reset_values.get(reset_name, "$anyseq") + ";",
            "        c_reset_asserted: cover(" + reset_name + " == " + reset_active + ");",
            "        c_reset_released: cover(!$initstate && " + reset_name + " == " + reset_inactive + ");",
        ]
    )
    clock_body.extend(
        "        " + name + " <= " + facts.qualified_reset_values.get(name, "$anyseq") + ";"
        for name in facts.scalar_inputs
    )
    clock_body.extend(_reset_behavior_assertions(facts, reset_active, reset_inactive))
    clock_body.extend(_ready_valid_assertions(plan, reset_name, reset_inactive))
    clock_body.extend(formal_apb4_assertions(plan, reset_name, reset_active, reset_inactive))
    clock_body.extend(formal_axi4_lite_assertions(plan, reset_name, reset_active, reset_inactive))
    clock_body.extend(formal_ahb_lite_assertions(plan, reset_name, reset_active, reset_inactive))
    clock_body.extend(formal_profile_assertions(plan, reset_name, reset_active))
    clock_body.extend(_memory_write_assertions(plan, reset_name, reset_inactive, facts.clock_name))
    clock_body.extend(_memory_collision_assertions(plan, reset_name, reset_inactive, facts.clock_name))
    clock_body.extend(_bounded_sram_assertions(plan, reset_name, reset_active, reset_inactive, facts.clock_name))
    clock_body.extend(_formal_contract_assertions(plan, reset_name, reset_active, reset_inactive, facts.clock_name))
    clock_body.extend(_formal_assumption_assertions(plan, reset_name, reset_active, reset_inactive, facts.clock_name))
    clock_body.extend(formal_peripheral_assertions(plan, reset_name, reset_active, reset_inactive))
    cover_expression = reset_name + " == " + reset_inactive
    if facts.scalar_inputs:
        joined_inputs = " || ".join(facts.scalar_inputs)
        cover_expression += " && " + (f"({joined_inputs})" if len(facts.scalar_inputs) > 1 else joined_inputs)
    return clock_body, cover_expression


def _reset_behavior_assertions(
    facts: _HarnessFacts,
    reset_active: str,
    reset_inactive: str,
) -> list[str]:
    assert facts.reset_name is not None
    lines: list[str] = []
    for name in facts.reset_zero_outputs:
        lines.extend(
            (
                f"        if (!$initstate && $past({facts.reset_name} == {reset_active})) begin",
                f"            assert({name} == '0);",
                "        end",
            )
        )
    for output_name, input_name in facts.increment_checks:
        condition = (
            f"$past({facts.reset_name} == {reset_inactive}) && "
            f"{facts.reset_name} == {reset_inactive} && $past({input_name})"
        )
        lines.extend(
            (
                f"        if (!$initstate && {condition}) begin",
                f"            assert({output_name} == $past({output_name}) + 1'b1);",
                "        end",
            )
        )
    for output_name, input_name in facts.hold_checks:
        condition = (
            f"$past({facts.reset_name} == {reset_inactive}) && "
            f"{facts.reset_name} == {reset_inactive} && !$past({input_name})"
        )
        lines.extend(
            (
                f"        if (!$initstate && {condition}) begin",
                f"            assert({output_name} == $past({output_name}));",
                "        end",
            )
        )
    return lines


def _unreset_clock_body(
    plan: VerificationPlan,
    facts: _HarnessFacts,
) -> tuple[list[str], str]:
    lines = [
        "        " + name + " <= " + facts.qualified_reset_values.get(name, "$anyseq") + ";"
        for name in facts.scalar_inputs
    ]
    for output_name, input_name in facts.increment_checks:
        lines.extend(
            (
                f"        if (!$initstate && $past({input_name})) begin",
                f"            assert({output_name} == $past({output_name}) + 1'b1);",
                "        end",
            )
        )
    for output_name, input_name in facts.hold_checks:
        lines.extend(
            (
                f"        if (!$initstate && !$past({input_name})) begin",
                f"            assert({output_name} == $past({output_name}));",
                "        end",
            )
        )
    lines.extend(_ready_valid_assertions(plan, None, None))
    lines.extend(formal_apb4_assertions(plan, None, None, None))
    lines.extend(formal_ahb_lite_assertions(plan, None, None, None))
    lines.extend(formal_profile_assertions(plan, None, None))
    lines.extend(_memory_write_assertions(plan, None, None, facts.clock_name))
    lines.extend(_memory_collision_assertions(plan, None, None, facts.clock_name))
    lines.extend(_bounded_sram_assertions(plan, None, None, None, facts.clock_name))
    lines.extend(_formal_contract_assertions(plan, None, None, None, facts.clock_name))
    lines.extend(_formal_assumption_assertions(plan, None, None, None, facts.clock_name))
    lines.extend(formal_peripheral_assertions(plan, None, None, None))
    cover_expression = " || ".join(facts.scalar_inputs) if facts.scalar_inputs else "!$initstate"
    return lines, cover_expression


for _legacy_class in (
    CDCProofPolicy,
    _CDCPathEvidence,
    FormalGenerator,
):
    _legacy_class.__module__ = "dv_platform.generators.formal"
del _legacy_class
