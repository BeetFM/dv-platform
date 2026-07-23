# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

from dv_platform.core.models import (
    RTLAssignment,
    RTLConnection,
    RTLInstance,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProceduralBlock,
    RTLType,
    RTLTypeMember,
)

SEMANTIC_CROSSCHECK_API_VERSION = 2
SEMANTIC_CROSSCHECK_SCHEMA_VERSION = 2
SLANG_MIN_TESTED_MAJOR = 11
SLANG_MAX_TESTED_MAJOR = 11

CAPABILITY_DESIGN_UNITS = "design_units"
CAPABILITY_SPECIALIZATIONS = "specializations"
CAPABILITY_PORTS = "ports"
CAPABILITY_PARAMETERS = "parameters"
CAPABILITY_TYPES = "types"
CAPABILITY_HIERARCHY = "hierarchy"
CAPABILITY_ASSIGNMENTS = "assignments"
CAPABILITY_PROCEDURAL_BLOCKS = "procedural_blocks"
CAPABILITY_EXPRESSIONS = "expressions"
CAPABILITY_BRANCHES = "branches"
CAPABILITY_CONTROL_DOMAINS = "control_domains"
CAPABILITY_PROPERTIES = "properties"
CAPABILITY_INTERFACES = "interfaces"
CAPABILITY_IMPORTS = "imports"
CAPABILITY_GENERATE_SCOPES = "generate_scopes"
CAPABILITY_MEMORIES = "memories"

CORE_REQUIRED_CAPABILITIES = (
    CAPABILITY_DESIGN_UNITS,
    CAPABILITY_SPECIALIZATIONS,
    CAPABILITY_PORTS,
    CAPABILITY_PARAMETERS,
)
BASE_STRUCTURAL_CAPABILITIES = (
    *CORE_REQUIRED_CAPABILITIES,
    CAPABILITY_HIERARCHY,
    CAPABILITY_ASSIGNMENTS,
    CAPABILITY_PROCEDURAL_BLOCKS,
)
COMPARABLE_CAPABILITIES = (
    *CORE_REQUIRED_CAPABILITIES,
    CAPABILITY_TYPES,
    CAPABILITY_HIERARCHY,
    CAPABILITY_ASSIGNMENTS,
    CAPABILITY_PROCEDURAL_BLOCKS,
    CAPABILITY_EXPRESSIONS,
    CAPABILITY_BRANCHES,
    CAPABILITY_CONTROL_DOMAINS,
    CAPABILITY_PROPERTIES,
    CAPABILITY_INTERFACES,
    CAPABILITY_IMPORTS,
    CAPABILITY_GENERATE_SCOPES,
    CAPABILITY_MEMORIES,
)


def _slang_instance(value: dict[str, Any], symbol_index: dict[str, dict[str, Any]]) -> RTLInstance:
    body = _slang_link(value["body"], symbol_index)
    body_name = (
        str(body.get("name")) if body is not None and body.get("name") else _canonical_symbol_name(str(value["body"]))
    )
    body_members = _json_dicts(body.get("members")) if body is not None else ()
    bindings = tuple(
        RTLParameterBinding(str(item.get("name")), _canonical_constant(item.get("value")))
        for item in body_members
        if item.get("kind") == "Parameter" and item.get("name") and not item.get("isLocal")
    )
    if not bindings:
        bindings = tuple(
            RTLParameterBinding(str(item.get("name")), _canonical_constant(item.get("value")))
            for item in _json_dicts(value.get("parameters") or value.get("parameterAssignments"))
            if item.get("name")
        )
    connections = tuple(
        RTLConnection(
            port_name=_slang_connection_port(item),
            direction=_slang_connection_direction(item),
            signal_refs=_slang_signal_refs(_slang_connection_expression(item)),
            expression=_slang_expression(_slang_connection_expression(item)),
            source_location=_slang_source_location(item),
        )
        for item in _json_dicts(value.get("connections"))
    )
    module_name = _slang_original_name(body) if body is not None and body.get("name") else body_name
    return RTLInstance(
        name=str(value["name"]),
        module_name=module_name,
        elaborated_module_name=body_name,
        specialization_id=_canonical_specialization_id(
            module_name or "unknown",
            tuple(RTLParameter(binding.name, binding.value) for binding in bindings),
        ),
        parameter_bindings=bindings,
        source_location=_slang_source_location(value),
        connections=connections,
    )


