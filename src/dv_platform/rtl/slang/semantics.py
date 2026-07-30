# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from dv_platform.core.models import (
    RTLBranch,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLMemory,
    RTLMemoryAccess,
    RTLProperty,
)

SEMANTIC_CROSSCHECK_API_VERSION = 3
SEMANTIC_CROSSCHECK_SCHEMA_VERSION = 3
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


def _slang_memory(value: dict[str, Any], symbol_index: dict[str, dict[str, Any]] | None = None) -> RTLMemory:
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    dimensions = _type_dimensions(type_data, "unpacked")
    depths = tuple(_range_width(item) for item in dimensions)
    depth = (
        None if any(item is None for item in depths) else _product(tuple(item for item in depths if item is not None))
    )
    element_width = _resolved_slang_type_width(_slang_memory_element_type(type_data), symbol_index or {})
    return RTLMemory(
        name=str(value.get("name")),
        element_width=element_width,
        depth=depth,
        address_width=(depth - 1).bit_length() if depth and depth > 1 else 1,
        source_location=_slang_source_location(value),
        unpacked_dimensions=dimensions,
    )


def _slang_memory_element_type(value: object) -> object:
    current = value
    while isinstance(current, dict) and str(current.get("kind")) in {
        "FixedSizeUnpackedArrayType",
        "UnpackedArrayType",
    }:
        current = current.get("elementType")
    return current


def _slang_memory_accesses(
    members: tuple[dict[str, Any], ...],
    memories: tuple[RTLMemory, ...],
    domains: tuple[RTLControlDomain, ...],
) -> tuple[RTLMemoryAccess, ...]:
    memory_names = {item.name for item in memories}
    result: list[RTLMemoryAccess] = []
    for member in members:
        if member.get("kind") == "ProceduralBlock":
            _visit_memory_access(member.get("body"), True, (), memory_names, domains, result)
        elif member.get("kind") == "ContinuousAssign":
            _visit_memory_access(member.get("assignment"), False, (), memory_names, domains, result)
    return tuple(result)


def _visit_memory_access(
    value: object,
    synchronous: bool,
    enables: tuple[str, ...],
    memory_names: set[str],
    domains: tuple[RTLControlDomain, ...],
    result: list[RTLMemoryAccess],
) -> None:
    if isinstance(value, list | tuple):
        for child in value:
            _visit_memory_access(child, synchronous, enables, memory_names, domains, result)
        return
    if not isinstance(value, dict):
        return
    kind = str(value.get("kind", ""))
    if kind == "Assignment":
        _record_memory_access(value, synchronous, enables, memory_names, domains, result)
        return
    nested_enables = enables
    if kind == "Conditional":
        conditions = _json_dicts(value.get("conditions"))
        condition_refs = (
            ref for condition in conditions for ref in _slang_signal_refs(condition.get("expr") or condition)
        )
        nested_enables = tuple(dict.fromkeys((*enables, *condition_refs)))
        for key in ("ifTrue", "ifFalse"):
            _visit_memory_access(value.get(key), synchronous, nested_enables, memory_names, domains, result)
        return
    for child in value.values():
        _visit_memory_access(child, synchronous, nested_enables, memory_names, domains, result)


def _record_memory_access(
    node: dict[str, Any],
    synchronous: bool,
    enables: tuple[str, ...],
    memory_names: set[str],
    domains: tuple[RTLControlDomain, ...],
    result: list[RTLMemoryAccess],
) -> None:
    left, right = node.get("left"), node.get("right")
    for kind, memory, selected, data in (
        ("write", _selected_memory(left, memory_names), left, right),
        ("read", _selected_memory(right, memory_names), right, left),
    ):
        if memory is None:
            continue
        location = _slang_source_location(node)
        result.append(
            RTLMemoryAccess(
                access_id=f"{memory}:{kind}:{location or len(result)}",
                memory=memory,
                kind=kind,
                address_signals=_slang_signal_refs(_slang_select_address(selected)),
                data_signals=tuple(ref for ref in _slang_signal_refs(data) if ref != memory),
                enable_signals=enables,
                domain_id=domains[0].domain_id if synchronous and domains else None,
                synchronous=synchronous,
                source_location=location,
            )
        )


def _selected_memory(value: object, names: set[str]) -> str | None:
    if not isinstance(value, dict) or value.get("kind") not in {"ElementSelect", "RangeSelect"}:
        return None
    refs = _slang_signal_refs(value.get("value") or value.get("base"))
    return next((item for item in refs if item in names), None)


