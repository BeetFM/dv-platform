# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Formal generator backend."""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import parse

from dv_platform.core.models import (
    RTLCDCPath,
    VerificationPlan,
)
from dv_platform.generation.rendering import render_target


def _cdc_scheme_assertions(
    plan: VerificationPlan,
    path: RTLCDCPath,
    clock: str,
    edge: str,
    reset_inactive: str | None,
    ports: set[str],
) -> list[str]:
    policy = _cdc_structure_policy(plan, path)
    if policy is None:
        return []
    structure = policy.parameter("structure") or path.classification
    label = _safe_identifier(path.path_id)
    source = _formal_signal_ref(path.signal, ports)
    output = _formal_signal_ref(path.stage_signals[-1], ports)
    if structure == "gray":
        return _gray_scheme_assertions(plan, path, clock, edge, reset_inactive, label, source, output)
    if structure == "multi_bit_handshake":
        ack_input = _formal_signal_ref(policy.parameter("ack_input_signal") or "", ports)
        ack_output = _formal_signal_ref(policy.parameter("ack_output_signal") or "", ports)
        data_signals = tuple(filter(None, (policy.parameter("data_signals") or "").split(",")))
        observed_signals = tuple(filter(None, (policy.parameter("observed_data_signals") or "").split(",")))
        valid = f"cdc_{label}_payload_valid"
        reset_active = f"!({reset_inactive})" if reset_inactive else None
        lines = [f"    reg {valid} = 1'b0;"]
        expected_names: list[str] = []
        for index, signal in enumerate(data_signals):
            width = next((port.width for port in plan.ports if port.name == signal), None)
            if width is None:
                return []
            expected = f"cdc_{label}_payload_expected_{index}"
            expected_names.append(expected)
            lines.append(f"    reg [{width - 1}:0] {expected} = '0;")
        lines.append(f"    always @({edge} {clock}) begin")
        if reset_active:
            lines.extend(
                (f"        if ({reset_active}) begin", f"            {valid} <= 1'b0;", "        end else begin")
            )
        else:
            lines.append("        begin")
        lines.extend(
            (
                f"            if (!$initstate && $past({source}) && !$past({ack_output})) "
                f"a_cdc_{label}_request_held: assume({source});",
            )
        )
        for index, signal in enumerate(data_signals):
            reference = _formal_signal_ref(signal, ports)
            lines.append(
                f"            if (!$initstate && $past({source}) && !$past({ack_output})) "
                f"a_cdc_{label}_data_stable_{index}: assume({reference} == $past({reference}));"
            )
            observed = _formal_signal_ref(observed_signals[index], ports)
            lines.append(
                f"            if ({valid}) a_cdc_{label}_payload_coherent_{index}: "
                f"assert({observed} == {expected_names[index]});"
            )
            lines.append(f"            if ({output}) {expected_names[index]} <= {reference};")
        lines.extend(
            (
                f"            {valid} <= {output};",
                f"            c_cdc_{label}_request_seen: cover({output});",
                f"            c_cdc_{label}_round_trip: cover({output} && {ack_input} && {ack_output});",
                "        end",
                "    end",
            )
        )
        return lines
    guard = f" && {reset_inactive}" if reset_inactive else ""
    lines = [f"    always @({edge} {clock}) begin", f"        if (!$initstate{guard}) begin"]
    if structure == "toggle":
        lines.extend(
            (
                f"            c_cdc_{label}_toggle_rise: cover(!$past({output}) && {output});",
                f"            c_cdc_{label}_toggle_fall: cover($past({output}) && !{output});",
            )
        )
    elif structure == "pulse":
        lines.extend(
            (
                f"            c_cdc_{label}_pulse_observed: cover({output} && !$past({output}));",
                f"            c_cdc_{label}_pulse_returned: cover(!{output} && $past({output}));",
            )
        )
    else:
        ack_input = _formal_signal_ref(policy.parameter("ack_input_signal") or "", ports)
        ack_output = _formal_signal_ref(policy.parameter("ack_output_signal") or "", ports)
        data_signals = tuple(filter(None, (policy.parameter("data_signals") or "").split(",")))
        lines.append(
            f"            if ($past({source}) && !$past({ack_output})) a_cdc_{label}_request_held: assume({source});"
        )
        for index, signal in enumerate(data_signals):
            reference = _formal_signal_ref(signal, ports)
            lines.append(
                f"            if ($past({source}) && !$past({ack_output})) "
                f"a_cdc_{label}_data_stable_{index}: assume({reference} == $past({reference}));"
            )
        lines.extend(
            (
                f"            c_cdc_{label}_request_seen: cover({output});",
                f"            c_cdc_{label}_round_trip: cover({output} && {ack_input} && {ack_output});",
            )
        )
    lines.extend(("        end", "    end"))
    return lines