def _slang_instances_with_paths(
    members: tuple[dict[str, Any], ...], symbol_index: dict[str, dict[str, Any]]
) -> tuple[RTLInstance, ...]:
    result: list[RTLInstance] = []

    def visit(items: tuple[dict[str, Any], ...], scope: str = "") -> None:
        for item in items:
            kind = str(item.get("kind", ""))
            if kind == "Instance" and _is_slang_instance(item):
                instance = _slang_instance(item, symbol_index)
                result.append(replace(instance, name=f"{scope}.{instance.name}" if scope else instance.name))
                continue
            if kind == "GenerateBlockArray":
                base = str(item.get("name") or "generate")
                for block in _json_dicts(item.get("members")):
                    if block.get("kind") != "GenerateBlock":
                        continue
                    index = _slang_generate_index(block)
                    child_scope = f"{base}[{index}]" if index is not None else base
                    visit(_json_dicts(block.get("members")), child_scope)
                continue
            if kind == "GenerateBlock":
                base = str(item.get("name") or item.get("branchKind") or "generate")
                child_scope = f"{scope}.{base}" if scope else base
                visit(_json_dicts(item.get("members")), child_scope)

    visit(members)
    return tuple(result)


def _slang_connection_port(value: dict[str, Any]) -> str:
    port = value.get("port") or value.get("name")
    if isinstance(port, dict):
        return str(port.get("name") or "")
    return _canonical_symbol_name(str(port)) if port is not None else ""


def _slang_connection_direction(value: dict[str, Any]) -> str | None:
    port = value.get("port")
    if not isinstance(port, dict):
        return None
    return {"In": "input", "Out": "output", "InOut": "inout", "Ref": "ref"}.get(str(port.get("direction")))


def _slang_connection_expression(value: dict[str, Any]) -> object:
    expression = value.get("expr") or value.get("expression") or value.get("value")
    port = value.get("port")
    if (
        isinstance(expression, dict)
        and expression.get("kind") == "Assignment"
        and isinstance(port, dict)
        and port.get("direction") == "Out"
    ):
        return expression.get("left")
    return expression


def _slang_summary(value: dict[str, Any]) -> str:
    return str(value.get("kind", "unknown"))


def _slang_source_location(value: dict[str, Any]) -> str | None:
    source = (
        value.get("source_file")
        or value.get("sourceFile")
        or value.get("source_file_start")
        or value.get("sourceFileStart")
    )
    if source is None:
        return None
    line = value.get(
        "source_line", value.get("sourceLine", value.get("source_line_start", value.get("sourceLineStart", "?")))
    )
    column = value.get(
        "source_column",
        value.get("sourceColumn", value.get("source_column_start", value.get("sourceColumnStart", "?"))),
    )
    return f"{source}:{line}:{column}"


def _slang_procedure_kind(value: dict[str, Any]) -> str:
    return _canonical_operation(str(value.get("procedureKind", "procedural")))


def _slang_procedure(value: dict[str, Any]) -> RTLProceduralBlock:
    kind = _slang_procedure_kind(value)
    body = value.get("body") or value.get("statement") or value
    expressions = tuple(
        expression
        for node in _walk_json_objects(body)
        if _is_expression_node(node) and (expression := _slang_expression(node)) is not None
    )
    branches = _slang_branches(body)
    refs = tuple(sorted(set(_slang_signal_refs(body))))
    return RTLProceduralBlock(
        kind=kind,
        name=str(value["name"]) if value.get("name") else None,
        source_location=_slang_source_location(value),
        summary=kind,
        signal_refs=refs,
        expressions=_dedupe_expressions(expressions),
        branches=branches,
    )


