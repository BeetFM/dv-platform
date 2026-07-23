# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dv_platform.core.models import (
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLModule,
    RTLProceduralBlock,
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


def _slang_source_generate_scopes(
    source_files: tuple[Path, ...],
) -> dict[str, tuple[RTLGenerateScope, ...]]:
    result: dict[str, list[RTLGenerateScope]] = {}
    module_pattern = re.compile(r"\bmodule\s+(?P<name>[A-Za-z_$][\w$]*)\b(?P<body>.*?)\bendmodule\b", re.S)
    patterns = (
        ("conditional", re.compile(r"\bif\s*\((?P<condition>[^)]*)\)\s*begin\s*:\s*(?P<name>[A-Za-z_$][\w$]*)")),
        (
            "loop",
            re.compile(r"\bfor\s*\([^;]*;(?P<condition>[^;]*);[^)]*\)\s*begin\s*:\s*(?P<name>[A-Za-z_$][\w$]*)"),
        ),
    )
    for path in source_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for module_match in module_pattern.finditer(text):
            module = module_match.group("name")
            body = module_match.group("body")
            body_offset = module_match.start("body")
            for kind, pattern in patterns:
                for match in pattern.finditer(body):
                    name = match.group("name")
                    location_offset = body_offset + match.start()
                    line = text.count("\n", 0, location_offset) + 1
                    column = location_offset - text.rfind("\n", 0, location_offset)
                    result.setdefault(module, []).append(
                        RTLGenerateScope(
                            scope_id=f"source:{module}:{name}",
                            name=name,
                            kind=kind,
                            source_location=f"{path}:{line}:{column}",
                            condition=_slang_source_expression(match.group("condition")),
                        )
                    )
    return {name: tuple(items) for name, items in result.items()}


def _slang_source_expression(value: str) -> RTLExpression:
    text = value.strip()
    if text.startswith("!"):
        return RTLExpression("not", children=(_slang_source_expression(text[1:]),))
    for token, operation in (
        ("<=", "lessequal"),
        (">=", "greaterequal"),
        ("==", "equal"),
        ("!=", "notequal"),
        ("<", "lessthan"),
        (">", "greaterthan"),
    ):
        if token in text:
            left, right = text.split(token, 1)
            return RTLExpression(
                operation,
                children=(_slang_source_expression(left), _slang_source_expression(right)),
            )
    if text.lstrip("-").isdigit():
        return RTLExpression("literal", value=str(int(text)))
    if re.fullmatch(r"[A-Za-z_$][\w$]*", text):
        return RTLExpression("ref", name=text)
    return RTLExpression("unsupported", value=text)


def _slang_control_domain(
    node: dict[str, Any],
    block: RTLProceduralBlock,
) -> RTLControlDomain | None:
    if not block.kind.startswith("always"):
        return None
    event_root = node.get("timing") or node.get("eventControl") or node
    events: list[tuple[str, str]] = []
    for item in _walk_json_objects(event_root):
        raw_edge = str(item.get("edge", item.get("edgeKind", item.get("kind", "")))).lower()
        if "posedge" in raw_edge or "positive" in raw_edge:
            edge = "pos"
        elif "negedge" in raw_edge or "negative" in raw_edge:
            edge = "neg"
        else:
            continue
        refs = _slang_signal_refs(item)
        if refs and (refs[0], edge) not in events:
            events.append((refs[0], edge))
    if not events:
        return None
    clock, clock_edge = events[0]
    reset = events[1][0] if len(events) > 1 else None
    reset_edge = events[1][1] if len(events) > 1 else None
    reset_active_low: bool | None = reset_edge == "neg" if reset_edge else None
    if reset is None:
        for branch in _slang_branches(node):
            refs = _slang_signal_refs_from_expression(branch.condition)
            candidate = next(
                (item for item in refs if item != clock and re.search(r"(?:^|_)(?:rst|reset)(?:_|$)", item, re.I)),
                None,
            )
            if candidate is not None:
                reset = candidate
                reset_active_low = _expression_is_active_low(branch.condition)
                break
    return RTLControlDomain(
        domain_id=f"{clock}:{reset or 'none'}",
        clock=clock,
        clock_edge=clock_edge,
        reset=reset,
        reset_edge=reset_edge,
        reset_active_low=reset_active_low,
        asynchronous_reset=len(events) > 1,
        source_location=block.source_location,
    )


def _slang_signal_refs_from_expression(value: RTLExpression | None) -> tuple[str, ...]:
    if value is None:
        return ()
    refs: list[str] = []
    for item in _walk_expressions(value):
        if item.name and item.kind in {"ref", "member"} and item.name not in refs:
            refs.append(item.name)
    return tuple(refs)


