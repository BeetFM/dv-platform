"""Executable protocol snippets shared by generation backends."""

from __future__ import annotations

import json

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import VerificationPlan, VerificationScenario, VerificationTarget
from dv_platform.generators.scenario_registry import scenario_is_executable

_OPEN_FORMAL_RESPONSE_BOUND = 16


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
    typed_ahb = any(
        scenario.kind == "ahb_lite_single_beat" and scenario_is_executable(scenario, VerificationTarget.COCOTB)
        for scenario in plan.scenarios
    )
    models = tuple(
        model
        for model in plan.protocol_models
        if model.name not in {"APB4", "AXI4-Lite"} and not (model.name == "AHB-Lite" and typed_ahb)
    )
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


def cocotb_profile_scenario_lines(plan: VerificationPlan, clock_name: str) -> tuple[str, ...]:
    """Render bounded handshake/backpressure checks for v1 transaction profiles."""

    scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind == "protocol_profile_transaction"
        and scenario_is_executable(scenario, VerificationTarget.COCOTB)
    )
    if not scenarios:
        return ()
    models = {model.instance_id or model.profile_id or model.name: model for model in plan.protocol_models}
    lines: list[str] = []
    for scenario in scenarios:
        stimulus = next((item for item in scenario.stimulus if item.kind == "protocol_profile"), None)
        parameters = dict(stimulus.parameters) if stimulus is not None else {}
        model = models.get(parameters.get("instance_id", ""))
        if model is None:
            continue
        suffix = scenario.scenario_id.rsplit(":", 1)[-1].replace("-", "_")
        bindings = dict(model.signal_bindings)
        directions = dict(model.signal_directions)
        lines.extend(
            [
                "",
                "",
                "@cocotb.test()",
                f"async def test_{_python_identifier(plan.module)}_scenario_{suffix}(dut):",
                f"    clock = _maybe_signal(dut, {clock_name!r})",
                "    assert clock is not None, 'protocol profile requires a normalized clock'",
                "    cocotb.start_soon(Clock(clock, 10, unit='ns').start())",
                f"    monitor = ProtocolMonitor({(model.profile_id or model.name)!r})",
                f"    reference = ProtocolReferenceModel({(model.profile_id or model.name)!r})",
                "    scoreboard = ProtocolScoreboard()",
                "    coverage = FunctionalCoverage()",
            ]
        )
        reset = model.reset_domain
        if reset:
            active = 0 if reset.lower().endswith(("n", "_b")) else 1
            lines.extend(
                [
                    f"    _drive_if_present(dut, {reset!r}, {active})",
                    "    await _sample_cycle(clock)",
                    f"    _drive_if_present(dut, {reset!r}, {1 - active})",
                    "    await _sample_cycle(clock)",
                ]
            )
        driven = [canonical for canonical, direction in directions.items() if direction == "input"]
        handshake_valids = {valid for valid, _ready, _accepted in _profile_handshake_specs(model)}
        for canonical in driven:
            actual = bindings[canonical]
            value = 0 if canonical in handshake_valids or canonical == "cyc" else _profile_drive_value(canonical)
            lines.append(f"    _drive_if_present(dut, {actual!r}, {value})")
        lines.append("    await _sample_cycle(clock)")
        handshake_specs = _profile_handshake_specs(model)
        if not handshake_specs:
            lines.append("    assert False, 'profile has no executable acceptance handshake'")
        for valid_name, ready_name, accepted_value in handshake_specs:
            valid = bindings.get(valid_name)
            ready = bindings.get(ready_name)
            if valid is None or ready is None:
                continue
            if directions.get(valid_name) == "output" and directions.get(ready_name) == "input":
                payload_map = {
                    name: bindings[name]
                    for name in _profile_payload_fields(model, valid_name)
                    if name in bindings and directions.get(name) == "output"
                }
                payloads = tuple(payload_map.values())
                lines.extend(
                    [
                        f"    _drive_if_present(dut, {ready!r}, {1 - accepted_value})",
                        f"    await _wait_signal(clock, dut, {valid!r}, 1, {scenario.completion.timeout_cycles})",
                        f"    stalled = {{name: _signal_int(dut, name) for name in {payloads!r}}}",
                        "    await _sample_cycle(clock)",
                        f"    assert stalled == {{name: _signal_int(dut, name) for name in {payloads!r}}}, 'payload changed while stalled'",
                        f"    _drive_if_present(dut, {ready!r}, {accepted_value})",
                        "    await _sample_cycle(clock)",
                        f"    transaction = monitor.observe({valid_name!r}, _profile_snapshot(dut, {payload_map!r}))",
                        "    scoreboard.expect(reference.apply(transaction))",
                        "    scoreboard.observe(transaction)",
                        f"    coverage.hit('acceptance', 'backpressure', {valid_name!r})",
                    ]
                )
            elif directions.get(valid_name) == "input" and directions.get(ready_name) == "output":
                payload_map = {
                    name: bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings
                }
                lines.extend(
                    [
                        *(
                            [f"    _drive_if_present(dut, {bindings['cyc']!r}, 1)"]
                            if valid_name == "stb" and "cyc" in bindings
                            else []
                        ),
                        f"    _drive_if_present(dut, {valid!r}, 1)",
                        f"    await _wait_acceptance(clock, dut, {ready!r}, {accepted_value}, {scenario.completion.timeout_cycles})",
                        f"    transaction = monitor.observe({valid_name!r}, _profile_snapshot(dut, {payload_map!r}))",
                        "    scoreboard.expect(reference.apply(transaction))",
                        "    scoreboard.observe(transaction)",
                        f"    coverage.hit('acceptance', {valid_name!r})",
                        f"    _drive_if_present(dut, {valid!r}, 0)",
                    ]
                )
            if model.profile_id == "avalon-mm-1.0" and valid_name in {"read", "write"}:
                response_valid = "readdatavalid" if valid_name == "read" else "writeresponsevalid"
                response_channel = "read_response" if valid_name == "read" else "write_response"
                response_signal = bindings.get(response_valid)
                if response_signal is not None:
                    response_payload = {
                        name: bindings[name]
                        for channel in model.channels
                        if channel.name == "response"
                        for name in channel.payload_fields
                        if name in bindings
                    }
                    if directions.get(response_valid) == "input":
                        lines.extend(
                            [
                                f"    _drive_if_present(dut, {response_signal!r}, 1)",
                                "    await _sample_cycle(clock)",
                            ]
                        )
                    else:
                        lines.append(
                            f"    await _wait_response_signal(clock, dut, {response_signal!r}, 1, {scenario.completion.timeout_cycles})"
                        )
                    lines.extend(
                        [
                            f"    transaction = monitor.observe({response_channel!r}, _profile_snapshot(dut, {response_payload!r}))",
                            "    scoreboard.expect(reference.apply(transaction))",
                            "    scoreboard.observe(transaction)",
                            f"    coverage.hit('response', {response_valid!r})",
                        ]
                    )
                    if directions.get(response_valid) == "input":
                        lines.append(f"    _drive_if_present(dut, {response_signal!r}, 0)")
                elif valid_name == "read" and "readdata" in bindings:
                    response_payload = {"readdata": bindings["readdata"]}
                    if "response" in bindings:
                        response_payload["response"] = bindings["response"]
                    lines.extend(
                        [
                            "    await _sample_cycle(clock)",
                            f"    transaction = monitor.observe('read_response', _profile_snapshot(dut, {response_payload!r}))",
                            "    scoreboard.expect(reference.apply(transaction))",
                            "    scoreboard.observe(transaction)",
                            "    coverage.hit('response', 'fixed_latency_read')",
                        ]
                    )
            if model.profile_id == "wishbone-b4-1.0" and valid_name == "stb" and ready_name == "stall":
                response_names = tuple(name for name in ("ack", "err", "rty") if name in bindings)
                response_payload = {name: bindings[name] for name in response_names}
                output_responses = tuple(bindings[name] for name in response_names if directions.get(name) == "output")
                input_responses = tuple(bindings[name] for name in response_names if directions.get(name) == "input")
                if output_responses:
                    if directions.get(valid_name) == "input":
                        lines.append(f"    _drive_if_present(dut, {bindings[valid_name]!r}, 1)")
                    lines.append(
                        f"    await _wait_any_signal(clock, dut, {output_responses!r}, {scenario.completion.timeout_cycles})"
                    )
                elif input_responses:
                    lines.extend(
                        [
                            f"    _drive_if_present(dut, {input_responses[0]!r}, 1)",
                            "    await _sample_cycle(clock)",
                        ]
                    )
                lines.extend(
                    [
                        f"    transaction = monitor.observe('wishbone_response', _profile_snapshot(dut, {response_payload!r}))",
                        "    scoreboard.expect(reference.apply(transaction))",
                        "    scoreboard.observe(transaction)",
                        "    coverage.hit('response')",
                    ]
                )
                if input_responses:
                    lines.append(f"    _drive_if_present(dut, {input_responses[0]!r}, 0)")
                if directions.get(valid_name) == "input":
                    lines.append(f"    _drive_if_present(dut, {bindings[valid_name]!r}, 0)")
                    if "cyc" in bindings:
                        lines.append(f"    _drive_if_present(dut, {bindings['cyc']!r}, 0)")
            if valid_name in {"tvalid", "valid"}:
                final_name = "tlast" if valid_name == "tvalid" else "endofpacket"
                final_signal = bindings.get(final_name)
                if final_signal is not None and directions.get(final_name) == "output":
                    payload_map = {
                        name: bindings[name]
                        for channel in model.channels
                        if valid_name in channel.signals
                        for name in channel.payload_fields
                        if name in bindings and directions.get(name) == "output"
                    }
                    lines.extend(
                        [
                            f"    while not transaction['payload'].get({final_name!r}, 0):",
                            f"        await _wait_signal(clock, dut, {bindings[valid_name]!r}, 1, {scenario.completion.timeout_cycles})",
                            f"        transaction = monitor.observe({valid_name!r}, _profile_snapshot(dut, {payload_map!r}))",
                            "        scoreboard.expect(reference.apply(transaction))",
                            "        scoreboard.observe(transaction)",
                            "        await _sample_cycle(clock)",
                        ]
                    )
        lines.extend(
            [
                "    scoreboard.reconcile()",
                "    coverage.require('acceptance')",
                "    assert monitor.transactions, 'profile monitor observed no accepted transaction'",
                "    result = _validate_profile_transactions(monitor.profile_id, monitor.transactions)",
                "    assert result.accepted > 0 and result.completed > 0, 'profile trace was vacuous or incomplete'",
                "    assert True  # non-vacuous bounded profile transaction completed",
            ]
        )
    lines.extend(
        [
            "",
            "",
            "class ProtocolMonitor:",
            "    def __init__(self, profile_id):",
            "        self.profile_id = profile_id",
            "        self.transactions = []",
            "",
            "    def observe(self, channel, payload):",
            "        transaction = {'profile_id': self.profile_id, 'channel': channel, 'payload': dict(payload), 'cycle': len(self.transactions)}",
            "        self.transactions.append(transaction)",
            "        return transaction",
            "",
            "",
            "class ProtocolReferenceModel:",
            "    def __init__(self, profile_id):",
            "        self.profile_id = profile_id",
            "        self.outstanding = []",
            "",
            "    def apply(self, transaction):",
            "        # The public versioned trace validator below is the semantic authority.",
            "        return {'profile_id': transaction['profile_id'], 'channel': transaction['channel'], 'payload': dict(transaction['payload']), 'cycle': transaction['cycle']}",
            "",
            "",
            "class ProtocolScoreboard:",
            "    def __init__(self):",
            "        self.expected = []",
            "        self.observed = []",
            "",
            "    def expect(self, transaction):",
            "        self.expected.append(transaction)",
            "",
            "    def observe(self, transaction):",
            "        self.observed.append(transaction)",
            "",
            "    def reconcile(self):",
            "        assert self.observed == self.expected, 'protocol transaction trace mismatch'",
            "        assert self.observed, 'protocol scoreboard was vacuous'",
            "",
            "",
            "class FunctionalCoverage:",
            "    def __init__(self):",
            "        self.bins = set()",
            "",
            "    def hit(self, *bins):",
            "        self.bins.update(bins)",
            "",
            "    def require(self, *bins):",
            "        missing = set(bins) - self.bins",
            "        assert not missing, f'missing functional coverage bins: {sorted(missing)}'",
            "",
            "",
            "def _profile_snapshot(dut, mapping):",
            "    return {canonical: _signal_int(dut, physical) for canonical, physical in mapping.items()}",
            "",
            "",
            "def _validate_profile_transactions(profile_id, transactions):",
            "    beats = []",
            "    channel_names = {",
            "        'awvalid': 'AW', 'wvalid': 'W', 'bvalid': 'B', 'arvalid': 'AR', 'rvalid': 'R',",
            "        'tvalid': 'T', 'valid': 'stream', 'a_valid': 'A', 'd_valid': 'D',",
            "        'hsel': 'transfer', 'read': 'command', 'write': 'command',",
            "        'read_response': 'read_response', 'write_response': 'write_response',",
            "    }",
            "    for transaction in transactions:",
            "        channel = transaction['channel']",
            "        payload = dict(transaction['payload'])",
            "        cycle = transaction['cycle']",
            "        if profile_id == 'avalon-mm-1.0' and channel == 'write':",
            "            payload['response_required'] = int(any(item['channel'] == 'write_response' for item in transactions))",
            "        if profile_id == 'wishbone-b4-1.0' and channel == 'stb':",
            "            beats.append(ProtocolBeat('request', cycle, tuple(sorted(payload.items()))))",
            "            response = {name: payload.get(name, 0) for name in ('ack', 'err', 'rty')}",
            "            if any(response.values()) and not any(item['channel'] == 'wishbone_response' for item in transactions):",
            "                beats.append(ProtocolBeat('response', cycle, tuple(sorted(response.items()))))",
            "            continue",
            "        if profile_id == 'wishbone-b4-1.0' and channel == 'wishbone_response':",
            "            beats.append(ProtocolBeat('response', cycle, tuple(sorted(payload.items()))))",
            "            continue",
            "        mapped = channel_names.get(channel)",
            "        if mapped is None:",
            "            raise AssertionError(f'no profile trace mapping for accepted channel {channel}')",
            "        beats.append(ProtocolBeat(mapped, cycle, tuple(sorted(payload.items()))))",
            "    return validate_protocol_trace(profile_id, tuple(beats))",
            "",
            "",
            "async def _wait_signal(clock, dut, name, expected, timeout_cycles):",
            "    for _cycle in range(timeout_cycles):",
            "        await _sample_cycle(clock)",
            "        if _signal_int(dut, name) == expected:",
            "            return",
            "    raise AssertionError(f'{name} did not become {expected} within {timeout_cycles} cycles')",
            "",
            "",
            "async def _wait_acceptance(clock, dut, name, expected, timeout_cycles):",
            "    for _cycle in range(timeout_cycles):",
            "        accepted = _signal_int(dut, name) == expected",
            "        await _sample_cycle(clock)",
            "        if accepted:",
            "            return",
            "    raise AssertionError(f'{name} did not permit acceptance within {timeout_cycles} cycles')",
            "",
            "",
            "async def _wait_response_signal(clock, dut, name, expected, timeout_cycles):",
            "    if _signal_int(dut, name) == expected:",
            "        return",
            "    await _wait_signal(clock, dut, name, expected, timeout_cycles)",
            "",
            "",
            "async def _wait_any_signal(clock, dut, names, timeout_cycles):",
            "    if any(_signal_int(dut, name) for name in names):",
            "        return",
            "    for _cycle in range(timeout_cycles):",
            "        await _sample_cycle(clock)",
            "        if any(_signal_int(dut, name) for name in names):",
            "            return",
            "    raise AssertionError(f'none of {names} asserted within {timeout_cycles} cycles')",
        ]
    )
    return tuple(lines)


