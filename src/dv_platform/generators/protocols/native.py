"""Native HDL protocol task generation."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.protocols.common import (
    _profile_drive_value,
    _profile_handshake_specs,
    _profile_payload_fields,
)
from dv_platform.generators.protocols.formal_standard import (
    _apb4_reset_value,
    _apb4_scenario_payload,
    _axi4_lite_scenario_payload,
    _protocol_identifier,
)


def native_protocol_task_declarations(plan: VerificationPlan, target: VerificationTarget) -> tuple[str, ...]:
    """Emit portable Verilog-2001 tasks for executable native bus scenarios."""

    apb = _apb4_scenario_payload(plan, target)
    if apb is not None:
        profile, _specs, timeout, _scenarios = apb
        binding = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
        binding["clock"] = profile.get("clock", "")
        required: tuple[str, ...] = (
            "paddr",
            "pwrite",
            "psel",
            "penable",
            "pwdata",
            "pstrb",
            "prdata",
            "pready",
            "pslverr",
        )
        if all(binding.get(name) for name in required):
            return _native_apb_tasks(binding, timeout)
    axi = _axi4_lite_scenario_payload(plan, target)
    if axi is not None:
        profile, _specs, timeout, _scenario = axi
        binding = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
        binding["clock"] = profile.get("clock", "")
        required = (
            "awaddr",
            "awvalid",
            "awready",
            "wdata",
            "wstrb",
            "wvalid",
            "wready",
            "bresp",
            "bvalid",
            "bready",
            "araddr",
            "arvalid",
            "arready",
            "rdata",
            "rresp",
            "rvalid",
            "rready",
        )
        if all(binding.get(name) for name in required):
            return _native_axi_tasks(binding, timeout)
    return _native_profile_tasks(plan)


def native_protocol_accesses(plan: VerificationPlan, target: VerificationTarget) -> tuple[str, ...]:
    """Exercise the first governed register and required protocol corner cases."""

    apb = _apb4_scenario_payload(plan, target)
    if apb is not None:
        profile, specs, _timeout, _scenarios = apb
        first = next(iter(specs.values()))
        address = int(str(first["offset"]), 0)
        invalid = int(profile["invalid_address"], 0)
        reset_value = _apb4_reset_value(first)
        data = 0x00AA99A5
        expected = _register_value_after_write(first, reset_value, data, 0xF)
        reset = profile.get("reset", "")
        active_low = profile.get("reset_active_low") == "true"
        lines = [
            "        // Executable native APB4 scoreboard and protocol checks.",
            f"        dv_apb_transfer(32'h{address:x}, 1'b0, 32'h0, 4'h0, dv_native_data, dv_native_error);",
            f"        if (dv_native_error || dv_native_data !== 32'h{reset_value:08x}) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_apb_transfer(32'h{address:x}, 1'b1, 32'hffffffff, 4'h0, dv_native_data, dv_native_error);",
            f"        dv_apb_transfer(32'h{address:x}, 1'b0, 32'h0, 4'h0, dv_native_data, dv_native_error);",
            f"        if (dv_native_error || dv_native_data !== 32'h{reset_value:08x}) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_apb_transfer(32'h{address:x}, 1'b1, 32'h{data:08x}, 4'hf, dv_native_data, dv_native_error);",
            f"        dv_apb_transfer(32'h{address:x}, 1'b0, 32'h0, 4'h0, dv_native_data, dv_native_error);",
            f"        if (dv_native_error || dv_native_data !== 32'h{expected:08x}) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_apb_transfer(32'h{invalid:x}, 1'b0, 32'h0, 4'h0, dv_native_data, dv_native_error);",
            "        if (!dv_native_error) dv_platform_failures = dv_platform_failures + 1;",
        ]
        if reset:
            active, inactive = ("1'b0", "1'b1") if active_low else ("1'b1", "1'b0")
            lines.extend(
                (
                    f"        {reset} = {active};",
                    "        repeat (2) @(posedge " + profile.get("clock", "clk") + ");",
                    f"        {reset} = {inactive};",
                    f"        dv_apb_transfer(32'h{address:x}, 1'b0, 32'h0, 4'h0, dv_native_data, dv_native_error);",
                    f"        if (dv_native_error || dv_native_data !== 32'h{reset_value:08x}) dv_platform_failures = dv_platform_failures + 1;",
                )
            )
        return tuple(lines)
    axi = _axi4_lite_scenario_payload(plan, target)
    if axi is not None:
        profile, specs, _timeout, _scenario = axi
        first = next(iter(specs.values()))
        address = int(str(first["offset"]), 0)
        invalid = int(profile["invalid_address"], 0)
        reset_value = _apb4_reset_value(first)
        return (
            "        // Executable native AXI4-Lite independent-channel scoreboard.",
            f"        dv_axi_read(32'h{address:x}, 1'b1, dv_native_data, dv_native_resp);",
            f"        if (dv_native_resp !== 2'b00 || dv_native_data !== 32'h{reset_value:08x}) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_axi_write(32'h{address:x}, 32'ha5, 4'h0, 1'b1, dv_native_resp);",
            "        if (dv_native_resp !== 2'b00) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_axi_read(32'h{address:x}, 1'b1, dv_native_data, dv_native_resp);",
            f"        if (dv_native_data !== 32'h{reset_value:08x}) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_axi_write(32'h{address:x}, 32'ha5, 4'hf, 1'b1, dv_native_resp);",
            "        if (dv_native_resp !== 2'b00) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_axi_read(32'h{address:x}, 1'b1, dv_native_data, dv_native_resp);",
            "        if (dv_native_resp !== 2'b00 || dv_native_data[7:0] !== 8'ha5) dv_platform_failures = dv_platform_failures + 1;",
            f"        dv_axi_read(32'h{invalid:x}, 1'b1, dv_native_data, dv_native_resp);",
            "        if (dv_native_resp !== 2'b10) dv_platform_failures = dv_platform_failures + 1;",
        )
    return tuple(
        f"        dv_profile_{_protocol_identifier(model.instance_id or model.profile_id or model.name)}_exercise();"
        for model in plan.protocol_models
        if model.profile_id and model.profile_id.endswith("-1.0")
    )


def _native_profile_tasks(plan: VerificationPlan) -> tuple[str, ...]:
    """Emit bounded portable tasks for every explicitly normalized profile agent."""

    lines: list[str] = []
    for model in plan.protocol_models:
        lines.extend(_native_profile_task(model))
    return tuple(lines)


def _native_profile_task(
    model: ProtocolModel,
) -> tuple[str, ...]:
    lines: list[str] = []
    if model.profile_id is None or not model.profile_id.endswith("-1.0"):
        return ()
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    handshakes = _profile_handshake_specs(model)
    if not handshakes:
        return ()
    clock = model.clock_domain or "clk"
    identifier = _protocol_identifier(model.instance_id or model.profile_id)
    valid_names = {valid for valid, _ready, _accepted in handshakes}
    lines.extend(
        [
            f"    task dv_profile_{identifier}_exercise;",
            "        integer cycles;",
            "        reg [1023:0] held_payload;",
            "        begin",
            f"            // profile={model.profile_id} role={model.role} instance={model.instance_id}",
        ]
    )
    for canonical, physical in model.signal_bindings:
        if directions.get(canonical) != "input":
            continue
        value = 0 if canonical in valid_names or canonical == "cyc" else _profile_drive_value(canonical)
        lines.append(f"            {physical} = {value};")
    for valid_name, ready_name, accepted in handshakes:
        valid, ready = bindings[valid_name], bindings[ready_name]
        if directions.get(valid_name) == "input" and directions.get(ready_name) == "output":
            if valid_name == "stb" and "cyc" in bindings:
                lines.append(f"            {bindings['cyc']} = 1'b1;")
            lines.extend(
                [
                    f"            {valid} = 1'b1; cycles = 0;",
                    f"            while (({ready} !== 1'b{accepted}) && cycles < {model.timeout_cycles}) begin @(posedge {clock}); cycles = cycles + 1; end",
                    f"            if ({ready} !== 1'b{accepted}) dv_platform_failures = dv_platform_failures + 1;",
                    f"            else begin @(posedge {clock}); #1; end",
                ]
            )
            if model.profile_id == "wishbone-b4-1.0" and valid_name == "stb":
                responses = tuple(bindings[name] for name in ("ack", "err", "rty") if name in bindings)
                if responses:
                    expression = " || ".join(responses)
                    lines.extend(
                        [
                            f"            cycles = 0; while (!({expression}) && cycles < {model.timeout_cycles}) begin @(posedge {clock}); #1; cycles = cycles + 1; end",
                            f"            if (!({expression})) dv_platform_failures = dv_platform_failures + 1;",
                        ]
                    )
            lines.extend(_native_avalon_response_wait(model, valid_name, bindings, clock))
            lines.append(f"            {valid} = 1'b0;")
            if valid_name == "stb" and "cyc" in bindings:
                lines.append(f"            {bindings['cyc']} = 1'b0;")
        elif directions.get(valid_name) == "output" and directions.get(ready_name) == "input":
            stalled = 1 - accepted
            payload = tuple(bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings)
            payload_expression = "{" + ", ".join(payload) + "}" if payload else valid
            lines.extend(
                [
                    f"            {ready} = 1'b{stalled}; cycles = 0;",
                    f"            while (!{valid} && cycles < {model.timeout_cycles}) begin @(posedge {clock}); #1; cycles = cycles + 1; end",
                    f"            if (!{valid}) dv_platform_failures = dv_platform_failures + 1;",
                    f"            else begin held_payload = {payload_expression}; @(posedge {clock}); #1; if (!{valid} || held_payload !== {payload_expression}) dv_platform_failures = dv_platform_failures + 1; end",
                    f"            {ready} = 1'b{accepted}; @(posedge {clock}); #1;",
                    f"            {ready} = 1'b{stalled};",
                ]
            )
    lines.extend(_native_profile_semantic_checks(model))
    lines.extend(("        end", "    endtask", ""))
    return tuple(lines)


def _native_avalon_response_wait(
    model: ProtocolModel,
    valid_name: str,
    bindings: dict[str, str],
    clock: str,
) -> tuple[str, ...]:
    if model.profile_id != "avalon-mm-1.0":
        return ()
    response_name = {"read": "readdatavalid", "write": "writeresponsevalid"}.get(valid_name)
    if response_name is None or response_name not in bindings:
        return ()
    response = bindings[response_name]
    return (
        f"            cycles = 0; while (!{response} && cycles < {model.timeout_cycles}) begin @(posedge {clock}); #1; cycles = cycles + 1; end",
        f"            if (!{response}) dv_platform_failures = dv_platform_failures + 1;",
    )


def _native_profile_semantic_checks(model: ProtocolModel) -> tuple[str, ...]:
    bindings = dict(model.signal_bindings)
    handlers = {
        "axi4-1.0": _native_axi_semantic_checks,
        "axi4-lite-1.0": _native_axi_semantic_checks,
        "axi4-stream-1.0": _native_stream_semantic_checks,
        "wishbone-b4-1.0": _native_wishbone_semantic_checks,
        "avalon-mm-1.0": _native_avalon_mm_semantic_checks,
        "avalon-st-1.0": _native_avalon_st_semantic_checks,
        "ahb-1.0": _native_ahb_semantic_checks,
        "tilelink-ul-uh-1.0": _native_tilelink_semantic_checks,
    }
    handler = handlers.get(model.profile_id) if model.profile_id is not None else None
    return handler(bindings) if handler is not None else ()


def _native_axi_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    lines: list[str] = []
    if "wstrb" in bindings:
        lines.append(f"            if ({bindings['wstrb']} == 0) dv_platform_failures = dv_platform_failures + 1;")
    for request, response in (("awid", "bid"), ("arid", "rid")):
        if request in bindings and response in bindings:
            lines.append(
                f"            if ({bindings[request]} !== {bindings[response]}) dv_platform_failures = dv_platform_failures + 1;"
            )
    for prefix in ("aw", "ar"):
        names = tuple(prefix + suffix for suffix in ("addr", "len", "size", "burst"))
        if all(name in bindings for name in names):
            address, length, size, burst = (bindings[name] for name in names)
            lines.append(
                f"            if ({burst} > 2 || (({address} & 12'hfff) + (({length} + 1) << {size})) > 4096) dv_platform_failures = dv_platform_failures + 1;"
            )
    return tuple(lines)


def _native_stream_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    lines = []
    if "tkeep" in bindings:
        lines.append(f"            if ({bindings['tkeep']} == 0) dv_platform_failures = dv_platform_failures + 1;")
    if "tkeep" in bindings and "tstrb" in bindings:
        lines.append(
            f"            if (({bindings['tstrb']} & ~{bindings['tkeep']}) != 0) dv_platform_failures = dv_platform_failures + 1;"
        )
    if "tlast" in bindings:
        lines.append(f"            if (!{bindings['tlast']}) dv_platform_failures = dv_platform_failures + 1;")
    return tuple(lines)


def _native_wishbone_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    lines = []
    responses = tuple(bindings[name] for name in ("ack", "err", "rty") if name in bindings)
    if responses:
        lines.append(
            f"            if (({' + '.join(responses)}) != 1) dv_platform_failures = dv_platform_failures + 1;"
        )
    if "we" in bindings and "sel" in bindings:
        lines.append(
            f"            if ({bindings['we']} && {bindings['sel']} == 0) dv_platform_failures = dv_platform_failures + 1;"
        )
    return tuple(lines)


def _native_avalon_mm_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    lines = []
    if all(name in bindings for name in ("read", "write")):
        lines.append(
            f"            if ({bindings['read']} && {bindings['write']}) dv_platform_failures = dv_platform_failures + 1;"
        )
    if "burstcount" in bindings:
        lines.append(f"            if ({bindings['burstcount']} == 0) dv_platform_failures = dv_platform_failures + 1;")
    return tuple(lines)


def _native_avalon_st_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    if not all(name in bindings for name in ("endofpacket", "empty")):
        return ()
    return (
        f"            if (!{bindings['endofpacket']} && {bindings['empty']} != 0) dv_platform_failures = dv_platform_failures + 1;",
    )


def _native_ahb_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    if "htrans" not in bindings:
        return ()
    return (f"            if (!{bindings['htrans']}[1]) dv_platform_failures = dv_platform_failures + 1;",)


def _native_tilelink_semantic_checks(bindings: dict[str, str]) -> tuple[str, ...]:
    lines = []
    for request, response in (("a_source", "d_source"), ("a_size", "d_size")):
        if request in bindings and response in bindings:
            lines.append(
                f"            if ({bindings[request]} !== {bindings[response]}) dv_platform_failures = dv_platform_failures + 1;"
            )
    return tuple(lines)


def _register_value_after_write(spec: dict[str, object], previous: int, data: int, strobes: int) -> int:
    result = previous
    fields = spec.get("fields", ())
    if not isinstance(fields, list):
        return result
    for field in fields:
        if not isinstance(field, dict):
            continue
        lsb, msb = int(field["lsb"]), int(field["msb"])
        if not any(strobes & (1 << lane) for lane in range(lsb // 8, msb // 8 + 1)):
            continue
        mask = ((1 << (msb - lsb + 1)) - 1) << lsb
        access = str(field["access"]).lower()
        if access == "rw":
            result = (result & ~mask) | (data & mask)
        elif access == "w1c":
            result &= ~(data & mask)
    return result


def _native_apb_tasks(binding: dict[str, str], timeout: int) -> tuple[str, ...]:
    b = binding
    return (
        "    reg [31:0] dv_native_data;",
        "    reg [1:0] dv_native_resp;",
        "    reg dv_native_error;",
        "    task dv_apb_transfer;",
        "        input [31:0] address; input write; input [31:0] data; input [3:0] strb;",
        "        output [31:0] observed; output error;",
        "        integer cycles; reg [31:0] held_data; reg held_error;",
        "        begin",
        f"            {b['paddr']} = address; {b['pwrite']} = write; {b['pwdata']} = data; {b['pstrb']} = strb;",
        f"            {b['psel']} = 1'b1; {b['penable']} = 1'b0; @(posedge {b.get('clock', 'pclk')});",
        f"            if ({b['pready']}) dv_platform_failures = dv_platform_failures + 1;",
        f"            {b['penable']} = 1'b1; cycles = 0; held_data = {b['prdata']}; held_error = {b['pslverr']};",
        f"            while (!{b['pready']} && cycles < {timeout}) begin",
        f"                @(posedge {b.get('clock', 'pclk')}); cycles = cycles + 1;",
        f"                if (!{b['pready']} && cycles > 1 && ({b['prdata']} !== held_data || {b['pslverr']} !== held_error)) dv_platform_failures = dv_platform_failures + 1;",
        f"                held_data = {b['prdata']}; held_error = {b['pslverr']};",
        "            end",
        f"            if (!{b['pready']} || cycles == 0) dv_platform_failures = dv_platform_failures + 1;",
        f"            observed = {b['prdata']}; error = {b['pslverr']};",
        f"            {b['psel']} = 1'b0; {b['penable']} = 1'b0; @(posedge {b.get('clock', 'pclk')});",
        "        end",
        "    endtask",
    )


def _native_axi_tasks(binding: dict[str, str], timeout: int) -> tuple[str, ...]:
    b = binding
    clock = b.get("clock", "aclk")
    return (
        "    reg [31:0] dv_native_data;",
        "    reg [1:0] dv_native_resp;",
        "    reg dv_native_error;",
        "    task dv_axi_write;",
        "        input [31:0] address; input [31:0] data; input [3:0] strb; input separate; output [1:0] response;",
        "        integer cycles; reg [1:0] held_resp;",
        "        begin",
        f"            {b['awaddr']} = address; {b['awvalid']} = 1'b1; {b['wvalid']} = separate ? 1'b0 : 1'b1; {b['wdata']} = data; {b['wstrb']} = strb; {b['bready']} = 1'b0;",
        f"            cycles = 0; while (!{b['awready']} && cycles < {timeout}) begin @(posedge {clock}); cycles = cycles + 1; end",
        f"            if (!{b['awready']}) dv_platform_failures = dv_platform_failures + 1;",
        f"            @(posedge {clock}); #1; {b['awvalid']} = 1'b0;",
        f"            if ({b['bvalid']}) dv_platform_failures = dv_platform_failures + 1;",
        f"            {b['awaddr']} = address + 1; {b['awvalid']} = 1'b1; #1; if ({b['awready']}) dv_platform_failures = dv_platform_failures + 1; {b['awvalid']} = 1'b0;",
        f"            {b['wvalid']} = 1'b1; cycles = 0; while (!{b['wready']} && cycles < {timeout}) begin @(posedge {clock}); cycles = cycles + 1; end",
        f"            if (!{b['wready']}) dv_platform_failures = dv_platform_failures + 1; @(posedge {clock}); #1; {b['wvalid']} = 1'b0;",
        f"            cycles = 0; while (!{b['bvalid']} && cycles < {timeout}) begin @(posedge {clock}); cycles = cycles + 1; end",
        f"            if (!{b['bvalid']}) dv_platform_failures = dv_platform_failures + 1; held_resp = {b['bresp']}; @(posedge {clock});",
        f"            if (!{b['bvalid']} || {b['bresp']} !== held_resp) dv_platform_failures = dv_platform_failures + 1;",
        f"            response = {b['bresp']}; {b['bready']} = 1'b1; @(posedge {clock}); #1; {b['bready']} = 1'b0;",
        "        end",
        "    endtask",
        "    task dv_axi_read;",
        "        input [31:0] address; input hold_response; output [31:0] data; output [1:0] response;",
        "        integer cycles; reg [31:0] held_data; reg [1:0] held_resp;",
        "        begin",
        f"            {b['araddr']} = address; {b['arvalid']} = 1'b1; {b['rready']} = 1'b0; cycles = 0;",
        f"            while (!{b['arready']} && cycles < {timeout}) begin @(posedge {clock}); cycles = cycles + 1; end",
        f"            if (!{b['arready']}) dv_platform_failures = dv_platform_failures + 1; @(posedge {clock}); #1; {b['arvalid']} = 1'b0;",
        f"            cycles = 0; while (!{b['rvalid']} && cycles < {timeout}) begin @(posedge {clock}); cycles = cycles + 1; end",
        f"            if (!{b['rvalid']}) dv_platform_failures = dv_platform_failures + 1; held_data = {b['rdata']}; held_resp = {b['rresp']};",
        f"            {b['araddr']} = address + 1; {b['arvalid']} = 1'b1; #1; if ({b['arready']}) dv_platform_failures = dv_platform_failures + 1; {b['arvalid']} = 1'b0;",
        f"            if (hold_response) begin @(posedge {clock}); #1; if (!{b['rvalid']} || {b['rdata']} !== held_data || {b['rresp']} !== held_resp) dv_platform_failures = dv_platform_failures + 1; end",
        f"            data = {b['rdata']}; response = {b['rresp']}; {b['rready']} = 1'b1; @(posedge {clock}); #1; {b['rready']} = 1'b0;",
        "        end",
        "    endtask",
    )


def sv_register_accesses(plan: VerificationPlan) -> tuple[str, ...]:
    """Emit conservative directed register accesses in an existing SV initial block."""

    if not plan.register_models or not plan.protocol_models:
        return ()
    model = plan.protocol_models[0]
    lines: list[str] = ["        // Executable generated register accesses."]
    for register in plan.register_models:
        if register.offset is None:
            continue
        lines.append(f"        // {register.name} offset {register.offset} width {register.width}.")
        assignments: tuple[tuple[str, str], ...]
        if model.name == "APB4":
            assignments = (
                ("paddr", str(register.offset or 0)),
                ("pwrite", "1'b1"),
                ("psel", "1'b1"),
                ("penable", "1'b0"),
            )
        elif model.name == "AHB-Lite":
            assignments = (
                ("haddr", str(register.offset or 0)),
                ("hwrite", "1'b1"),
                ("hsel", "1'b1"),
                ("htrans", "2'b10"),
            )
        else:
            assignments = (("awaddr", str(register.offset or 0)), ("awvalid", "1'b1"), ("wvalid", "1'b1"))
        directions = dict(model.signal_directions)
        bindings = dict(model.signal_bindings)
        for canonical, value in assignments:
            actual = bindings.get(canonical)
            if actual and directions.get(canonical) in {"input", "inout", "ref"}:
                lines.append(f"        {actual} = {value};")
        lines.append("        @(posedge " + (model.clock_domain or "clk") + ");")
        if model.name == "APB4":
            actual = bindings.get("penable")
            if actual and directions.get("penable") in {"input", "inout", "ref"}:
                lines.append(f"        {actual} = 1'b1;")
            lines.append("        @(posedge " + (model.clock_domain or "clk") + ");")
    return tuple(lines)