def _slang_assignment(value: dict[str, Any], parameter_names: set[str]) -> RTLAssignment:
    assignment = value.get("assignment") or value.get("expression")
    left = assignment.get("left") if isinstance(assignment, dict) else None
    right = assignment.get("right") if isinstance(assignment, dict) else None
    lhs_refs = tuple(ref for ref in _slang_written_refs(left) if ref not in parameter_names)
    rhs_refs = tuple(ref for ref in _slang_signal_refs(right) if ref not in parameter_names)
    expressions = tuple(item for item in (_slang_expression(right), _slang_expression(left)) if item is not None)
    return RTLAssignment(
        kind="continuous",
        name=str(value["name"]) if value.get("name") else None,
        source_location=_slang_source_location(value),
        summary="ContinuousAssign",
        lhs_signals=lhs_refs,
        rhs_signals=rhs_refs,
        expressions=expressions,
    )


def _slang_procedural_assignments(
    value: dict[str, Any],
    parameter_names: set[str],
) -> tuple[RTLAssignment, ...]:
    assignments: list[RTLAssignment] = []
    for node in _walk_json_objects(value.get("body") or value):
        kind = str(node.get("kind", "")).lower()
        if kind not in {"assignment", "assignmentexpression", "nonblockingassignment"}:
            continue
        left = node.get("left") or node.get("lhs")
        right = node.get("right") or node.get("rhs")
        expressions = tuple(item for raw in (right, left) if (item := _slang_expression(raw)) is not None)
        assignments.append(
            RTLAssignment(
                kind="nonblocking" if "nonblocking" in kind or node.get("isNonBlocking") else "procedural",
                source_location=_slang_source_location(node),
                summary=str(node.get("kind")),
                lhs_signals=tuple(ref for ref in _slang_written_refs(left) if ref not in parameter_names),
                rhs_signals=tuple(ref for ref in _slang_signal_refs(right) if ref not in parameter_names),
                expressions=expressions,
            )
        )
    return tuple(assignments)


def _slang_signal_refs(value: object) -> tuple[str, ...]:
    refs: list[str] = []
    for item in _walk_json_objects(value):
        if item.get("kind") not in {"NamedValue", "HierarchicalValue", "MemberAccess"}:
            continue
        if item.get("constant") is not None:
            continue
        symbol = item.get("symbol") or item.get("name") or item.get("member")
        if not isinstance(symbol, str):
            continue
        name = _canonical_symbol_name(symbol)
        if name and name not in refs:
            refs.append(name)
    return tuple(refs)


def _slang_written_refs(value: object) -> tuple[str, ...]:
    if isinstance(value, dict) and value.get("kind") in {"ElementSelect", "RangeSelect", "MemberAccess"}:
        return _slang_signal_refs(value.get("value") or value.get("base"))[:1]
    return _slang_signal_refs(value)[:1]


def _slang_port(value: dict[str, Any], interface_array_ranges: dict[str, tuple[str, ...]] | None = None) -> RTLPort:
    if value.get("kind") == "InterfacePort":
        return RTLPort(
            name=str(value["name"]),
            direction="interface",
            data_type="interface",
            source_location=_slang_source_location(value),
            interface_name=_canonical_symbol_name(str(value.get("interfaceDef") or "")) or None,
            modport=str(value.get("modport")) if value.get("modport") else None,
            interface_direction="modport",
            unpacked_dimensions=(interface_array_ranges or {}).get(str(value["name"]), ()),
        )
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    type_kind = str(type_data.get("kind", ""))
    range_text = _type_range(type_data)
    interface = type_data.get("interface") or type_data.get("definition")
    modport = type_data.get("modport")
    return RTLPort(
        name=str(value["name"]),
        direction={"In": "input", "Out": "output", "InOut": "inout", "Ref": "ref"}.get(
            str(value.get("direction")), "unknown"
        ),
        data_type=type_kind,
        width=_type_width(type_data),
        signed=_type_signed(type_data),
        packed_range=range_text,
        source_location=_slang_source_location(value),
        interface_name=str(interface) if interface is not None else None,
        modport=str(modport) if modport is not None else None,
        interface_direction=str(value.get("direction")) if interface is not None else None,
        packed_dimensions=_type_dimensions(type_data, "packed"),
        unpacked_dimensions=_type_dimensions(type_data, "unpacked"),
    )


