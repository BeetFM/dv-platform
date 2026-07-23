"""Built-in APB, AXI-Lite, and AHB-Lite formal generation."""

from __future__ import annotations

import json

from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import VerificationPlan, VerificationScenario, VerificationTarget
from dv_platform.generators.protocols.common import _OPEN_FORMAL_RESPONSE_BOUND
from dv_platform.generators.scenario_registry import scenario_is_executable


def formal_apb4_declarations(plan: VerificationPlan) -> tuple[str, ...]:
    """Declare state used by the typed APB4 formal reference model."""

    payload = _apb4_scenario_payload(plan, VerificationTarget.FORMAL)
    if payload is None:
        return ()
    _profile, specs, timeout, scenarios = payload
    counter_width = max(1, timeout.bit_length())
    lines = [
        "    // State for executable typed APB4 scenarios.",
        f"    reg [{counter_width - 1}:0] dv_apb_wait_count = '0;",
    ]
    for name, spec in specs.items():
        width = int(str(spec["width"]))
        reset_value = _apb4_reset_value(spec)
        lines.append(
            f"    reg [{width - 1}:0] dv_apb_expected_{_protocol_identifier(name)} = {width}'h{reset_value:x};"
        )
    lines.extend(f"    // scenario={scenario.scenario_id}" for scenario in scenarios)
    return tuple(lines)


def formal_axi4_lite_declarations(plan: VerificationPlan) -> tuple[str, ...]:
    payload = _axi4_lite_scenario_payload(plan, VerificationTarget.FORMAL)
    if payload is None:
        return ()
    _profile, specs, timeout, scenario = payload
    width = max(int(str(spec["width"])) for spec in specs.values())
    counter_width = max(1, timeout.bit_length())
    lines = [
        "    // State for executable typed bounded AXI4-Lite scenario.",
        "    reg dv_axi_have_aw = 1'b0, dv_axi_have_w = 1'b0, dv_axi_read_pending = 1'b0;",
        f"    reg [{width - 1}:0] dv_axi_awaddr = '0, dv_axi_araddr = '0, dv_axi_wdata = '0;",
        f"    reg [{width - 1}:0] dv_axi_read_expected = '0;",
        f"    reg [{max(1, width // 8) - 1}:0] dv_axi_wstrb = '0;",
        f"    reg [{counter_width - 1}:0] dv_axi_write_wait = '0, dv_axi_read_wait = '0;",
    ]
    for name, spec in specs.items():
        register_width = int(str(spec["width"]))
        reset_value = _apb4_reset_value(spec)
        lines.append(
            f"    reg [{register_width - 1}:0] dv_axi_expected_{_protocol_identifier(name)} = "
            f"{register_width}'h{reset_value:x};"
        )
    lines.append(f"    // scenario={scenario.scenario_id}")
    return tuple(lines)


def formal_ahb_lite_declarations(plan: VerificationPlan) -> tuple[str, ...]:
    payload = _ahb_lite_scenario_payload(plan, VerificationTarget.FORMAL)
    if payload is None:
        return ()
    _profile, specs, timeout, scenario = payload
    counter_width = max(1, timeout.bit_length())
    width = max(int(str(spec["width"])) for spec in specs.values())
    lines = [
        "    // State for executable typed bounded AHB-Lite scenario.",
        "    reg dv_ahb_pending = 1'b0;",
        f"    reg [{width - 1}:0] dv_ahb_address = '0, dv_ahb_write_data = '0;",
        "    reg dv_ahb_write = 1'b0;",
        f"    reg [{counter_width - 1}:0] dv_ahb_wait = '0;",
    ]
    for name, spec in specs.items():
        width = int(str(spec["width"]))
        lines.append(
            f"    reg [{width - 1}:0] dv_ahb_expected_{_protocol_identifier(name)} = "
            f"{width}'h{_apb4_reset_value(spec):x};"
        )
    lines.append(f"    // scenario={scenario.scenario_id}")
    return tuple(lines)


