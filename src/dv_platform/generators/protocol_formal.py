"""Profile-neutral formal protocol generation."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import VerificationPlan
from dv_platform.generators.protocol_common import (
    _OPEN_FORMAL_RESPONSE_BOUND,
    _profile_handshake_specs,
    _profile_payload_fields,
    haddr,
    signal,
)
from dv_platform.generators.protocol_formal_standard import _protocol_identifier


def sv_protocol_assertions(plan: VerificationPlan, clock_name: str | None) -> tuple[str, ...]:
    if clock_name is None:
        return ()
    lines: list[str] = []
    for _index, model in enumerate(plan.protocol_models, start=1):
        lines.extend(_sv_model_assertions(model, clock_name))
    apb_scenarios = tuple(scenario for scenario in plan.scenarios if scenario.kind.startswith("apb4_"))
    profile_stimulus = next(
        (stimulus for scenario in apb_scenarios for stimulus in scenario.stimulus if stimulus.kind == "apb4_profile"),
        None,
    )
    if profile_stimulus is not None:
        profile = dict(profile_stimulus.parameters)
        bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
        psel, penable, pready = (bindings.get(name) for name in ("psel", "penable", "pready"))
        if psel and penable and pready:
            stable_expr = ", ".join(
                bindings[name] for name in ("paddr", "pwrite", "pwdata", "pstrb") if bindings.get(name)
            )
            lines.extend(
                (
                    f"    assert property (@(posedge {clock_name}) ({psel} && !{penable}) |=> {psel} && {penable});",
                    f"    assert property (@(posedge {clock_name}) ({psel} && {penable} && !{pready}) |=> {psel} && {penable});",
                    *(
                        (
                            f"    assert property (@(posedge {clock_name}) ({psel} && {penable} && !{pready}) |=> $stable({{{stable_expr}}}));",
                        )
                        if stable_expr
                        else ()
                    ),
                    f"    cover property (@(posedge {clock_name}) ({psel} && {penable} && {pready}));",
                )
            )
    axi_scenario = next(
        (scenario for scenario in plan.scenarios if scenario.kind == "axi4_lite_single_outstanding"), None
    )
    axi_stimulus = (
        next(
            (stimulus for stimulus in axi_scenario.stimulus if stimulus.kind == "axi4_lite_profile"),
            None,
        )
        if axi_scenario is not None
        else None
    )
    if axi_stimulus is not None:
        profile = dict(axi_stimulus.parameters)
        bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
        channel_payloads = (
            ("awvalid", "awready", ("awaddr",)),
            ("wvalid", "wready", ("wdata", "wstrb")),
            ("bvalid", "bready", ("bresp",)),
            ("arvalid", "arready", ("araddr",)),
            ("rvalid", "rready", ("rdata", "rresp")),
        )
        for valid_key, ready_key, payload_keys in channel_payloads:
            valid, ready = bindings.get(valid_key), bindings.get(ready_key)
            payload = [bindings[key] for key in payload_keys if bindings.get(key)]
            if not valid or not ready or len(payload) != len(payload_keys):
                continue
            stable = ", ".join((valid, *payload))
            lines.extend(
                (
                    f"    assert property (@(posedge {clock_name}) ({valid} && !{ready}) |=> $stable({{{stable}}}));",
                    f"    cover property (@(posedge {clock_name}) ({valid} && {ready}));",
                )
            )
    return tuple(lines)


def _sv_model_assertions(model: ProtocolModel, clock_name: str) -> tuple[str, ...]:
    if model.name in {"AXI4-Lite", "APB4"}:
        return ()
    if model.name == "AHB-Lite":
        hsel, htrans, hready = signal(model, "hsel"), signal(model, "htrans"), signal(model, "hready")
        if not (hsel and htrans and hready):
            return ()
        return (
            f"    assert property (@(posedge {clock_name}) ({hsel} && {htrans}[1] && !{hready}) |=> $stable({haddr(model)}));",
            f"    cover property (@(posedge {clock_name}) ({hsel} && {htrans}[1] && {hready}));",
        )
    if model.profile_id is None or not model.profile_id.endswith("-1.0"):
        return ()
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    lines: list[str] = []
    for pair_index, (valid_name, ready_name, accepted) in enumerate(_profile_handshake_specs(model), start=1):
        profile_valid, profile_ready = bindings[valid_name], bindings[ready_name]
        payload = tuple(bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings)
        accepted_expr = profile_ready if accepted else f"!{profile_ready}"
        stalled_expr = f"!{profile_ready}" if accepted else profile_ready
        stable = ", ".join((profile_valid, *payload))
        instance = _protocol_identifier(model.instance_id or model.profile_id)
        if directions.get(valid_name) == "output":
            lines.append(
                f"    assert property (@(posedge {clock_name}) ({profile_valid} && {stalled_expr}) |=> $stable({{{stable}}}));"
            )
        lines.append(
            f"    cover property (@(posedge {clock_name}) ({profile_valid} && {accepted_expr})); // {instance}_{pair_index}"
        )
    return tuple(lines)


def formal_profile_declarations(plan: VerificationPlan) -> tuple[str, ...]:
    """Declare bounded progress counters for every production-profile handshake."""

    lines: list[str] = []
    for model in plan.protocol_models:
        if model.profile_id is None or not model.profile_id.endswith("-1.0"):
            continue
        instance = _protocol_identifier(model.instance_id or model.profile_id)
        for index, _spec in enumerate(_profile_handshake_specs(model), start=1):
            lines.append(f"    integer dv_profile_wait_{instance}_{index} = 0;")
        if model.profile_id in {"axi4-stream-1.0", "avalon-st-1.0"}:
            lines.extend(
                (
                    f"    integer dv_profile_packet_beats_{instance} = 0;",
                    f"    reg dv_profile_packet_open_{instance} = 1'b0;",
                    f"    reg [63:0] dv_profile_packet_route_{instance} = '0;",
                )
            )
    return tuple(lines)


def formal_profile_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
) -> tuple[str, ...]:
    """Emit stability, bounded fairness/progress, and non-vacuity contracts."""

    lines: list[str] = []
    for model in plan.protocol_models:
        lines.extend(_formal_profile_model_assertions(model, reset_name, reset_active))
    return tuple(lines)


def _formal_profile_model_assertions(
    model: ProtocolModel,
    reset_name: str | None,
    reset_active: str | None,
) -> tuple[str, ...]:
    lines: list[str] = []
    if model.profile_id is None or not model.profile_id.endswith("-1.0"):
        return ()
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    instance = _protocol_identifier(model.instance_id or model.profile_id)
    for index, (valid_name, ready_name, accepted) in enumerate(_profile_handshake_specs(model), start=1):
        valid, ready = bindings[valid_name], bindings[ready_name]
        accepted_expr = ready if accepted else f"!{ready}"
        stalled_expr = f"!{ready}" if accepted else ready
        payload = tuple(bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings)
        stable_terms = " && ".join(f"$stable({name})" for name in (valid, *payload)) or "1'b1"
        source_is_dut = directions.get(valid_name) == "output"
        keyword = "assert" if source_is_dut else "assume"
        counter_keyword = "assume" if source_is_dut else "assert"
        counter = f"dv_profile_wait_{instance}_{index}"
        response_bound = min(model.timeout_cycles, _OPEN_FORMAL_RESPONSE_BOUND)
        # A DUT sink may remain blocked for the entire downstream
        # environment-fairness horizon while an earlier response drains.
        # Account for the sequential hand-off cycle without relaxing the
        # source-side fairness assumption.
        counter_relation = "<" if source_is_dut else "<="
        guard = f"{valid} && {stalled_expr}"
        lines.extend(
            (
                f"        if (!$initstate && $past({guard})) {keyword}({stable_terms});",
                f"        if ({reset_name} == {reset_active}) {counter} <= 0;"
                if reset_name and reset_active
                else f"        if ($initstate) {counter} <= 0;",
                f"        else if ({guard}) begin",
                f"            {counter} <= {counter} + 1;",
                f"            {counter_keyword}({counter} {counter_relation} {response_bound});",
                "        end else begin",
                f"            {counter} <= 0;",
                "        end",
                f"        cover({valid} && {accepted_expr});",
            )
        )
    lines.extend(_formal_profile_semantic_assertions(model, instance, bindings, directions, reset_name, reset_active))
    return tuple(lines)


def _formal_profile_semantic_assertions(
    model: ProtocolModel,
    instance: str,
    bindings: dict[str, str],
    directions: dict[str, str],
    reset_name: str | None,
    reset_active: str | None,
) -> tuple[str, ...]:
    lines: list[str] = []
    profile_id = model.profile_id
    if profile_id == "axi4-1.0":
        lines.extend(_formal_axi4_semantics(model, bindings, directions))
    elif profile_id == "axi4-stream-1.0" and all(name in bindings for name in ("tvalid", "tready", "tkeep")):
        keyword = "assert" if directions.get("tvalid") == "output" else "assume"
        legality = f"({bindings['tkeep']} != 0)"
        if "tstrb" in bindings:
            legality += f" && (({bindings['tstrb']} & ~{bindings['tkeep']}) == 0)"
        lines.append(f"        if ({bindings['tvalid']} && {bindings['tready']}) {keyword}({legality});")
        lines.extend(_formal_packet_state_lines(model, instance, bindings, directions, reset_name, reset_active))
    elif profile_id == "wishbone-b4-1.0":
        lines.extend(_formal_wishbone_semantics(bindings, directions))
    elif profile_id == "avalon-mm-1.0" and all(name in bindings for name in ("read", "write", "waitrequest")):
        keyword = "assert" if directions.get("read") == "output" else "assume"
        command = f"({bindings['read']} || {bindings['write']}) && !{bindings['waitrequest']}"
        legality = f"({bindings['read']} != {bindings['write']})"
        if "burstcount" in bindings:
            legality += (
                f" && ({bindings['burstcount']} >= 1) && ({bindings['burstcount']} <= {model.maximum_burst_length})"
            )
        lines.append(f"        if ({command}) {keyword}({legality});")
    elif profile_id == "avalon-st-1.0" and all(name in bindings for name in ("valid", "ready", "endofpacket", "empty")):
        keyword = "assert" if directions.get("valid") == "output" else "assume"
        lines.append(
            f"        if ({bindings['valid']} && {bindings['ready']} && !{bindings['endofpacket']}) {keyword}({bindings['empty']} == 0);"
        )
        lines.extend(_formal_packet_state_lines(model, instance, bindings, directions, reset_name, reset_active))
    elif profile_id == "ahb-1.0" and all(name in bindings for name in ("hsel", "htrans", "hready")):
        keyword = "assert" if directions.get("hsel") == "output" else "assume"
        lines.append(f"        if ({bindings['hsel']} && {bindings['hready']}) {keyword}({bindings['htrans']}[1]);")
    elif profile_id == "tilelink-ul-uh-1.0" and all(name in bindings for name in ("a_valid", "a_ready", "a_mask")):
        keyword = "assert" if directions.get("a_valid") == "output" else "assume"
        lines.append(
            f"        if ({bindings['a_valid']} && {bindings['a_ready']}) {keyword}({bindings['a_mask']} != 0);"
        )
    return tuple(lines)


def _formal_axi4_semantics(
    model: ProtocolModel,
    bindings: dict[str, str],
    directions: dict[str, str],
) -> tuple[str, ...]:
    lines: list[str] = []
    for prefix in ("aw", "ar"):
        names = tuple(prefix + suffix for suffix in ("valid", "ready", "addr", "len", "size", "burst"))
        if not all(name in bindings for name in names):
            continue
        valid, ready, address, length, size, burst = (bindings[name] for name in names)
        keyword = "assert" if directions.get(prefix + "valid") == "output" else "assume"
        lines.append(
            f"        if ({valid} && {ready}) {keyword}(({burst} <= 2) && ({length} < {model.maximum_burst_length}) && ((({address} & 12'hfff) + (({length} + 1) << {size})) <= 4096));"
        )
    if all(name in bindings for name in ("wvalid", "wready", "wstrb")):
        keyword = "assert" if directions.get("wvalid") == "output" else "assume"
        lines.append(f"        if ({bindings['wvalid']} && {bindings['wready']}) {keyword}({bindings['wstrb']} != 0);")
    return tuple(lines)


def _formal_wishbone_semantics(
    bindings: dict[str, str],
    directions: dict[str, str],
) -> tuple[str, ...]:
    lines: list[str] = []
    response_names = tuple(name for name in ("ack", "err", "rty") if name in bindings)
    responses = tuple(bindings[name] for name in response_names)
    if responses:
        keyword = "assert" if directions.get(response_names[0]) == "output" else "assume"
        response_sum = " + ".join(f"({name} ? 1 : 0)" for name in responses)
        lines.append(f"        {keyword}(({response_sum}) <= 1);")
    if all(name in bindings for name in ("cyc", "stb")):
        stall = bindings.get("stall")
        acceptance = f"{bindings['cyc']} && {bindings['stb']}" + (f" && !{stall}" if stall else "")
        keyword = "assert" if directions.get("stb") == "output" else "assume"
        legality = "1'b1"
        if "cti" in bindings:
            cti = bindings["cti"]
            legality = f"(({cti} == 0) || ({cti} == 1) || ({cti} == 2) || ({cti} == 7))"
        lines.append(f"        if ({acceptance}) {keyword}({legality});")
    return tuple(lines)


def _formal_packet_state_lines(
    model: ProtocolModel,
    instance: str,
    bindings: dict[str, str],
    directions: dict[str, str],
    reset_name: str | None,
    reset_active: str | None,
) -> tuple[str, ...]:
    route_names: tuple[str, ...]
    if model.profile_id == "axi4-stream-1.0":
        valid_name, ready_name, last_name = "tvalid", "tready", "tlast"
        route_names = ("tid", "tdest")
        start_name = None
    else:
        valid_name, ready_name, last_name = "valid", "ready", "endofpacket"
        route_names = ("channel",)
        start_name = "startofpacket"
    if last_name not in bindings:
        return ()
    valid, ready, last = bindings[valid_name], bindings[ready_name], bindings[last_name]
    keyword = "assert" if directions.get(valid_name) == "output" else "assume"
    count = f"dv_profile_packet_beats_{instance}"
    opened = f"dv_profile_packet_open_{instance}"
    route_state = f"dv_profile_packet_route_{instance}"
    route_signals = tuple(bindings[name] for name in route_names if name in bindings)
    route = "{" + ", ".join(route_signals) + "}" if route_signals else "64'b0"
    lines = [
        (
            f"        if ({reset_name} == {reset_active}) begin {count} <= 0; {opened} <= 1'b0; {route_state} <= '0; end"
            if reset_name and reset_active
            else f"        if ($initstate) begin {count} <= 0; {opened} <= 1'b0; {route_state} <= '0; end"
        ),
        f"        else if ({valid} && {ready}) begin",
    ]
    if start_name and start_name in bindings:
        start = bindings[start_name]
        lines.append(f"            {keyword}({start} == !{opened});")
    if route_signals:
        lines.extend(
            (
                f"            if ({opened}) {keyword}({route} == {route_state});",
                f"            else {route_state} <= {route};",
            )
        )
    lines.extend(
        (
            f"            if ({last}) begin {count} <= 0; {opened} <= 1'b0; end",
            f"            else begin {keyword}({count} < {model.timeout_cycles - 1}); {count} <= {count} + 1; {opened} <= 1'b1; end",
            "        end",
        )
    )
    return tuple(lines)
