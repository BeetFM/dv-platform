"""UVM generator backend."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    EvidenceRef,
    GeneratedArtifact,
    RTLProtocol,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.signals import (
    artifact_trace,
    port_by_name,
    port_names,
    primary_clock_name,
    protocol_mapping_header,
    provenance_refs,
    structured_quality_requirements,
    sv_parameter_clause,
)


class UvmGenerator:
    """Generate conservative UVM scaffold artifacts without inventing transactions."""

    target = VerificationTarget.UVM

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        refs = provenance_refs(plan)
        quality = structured_quality_requirements(plan, "UVM")
        if plan.protocol_models or plan.register_models:
            quality = (
                *quality,
                ArtifactQualityRequirement(
                    "uvm_validator_configured",
                    "Protocol/register UVM generation requires an explicitly configured UVM validator.",
                    False,
                    "no UVM validator is configured for protocol/register semantics",
                ),
            )
        return [
            GeneratedArtifact(
                path=Path(f"{module_name}_pkg.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _package_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=quality,
                traceability=artifact_trace(plan, f"{module_name}_test", target=self.target),
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}_if.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _interface_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=quality,
                traceability=artifact_trace(plan, f"{module_name}_if", target=self.target),
            ),
            GeneratedArtifact(
                path=Path(f"tb_{module_name}_uvm.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _top_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=quality,
                traceability=artifact_trace(plan, f"tb_{module_name}_uvm", target=self.target),
            ),
            GeneratedArtifact(
                path=Path("README.md"),
                kind=ArtifactKind.REPORT,
                target=self.target,
                content=protocol_mapping_header(plan, self.target) + _readme_content(plan),
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
            ),
        ]


def _package_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    pair = _paired_protocol(plan)
    if pair is not None:
        return _protocol_package_content(plan, module_name, *pair)
    return "\n".join(
        [
            "// Generated UVM scaffold package for " + plan.module + ".",
            "package " + module_name + "_pkg;",
            "    import uvm_pkg::*;",
            '    `include "uvm_macros.svh"',
            "",
            "    class " + module_name + "_test extends uvm_test;",
            "        `uvm_component_utils(" + module_name + "_test)",
            "",
            '        function new(string name = "' + module_name + '_test", uvm_component parent = null);',
            "            super.new(name, parent);",
            "        endfunction",
            "",
            "        task run_phase(uvm_phase phase);",
            "            phase.raise_objection(this);",
            '            `uvm_info(get_type_name(), "Generated scaffold: transaction semantics are not yet inferred.", UVM_LOW)',
            "            phase.drop_objection(this);",
            "        endtask",
            "    endclass",
            "endpackage",
            "",
        ]
    )


def _protocol_package_content(
    plan: VerificationPlan,
    module_name: str,
    sink: RTLProtocol,
    source: RTLProtocol,
) -> str:
    width = sink.data_width or source.data_width or 1
    clock = sink.clock or source.clock or primary_clock_name(plan, port_names(plan)) or "clk"
    transaction = f"{module_name}_transaction"
    sequence = f"{module_name}_sequence"
    sequencer = f"{module_name}_sequencer"
    driver = f"{module_name}_driver"
    monitor = f"{module_name}_monitor"
    scoreboard = f"{module_name}_scoreboard"
    environment = f"{module_name}_env"
    test = f"{module_name}_test"
    interface = f"{module_name}_if"
    lines = [
        "// Generated protocol-backed UVM environment for " + plan.module + ".",
        "package " + module_name + "_pkg;",
        "    import uvm_pkg::*;",
        '    `include "uvm_macros.svh"',
        "",
        f"    class {transaction} extends uvm_sequence_item;",
        f"        rand bit [{width - 1}:0] data;",
        f"        `uvm_object_utils_begin({transaction})",
        "            `uvm_field_int(data, UVM_ALL_ON)",
        "        `uvm_object_utils_end",
        f'        function new(string name = "{transaction}"); super.new(name); endfunction',
        "    endclass",
        "",
        f"    class {sequence} extends uvm_sequence #({transaction});",
        f"        `uvm_object_utils({sequence})",
        f'        function new(string name = "{sequence}"); super.new(name); endfunction',
        "        task body();",
        "            repeat (16) begin",
        f'                req = {transaction}::type_id::create("req");',
        "                start_item(req);",
        '                if (!req.randomize()) `uvm_fatal(get_type_name(), "transaction randomization failed")',
        "                finish_item(req);",
        "            end",
        "        endtask",
        "    endclass",
        "",
        f"    class {sequencer} extends uvm_sequencer #({transaction});",
        f"        `uvm_component_utils({sequencer})",
        "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
        "    endclass",
        "",
        f"    class {driver} extends uvm_driver #({transaction});",
        f"        `uvm_component_utils({driver})",
        f"        virtual {interface} vif;",
        f"        uvm_analysis_port #({transaction}) expected_ap;",
        "        function new(string name, uvm_component parent);",
        '            super.new(name, parent); expected_ap = new("expected_ap", this);',
        "        endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            if (!uvm_config_db #(virtual {interface})::get(this, "", "vif", vif))',
        '                `uvm_fatal(get_type_name(), "virtual interface was not configured")',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        f"            vif.{sink.valid} <= 1'b0;",
        f"            vif.{source.ready} <= 1'b1;",
        "            forever begin",
        "                seq_item_port.get_next_item(req);",
        f"                vif.{sink.data} <= req.data;",
        f"                vif.{sink.valid} <= 1'b1;",
        f"                do @(posedge vif.{clock}); while (!vif.{sink.ready});",
        f"                vif.{sink.valid} <= 1'b0;",
        "                expected_ap.write(req);",
        "                seq_item_port.item_done();",
        "            end",
        "        endtask",
        "    endclass",
        "",
        f"    class {monitor} extends uvm_component;",
        f"        `uvm_component_utils({monitor})",
        f"        virtual {interface} vif;",
        f"        uvm_analysis_port #({transaction}) actual_ap;",
        "        function new(string name, uvm_component parent);",
        '            super.new(name, parent); actual_ap = new("actual_ap", this);',
        "        endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            if (!uvm_config_db #(virtual {interface})::get(this, "", "vif", vif))',
        '                `uvm_fatal(get_type_name(), "virtual interface was not configured")',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        f"            {transaction} observed;",
        "            forever begin",
        f"                @(posedge vif.{clock});",
        f"                if (vif.{source.valid} && vif.{source.ready}) begin",
        f'                    observed = {transaction}::type_id::create("observed");',
        f"                    observed.data = vif.{source.data};",
        "                    actual_ap.write(observed);",
        "                end",
        "            end",
        "        endtask",
        "    endclass",
        "",
        f"    class {scoreboard} extends uvm_component;",
        f"        `uvm_component_utils({scoreboard})",
        f"        uvm_tlm_analysis_fifo #({transaction}) expected_fifo;",
        f"        uvm_tlm_analysis_fifo #({transaction}) actual_fifo;",
        "        int unsigned compared;",
        "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        '            expected_fifo = new("expected_fifo", this); actual_fifo = new("actual_fifo", this);',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        f"            {transaction} expected, actual;",
        "            forever begin",
        "                expected_fifo.get(expected); actual_fifo.get(actual);",
        "                if (!expected.compare(actual))",
        '                    `uvm_error(get_type_name(), $sformatf("data mismatch expected=%0h actual=%0h", expected.data, actual.data))',
        "                else compared++;",
        "            end",
        "        endtask",
        "        function void check_phase(uvm_phase phase);",
        "            super.check_phase(phase);",
        '            if (compared == 0) `uvm_error(get_type_name(), "no transactions were compared")',
        "        endfunction",
        "    endclass",
        "",
        f"    class {environment} extends uvm_env;",
        f"        `uvm_component_utils({environment})",
        f"        {sequencer} sequencer; {driver} driver; {monitor} monitor; {scoreboard} scoreboard;",
        "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            sequencer = {sequencer}::type_id::create("sequencer", this);',
        f'            driver = {driver}::type_id::create("driver", this);',
        f'            monitor = {monitor}::type_id::create("monitor", this);',
        f'            scoreboard = {scoreboard}::type_id::create("scoreboard", this);',
        "        endfunction",
        "        function void connect_phase(uvm_phase phase);",
        "            driver.seq_item_port.connect(sequencer.seq_item_export);",
        "            driver.expected_ap.connect(scoreboard.expected_fifo.analysis_export);",
        "            monitor.actual_ap.connect(scoreboard.actual_fifo.analysis_export);",
        "        endfunction",
        "    endclass",
        "",
        f"    class {test} extends uvm_test;",
        f"        `uvm_component_utils({test})",
        f"        {environment} env;",
        f'        function new(string name = "{test}", uvm_component parent = null); super.new(name, parent); endfunction',
        f'        function void build_phase(uvm_phase phase); super.build_phase(phase); env = {environment}::type_id::create("env", this); endfunction',
        "        task run_phase(uvm_phase phase);",
        f'            {sequence} stimulus = {sequence}::type_id::create("stimulus");',
        "            phase.raise_objection(this); stimulus.start(env.sequencer); #100ns; phase.drop_objection(this);",
        "        endtask",
        "    endclass",
        "endpackage",
        "",
    ]
    return "\n".join(lines)


def _interface_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = port_names(plan)
    clock_name = primary_clock_name(plan, ports) or "clk"
    lines = [
        "// Generated UVM interface scaffold for " + plan.module + ".",
        "interface " + module_name + "_if(input logic " + clock_name + ");",
    ]
    for port in ports:
        if port == clock_name:
            continue
        detail = port_by_name(plan, port)
        width = (
            f" [{detail.width - 1}:0]" if detail is not None and detail.width is not None and detail.width > 1 else ""
        )
        signed = " signed" if detail is not None and detail.signed else ""
        lines.append("    logic" + signed + width + " " + port + ";")
    lines.extend(["endinterface", ""])
    return "\n".join(lines)


def _top_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    ports = port_names(plan)
    clock_name = primary_clock_name(plan, ports) or "clk"
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
        "    " + (plan.design_unit or plan.module) + sv_parameter_clause(plan) + " dut (",
        *_comma_terminate(connections),
        "    );",
        "",
        "    initial begin",
        "        uvm_config_db #(virtual " + module_name + '_if)::set(null, "*", "vif", vif);',
        '        run_test("' + module_name + '_test");',
        "    end",
        "endmodule",
        "",
    ]
    return "\n".join(lines)


def _readme_content(plan: VerificationPlan) -> str:
    pair = _paired_protocol(plan)
    if pair is not None:
        sink, source = pair
        return "\n".join(
            [
                "# UVM Environment for " + plan.module,
                "",
                "Generated transaction-level UVM components:",
                "",
                "- randomized sequence and sequencer",
                f"- driver for {sink.name} ({sink.profile})",
                f"- monitor for {source.name} ({source.profile})",
                "- expected/actual FIFO scoreboard",
                "- environment, test, virtual-interface configuration, and DUT top",
                "",
                "Compile order: interface, package, RTL sources, then UVM top.",
                "",
            ]
        )
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


def _paired_protocol(plan: VerificationPlan) -> tuple[RTLProtocol, RTLProtocol] | None:
    sinks = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "sink" and protocol.data is not None
    )
    sources = tuple(
        protocol
        for protocol in plan.protocols
        if protocol.kind in {"ready_valid", "req_ack"} and protocol.role == "source" and protocol.data is not None
    )
    if len(sinks) != 1 or len(sources) != 1 or sinks[0].kind != sources[0].kind:
        return None
    if sinks[0].clock and sources[0].clock and sinks[0].clock != sources[0].clock:
        return None
    return sinks[0], sources[0]


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


def _comma_terminate(lines: Iterable[str]) -> list[str]:
    values = list(lines)
    return [line + ("," if index < len(values) - 1 else "") for index, line in enumerate(values)]


def _unique_refs(refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    return tuple(dict.fromkeys(refs))


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