def formal_ahb_lite_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
) -> tuple[str, ...]:
    payload = _ahb_lite_scenario_payload(plan, VerificationTarget.FORMAL)
    if payload is None or reset_name is None or reset_active is None or reset_inactive is None:
        return ()
    profile, specs, timeout, _scenario = payload
    bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
    required = ("haddr", "htrans", "hwrite", "hready", "hreadyout", "hresp", "hsel", "hwdata", "hrdata")
    if any(not bindings.get(name) for name in required):
        return ()
    b = bindings
    invalid = int(profile["invalid_address"], 0)
    valid_offsets = tuple(int(str(spec["offset"])) for spec in specs.values())
    data_width = max(int(str(spec["width"])) for spec in specs.values())
    address_choices = " || ".join(f"({b['haddr']} == {address})" for address in (*valid_offsets, invalid))
    lines = [
        "        // Executable typed bounded AHB-Lite protocol and register scoreboard checks.",
        f"        if ({reset_name} == {reset_active}) begin",
        "            dv_ahb_pending <= 1'b0; dv_ahb_wait <= '0;",
    ]
    for name, spec in specs.items():
        width = int(str(spec["width"]))
        lines.append(
            f"            dv_ahb_expected_{_protocol_identifier(name)} <= {width}'h{_apb4_reset_value(spec):x};"
        )
    lines.extend(
        (
            "        end else begin",
            f"            assume({b['hready']} == 1'b1);",
            f"            assume({address_choices});",
            f"            assume(({b['hwdata']} == '0) || ({b['hwdata']} == {data_width}'h{(1 << data_width) - 1:x}));",
            "            if (dv_ahb_pending) begin",
            f"                assume({b['hsel']} && {b['htrans']}[1]);",
            f"                assume({b['haddr']} == dv_ahb_address && {b['hwrite']} == dv_ahb_write && "
            f"{b['hwdata']} == dv_ahb_write_data);",
            "            end",
            f"            if (!dv_ahb_pending && {b['hsel']} && {b['htrans']}[1] && {b['hready']}) begin",
            "                dv_ahb_pending <= 1'b1;",
            f"                dv_ahb_address <= {b['haddr']}; dv_ahb_write <= {b['hwrite']}; "
            f"dv_ahb_write_data <= {b['hwdata']};",
            "            end",
            f"            if (dv_ahb_pending && !{b['hreadyout']}) begin",
            f"                a_ahb_bounded_completion: assert(dv_ahb_wait < {timeout - 1});",
            "                dv_ahb_wait <= dv_ahb_wait + 1'b1;",
            "            end else dv_ahb_wait <= '0;",
            f"            if (dv_ahb_pending && {b['hreadyout']}) begin",
            "                dv_ahb_pending <= 1'b0;",
            f"                if (dv_ahb_address == {invalid}) a_ahb_invalid_hresp: assert({b['hresp']} != 0);",
            f"                else a_ahb_mapped_okay: assert({b['hresp']} == 0);",
            "            end",
        )
    )
    for name, spec in specs.items():
        identifier = _protocol_identifier(name)
        offset = int(str(spec["offset"]))
        expected = f"dv_ahb_expected_{identifier}"
        lines.extend(
            (
                f"            if (dv_ahb_pending && {b['hreadyout']} && !dv_ahb_write && "
                f"dv_ahb_address == {offset}) begin",
                f"                a_ahb_{identifier}_read_scoreboard: assert({b['hrdata']} == {expected});",
                "            end",
                f"            if (dv_ahb_pending && {b['hreadyout']} && dv_ahb_write && "
                f"dv_ahb_address == {offset}) begin",
            )
        )
        fields = spec.get("fields", ())
        if not isinstance(fields, list):
            fields = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            access = str(field["access"]).lower()
            if access not in {"rw", "w1c"}:
                continue
            for bit in range(int(field["lsb"]), int(field["msb"]) + 1):
                update = (
                    f"dv_ahb_write_data[{bit}]" if access == "rw" else f"{expected}[{bit}] & ~dv_ahb_write_data[{bit}]"
                )
                lines.append(f"                {expected}[{bit}] <= {update};")
        lines.append("            end")
    lines.extend(
        (
            f"            c_ahb_read: cover(dv_ahb_pending && !dv_ahb_write && {b['hreadyout']});",
            f"            c_ahb_write: cover(dv_ahb_pending && dv_ahb_write && {b['hreadyout']});",
            f"            c_ahb_wait: cover(dv_ahb_pending && !{b['hreadyout']});",
            f"            c_ahb_error: cover(dv_ahb_pending && {b['hreadyout']} && {b['hresp']});",
            "        end",
        )
    )
    return tuple(lines)