def _reconvergent_cdc_assertions(plan: VerificationPlan, ports: set[str]) -> list[str]:
    scenarios = tuple(
        scenario
        for scenario in plan.scenarios
        if scenario.kind == "cdc_two_branch_reconvergent"
        and scenario_is_executable(scenario, VerificationTarget.FORMAL)
    )
    lines: list[str] = []
    for index, scenario in enumerate(scenarios, 1):
        profile = dict(scenario.stimulus[0].parameters)
        clock = _formal_signal_ref(profile["clock"], ports)
        branch0 = _formal_signal_ref(profile["branch0_signal"], ports)
        branch1 = _formal_signal_ref(profile["branch1_signal"], ports)
        observed = _formal_signal_ref(profile["reconvergence_signal"], ports)
        bound = int(profile["coherent_arrival_bound"])
        rate = int(profile["source_rate_bound"])
        stability = int(profile["source_stability_cycles"])
        hold = max(rate, stability)
        reset = _formal_signal_ref(profile.get("reset", ""), ports) if profile.get("reset") else None
        reset_active = f"!{reset}" if reset and profile.get("reset_active_low") == "true" else reset
        lines.extend(
            (
                f"    reg [{bound - 1}:0] cdc_reconvergent_{index}_history = '0;",
                f"    reg [{bound - 1}:0] cdc_reconvergent_{index}_valid = '0;",
                f"    reg [{max(1, hold.bit_length()) - 1}:0] cdc_reconvergent_{index}_cooldown = '0;",
                f"    always @(posedge {clock}) begin",
            )
        )
        if reset_active:
            lines.extend(
                (
                    f"        if ({reset_active}) begin",
                    f"            cdc_reconvergent_{index}_history <= '0;",
                    f"            cdc_reconvergent_{index}_valid <= '0;",
                    f"            cdc_reconvergent_{index}_cooldown <= '0;",
                    "        end else begin",
                )
            )
        else:
            lines.append("        begin")
        lines.extend(
            (
                f"            a_cdc_reconvergent_{index}_coherent_source: assume({branch0} == {branch1});",
                f"            if (!$initstate && cdc_reconvergent_{index}_cooldown != 0) begin",
                f"                a_cdc_reconvergent_{index}_source_stable: assume({branch0} == $past({branch0}));",
                f"                cdc_reconvergent_{index}_cooldown <= cdc_reconvergent_{index}_cooldown - 1'b1;",
                f"            end else if (!$initstate && {branch0} != $past({branch0})) begin",
                f"                cdc_reconvergent_{index}_cooldown <= {hold};",
                "            end",
                f"            cdc_reconvergent_{index}_history[0] <= {branch0};",
                f"            cdc_reconvergent_{index}_valid[0] <= 1'b1;",
            )
        )
        for stage in range(1, bound):
            lines.extend(
                (
                    f"            cdc_reconvergent_{index}_history[{stage}] <= "
                    f"cdc_reconvergent_{index}_history[{stage - 1}];",
                    f"            cdc_reconvergent_{index}_valid[{stage}] <= "
                    f"cdc_reconvergent_{index}_valid[{stage - 1}];",
                )
            )
        lines.extend(
            (
                f"            if (cdc_reconvergent_{index}_valid[{bound - 1}]) "
                f"a_cdc_reconvergent_{index}_coherent_arrival: "
                f"assert({observed} == cdc_reconvergent_{index}_history[{bound - 1}]);",
                f"            c_cdc_reconvergent_{index}_source_change: "
                f"cover(!$initstate && {branch0} != $past({branch0}));",
                f"            c_cdc_reconvergent_{index}_completion: "
                f"cover(cdc_reconvergent_{index}_valid[{bound - 1}] && "
                f"{observed} == cdc_reconvergent_{index}_history[{bound - 1}]);",
                "        end",
                "    end",
            )
        )
    return lines


