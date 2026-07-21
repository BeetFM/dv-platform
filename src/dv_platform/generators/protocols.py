"""Executable protocol snippets shared by generation backends."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable


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


def cocotb_apb4_scenario_lines(plan: VerificationPlan, clock_name: str) -> tuple[str, ...]:
    """Render independently reported APB4 scenarios with bounded completion and an oracle."""

    model = next((item for item in plan.protocol_models if item.name == "APB4"), None)
    scenarios = tuple(
        item
        for item in plan.scenarios
        if item.kind.startswith("apb4_") and scenario_is_executable(item, VerificationTarget.COCOTB)
    )
    if model is None or not scenarios:
        return ()
    bindings = dict(model.signal_bindings)
    register_specs = {
        register.name: {
            "offset": register.offset,
            "width": register.width,
            "fields": [
                (field.name, field.msb, field.lsb, field.access.lower(), field.reset_value) for field in register.fields
            ],
        }
        for register in plan.register_models
        if register.offset is not None
    }
    lines: list[str] = [
        "",
        "",
        f"_APB_BINDINGS = {bindings!r}",
        f"_APB_REGISTERS = {register_specs!r}",
        "",
        "",
        "class APB4Monitor:",
        "    def __init__(self):",
        "        self.transactions = []",
        "",
        "    def observe(self, operation, address, data, error):",
        "        self.transactions.append((operation, address, data, error))",
        "",
        "",
        "class APB4RegisterReferenceModel:",
        "    def __init__(self, specs):",
        "        self.specs = specs",
        "        self.values = {name: 0 for name in specs}",
        "        for name, spec in specs.items():",
        "            for _field, msb, lsb, _access, reset in spec['fields']:",
        "                if reset is not None:",
        "                    text = str(reset).lower().replace('_', '')",
        '                    if "\'h" in text:',
        '                        parsed = int(text.split("\'h", 1)[1], 16)',
        '                    elif "\'d" in text:',
        '                        parsed = int(text.split("\'d", 1)[1], 10)',
        '                    elif "\'b" in text:',
        '                        parsed = int(text.split("\'b", 1)[1], 2)',
        "                    else:",
        "                        parsed = int(text, 0)",
        "                    self.values[name] |= (parsed & ((1 << (msb - lsb + 1)) - 1)) << lsb",
        "",
        "    def write(self, name, data, strobe):",
        "        spec = self.specs[name]",
        "        current = self.values[name]",
        "        byte_mask = sum(0xFF << (index * 8) for index in range((spec['width'] + 7) // 8) if strobe & (1 << index))",
        "        for _field, msb, lsb, access, _reset in spec['fields']:",
        "            mask = ((1 << (msb - lsb + 1)) - 1) << lsb",
        "            selected = mask & byte_mask",
        "            if access == 'rw':",
        "                current = (current & ~selected) | (data & selected)",
        "            elif access == 'w1c':",
        "                current &= ~(data & selected)",
        "        self.values[name] = current",
        "",
        "",
        "class APB4Driver:",
        "    def __init__(self, dut, clock, bindings, monitor):",
        "        self.dut = dut",
        "        self.clock = clock",
        "        self.bindings = bindings",
        "        self.monitor = monitor",
        "",
        "    def drive(self, canonical, value):",
        "        _drive_if_present(self.dut, self.bindings.get(canonical), value)",
        "",
        "    def sample(self, canonical):",
        "        return _signal_int(self.dut, self.bindings.get(canonical))",
        "",
        "    async def transfer(self, address, write=False, data=0, strobe=None, timeout_cycles=32):",
        "        self.drive('paddr', address)",
        "        self.drive('pwrite', int(write))",
        "        self.drive('pwdata', data)",
        "        if strobe is not None:",
        "            self.drive('pstrb', strobe)",
        "        self.drive('psel', 1)",
        "        self.drive('penable', 0)",
        "        await _sample_cycle(self.clock)",
        "        self.drive('penable', 1)",
        "        for _cycle in range(timeout_cycles):",
        "            await _sample_cycle(self.clock)",
        "            if self.sample('pready') == 1:",
        "                result = self.sample('prdata') if not write else data",
        "                error = self.sample('pslverr') or 0",
        "                self.monitor.observe('write' if write else 'read', address, result, error)",
        "                self.drive('psel', 0)",
        "                self.drive('penable', 0)",
        "                return result, error",
        "        self.drive('psel', 0)",
        "        self.drive('penable', 0)",
        "        raise AssertionError(f'APB4 transfer timed out after {timeout_cycles} cycles at 0x{address:x}')",
    ]
    for scenario in scenarios:
        suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
        timeout = scenario.completion.timeout_cycles
        lines.extend(
            [
                "",
                "",
                "@cocotb.test()",
                f"async def test_{_identifier(plan.module)}_scenario_{suffix}(dut):",
                f"    clock = _maybe_signal(dut, {clock_name!r})",
                "    assert clock is not None, 'APB4 scenario requires its normalized clock'",
                "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
                "    monitor = APB4Monitor()",
                "    driver = APB4Driver(dut, clock, _APB_BINDINGS, monitor)",
                "    model = APB4RegisterReferenceModel(_APB_REGISTERS)",
            ]
        )
        if scenario.kind == "apb4_register_access" and scenario.oracle.expected in register_specs:
            name = scenario.oracle.expected
            offset = register_specs[name]["offset"]
            raw_width = register_specs[name]["width"]
            width = raw_width if isinstance(raw_width, int) else 32
            strobe = (1 << ((width + 7) // 8)) - 1
            lines.extend(
                [
                    f"    model.write({name!r}, 0xA5A5A5A5, {strobe})",
                    f"    _written, write_error = await driver.transfer({offset}, write=True, data=0xA5A5A5A5, strobe={strobe}, timeout_cycles={timeout})",
                    "    assert write_error == 0, 'mapped register write unexpectedly asserted PSLVERR'",
                    f"    observed, read_error = await driver.transfer({offset}, timeout_cycles={timeout})",
                    "    assert read_error == 0, 'mapped register read unexpectedly asserted PSLVERR'",
                    f"    assert observed == model.values[{name!r}], 'APB4 register scoreboard mismatch'",
                ]
            )
        else:
            lines.extend(
                [
                    f"    _data, _error = await driver.transfer(0, timeout_cycles={timeout})",
                    "    assert len(monitor.transactions) == 1, 'APB4 monitor did not observe exactly one completion'",
                ]
            )
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
                stable_signals = tuple(
                    actual
                    for canonical in ("paddr", "pwrite", "pwdata", "pstrb", "pprot")
                    if (actual := signal(model, canonical)) is not None
                )
                stable_expr = ", ".join(stable_signals)
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


def _identifier(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character == "_" else "_" for character in value)
    return normalized if normalized and not normalized[0].isdigit() else "dut_" + normalized