def _slang_parameter(value: dict[str, Any]) -> RTLParameter:
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    return RTLParameter(
        name=str(value["name"]),
        default_value=_canonical_constant(
            value.get("value") if value.get("value") is not None else _expression_constant(value.get("initializer"))
        ),
        data_type=str(type_data.get("kind")) if type_data.get("kind") is not None else None,
        width=_type_width(type_data),
        signed=_type_signed(type_data),
        local=bool(value.get("isLocal", False)),
        source_location=_slang_source_location(value),
    )


def _is_slang_type(value: dict[str, Any]) -> bool:
    return str(value.get("kind", "")) in {
        "TypeAlias",
        "Typedef",
        "EnumType",
        "StructType",
        "UnionType",
        "PackedStructType",
        "PackedUnionType",
    }


def _slang_type(value: dict[str, Any], symbol_index: dict[str, dict[str, Any]] | None = None) -> RTLType:
    raw_type = value.get("type") or value.get("target")
    resolved = _slang_link(raw_type, symbol_index or {}) if raw_type is not None else None
    type_data: dict[str, Any] = resolved if resolved is not None else value
    members = tuple(_json_dicts(type_data.get("members")))
    type_id = str(value.get("id") or value.get("name") or hashlib.sha256(repr(value).encode()).hexdigest()[:12])
    member_details = tuple(
        RTLTypeMember(
            name=str(item.get("name")),
            width=_resolved_slang_type_width(item.get("type"), symbol_index or {}),
            signed=_type_signed(_resolve_slang_type(item.get("type"), symbol_index or {})),
            packed_range=_type_range(_resolve_slang_type(item.get("type"), symbol_index or {})),
            bit_offset=int(item["bitOffset"]) if item.get("bitOffset") is not None else None,
            packed_dimensions=_type_dimensions(_resolve_slang_type(item.get("type"), symbol_index or {}), "packed"),
            unpacked_dimensions=_type_dimensions(_resolve_slang_type(item.get("type"), symbol_index or {}), "unpacked"),
            source_location=_slang_source_location(item),
        )
        for item in members
        if item.get("name") and item.get("kind") != "EnumValue"
    )
    type_width = _type_width(type_data)
    if type_width is None and member_details and all(item.width is not None for item in member_details):
        widths = tuple(item.width for item in member_details if item.width is not None)
        type_width = max(widths) if "Union" in str(type_data.get("kind")) else sum(widths)
    return RTLType(
        type_id=type_id,
        name=str(value.get("name")) if value.get("name") else None,
        kind=_canonical_operation(str(type_data.get("kind", value.get("kind", "type")))),
        width=type_width,
        signed=_type_signed(type_data),
        members=tuple(
            str(item.get("name")) for item in members if item.get("name") and item.get("kind") != "EnumValue"
        ),
        enum_values=tuple(
            str(item.get("name"))
            for item in _json_dicts(type_data.get("values") or type_data.get("members"))
            if item.get("kind") == "EnumValue" and item.get("name")
        ),
        source_location=_slang_source_location(value),
        member_details=member_details,
        packed_dimensions=_type_dimensions(type_data, "packed"),
        unpacked_dimensions=_type_dimensions(type_data, "unpacked"),
        package_name=str(value.get("package")) if value.get("package") else None,
    )