def formal_axi4_lite_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
) -> tuple[str, ...]:
    payload = _axi4_lite_scenario_payload(plan, VerificationTarget.FORMAL)
    if payload is None or reset_name is None or reset_active is None or reset_inactive is None:
        return ()
    profile, specs, timeout, _scenario = payload
    bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
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
    if any(not bindings.get(name) for name in required):
        return ()
    b = bindings
    invalid = int(profile["invalid_address"], 0)
    data_width = max(int(str(spec["width"])) for spec in specs.values())
    lines = [
        "        // Executable typed bounded AXI4-Lite channel and scoreboard checks.",
        f"        if ({reset_name} == {reset_active}) begin",
        "            dv_axi_have_aw <= 1'b0; dv_axi_have_w <= 1'b0; dv_axi_read_pending <= 1'b0;",
        "            dv_axi_read_expected <= '0;",
        "            dv_axi_write_wait <= '0; dv_axi_read_wait <= '0;",
    ]
    for name, spec in specs.items():
        width = int(str(spec["width"]))
        lines.append(
            f"            dv_axi_expected_{_protocol_identifier(name)} <= {width}'h{_apb4_reset_value(spec):x};"
        )
    lines.extend(
        (
            "        end else begin",
            f"            assume(({b['awaddr']} == {min(int(str(spec['offset'])) for spec in specs.values())}) || ({b['awaddr']} == {invalid}));",
            f"            assume(({b['araddr']} == {min(int(str(spec['offset'])) for spec in specs.values())}) || ({b['araddr']} == {invalid}));",
            f"            assume(({b['wdata']} == 0) || ({b['wdata']} == {data_width}'h{(1 << data_width) - 1:x}));",
            f"            assume(({b['wstrb']} == 0) || ({b['wstrb']} == 1) || (&{b['wstrb']}));",
            f"            if (!$initstate && $past({reset_name} == {reset_inactive}) && $past({b['awvalid']} && !{b['awready']})) begin",
            f"                assume({b['awvalid']} && $stable({b['awaddr']}));",
            "            end",
            f"            if (!$initstate && $past({reset_name} == {reset_inactive}) && $past({b['wvalid']} && !{b['wready']})) begin",
            f"                assume({b['wvalid']} && $stable({{{b['wdata']}, {b['wstrb']}}}));",
            "            end",
            f"            if (!$initstate && $past({reset_name} == {reset_inactive}) && $past({b['arvalid']} && !{b['arready']})) begin",
            f"                assume({b['arvalid']} && $stable({b['araddr']}));",
            "            end",
            "            if (dv_axi_have_aw) a_axi_no_second_aw: assert(!" + b["awready"] + ");",
            "            if (dv_axi_have_w) a_axi_no_second_w: assert(!" + b["wready"] + ");",
            "            if (dv_axi_read_pending) a_axi_no_second_ar: assert(!" + b["arready"] + ");",
            f"            if ({b['awvalid']} && {b['awready']}) begin",
            f"                dv_axi_have_aw <= 1'b1; dv_axi_awaddr <= {b['awaddr']};",
            "            end",
            f"            if ({b['wvalid']} && {b['wready']}) begin",
            f"                dv_axi_have_w <= 1'b1; dv_axi_wdata <= {b['wdata']}; dv_axi_wstrb <= {b['wstrb']};",
            "            end",
            f"            if (dv_axi_have_aw && dv_axi_have_w && !{b['bvalid']}) begin",
            f"                a_axi_bounded_bvalid: assert(dv_axi_write_wait < {timeout - 1});",
            "                dv_axi_write_wait <= dv_axi_write_wait + 1'b1;",
            "            end else dv_axi_write_wait <= '0;",
            f"            if ({b['bvalid']}) begin",
            "                a_axi_b_after_aw_w: assert(dv_axi_have_aw && dv_axi_have_w);",
            f"                if (dv_axi_awaddr == {invalid}) a_axi_invalid_bresp: assert({b['bresp']} != 0);",
            f"                if (!$initstate && $past({b['bvalid']} && !{b['bready']})) begin",
            f"                    a_axi_stable_b: assert({b['bvalid']} && $stable({b['bresp']}));",
            "                end",
            "            end",
            f"            if ({b['bvalid']} && {b['bready']}) begin dv_axi_have_aw <= 1'b0; dv_axi_have_w <= 1'b0; end",
            f"            if ({b['arvalid']} && {b['arready']}) begin",
            f"                dv_axi_read_pending <= 1'b1; dv_axi_araddr <= {b['araddr']};",
            f"                case ({b['araddr']})",
            *(
                f"                    {int(str(spec['offset']))}: dv_axi_read_expected <= dv_axi_expected_{_protocol_identifier(name)};"
                for name, spec in specs.items()
            ),
            "                    default: dv_axi_read_expected <= '0;",
            "                endcase",
            "            end",
            f"            if (dv_axi_read_pending && !{b['rvalid']}) begin",
            f"                a_axi_bounded_rvalid: assert(dv_axi_read_wait < {timeout - 1});",
            "                dv_axi_read_wait <= dv_axi_read_wait + 1'b1;",
            "            end else dv_axi_read_wait <= '0;",
            f"            if ({b['rvalid']}) begin",
            "                a_axi_r_after_ar: assert(dv_axi_read_pending);",
            f"                if (dv_axi_araddr == {invalid}) a_axi_invalid_rresp: assert({b['rresp']} != 0);",
            f"                if (!$initstate && $past({b['rvalid']} && !{b['rready']})) begin",
            f"                    a_axi_stable_r: assert({b['rvalid']} && $stable({{{b['rdata']}, {b['rresp']}}}));",
            "                end",
            "            end",
            f"            if ({b['rvalid']} && {b['rready']}) dv_axi_read_pending <= 1'b0;",
        )
    )
    for name, spec in specs.items():
        identifier = _protocol_identifier(name)
        offset = int(str(spec["offset"]))
        expected = f"dv_axi_expected_{identifier}"
        lines.extend(
            (
                f"            if ({b['bvalid']} && dv_axi_awaddr == {offset}) begin",
                f"                a_axi_{identifier}_write_okay: assert({b['bresp']} == 0);",
                "            end",
                f"            if (dv_axi_have_aw && dv_axi_have_w && !{b['bvalid']} && dv_axi_awaddr == {offset}) begin",
            )
        )
        fields = spec.get("fields", ())
        if not isinstance(fields, list):
            fields = []
        for field in fields:
            if not isinstance(field, dict) or str(field["access"]).lower() not in {"rw", "w1c"}:
                continue
            for bit in range(int(field["lsb"]), int(field["msb"]) + 1):
                update = (
                    f"dv_axi_wdata[{bit}]"
                    if str(field["access"]).lower() == "rw"
                    else f"{expected}[{bit}] & ~dv_axi_wdata[{bit}]"
                )
                lines.append(f"                if (dv_axi_wstrb[{bit // 8}]) {expected}[{bit}] <= {update};")
        lines.extend(
            (
                "            end",
                f"            if ({b['rvalid']} && dv_axi_araddr == {offset}) begin",
                f"                a_axi_{identifier}_read_okay: assert({b['rresp']} == 0);",
                f"                a_axi_{identifier}_read_scoreboard: assert({b['rdata']} == dv_axi_read_expected);",
                "            end",
            )
        )
    lines.extend(
        (
            f"            c_axi_aw: cover({b['awvalid']} && {b['awready']});",
            f"            c_axi_w: cover({b['wvalid']} && {b['wready']});",
            f"            c_axi_aw_before_w: cover({b['awvalid']} && {b['awready']} && !({b['wvalid']} && {b['wready']}));",
            f"            c_axi_w_before_aw: cover({b['wvalid']} && {b['wready']} && !({b['awvalid']} && {b['awready']}));",
            f"            c_axi_aw_w_same_cycle: cover({b['awvalid']} && {b['awready']} && {b['wvalid']} && {b['wready']});",
            f"            c_axi_b: cover({b['bvalid']} && {b['bready']});",
            f"            c_axi_b_backpressure: cover({b['bvalid']} && !{b['bready']});",
            f"            c_axi_ar: cover({b['arvalid']} && {b['arready']});",
            f"            c_axi_r: cover({b['rvalid']} && {b['rready']});",
            f"            c_axi_r_backpressure: cover({b['rvalid']} && !{b['rready']});",
            f"            c_axi_error: cover(({b['bvalid']} && {b['bresp']} != 0) || ({b['rvalid']} && {b['rresp']} != 0));",
            "        end",
        )
    )
    return tuple(lines)


