# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Formal generator backend."""

from __future__ import annotations

from dv_platform.core.models import (
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.scenario_registry import scenario_is_executable


def _ready_valid_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
) -> list[str]:
    lines: list[str] = []
    for index, protocol in enumerate(plan.protocols, start=1):
        if protocol.kind not in {"ready_valid", "req_ack"} or protocol.role != "source":
            continue
        antecedent = f"$past({protocol.valid} && !{protocol.ready})"
        current_guard = ""
        if reset_name is not None and reset_inactive is not None:
            antecedent = f"$past({reset_name} == {reset_inactive} && {protocol.valid} && !{protocol.ready})"
            current_guard = f" && {reset_name} == {reset_inactive}"
        lines.extend(
            [
                f"        if (!$initstate && {antecedent}{current_guard}) begin",
                f"            assert({protocol.valid});",
                *(
                    [f"            assert({protocol.data} == $past({protocol.data}));"]
                    if protocol.data is not None
                    else []
                ),
                "        end",
                f"        c_protocol_transfer_{index}: cover({protocol.valid} && {protocol.ready});",
                f"        c_protocol_backpressure_{index}: cover({protocol.valid} && !{protocol.ready});",
                f"        c_protocol_recovery_{index}: cover(!$initstate && $past({protocol.valid} && !{protocol.ready}) && {protocol.valid} && {protocol.ready});",
            ]
        )
    return lines


def _memory_collision_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    lines: list[str] = []
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    ports = {port.name for port in plan.ports}
    for policy_index, policy in enumerate(plan.depth_policies, start=1):
        collision = policy.parameter("read_during_write")
        if policy.kind != "memory" or collision not in {"read_first", "write_first", "no_change"}:
            continue
        if policy.parameter("profile") in {"bounded_sram", "bounded_sram_init_hex"}:
            continue
        reads = tuple(
            access
            for access in plan.memory_accesses
            if access.memory == policy.subject
            and access.kind == "read"
            and access.synchronous
            and len(access.address_signals) == 1
            and len(access.data_signals) == 1
        )
        writes = tuple(
            access
            for access in plan.memory_accesses
            if access.memory == policy.subject
            and access.kind == "write"
            and access.synchronous
            and len(access.address_signals) == 1
            and len(access.data_signals) == 1
        )
        for pair_index, (read, write) in enumerate(((r, w) for r in reads for w in writes), start=1):
            read_domain = domains.get(read.domain_id or "")
            write_domain = domains.get(write.domain_id or "")
            if (read_domain is not None and read_domain.clock != clock_name) or (
                write_domain is not None and write_domain.clock != clock_name
            ):
                continue
            read_address = _formal_signal_ref(read.address_signals[0], ports)
            write_address = _formal_signal_ref(write.address_signals[0], ports)
            read_data = _formal_signal_ref(read.data_signals[0], ports)
            write_data = _formal_signal_ref(write.data_signals[0], ports)
            read_enable = " && ".join(_formal_signal_ref(signal, ports) for signal in read.enable_signals) or "1'b1"
            write_enable = " && ".join(_formal_signal_ref(signal, ports) for signal in write.enable_signals) or "1'b1"
            reset_guard = (
                f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
                if reset_name and reset_inactive
                else ""
            )
            simultaneous = f"({read_enable}) && ({write_enable}) && ({read_address} == {write_address})"
            if collision == "read_first":
                expected = f"$past(dut.{policy.subject}[{read_address}])"
            elif collision == "write_first":
                expected = f"$past({write_data})"
            else:
                expected = f"$past({read_data})"
            label = f"{policy_index}_{pair_index}"
            lines.extend(
                (
                    f"        if (!$initstate{reset_guard} && $past({simultaneous})) begin",
                    f"            a_memory_collision_{label}: assert({read_data} == {expected});",
                    "        end",
                    f"        c_memory_collision_{label}: cover({simultaneous});",
                )
            )
    return lines