def _expression_is_active_low(value: RTLExpression | None) -> bool | None:
    if value is None:
        return None
    if value.kind in {"logicalnot", "bitwisenot", "not"}:
        return True
    return False


def _modules_by_specialization(modules: tuple[RTLModule, ...]) -> dict[tuple[str, str], tuple[RTLModule, ...]]:
    grouped: dict[tuple[str, str], list[RTLModule]] = {}
    for module in modules:
        key = (module.original_name or module.name, _specialization_signature(module))
        grouped.setdefault(key, []).append(module)
    return {
        key: tuple(sorted(items, key=lambda item: (item.elaborated_name or "", item.name)))
        for key, items in grouped.items()
    }


def _specialization_signature(module: RTLModule) -> str:
    parameters = tuple(
        sorted(
            (parameter.name, _canonical_parameter_constant(parameter.default_value))
            for parameter in module.parameter_details
            if not parameter.local
        )
    )
    return ",".join(f"{name}={value}" for name, value in parameters) if parameters else "default"


def _display_specialization(module: str, specialization: str) -> str:
    return module if specialization == "default" else f"{module}[{specialization}]"


def _compare_module(
    primary: RTLModule,
    reference: RTLModule,
    specialization: str,
    capabilities: frozenset[str],
    required_capabilities: frozenset[str],
    nonrequired_severity: str,
    issues: list[SemanticCrossCheckIssue],
) -> None:
    comparisons: tuple[tuple[str, str, object, object], ...] = (
        (CAPABILITY_PORTS, "ports", tuple(sorted(primary.ports)), tuple(sorted(reference.ports))),
        (CAPABILITY_PARAMETERS, "parameters", _parameter_signature(primary), _parameter_signature(reference)),
        (CAPABILITY_HIERARCHY, "instances", _instance_signature(primary), _instance_signature(reference)),
        (CAPABILITY_TYPES, "type_details", _type_signature(primary), _type_signature(reference)),
        (CAPABILITY_PORTS, "port_details", _port_signature(primary), _port_signature(reference)),
        (CAPABILITY_ASSIGNMENTS, "assignments", _assignment_signature(primary), _assignment_signature(reference)),
        (
            CAPABILITY_PROCEDURAL_BLOCKS,
            "procedural_blocks",
            _procedural_signature(primary),
            _procedural_signature(reference),
        ),
        (CAPABILITY_EXPRESSIONS, "expressions", _expression_signature(primary), _expression_signature(reference)),
        (CAPABILITY_BRANCHES, "branches", _branch_signature(primary), _branch_signature(reference)),
        (CAPABILITY_CONTROL_DOMAINS, "control_domains", _domain_signature(primary), _domain_signature(reference)),
        (CAPABILITY_PROPERTIES, "properties", _property_signature(primary), _property_signature(reference)),
        (CAPABILITY_IMPORTS, "imports", tuple(sorted(primary.imports)), tuple(sorted(reference.imports))),
        (CAPABILITY_GENERATE_SCOPES, "generate_scopes", _generate_signature(primary), _generate_signature(reference)),
        (CAPABILITY_MEMORIES, "memories", _memory_signature(primary), _memory_signature(reference)),
    )
    for capability, field, left, right in comparisons:
        if capability in capabilities:
            _compare_value(
                primary,
                reference,
                specialization,
                capability,
                field,
                left,
                right,
                "error" if capability in required_capabilities else nonrequired_severity,
                issues,
            )


def _compare_value(
    primary_module: RTLModule,
    reference_module: RTLModule,
    specialization: str,
    capability: str,
    field: str,
    primary: object,
    reference: object,
    severity: str,
    issues: list[SemanticCrossCheckIssue],
) -> None:
    if primary == reference:
        return
    issues.append(
        SemanticCrossCheckIssue(
            primary_module.original_name or primary_module.name,
            field,
            repr(primary),
            repr(reference),
            capability=capability,
            severity=severity,
            specialization=specialization,
            primary_evidence=primary_module.ast_refs,
            reference_evidence=reference_module.ast_refs,
            primary_location=_module_field_location(primary_module, field),
            reference_location=_module_field_location(reference_module, field),
        )
    )


def _module_field_location(module: RTLModule, field: str) -> str | None:
    values: tuple[object, ...]
    if field == "port_details":
        values = module.port_details
    elif field == "assignments":
        values = module.assignment_details
    elif field == "procedural_blocks":
        values = module.procedural_block_details
    elif field == "properties":
        values = module.property_details
    else:
        values = ()
    for value in values:
        location = getattr(value, "source_location", None)
        if isinstance(location, str):
            return location
    return str(module.source) if module.source is not None else None