def formal_apb4_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
) -> tuple[str, ...]:
    """Emit immediate assumptions, assertions, covers, and a register scoreboard.

    All bindings, timeouts, addresses, fields, and reset values come from the
    executable typed scenario payload.  The environment is constrained to a
    legal APB master; DUT response behavior remains unconstrained and proved.
    """

    payload = _apb4_scenario_payload(plan, VerificationTarget.FORMAL)
    if payload is None or reset_name is None or reset_active is None or reset_inactive is None:
        return ()
    profile, specs, timeout, _scenarios = payload
    timeout = min(timeout, _OPEN_FORMAL_RESPONSE_BOUND)
    bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
    required = ("psel", "penable", "pwrite", "paddr", "pwdata", "pstrb", "prdata", "pready", "pslverr")
    if any(not bindings.get(name) for name in required):
        return ()
    psel, penable, pwrite = (bindings[name] for name in ("psel", "penable", "pwrite"))
    paddr, pwdata, pstrb = (bindings[name] for name in ("paddr", "pwdata", "pstrb"))
    prdata, pready, pslverr = (bindings[name] for name in ("prdata", "pready", "pslverr"))
    stable_controls = ", ".join((paddr, pwrite, pwdata, pstrb, psel, penable))
    invalid_address = int(profile["invalid_address"], 0)
    lines = [
        "        // Executable typed APB4 protocol environment and response checks.",
        f"        if ({reset_name} == {reset_active}) begin",
        "            dv_apb_wait_count <= '0;",
    ]
    for name, spec in specs.items():
        width = int(str(spec["width"]))
        reset_value = _apb4_reset_value(spec)
        lines.append(f"            dv_apb_expected_{_protocol_identifier(name)} <= {width}'h{reset_value:x};")
    lines.extend(
        (
            "        end else begin",
            f"            assume(!{penable} || {psel});",
            f"            if (!$initstate && $past({reset_name} == {reset_inactive}) && $past({psel} && !{penable})) begin",
            f"                assume({psel} && {penable});",
            "            end",
            f"            if (!$initstate && $past({reset_name} == {reset_inactive}) && $past({psel} && {penable} && !{pready})) begin",
            f"                assume({psel} && {penable});",
            f"                assume($stable({{{stable_controls}}}));",
            "            end",
            f"            if ({psel} && {penable} && !{pready}) begin",
            f"                a_apb_bounded_completion: assert(dv_apb_wait_count < {timeout - 1});",
            "                dv_apb_wait_count <= dv_apb_wait_count + 1'b1;",
            f"                if (!$initstate && $past({psel} && {penable} && !{pready})) begin",
            f"                    a_apb_stable_wait_response: assert($stable({{{prdata}, {pslverr}}}));",
            "                end",
            "            end else begin",
            "                dv_apb_wait_count <= '0;",
            "            end",
            f"            c_apb_setup: cover({psel} && !{penable});",
            f"            c_apb_access: cover({psel} && {penable});",
            f"            c_apb_wait: cover({psel} && {penable} && !{pready});",
            f"            c_apb_read_complete: cover({psel} && {penable} && {pready} && !{pwrite});",
            f"            c_apb_write_complete: cover({psel} && {penable} && {pready} && {pwrite});",
            f"            if ({psel} && {penable} && {pready} && ({paddr} == {invalid_address})) begin",
            f"                a_apb_invalid_error: assert({pslverr});",
            f"                c_apb_error: cover({pslverr});",
            "            end",
        )
    )
    for name, spec in specs.items():
        identifier = _protocol_identifier(name)
        offset = int(str(spec["offset"]))
        expected = f"dv_apb_expected_{identifier}"
        lines.extend(
            (
                f"            if ({psel} && {penable} && {pready} && ({paddr} == {offset})) begin",
                f"                a_apb_{identifier}_mapped_no_error: assert(!{pslverr});",
                f"                if (!{pwrite}) begin",
                f"                    a_apb_{identifier}_read_scoreboard: assert({prdata} == {expected});",
                "                end else begin",
            )
        )
        fields = spec.get("fields", ())
        if not isinstance(fields, list):
            fields = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            access = str(field["access"]).lower()
            if access not in {"rw", "w1c"}:
                continue
            for bit in range(int(field["lsb"]), int(field["msb"]) + 1):
                if access == "rw":
                    update = f"{pwdata}[{bit}]"
                else:
                    update = f"{expected}[{bit}] & ~{pwdata}[{bit}]"
                lines.extend(
                    (
                        f"                    if ({pstrb}[{bit // 8}]) begin",
                        f"                        {expected}[{bit}] <= {update};",
                        "                    end",
                    )
                )
        lines.extend(("                end", "            end"))
    lines.append("        end")
    return tuple(lines)