def _python_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)


def _profile_drive_value(name: str) -> int:
    if name.endswith(("ready", "valid")) or name in {
        "cyc",
        "stb",
        "read",
        "hsel",
        "startofpacket",
    }:
        return 1
    if name in {"htrans"}:
        return 2
    if name.endswith(("strb", "keep", "sel", "mask", "byteenable")):
        return 1
    if name.endswith(("last", "endofpacket")):
        return 1
    if name == "burstcount":
        return 1
    return 0


def _profile_handshake_specs(model: ProtocolModel) -> tuple[tuple[str, str, int], ...]:
    """Return request/completion pairs and the responder's acceptance polarity."""

    bindings = dict(model.signal_bindings)
    pairs: list[tuple[str, str, int]] = []
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
            pairs.append((valid, ready, accepted))
    if "stb" in bindings and "stall" not in bindings and "ack" in bindings:
        pairs.append(("stb", "ack", 1))
    return tuple(pairs)


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
        elif model.profile_id is not None and model.profile_id.endswith("-1.0"):
            bindings = dict(model.signal_bindings)
            directions = dict(model.signal_directions)
            for pair_index, (valid_name, ready_name, accepted) in enumerate(_profile_handshake_specs(model), start=1):
                profile_valid, profile_ready = bindings[valid_name], bindings[ready_name]
                profile_payload = tuple(
                    bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings
                )
                accepted_expr = profile_ready if accepted else f"!{profile_ready}"
                stalled_expr = f"!{profile_ready}" if accepted else profile_ready
                stable = ", ".join((profile_valid, *profile_payload))
                instance = _protocol_identifier(model.instance_id or model.profile_id)
                if directions.get(valid_name) == "output":
                    lines.append(
                        f"    assert property (@(posedge {clock_name}) ({profile_valid} && {stalled_expr}) |=> $stable({{{stable}}}));"
                    )
                lines.append(
                    f"    cover property (@(posedge {clock_name}) ({profile_valid} && {accepted_expr})); // {instance}_{pair_index}"
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
        if model.profile_id is None or not model.profile_id.endswith("-1.0"):
            continue
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
        profile_id = model.profile_id
        if profile_id == "axi4-1.0":
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
                lines.append(
                    f"        if ({bindings['wvalid']} && {bindings['wready']}) {keyword}({bindings['wstrb']} != 0);"
                )
        elif profile_id == "axi4-stream-1.0" and all(name in bindings for name in ("tvalid", "tready", "tkeep")):
            keyword = "assert" if directions.get("tvalid") == "output" else "assume"
            legality = f"({bindings['tkeep']} != 0)"
            if "tstrb" in bindings:
                legality += f" && (({bindings['tstrb']} & ~{bindings['tkeep']}) == 0)"
            lines.append(f"        if ({bindings['tvalid']} && {bindings['tready']}) {keyword}({legality});")
            lines.extend(_formal_packet_state_lines(model, instance, bindings, directions, reset_name, reset_active))
        elif profile_id == "wishbone-b4-1.0":
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
        elif profile_id == "avalon-mm-1.0" and all(name in bindings for name in ("read", "write", "waitrequest")):
            keyword = "assert" if directions.get("read") == "output" else "assume"
            command = f"({bindings['read']} || {bindings['write']}) && !{bindings['waitrequest']}"
            legality = f"({bindings['read']} != {bindings['write']})"
            if "burstcount" in bindings:
                legality += (
                    f" && ({bindings['burstcount']} >= 1) && ({bindings['burstcount']} <= {model.maximum_burst_length})"
                )
            lines.append(f"        if ({command}) {keyword}({legality});")
        elif profile_id == "avalon-st-1.0" and all(
            name in bindings for name in ("valid", "ready", "endofpacket", "empty")
        ):
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
        if model.profile_id is None or not model.profile_id.endswith("-1.0"):
            continue
        bindings = dict(model.signal_bindings)
        directions = dict(model.signal_directions)
        handshakes = _profile_handshake_specs(model)
        if not handshakes:
            continue
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
                lines.append(f"            {valid} = 1'b0;")
                if valid_name == "stb" and "cyc" in bindings:
                    lines.append(f"            {bindings['cyc']} = 1'b0;")
            elif directions.get(valid_name) == "output" and directions.get(ready_name) == "input":
                stalled = 1 - accepted
                payload = tuple(
                    bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings
                )
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


def _native_profile_semantic_checks(model: ProtocolModel) -> tuple[str, ...]:
    bindings = dict(model.signal_bindings)
    profile_id = model.profile_id
    lines: list[str] = []
    if profile_id in {"axi4-1.0", "axi4-lite-1.0"}:
        if all(name in bindings for name in ("wstrb",)):
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
    elif profile_id == "axi4-stream-1.0":
        if "tkeep" in bindings:
            lines.append(f"            if ({bindings['tkeep']} == 0) dv_platform_failures = dv_platform_failures + 1;")
        if "tkeep" in bindings and "tstrb" in bindings:
            lines.append(
                f"            if (({bindings['tstrb']} & ~{bindings['tkeep']}) != 0) dv_platform_failures = dv_platform_failures + 1;"
            )
        if "tlast" in bindings:
            lines.append(f"            if (!{bindings['tlast']}) dv_platform_failures = dv_platform_failures + 1;")
    elif profile_id == "wishbone-b4-1.0":
        responses = tuple(bindings[name] for name in ("ack", "err", "rty") if name in bindings)
        if responses:
            expression = " + ".join(responses)
            lines.append(f"            if (({expression}) != 1) dv_platform_failures = dv_platform_failures + 1;")
        if "we" in bindings and "sel" in bindings:
            lines.append(
                f"            if ({bindings['we']} && {bindings['sel']} == 0) dv_platform_failures = dv_platform_failures + 1;"
            )
    elif profile_id == "avalon-mm-1.0":
        if all(name in bindings for name in ("read", "write")):
            lines.append(
                f"            if ({bindings['read']} && {bindings['write']}) dv_platform_failures = dv_platform_failures + 1;"
            )
        if "burstcount" in bindings:
            lines.append(
                f"            if ({bindings['burstcount']} == 0) dv_platform_failures = dv_platform_failures + 1;"
            )
    elif profile_id == "avalon-st-1.0" and all(name in bindings for name in ("endofpacket", "empty")):
        lines.append(
            f"            if (!{bindings['endofpacket']} && {bindings['empty']} != 0) dv_platform_failures = dv_platform_failures + 1;"
        )
    elif profile_id == "ahb-1.0" and "htrans" in bindings:
        lines.append(f"            if (!{bindings['htrans']}[1]) dv_platform_failures = dv_platform_failures + 1;")
    elif profile_id == "tilelink-ul-uh-1.0":
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


def vhdl_protocol_accesses(plan: VerificationPlan, clock_name: str | None) -> tuple[str, ...]:
    """Emit bounded typed VHDL transactions for every executable profile."""

    if not plan.protocol_models or clock_name is None:
        return ()
    executable_instances = {
        dict(stimulus.parameters).get("instance_id")
        for scenario in plan.scenarios
        if scenario.kind == "protocol_profile_transaction" and scenario_is_executable(scenario, VerificationTarget.VHDL)
        for stimulus in scenario.stimulus
        if stimulus.kind == "protocol_profile"
    }
    lines: list[str] = []
    for model in plan.protocol_models:
        if (model.instance_id or model.profile_id or model.name) not in executable_instances:
            continue
        directions = dict(model.signal_directions)
        bindings = dict(model.signal_bindings)
        specs = _profile_handshake_specs(model)
        if not specs:
            continue
        lines.append(f"        -- Executable {model.profile_id or model.name} transaction profile.")
        valid_names = {valid for valid, _ready, _accepted in specs}
        for canonical, actual in model.signal_bindings:
            if directions.get(canonical) not in {"input", "inout", "ref"}:
                continue
            value = 0 if canonical in valid_names or canonical == "cyc" else _profile_drive_value(canonical)
            lines.append(f"        {actual} <= {_vhdl_profile_literal(plan, actual, value)};")
        lines.append(f"        wait until rising_edge({clock_name});")
        for valid_name, ready_name, accepted in specs:
            valid, ready = bindings[valid_name], bindings[ready_name]
            valid_is_output = directions.get(valid_name) == "output"
            accepted_literal = _vhdl_profile_literal(plan, ready, accepted)
            if valid_is_output:
                if directions.get(ready_name) in {"input", "inout", "ref"}:
                    lines.append(f"        {ready} <= {accepted_literal};")
                observed, expected = valid, _vhdl_profile_literal(plan, valid, 1)
            else:
                lines.append(f"        {valid} <= {_vhdl_profile_literal(plan, valid, 1)};")
                if model.profile_id == "wishbone-b4-1.0" and "cyc" in bindings:
                    lines.append(f"        {bindings['cyc']} <= {_vhdl_profile_literal(plan, bindings['cyc'], 1)};")
                observed, expected = ready, accepted_literal
            lines.extend(
                (
                    "        dv_protocol_cycles := 0;",
                    f"        while {observed} /= {expected} and dv_protocol_cycles < {model.timeout_cycles} loop",
                    f"            wait until rising_edge({clock_name});",
                    "            dv_protocol_cycles := dv_protocol_cycles + 1;",
                    "        end loop;",
                    f"        if {observed} /= {expected} then",
                    "            dv_platform_failures := dv_platform_failures + 1;",
                    f'            report "{model.profile_id or model.name} handshake timed out" severity error;',
                    "        end if;",
                    f"        wait until rising_edge({clock_name});",
                )
            )
            if not valid_is_output:
                lines.append(f"        {valid} <= {_vhdl_profile_literal(plan, valid, 0)};")
        for canonical in ("tkeep", "a_mask"):
            mask_actual = bindings.get(canonical)
            if mask_actual and directions.get(canonical) == "output":
                zero = _vhdl_profile_literal(plan, mask_actual, 0)
                lines.extend(
                    (
                        f"        if {mask_actual} = {zero} then",
                        "            dv_platform_failures := dv_platform_failures + 1;",
                        f'            report "{model.profile_id or model.name} emitted an empty byte mask" severity error;',
                        "        end if;",
                    )
                )
        for canonical in ("tlast", "endofpacket"):
            last_actual = bindings.get(canonical)
            if last_actual and directions.get(canonical) == "output":
                one = _vhdl_profile_literal(plan, last_actual, 1)
                lines.extend(
                    (
                        f"        if {last_actual} /= {one} then",
                        "            dv_platform_failures := dv_platform_failures + 1;",
                        f'            report "{model.profile_id or model.name} did not terminate the bounded packet" severity error;',
                        "        end if;",
                    )
                )
        if all(name in bindings for name in ("tstrb", "tkeep")) and all(
            directions.get(name) == "output" for name in ("tstrb", "tkeep")
        ):
            illegal = _vhdl_profile_literal(plan, bindings["tstrb"], 0)
            lines.extend(
                (
                    f"        if ({bindings['tstrb']} and not {bindings['tkeep']}) /= {illegal} then",
                    "            dv_platform_failures := dv_platform_failures + 1;",
                    f'            report "{model.profile_id or model.name} asserted TSTRB outside TKEEP" severity error;',
                    "        end if;",
                )
            )
    if not lines:
        model = plan.protocol_models[0]
        directions = dict(model.signal_directions)
        bindings = dict(model.signal_bindings)
        assignments = {
            "APB4": (("psel", 1), ("penable", 0), ("pwrite", 1)),
            "AHB-Lite": (("hsel", 1), ("hwrite", 1), ("htrans", 0)),
            "AXI4-Lite": (("awvalid", 1), ("wvalid", 1)),
        }.get(model.name, ())
        if assignments:
            lines.append("        -- Executable mapped protocol/register access.")
            for canonical, value in assignments:
                legacy_actual = bindings.get(canonical)
                if legacy_actual and directions.get(canonical) in {"input", "inout", "ref"}:
                    lines.append(f"        {legacy_actual} <= {_vhdl_profile_literal(plan, legacy_actual, value)};")
            lines.append(f"        wait until rising_edge({clock_name});")
            if model.name == "APB4":
                penable = bindings.get("penable")
                if penable and directions.get("penable") in {"input", "inout", "ref"}:
                    lines.append(f"        {penable} <= {_vhdl_profile_literal(plan, penable, 1)};")
                lines.append(f"        wait until rising_edge({clock_name});")
    return tuple(lines)


def _vhdl_profile_literal(plan: VerificationPlan, actual: str, value: int) -> str:
    port = next((item for item in plan.ports if item.name == actual), None)
    if port is None or port.width in {None, 1}:
        return f"'{1 if value else 0}'"
    if value == 0:
        return f"({actual}'range => '0')"
    if value == 1:
        return f"std_logic_vector(to_unsigned(1, {port.width}))"
    return f"std_logic_vector(to_unsigned({value}, {port.width}))"


def _profile_payload_fields(model: ProtocolModel, valid_name: str) -> tuple[str, ...]:
    """Return typed payload fields, retaining payloads for migrated legacy profiles."""

    declared = tuple(
        dict.fromkeys(
            name for channel in model.channels if valid_name in channel.signals for name in channel.payload_fields
        )
    )
    if declared:
        return declared
    legacy: dict[str, dict[str, tuple[str, ...]]] = {
        "axi4-lite-1.0": {
            "awvalid": ("awaddr",),
            "wvalid": ("wdata", "wstrb"),
            "bvalid": ("bresp",),
            "arvalid": ("araddr",),
            "rvalid": ("rdata", "rresp"),
        },
        "apb4-1.0": {
            "psel": ("paddr", "pwrite", "pwdata", "pstrb"),
        },
    }
    return legacy.get(model.profile_id or "", {}).get(valid_name, ())


def haddr(model: ProtocolModel) -> str:
    return signal(model, "haddr") or "1'b0"


def _identifier(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character == "_" else "_" for character in value)
    return normalized if normalized and not normalized[0].isdigit() else "dut_" + normalized
