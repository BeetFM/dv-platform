"""Formal generator backend."""

from __future__ import annotations

from pathlib import Path

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

    lines = [
        "// Generated formal harness for " + plan.module + ".",
        "`default_nettype none",
        "",
        "module " + harness_name + ";",
        "    reg " + clock_name + " = 1'b0;",
    ]
    if reset_name:
        reset_initial = "1'b0" if _reset_active_low(reset_name) else "1'b1"
        lines.append("    reg " + reset_name + " = " + reset_initial + ";")
    for name in scalar_inputs:
        lines.append("    reg " + name + " = 1'b0;")

    lines.extend(["", "    " + plan.module + " dut ("])
    port_connections = ["        ." + name + "(" + name + ")" for name in connected_ports]
    port_connections.extend("        ." + name + "()" for name in unconnected_outputs)
    lines.extend(_comma_terminate(port_connections))
    lines.extend(["    );", "", "    always @* begin", "        " + clock_name + " = $anyseq;", "    end", ""])

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
        cover_terms = [reset_name + " == " + reset_inactive, *scalar_inputs]
    else:
        for name in scalar_inputs:
            lines.append("        " + name + " <= $anyseq;")
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