def _apb4_scenario_payload(
    plan: VerificationPlan, target: VerificationTarget
) -> tuple[dict[str, str], dict[str, dict[str, object]], int, tuple[VerificationScenario, ...]] | None:
    scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind.startswith("apb4_") and scenario_is_executable(scenario, target)
    )
    if not scenarios:
        return None
    profile_stimulus = next((stimulus for stimulus in scenarios[0].stimulus if stimulus.kind == "apb4_profile"), None)
    if profile_stimulus is None:
        return None
    specs: dict[str, dict[str, object]] = {}
    for scenario in scenarios:
        encoded = next(
            (
                dict(stimulus.parameters).get("json")
                for stimulus in scenario.stimulus
                if stimulus.kind == "register_spec"
            ),
            None,
        )
        if encoded is None:
            continue
        decoded = json.loads(encoded)
        if isinstance(decoded, dict) and isinstance(decoded.get("name"), str):
            specs[str(decoded["name"])] = decoded
    if not specs:
        return None
    timeout = min(scenario.completion.timeout_cycles for scenario in scenarios)
    return dict(profile_stimulus.parameters), specs, timeout, scenarios


def _axi4_lite_scenario_payload(
    plan: VerificationPlan, target: VerificationTarget
) -> tuple[dict[str, str], dict[str, dict[str, object]], int, VerificationScenario] | None:
    scenario = next(
        (
            item
            for item in plan.scenarios
            if item.kind == "axi4_lite_single_outstanding" and scenario_is_executable(item, target)
        ),
        None,
    )
    if scenario is None:
        return None
    profile_stimulus = next((item for item in scenario.stimulus if item.kind == "axi4_lite_profile"), None)
    if profile_stimulus is None:
        return None
    specs: dict[str, dict[str, object]] = {}
    for stimulus in scenario.stimulus:
        if stimulus.kind != "register_spec":
            continue
        encoded = dict(stimulus.parameters).get("json")
        if encoded is None:
            continue
        decoded = json.loads(encoded)
        if isinstance(decoded, dict) and isinstance(decoded.get("name"), str):
            specs[str(decoded["name"])] = decoded
    if not specs:
        return None
    return dict(profile_stimulus.parameters), specs, scenario.completion.timeout_cycles, scenario