def _slang_global_types(value: object, symbol_index: dict[str, dict[str, Any]]) -> tuple[RTLType, ...]:
    result: list[RTLType] = []
    for owner in _walk_json_objects(value):
        owner_kind = str(owner.get("kind", ""))
        if owner_kind not in {"Package", "InstanceBody"}:
            continue
        owner_name = str(owner.get("name") or "")
        owner_members = _json_dicts(owner.get("members"))
        aliases = {str(item.get("name")) for item in owner_members if item.get("kind") in {"TypeAlias", "Typedef"}}
        for member in owner_members:
            if _is_slang_type(member):
                if (
                    member.get("kind") in {"EnumType", "PackedStructType", "PackedUnionType"}
                    and str(member.get("name")) in aliases
                ):
                    continue
                item = _slang_type(member, symbol_index)
                result.append(
                    RTLType(
                        **{
                            **item.__dict__,
                            "package_name": owner_name or item.package_name,
                        }
                    )
                )
            elif member.get("kind") == "Modport":
                modport_members = tuple(
                    RTLTypeMember(
                        name=str(port.get("name")),
                        width=_type_width(port.get("type")),
                        signed=_type_signed(port.get("type")),
                        packed_range=_type_range(port.get("type")),
                        bit_offset=(int(port["bitOffset"]) if port.get("bitOffset") is not None else None),
                        packed_dimensions=_type_dimensions(port.get("type"), "packed"),
                        unpacked_dimensions=_type_dimensions(port.get("type"), "unpacked"),
                        source_location=_slang_source_location(port),
                    )
                    for port in _json_dicts(member.get("members"))
                    if port.get("kind") == "ModportPort" and port.get("name")
                )
                directions = tuple(
                    f"{port.get('name')}:{str(port.get('direction', '')).lower()}"
                    for port in _json_dicts(member.get("members"))
                    if port.get("kind") == "ModportPort" and port.get("name")
                )
                result.append(
                    RTLType(
                        type_id=f"{owner_name}.{member.get('name')}",
                        name=str(member.get("name")),
                        kind="modport",
                        members=directions,
                        member_details=modport_members,
                        source_location=_slang_source_location(member),
                        package_name=owner_name,
                    )
                )
    return tuple(result)


def _resolve_slang_type(value: object, symbol_index: dict[str, dict[str, Any]]) -> object:
    linked = _slang_link(value, symbol_index)
    if linked is None:
        return value
    if linked.get("kind") in {"TypeAlias", "Typedef"}:
        return _resolve_slang_type(linked.get("target") or linked.get("type"), symbol_index)
    if linked.get("kind") == "EnumType" and isinstance(linked.get("baseType"), dict):
        return linked.get("baseType")
    return linked


def _resolved_slang_type_width(value: object, symbol_index: dict[str, dict[str, Any]]) -> int | None:
    resolved = _resolve_slang_type(value, symbol_index)
    if not isinstance(resolved, dict):
        return _type_width(resolved)
    kind = str(resolved.get("kind", ""))
    if kind == "EnumType":
        return _resolved_slang_type_width(resolved.get("baseType"), symbol_index)
    if kind in {"PackedStructType", "StructType", "PackedUnionType", "UnionType"}:
        widths = tuple(
            _resolved_slang_type_width(item.get("type"), symbol_index)
            for item in _json_dicts(resolved.get("members"))
            if item.get("kind") != "EnumValue"
        )
        if any(item is None for item in widths):
            return None
        known = tuple(item for item in widths if item is not None)
        return max(known, default=0) if "Union" in kind else sum(known)
    return _type_width(resolved)


def _slang_imports(members: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _canonical_symbol_name(str(item.get("package")))
                for item in members
                if item.get("kind") in {"Import", "WildcardImport"} and item.get("package")
            }
        )
    )


def _is_slang_memory(value: dict[str, Any]) -> bool:
    return value.get("kind") in {"Variable", "Net"} and bool(_type_dimensions(value.get("type"), "unpacked"))
