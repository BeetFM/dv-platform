# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Plan persistence and derived review views."""

from __future__ import annotations

from typing import Any

from dv_platform.core.models import (
    RTLCDCPath,
    RTLClock,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProperty,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    RTLTypeMember,
    VerificationTarget,
)


def _port_from_json(data: dict[str, Any]) -> RTLPort:
    return RTLPort(
        name=str(data["name"]),
        direction=str(data.get("direction", "unknown")),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        packed_range=str(data["packed_range"]) if data.get("packed_range") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        interface_name=str(data["interface_name"]) if data.get("interface_name") is not None else None,
        modport=str(data["modport"]) if data.get("modport") is not None else None,
        interface_direction=(str(data["interface_direction"]) if data.get("interface_direction") is not None else None),
        packed_dimensions=tuple(str(item) for item in data.get("packed_dimensions", ())),
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
    )


def _clock_from_json(data: dict[str, Any]) -> RTLClock:
    return RTLClock(
        name=str(data["name"]),
        direction=str(data.get("direction", "input")),
        width=int(data["width"]) if data.get("width") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
        confidence=str(data.get("confidence", "low")),
    )


def _reset_from_json(data: dict[str, Any]) -> RTLReset:
    return RTLReset(
        name=str(data["name"]),
        direction=str(data.get("direction", "input")),
        width=int(data["width"]) if data.get("width") is not None else None,
        active_low=bool(data["active_low"]) if data.get("active_low") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
        confidence=str(data.get("confidence", "low")),
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


def _parameter_to_json(parameter: RTLParameter) -> dict[str, object]:
    return {
        "name": parameter.name,
        "default_value": parameter.default_value,
        "dtype_id": parameter.dtype_id,
        "data_type": parameter.data_type,
        "width": parameter.width,
        "signed": parameter.signed,
        "local": parameter.local,
        "source_location": parameter.source_location,
    }


def _parameter_from_json(data: dict[str, Any]) -> RTLParameter:
    return RTLParameter(
        name=str(data["name"]),
        default_value=str(data["default_value"]) if data.get("default_value") is not None else None,
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        local=bool(data.get("local", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _memory_to_json(memory: RTLMemory) -> dict[str, object]:
    return {
        "name": memory.name,
        "dtype_id": memory.dtype_id,
        "element_width": memory.element_width,
        "depth": memory.depth,
        "address_width": memory.address_width,
        "read_during_write": memory.read_during_write,
        "source_location": memory.source_location,
        "unpacked_dimensions": list(memory.unpacked_dimensions),
        "initialization_profile": memory.initialization_profile,
        "initialization_path": memory.initialization_path,
        "initialization_sha256": memory.initialization_sha256,
        "initialization_default_policy": memory.initialization_default_policy,
    }


def _memory_from_json(data: dict[str, Any]) -> RTLMemory:
    return RTLMemory(
        name=str(data["name"]),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        element_width=int(data["element_width"]) if data.get("element_width") is not None else None,
        depth=int(data["depth"]) if data.get("depth") is not None else None,
        address_width=int(data["address_width"]) if data.get("address_width") is not None else None,
        read_during_write=str(data.get("read_during_write", "unknown")),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
        initialization_profile=str(data.get("initialization_profile", "unknown")),
        initialization_path=(str(data["initialization_path"]) if data.get("initialization_path") is not None else None),
        initialization_sha256=(
            str(data["initialization_sha256"]) if data.get("initialization_sha256") is not None else None
        ),
        initialization_default_policy=str(data.get("initialization_default_policy", "unknown")),
    )


def _memory_access_to_json(access: RTLMemoryAccess) -> dict[str, object]:
    return {
        "access_id": access.access_id,
        "memory": access.memory,
        "kind": access.kind,
        "address_signals": list(access.address_signals),
        "data_signals": list(access.data_signals),
        "enable_signals": list(access.enable_signals),
        "domain_id": access.domain_id,
        "synchronous": access.synchronous,
        "source_location": access.source_location,
        "evidence_refs": [_evidence_to_json(ref) for ref in access.evidence_refs],
    }


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


def _type_to_json(type_detail: RTLType) -> dict[str, object]:
    return {
        "type_id": type_detail.type_id,
        "name": type_detail.name,
        "kind": type_detail.kind,
        "width": type_detail.width,
        "signed": type_detail.signed,
        "members": list(type_detail.members),
        "enum_values": list(type_detail.enum_values),
        "source_location": type_detail.source_location,
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
            for member in type_detail.member_details
        ],
        "packed_dimensions": list(type_detail.packed_dimensions),
        "unpacked_dimensions": list(type_detail.unpacked_dimensions),
        "package_name": type_detail.package_name,
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


def _connection_to_json(connection: RTLConnection) -> dict[str, object]:
    return {
        "port_name": connection.port_name,
        "direction": connection.direction,
        "signal_refs": list(connection.signal_refs),
        "expression": _expression_to_json(connection.expression) if connection.expression is not None else None,
        "source_location": connection.source_location,
    }


def _connection_from_json(data: dict[str, Any]) -> RTLConnection:
    expression = data.get("expression")
    return RTLConnection(
        port_name=str(data["port_name"]),
        direction=str(data["direction"]) if data.get("direction") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expression=_expression_from_json(expression) if isinstance(expression, dict) else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _instance_to_json(instance: RTLInstance) -> dict[str, object]:
    return {
        "name": instance.name,
        "module_name": instance.module_name,
        "elaborated_module_name": instance.elaborated_module_name,
        "plan_module_name": instance.plan_module_name,
        "specialization_id": instance.specialization_id,
        "parameter_bindings": [
            {"name": binding.name, "value": binding.value} for binding in instance.parameter_bindings
        ],
        "kind": instance.kind,
        "source_location": instance.source_location,
        "connections": [_connection_to_json(connection) for connection in instance.connections],
    }


def _instance_from_json(data: dict[str, Any]) -> RTLInstance:
    return RTLInstance(
        name=str(data["name"]),
        module_name=str(data["module_name"]) if data.get("module_name") is not None else None,
        elaborated_module_name=(
            str(data["elaborated_module_name"]) if data.get("elaborated_module_name") is not None else None
        ),
        plan_module_name=str(data["plan_module_name"]) if data.get("plan_module_name") is not None else None,
        specialization_id=str(data["specialization_id"]) if data.get("specialization_id") is not None else None,
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


def _control_domain_to_json(domain: RTLControlDomain) -> dict[str, object]:
    return {
        "domain_id": domain.domain_id,
        "clock": domain.clock,
        "clock_edge": domain.clock_edge,
        "reset": domain.reset,
        "reset_edge": domain.reset_edge,
        "reset_active_low": domain.reset_active_low,
        "asynchronous_reset": domain.asynchronous_reset,
        "source_location": domain.source_location,
    }


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
        reset_compatible=(bool(data["reset_compatible"]) if data.get("reset_compatible") is not None else None),
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


def _protocol_to_json(protocol: RTLProtocol) -> dict[str, object]:
    return {
        "protocol_id": protocol.protocol_id,
        "kind": protocol.kind,
        "name": protocol.name,
        "role": protocol.role,
        "valid": protocol.valid,
        "ready": protocol.ready,
        "data": protocol.data,
        "data_width": protocol.data_width,
        "clock": protocol.clock,
        "reset": protocol.reset,
        "confidence": protocol.confidence,
        "profile": protocol.profile,
        "signal_map": [list(item) for item in protocol.signal_map],
        "evidence_refs": [_evidence_to_json(ref) for ref in protocol.evidence_refs],
    }


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