def _bounded_sram_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    """Emit the complete property set for qualified bounded SRAM scenarios."""

    executable = {
        dict(scenario.stimulus[0].parameters).get("memory")
        for scenario in plan.scenarios
        if scenario.kind == "memory_bounded_sram" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    memories = {memory.name: memory for memory in plan.memories}
    lines: list[str] = []
    for index, policy in enumerate(
        (item for item in plan.depth_policies if item.kind == "memory" and item.subject in executable),
        start=1,
    ):
        memory = memories.get(policy.subject)
        if memory is None or memory.depth is None or memory.element_width is None:
            continue
        if policy.parameter("clock") != clock_name:
            continue
        p = dict(policy.parameters)
        req0, req1 = p["port0_request"], p["port1_request"]
        we0, we1 = p["port0_write_enable"], p["port1_write_enable"]
        grant0, grant1 = p["port0_grant"], p["port1_grant"]
        addr0, addr1 = p["port0_address"], p["port1_address"]
        data0, data1 = p["port0_write_data"], p["port1_write_data"]
        be0, be1 = p["port0_byte_enable"], p["port1_byte_enable"]
        read_enable = p["read_enable"]
        protection = p.get("protection", "parity")
        guard = (
            f" && $past({reset_name} == {reset_inactive}) && {reset_name} == {reset_inactive}"
            if reset_name and reset_inactive
            else ""
        )
        lines.extend(
            (
                f"        a_memory_{index}_exclusive_grant: assert(!({grant0} && {grant1}));",
                f"        a_memory_{index}_grant0_request: assert(!{grant0} || ({req0} && {we0}));",
                f"        a_memory_{index}_grant1_request: assert(!{grant1} || ({req1} && {we1}));",
                f"        a_memory_{index}_work_conserving: assert(!({req0} && {we0}) || !({req1} && {we1}) || ({grant0} ^ {grant1}));",
                f"        if (!$initstate{guard} && ({req0} && {we0} && {req1} && {we1}) && $past({req0} && {we0} && {req1} && {we1} && {grant0})) begin",
                f"            a_memory_{index}_round_robin_1: assert({grant1});",
                "        end",
                f"        if (!$initstate{guard} && ({req0} && {we0} && {req1} && {we1}) && $past({req0} && {we0} && {req1} && {we1} && {grant1})) begin",
                f"            a_memory_{index}_round_robin_0: assert({grant0});",
                "        end",
                f"        c_memory_{index}_port0_grant: cover({grant0});",
                f"        c_memory_{index}_port1_grant: cover({grant1});",
                f"        c_memory_{index}_contention: cover({req0} && {we0} && {req1} && {we1});",
            )
        )
        read_address = p["read_address"]
        read_data = p["read_data"]
        byte_lanes = memory.element_width // 8
        mask0 = "{" + ", ".join(f"{{8{{{be0}[{lane}]}}}}" for lane in reversed(range(byte_lanes))) + "}"
        mask1 = "{" + ", ".join(f"{{8{{{be1}[{lane}]}}}}" for lane in reversed(range(byte_lanes))) + "}"
        model = f"dv_memory_{index}_model"
        expected = f"dv_memory_{index}_expected"
        valid = f"dv_memory_{index}_expected_valid"
        if reset_name and reset_active:
            lines.append(f"        if ({reset_name} == {reset_active}) begin")
            lines.append(f"            {model} <= '0;")
            lines.extend((f"            {expected} <= '0;", f"            {valid} <= 1'b0;", "        end else begin"))
        else:
            lines.append("        begin")
        lines.extend(
            (
                f"            if ({valid}) a_memory_{index}_scoreboard: assert({read_data} == {expected});",
                f"            {valid} <= {read_enable} && ({read_address} == '0);",
                f"            if ({read_enable}) begin",
            )
        )
        collision0 = f"{grant0} && ({read_address} == {addr0})"
        collision1 = f"{grant1} && ({read_address} == {addr1})"
        model_read = model
        if p["read_during_write"] == "write_first":
            lines.extend(
                (
                    f"                if ({collision1}) {expected} <= ({model_read} & ~({mask1})) | ({data1} & {mask1});",
                    f"                else if ({collision0}) {expected} <= ({model_read} & ~({mask0})) | ({data0} & {mask0});",
                    f"                else {expected} <= {model_read};",
                )
            )
        elif p["read_during_write"] == "no_change":
            lines.extend(
                (
                    f"                if ({collision0} || {collision1}) {expected} <= {read_data};",
                    f"                else {expected} <= {model_read};",
                )
            )
        else:
            lines.append(f"                {expected} <= {model_read};")
        lines.extend(
            (
                "            end",
                f"            if ({grant0} && ({addr0} == '0)) {model} <= ({model} & ~({mask0})) | ({data0} & {mask0});",
                f"            if ({grant1} && ({addr1} == '0)) {model} <= ({model} & ~({mask1})) | ({data1} & {mask1});",
                "        end",
                f"        c_memory_{index}_port0_collision: cover({read_enable} && {collision0});",
                f"        c_memory_{index}_port1_collision: cover({read_enable} && {collision1});",
            )
        )
        if protection == "parity":
            inject_error, error_signal = p["inject_error"], p["error_signal"]
            lines.extend(
                (
                    f"        if (!$initstate{guard} && $past({read_enable} && {inject_error})) begin",
                    f"            a_memory_{index}_parity_detect: assert({error_signal});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && !{inject_error})) begin",
                    f"            a_memory_{index}_parity_clean: assert(!{error_signal});",
                    "        end",
                    f"        c_memory_{index}_parity_error: cover({read_enable} && {inject_error});",
                )
            )
        else:
            single = p["inject_single_error"]
            double = p["inject_double_error"]
            corrected = p["corrected_error_signal"]
            uncorrectable = p["uncorrectable_error_signal"]
            scrub_enable = p["scrub_enable"]
            scrub_done = p["scrub_done"]
            lines.extend(
                (
                    f"        a_memory_{index}_injection_exclusive: assume(!({single} && {double}));",
                    f"        if (!$initstate{guard} && $past({read_enable} && {single})) begin",
                    f"            a_memory_{index}_secded_correct: assert({corrected} && !{uncorrectable});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && {double})) begin",
                    f"            a_memory_{index}_secded_double_detect: assert({uncorrectable});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && {single} && {scrub_enable})) begin",
                    f"            a_memory_{index}_secded_scrub: assert({scrub_done});",
                    "        end",
                    f"        if (!$initstate{guard} && $past({read_enable} && !{single} && !{double})) begin",
                    f"            a_memory_{index}_secded_clean: assert(!{corrected} && !{uncorrectable});",
                    "        end",
                    f"        c_memory_{index}_secded_single: cover({read_enable} && {single});",
                    f"        c_memory_{index}_secded_double: cover({read_enable} && {double});",
                    f"        c_memory_{index}_secded_scrub: cover({read_enable} && {single} && {scrub_enable});",
                )
            )
    return lines


def _qualified_formal_contract_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    subjects = {
        dict(scenario.stimulus[0].parameters).get("contract")
        for scenario in plan.scenarios
        if scenario.kind == "formal_bounded_response" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    return tuple(policy for policy in plan.depth_policies if policy.kind == "formal" and policy.subject in subjects)


def _formal_contract_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    return tuple(
        dict.fromkeys(
            signal
            for policy in _qualified_formal_contract_policies(plan)
            for name in ("response_signal", "invariant_signal")
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _formal_contract_declarations(plan: VerificationPlan) -> list[str]:
    lines: list[str] = []
    for index, _policy in enumerate(_qualified_formal_contract_policies(plan), start=1):
        lines.extend(
            (
                f"    reg dv_formal_contract_{index}_pending = 1'b0;",
                f"    reg [7:0] dv_formal_contract_{index}_age = '0;",
            )
        )
    for index, _policy in enumerate(
        (policy for policy in plan.depth_policies if policy.kind == "formal_assumption"),
        start=1,
    ):
        lines.append(f"    reg [6:0] dv_formal_assumption_{index}_age = '0;")
    return lines


def _formal_contract_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    lines: list[str] = []
    for index, policy in enumerate(_qualified_formal_contract_policies(plan), start=1):
        if policy.parameter("clock") != clock_name:
            continue
        trigger = policy.parameter("trigger_signal") or ""
        response = policy.parameter("response_signal") or ""
        invariant = policy.parameter("invariant_signal") or ""
        bound = int(policy.parameter("max_latency_cycles") or "4")
        pending = f"dv_formal_contract_{index}_pending"
        age = f"dv_formal_contract_{index}_age"
        active_test = f"{reset_name} == {reset_active}" if reset_name and reset_active else "1'b0"
        inactive_guard = f" && {reset_name} == {reset_inactive}" if reset_name and reset_inactive else ""
        lines.extend(
            (
                f"        if (!$initstate{inactive_guard}) a_formal_contract_{index}_trigger_pulse: assume(!({trigger} && $past({trigger})));",
                f"        if ({active_test}) begin",
                f"            {pending} <= 1'b0;",
                f"            {age} <= '0;",
                "        end else begin",
                f"            a_formal_contract_{index}_invariant: assert({invariant});",
                f"            a_formal_contract_{index}_induction_state: assert(!{pending} || ({age} < {bound}));",
                f"            a_formal_contract_{index}_causality: assert(!{response} || {pending} || {trigger});",
                f"            if ({pending} && ({age} >= {bound - 1}))",
                f"                a_formal_contract_{index}_bounded_liveness: assert({response});",
                f"            if ({trigger}) begin",
                f"                {pending} <= 1'b1;",
                f"                {age} <= '0;",
                f"            end else if ({pending} && {response}) begin",
                f"                {pending} <= 1'b0;",
                f"                {age} <= '0;",
                f"            end else if ({pending}) begin",
                f"                {age} <= {age} + 1'b1;",
                "            end",
                f"            c_formal_contract_{index}_assumption_witness: cover({trigger} && !$past({trigger}));",
                f"            c_formal_contract_{index}_response: cover({response});",
                f"            c_formal_contract_{index}_completed: cover({pending} && {response});",
                "        end",
            )
        )
    return lines


def _formal_assumption_assertions(
    plan: VerificationPlan,
    reset_name: str | None,
    reset_active: str | None,
    reset_inactive: str | None,
    clock_name: str,
) -> list[str]:
    executable = {
        scenario.scenario_id
        for scenario in plan.scenarios
        if scenario.kind == "formal_assumption" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    lines: list[str] = []
    policies = tuple(policy for policy in plan.depth_policies if policy.kind == "formal_assumption")
    for index, policy in enumerate(policies, start=1):
        scenario_id = next(
            (
                scenario.scenario_id
                for scenario in plan.scenarios
                if scenario.kind == "formal_assumption"
                and dict(scenario.stimulus[0].parameters).get("signal") == policy.parameter("signal")
            ),
            None,
        )
        if scenario_id not in executable or policy.parameter("clock") != clock_name:
            continue
        signal = policy.parameter("signal") or ""
        bound = int(policy.parameter("bound_cycles") or "1")
        age = f"dv_formal_assumption_{index}_age"
        inactive_guard = f"{reset_name} == {reset_inactive}" if reset_name and reset_inactive else "1'b1"
        active_test = f"{reset_name} == {reset_active}" if reset_name and reset_active else "1'b0"
        if policy.parameter("assumption") == "stability":
            predicate = f"$stable({signal})"
            witness = predicate
        else:
            minimum = policy.parameter("minimum") or "0"
            maximum = policy.parameter("maximum") or "0"
            predicate = f"({signal} >= {minimum}) && ({signal} <= {maximum})"
            witness = f"({signal} == {minimum}) || ({signal} == {maximum})"
        lines.extend(
            (
                f"        if (!$initstate && {inactive_guard}) begin",
                f"            a_formal_assumption_{index}_typed: assume({predicate});",
                "        end",
                f"        if ({active_test}) begin",
                f"            {age} <= '0;",
                f"        end else if ({age} < {bound}) begin",
                f"            {age} <= {age} + 1'b1;",
                "        end",
                f"        c_formal_assumption_{index}_witness: cover(!$initstate && !{active_test} && {witness});",
                f"        c_formal_assumption_{index}_response: cover(!$initstate && !{active_test} && {predicate});",
                f"        c_formal_assumption_{index}_completion: cover(!$initstate && !{active_test} && "
                f"{age} >= {bound - 1} && {predicate});",
            )
        )
    return lines


def _async_fifo_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    return tuple(
        policy
        for policy in plan.depth_policies
        if policy.kind == "cdc" and policy.parameter("structure") == "async_fifo"
    )


def _qualified_reset_policies(plan: VerificationPlan) -> tuple[VerificationDepthPolicy, ...]:
    executable_subjects = {
        dict(scenario.stimulus[0].parameters).get("reset")
        for scenario in plan.scenarios
        if scenario.kind == "reset_domain_sequence" and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    }
    return tuple(
        policy for policy in plan.depth_policies if policy.kind == "reset" and policy.subject in executable_subjects
    )


def _reset_domain_output_signals(plan: VerificationPlan) -> tuple[str, ...]:
    outputs = {port.name for port in plan.ports if port.direction == "output"}
    return tuple(
        dict.fromkeys(
            signal
            for policy in _qualified_reset_policies(plan)
            for name in (
                "ready_signal",
                "depends_on_ready",
                "dependency_sync_signal",
                "isolation_signal",
                "retention_signal",
            )
            if (signal := policy.parameter(name)) in outputs
        )
    )


def _reset_domain_assertions(plan: VerificationPlan) -> list[str]:
    lines: list[str] = []
    ports = set(_port_names_from_plan(plan))
    for index, policy in enumerate(_qualified_reset_policies(plan), start=1):
        reset = policy.subject
        clock = policy.parameter("clock")
        ready = policy.parameter("ready_signal")
        if reset not in ports or clock not in ports or ready not in ports:
            continue
        active_low = reset.endswith("_n")
        reset_active = f"!{reset}" if active_low else reset
        release_cycles = max(
            int(policy.parameter("release_cycles") or "2"),
            int(policy.parameter("recovery_cycles") or "1"),
            int(policy.parameter("removal_cycles") or "1"),
        )
        dependency_sync = policy.parameter("dependency_sync_signal")
        dependency_guard = dependency_sync if dependency_sync in ports else "1'b1"
        power_good = policy.parameter("power_good_signal")
        isolation = policy.parameter("isolation_signal")
        retention = policy.parameter("retention_signal")
        power_guard = power_good if power_good in ports else "1'b1"
        sequence_guard = f"({dependency_guard}) && ({power_guard})"
        ordered_hold_guard = (
            f"!({dependency_guard}) || (!$initstate && $past(!{power_good}))"
            if power_good in ports
            else f"!({dependency_guard})"
        )
        lines.extend(
            (
                "",
                f"    reg [7:0] reset_domain_{index}_release_count = '0;",
                "    always @(*) begin",
                f"        if ({reset_active}) a_reset_domain_{index}_async_assert: assert(!{ready});",
                *(
                    (
                        f"        if ({ready} && {power_good}) a_reset_domain_{index}_power_release: assert(!{isolation} && !{retention});",
                    )
                    if power_good in ports and isolation in ports and retention in ports
                    else ()
                ),
                "    end",
                f"    always @(posedge {clock}) begin",
                *(
                    (
                        f"        if (!$initstate && $past(!{power_good})) a_reset_domain_{index}_power_hold: assert(!{ready} && {isolation} && {retention});",
                    )
                    if power_good in ports and isolation in ports and retention in ports
                    else ()
                ),
                f"        if (!$initstate && $past(!({reset_active}))) a_reset_domain_{index}_monotonic_release: assume(!({reset_active}));",
                f"        if ({reset_active}) begin",
                f"            reset_domain_{index}_release_count <= '0;",
                "        end else if (!$initstate) begin",
                f"            if (!({sequence_guard})) begin",
                f"                reset_domain_{index}_release_count <= '0;",
                f"                if ({ordered_hold_guard}) a_reset_domain_{index}_ordered_hold: assert(!{ready});",
                "            end else begin",
                f"                if (reset_domain_{index}_release_count < {release_cycles + 1})",
                f"                    reset_domain_{index}_release_count <= reset_domain_{index}_release_count + 1'b1;",
                f"                if (reset_domain_{index}_release_count < {release_cycles})",
                f"                    a_reset_domain_{index}_release_hold: assert(!{ready});",
                f"                else if (reset_domain_{index}_release_count >= {release_cycles + 1})",
                f"                    a_reset_domain_{index}_bounded_release: assert({ready});",
                "            end",
                f"            c_reset_domain_{index}_dependency_seen: cover({sequence_guard});",
                f"            c_reset_domain_{index}_released: cover({ready});",
                "        end",
                "    end",
            )
        )
    return lines
