"""Executable protocol snippets shared by generation backends."""

from __future__ import annotations

import json

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import VerificationPlan, VerificationScenario, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable


def signal(model: ProtocolModel, canonical: str) -> str | None:
    return dict(model.signal_bindings).get(canonical)


def input_signal(model: ProtocolModel, canonical: str) -> str | None:
    actual = signal(model, canonical)
    directions = dict(model.signal_directions)
    return actual if actual is not None and directions.get(canonical) in {"input", "inout", "ref"} else None


def cocotb_protocol_lines(plan: VerificationPlan, clock_name: str) -> tuple[str, ...]:
    lines: list[str] = []
    # APB4 collateral is emitted only from typed scenarios below; retaining a
    # second model-driven probe would create untracked duplicate intent.
    models = tuple(model for model in plan.protocol_models if model.name not in {"APB4", "AXI4-Lite"})
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
    """Render self-checking APB4 tests exclusively from typed scenario payloads."""

    scenarios = tuple(
        item
        for item in plan.scenarios
        if item.kind.startswith("apb4_") and scenario_is_executable(item, VerificationTarget.COCOTB)
    )
    if not scenarios:
        return ()
    profile_stimulus = next(
        (stimulus for scenario in scenarios for stimulus in scenario.stimulus if stimulus.kind == "apb4_profile"),
        None,
    )
    if profile_stimulus is None:
        return ()
    profile = dict(profile_stimulus.parameters)
    bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
    register_specs: dict[str, dict[str, object]] = {}
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
            register_specs[str(decoded["name"])] = decoded
    lines: list[str] = [
        "",
        "",
        f"_APB_PROFILE = {profile!r}",
        f"_APB_BINDINGS = {bindings!r}",
        f"_APB_REGISTERS = {register_specs!r}",
        "",
        "",
        "class APB4Monitor:",
        "    def __init__(self):",
        "        self.transactions = []",
        "        self.coverage = set()",
        "",
        "    def observe(self, operation, address, data, error, strobe, wait_cycles, phases):",
        "        self.transactions.append({",
        "            'operation': operation, 'address': address, 'data': data, 'error': error,",
        "            'strobe': strobe, 'wait_cycles': wait_cycles, 'phases': tuple(phases),",
        "        })",
        "        self.coverage.update({'setup', 'access', operation + '-completion'})",
        "        if wait_cycles:",
        "            self.coverage.add('wait-state')",
        "        if error:",
        "            self.coverage.update({'invalid-address', 'pslverr'})",
        "",
        "",
        "class APB4RegisterReferenceModel:",
        "    def __init__(self, specs):",
        "        self.specs = specs",
        "        self.reset()",
        "",
        "    def reset(self):",
        "        self.values = {name: 0 for name in self.specs}",
        "        for name, spec in self.specs.items():",
        "            for field in spec['fields']:",
        "                msb, lsb, reset = field['msb'], field['lsb'], field['reset']",
        "                if reset is not None:",
        "                    parsed = _apb_literal(reset)",
        "                    self.values[name] |= (parsed & ((1 << (msb - lsb + 1)) - 1)) << lsb",
        "",
        "    def write(self, name, data, strobe):",
        "        spec = self.specs[name]",
        "        current = self.values[name]",
        "        byte_mask = sum(0xFF << (index * 8) for index in range((spec['width'] + 7) // 8) if strobe & (1 << index))",
        "        for field in spec['fields']:",
        "            msb, lsb, access = field['msb'], field['lsb'], field['access']",
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
        "    async def reset(self, cycles=2):",
        "        reset_name = _APB_PROFILE['reset']",
        "        active_low = _APB_PROFILE['reset_active_low'] == 'true'",
        "        self.drive('psel', 0)",
        "        self.drive('penable', 0)",
        "        _drive_if_present(self.dut, reset_name, 0 if active_low else 1)",
        "        for _ in range(cycles):",
        "            await _sample_cycle(self.clock)",
        "        _drive_if_present(self.dut, reset_name, 1 if active_low else 0)",
        "        await _sample_cycle(self.clock)",
        "        self.monitor.coverage.add('reset')",
        "",
        "    async def transfer(self, address, write=False, data=0, strobe=None, timeout_cycles=32):",
        "        width_bytes = max(1, max(spec['width'] for spec in _APB_REGISTERS.values()) // 8)",
        "        effective_strobe = ((1 << width_bytes) - 1) if strobe is None else strobe",
        "        self.drive('paddr', address)",
        "        self.drive('pwrite', int(write))",
        "        self.drive('pwdata', data)",
        "        self.drive('pstrb', effective_strobe)",
        "        self.drive('psel', 1)",
        "        self.drive('penable', 0)",
        "        phases = ['setup']",
        "        await _sample_cycle(self.clock)",
        "        assert self.sample('psel') == 1 and self.sample('penable') == 0, 'APB4 setup phase was not held for one cycle'",
        "        self.drive('penable', 1)",
        "        expected_controls = {",
        "            'paddr': address, 'pwrite': int(write), 'pwdata': data, 'pstrb': effective_strobe, 'psel': 1, 'penable': 1,",
        "        }",
        "        wait_cycles = 0",
        "        wait_response = None",
        "        for _cycle in range(timeout_cycles):",
        "            await _sample_cycle(self.clock)",
        "            phases.append('access')",
        "            for canonical, expected in expected_controls.items():",
        "                assert self.sample(canonical) == expected, f'APB4 control {canonical} changed during access/wait'",
        "            if self.sample('pready') == 1:",
        "                result = self.sample('prdata') if not write else data",
        "                error = self.sample('pslverr') or 0",
        "                phases.append('complete')",
        "                self.monitor.observe(",
        "                    'write' if write else 'read', address, result, error, effective_strobe, wait_cycles, phases",
        "                )",
        "                self.drive('psel', 0)",
        "                self.drive('penable', 0)",
        "                return result, error, wait_cycles",
        "            response = (self.sample('prdata'), self.sample('pslverr'))",
        "            if wait_response is not None:",
        "                assert response == wait_response, 'APB4 response changed during wait state'",
        "            wait_response = response",
        "            phases.append('wait')",
        "            wait_cycles += 1",
        "        self.drive('psel', 0)",
        "        self.drive('penable', 0)",
        "        raise AssertionError(f'APB4 transfer timed out after {timeout_cycles} cycles at 0x{address:x}')",
        "",
        "",
        "def _apb_literal(value):",
        "    text = str(value).lower().replace('_', '')",
        '    if "\'h" in text:',
        '        return int(text.split("\'h", 1)[1], 16)',
        '    if "\'d" in text:',
        '        return int(text.split("\'d", 1)[1], 10)',
        '    if "\'b" in text:',
        '        return int(text.split("\'b", 1)[1], 2)',
        "    return int(text, 0)",
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
                "    await driver.reset()",
            ]
        )
        if scenario.kind == "apb4_register_access" and scenario.oracle.expected in register_specs:
            name = scenario.oracle.expected
            spec = register_specs[name]
            offset = spec["offset"]
            assert isinstance(offset, int)
            raw_width = spec["width"]
            width = raw_width if isinstance(raw_width, int) else 32
            strobe = (1 << ((width + 7) // 8)) - 1
            lines.extend(
                [
                    f"    reset_value, reset_error, _wait = await driver.transfer({offset}, timeout_cycles={timeout})",
                    "    assert reset_error == 0, 'mapped register reset read unexpectedly asserted PSLVERR'",
                    f"    assert reset_value == model.values[{name!r}], 'APB4 register reset value mismatch'",
                    f"    model.write({name!r}, 0xA5A5A5A5, {strobe})",
                    f"    _written, write_error, _wait = await driver.transfer({offset}, write=True, data=0xA5A5A5A5, strobe={strobe}, timeout_cycles={timeout})",
                    "    assert write_error == 0, 'mapped register write unexpectedly asserted PSLVERR'",
                    f"    observed, read_error, _wait = await driver.transfer({offset}, timeout_cycles={timeout})",
                    "    assert read_error == 0, 'mapped register read unexpectedly asserted PSLVERR'",
                    f"    assert observed == model.values[{name!r}], 'APB4 register scoreboard mismatch'",
                    f"    model.write({name!r}, 0x5A5A5A5A, 0)",
                    f"    _written, write_error, _wait = await driver.transfer({offset}, write=True, data=0x5A5A5A5A, strobe=0, timeout_cycles={timeout})",
                    "    assert write_error == 0, 'zero-strobe write unexpectedly asserted PSLVERR'",
                    f"    observed, read_error, _wait = await driver.transfer({offset}, timeout_cycles={timeout})",
                    f"    assert observed == model.values[{name!r}], 'APB4 PSTRB/field-policy scoreboard mismatch'",
                    "    await driver.reset()",
                    "    model.reset()",
                    f"    observed, read_error, _wait = await driver.transfer({offset}, timeout_cycles={timeout})",
                    f"    assert observed == model.values[{name!r}], 'APB4 register reset recovery mismatch'",
                    "    assert {'reset', 'setup', 'access', 'read-completion', 'write-completion'} <= monitor.coverage, 'APB4 register coverage was vacuous'",
                ]
            )
        else:
            valid_address = int(profile.get("valid_address", "0"), 0)
            invalid_address = int(profile.get("invalid_address", "4"), 0)
            lines.extend(
                [
                    f"    _data, valid_error, _wait = await driver.transfer({valid_address}, timeout_cycles={timeout})",
                    "    assert valid_error == 0, 'valid APB4 address unexpectedly asserted PSLVERR'",
                    f"    _data, invalid_error, _wait = await driver.transfer({invalid_address}, timeout_cycles={timeout})",
                    "    assert invalid_error == 1, 'invalid APB4 address did not assert PSLVERR'",
                    "    assert len(monitor.transactions) == 2, 'APB4 monitor did not observe both completions'",
                    "    assert {'reset', 'setup', 'access', 'read-completion', 'invalid-address', 'pslverr'} <= monitor.coverage, 'APB4 protocol coverage was vacuous'",
                ]
            )
    return tuple(lines)


def cocotb_axi4_lite_scenario_lines(plan: VerificationPlan, clock_name: str) -> tuple[str, ...]:
    """Render the bounded independent-channel AXI4-Lite scenario."""

    scenario = next(
        (
            item
            for item in plan.scenarios
            if item.kind == "axi4_lite_single_outstanding" and scenario_is_executable(item, VerificationTarget.COCOTB)
        ),
        None,
    )
    if scenario is None:
        return ()
    profile_stimulus = next((item for item in scenario.stimulus if item.kind == "axi4_lite_profile"), None)
    if profile_stimulus is None:
        return ()
    profile = dict(profile_stimulus.parameters)
    bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
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
        return ()
    suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
    timeout = scenario.completion.timeout_cycles
    lines = [
        "",
        "",
        f"_AXI_PROFILE = {profile!r}",
        f"_AXI_BINDINGS = {bindings!r}",
        f"_AXI_REGISTERS = {specs!r}",
        "",
        "",
        "class AXI4LiteMonitor:",
        "    def __init__(self):",
        "        self.coverage = set()",
        "        self.writes = []",
        "        self.reads = []",
        "",
        "",
        "class AXI4LiteReferenceModel:",
        "    def __init__(self, specs):",
        "        self.specs = specs",
        "        self.reset()",
        "",
        "    def reset(self):",
        "        self.values = {name: 0 for name in self.specs}",
        "        for name, spec in self.specs.items():",
        "            for field in spec['fields']:",
        "                value = int(str(field['reset']), 0)",
        "                width = field['msb'] - field['lsb'] + 1",
        "                self.values[name] |= (value & ((1 << width) - 1)) << field['lsb']",
        "",
        "    def write(self, name, data, strobe):",
        "        spec, current = self.specs[name], self.values[name]",
        "        byte_mask = sum(0xFF << (lane * 8) for lane in range((spec['width'] + 7) // 8) if strobe & (1 << lane))",
        "        for field in spec['fields']:",
        "            mask = ((1 << (field['msb'] - field['lsb'] + 1)) - 1) << field['lsb']",
        "            selected = mask & byte_mask",
        "            if field['access'] == 'rw':",
        "                current = (current & ~selected) | (data & selected)",
        "            elif field['access'] == 'w1c':",
        "                current &= ~(data & selected)",
        "        self.values[name] = current",
        "",
        "",
        "class AXI4LiteDriver:",
        "    def __init__(self, dut, clock, bindings, monitor):",
        "        self.dut, self.clock, self.bindings, self.monitor = dut, clock, bindings, monitor",
        "",
        "    def drive(self, name, value):",
        "        _drive_if_present(self.dut, self.bindings.get(name), value)",
        "",
        "    def sample(self, name):",
        "        return _signal_int(self.dut, self.bindings.get(name))",
        "",
        "    async def reset(self):",
        "        for name in ('awvalid', 'wvalid', 'bready', 'arvalid', 'rready'):",
        "            self.drive(name, 0)",
        "        reset_name = _AXI_PROFILE['reset']",
        "        active_low = _AXI_PROFILE['reset_active_low'] == 'true'",
        "        _drive_if_present(self.dut, reset_name, 0 if active_low else 1)",
        "        await _sample_cycle(self.clock)",
        "        await _sample_cycle(self.clock)",
        "        _drive_if_present(self.dut, reset_name, 1 if active_low else 0)",
        "        await _sample_cycle(self.clock)",
        "        assert self.sample('bvalid') == 0 and self.sample('rvalid') == 0, 'AXI4-Lite reset did not clear responses'",
        "        self.monitor.coverage.add('reset')",
        "",
        "    async def write(self, address, data, strobe, aw_delay, w_delay, timeout, check_second=False):",
        "        self.drive('awaddr', address); self.drive('wdata', data); self.drive('wstrb', strobe)",
        "        self.drive('bready', 0)",
        "        aw_done = w_done = False; aw_cycle = w_cycle = None",
        "        for cycle in range(timeout):",
        "            self.drive('awvalid', int(not aw_done and cycle >= aw_delay))",
        "            self.drive('wvalid', int(not w_done and cycle >= w_delay))",
        "            aw_ready = self.sample('awready')",
        "            w_ready = self.sample('wready')",
        "            assert not (self.sample('bvalid') and not (aw_done and w_done)), 'AXI4-Lite produced BVALID before both AW and W requests'",
        "            await _sample_cycle(self.clock)",
        "            if not aw_done and cycle >= aw_delay and aw_ready:",
        "                aw_done = True; aw_cycle = cycle; self.drive('awvalid', 0); self.monitor.coverage.add('AW')",
        "                if check_second:",
        "                    self.drive('awaddr', address + 4); self.drive('awvalid', 1)",
        "                    await _sample_cycle(self.clock)",
        "                    assert self.sample('awready') == 0, 'AXI4-Lite accepted a second outstanding AW request'",
        "                    self.drive('awvalid', 0); self.drive('awaddr', address)",
        "            if not w_done and cycle >= w_delay and w_ready:",
        "                w_done = True; w_cycle = cycle; self.drive('wvalid', 0); self.monitor.coverage.add('W')",
        "            if aw_done and w_done:",
        "                break",
        "        assert aw_done and w_done, 'AXI4-Lite AW/W request timed out'",
        "        if aw_delay < w_delay:",
        "            assert aw_cycle < w_cycle, 'AXI4-Lite coupled AW and W acceptance'",
        "            self.monitor.coverage.add('AW-before-W')",
        "        elif w_delay < aw_delay:",
        "            assert w_cycle < aw_cycle, 'AXI4-Lite coupled W and AW acceptance'",
        "            self.monitor.coverage.add('W-before-AW')",
        "        else:",
        "            assert aw_cycle == w_cycle, 'AXI4-Lite same-cycle acceptance split unexpectedly'",
        "            self.monitor.coverage.add('same-cycle')",
        "        for _ in range(timeout):",
        "            await _sample_cycle(self.clock)",
        "            if self.sample('bvalid'): break",
        "        assert self.sample('bvalid') == 1, 'AXI4-Lite BVALID was lost or never produced'",
        "        self.monitor.coverage.add('B')",
        "        response = self.sample('bresp')",
        "        await _sample_cycle(self.clock); await _sample_cycle(self.clock)",
        "        assert self.sample('bvalid') == 1, 'AXI4-Lite BVALID dropped under backpressure'",
        "        assert self.sample('bresp') == response, 'AXI4-Lite BRESP changed under backpressure'",
        "        self.monitor.coverage.add('B-backpressure')",
        "        self.drive('bready', 1); await _sample_cycle(self.clock); self.drive('bready', 0)",
        "        self.monitor.writes.append((address, data, strobe, response))",
        "        return response",
        "",
        "    async def read(self, address, timeout, check_second=False):",
        "        self.drive('araddr', address); self.drive('arvalid', 1); self.drive('rready', 0)",
        "        for _ in range(timeout):",
        "            ar_ready = self.sample('arready')",
        "            await _sample_cycle(self.clock)",
        "            if ar_ready: break",
        "        assert ar_ready == 1, 'AXI4-Lite AR request timed out'",
        "        self.monitor.coverage.add('AR')",
        "        if check_second:",
        "            self.drive('araddr', address + 4)",
        "            await _sample_cycle(self.clock)",
        "            assert self.sample('arready') == 0, 'AXI4-Lite accepted a second outstanding AR request'",
        "            self.drive('araddr', address)",
        "        self.drive('arvalid', 0)",
        "        for _ in range(timeout):",
        "            await _sample_cycle(self.clock)",
        "            if self.sample('rvalid'): break",
        "        assert self.sample('rvalid') == 1, 'AXI4-Lite RVALID was lost or never produced'",
        "        self.monitor.coverage.add('R')",
        "        data, response = self.sample('rdata'), self.sample('rresp')",
        "        await _sample_cycle(self.clock); await _sample_cycle(self.clock)",
        "        assert self.sample('rvalid') == 1, 'AXI4-Lite RVALID dropped under backpressure'",
        "        assert (self.sample('rdata'), self.sample('rresp')) == (data, response), 'AXI4-Lite R payload changed under backpressure'",
        "        self.monitor.coverage.add('R-backpressure')",
        "        self.drive('rready', 1); await _sample_cycle(self.clock); self.drive('rready', 0)",
        "        self.monitor.reads.append((address, data, response))",
        "        return data, response",
        "",
        "",
        "@cocotb.test()",
        f"async def test_{_protocol_identifier(plan.module)}_scenario_{suffix}(dut):",
        f"    clock = _maybe_signal(dut, {clock_name!r})",
        "    assert clock is not None, 'AXI4-Lite scenario requires its normalized clock'",
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    monitor = AXI4LiteMonitor(); driver = AXI4LiteDriver(dut, clock, _AXI_BINDINGS, monitor)",
        "    model = AXI4LiteReferenceModel(_AXI_REGISTERS)",
        "    await driver.reset()",
    ]
    first_name, first_spec = next(iter(specs.items()))
    offset = int(str(first_spec["offset"]))
    register_width = int(str(first_spec["width"]))
    full_strobe = (1 << ((register_width + 7) // 8)) - 1
    write_value = int("a5" * ((register_width + 7) // 8), 16) & ((1 << register_width) - 1)
    invalid = int(profile["invalid_address"], 0)
    lines.extend(
        (
            f"    initial, response = await driver.read({offset}, {timeout}, check_second=True)",
            f"    assert response == 0 and initial == model.values[{first_name!r}], 'AXI4-Lite reset read mismatch'",
            "    for aw_delay, w_delay in ((0, 2), (2, 0), (0, 0)):",
            f"        model.write({first_name!r}, {write_value}, {full_strobe})",
            f"        response = await driver.write({offset}, {write_value}, {full_strobe}, aw_delay, w_delay, {timeout}, check_second=(aw_delay == 0 and w_delay == 2))",
            "        assert response == 0, 'AXI4-Lite valid write returned an error'",
            f"        observed, response = await driver.read({offset}, {timeout})",
            f"        assert response == 0 and observed == model.values[{first_name!r}], 'AXI4-Lite independent-channel scoreboard mismatch'",
            f"    model.write({first_name!r}, {(1 << register_width) - 1}, 0)",
            f"    assert await driver.write({offset}, {(1 << register_width) - 1}, 0, 0, 0, {timeout}) == 0",
            f"    observed, response = await driver.read({offset}, {timeout})",
            f"    assert observed == model.values[{first_name!r}], 'AXI4-Lite WSTRB scoreboard mismatch'",
            "    monitor.coverage.add('WSTRB')",
            f"    concurrent_value = {write_value} ^ {(1 << register_width) - 1}",
            f"    write_task = cocotb.start_soon(driver.write({offset}, concurrent_value, {full_strobe}, 0, 1, {timeout}))",
            f"    _data, read_response = await driver.read({invalid}, {timeout})",
            "    write_response = await write_task",
            "    assert write_response == 0 and read_response != 0, 'independent AXI4-Lite read/write progress failed'",
            f"    model.write({first_name!r}, concurrent_value, {full_strobe})",
            "    monitor.coverage.add('concurrent-read-write')",
            f"    assert await driver.write({invalid}, 0, {full_strobe}, 0, 0, {timeout}) != 0, 'invalid AXI4-Lite write did not return an error'",
            f"    _data, response = await driver.read({invalid}, {timeout})",
            "    assert response != 0, 'invalid AXI4-Lite read did not return an error'",
            "    monitor.coverage.update({'invalid-address', 'BRESP-error', 'RRESP-error'})",
            "    await driver.reset(); model.reset()",
            f"    observed, response = await driver.read({offset}, {timeout})",
            f"    assert observed == model.values[{first_name!r}], 'AXI4-Lite reset recovery mismatch'",
            "    required = {'reset', 'AW', 'W', 'B', 'AR', 'R', 'AW-before-W', 'W-before-AW', 'same-cycle', 'B-backpressure', 'R-backpressure', 'WSTRB', 'concurrent-read-write', 'invalid-address', 'BRESP-error', 'RRESP-error'}",
            "    assert required <= monitor.coverage, 'AXI4-Lite scenario coverage was vacuous'",
        )
    )
    return tuple(lines)


def sv_protocol_assertions(plan: VerificationPlan, clock_name: str | None) -> tuple[str, ...]:
    if clock_name is None:
        return ()
    lines: list[str] = []
    for _index, model in enumerate(plan.protocol_models, start=1):
        if model.name == "AXI4-Lite":
            # AXI4-Lite assertions are rendered below from the typed bounded
            # scenario profile rather than the recognition model.
            continue
        elif model.name == "APB4":
            # APB assertions are rendered below from the typed scenario profile,
            # never directly from the protocol-recognition model.
            continue
        elif model.name == "AHB-Lite":
            hsel, htrans, hready = signal(model, "hsel"), signal(model, "htrans"), signal(model, "hready")
            if hsel and htrans and hready:
                lines.extend(
                    (
                        f"    assert property (@(posedge {clock_name}) ({hsel} && {htrans}[1] && !{hready}) |=> $stable({haddr(model)}));",
                        f"    cover property (@(posedge {clock_name}) ({hsel} && {htrans}[1] && {hready}));",
                    )
                )
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
