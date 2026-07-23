"""Built-in cocotb protocol generation."""

from __future__ import annotations

import json

from dv_platform.core.models import VerificationPlan, VerificationTarget
from dv_platform.generators.protocol_common import (
    _identifier,
)
from dv_platform.generators.protocol_formal_standard import (
    _ahb_lite_scenario_payload,
    _protocol_identifier,
)
from dv_platform.generators.scenario_registry import scenario_is_executable


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


def cocotb_ahb_lite_scenario_lines(plan: VerificationPlan, clock_name: str) -> tuple[str, ...]:
    """Render the bounded self-checking AHB-Lite single-beat scenario."""

    payload = _ahb_lite_scenario_payload(plan, VerificationTarget.COCOTB)
    if payload is None:
        return ()
    profile, specs, timeout, scenario = payload
    bindings = {key.removeprefix("binding."): value for key, value in profile.items() if key.startswith("binding.")}
    suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
    lines = [
        "",
        "",
        f"_AHB_PROFILE = {profile!r}",
        f"_AHB_BINDINGS = {bindings!r}",
        f"_AHB_REGISTERS = {specs!r}",
        "",
        "",
        "class AHBLiteReferenceModel:",
        "    def __init__(self, specs):",
        "        self.specs = specs",
        "        self.reset()",
        "",
        "    def reset(self):",
        "        self.values = {name: 0 for name in self.specs}",
        "        for name, spec in self.specs.items():",
        "            for field in spec['fields']:",
        "                width = field['msb'] - field['lsb'] + 1",
        "                self.values[name] |= (_ahb_literal(field['reset']) & ((1 << width) - 1)) << field['lsb']",
        "",
        "    def write(self, name, data):",
        "        current = self.values[name]",
        "        for field in self.specs[name]['fields']:",
        "            mask = ((1 << (field['msb'] - field['lsb'] + 1)) - 1) << field['lsb']",
        "            if field['access'] == 'rw':",
        "                current = (current & ~mask) | (data & mask)",
        "            elif field['access'] == 'w1c':",
        "                current &= ~(data & mask)",
        "        self.values[name] = current",
        "",
        "",
        "def _ahb_literal(value):",
        "    text = str(value).lower().replace('_', '')",
        '    if "\'h" in text:',
        '        return int(text.split("\'h", 1)[1], 16)',
        '    if "\'d" in text:',
        '        return int(text.split("\'d", 1)[1], 10)',
        '    if "\'b" in text:',
        '        return int(text.split("\'b", 1)[1], 2)',
        "    return int(text, 0)",
        "",
        "",
        "class AHBLiteMonitor:",
        "    def __init__(self):",
        "        self.coverage = set()",
        "        self.transactions = []",
        "",
        "    def observe(self, operation, address, data, error, waits):",
        "        self.transactions.append((operation, address, data, error, waits))",
        "        self.coverage.add(operation + '-completion')",
        "        if waits:",
        "            self.coverage.update({'wait-state', 'stable-control'})",
        "        if error:",
        "            self.coverage.update({'invalid-address', 'hresp-error'})",
        "",
        "",
        "class AHBLiteDriver:",
        "    def __init__(self, dut, clock, monitor):",
        "        self.dut = dut",
        "        self.clock = clock",
        "        self.monitor = monitor",
        "",
        "    def drive(self, canonical, value):",
        "        _drive_if_present(self.dut, _AHB_BINDINGS.get(canonical), value)",
        "",
        "    def sample(self, canonical):",
        "        return _signal_int(self.dut, _AHB_BINDINGS.get(canonical))",
        "",
        "    async def reset(self, cycles=2):",
        "        active_low = _AHB_PROFILE['reset_active_low'] == 'true'",
        "        self.drive('hsel', 0)",
        "        self.drive('htrans', 0)",
        "        self.drive('hready', 1)",
        "        _drive_if_present(self.dut, _AHB_PROFILE['reset'], 0 if active_low else 1)",
        "        for _ in range(cycles):",
        "            await _sample_cycle(self.clock)",
        "        _drive_if_present(self.dut, _AHB_PROFILE['reset'], 1 if active_low else 0)",
        "        await _sample_cycle(self.clock)",
        "        self.monitor.coverage.add('reset')",
        "",
        "    async def transfer(self, address, write=False, data=0, timeout_cycles=16):",
        "        self.drive('haddr', address)",
        "        self.drive('htrans', 2)",
        "        self.drive('hwrite', int(write))",
        "        self.drive('hsel', 1)",
        "        self.drive('hready', 1)",
        "        self.drive('hwdata', data)",
        "        expected = (address, 2, int(write), 1)",
        "        waits = 0",
        "        for _cycle in range(timeout_cycles):",
        "            await _sample_cycle(self.clock)",
        "            if self.sample('hreadyout') == 1:",
        "                result = data if write else self.sample('hrdata')",
        "                error = self.sample('hresp') or 0",
        "                self.monitor.observe('write' if write else 'read', address, result, error, waits)",
        "                self.drive('hsel', 0)",
        "                self.drive('htrans', 0)",
        "                await _sample_cycle(self.clock)",
        "                self.monitor.coverage.add('idle')",
        "                return result, error, waits",
        "            observed = (self.sample('haddr'), self.sample('htrans'), self.sample('hwrite'), self.sample('hsel'))",
        "            assert observed == expected, 'AHB-Lite address/control changed while HREADYOUT was low'",
        "            waits += 1",
        "        self.drive('hsel', 0)",
        "        self.drive('htrans', 0)",
        "        raise AssertionError(f'AHB-Lite transfer timed out after {timeout_cycles} cycles at 0x{address:x}')",
        "",
        "",
        "@cocotb.test()",
        f"async def test_{_identifier(plan.module)}_scenario_{suffix}(dut):",
        f"    clock = _maybe_signal(dut, {clock_name!r})",
        "    assert clock is not None, 'AHB-Lite scenario requires its normalized clock'",
        "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
        "    monitor = AHBLiteMonitor()",
        "    driver = AHBLiteDriver(dut, clock, monitor)",
        "    model = AHBLiteReferenceModel(_AHB_REGISTERS)",
        "    await driver.reset()",
        "    for name, spec in _AHB_REGISTERS.items():",
        f"        observed, error, _waits = await driver.transfer(spec['offset'], timeout_cycles={timeout})",
        "        assert error == 0 and observed == model.values[name], 'AHB-Lite register reset value mismatch'",
        "        model.write(name, 0xA5A5A5A5)",
        f"        _data, error, _waits = await driver.transfer(spec['offset'], write=True, data=0xA5A5A5A5, timeout_cycles={timeout})",
        "        assert error == 0, 'AHB-Lite mapped write unexpectedly asserted HRESP'",
        f"        observed, error, _waits = await driver.transfer(spec['offset'], timeout_cycles={timeout})",
        "        assert error == 0 and observed == model.values[name], 'AHB-Lite register scoreboard mismatch'",
        f"    _data, error, _waits = await driver.transfer(int(_AHB_PROFILE['invalid_address']), timeout_cycles={timeout})",
        "    assert error == 1, 'AHB-Lite invalid address did not assert HRESP'",
        "    await driver.reset()",
        "    model.reset()",
        "    first_name = next(iter(_AHB_REGISTERS))",
        "    first_spec = _AHB_REGISTERS[first_name]",
        f"    observed, error, _waits = await driver.transfer(first_spec['offset'], timeout_cycles={timeout})",
        "    assert error == 0 and observed == model.values[first_name], 'AHB-Lite reset recovery mismatch'",
        "    monitor.coverage.add('reset-recovery')",
        "    required = {'reset', 'idle', 'read-completion', 'write-completion', 'wait-state', 'stable-control', 'invalid-address', 'hresp-error', 'reset-recovery'}",
        "    assert required <= monitor.coverage, f'AHB-Lite coverage was vacuous: {sorted(required - monitor.coverage)}'",
    ]
    return tuple(lines)
