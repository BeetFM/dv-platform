# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Plan persistence and derived review views."""

from __future__ import annotations

from typing import Any

from dv_platform.agent.protocols import ProtocolChannel, ProtocolModel, RegisterConflict, RegisterField, RegisterModel
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    Severity,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationRequirement,
    VerificationScenario,
    VerificationTarget,
)


def _protocol_model_to_json(protocol: ProtocolModel) -> dict[str, object]:
    return {
        "name": protocol.name,
        "version": protocol.version,
        "channels": [
            {
                "name": channel.name,
                "signals": list(channel.signals),
                "direction": channel.direction,
                "transfer_condition": channel.transfer_condition,
                "payload_fields": list(channel.payload_fields),
                "completion_condition": channel.completion_condition,
                "evidence_refs": [_evidence_to_json(ref) for ref in channel.evidence_refs],
            }
            for channel in protocol.channels
        ],
        "signal_bindings": [list(item) for item in protocol.signal_bindings],
        "signal_directions": [list(item) for item in protocol.signal_directions],
        "clock_domain": protocol.clock_domain,
        "reset_domain": protocol.reset_domain,
        "ordering_rules": list(protocol.ordering_rules),
        "response_rules": list(protocol.response_rules),
        "error_behavior": protocol.error_behavior,
        "confidence": protocol.confidence,
        "unsupported_semantics": list(protocol.unsupported_semantics),
        "evidence_refs": [_evidence_to_json(ref) for ref in protocol.evidence_refs],
        "profile_id": protocol.profile_id,
        "instance_id": protocol.instance_id,
        "role": protocol.role,
        "maximum_burst_length": protocol.maximum_burst_length,
        "maximum_outstanding": protocol.maximum_outstanding,
        "timeout_cycles": protocol.timeout_cycles,
        "scoreboard_keys": list(protocol.scoreboard_keys),
        "coverage_bins": list(protocol.coverage_bins),
        "formal_properties": list(protocol.formal_properties),
        "result_traces": list(protocol.result_traces),
    }


def _protocol_model_from_json(data: dict[str, Any]) -> ProtocolModel:
    return ProtocolModel(
        name=str(data["name"]),
        version=str(data["version"]),
        channels=tuple(
            ProtocolChannel(
                name=str(item["name"]),
                signals=tuple(str(value) for value in item.get("signals", ())),
                direction=str(item["direction"]),
                transfer_condition=str(item["transfer_condition"]),
                evidence_refs=tuple(_evidence_from_json(ref) for ref in item.get("evidence_refs", ())),
                payload_fields=tuple(str(value) for value in item.get("payload_fields", ())),
                completion_condition=(
                    str(item["completion_condition"]) if item.get("completion_condition") is not None else None
                ),
            )
            for item in data.get("channels", ())
        ),
        signal_bindings=tuple((str(item[0]), str(item[1])) for item in data.get("signal_bindings", ())),
        signal_directions=tuple((str(item[0]), str(item[1])) for item in data.get("signal_directions", ())),
        clock_domain=str(data["clock_domain"]) if data.get("clock_domain") is not None else None,
        reset_domain=str(data["reset_domain"]) if data.get("reset_domain") is not None else None,
        ordering_rules=tuple(str(item) for item in data.get("ordering_rules", ())),
        response_rules=tuple(str(item) for item in data.get("response_rules", ())),
        error_behavior=str(data.get("error_behavior", "unknown")),
        confidence=str(data.get("confidence", "unknown")),
        unsupported_semantics=tuple(str(item) for item in data.get("unsupported_semantics", ())),
        evidence_refs=tuple(_evidence_from_json(ref) for ref in data.get("evidence_refs", ())),
        profile_id=str(data["profile_id"]) if data.get("profile_id") is not None else None,
        instance_id=str(data["instance_id"]) if data.get("instance_id") is not None else None,
        role=str(data.get("role", "subordinate")),
        maximum_burst_length=int(data.get("maximum_burst_length", 1)),
        maximum_outstanding=int(data.get("maximum_outstanding", 1)),
        timeout_cycles=int(data.get("timeout_cycles", 32)),
        scoreboard_keys=tuple(str(item) for item in data.get("scoreboard_keys", ("sequence",))),
        coverage_bins=tuple(str(item) for item in data.get("coverage_bins", ())),
        formal_properties=tuple(str(item) for item in data.get("formal_properties", ())),
        result_traces=tuple(str(item) for item in data.get("result_traces", ())),
    )