def _ahb_lite_scenario_payload(
    plan: VerificationPlan, target: VerificationTarget
) -> tuple[dict[str, str], dict[str, dict[str, object]], int, VerificationScenario] | None:
    scenario = next(
        (
            item
            for item in plan.scenarios
            if item.kind == "ahb_lite_single_beat" and scenario_is_executable(item, target)
        ),
        None,
    )
    if scenario is None:
        return None
    profile_stimulus = next((item for item in scenario.stimulus if item.kind == "ahb_lite_profile"), None)
    if profile_stimulus is None:
        return None
    specs: dict[str, dict[str, object]] = {}
    for stimulus in scenario.stimulus:
        if stimulus.kind != "register_spec":
            continue
        encoded = dict(stimulus.parameters).get("json")
        if encoded is None:
            continue
        decoded = json.loads(encoded)
        if isinstance(decoded, dict) and isinstance(decoded.get("name"), str):
            specs[str(decoded["name"])] = decoded
    if not specs:
        return None
    return dict(profile_stimulus.parameters), specs, scenario.completion.timeout_cycles, scenario


def _apb4_reset_value(spec: dict[str, object]) -> int:
    value = 0
    fields = spec.get("fields", ())
    if not isinstance(fields, list):
        return value
    for field in fields:
        if not isinstance(field, dict):
            continue
        lsb, msb = int(field["lsb"]), int(field["msb"])
        reset_text = str(field["reset"])
        parsed = sv_numeric_literal_to_int(reset_text, width=msb - lsb + 1)
        if parsed is None:
            try:
                parsed = int(reset_text, 0)
            except ValueError:
                parsed = None
        if parsed is not None:
            value |= (parsed & ((1 << (msb - lsb + 1)) - 1)) << lsb
    return value


def _protocol_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
