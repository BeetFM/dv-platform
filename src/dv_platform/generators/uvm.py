"""UVM generator backend."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dv_platform.agent.protocols import ProtocolModel, RegisterField, RegisterModel
from dv_platform.core.literals import sv_numeric_literal_to_int
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
    primary_reset,
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
            qualified_ready_valid = _paired_protocol(plan) is not None and not plan.register_models
            quality = (
                *quality,
                ArtifactQualityRequirement(
                    "uvm_vendor_profile_qualified",
                    "Protocol/register UVM generation requires a vendor-qualified deterministic profile.",
                    qualified_ready_valid,
                    None
                    if qualified_ready_valid
                    else "only the paired ready/valid UVM 1.2 profile is vendor-qualified",
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
    if any(model.profile_id and model.profile_id.endswith("-1.0") for model in plan.protocol_models):
        return _profile_uvm_package_content(plan, module_name)
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


def _profile_uvm_package_content(plan: VerificationPlan, module_name: str) -> str:
    """Emit reusable multi-agent UVM contracts for shared protocol profiles."""

    models = tuple(model for model in plan.protocol_models if model.profile_id and model.profile_id.endswith("-1.0"))
    lines = [
        f"// Generated multi-agent protocol contract for {plan.module}.",
        f"package {module_name}_pkg;",
        "    import uvm_pkg::*;",
        '    `include "uvm_macros.svh"',
        "",
    ]
    for index, model in enumerate(models):
        stem = f"{module_name}_p{index}"
        transaction_fields = _uvm_transaction_fields(plan, model)
        lines.extend(
            [
                f"    // profile={model.profile_id} instance={model.instance_id} role={model.role}",
                f"    class {stem}_transaction extends uvm_sequence_item;",
                *(f"        rand bit [{width - 1}:0] {name};" for name, width in transaction_fields),
                "        rand int unsigned transaction_id;",
                "        rand int unsigned beat;",
                "        rand bit last;",
                f"        constraint bounded_beat {{ beat < {max(1, model.maximum_burst_length)}; }}",
                f"        constraint bounded_id {{ transaction_id < {max(1, model.maximum_outstanding)}; }}",
                f"        `uvm_object_utils_begin({stem}_transaction)",
                *(f"            `uvm_field_int({name}, UVM_ALL_ON)" for name, _width in transaction_fields),
                "            `uvm_field_int(transaction_id, UVM_ALL_ON)",
                "            `uvm_field_int(beat, UVM_ALL_ON)",
                "            `uvm_field_int(last, UVM_ALL_ON)",
                "        `uvm_object_utils_end",
                f'        function new(string name = "{stem}_transaction"); super.new(name); endfunction',
                "    endclass",
                "",
                f"    class {stem}_sequence extends uvm_sequence #({stem}_transaction);",
                f"        `uvm_object_utils({stem}_sequence)",
                f'        function new(string name = "{stem}_sequence"); super.new(name); endfunction',
                "        task body();",
                f"            repeat ({min(model.maximum_outstanding * 2, 32)}) begin",
                f'                req = {stem}_transaction::type_id::create("req");',
                "                start_item(req);",
                '                if (!req.randomize()) `uvm_fatal(get_type_name(), "randomization failed")',
                "                finish_item(req);",
                "            end",
                "        endtask",
                "    endclass",
                "",
                f"    class {stem}_sequencer extends uvm_sequencer #({stem}_transaction);",
                f"        `uvm_component_utils({stem}_sequencer)",
                "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
                "    endclass",
                "",
                *_profile_uvm_agent_lines(plan, module_name, stem, model, transaction_fields),
            ]
        )
    lines.extend(_uvm_ral_lines(plan, module_name))
    lines.extend(
        [
            f"    class {module_name}_cross_scoreboard extends uvm_component;",
            f"        `uvm_component_utils({module_name}_cross_scoreboard)",
            "        int unsigned compared;",
            "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
            "        function void check_phase(uvm_phase phase);",
            "            super.check_phase(phase);",
            '            if (compared == 0) `uvm_info(get_type_name(), "contract-only scoreboard awaiting endpoint model", UVM_LOW)',
            "        endfunction",
            "    endclass",
            "",
            f"    class {module_name}_virtual_sequence extends uvm_sequence;",
            f"        `uvm_object_utils({module_name}_virtual_sequence)",
            *(f"        {module_name}_p{index}_sequencer sequencer_{index};" for index in range(len(models))),
            f'        function new(string name = "{module_name}_virtual_sequence"); super.new(name); endfunction',
            "        task body();",
            *(f"            {module_name}_p{index}_sequence sequence_{index};" for index in range(len(models))),
            *(
                f'            sequence_{index} = {module_name}_p{index}_sequence::type_id::create("sequence_{index}");'
                for index in range(len(models))
            ),
            "            fork",
            *(f"                sequence_{index}.start(sequencer_{index});" for index in range(len(models))),
            "            join",
            "        endtask",
            "    endclass",
            "",
            f"    class {module_name}_env extends uvm_env;",
            f"        `uvm_component_utils({module_name}_env)",
            *[f"        {module_name}_p{index}_agent agent_{index};" for index in range(len(models))],
            f"        {module_name}_cross_scoreboard scoreboard;",
            "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
            "        function void build_phase(uvm_phase phase);",
            "            super.build_phase(phase);",
            *[
                f'            agent_{index} = {module_name}_p{index}_agent::type_id::create("agent_{index}", this);'
                for index in range(len(models))
            ],
            f'            scoreboard = {module_name}_cross_scoreboard::type_id::create("scoreboard", this);',
            "        endfunction",
            "    endclass",
            "",
            f"    class {module_name}_test extends uvm_test;",
            f"        `uvm_component_utils({module_name}_test)",
            f"        {module_name}_env env;",
            f'        function new(string name = "{module_name}_test", uvm_component parent = null); super.new(name, parent); endfunction',
            f'        function void build_phase(uvm_phase phase); super.build_phase(phase); env = {module_name}_env::type_id::create("env", this); endfunction',
            "        task run_phase(uvm_phase phase);",
            f"            {module_name}_virtual_sequence virtual_sequence;",
            "            phase.raise_objection(this);",
            f'            virtual_sequence = {module_name}_virtual_sequence::type_id::create("virtual_sequence");',
            *(
                f"            virtual_sequence.sequencer_{index} = env.agent_{index}.sequencer;"
                for index in range(len(models))
            ),
            "            fork",
            "                virtual_sequence.start(null);",
            "                begin",
            f"                    #{max((model.timeout_cycles for model in models), default=32) * 1000}ns;",
            '                    `uvm_fatal(get_type_name(), "profile virtual sequence timed out")',
            "                end",
            "            join_any",
            "            disable fork;",
            "            #100ns;",
            *(
                f'            if (env.agent_{index}.monitor.observed_count == 0) `uvm_error(get_type_name(), "agent_{index} was vacuous")'
                for index in range(len(models))
            ),
            "            phase.drop_objection(this);",
            "        endtask",
            "    endclass",
            "endpackage",
            "",
        ]
    )
    return "\n".join(lines)


def _uvm_transaction_fields(plan: VerificationPlan, model: ProtocolModel) -> tuple[tuple[str, int], ...]:
    ports = {port.name: port for port in plan.ports}
    bindings = dict(model.signal_bindings)
    fields: list[tuple[str, int]] = []
    for channel in model.channels:
        for canonical in channel.payload_fields:
            physical = bindings.get(canonical)
            if physical is None or any(name == canonical for name, _width in fields):
                continue
            port = ports.get(physical)
            fields.append((_safe_identifier(canonical), max(1, port.width if port and port.width else 1)))
    return tuple(fields)


def _profile_uvm_handshake(model: ProtocolModel) -> tuple[str, str, int] | None:
    bindings = dict(model.signal_bindings)
    for valid, ready, accepted in (
        ("awvalid", "awready", 1),
        ("wvalid", "wready", 1),
        ("bvalid", "bready", 1),
        ("arvalid", "arready", 1),
        ("rvalid", "rready", 1),
        ("tvalid", "tready", 1),
        ("valid", "ready", 1),
        ("a_valid", "a_ready", 1),
        ("d_valid", "d_ready", 1),
        ("stb", "stall", 0),
        ("read", "waitrequest", 0),
        ("write", "waitrequest", 0),
        ("hsel", "hready", 1),
    ):
        if valid in bindings and ready in bindings:
            return valid, ready, accepted
    if "stb" in bindings and "ack" in bindings:
        return "stb", "ack", 1
    return None


def _profile_uvm_agent_lines(
    plan: VerificationPlan,
    module_name: str,
    stem: str,
    model: ProtocolModel,
    transaction_fields: tuple[tuple[str, int], ...],
) -> list[str]:
    handshake = _profile_uvm_handshake(model)
    if handshake is None:
        raise ValueError(f"UVM profile {model.profile_id} has no recognized acceptance handshake")
    valid_name, ready_name, accepted = handshake
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    valid, ready = bindings[valid_name], bindings[ready_name]
    clock = model.clock_domain or "clk"
    active = directions.get(valid_name) == "input"
    accepted_expression = f"vif.{ready}" if accepted else f"!vif.{ready}"
    monitor_acceptance = f"vif.{valid} && ({accepted_expression})"
    input_payloads = tuple(
        (canonical, bindings[canonical])
        for canonical, _width in transaction_fields
        if canonical in bindings and directions.get(canonical) == "input"
    )
    id_field = next(
        (name for name, _width in transaction_fields if name.endswith("id") or name.endswith("source")), None
    )
    last_field = next(
        (name for name, _width in transaction_fields if name.endswith("last") or name == "endofpacket"), None
    )
    id_expression = f"observed.{id_field}" if id_field else "observed_count"
    last_expression = f"observed.{last_field}" if last_field else "1'b1"
    coverage_comments = ", ".join(model.coverage_bins) or "acceptance"
    compare_expression = (
        " && ".join(f"expected.{canonical} == actual.{canonical}" for canonical, _physical in input_payloads) or "1'b1"
    )
    lines = [
        f"    class {stem}_driver extends uvm_driver #({stem}_transaction);",
        f"        `uvm_component_utils({stem}_driver)",
        f"        virtual {module_name}_if vif;",
        f"        uvm_analysis_port #({stem}_transaction) expected_ap;",
        "        function new(string name, uvm_component parent);",
        '            super.new(name, parent); expected_ap = new("expected_ap", this);',
        "        endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            if (!uvm_config_db #(virtual {module_name}_if)::get(this, "", "vif", vif))',
        '                `uvm_fatal(get_type_name(), "virtual interface was not configured")',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        *(() if not active else (f"            vif.{valid} <= 1'b0;",)),
        *(f"            vif.{physical} <= '0;" for _canonical, physical in input_payloads),
        *(() if active else (f"            vif.{ready} <= 1'b{accepted};",)),
        "            forever begin",
        "                seq_item_port.get_next_item(req);",
        *(f"                vif.{physical} <= req.{canonical};" for canonical, physical in input_payloads),
        *(
            f"                vif.{valid} <= 1'b1;"
            if active
            else "                // Passive-source agent supplies acceptance only.",
        ),
        f"                do @(posedge vif.{clock}); while (!({monitor_acceptance}));",
        *(
            "                expected_ap.write(req);"
            if active
            else "                // Observed source data is the scoreboard authority.",
        ),
        *(
            f"                vif.{valid} <= 1'b0;"
            if active
            else "                // Keep responder ready for the next transfer.",
        ),
        "                seq_item_port.item_done();",
        "            end",
        "        endtask",
        "    endclass",
        "",
        f"    class {stem}_monitor extends uvm_component;",
        f"        `uvm_component_utils({stem}_monitor)",
        f"        virtual {module_name}_if vif;",
        f"        uvm_analysis_port #({stem}_transaction) observed_ap;",
        "        int unsigned observed_count;",
        f"        covergroup protocol_cg with function sample({stem}_transaction tr);",
        f'            option.comment = "profile bins: {coverage_comments}";',
        f"            cp_beat: coverpoint tr.beat {{ bins first = {{0}}; bins bounded[] = {{[1:{max(1, model.maximum_burst_length - 1)}]}}; }}",
        "            cp_id: coverpoint tr.transaction_id;",
        "            cp_last: coverpoint tr.last;",
        "            id_x_last: cross cp_id, cp_last;",
        "        endgroup",
        "        function new(string name, uvm_component parent);",
        '            super.new(name, parent); observed_ap = new("observed_ap", this); protocol_cg = new();',
        "        endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            if (!uvm_config_db #(virtual {module_name}_if)::get(this, "", "vif", vif))',
        '                `uvm_fatal(get_type_name(), "virtual interface was not configured")',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        f"            {stem}_transaction observed;",
        "            forever begin",
        f"                @(posedge vif.{clock});",
        f"                if ({monitor_acceptance}) begin",
        f'                    observed = {stem}_transaction::type_id::create("observed");',
        *(
            f"                    observed.{canonical} = vif.{bindings[canonical]};"
            for canonical, _width in transaction_fields
        ),
        f"                    observed.transaction_id = {id_expression};",
        f"                    observed.last = {last_expression};",
        "                    observed.beat = observed_count;",
        "                    observed_count++; protocol_cg.sample(observed); observed_ap.write(observed);",
        "                end",
        "            end",
        "        endtask",
        "    endclass",
        "",
        f"    class {stem}_scoreboard extends uvm_component;",
        f"        `uvm_component_utils({stem}_scoreboard)",
        f"        localparam bit ACTIVE = 1'b{int(active)};",
        f"        uvm_tlm_analysis_fifo #({stem}_transaction) expected_fifo, actual_fifo;",
        "        int unsigned compared;",
        "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
        "        function void build_phase(uvm_phase phase);",
        '            expected_fifo = new("expected_fifo", this); actual_fifo = new("actual_fifo", this);',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        f"            {stem}_transaction expected, actual;",
        "            forever begin",
        "                actual_fifo.get(actual);",
        "                if (ACTIVE) begin",
        "                    expected_fifo.get(expected);",
        f'                    if (!({compare_expression})) `uvm_error(get_type_name(), "protocol transaction mismatch")',
        "                end",
        "                compared++;",
        "            end",
        "        endtask",
        "        function void check_phase(uvm_phase phase);",
        '            if (compared == 0) `uvm_error(get_type_name(), "no accepted transactions were observed")',
        "        endfunction",
        "    endclass",
        "",
        f"    class {stem}_agent extends uvm_agent;",
        f"        `uvm_component_utils({stem}_agent)",
        f"        {stem}_sequencer sequencer; {stem}_driver driver; {stem}_monitor monitor; {stem}_scoreboard scoreboard;",
        "        function new(string name, uvm_component parent); super.new(name, parent); endfunction",
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            sequencer = {stem}_sequencer::type_id::create("sequencer", this);',
        f'            driver = {stem}_driver::type_id::create("driver", this);',
        f'            monitor = {stem}_monitor::type_id::create("monitor", this);',
        f'            scoreboard = {stem}_scoreboard::type_id::create("scoreboard", this);',
        "        endfunction",
        "        function void connect_phase(uvm_phase phase);",
        "            driver.seq_item_port.connect(sequencer.seq_item_export);",
        "            driver.expected_ap.connect(scoreboard.expected_fifo.analysis_export);",
        "            monitor.observed_ap.connect(scoreboard.actual_fifo.analysis_export);",
        "        endfunction",
        "    endclass",
        f"    // canonical payload fields: {', '.join(name for name, _width in transaction_fields) or 'none'}",
        "",
    ]
    return lines


def _uvm_ral_lines(plan: VerificationPlan, module_name: str) -> list[str]:
    lines: list[str] = []
    for index, register in enumerate(plan.register_models):
        register_type = f"{module_name}_reg_{index}"
        lines.extend(
            [
                f"    class {register_type} extends uvm_reg;",
                f"        `uvm_object_utils({register_type})",
                *(f"        rand uvm_reg_field {_safe_identifier(field.name)};" for field in register.fields),
                f'        function new(string name = "{register.name}"); super.new(name, {register.width}, UVM_CVR_FIELD_VALS); endfunction',
                "        virtual function void build();",
                *(_uvm_field_configuration(field) for field in register.fields),
                "        endfunction",
                "    endclass",
                "",
            ]
        )
    if plan.register_models:
        block_type = f"{module_name}_reg_block"
        lines.extend(
            [
                f"    class {block_type} extends uvm_reg_block;",
                f"        `uvm_object_utils({block_type})",
                *(
                    f"        rand {module_name}_reg_{index} {_safe_identifier(register.name)};"
                    for index, register in enumerate(plan.register_models)
                ),
                f'        function new(string name = "{block_type}"); super.new(name, UVM_CVR_ALL); endfunction',
                "        virtual function void build();",
                '            default_map = create_map("default_map", 0, 4, UVM_LITTLE_ENDIAN, 1);',
                *(
                    line
                    for index, register in enumerate(plan.register_models)
                    for line in _uvm_register_build_lines(module_name, index, register)
                ),
                "            lock_model();",
                "        endfunction",
                "    endclass",
                "",
            ]
        )
    return lines


def _uvm_field_configuration(field: RegisterField) -> str:
    name = _safe_identifier(field.name)
    width = field.msb - field.lsb + 1
    lsb = field.lsb
    access = field.access.upper().replace("_", "")
    supported = {
        "RO",
        "RW",
        "RC",
        "RS",
        "WRC",
        "WRS",
        "WC",
        "WS",
        "WSRC",
        "WCRS",
        "W1C",
        "W1S",
        "W1T",
        "W0C",
        "W0S",
        "W0T",
        "WO",
        "WOC",
        "WOS",
        "W1",
        "WO1",
    }
    if access not in supported:
        access = "RO" if field.reserved else "RW"
    reset_text = field.reset_value
    reset = sv_numeric_literal_to_int(str(reset_text), width=width) if reset_text is not None else None
    if reset is None and reset_text is not None:
        try:
            reset = int(str(reset_text), 0)
        except ValueError:
            reset = 0
    has_reset = int(reset_text is not None)
    is_rand = int(access in {"RW", "WRC", "WRS"} and not field.reserved)
    return (
        f'            {name} = uvm_reg_field::type_id::create("{name}"); '
        f'{name}.configure(this, {width}, {lsb}, "{access}", 0, \'h{reset or 0:x}, {has_reset}, {is_rand}, 0);'
    )


def _uvm_register_build_lines(module_name: str, index: int, register: RegisterModel) -> tuple[str, ...]:
    name = _safe_identifier(register.name)
    if register.offset is None:
        raise ValueError(f"UVM RAL requires an exact offset for {register.name}")
    offset = register.offset
    return (
        f'            {name} = {module_name}_reg_{index}::type_id::create("{name}");',
        f'            {name}.configure(this, null, "");',
        f"            {name}.build();",
        f'            default_map.add_reg({name}, \'h{offset:x}, "RW");',
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
    reset = primary_reset(plan, port_names(plan))
    reset_lines: tuple[str, ...] = ()
    if reset is not None:
        active_low = reset.active_low if reset.active_low is not None else reset.name.endswith("_n")
        active, inactive = ("1'b0", "1'b1") if active_low else ("1'b1", "1'b0")
        reset_lines = (
            f"            vif.{reset.name} <= {active};",
            f"            repeat (3) @(posedge vif.{clock});",
            f"            vif.{reset.name} <= {inactive};",
            f"            repeat (2) @(posedge vif.{clock});",
        )
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
        f"        virtual {interface} vif;",
        f'        function new(string name = "{test}", uvm_component parent = null); super.new(name, parent); endfunction',
        "        function void build_phase(uvm_phase phase);",
        "            super.build_phase(phase);",
        f'            env = {environment}::type_id::create("env", this);',
        f'            if (!uvm_config_db #(virtual {interface})::get(this, "", "vif", vif))',
        '                `uvm_fatal(get_type_name(), "virtual interface was not configured")',
        "        endfunction",
        "        task run_phase(uvm_phase phase);",
        f'            {sequence} stimulus = {sequence}::type_id::create("stimulus");',
        "            phase.raise_objection(this);",
        *reset_lines,
        "            stimulus.start(env.sequencer);",
        "            #100ns;",
        "            phase.drop_objection(this);",
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
