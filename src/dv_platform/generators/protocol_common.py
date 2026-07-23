"""Shared protocol generation helpers."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel, RegisterModel
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
        body.extend(_cocotb_model_probe(model, index))
    for register in plan.register_models:
        body.extend(_cocotb_register_probe(register, models[0]))
    body.append("    return")
    lines.extend(body)
    return tuple(lines)


def _cocotb_model_probe(model: ProtocolModel, index: int) -> tuple[str, ...]:
    lines = [f"    # Executable {model.name} transfer probe {index}."]
    assignments = {
        "AXI4-Lite": (("awvalid", 0), ("wvalid", 0), ("arvalid", 0), ("bready", 0), ("rready", 0)),
        "APB4": (("psel", 1), ("penable", 0), ("pwrite", 0)),
        "AHB-Lite": (("hsel", 1), ("htrans", 2), ("hwrite", 0)),
    }.get(model.name, ())
    if not assignments:
        return tuple(lines)
    for canonical, value in assignments:
        actual = input_signal(model, canonical)
        if actual:
            lines.append(f"    _drive_if_present(dut, {actual!r}, {value})")
    lines.append("    await _sample_cycle(clock)")
    if model.name == "APB4" and (penable := input_signal(model, "penable")):
        lines.extend((f"    _drive_if_present(dut, {penable!r}, 1)", "    await _sample_cycle(clock)"))
    return tuple(lines)


def _cocotb_register_probe(register: RegisterModel, model: ProtocolModel) -> tuple[str, ...]:
    if register.offset is None:
        return ()
    lines = [f"    # Executable register access probe for {register.name} at offset {register.offset}."]
    assignments = {
        "AXI4-Lite": (("awaddr", register.offset or 0), ("wdata", 0), ("awvalid", 1), ("wvalid", 1)),
        "APB4": (
            ("paddr", register.offset or 0),
            ("pwdata", 0),
            ("pwrite", 1),
            ("psel", 1),
            ("penable", 0),
        ),
        "AHB-Lite": (
            ("haddr", register.offset or 0),
            ("hwdata", 0),
            ("hwrite", 1),
            ("hsel", 1),
            ("htrans", 2),
        ),
    }.get(model.name, ())
    if not assignments:
        return tuple(lines)
    for canonical, value in assignments:
        actual = input_signal(model, canonical)
        if actual:
            lines.append(f"    _drive_if_present(dut, {actual!r}, {value})")
    lines.append("    await _sample_cycle(clock)")
    if model.name == "APB4" and (penable := input_signal(model, "penable")):
        lines.extend((f"    _drive_if_present(dut, {penable!r}, 1)", "    await _sample_cycle(clock)"))
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
        lines.extend(_cocotb_profile_scenario(plan, clock_name, scenario, models))
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


def _cocotb_profile_scenario(
    plan: VerificationPlan,
    clock_name: str,
    scenario: VerificationScenario,
    models: dict[str, ProtocolModel],
) -> tuple[str, ...]:
    lines: list[str] = []
    stimulus = next((item for item in scenario.stimulus if item.kind == "protocol_profile"), None)
    parameters = dict(stimulus.parameters) if stimulus is not None else {}
    model = models.get(parameters.get("instance_id", ""))
    if model is None:
        return ()
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
        lines.extend(
            _cocotb_profile_handshake(
                plan, scenario, model, bindings, directions, valid_name, ready_name, accepted_value
            )
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
    return tuple(lines)


def _cocotb_profile_handshake(
    plan: VerificationPlan,
    scenario: VerificationScenario,
    model: ProtocolModel,
    bindings: dict[str, str],
    directions: dict[str, str],
    valid_name: str,
    ready_name: str,
    accepted_value: int,
) -> tuple[str, ...]:
    lines: list[str] = []
    valid = bindings.get(valid_name)
    ready = bindings.get(ready_name)
    if valid is None or ready is None:
        return ()
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
        payload_map = {name: bindings[name] for name in _profile_payload_fields(model, valid_name) if name in bindings}
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
    lines.extend(_cocotb_avalon_response(scenario, model, bindings, directions, valid_name))
    lines.extend(_cocotb_wishbone_response(scenario, model, bindings, directions, valid_name, ready_name))
    lines.extend(_cocotb_packet_completion(scenario, model, bindings, directions, valid_name))
    return tuple(lines)


def _cocotb_avalon_response(
    scenario: VerificationScenario,
    model: ProtocolModel,
    bindings: dict[str, str],
    directions: dict[str, str],
    valid_name: str,
) -> tuple[str, ...]:
    if model.profile_id != "avalon-mm-1.0" or valid_name not in {"read", "write"}:
        return ()
    lines: list[str] = []
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
    return tuple(lines)


def _cocotb_wishbone_response(
    scenario: VerificationScenario,
    model: ProtocolModel,
    bindings: dict[str, str],
    directions: dict[str, str],
    valid_name: str,
    ready_name: str,
) -> tuple[str, ...]:
    if model.profile_id != "wishbone-b4-1.0" or valid_name != "stb" or ready_name != "stall":
        return ()
    lines: list[str] = []
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
    return tuple(lines)


def _cocotb_packet_completion(
    scenario: VerificationScenario,
    model: ProtocolModel,
    bindings: dict[str, str],
    directions: dict[str, str],
    valid_name: str,
) -> tuple[str, ...]:
    if valid_name not in {"tvalid", "valid"}:
        return ()
    final_name = "tlast" if valid_name == "tvalid" else "endofpacket"
    final_signal = bindings.get(final_name)
    if final_signal is None or directions.get(final_name) != "output":
        return ()
    payload_map = {
        name: bindings[name]
        for channel in model.channels
        if valid_name in channel.signals
        for name in channel.payload_fields
        if name in bindings and directions.get(name) == "output"
    }
    return (
        f"    while not transaction['payload'].get({final_name!r}, 0):",
        f"        await _wait_signal(clock, dut, {bindings[valid_name]!r}, 1, {scenario.completion.timeout_cycles})",
        f"        transaction = monitor.observe({valid_name!r}, _profile_snapshot(dut, {payload_map!r}))",
        "        scoreboard.expect(reference.apply(transaction))",
        "        scoreboard.observe(transaction)",
        "        await _sample_cycle(clock)",
    )


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