def _slang_select_address(value: object) -> object:
    if not isinstance(value, dict):
        return None
    return value.get("selector") or value.get("index") or value.get("left")


def _slang_expression(value: object) -> RTLExpression | None:
    if not isinstance(value, dict):
        return None
    raw_kind = str(value.get("kind", "unsupported"))
    kind = _slang_expression_kind(raw_kind, value.get("op"))
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    children = _slang_expression_children(value)
    literal = value.get("constant")
    if literal is None and raw_kind.lower().endswith("literal"):
        literal = value.get("value")
    symbol = value.get("symbol") or value.get("name") or value.get("member")
    if raw_kind in {"NamedValue", "HierarchicalValue"} and value.get("constant") is not None:
        kind = "literal"
        symbol = None
        literal = value.get("constant")
    if raw_kind == "SequenceConcat":
        children = tuple(
            RTLExpression(
                kind="delay",
                value=f"{item.get('min')}:{item.get('max')}",
                source_location=_slang_source_location(item.get("sequence") or item),
                children=tuple(
                    expression for expression in (_slang_expression(item.get("sequence")),) if expression is not None
                ),
            )
            for item in _json_dicts(value.get("elements"))
        )
    width = _type_width(type_data)
    signed = _type_signed(type_data) if type_data else None
    determination = str(value.get("determination", "")).lower()
    if determination not in {"self", "context"}:
        determination = "context" if kind == "cast" else "self" if kind in {"literal", "ref"} else "unknown"
    context_type = str(value["contextType"]) if value.get("contextType") is not None else None
    if context_type is None and kind == "cast":
        context_type = _slang_type_identity(type_data)
    truncation = str(value.get("truncation", "")).lower()
    if truncation not in {"yes", "no"}:
        operand_width = children[0].width if kind == "cast" and children else None
        truncation = (
            "yes"
            if width is not None and operand_width is not None and width < operand_width
            else "no"
            if width is not None and operand_width is not None
            else "unknown"
        )
    unknown_bits = str(value.get("unknownBits", "")).lower()
    if unknown_bits not in {"present", "absent"}:
        unknown_bits = _slang_unknown_bit_state(kind, literal, type_data)
    return RTLExpression(
        kind=kind,
        name=_canonical_symbol_name(str(symbol)) if symbol is not None else None,
        value=_canonical_constant(literal),
        source_location=_slang_source_location(value),
        children=children,
        width=width,
        signed=signed,
        determination=determination,
        context_type=context_type,
        cast_kind=(
            str(value.get("conversionKind") or value.get("castKind") or type_data.get("name") or "implicit")
            if kind == "cast"
            else None
        ),
        truncation=truncation,
        unknown_bits=unknown_bits,
        packed_range=_type_range(type_data),
        frontend_identity="slang",
        specialization_identity=(str(value["specialization"]) if value.get("specialization") is not None else None),
    )


def _slang_type_identity(type_data: dict[str, Any]) -> str | None:
    """Describe the exact evaluated type emitted by Slang without re-evaluating it."""

    name = str(type_data.get("name") or "").strip()
    element = type_data.get("elementType")
    if not name and isinstance(element, dict):
        name = str(element.get("name") or element.get("kind") or "").strip()
        if _type_signed(type_data):
            name = f"{name} signed"
    packed_range = _type_range(type_data)
    identity = " ".join(item for item in (name, packed_range) if item)
    return identity or str(type_data.get("kind") or "").strip() or None


def _slang_unknown_bit_state(kind: str, literal: object, type_data: dict[str, Any]) -> str:
    if kind == "literal" and literal is not None:
        text = str(literal).lower()
        return "present" if "x" in text or "z" in text or "?" in text else "absent"
    current: object = type_data
    while isinstance(current, dict):
        if str(current.get("name") or "").lower() == "bit":
            return "absent"
        current = current.get("elementType")
    return "unknown"


def _slang_expression_kind(raw_kind: str, operation: object) -> str:
    if raw_kind in {"Conversion", "ConversionExpression", "Cast"}:
        return "cast"
    if raw_kind in {"ConditionalOp", "ConditionalExpression"}:
        return "cond"
    if raw_kind in {"NamedValue", "HierarchicalValue", "MemberAccess"}:
        return "ref" if raw_kind != "MemberAccess" else "member"
    if raw_kind.endswith("Literal"):
        return "literal"
    return _canonical_operation(str(operation or raw_kind))


