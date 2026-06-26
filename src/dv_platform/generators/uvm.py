"""UVM generator backend."""

from __future__ import annotations

from pathlib import Path

from dv_platform.core.models import ArtifactKind, EvidenceRef, GeneratedArtifact, VerificationPlan, VerificationTarget


class UvmGenerator:
    """Generate conservative UVM scaffold artifacts without inventing transactions."""

    target = VerificationTarget.UVM

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        refs = _unique_refs(tuple(ref for claim in plan.claims for ref in claim.evidence_refs))
        return [
            GeneratedArtifact(
                path=Path(f"{module_name}_pkg.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_package_content(plan),
                source_plan_module=plan.module,
                provenance_refs=refs,
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}_if.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_interface_content(plan),
                source_plan_module=plan.module,
                provenance_refs=refs,
            ),
            GeneratedArtifact(
                path=Path(f"tb_{module_name}_uvm.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=_top_content(plan),
                source_plan_module=plan.module,
                provenance_refs=refs,
            ),
            GeneratedArtifact(
                path=Path("README.md"),
                kind=ArtifactKind.REPORT,
                target=self.target,
                content=_readme_content(plan),
                source_plan_module=plan.module,
                provenance_refs=refs,
            ),
        ]


def _package_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    return "\n".join(
        [
            "// Generated UVM scaffold package for " + plan.module + ".",
            "package " + module_name + "_pkg;",
            "    import uvm_pkg::*;",
            "    `include \"uvm_macros.svh\"",
            "",
            "    class " + module_name + "_test extends uvm_test;",
            "        `uvm_component_utils(" + module_name + "_test)",
            "",
            "        function new(string name = \"" + module_name + "_test\", uvm_component parent = null);",
            "            super.new(name, parent);",
            "        endfunction",
            "",
            "        task run_phase(uvm_phase phase);",
            "            phase.raise_objection(this);",
            "            `uvm_info(get_type_name(), \"Generated scaffold: transaction semantics are not yet inferred.\", UVM_LOW)",
            "            phase.drop_objection(this);",
            "        endtask",
            "    endclass",
            "endpackage",
            "",
        ]
    )


def _interface_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports) or "clk"
    lines = [
        "// Generated UVM interface scaffold for " + plan.module + ".",
        "interface " + module_name + "_if(input logic " + clock_name + ");",
    ]
    for port in ports:
        if port == clock_name:
            continue
        lines.append("    logic " + port + ";")
    lines.extend(["endinterface", ""])
    return "\n".join(lines)


def _top_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = _port_names_from_plan(plan)
    clock_name = _clock_name(ports) or "clk"
    connections = _connections(ports, module_name, clock_name)
    lines = [
        "// Generated UVM top-level scaffold for " + plan.module + ".",
        "`timescale 1ns/1ps",
        "",
        "module tb_" + module_name + "_uvm;",
        "    import uvm_pkg::*;",
        "    import " + module_name + "_pkg::*;",
        "",
        "    logic " + clock_name + ";",
        "    " + module_name + "_if vif(" + clock_name + ");",
        "",
        "    initial " + clock_name + " = 1'b0;",
        "    always #5 " + clock_name + " = ~" + clock_name + ";",
        "",
        "    " + plan.module + " dut (",
        *_comma_terminate(connections),
        "    );",
        "",
        "    initial begin",
        "        run_test(\"" + module_name + "_test\");",
        "    end",
        "endmodule",
        "",
    ]
    return "\n".join(lines)


def _readme_content(plan: VerificationPlan) -> str:
    lines = [
        "# UVM Scaffold for " + plan.module,
        "",
        "This scaffold is intentionally conservative.",
        "",
        "Advanced UVM generation is blocked until transaction semantics, agent boundaries, and scoreboard intent are provided by documentation or configuration.",
        "",
        "## Open Questions",
        "",
        "- What transaction type should drive this interface?",
        "- Which signals define request, response, valid, ready, error, and completion semantics?",
        "- What scoreboard or reference model should be used?",
    ]
    if plan.requirements:
        lines.extend(["", "## Retrieved Requirements", ""])
        lines.extend("- " + requirement for requirement in plan.requirements)
    return "\n".join(lines) + "\n"


def _connections(ports: tuple[str, ...], module_name: str, clock_name: str) -> list[str]:
    connections: list[str] = []
    for port in ports:
        signal = clock_name if port == clock_name else "vif." + port
        connections.append("        ." + port + "(" + signal + ")")
    return connections


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
    return next((port for port in ports if port in {"clk", "clock"} or port.endswith(("_clk", "_clock"))), None)


def _comma_terminate(lines: object) -> list[str]:
    values = list(lines)
    return [line + ("," if index < len(values) - 1 else "") for index, line in enumerate(values)]


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