def _port_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                port.name,
                port.direction.lower(),
                port.width if port.width is not None else 1,
                bool(port.signed),
                port.interface_name,
                port.modport,
                port.interface_direction,
                tuple(_canonical_range(item) for item in port.packed_dimensions),
                tuple(_canonical_range(item) for item in port.unpacked_dimensions),
            )
            for port in module.port_details
        )
    )


def _parameter_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                item.name,
                _canonical_parameter_constant(item.default_value),
                item.width,
                bool(item.signed),
                bool(item.local),
            )
            for item in module.parameter_details
        )
    )


def _instance_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    if not module.instance_details:
        return tuple(sorted((item, None, (), ()) for item in module.instances))
    return tuple(
        sorted(
            (
                item.name,
                item.module_name,
                tuple(
                    sorted(
                        (binding.name, _canonical_parameter_constant(binding.value))
                        for binding in item.parameter_bindings
                    )
                ),
                tuple(
                    sorted(
                        (
                            connection.port_name,
                            tuple(sorted(connection.signal_refs)),
                            _expression_node_signature(connection.expression),
                        )
                        for connection in item.connections
                    )
                ),
            )
            for item in module.instance_details
        )
    )


def _assignment_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                (
                    _canonical_assignment_kind(item.kind),
                    tuple(sorted(item.lhs_signals)),
                    tuple(sorted(item.rhs_signals)),
                    tuple(_expression_node_signature(expression) for expression in item.expressions),
                )
                for item in module.assignment_details
            ),
            key=repr,
        )
    )


def _procedural_signature(module: RTLModule) -> tuple[str, ...]:
    return tuple(sorted(_canonical_procedure_kind(item.kind) for item in module.procedural_block_details))


def _canonical_assignment_kind(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    if compact in {"procedural", "assignment", "assign"}:
        return "assign"
    if compact in {"nonblocking", "nonblockingassignment", "assigndly"}:
        return "assigndly"
    kind = _canonical_operation(value)
    if kind in {"continuous", "contassign"}:
        return "contassign"
    if kind in {"procedural", "assignment", "assign"}:
        return "assign"
    if kind in {"nonblocking", "nonblockingassignment", "assigndly"}:
        return "assigndly"
    return kind


def _canonical_procedure_kind(value: str) -> str:
    kind = _canonical_operation(value)
    return "always" if kind in {"always", "alwaysff", "alwayscomb", "alwayslatch", "alwayslat"} else kind


def _type_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                _canonical_symbol_name(item.name) if item.name else None,
                _canonical_type_kind(item.kind),
                item.width,
                bool(item.signed),
                tuple(item.members),
                tuple(item.enum_values),
                tuple(
                    (
                        member.name,
                        member.width,
                        bool(member.signed),
                        _canonical_range(member.packed_range),
                        member.bit_offset,
                        tuple(_canonical_range(value) for value in member.packed_dimensions),
                        tuple(_canonical_range(value) for value in member.unpacked_dimensions),
                    )
                    for member in item.member_details
                ),
                tuple(_canonical_range(value) for value in item.packed_dimensions),
                tuple(_canonical_range(value) for value in item.unpacked_dimensions),
                item.package_name,
            )
            for item in module.type_details
            if item.members
            or item.enum_values
            or item.package_name is not None
            or any(
                token in _canonical_operation(item.kind)
                for token in ("enum", "struct", "union", "interface", "modport")
            )
        )
    )


def _expression_signature(module: RTLModule) -> tuple[object, ...]:
    roots = tuple(
        expression for assignment in module.assignment_details for expression in assignment.expressions
    ) + tuple(expression for block in module.procedural_block_details for expression in block.expressions)
    return tuple(sorted((_expression_node_signature(item) for item in roots), key=repr))


def _expression_node_signature(expression: RTLExpression | None) -> object:
    if expression is None:
        return None
    return (
        _canonical_operation(expression.kind),
        expression.name,
        _canonical_constant(expression.value),
        expression.width,
        expression.signed,
        _canonical_range(expression.packed_range),
        _canonical_operation(expression.cast_kind) if expression.cast_kind else None,
        tuple(_expression_node_signature(item) for item in expression.children),
    )


def _branch_signature(module: RTLModule) -> tuple[object, ...]:
    return tuple(
        sorted(
            [
                (
                    _canonical_operation(branch.kind),
                    _expression_node_signature(branch.condition),
                    tuple(_expression_node_signature(item) for item in branch.labels),
                    branch.is_default,
                    branch.mutually_exclusive,
                )
                for block in module.procedural_block_details
                for branch in block.branches
            ],
            key=repr,
        )
    )
