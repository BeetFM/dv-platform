"""Executable protocol snippets shared by generation backends."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import VerificationPlan


def signal(model: ProtocolModel, canonical: str) -> str | None:
    return dict(model.signal_bindings).get(canonical)


def input_signal(model: ProtocolModel, canonical: str) -> str | None:
    actual = signal(model, canonical)
    directions = dict(model.signal_directions)
    return actual if actual is not None and directions.get(canonical) in {"input", "inout", "ref"} else None


def cocotb_protocol_lines(plan: VerificationPlan, clock_name: str) -> tuple[str, ...]:
    lines: list[str] = []
    models = tuple(plan.protocol_models)
    if not models:
        return ()
    lines.extend(["", "    await _exercise_mapped_protocols(dut, " + repr(clock_name) + ")"])
    body = [
        "",
        "",
        "async def _exercise_mapped_protocols(dut, clock_name):",
        "    clock = _maybe_signal(dut, clock_name) if clock_name is not None else None",
        "    if clock is None:",
        "        return",
    ]
    for index, model in enumerate(models, start=1):
        body.extend([f"    # Executable {model.name} transfer probe {index}."])
        if model.name == "AXI4-Lite":
            for canonical in ("awvalid", "wvalid", "arvalid", "bready", "rready"):
                actual = input_signal(model, canonical)
                if actual:
                    body.append(f"    _drive_if_present(dut, {actual!r}, 0)")
            body.extend(["    await _sample_cycle(clock)"])
        elif model.name == "APB4":
            for canonical, value in (("psel", 1), ("penable", 0), ("pwrite", 0)):
                actual = input_signal(model, canonical)
                if actual:
                    body.append(f"    _drive_if_present(dut, {actual!r}, {value})")
            body.extend(["    await _sample_cycle(clock)"])
            actual = input_signal(model, "penable")
            if actual:
                body.append(f"    _drive_if_present(dut, {actual!r}, 1)")
                body.append("    await _sample_cycle(clock)")
        elif model.name == "AHB-Lite":
            for canonical, value in (("hsel", 1), ("htrans", 2), ("hwrite", 0)):
                actual = input_signal(model, canonical)
                if actual:
                    body.append(f"    _drive_if_present(dut, {actual!r}, {value})")
            body.append("    await _sample_cycle(clock)")
    for register in plan.register_models:
        if register.offset is None:
            continue
        body.append(f"    # Executable register access probe for {register.name} at offset {register.offset}.")
        model = models[0]
        if model.name == "AXI4-Lite":
            for canonical, value in (("awaddr", register.offset or 0), ("wdata", 0), ("awvalid", 1), ("wvalid", 1)):
                actual = input_signal(model, canonical)
                if actual:
                    body.append(f"    _drive_if_present(dut, {actual!r}, {value})")
            body.append("    await _sample_cycle(clock)")
        elif model.name == "APB4":
            for canonical, value in (
                ("paddr", register.offset or 0),
                ("pwdata", 0),
                ("pwrite", 1),
                ("psel", 1),
                ("penable", 0),
            ):
                actual = input_signal(model, canonical)
                if actual:
                    body.append(f"    _drive_if_present(dut, {actual!r}, {value})")
            body.append("    await _sample_cycle(clock)")
            actual = input_signal(model, "penable")
            if actual:
                body.append(f"    _drive_if_present(dut, {actual!r}, 1)")
                body.append("    await _sample_cycle(clock)")
        elif model.name == "AHB-Lite":
            for canonical, value in (
                ("haddr", register.offset or 0),
                ("hwdata", 0),
                ("hwrite", 1),
                ("hsel", 1),
                ("htrans", 2),
            ):
                actual = input_signal(model, canonical)
                if actual:
                    body.append(f"    _drive_if_present(dut, {actual!r}, {value})")
            body.append("    await _sample_cycle(clock)")
    body.append("    return")
    lines.extend(body)
    return tuple(lines)


def sv_protocol_assertions(plan: VerificationPlan, clock_name: str | None) -> tuple[str, ...]:
    if clock_name is None:
        return ()
    lines: list[str] = []
    for _index, model in enumerate(plan.protocol_models, start=1):
        if model.name == "AXI4-Lite":
            valid = signal(model, "awvalid") or signal(model, "arvalid")
            ready = signal(model, "awready") or signal(model, "arready")
            if valid and ready:
                lines.extend(
                    (
                        f"    assert property (@(posedge {clock_name}) ({valid} && !{ready}) |=> $stable({valid}));",
                        f"    cover property (@(posedge {clock_name}) ({valid} && {ready}));",
                    )
                )
        elif model.name == "APB4":
            psel, penable, pready = signal(model, "psel"), signal(model, "penable"), signal(model, "pready")
            if psel and penable and pready:
                lines.extend(
                    (
                        f"    assert property (@(posedge {clock_name}) ({psel} && !{penable}) |=> {psel} && {penable});",
                        f"    assert property (@(posedge {clock_name}) ({psel} && {penable} && !{pready}) |=> {psel} && {penable});",
                        f"    cover property (@(posedge {clock_name}) ({psel} && {penable} && {pready}));",
                    )
                )
        elif model.name == "AHB-Lite":
            hsel, htrans, hready = signal(model, "hsel"), signal(model, "htrans"), signal(model, "hready")
            if hsel and htrans and hready:
                lines.extend(
                    (
                        f"    assert property (@(posedge {clock_name}) ({hsel} && {htrans}[1] && !{hready}) |=> $stable({haddr(model)}));",
                        f"    cover property (@(posedge {clock_name}) ({hsel} && {htrans}[1] && {hready}));",
                    )
                )
    return tuple(lines)


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


def vhdl_protocol_accesses(plan: VerificationPlan, clock_name: str | None) -> tuple[str, ...]:
    """Emit typed VHDL control-plane accesses when port directions are known."""

    if not plan.protocol_models or clock_name is None:
        return ()
    model = plan.protocol_models[0]
    directions = dict(model.signal_directions)
    bindings = dict(model.signal_bindings)
    lines = ["        -- Executable mapped protocol/register access."]
    assignments = {
        "APB4": (("psel", "'1'"), ("penable", "'0'"), ("pwrite", "'1'")),
        "AHB-Lite": (("hsel", "'1'"), ("hwrite", "'1'"), ("htrans", "(others => '0')")),
        "AXI4-Lite": (("awvalid", "'1'"), ("wvalid", "'1'")),
    }.get(model.name, ())
    for canonical, value in assignments:
        actual = bindings.get(canonical)
        if canonical == "htrans":
            detail = next((port for port in plan.ports if port.name == actual), None)
            if detail is None or detail.width is None or detail.width < 2:
                continue
        if actual and directions.get(canonical) in {"input", "inout", "ref"}:
            lines.append(f"        {actual} <= {value};")
    lines.append(f"        wait until rising_edge({clock_name});")
    if model.name == "APB4":
        actual = bindings.get("penable")
        if actual and directions.get("penable") in {"input", "inout", "ref"}:
            lines.append(f"        {actual} <= '1';")
        lines.append(f"        wait until rising_edge({clock_name});")
    return tuple(lines)


def haddr(model: ProtocolModel) -> str:
    return signal(model, "haddr") or "1'b0"