def _slang_expression_children(value: dict[str, Any]) -> tuple[RTLExpression, ...]:
    singular = (
        "operand",
        "left",
        "right",
        "predicate",
        "condition",
        "expr",
        "trueExpr",
        "falseExpr",
        "value",
        "selector",
        "base",
        "index",
    )
    child_values: list[object] = [value[key] for key in singular if isinstance(value.get(key), dict)]
    for key in ("operands", "elements", "parts", "arguments", "conditions"):
        child_values.extend(
            child.get("expr") or child.get("sequence") or child for child in _json_dicts(value.get(key))
        )
    return tuple(item for child in child_values if (item := _slang_expression(child)) is not None)


def _slang_branches(value: object) -> tuple[RTLBranch, ...]:
    branches: list[RTLBranch] = []
    for node in _walk_json_objects(value):
        kind = str(node.get("kind", "")).lower()
        if kind in {"if", "ifstatement", "conditionalstatement", "conditional"}:
            conditions = _json_dicts(node.get("conditions"))
            condition_value = (
                conditions[0].get("expr") if conditions else node.get("condition") or node.get("predicate")
            )
            branches.append(
                RTLBranch(
                    "if",
                    _slang_source_location(node),
                    _slang_expression(condition_value),
                    mutually_exclusive=True,
                )
            )
        elif kind in {"case", "casestatement", "casez", "casex"}:
            condition = str(node.get("condition", "Normal"))
            case_kind = {
                "Normal": "case",
                "WildcardJustZ": "casez",
                "WildcardXOrZ": "casex",
                "Inside": "caseinside",
            }.get(condition, str(node.get("caseKind", kind)).lower())
            exclusive = True if case_kind == "case" or node.get("unique") or node.get("priority") else None
            selector = _slang_expression(node.get("expr") or node.get("expression") or node.get("selector"))
            for item in _json_dicts(node.get("items")):
                labels = tuple(
                    label
                    for raw in _json_dicts(item.get("expressions") or item.get("labels") or item.get("expressions"))
                    if (label := _slang_expression(raw)) is not None
                )
                branches.append(
                    RTLBranch(
                        case_kind,
                        _slang_source_location(item),
                        selector,
                        labels,
                        bool(item.get("isDefault", False) or not labels),
                        exclusive,
                    )
                )
            default = node.get("defaultCase")
            if default is not None:
                branches.append(
                    RTLBranch(
                        case_kind,
                        _slang_source_location(default) if isinstance(default, dict) else _slang_source_location(node),
                        selector,
                        (),
                        True,
                        exclusive,
                    )
                )
    return tuple(branches)


def _slang_properties(members: tuple[dict[str, Any], ...]) -> tuple[RTLProperty, ...]:
    properties: list[RTLProperty] = []
    consumed: set[int] = set()
    for wrapper in _walk_json_objects(members):
        body = wrapper.get("body")
        if not isinstance(body, dict) or str(body.get("kind", "")).lower() not in _PROPERTY_KINDS:
            continue
        consumed.add(id(body))
        label = wrapper.get("block") or wrapper.get("name")
        properties.append(_slang_property(body, _canonical_symbol_name(str(label)) if label else None))
    for node in _walk_json_objects(members):
        if id(node) in consumed or str(node.get("kind", "")).lower() not in _PROPERTY_KINDS:
            continue
        properties.append(_slang_property(node))
    return tuple(properties)


def _slang_property(value: dict[str, Any], name: str | None = None) -> RTLProperty:
    raw_kind = str(value.get("kind", "assert")).lower()
    assertion_kind = str(value.get("assertionKind", ""))
    kind_text = f"{raw_kind} {assertion_kind}".lower()
    kind = "cover" if "cover" in kind_text else "assume" if "assume" in kind_text else "assert"
    concurrent = "concurrent" in raw_kind or "property" in raw_kind
    spec = value.get("propertySpec") or value.get("property") or value.get("expression")
    if not isinstance(spec, dict):
        spec = value.get("cond") or value.get("condition")
    clock_node: object = None
    disable: object = None
    body_node = spec
    if isinstance(body_node, dict) and body_node.get("kind") == "Clocking":
        clock_node = body_node.get("clocking")
        body_node = body_node.get("expr")
    if isinstance(body_node, dict) and body_node.get("kind") == "DisableIff":
        disable = body_node.get("condition")
        body_node = body_node.get("expr")
    body = _slang_expression(body_node)
    known_property_nodes = {
        "Binary",
        "Clocking",
        "DisableIff",
        "Simple",
        "SequenceConcat",
        "Unary",
        "StrongWeak",
        "FirstMatch",
        "Conditional",
        "Parenthesized",
    }
    unsupported = tuple(
        sorted(
            {
                str(item.get("kind"))
                for item in _walk_json_objects(spec)
                if _looks_like_property_expression(item) and str(item.get("kind")) not in known_property_nodes
            }
        )
    )
    return RTLProperty(
        kind,
        name or (str(value.get("name")) if value.get("name") else None),
        concurrent=concurrent,
        clock=_first_signal(clock_node or value.get("clocking") or value.get("clock")),
        clock_edge=_event_edge(clock_node or value.get("clocking") or value.get("clock")),
        disable_condition=_slang_expression(disable or value.get("disableCondition") or value.get("disable")),
        body=body,
        source_location=_slang_source_location(value),
        support_status="unsupported" if unsupported or body is None else "normalized",
        unsupported_operators=unsupported,
    )


