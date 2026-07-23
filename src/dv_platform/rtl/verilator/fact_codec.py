# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

from typing import Any

from dv_platform.agent.protocols import ProtocolChannel, ProtocolModel, RegisterConflict, RegisterField, RegisterModel
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLAssignment,
    RTLBranch,
    RTLCDCPath,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemoryAccess,
    RTLParameterBinding,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProperty,
    RTLProtocol,
    RTLSemanticFeature,
    RTLType,
    RTLTypeMember,
    VerificationTarget,
)

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


def _memory_access_from_json(data: dict[str, Any]) -> RTLMemoryAccess:
    return RTLMemoryAccess(
        access_id=str(data["access_id"]),
        memory=str(data["memory"]),
        kind=str(data["kind"]),
        address_signals=tuple(str(item) for item in data.get("address_signals", ())),
        data_signals=tuple(str(item) for item in data.get("data_signals", ())),
        enable_signals=tuple(str(item) for item in data.get("enable_signals", ())),
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
        synchronous=bool(data.get("synchronous", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _type_to_json(item: RTLType) -> dict[str, object]:
    return {
        "type_id": item.type_id,
        "name": item.name,
        "kind": item.kind,
        "width": item.width,
        "signed": item.signed,
        "members": list(item.members),
        "enum_values": list(item.enum_values),
        "source_location": item.source_location,
        "member_details": [
            {
                "name": member.name,
                "dtype_id": member.dtype_id,
                "width": member.width,
                "signed": member.signed,
                "packed_range": member.packed_range,
                "bit_offset": member.bit_offset,
                "packed_dimensions": list(member.packed_dimensions),
                "unpacked_dimensions": list(member.unpacked_dimensions),
                "source_location": member.source_location,
            }
            for member in item.member_details
        ],
        "packed_dimensions": list(item.packed_dimensions),
        "unpacked_dimensions": list(item.unpacked_dimensions),
        "package_name": item.package_name,
    }


def _type_from_json(data: dict[str, Any]) -> RTLType:
    return RTLType(
        type_id=str(data["type_id"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        kind=str(data["kind"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        members=tuple(str(item) for item in data.get("members", ())),
        enum_values=tuple(str(item) for item in data.get("enum_values", ())),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        member_details=tuple(
            RTLTypeMember(
                name=str(item["name"]),
                dtype_id=str(item["dtype_id"]) if item.get("dtype_id") is not None else None,
                width=int(item["width"]) if item.get("width") is not None else None,
                signed=bool(item["signed"]) if item.get("signed") is not None else None,
                packed_range=str(item["packed_range"]) if item.get("packed_range") is not None else None,
                bit_offset=int(item["bit_offset"]) if item.get("bit_offset") is not None else None,
                packed_dimensions=tuple(str(value) for value in item.get("packed_dimensions", ())),
                unpacked_dimensions=tuple(str(value) for value in item.get("unpacked_dimensions", ())),
                source_location=str(item["source_location"]) if item.get("source_location") is not None else None,
            )
            for item in data.get("member_details", ())
        ),
        packed_dimensions=tuple(str(item) for item in data.get("packed_dimensions", ())),
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
        package_name=str(data["package_name"]) if data.get("package_name") is not None else None,
    )


def _semantic_feature_from_json(data: dict[str, Any]) -> RTLSemanticFeature:
    return RTLSemanticFeature(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        confidence=str(data.get("confidence", "parser")),
        generation_supported=bool(data.get("generation_supported", False)),
        supported_targets=tuple(VerificationTarget(str(item)) for item in data.get("supported_targets", ())),
    )


def _instance_from_json(data: dict[str, Any]) -> RTLInstance:
    return RTLInstance(
        name=str(data["name"]),
        module_name=str(data["module_name"]) if data.get("module_name") is not None else None,
        elaborated_module_name=(
            str(data["elaborated_module_name"]) if data.get("elaborated_module_name") is not None else None
        ),
        plan_module_name=str(data["plan_module_name"]) if data.get("plan_module_name") is not None else None,
        specialization_id=(str(data["specialization_id"]) if data.get("specialization_id") is not None else None),
        parameter_bindings=tuple(
            RTLParameterBinding(
                name=str(item["name"]),
                value=str(item["value"]) if item.get("value") is not None else None,
            )
            for item in data.get("parameter_bindings", ())
        ),
        kind=str(data["kind"]) if data.get("kind") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        connections=tuple(_connection_from_json(item) for item in data.get("connections", ())),
    )


def _connection_from_json(data: dict[str, Any]) -> RTLConnection:
    expression_data = data.get("expression")
    return RTLConnection(
        port_name=str(data["port_name"]),
        direction=str(data["direction"]) if data.get("direction") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expression=_expression_from_json(expression_data) if isinstance(expression_data, dict) else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _assignment_from_json(data: dict[str, Any]) -> RTLAssignment:
    return RTLAssignment(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        lhs_signals=tuple(str(item) for item in data.get("lhs_signals", ())),
        rhs_signals=tuple(str(item) for item in data.get("rhs_signals", ())),
        expressions=tuple(_expression_from_json(item) for item in data.get("expressions", ())),
    )


def _expression_from_json(data: dict[str, Any]) -> RTLExpression:
    return RTLExpression(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        children=tuple(_expression_from_json(item) for item in data.get("children", ())),
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data["signed"]) if data.get("signed") is not None else None,
        cast_kind=str(data["cast_kind"]) if data.get("cast_kind") is not None else None,
        packed_range=str(data["packed_range"]) if data.get("packed_range") is not None else None,
    )


def _expression_to_json(expression: RTLExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "value": expression.value,
        "dtype_id": expression.dtype_id,
        "source_location": expression.source_location,
        "children": [_expression_to_json(child) for child in expression.children],
        "width": expression.width,
        "signed": expression.signed,
        "cast_kind": expression.cast_kind,
        "packed_range": expression.packed_range,
    }


def _procedural_block_from_json(data: dict[str, Any]) -> RTLProceduralBlock:
    return RTLProceduralBlock(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expressions=tuple(_expression_from_json(item) for item in data.get("expressions", ())),
        branches=tuple(_branch_from_json(item) for item in data.get("branches", ())),
        patterns=tuple(_procedural_pattern_from_json(item) for item in data.get("patterns", ())),
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
    )


def _branch_from_json(data: dict[str, Any]) -> RTLBranch:
    condition = data.get("condition")
    return RTLBranch(
        kind=str(data["kind"]),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        condition=_expression_from_json(condition) if isinstance(condition, dict) else None,
        labels=tuple(_expression_from_json(item) for item in data.get("labels", ())),
        is_default=bool(data.get("is_default", False)),
        mutually_exclusive=(bool(data["mutually_exclusive"]) if data.get("mutually_exclusive") is not None else None),
    )


def _procedural_pattern_from_json(data: dict[str, Any]) -> RTLProceduralPattern:
    return RTLProceduralPattern(
        kind=str(data["kind"]),
        target=str(data["target"]),
        control=str(data["control"]) if data.get("control") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        source=str(data["source"]) if data.get("source") is not None else None,
        confidence=str(data.get("confidence", "shape")),
    )


def _control_domain_from_json(data: dict[str, Any]) -> RTLControlDomain:
    return RTLControlDomain(
        domain_id=str(data["domain_id"]),
        clock=str(data["clock"]),
        clock_edge=str(data.get("clock_edge", "pos")),
        reset=str(data["reset"]) if data.get("reset") is not None else None,
        reset_edge=str(data["reset_edge"]) if data.get("reset_edge") is not None else None,
        reset_active_low=bool(data["reset_active_low"]) if data.get("reset_active_low") is not None else None,
        asynchronous_reset=bool(data.get("asynchronous_reset", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _cdc_path_to_json(path: RTLCDCPath) -> dict[str, object]:
    return {
        "path_id": path.path_id,
        "signal": path.signal,
        "source_domain": path.source_domain,
        "destination_domain": path.destination_domain,
        "classification": path.classification,
        "synchronizer_stages": path.synchronizer_stages,
        "stage_signals": list(path.stage_signals),
        "safe": path.safe,
        "reset_compatible": path.reset_compatible,
        "source_location": path.source_location,
        "evidence_refs": [_evidence_to_json(ref) for ref in path.evidence_refs],
    }


def _cdc_path_from_json(data: dict[str, Any]) -> RTLCDCPath:
    return RTLCDCPath(
        path_id=str(data["path_id"]),
        signal=str(data["signal"]),
        source_domain=str(data["source_domain"]),
        destination_domain=str(data["destination_domain"]),
        classification=str(data.get("classification", "direct")),
        synchronizer_stages=int(data.get("synchronizer_stages", 0)),
        stage_signals=tuple(str(item) for item in data.get("stage_signals", ())),
        safe=bool(data.get("safe", False)),
        reset_compatible=bool(data["reset_compatible"]) if data.get("reset_compatible") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _generate_scope_to_json(scope: RTLGenerateScope) -> dict[str, object]:
    return {
        "scope_id": scope.scope_id,
        "name": scope.name,
        "kind": scope.kind,
        "source_location": scope.source_location,
        "instance_names": list(scope.instance_names),
        "condition": _expression_to_json(scope.condition) if scope.condition is not None else None,
        "selected": scope.selected,
        "iteration_index": scope.iteration_index,
    }


def _generate_scope_from_json(data: dict[str, Any]) -> RTLGenerateScope:
    condition = data.get("condition")
    return RTLGenerateScope(
        scope_id=str(data["scope_id"]),
        name=str(data["name"]),
        kind=str(data["kind"]),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        instance_names=tuple(str(item) for item in data.get("instance_names", ())),
        condition=_expression_from_json(condition) if isinstance(condition, dict) else None,
        selected=bool(data["selected"]) if data.get("selected") is not None else None,
        iteration_index=int(data["iteration_index"]) if data.get("iteration_index") is not None else None,
    )


def _property_to_json(prop: RTLProperty) -> dict[str, object]:
    return {
        "kind": prop.kind,
        "name": prop.name,
        "concurrent": prop.concurrent,
        "clock": prop.clock,
        "clock_edge": prop.clock_edge,
        "disable_condition": (
            _expression_to_json(prop.disable_condition) if prop.disable_condition is not None else None
        ),
        "body": _expression_to_json(prop.body) if prop.body is not None else None,
        "source_location": prop.source_location,
        "support_status": prop.support_status,
        "unsupported_operators": list(prop.unsupported_operators),
    }


def _property_from_json(data: dict[str, Any]) -> RTLProperty:
    disable = data.get("disable_condition")
    body = data.get("body")
    return RTLProperty(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        concurrent=bool(data.get("concurrent", False)),
        clock=str(data["clock"]) if data.get("clock") is not None else None,
        clock_edge=str(data["clock_edge"]) if data.get("clock_edge") is not None else None,
        disable_condition=_expression_from_json(disable) if isinstance(disable, dict) else None,
        body=_expression_from_json(body) if isinstance(body, dict) else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        support_status=str(data.get("support_status", "unsupported")),
        unsupported_operators=tuple(str(item) for item in data.get("unsupported_operators", ())),
    )


def _protocol_from_json(data: dict[str, Any]) -> RTLProtocol:
    return RTLProtocol(
        protocol_id=str(data["protocol_id"]),
        kind=str(data["kind"]),
        name=str(data["name"]),
        role=str(data["role"]),
        valid=str(data["valid"]),
        ready=str(data["ready"]),
        data=str(data["data"]) if data.get("data") is not None else None,
        data_width=int(data["data_width"]) if data.get("data_width") is not None else None,
        clock=str(data["clock"]) if data.get("clock") is not None else None,
        reset=str(data["reset"]) if data.get("reset") is not None else None,
        confidence=str(data.get("confidence", "naming")),
        profile=str(data.get("profile", "builtin")),
        signal_map=tuple((str(item[0]), str(item[1])) for item in data.get("signal_map", ())),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
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
                str(item["name"]),
                tuple(str(value) for value in item.get("signals", ())),
                str(item["direction"]),
                str(item["transfer_condition"]),
                tuple(_evidence_from_json(ref) for ref in item.get("evidence_refs", ())),
                tuple(str(value) for value in item.get("payload_fields", ())),
                str(item["completion_condition"]) if item.get("completion_condition") is not None else None,
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
                str(item["name"]),
                int(item["msb"]),
                int(item["lsb"]),
                str(item["reset_value"]) if item.get("reset_value") is not None else None,
                str(item.get("access", "unknown")),
                str(item["side_effect"]) if item.get("side_effect") is not None else None,
                bool(item.get("reserved", False)),
                tuple(_evidence_from_json(ref) for ref in item.get("evidence_refs", ())),
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
        tuple(_evidence_from_json(ref) for ref in data.get("evidence_refs", ())),
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
