"""VHDL protocol access generation."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.protocols.common import (
    _profile_drive_value,
    _profile_handshake_specs,
)
from dv_platform.generators.scenario_registry import scenario_is_executable


def vhdl_protocol_accesses(plan: VerificationPlan, clock_name: str | None) -> tuple[str, ...]:
    """Emit bounded typed VHDL transactions for every executable profile."""

    if not plan.protocol_models or clock_name is None:
        return ()
    executable_instances = {
        dict(stimulus.parameters).get("instance_id")
        for scenario in plan.scenarios
        if scenario.kind == "protocol_profile_transaction" and scenario_is_executable(scenario, VerificationTarget.VHDL)
        for stimulus in scenario.stimulus
        if stimulus.kind == "protocol_profile"
    }
    lines: list[str] = []
    for model in plan.protocol_models:
        lines.extend(_vhdl_profile_accesses(plan, clock_name, model, executable_instances))
    if not lines:
        model = plan.protocol_models[0]
        directions = dict(model.signal_directions)
        bindings = dict(model.signal_bindings)
        assignments = {
            "APB4": (("psel", 1), ("penable", 0), ("pwrite", 1)),
            "AHB-Lite": (("hsel", 1), ("hwrite", 1), ("htrans", 0)),
            "AXI4-Lite": (("awvalid", 1), ("wvalid", 1)),
        }.get(model.name, ())
        if assignments:
            lines.append("        -- Executable mapped protocol/register access.")
            for canonical, value in assignments:
                legacy_actual = bindings.get(canonical)
                if legacy_actual and directions.get(canonical) in {"input", "inout", "ref"}:
                    lines.append(f"        {legacy_actual} <= {_vhdl_profile_literal(plan, legacy_actual, value)};")
            lines.append(f"        wait until rising_edge({clock_name});")
            if model.name == "APB4":
                penable = bindings.get("penable")
                if penable and directions.get("penable") in {"input", "inout", "ref"}:
                    lines.append(f"        {penable} <= {_vhdl_profile_literal(plan, penable, 1)};")
                lines.append(f"        wait until rising_edge({clock_name});")
    return tuple(lines)


def _vhdl_profile_accesses(
    plan: VerificationPlan,
    clock_name: str,
    model: ProtocolModel,
    executable_instances: set[str | None],
) -> tuple[str, ...]:
    lines: list[str] = []
    if (model.instance_id or model.profile_id or model.name) not in executable_instances:
        return ()
    directions = dict(model.signal_directions)
    bindings = dict(model.signal_bindings)
    specs = _profile_handshake_specs(model)
    if not specs:
        return ()
    lines.append(f"        -- Executable {model.profile_id or model.name} transaction profile.")
    valid_names = {valid for valid, _ready, _accepted in specs}
    for canonical, actual in model.signal_bindings:
        if directions.get(canonical) not in {"input", "inout", "ref"}:
            continue
        value = 0 if canonical in valid_names or canonical == "cyc" else _profile_drive_value(canonical)
        lines.append(f"        {actual} <= {_vhdl_profile_literal(plan, actual, value)};")
    lines.append(f"        wait until rising_edge({clock_name});")
    for valid_name, ready_name, accepted in specs:
        valid, ready = bindings[valid_name], bindings[ready_name]
        valid_is_output = directions.get(valid_name) == "output"
        accepted_literal = _vhdl_profile_literal(plan, ready, accepted)
        if valid_is_output:
            if directions.get(ready_name) in {"input", "inout", "ref"}:
                lines.append(f"        {ready} <= {accepted_literal};")
            observed, expected = valid, _vhdl_profile_literal(plan, valid, 1)
        else:
            lines.append(f"        {valid} <= {_vhdl_profile_literal(plan, valid, 1)};")
            if model.profile_id == "wishbone-b4-1.0" and "cyc" in bindings:
                lines.append(f"        {bindings['cyc']} <= {_vhdl_profile_literal(plan, bindings['cyc'], 1)};")
            observed, expected = ready, accepted_literal
        lines.extend(
            (
                "        dv_protocol_cycles := 0;",
                f"        while {observed} /= {expected} and dv_protocol_cycles < {model.timeout_cycles} loop",
                f"            wait until rising_edge({clock_name});",
                "            dv_protocol_cycles := dv_protocol_cycles + 1;",
                "        end loop;",
                f"        if {observed} /= {expected} then",
                "            dv_platform_failures := dv_platform_failures + 1;",
                f'            report "{model.profile_id or model.name} handshake timed out" severity error;',
                "        end if;",
                f"        wait until rising_edge({clock_name});",
            )
        )
        lines.extend(_vhdl_profile_completion_check(plan, model, valid_name, bindings, directions))
        if not valid_is_output:
            lines.append(f"        {valid} <= {_vhdl_profile_literal(plan, valid, 0)};")
    lines.extend(_vhdl_profile_semantics(plan, model, bindings, directions))
    return tuple(lines)


def _vhdl_profile_completion_check(
    plan: VerificationPlan,
    model: ProtocolModel,
    valid_name: str,
    bindings: dict[str, str],
    directions: dict[str, str],
) -> tuple[str, ...]:
    """Check profile-specific completion responses after acceptance."""

    if model.profile_id == "wishbone-b4-1.0":
        response = next((name for name in ("ack", "err", "rty") if name in bindings), None)
    elif model.profile_id == "avalon-mm-1.0":
        response = "readdatavalid" if valid_name == "read" else "writeresponsevalid"
        if response not in bindings:
            response = None
    else:
        response = None
    if response is None or directions.get(response) != "output":
        return ()
    actual = bindings[response]
    expected = _vhdl_profile_literal(plan, actual, 1)
    return (
        "        wait for 1 ns;",
        f"        if {actual} /= {expected} then",
        "            dv_platform_failures := dv_platform_failures + 1;",
        f'            report "{model.profile_id or model.name} completion response missing" severity error;',
        "        end if;",
    )


def _vhdl_profile_semantics(
    plan: VerificationPlan,
    model: ProtocolModel,
    bindings: dict[str, str],
    directions: dict[str, str],
) -> tuple[str, ...]:
    lines: list[str] = []
    for canonical in ("tkeep", "a_mask"):
        mask_actual = bindings.get(canonical)
        if mask_actual and directions.get(canonical) == "output":
            zero = _vhdl_profile_literal(plan, mask_actual, 0)
            lines.extend(
                (
                    f"        if {mask_actual} = {zero} then",
                    "            dv_platform_failures := dv_platform_failures + 1;",
                    f'            report "{model.profile_id or model.name} emitted an empty byte mask" severity error;',
                    "        end if;",
                )
            )
    for canonical in ("tlast", "endofpacket"):
        last_actual = bindings.get(canonical)
        if last_actual and directions.get(canonical) == "output":
            one = _vhdl_profile_literal(plan, last_actual, 1)
            lines.extend(
                (
                    f"        if {last_actual} /= {one} then",
                    "            dv_platform_failures := dv_platform_failures + 1;",
                    f'            report "{model.profile_id or model.name} did not terminate the bounded packet" severity error;',
                    "        end if;",
                )
            )
    if all(name in bindings for name in ("tstrb", "tkeep")) and all(
        directions.get(name) == "output" for name in ("tstrb", "tkeep")
    ):
        illegal = _vhdl_profile_literal(plan, bindings["tstrb"], 0)
        lines.extend(
            (
                f"        if ({bindings['tstrb']} and not {bindings['tkeep']}) /= {illegal} then",
                "            dv_platform_failures := dv_platform_failures + 1;",
                f'            report "{model.profile_id or model.name} asserted TSTRB outside TKEEP" severity error;',
                "        end if;",
            )
        )
    return tuple(lines)


def _vhdl_profile_literal(plan: VerificationPlan, actual: str, value: int) -> str:
    port = next((item for item in plan.ports if item.name == actual), None)
    if port is None or port.width in {None, 1}:
        return f"'{1 if value else 0}'"
    if value == 0:
        return f"({actual}'range => '0')"
    if value == 1:
        return f"std_logic_vector(to_unsigned(1, {port.width}))"
    return f"std_logic_vector(to_unsigned({value}, {port.width}))"