def _looks_like_property_expression(value: dict[str, Any]) -> bool:
    kind = str(value.get("kind", ""))
    return kind in {
        "Binary",
        "Clocking",
        "DisableIff",
        "Simple",
        "SequenceConcat",
        "Unary",
        "StrongWeak",
        "FirstMatch",
        "Conditional",
        "Parenthesized",
        "Intersect",
        "Throughout",
        "Within",
        "Abort",
        "Repetition",
    }


def _slang_generate_scope(value: dict[str, Any]) -> RTLGenerateScope:
    name = str(value.get("name") or value.get("scope") or "generate")
    condition = _slang_expression(value.get("condition") or value.get("selector") or value.get("stopExpression"))
    selected = value.get("selected")
    if not isinstance(selected, bool) and "isUninstantiated" in value:
        selected = not bool(value.get("isUninstantiated"))
    index = value.get("index")
    if not isinstance(index, int):
        index = _slang_generate_index(value)
    return RTLGenerateScope(
        scope_id=str(value.get("id") or name),
        name=name,
        kind=_canonical_operation(str(value.get("branchKind") or value.get("kind", "generate"))),
        source_location=_slang_source_location(value),
        instance_names=tuple(
            str(item.get("name"))
            for item in _walk_json_objects(value.get("members"))
            if item.get("kind") == "Instance" and item.get("name")
        ),
        condition=condition,
        selected=bool(selected) if isinstance(selected, bool) else None,
        iteration_index=int(index) if isinstance(index, int) else None,
    )


def _slang_generate_index(value: dict[str, Any]) -> int | None:
    index_parameter = next(
        (item for item in _json_dicts(value.get("members")) if item.get("kind") == "Parameter" and item.get("isLocal")),
        None,
    )
    if index_parameter is None:
        return None
    raw_index = _canonical_constant(index_parameter.get("value"))
    return int(raw_index) if raw_index is not None and raw_index.lstrip("-").isdigit() else None


def _slang_generate_scopes(members: tuple[dict[str, Any], ...]) -> tuple[RTLGenerateScope, ...]:
    scopes: list[RTLGenerateScope] = []
    for item in members:
        kind = str(item.get("kind", ""))
        if kind == "GenerateBlockArray":
            parent = _slang_generate_scope(item)
            scopes.append(replace(parent, selected=True))
            base = str(item.get("name") or "generate")
            for block in _json_dicts(item.get("members")):
                if block.get("kind") != "GenerateBlock":
                    continue
                index = _slang_generate_index(block)
                child = _slang_generate_scope(block)
                scopes.append(
                    replace(
                        child,
                        name=f"{base}[{index}]" if index is not None else base,
                        scope_id=f"{parent.scope_id}[{index}]" if index is not None else child.scope_id,
                    )
                )
        elif kind == "GenerateBlock":
            scopes.append(_slang_generate_scope(item))
    return tuple(scopes)


def _merge_slang_generate_scopes(
    elaborated: tuple[RTLGenerateScope, ...],
    declared: tuple[RTLGenerateScope, ...],
) -> tuple[RTLGenerateScope, ...]:
    by_name = {item.name: item for item in elaborated}
    for declaration in declared:
        current = by_name.get(declaration.name)
        if current is None:
            by_name[declaration.name] = replace(declaration, selected=False)
        elif current.condition is None:
            by_name[declaration.name] = replace(
                current,
                condition=declaration.condition,
                selected=True if current.selected is None else current.selected,
            )
    ordered = [by_name[item.name] for item in elaborated]
    ordered.extend(by_name[item.name] for item in declared if item.name not in {value.name for value in elaborated})
    return tuple(ordered)