def _register_model_to_json(register: RegisterModel) -> dict[str, object]:
    return {
        "name": register.name,
        "offset": register.offset,
        "width": register.width,
        "fields": [
            {
                "name": field.name,
                "msb": field.msb,
                "lsb": field.lsb,
                "reset_value": field.reset_value,
                "access": field.access,
                "side_effect": field.side_effect,
                "reserved": field.reserved,
                "evidence_refs": [_evidence_to_json(ref) for ref in field.evidence_refs],
            }
            for field in register.fields
        ],
        "invalid_address_behavior": register.invalid_address_behavior,
        "byte_enable_behavior": register.byte_enable_behavior,
        "source": register.source,
        "evidence_refs": [_evidence_to_json(ref) for ref in register.evidence_refs],
    }


def _register_model_from_json(data: dict[str, Any]) -> RegisterModel:
    return RegisterModel(
        name=str(data["name"]),
        offset=int(data["offset"]) if data.get("offset") is not None else None,
        width=int(data["width"]),
        fields=tuple(
            RegisterField(
                name=str(item["name"]),
                msb=int(item["msb"]),
                lsb=int(item["lsb"]),
                reset_value=str(item["reset_value"]) if item.get("reset_value") is not None else None,
                access=str(item.get("access", "unknown")),
                side_effect=str(item["side_effect"]) if item.get("side_effect") is not None else None,
                reserved=bool(item.get("reserved", False)),
                evidence_refs=tuple(_evidence_from_json(ref) for ref in item.get("evidence_refs", ())),
            )
            for item in data.get("fields", ())
        ),
        invalid_address_behavior=str(data.get("invalid_address_behavior", "unknown")),
        byte_enable_behavior=str(data.get("byte_enable_behavior", "unknown")),
        source=str(data.get("source", "unknown")),
        evidence_refs=tuple(_evidence_from_json(ref) for ref in data.get("evidence_refs", ())),
    )


def _register_conflict_to_json(conflict: RegisterConflict) -> dict[str, object]:
    return {
        "register_name": conflict.register_name,
        "property_name": conflict.property_name,
        "values": list(conflict.values),
        "reason": conflict.reason,
        "evidence_refs": [_evidence_to_json(ref) for ref in conflict.evidence_refs],
    }


