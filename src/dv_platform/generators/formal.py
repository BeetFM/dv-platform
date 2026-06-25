"""Formal generator backend."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from dv_platform.core.models import ArtifactKind, EvidenceRef, GeneratedArtifact, VerificationPlan, VerificationTarget


class FormalGenerator:
    """Generate initial SymbiYosys-oriented formal collateral from a plan."""

    target = VerificationTarget.FORMAL

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        refs = _unique_refs(tuple(ref for claim in plan.claims for ref in claim.evidence_refs))
        module_name = _safe_identifier(plan.module)
        return [
            GeneratedArtifact(
                path=Path(f"formal_{module_name}.sv"),
                kind=ArtifactKind.FORMAL_HARNESS,
                target=self.target,
                content=_harness_content(plan),
                source_plan_module=plan.module,
                provenance_refs=refs,
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}.sby"),
                kind=ArtifactKind.RUN_SCRIPT,
                target=self.target,
                content=_sby_content(plan),
                source_plan_module=plan.module,
                provenance_refs=refs,
            ),
        ]


def _harness_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    harness_name = f"formal_{module_name}"
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports) or "clk"
    reset_name = _reset_name(ports)
    scalar_inputs = tuple(port for port in ports if _looks_like_scalar_input(port) and port != clock_name and port != reset_name)
    connected_ports = tuple(dict.fromkeys((clock_name, *(port for port in (reset_name, *scalar_inputs) if port))))
    unconnected_outputs = tuple(port for port in ports if _looks_like_output(port))
    reset_zero_outputs = _reset_zero_outputs(plan, unconnected_outputs, reset_name)
    increment_checks = _increment_checks(plan, unconnected_outputs, scalar_inputs)
    hold_checks = _hold_checks(plan, unconnected_outputs, scalar_inputs)
    checked_outputs = tuple(
        dict.fromkeys((*reset_zero_outputs, *(output for output, _input in increment_checks), *(output for output, _input in hold_checks)))
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
        reset_initial = "1'b0" if _reset_active_low(reset_name) else "1'b1"
        lines.append("    reg " + reset_name + " = " + reset_initial + ";")
    for name in scalar_inputs:
        lines.append("    reg " + name + " = 1'b0;")
    for name in checked_outputs:
        lines.append("    " + output_declarations.get(name, "wire " + name) + ";")

    lines.extend(["", "    " + plan.module + " dut ("])
    port_connections = ["        ." + name + "(" + name + ")" for name in connected_ports]
    port_connections.extend(
        "        ." + name + "(" + name + ")" if name in checked_outputs else "        ." + name + "()"
        for name in unconnected_outputs
    )
    lines.extend(_comma_terminate(port_connections))
    lines.extend(["    );", ""])

    lines.extend(["    always @(posedge " + clock_name + ") begin"])
    if reset_name:
        reset_active = "1'b0" if _reset_active_low(reset_name) else "1'b1"
        reset_inactive = "1'b1" if _reset_active_low(reset_name) else "1'b0"
        lines.extend(
            [
                "        if ($initstate) begin",
                "            assume(" + reset_name + " == " + reset_active + ");",
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
    return "\n".join(
        [
            "[options]",
            "mode prove",
            "depth 20",
            "",
            "[engines]",
            "smtbmc",
            "",
            "[script]",
            f"read -formal formal_{module_name}.sv",
            "# RTL source files are supplied by the formal runner from the project manifest.",
            f"prep -top {harness_name}",
            "",
            "[files]",
            f"formal_{module_name}.sv",
            "",
        ]
    )


def _port_names_from_plan(plan: VerificationPlan) -> tuple[str, ...]:
    ports: list[str] = []
    prefix = f"port:{plan.module}."
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            locator = ref.locator.split("@", 1)[0]
            if locator.startswith(prefix):
                ports.append(locator.removeprefix(prefix))
    return tuple(dict.fromkeys(ports))


def _clock_name(ports: tuple[str, ...]) -> str | None:
    return next((port for port in ports if port in {"clk", "clock"} or port.endswith("_clk") or port.endswith("_clock")), None)


def _reset_name(ports: tuple[str, ...]) -> str | None:
    return next(
        (
            port
            for port in ports
            if port in {"rst", "reset", "rst_n", "reset_n"}
            or port.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
        ),
        None,
    )


def _reset_active_low(reset_name: str) -> bool:
    return reset_name.endswith("_n")


def _reset_zero_outputs(plan: VerificationPlan, output_ports: tuple[str, ...], reset_name: str | None) -> tuple[str, ...]:
    if not reset_name:
        return ()
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text:
        return ()
    reset_terms = (reset_name.lower(), "reset", "rst", "clear", "clears", "cleared", "zero")
    if not any(term in requirement_text for term in reset_terms):
        return ()
    return tuple(port for port in output_ports if port.lower() in requirement_text)


def _increment_checks(
    plan: VerificationPlan,
    output_ports: tuple[str, ...],
    scalar_inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text or not any(term in requirement_text for term in ("increment", "increments", "increase", "increases")):
        return ()
    return tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in requirement_text and input_name.lower() in requirement_text
    )


def _hold_checks(
    plan: VerificationPlan,
    output_ports: tuple[str, ...],
    scalar_inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    requirement_text = " ".join(plan.requirements).lower()
    if not requirement_text:
        return ()
    hold_terms = ("hold", "holds", "stable", "unchanged")
    inactive_terms = ("low", "deassert", "deasserted", "false", "0")
    if not any(term in requirement_text for term in hold_terms) or not any(term in requirement_text for term in inactive_terms):
        return ()
    return tuple(
        (output, input_name)
        for output in output_ports
        for input_name in scalar_inputs
        if output.lower() in requirement_text and input_name.lower() in requirement_text
    )


def _output_wire_declarations(plan: VerificationPlan, ports: tuple[str, ...]) -> dict[str, str]:
    return {port: _output_wire_declaration(plan, port) for port in ports}


def _output_wire_declaration(plan: VerificationPlan, port: str) -> str:
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
            dtype_id = _verilator_port_dtype_id(root, plan.module, port)
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


def _looks_like_scalar_input(port: str) -> bool:
    if port.endswith(("_o", "_out")):
        return False
    return port.endswith(("_i", "_in")) or port in {"enable", "en", "valid", "ready", "start", "clear", "load"}


def _looks_like_output(port: str) -> bool:
    return port.endswith(("_o", "_out"))


def _comma_terminate(lines: list[str]) -> list[str]:
    return [line + ("," if index < len(lines) - 1 else "") for index, line in enumerate(lines)]


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