def _gray_scheme_assertions(
    plan: VerificationPlan,
    path: RTLCDCPath,
    clock: str,
    edge: str,
    reset_inactive: str | None,
    label: str,
    source: str,
    output: str,
) -> list[str]:
    width = next((port.width for port in plan.ports if port.name == path.signal), None)
    if width is None or width < 2:
        return []
    source_sample = f"cdc_{label}_gray_source_sample"
    output_sample = f"cdc_{label}_gray_output_sample"
    reset_active = f"!({reset_inactive})" if reset_inactive else None
    lines = [
        f"    reg [{width - 1}:0] {source_sample} = '0;",
        f"    reg [{width - 1}:0] {output_sample} = '0;",
        f"    always @({edge} {clock}) begin",
    ]
    if reset_active:
        lines.extend(
            (
                f"        if ({reset_active}) begin",
                f"            a_cdc_{label}_gray_reset_source: assume({source} == '0);",
                f"            {source_sample} <= '0;",
                f"            {output_sample} <= '0;",
                "        end else begin",
            )
        )
    else:
        lines.append("        begin")
    lines.extend(
        (
            f"            a_cdc_{label}_gray_source_one_bit: assume((({source} ^ {source_sample}) & (({source} ^ {source_sample}) - 1'b1)) == '0);",
            f"            a_cdc_{label}_gray_one_bit: assert((({output} ^ {output_sample}) & (({output} ^ {output_sample}) - 1'b1)) == '0);",
            f"            c_cdc_{label}_gray_changed: cover({output} != {output_sample});",
            f"            {source_sample} <= {source};",
            f"            {output_sample} <= {output};",
            "        end",
            "    end",
        )
    )
    return lines


def _cdc_structure_policy(plan: VerificationPlan, path: RTLCDCPath):
    supported = {"pulse", "toggle", "gray", "handshake", "multi_bit_handshake"}
    return next(
        (
            item
            for item in plan.depth_policies
            if item.kind == "cdc" and item.subject == path.signal and item.parameter("structure") in supported
        ),
        None,
    )


def _cdc_evidence(
    plan: VerificationPlan,
    policy: CDCProofPolicy,
    bmc_depth: int,
) -> tuple[_CDCPathEvidence, ...]:
    ports = set(_port_names_from_plan(plan))
    domains = {domain.domain_id: domain for domain in plan.control_domains}
    evidence: list[_CDCPathEvidence] = []
    for path in plan.cdc_paths:
        observed = tuple(stage for stage in path.stage_signals if stage in ports)
        hidden = tuple(stage for stage in path.stage_signals if stage not in ports)
        domain = domains.get(path.destination_domain)
        reason = _cdc_path_reason(path, domain, ports)
        level, task, closure_eligible, bound_steps, reason = _cdc_evidence_level(
            path, policy, bmc_depth, ports, hidden, reason
        )

        evidence.append(
            _CDCPathEvidence(
                path_id=path.path_id,
                signal=path.signal,
                evidence_level=level,
                closure_eligible=closure_eligible,
                task=task,
                clock=domain.clock if domain is not None else None,
                observed_stages=observed,
                hidden_stages=hidden,
                latency_cycles=path.synchronizer_stages,
                bound_steps=bound_steps,
                reason=reason,
            )
        )
    return tuple(evidence)


def _cdc_path_reason(path, domain, ports: set[str]) -> str | None:
    if not path.safe:
        return "RTL analysis did not classify the crossing as safe"
    if path.classification not in {"two_flop", "pulse", "toggle", "gray", "handshake", "multi_bit_handshake"}:
        return f"unsupported CDC classification {path.classification!r}"
    if path.synchronizer_stages < 2 or len(path.stage_signals) != path.synchronizer_stages:
        return "synchronizer stage metadata is incomplete or inconsistent"
    if path.reset_compatible is False:
        return "source and destination reset strategies are incompatible"
    if domain is None or not domain.clock:
        return "destination control domain has no classified clock"
    if domain.clock not in ports:
        return "destination clock is not an observable input port"
    if path.signal not in ports:
        return "CDC source signal is not an observable port"
    return None


def _cdc_evidence_level(
    path,
    policy: CDCProofPolicy,
    bmc_depth: int,
    ports: set[str],
    hidden: tuple[str, ...],
    reason: str | None,
) -> tuple[str, str | None, bool, int | None, str | None]:
    if reason is not None:
        return "unsupported", None, False, None, reason
    if not hidden:
        return "structural", "prove", True, None, None
    if policy != CDCProofPolicy.BOUNDED:
        reason = "internal synchronizer stages are hidden; select bounded policy or expose formal stage ports"
        return "unsupported", None, False, None, reason
    if not path.stage_signals or path.stage_signals[-1] not in ports:
        reason = "final synchronizer stage is not an observable output port"
        return "unsupported", None, False, None, reason
    if bmc_depth < path.synchronizer_stages + 1:
        reason = f"CDC BMC depth {bmc_depth} is below the minimum {path.synchronizer_stages + 1} steps"
        return "unsupported", None, False, None, reason
    reason = "internal synchronizer stages are hidden; only external latency is checked"
    return "bounded", "cdc_bmc", False, bmc_depth, reason