def _register_conflict_from_json(data: dict[str, Any]) -> RegisterConflict:
    return RegisterConflict(
        str(data["register_name"]),
        str(data["property_name"]),
        tuple(str(item) for item in data.get("values", ())),
        str(data["reason"]),
        tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _check_to_json(check: VerificationCheck) -> dict[str, object]:
    return {
        "check_id": check.check_id,
        "statement": check.statement,
        "category": check.category,
        "executable": check.executable,
        "evidence_refs": [_evidence_to_json(ref) for ref in check.evidence_refs],
        "closure_status": check.closure_status,
        "coverage_point_ids": list(check.coverage_point_ids),
    }


def _check_from_json(data: dict[str, Any]) -> VerificationCheck:
    return VerificationCheck(
        check_id=str(data["check_id"]),
        statement=str(data["statement"]),
        category=str(data.get("category", "general")),
        executable=bool(data.get("executable", False)),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
        closure_status=str(data["closure_status"]) if data.get("closure_status") is not None else None,
        coverage_point_ids=tuple(str(item) for item in data.get("coverage_point_ids", ())),
    )


def _scenario_to_json(scenario: VerificationScenario) -> dict[str, object]:
    return {
        "scenario_id": scenario.scenario_id,
        "kind": scenario.kind,
        "stimulus": [
            {
                "kind": item.kind,
                "signal": item.signal,
                "value": item.value,
                "parameters": [list(pair) for pair in item.parameters],
            }
            for item in scenario.stimulus
        ],
        "oracle": {
            "kind": scenario.oracle.kind,
            "actual": scenario.oracle.actual,
            "expected": scenario.oracle.expected,
            "condition": scenario.oracle.condition,
        },
        "completion": {
            "kind": scenario.completion.kind,
            "signal": scenario.completion.signal,
            "value": scenario.completion.value,
            "timeout_cycles": scenario.completion.timeout_cycles,
        },
        "coverage_goals": [
            {"goal_id": goal.goal_id, "kind": goal.kind, "bins": list(goal.bins)} for goal in scenario.coverage_goals
        ],
        "supported_targets": [str(target) for target in scenario.supported_targets],
        "target_states": [
            {
                "target": str(item.target),
                "state": str(item.state),
                "renderer_id": item.renderer_id,
                "reason": item.reason,
            }
            for item in scenario.target_states
        ],
        "requirement_ids": list(scenario.requirement_ids),
        "check_ids": list(scenario.check_ids),
        "evidence_refs": [_evidence_to_json(ref) for ref in scenario.evidence_refs],
        "executable": scenario.executable,
    }


def _scenario_from_json(data: dict[str, Any]) -> VerificationScenario:
    oracle = data.get("oracle", {})
    completion = data.get("completion", {})
    if not isinstance(oracle, dict) or not isinstance(completion, dict):
        raise ValueError("Plan scenario oracle and completion must be objects")
    return VerificationScenario(
        scenario_id=str(data["scenario_id"]),
        kind=str(data["kind"]),
        stimulus=tuple(
            ScenarioStimulus(
                kind=str(item["kind"]),
                signal=str(item["signal"]) if item.get("signal") is not None else None,
                value=str(item["value"]) if item.get("value") is not None else None,
                parameters=tuple((str(pair[0]), str(pair[1])) for pair in item.get("parameters", ())),
            )
            for item in data.get("stimulus", ())
        ),
        oracle=ScenarioOracle(
            kind=str(oracle["kind"]),
            actual=str(oracle["actual"]) if oracle.get("actual") is not None else None,
            expected=str(oracle["expected"]) if oracle.get("expected") is not None else None,
            condition=str(oracle["condition"]) if oracle.get("condition") is not None else None,
        ),
        completion=ScenarioCompletion(
            kind=str(completion["kind"]),
            signal=str(completion["signal"]) if completion.get("signal") is not None else None,
            value=str(completion["value"]) if completion.get("value") is not None else None,
            timeout_cycles=int(completion.get("timeout_cycles", 32)),
        ),
        coverage_goals=tuple(
            ScenarioCoverageGoal(
                str(item["goal_id"]), str(item["kind"]), tuple(str(value) for value in item.get("bins", ()))
            )
            for item in data.get("coverage_goals", ())
        ),
        supported_targets=tuple(VerificationTarget(str(item)) for item in data.get("supported_targets", ())),
        target_states=tuple(
            ScenarioTargetSupport(
                VerificationTarget(str(item["target"])),
                ScenarioTargetState(str(item["state"])),
                str(item["renderer_id"]) if item.get("renderer_id") is not None else None,
                str(item["reason"]) if item.get("reason") is not None else None,
            )
            for item in data.get("target_states", ())
        ),
        requirement_ids=tuple(str(item) for item in data.get("requirement_ids", ())),
        check_ids=tuple(str(item) for item in data.get("check_ids", ())),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
        executable=bool(data.get("executable", False)),
    )


def _requirement_from_json(data: dict[str, Any]) -> VerificationRequirement:
    return VerificationRequirement(
        requirement_id=str(data["requirement_id"]),
        scope=str(data["scope"]),
        statement=str(data["statement"]),
        category=str(data.get("category", "general")),
        signals=tuple(str(item) for item in data.get("signals", ())),
        expected_value=str(data["expected_value"]) if data.get("expected_value") is not None else None,
        condition=str(data["condition"]) if data.get("condition") is not None else None,
        confidence=str(data.get("confidence", "lexical")),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _conflict_from_json(data: dict[str, Any]) -> RequirementConflict:
    return RequirementConflict(
        conflict_id=str(data["conflict_id"]),
        scope=str(data["scope"]),
        requirement_ids=tuple(str(item) for item in data.get("requirement_ids", ())),
        reason=str(data["reason"]),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _behavior_from_json(data: dict[str, Any]) -> VerificationBehavior:
    return VerificationBehavior(
        behavior_id=str(data["behavior_id"]),
        scope=str(data["scope"]),
        kind=str(data["kind"]),
        target=str(data["target"]),
        control=str(data["control"]) if data.get("control") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        source=str(data["source"]) if data.get("source") is not None else None,
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
        confidence=str(data.get("confidence", "shape")),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _claim_from_json(data: dict[str, Any]) -> VerificationClaim:
    return VerificationClaim(
        claim_id=str(data["claim_id"]),
        scope=str(data["scope"]),
        statement=str(data["statement"]),
        claim_type=ClaimType(str(data["claim_type"])),
        severity=Severity(str(data["severity"])),
        generation_precondition=bool(data["generation_precondition"]),
        status=ClaimStatus(str(data["status"])),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _evidence_from_json(data: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind(str(data["kind"])),
        source_id=str(data["source_id"]),
        locator=str(data["locator"]),
        summary=str(data["summary"]) if data.get("summary") is not None else None,
    )


def _evidence_to_json(ref: EvidenceRef) -> dict[str, object]:
    return {
        "kind": str(ref.kind),
        "source_id": ref.source_id,
        "locator": ref.locator,
        "summary": ref.summary,
    }
