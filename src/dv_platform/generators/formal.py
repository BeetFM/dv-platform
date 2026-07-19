"""Formal generator backend."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    GeneratedArtifact,
    RTLPort,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.signals import (
    artifact_trace,
    primary_clock_name,
    primary_reset,
    provenance_refs,
    safe_parameter_value,
    sv_parameter_clause,
)


class FormalGenerator:
    """Generate evidence-backed SymbiYosys collateral from a plan."""

    target = VerificationTarget.FORMAL

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        refs = provenance_refs(plan)
        module_name = _safe_identifier(plan.module)
        return [
            GeneratedArtifact(
                path=Path(f"formal_{module_name}.sv"),
                kind=ArtifactKind.FORMAL_HARNESS,
                target=self.target,
                content=_harness_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=_quality_requirements(plan),
                traceability=artifact_trace(
                    plan,
                    f"formal_{module_name}_properties",
                    categories=("reset", "increment", "hold", "protocol", "memory"),
                ),
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}.sby"),
                kind=ArtifactKind.RUN_SCRIPT,
                target=self.target,
                content=_sby_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=_quality_requirements(plan),
                traceability=artifact_trace(
                    plan,
                    f"formal_{module_name}_run",
                    categories=("reset", "increment", "hold", "protocol", "memory"),
                ),
            ),
        ]


def _harness_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    harness_name = f"formal_{module_name}"
    ports = _port_names_from_plan(plan)
    clock_name = primary_clock_name(plan, ports) or "clk"
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    reset_active_low = (
        reset.active_low
        if reset is not None and reset.active_low is not None
        else bool(reset_name and reset_name.endswith("_n"))
    )
    scalar_inputs = _input_ports(plan, ports, clock_name, reset_name)
    connected_ports = tuple(dict.fromkeys((clock_name, *(port for port in (reset_name, *scalar_inputs) if port))))
    unconnected_outputs = _output_ports(plan, ports)
    reset_zero_outputs = _reset_zero_outputs(plan, unconnected_outputs, reset_name)
    increment_checks = _increment_checks(plan, unconnected_outputs, scalar_inputs)
    hold_checks = _hold_checks(plan, unconnected_outputs, scalar_inputs)
    checked_outputs = tuple(
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
            )
        )
    )
    output_declarations = _output_wire_declarations(plan, checked_outputs)

    lines = [
        "// Generated formal harness for " + plan.module + ".",
        "`default_nettype none",
        "",
        "module " + harness_name + ";",
        "    (* gclk *) reg " + clock_name + ";",
    ]
    if reset_name:
        reset_initial = "1'b0" if reset_active_low else "1'b1"
        lines.append("    reg " + reset_name + " = " + reset_initial + ";")
    input_declarations = _input_reg_declarations(plan, scalar_inputs)
    for name in scalar_inputs:
        lines.append("    " + input_declarations.get(name, "reg " + name) + " = '0;")
    for name in checked_outputs:
        lines.append("    " + output_declarations.get(name, "wire " + name) + ";")

    parameter_clause = sv_parameter_clause(plan)
    lines.extend(["", "    " + (plan.design_unit or plan.module) + parameter_clause + " dut ("])
    port_connections = ["        ." + name + "(" + name + ")" for name in connected_ports]
    port_connections.extend(
        "        ." + name + "(" + name + ")" if name in checked_outputs else "        ." + name + "()"
        for name in unconnected_outputs
    )
    lines.extend(_comma_terminate(port_connections))
    lines.extend(["    );", ""])

    lines.extend(["    always @(posedge " + clock_name + ") begin"])
    if reset_name:
        reset_active = "1'b0" if reset_active_low else "1'b1"
        reset_inactive = "1'b1" if reset_active_low else "1'b0"
        lines.extend(
            [
                "        if ($initstate) begin",
                "            assume(" + reset_name + " == " + reset_active + ");",
                "        end else begin",
                "            assume(" + reset_name + " == " + reset_inactive + ");",
                "        end",
                "        " + reset_name + " <= $anyseq;",
            ]
        )
        for name in scalar_inputs:
            lines.append("        " + name + " <= $anyseq;")
        for name in reset_zero_outputs:
            lines.extend(
                [
                    "        if (!$initstate && $past(" + reset_name + " == " + reset_active + ")) begin",
                    "            assert(" + name + " == '0);",
                    "        end",
                ]
            )
        for output_name, input_name in increment_checks:
            lines.extend(
                [
                    "        if (!$initstate && $past("
                    + reset_name
                    + " == "
                    + reset_inactive
                    + ") && "
                    + reset_name
                    + " == "
                    + reset_inactive
                    + " && $past("
                    + input_name
                    + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + ") + 1'b1);",
                    "        end",
                ]
            )
        for output_name, input_name in hold_checks:
            lines.extend(
                [
                    "        if (!$initstate && $past("
                    + reset_name
                    + " == "
                    + reset_inactive
                    + ") && "
                    + reset_name
                    + " == "
                    + reset_inactive
                    + " && !$past("
                    + input_name
                    + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + "));",
                    "        end",
                ]
            )
        lines.extend(_ready_valid_assertions(plan, reset_name, reset_inactive))
        lines.extend(_memory_write_assertions(plan, reset_name, reset_inactive, clock_name))
        cover_terms = [reset_name + " == " + reset_inactive, *scalar_inputs]
    else:
        for name in scalar_inputs:
            lines.append("        " + name + " <= $anyseq;")
        for output_name, input_name in increment_checks:
            lines.extend(
                [
                    "        if (!$initstate && $past(" + input_name + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + ") + 1'b1);",
                    "        end",
                ]
            )
        for output_name, input_name in hold_checks:
            lines.extend(
                [
                    "        if (!$initstate && !$past(" + input_name + ")) begin",
                    "            assert(" + output_name + " == $past(" + output_name + "));",
                    "        end",
                ]
            )
        lines.extend(_ready_valid_assertions(plan, None, None))
        lines.extend(_memory_write_assertions(plan, None, None, clock_name))
        cover_terms = list(scalar_inputs)

    if cover_terms:
        lines.append("        cover(" + " && ".join(cover_terms) + ");")
    else:
        lines.append("        cover(!$initstate);")
    lines.extend(["    end", "", "endmodule", "`default_nettype wire"])
    return "\n".join(lines) + "\n"


def _sby_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    harness_name = f"formal_{module_name}"
    depth = _proof_depth(plan)
    return "\n".join(
        [
            "[tasks]",
            "prove",
            "cover",
            "",
            "[options]",
            "prove: mode prove",
            "cover: mode cover",
            f"depth {depth}",
            "",
            "[engines]",
            "smtbmc z3",
            "",
            "[script]",
            f"read -formal formal_{module_name}.sv",
            "# RTL source files are supplied by the formal runner from the execution manifest.",
            f"prep -top {harness_name}",
            "",
            "[files]",
            f"formal_{module_name}.sv",
            "",
        ]
    )


def _proof_depth(plan: VerificationPlan) -> int:
    latency_cycles = [
        int(requirement.expected_value.split()[0])
        for requirement in plan.structured_requirements
        if requirement.category == "latency"
        and requirement.expected_value is not None
        and requirement.expected_value.split()[0].isdigit()
    ]
    return max((20, *(cycle + 5 for cycle in latency_cycles)))


def _quality_requirements(plan: VerificationPlan) -> tuple[ArtifactQualityRequirement, ...]:
    ports = _port_names_from_plan(plan)
    clock_name = primary_clock_name(plan, ports) or "clk"
    reset = primary_reset(plan, ports)
    reset_name = reset.name if reset is not None else None
    scalar_inputs = _scalar_input_ports(plan, ports, clock_name, reset_name)
    output_ports = _output_ports(plan, ports)
    reset_checks = _reset_zero_outputs(plan, output_ports, reset_name)
    increment_checks = _increment_checks(plan, output_ports, scalar_inputs)
    hold_checks = _hold_checks(plan, output_ports, scalar_inputs)
    protocol_checks = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source"
    )
    memory_checks = tuple(
        access
        for access in plan.memory_accesses
        if access.kind == "write"
        and access.synchronous
        and len(access.address_signals) == 1
        and len(access.data_signals) == 1
        and bool(access.enable_signals)
    )
    has_sequential_checks = bool(increment_checks or hold_checks or protocol_checks)
    has_backed_checks = bool(reset_checks or increment_checks or hold_checks or protocol_checks or memory_checks)
    port_names = tuple(port.name for port in plan.ports)
    directions = {port.direction for port in plan.ports}
    return (
        ArtifactQualityRequirement(
            requirement_id="structured_ports",
            description="Executable formal harnesses require structured port metadata.",
            satisfied=bool(plan.ports),
            reason=None if plan.ports else "plan has no structured ports",
        ),
        ArtifactQualityRequirement(
            requirement_id="unambiguous_port_directions",
            description="Executable formal harnesses require unique input/output port directions.",
            satisfied=bool(plan.ports)
            and len(set(port_names)) == len(port_names)
            and {"input", "output"}.issubset(directions)
            and all(port.direction in {"input", "output", "inout", "ref"} for port in plan.ports),
            reason="ports are missing, duplicated, or lack valid directions",
        ),
        ArtifactQualityRequirement(
            requirement_id="backed_executable_checks",
            description="Executable formal harness must contain assertions backed by plan behaviors or requirements.",
            satisfied=has_backed_checks and bool(plan.behaviors or plan.structured_requirements),
            reason="no reset, state-transition, or protocol assertion is backed by structured evidence",
        ),
        ArtifactQualityRequirement(
            requirement_id="clock_for_sequential_checks",
            description="Sequential formal assertions require a known clock input.",
            satisfied=not has_sequential_checks
            or any(port.name == clock_name and port.direction == "input" for port in plan.ports),
            reason="increment/hold assertions were generated without a structured clock input",
        ),
        ArtifactQualityRequirement(
            requirement_id="unambiguous_control_domains",
            description="Generated formal properties require a single classified clock and reset domain.",
            satisfied=len(plan.clocks) <= 1 and len(plan.resets) <= 1,
            reason="multi-clock or multi-reset behavior lacks an explicit property-to-domain mapping",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_parameter_values",
            description="Formal generation requires safely renderable numeric elaborated parameters.",
            satisfied=all(
                parameter.local or parameter.default_value is None or safe_parameter_value(parameter.default_value)
                for parameter in plan.parameters
            ),
            reason="an elaborated parameter is not a supported numeric literal",
        ),
        ArtifactQualityRequirement(
            requirement_id="supported_semantic_features",
            description="Formal generation must not guess unsupported RTL semantics.",
            satisfied=all(feature.supports_target(VerificationTarget.FORMAL) for feature in plan.semantic_features),
            reason="the plan contains unsupported semantic features",
        ),
    )


def _port_names_from_plan(plan: VerificationPlan) -> tuple[str, ...]:
    if plan.ports:
        return tuple(port.name for port in plan.ports)
    ports: list[str] = []
    prefix = f"port:{plan.module}."
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            locator = ref.locator.split("@", 1)[0]
            if locator.startswith(prefix):
                ports.append(locator.removeprefix(prefix))
    return tuple(dict.fromkeys(ports))


def _structured_ports(plan: VerificationPlan) -> dict[str, RTLPort]:
    return {port.name: port for port in plan.ports}


def _input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str | None,
) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        excluded = {clock_name}
        if reset_name:
            excluded.add(reset_name)
        return tuple(port.name for port in plan.ports if port.direction == "input" and port.name not in excluded)
    return tuple(port for port in ports if _looks_like_scalar_input(port) and port != clock_name and port != reset_name)


def _scalar_input_ports(
    plan: VerificationPlan,
    ports: tuple[str, ...],
    clock_name: str,
    reset_name: str | None,
) -> tuple[str, ...]:
    """Compatibility alias retained for existing generator helper tests."""

    return _input_ports(plan, ports, clock_name, reset_name)


def _output_ports(plan: VerificationPlan, ports: tuple[str, ...]) -> tuple[str, ...]:
    structured_ports = _structured_ports(plan)
    if structured_ports:
        return tuple(port.name for port in plan.ports if port.direction == "output")
    return tuple(port for port in ports if _looks_like_output(port))


def _clock_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (port for port in ports if port in {"clk", "clock"} or port.endswith("_clk") or port.endswith("_clock")), None
    )


def _reset_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (
            port
            for port in ports
            if port in {"rst", "reset", "rst_n", "reset_n"} or port.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
        ),
        None,
    )


def _reset_active_low(reset_name: str) -> bool:
    return reset_name.endswith("_n")


def _reset_zero_outputs(
    plan: VerificationPlan, output_ports: tuple[str, ...], reset_name: str | None
) -> tuple[str, ...]:
    if not reset_name:
        return ()
    behavior_outputs = tuple(
        behavior.target
        for behavior in plan.behaviors
        if behavior.kind == "reset_to_constant"
        and behavior.target in output_ports
        and behavior.control == reset_name
        and _is_zero_value(behavior.value)
    )
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text:
        return tuple(dict.fromkeys(behavior_outputs))
    reset_terms = (reset_name.lower(), "reset", "rst", "clear", "clears", "cleared", "zero")
    if not any(term in requirement_text for term in reset_terms):
        return tuple(dict.fromkeys(behavior_outputs))
    text_outputs = tuple(port for port in output_ports if port.lower() in requirement_text)
    return tuple(dict.fromkeys((*behavior_outputs, *text_outputs)))


def _increment_checks(
    plan: VerificationPlan,
    output_ports: tuple[str, ...],
    scalar_inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    behavior_checks = tuple(
        (behavior.target, behavior.control)
        for behavior in plan.behaviors
        if behavior.kind == "increment" and behavior.target in output_ports and behavior.control in scalar_inputs
    )
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text or not any(
        term in requirement_text for term in ("increment", "increments", "increase", "increases")
    ):
        return tuple(dict.fromkeys(behavior_checks))
    text_checks = tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in requirement_text and input_name.lower() in requirement_text
    )
    return tuple(dict.fromkeys((*behavior_checks, *text_checks)))


def _hold_checks(
    plan: VerificationPlan,
    output_ports: tuple[str, ...],
    scalar_inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    hold_requirements = tuple(
        requirement.statement for requirement in plan.structured_requirements if requirement.category == "hold"
    )
    if plan.structured_requirements and not hold_requirements:
        return ()
    requirement_text = " ".join(hold_requirements or plan.requirements).lower()
    if not requirement_text:
        return ()
    hold_terms = ("hold", "holds", "stable", "unchanged")
    inactive_terms = ("low", "deassert", "deasserted", "false", "0")
    if not any(term in requirement_text for term in hold_terms) or not any(
        term in requirement_text for term in inactive_terms
    ):
        return ()
    return tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in requirement_text and input_name.lower() in requirement_text
    )


def _output_wire_declarations(plan: VerificationPlan, ports: tuple[str, ...]) -> dict[str, str]:
    return {port: _output_wire_declaration(plan, port) for port in ports}


def _input_reg_declarations(plan: VerificationPlan, ports: tuple[str, ...]) -> dict[str, str]:
    declarations: dict[str, str] = {}
    structured = _structured_ports(plan)
    for name in ports:
        port = structured.get(name)
        if port is None:
            declarations[name] = "reg " + name
            continue
        signed = " signed" if port.signed else ""
        packed_range = f" [{port.width - 1}:0]" if port.width is not None and port.width > 1 else ""
        declarations[name] = "reg" + signed + packed_range + " " + name
    return declarations


def _memory_write_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    lines: list[str] = []
    memories = {memory.name: memory for memory in plan.memories}
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    for index, access in enumerate(plan.memory_accesses, start=1):
        if (
            access.kind != "write"
            or not access.synchronous
            or len(access.address_signals) != 1
            or len(access.data_signals) != 1
            or not access.enable_signals
        ):
            continue
        domain = domains.get(access.domain_id or "")
        if domain is not None and domain.clock != clock_name:
            continue
        memory = memories.get(access.memory)
        if memory is None:
            continue
        address = access.address_signals[0]
        data = access.data_signals[0]
        enable = " && ".join(access.enable_signals)
        reset_guard = (
            f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
            if reset_name and reset_inactive
            else ""
        )
        if memory.depth is not None:
            lines.append(f"        a_memory_address_{index}: assume(!({enable}) || ({address} < {memory.depth}));")
        lines.extend(
            (
                f"        if (!$initstate{reset_guard} && $past({enable})) begin",
                f"            a_memory_write_{index}: assert(dut.{memory.name}[$past({address})] == $past({data}));",
                "        end",
                f"        c_memory_write_{index}: cover({enable});",
            )
        )
    return lines


def _ready_valid_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
) -> list[str]:
    lines: list[str] = []
    for protocol in plan.protocols:
        if protocol.kind not in {"ready_valid", "req_ack"} or protocol.role != "source":
            continue
        antecedent = f"$past({protocol.valid} && !{protocol.ready})"
        current_guard = ""
        if reset_name is not None and reset_inactive is not None:
            antecedent = f"$past({reset_name} == {reset_inactive} && {protocol.valid} && !{protocol.ready})"
            current_guard = f" && {reset_name} == {reset_inactive}"
        lines.extend(
            [
                f"        if (!$initstate && {antecedent}{current_guard}) begin",
                f"            assert({protocol.valid});",
                *(
                    [f"            assert({protocol.data} == $past({protocol.data}));"]
                    if protocol.data is not None
                    else []
                ),
                "        end",
            ]
        )
    return lines


def _output_wire_declaration(plan: VerificationPlan, port: str) -> str:
    planned_port = _structured_ports(plan).get(port)
    if planned_port is not None:
        signed = " signed" if planned_port.signed else ""
        if planned_port.width is not None and planned_port.width > 1:
            return "wire" + signed + " [" + str(planned_port.width - 1) + ":0] " + port
        if planned_port.packed_range and _safe_packed_range(planned_port.packed_range):
            return "wire" + signed + " " + planned_port.packed_range + " " + port
        return "wire" + signed + " " + port
    dtype = _verilator_port_dtype(plan, port)
    if dtype is None:
        return "wire " + port
    left = dtype.attrib.get("left")
    right = dtype.attrib.get("right")
    signed = " signed" if dtype.attrib.get("signed") == "true" else ""
    if left is not None and right is not None and _safe_sv_bound(left) and _safe_sv_bound(right):
        return "wire" + signed + " [" + left + ":" + right + "] " + port
    return "wire" + signed + " " + port


def _verilator_port_dtype(plan: VerificationPlan, port: str) -> ElementTree.Element | None:
    locator = "port:" + plan.module + "." + port
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            if ref.locator.split("@", 1)[0] != locator:
                continue
            source_path = Path(ref.source_id)
            if not source_path.is_file():
                continue
            try:
                root = ElementTree.parse(source_path).getroot()
            except ElementTree.ParseError:
                continue
            dtype_id = _verilator_port_dtype_id(root, plan.design_unit or plan.module, port)
            if dtype_id is None:
                continue
            dtype = _verilator_dtype(root, dtype_id)
            if dtype is not None:
                return dtype
    return None


def _verilator_port_dtype_id(root: ElementTree.Element, module: str, port: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) != "module":
            continue
        if (element.attrib.get("origName") or element.attrib.get("name")) != module:
            continue
        for child in element:
            if _local_name(child.tag) != "var":
                continue
            if (child.attrib.get("origName") or child.attrib.get("name")) == port:
                return child.attrib.get("dtype_id")
    return None


def _verilator_dtype(root: ElementTree.Element, dtype_id: str) -> ElementTree.Element | None:
    for element in root.iter():
        if element.attrib.get("id") == dtype_id and _local_name(element.tag).endswith("dtype"):
            return element
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_sv_bound(value: str) -> bool:
    return value.isdecimal()


def _safe_packed_range(value: str) -> bool:
    if not value.startswith("[") or not value.endswith("]") or ":" not in value:
        return False
    left, right = value.strip("[]").split(":", 1)
    return _safe_sv_bound(left.strip()) and _safe_sv_bound(right.strip())


def _is_zero_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.lower().replace("_", "")
    if normalized in {"0", "'0", "1'b0", "1'h0", "1'd0"}:
        return True
    if "'" in normalized:
        return normalized.rsplit("'", 1)[-1].lstrip("s").lstrip("bhd") == "0"
    return False


def _looks_like_scalar_input(port: str) -> bool:
    if port.endswith(("_o", "_out")):
        return False
    return port.endswith(("_i", "_in")) or port in {"enable", "en", "valid", "ready", "start", "clear", "load"}


def _looks_like_output(port: str) -> bool:
    return port.endswith(("_o", "_out"))


def _comma_terminate(lines: list[str]) -> list[str]:
    return [line + ("," if index < len(lines) - 1 else "") for index, line in enumerate(lines)]


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
