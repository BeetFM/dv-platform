# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Formal generator backend."""

from __future__ import annotations

from dv_platform.core.models import (
    RTLCDCPath,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.scenario_registry import scenario_is_executable


def _qualified_bounded_sram_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    subjects = {
        dict(scenario.stimulus[0].parameters).get("memory")
        for scenario in plan.scenarios
        if scenario.kind == "memory_bounded_sram" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    return tuple(policy for policy in plan.depth_policies if policy.kind == "memory" and policy.subject in subjects)


def _bounded_sram_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    names = (
        "read_data",
        "port0_grant",
        "port1_grant",
        "error_signal",
        "corrected_error_signal",
        "uncorrectable_error_signal",
        "scrub_done",
    )
    return tuple(
        dict.fromkeys(
            signal
            for policy in _qualified_bounded_sram_policies(plan)
            for name in names
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _bounded_sram_declarations(plan: VerificationPlan) -> list[str]:
    memories = {memory.name: memory for memory in plan.memories}
    lines: list[str] = []
    for index, policy in enumerate(_qualified_bounded_sram_policies(plan), start=1):
        memory = memories.get(policy.subject)
        if memory is None or memory.depth is None or memory.element_width is None:
            continue
        lines.extend(
            (
                f"    reg [{memory.element_width - 1}:0] dv_memory_{index}_model = '0;",
                f"    reg [{memory.element_width - 1}:0] dv_memory_{index}_expected = '0;",
                f"    reg dv_memory_{index}_expected_valid = 1'b0;",
            )
        )
    return lines


def _async_fifo_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    names = (
        "write_binary_pointer",
        "write_gray_pointer",
        "write_gray_sync",
        "full_signal",
        "read_data",
        "read_binary_pointer",
        "read_gray_pointer",
        "read_gray_sync",
        "empty_signal",
    )
    return tuple(
        dict.fromkeys(
            signal
            for policy in _async_fifo_policies(plan)
            for name in names
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _async_fifo_assertions(plan: VerificationPlan) -> list[str]:
    lines: list[str] = []
    memories = {memory.name: memory for memory in plan.memories}
    ports = set(_port_names_from_plan(plan))
    for index, policy in enumerate(_async_fifo_policies(plan), start=1):
        memory = memories.get(policy.subject)
        if memory is None or memory.address_width is None or memory.element_width is None:
            continue
        required = {
            name: policy.parameter(name)
            for name in (
                "write_clock",
                "write_reset",
                "write_enable",
                "write_binary_pointer",
                "write_gray_pointer",
                "write_gray_sync",
                "full_signal",
                "read_clock",
                "read_reset",
                "read_enable",
                "read_data",
                "read_binary_pointer",
                "read_gray_pointer",
                "read_gray_sync",
                "empty_signal",
            )
        }
        if any(signal not in ports for signal in required.values()):
            continue
        signal = {name: _formal_signal_ref(value or "", ports) for name, value in required.items()}
        pointer_width = memory.address_width + 1
        w_reset_active = (
            f"!{signal['write_reset']}"
            if (policy.parameter("write_reset") or "").endswith("_n")
            else signal["write_reset"]
        )
        r_reset_active = (
            f"!{signal['read_reset']}"
            if (policy.parameter("read_reset") or "").endswith("_n")
            else signal["read_reset"]
        )
        w_reset_edge = (
            f"negedge {signal['write_reset']}"
            if (policy.parameter("write_reset") or "").endswith("_n")
            else f"posedge {signal['write_reset']}"
        )
        r_reset_edge = (
            f"negedge {signal['read_reset']}"
            if (policy.parameter("read_reset") or "").endswith("_n")
            else f"posedge {signal['read_reset']}"
        )
        inverted_read = (
            f"{{~{signal['read_gray_sync']}[{pointer_width - 1}:{pointer_width - 2}], "
            f"{signal['read_gray_sync']}[{pointer_width - 3}:0]}}"
            if pointer_width > 2
            else f"~{signal['read_gray_sync']}"
        )
        lines.extend(
            (
                "",
                f"    reg async_fifo_{index}_write_valid = 1'b0;",
                f"    reg async_fifo_{index}_write_accept = 1'b0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_write_pointer = '0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_write_gray = '0;",
                f"    reg async_fifo_{index}_read_valid = 1'b0;",
                f"    reg async_fifo_{index}_read_accept = 1'b0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_read_pointer = '0;",
                f"    reg [{pointer_width - 1}:0] async_fifo_{index}_read_gray = '0;",
                *(
                    (
                        f"    reg async_fifo_{index}_read_empty = 1'b1;",
                        f"    reg async_fifo_{index}_read_enable = 1'b0;",
                        f"    reg [{memory.element_width - 1}:0] async_fifo_{index}_read_data = '0;",
                        f"    reg [{pointer_width - 1}:0] async_fifo_{index}_read_write_pointer = '0;",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                "",
                f"    always @(posedge {signal['write_clock']} or {w_reset_edge}) begin",
                f"        if ({w_reset_active}) begin",
                f"            a_async_fifo_{index}_write_reset: assert({signal['write_binary_pointer']} == '0 && {signal['write_gray_pointer']} == '0 && !{signal['full_signal']});",
                f"            async_fifo_{index}_write_valid <= 1'b0;",
                "        end else if (!$initstate) begin",
                f"            a_async_fifo_{index}_write_gray_encoding: assert({signal['write_gray_pointer']} == (({signal['write_binary_pointer']} >> 1) ^ {signal['write_binary_pointer']}));",
                f"            a_async_fifo_{index}_full_equation: assert({signal['full_signal']} == ({signal['write_gray_pointer']} == {inverted_read}));",
                f"            if (async_fifo_{index}_write_valid && async_fifo_{index}_write_accept) begin",
                f"                a_async_fifo_{index}_write_increment: assert({signal['write_binary_pointer']} == async_fifo_{index}_write_pointer + 1'b1);",
                f"                a_async_fifo_{index}_write_gray_one_bit: assert((({signal['write_gray_pointer']} ^ async_fifo_{index}_write_gray) & (({signal['write_gray_pointer']} ^ async_fifo_{index}_write_gray) - 1'b1)) == '0);",
                f"            end else if (async_fifo_{index}_write_valid) begin",
                f"                a_async_fifo_{index}_write_hold: assert({signal['write_binary_pointer']} == async_fifo_{index}_write_pointer);",
                "            end",
                f"            c_async_fifo_{index}_write: cover({signal['write_enable']} && !{signal['full_signal']});",
                f"            c_async_fifo_{index}_full: cover({signal['full_signal']});",
                f"            async_fifo_{index}_write_valid <= 1'b1;",
                f"            async_fifo_{index}_write_accept <= {signal['write_enable']} && !{signal['full_signal']};",
                f"            async_fifo_{index}_write_pointer <= {signal['write_binary_pointer']};",
                f"            async_fifo_{index}_write_gray <= {signal['write_gray_pointer']};",
                "        end",
                "    end",
                "",
                f"    always @(posedge {signal['read_clock']} or {r_reset_edge}) begin",
                f"        if ({r_reset_active}) begin",
                f"            a_async_fifo_{index}_read_reset: assert({signal['read_binary_pointer']} == '0 && {signal['read_gray_pointer']} == '0 && {signal['empty_signal']});",
                f"            async_fifo_{index}_read_valid <= 1'b0;",
                *(
                    (
                        f"            async_fifo_{index}_read_empty <= 1'b1;",
                        f"            async_fifo_{index}_read_enable <= 1'b0;",
                        f"            async_fifo_{index}_read_data <= '0;",
                        f"            async_fifo_{index}_read_write_pointer <= '0;",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                "        end else if (!$initstate) begin",
                f"            a_async_fifo_{index}_read_gray_encoding: assert({signal['read_gray_pointer']} == (({signal['read_binary_pointer']} >> 1) ^ {signal['read_binary_pointer']}));",
                f"            a_async_fifo_{index}_empty_equation: assert({signal['empty_signal']} == ({signal['read_gray_pointer']} == {signal['write_gray_sync']}));",
                *(
                    (
                        f"            if (async_fifo_{index}_read_valid && !async_fifo_{index}_read_empty && !async_fifo_{index}_read_enable && {signal['write_binary_pointer']} == async_fifo_{index}_read_write_pointer) a_async_fifo_{index}_fwft_stable: assert({signal['read_data']} == async_fifo_{index}_read_data);",
                        f"            c_async_fifo_{index}_fwft_visible: cover(!{signal['empty_signal']} && !{signal['read_enable']});",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                f"            if (async_fifo_{index}_read_valid && async_fifo_{index}_read_accept) begin",
                f"                a_async_fifo_{index}_read_increment: assert({signal['read_binary_pointer']} == async_fifo_{index}_read_pointer + 1'b1);",
                f"                a_async_fifo_{index}_read_gray_one_bit: assert((({signal['read_gray_pointer']} ^ async_fifo_{index}_read_gray) & (({signal['read_gray_pointer']} ^ async_fifo_{index}_read_gray) - 1'b1)) == '0);",
                f"            end else if (async_fifo_{index}_read_valid) begin",
                f"                a_async_fifo_{index}_read_hold: assert({signal['read_binary_pointer']} == async_fifo_{index}_read_pointer);",
                "            end",
                f"            c_async_fifo_{index}_read: cover({signal['read_enable']} && !{signal['empty_signal']});",
                f"            c_async_fifo_{index}_empty: cover({signal['empty_signal']});",
                f"            async_fifo_{index}_read_valid <= 1'b1;",
                f"            async_fifo_{index}_read_accept <= {signal['read_enable']} && !{signal['empty_signal']};",
                f"            async_fifo_{index}_read_pointer <= {signal['read_binary_pointer']};",
                f"            async_fifo_{index}_read_gray <= {signal['read_gray_pointer']};",
                *(
                    (
                        f"            async_fifo_{index}_read_empty <= {signal['empty_signal']};",
                        f"            async_fifo_{index}_read_enable <= {signal['read_enable']};",
                        f"            async_fifo_{index}_read_data <= {signal['read_data']};",
                        f"            async_fifo_{index}_read_write_pointer <= {signal['write_binary_pointer']};",
                    )
                    if policy.parameter("first_word_fall_through") == "true"
                    else ()
                ),
                "        end",
                "    end",
            )
        )
    return lines


def _cdc_assertions(
    plan: VerificationPlan,
    evidence: tuple[_CDCPathEvidence, ...] | None = None,
) -> list[str]:
    lines: list[str] = []
    ports = set(_port_names_from_plan(plan))
    port_widths = {port.name: port.width or 1 for port in plan.ports}
    evidence_by_id = {item.path_id: item for item in (evidence or _cdc_evidence(plan, CDCProofPolicy.FAIL_CLOSED, 20))}
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    for path in plan.cdc_paths:
        path_evidence = evidence_by_id.get(path.path_id)
        if path_evidence is None or path_evidence.evidence_level == "unsupported":
            continue
        domain = domains.get(path.destination_domain)
        if domain is None or not domain.clock:
            continue
        clock = _formal_signal_ref(domain.clock, ports)
        label = _safe_identifier(path.path_id)
        source = _formal_signal_ref(path.signal, ports)
        edge = "negedge" if domain.clock_edge == "neg" else "posedge"
        reset = _formal_signal_ref(domain.reset, ports) if domain.reset else None
        reset_active = f"!{reset}" if reset and domain.reset_active_low else reset
        reset_inactive = reset if reset and domain.reset_active_low else f"!{reset}" if reset else None
        reset_edge = "negedge" if domain.reset_active_low else "posedge"
        event = f"{edge} {clock}" + (f" or {reset_edge} {reset}" if reset else "")
        initialization = "" if reset else " = '0"
        if path_evidence.evidence_level == "structural":
            lines.extend(
                _structural_cdc_assertions(
                    plan,
                    path,
                    ports,
                    port_widths,
                    clock,
                    edge,
                    label,
                    source,
                    reset_active,
                    reset_inactive,
                    event,
                    initialization,
                )
            )
            continue

        maximum_latency = path.synchronizer_stages
        history_name = f"cdc_{label}_history"
        valid_name = f"cdc_{label}_valid"
        lines.append("`ifdef DV_CDC_BOUNDED")
        lines.append(f"    reg [{maximum_latency - 1}:0] {history_name}{initialization};")
        lines.append(f"    reg [{maximum_latency - 1}:0] {valid_name}{initialization};")
        lines.append(f"    always @({event}) begin")
        if reset_active:
            lines.append(f"        if ({reset_active}) begin")
            lines.append(f"            {history_name} <= '0;")
            lines.append(f"            {valid_name} <= '0;")
            lines.append("        end else begin")
        else:
            lines.append("        begin")
        lines.append(f"            {history_name}[0] <= {source};")
        lines.append(f"            {valid_name}[0] <= 1'b1;")
        for index in range(1, maximum_latency):
            lines.append(f"            {history_name}[{index}] <= {history_name}[{index - 1}];")
            lines.append(f"            {valid_name}[{index}] <= {valid_name}[{index - 1}];")
        final_index = maximum_latency - 1
        final_stage = _formal_signal_ref(path.stage_signals[-1], ports)
        lines.append("        end")
        lines.append("    end")
        lines.append("    always @(*) begin")
        bounded_guard = f"{valid_name}[{final_index}]"
        if reset_inactive:
            bounded_guard += f" && {reset_inactive}"
        lines.append(
            f"        if ({bounded_guard}) "
            f"a_cdc_{label}_bounded: assert({final_stage} == {history_name}[{final_index}]);"
        )
        lines.append(
            f"        c_cdc_{label}_observed: cover({valid_name}[{final_index}] "
            f"&& {final_stage} == {history_name}[{final_index}]);"
        )
        lines.append("    end")
        lines.append("`endif")
        lines.extend(_cdc_scheme_assertions(plan, path, clock, edge, reset_inactive, ports))
    return lines


def _structural_cdc_assertions(
    plan: VerificationPlan,
    path: RTLCDCPath,
    ports: set[str],
    port_widths: dict[str, int],
    clock: str,
    edge: str,
    label: str,
    source: str,
    reset_active: str | None,
    reset_inactive: str | None,
    event: str,
    initialization: str,
) -> list[str]:
    stage_count = path.synchronizer_stages
    expected_name = f"cdc_{label}_expected"
    valid_name = f"cdc_{label}_valid"
    signal_width = port_widths.get(path.signal, 1)
    if signal_width == 1:
        lines = [f"    reg [{stage_count - 1}:0] {expected_name}{initialization};"]
    else:
        lines = [
            f"    reg [{signal_width - 1}:0] {expected_name}_{index}{initialization};" for index in range(stage_count)
        ]
    lines.extend((f"    reg [{stage_count - 1}:0] {valid_name}{initialization};", f"    always @({event}) begin"))
    if reset_active:
        lines.append(f"        if ({reset_active}) begin")
        if signal_width == 1:
            lines.append(f"            {expected_name} <= '0;")
        else:
            lines.extend(f"            {expected_name}_{index} <= '0;" for index in range(stage_count))
        lines.extend((f"            {valid_name} <= '0;", "        end else begin"))
    else:
        lines.append("        begin")
    for index in range(stage_count):
        previous = source if index == 0 else _formal_signal_ref(path.stage_signals[index - 1], ports)
        expected = f"{expected_name}[{index}]" if signal_width == 1 else f"{expected_name}_{index}"
        validity = "1'b1" if index == 0 else f"{valid_name}[{index - 1}]"
        lines.extend((f"            {expected} <= {previous};", f"            {valid_name}[{index}] <= {validity};"))
    lines.extend(("        end", "    end", "    always @(*) begin"))
    for index, stage in enumerate(path.stage_signals):
        current = _formal_signal_ref(stage, ports)
        guard = f"{valid_name}[{index}]" + (f" && {reset_inactive}" if reset_inactive else "")
        expected = f"{expected_name}[{index}]" if signal_width == 1 else f"{expected_name}_{index}"
        lines.append(f"        if ({guard}) a_cdc_{label}_stage_{index}: assert({current} == {expected});")
    final_stage = _formal_signal_ref(path.stage_signals[-1], ports)
    final_expected = (
        f"{expected_name}[{stage_count - 1}]" if signal_width == 1 else f"{expected_name}_{stage_count - 1}"
    )
    lines.extend(
        (
            f"        c_cdc_{label}_observed: cover({valid_name}[{stage_count - 1}] "
            f"&& {final_stage} == {final_expected});",
            "    end",
        )
    )
    lines.extend(_cdc_scheme_assertions(plan, path, clock, edge, reset_inactive, ports))
    return lines