def _cdc_report_content(
    plan: VerificationPlan,
    policy: CDCProofPolicy,
    bmc_depth: int,
    evidence: tuple[_CDCPathEvidence, ...],
) -> str:
    presentation: dict[str, object] = {
        "_plan": plan,
        "artifact_kind": "report",
        "header": "",
        "payload": _cdc_report_payload(plan, policy, bmc_depth, evidence),
    }
    return render_target("formal", presentation)  # type: ignore[arg-type]


def _cdc_report_payload(
    plan: VerificationPlan,
    policy: CDCProofPolicy,
    bmc_depth: int,
    evidence: tuple[_CDCPathEvidence, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "module": plan.module,
        "policy": str(policy),
        "bounded_depth": bmc_depth,
        "paths": [
            {
                "path_id": item.path_id,
                "signal": item.signal,
                "evidence_level": item.evidence_level,
                "closure_eligible": item.closure_eligible,
                "formal_task": item.task,
                "clock": item.clock,
                "observed_stages": list(item.observed_stages),
                "hidden_stages": list(item.hidden_stages),
                "latency_cycles": item.latency_cycles,
                "bound_steps": item.bound_steps,
                "reason": item.reason,
            }
            for item in evidence
        ],
    }


def _formal_signal_ref(signal: str, ports: set[str]) -> str:
    safe = _safe_identifier(signal)
    return safe if signal in ports else f"dut.{safe}"


def _output_wire_declaration(plan: VerificationPlan, port: str) -> str:
    planned_port = _structured_ports(plan).get(port)
    if planned_port is not None:
        signed = " signed" if planned_port.signed else ""
        if planned_port.width is not None and planned_port.width > 1:
            return "wire" + signed + " [" + str(planned_port.width - 1) + ":0] " + port
        if planned_port.packed_range and _safe_packed_range(planned_port.packed_range):
            return "wire" + signed + " " + planned_port.packed_range + " " + port
        return "wire" + signed + " " + port
    dtype = _verilator_port_dtype(plan, port)
    if dtype is None:
        return "wire " + port
    left = dtype.attrib.get("left")
    right = dtype.attrib.get("right")
    signed = " signed" if dtype.attrib.get("signed") == "true" else ""
    if left is not None and right is not None and _safe_sv_bound(left) and _safe_sv_bound(right):
        return "wire" + signed + " [" + left + ":" + right + "] " + port
    return "wire" + signed + " " + port


def _verilator_port_dtype(plan: VerificationPlan, port: str) -> Element | None:
    locator = "port:" + plan.module + "." + port
    for claim in plan.claims:
        for ref in claim.evidence_refs:
            if ref.locator.split("@", 1)[0] != locator:
                continue
            source_path = Path(ref.source_id)
            if not source_path.is_file():
                continue
            try:
                root = parse(source_path).getroot()
            except ParseError:
                continue
            if root is None:
                continue
            dtype_id = _verilator_port_dtype_id(root, plan.design_unit or plan.module, port)
            if dtype_id is None:
                continue
            dtype = _verilator_dtype(root, dtype_id)
            if dtype is not None:
                return dtype
    return None


def _verilator_port_dtype_id(root: Element, module: str, port: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) != "module":
            continue
        if (element.attrib.get("origName") or element.attrib.get("name")) != module:
            continue
        for child in element:
            if _local_name(child.tag) != "var":
                continue
            if (child.attrib.get("origName") or child.attrib.get("name")) == port:
                return child.attrib.get("dtype_id")
    return None


def _verilator_dtype(root: Element, dtype_id: str) -> Element | None:
    for element in root.iter():
        if element.attrib.get("id") == dtype_id and _local_name(element.tag).endswith("dtype"):
            return element
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_sv_bound(value: str) -> bool:
    return value.isdecimal()


def _safe_packed_range(value: str) -> bool:
    if not value.startswith("[") or not value.endswith("]") or ":" not in value:
        return False
    left, right = value.strip("[]").split(":", 1)
    return _safe_sv_bound(left.strip()) and _safe_sv_bound(right.strip())


def _is_zero_value(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.lower().replace("_", "")
    if normalized in {"0", "'0", "1'b0", "1'h0", "1'd0"}:
        return True
    if "'" in normalized:
        return normalized.rsplit("'", 1)[-1].lstrip("s").lstrip("bhd") == "0"
    return False


def _looks_like_scalar_input(port: str) -> bool:
    if port.endswith(("_o", "_out")):
        return False
    return port.endswith(("_i", "_in")) or port in {"enable", "en", "valid", "ready", "start", "clear", "load"}


def _looks_like_output(port: str) -> bool:
    return port.endswith(("_o", "_out"))


def _comma_terminate(lines: list[str]) -> list[str]:
    return [line + ("," if index < len(lines) - 1 else "") for index, line in enumerate(lines)]


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
