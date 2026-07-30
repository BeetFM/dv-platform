# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from dv_platform.core.models import (
    RTLExpression,
    RTLModule,
    RTLParameter,
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


def _domain_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                (
                    item.clock,
                    item.clock_edge,
                    item.reset,
                    item.reset_edge,
                    item.reset_active_low,
                    item.asynchronous_reset,
                )
                for item in module.control_domains
            ),
            key=repr,
        )
    )


def _property_signature(module: RTLModule) -> tuple[object, ...]:
    return tuple(
        sorted(
            [
                (
                    item.kind,
                    item.name,
                    item.concurrent,
                    item.clock,
                    item.clock_edge,
                    _expression_node_signature(item.disable_condition),
                    _expression_node_signature(item.body),
                    item.support_status,
                    tuple(item.unsupported_operators),
                )
                for item in module.property_details
            ],
            key=repr,
        )
    )


def _generate_signature(module: RTLModule) -> tuple[object, ...]:
    return tuple(
        sorted(
            [
                (
                    item.name,
                    "generate",
                    tuple(sorted(name.rsplit(".", 1)[-1] for name in item.instance_names)),
                    _expression_node_signature(item.condition),
                    True if item.selected is None else item.selected,
                    item.iteration_index,
                )
                for item in module.generate_scopes
            ],
            key=repr,
        )
    )


def _memory_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                item.name,
                item.element_width,
                item.depth,
                tuple(_canonical_range(value) for value in item.unpacked_dimensions),
                item.read_during_write,
            )
            for item in module.memories
        )
    )


def _canonical_operation(value: str | None) -> str:
    if not value:
        return ""
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    return _OPERATION_NAMES.get(compact, compact)


def _canonical_type_kind(value: str) -> str:
    kind = _canonical_operation(value)
    if "enum" in kind:
        return "enum"
    if "struct" in kind:
        return "struct"
    if "union" in kind:
        return "union"
    if "modport" in kind:
        return "modport"
    if "interface" in kind or "ifaceref" in kind:
        return "interface"
    return kind


def _canonical_symbol_name(value: str) -> str:
    stripped = value.strip()
    if " " in stripped and stripped.split(" ", 1)[0].isdigit():
        stripped = stripped.split(" ", 1)[1]
    return stripped.rsplit("::", 1)[-1]


def _canonical_constant(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    text = str(value).strip().replace("_", "").lower()
    match = re.fullmatch(r"(?:(\d+))?'([s]?)([bodh])([0-9a-fxz?]+)", text)
    if not match:
        return text
    width, signed, radix, digits = match.groups()
    if any(character in digits for character in "xz?"):
        return f"{width or ''}'{signed}{radix}{digits}"
    number = int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[radix])
    return f"{width or ''}:{'s' if signed else 'u'}:{number}"


def _canonical_parameter_constant(value: object) -> str | None:
    canonical = _canonical_constant(value)
    if canonical is None:
        return None
    normalized = re.fullmatch(r"(?:\d*):[su]:(-?\d+)", canonical)
    if normalized:
        return str(int(normalized.group(1)))
    if canonical.lstrip("-").isdigit():
        return str(int(canonical))
    return canonical


def _expression_constant(value: object) -> object:
    if not isinstance(value, dict):
        return None
    if value.get("constant") is not None:
        return value.get("constant")
    if str(value.get("kind", "")).endswith("Literal"):
        return value.get("value")
    return None


def _canonical_range(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.fullmatch(r"\[?\s*(-?\d+)\s*:\s*(-?\d+)\s*\]?", value)
    return f"[{int(match.group(1))}:{int(match.group(2))}]" if match else value.replace(" ", "")


def _canonical_specialization_id(name: str, parameters: tuple[RTLParameter, ...]) -> str:
    signature = "\0".join(
        (
            name,
            *(
                f"{item.name}={_canonical_parameter_constant(item.default_value)}"
                for item in parameters
                if not item.local
            ),
        )
    )
    return hashlib.sha256(signature.encode()).hexdigest()[:16]


def _type_range(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("range") or value.get("packedRange")
    if raw is not None:
        return _canonical_range(str(raw))
    dimensions = _type_dimensions(value, "packed")
    return dimensions[0] if dimensions else None


def _type_width(value: object) -> int | None:
    if isinstance(value, str):
        return None
    if not isinstance(value, dict) or not value:
        return None
    width = value.get("bitWidth") or value.get("width")
    if isinstance(width, int):
        return width
    kind = str(value.get("kind", ""))
    if kind == "EnumType":
        return _type_width(value.get("baseType"))
    if kind in {"PredefinedIntegerType", "IntegerType"}:
        name = str(value.get("name", "")).lower()
        return {"byte": 8, "shortint": 16, "int": 32, "integer": 32, "longint": 64}.get(name, 32)
    if kind in {"PackedStructType", "PackedUnionType", "StructType", "UnionType"}:
        widths = tuple(_type_width(item.get("type")) for item in _json_dicts(value.get("members")))
        known = tuple(item for item in widths if item is not None)
        if len(known) != len(widths):
            return None
        return max(known, default=0) if "Union" in kind else sum(known)
    range_width = _range_width(_type_range(value))
    element_width = _type_width(value.get("elementType"))
    if range_width is not None and element_width is not None:
        return range_width * element_width
    return range_width if range_width is not None else 1


def _type_signed(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "isSigned" in value:
        return bool(value.get("isSigned"))
    if value.get("kind") == "PredefinedIntegerType":
        return str(value.get("name", "")).lower() not in {"bit", "logic", "reg"}
    return _type_signed(value.get("elementType"))


def _type_dimensions(value: object, category: str) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    keys = (f"{category}Dimensions", f"{category}_dimensions")
    raw: object = None
    for key in keys:
        if key in value:
            raw = value[key]
            break
    explicit = (
        tuple(_canonical_range(str(item.get("range") if isinstance(item, dict) else item)) or "" for item in raw)
        if isinstance(raw, list)
        else ()
    )
    kind = str(value.get("kind", ""))
    is_dimension = (category == "packed" and kind in {"PackedArrayType", "PackedDimensionType"}) or (
        category == "unpacked" and kind in {"FixedSizeUnpackedArrayType", "UnpackedArrayType", "DynamicArrayType"}
    )
    own = (_canonical_range(str(value.get("range"))) or "",) if is_dimension and value.get("range") else ()
    nested = _type_dimensions(value.get("elementType"), category)
    return (*explicit, *own, *nested)


def _range_width(value: str | None) -> int | None:
    if value is None:
        return 1
    match = re.fullmatch(r"\[(-?\d+):(-?\d+)\]", value.strip())
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else None


def _product(values: tuple[int, ...]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def _is_expression_node(value: dict[str, Any]) -> bool:
    return str(value.get("kind", "")) in _SLANG_EXPRESSION_KINDS


def _add_gap(gaps: dict[str, set[str]], capability: str, reason: str) -> None:
    gaps.setdefault(capability, set()).add(reason)


def _collect_slang_capability_gaps(value: object, gaps: dict[str, set[str]]) -> None:
    for node in _walk_json_objects(value):
        kind = str(node.get("kind", ""))
        location = _slang_source_location(node)
        prefix = f"{location}: " if location else ""
        if kind in _SLANG_UNSUPPORTED_EXPRESSION_KINDS:
            _add_gap(gaps, CAPABILITY_EXPRESSIONS, f"{prefix}unsupported expression {kind}")
        if kind in {"PatternCase", "RandCase", "RandSequence"}:
            _add_gap(gaps, CAPABILITY_BRANCHES, f"{prefix}unsupported branch {kind}")
        if kind in {"AssociativeArrayType", "QueueType", "VirtualInterfaceType"}:
            _add_gap(gaps, CAPABILITY_TYPES, f"{prefix}unsupported type {kind}")
        if kind in {"CheckerInstance", "PrimitiveInstance"}:
            _add_gap(gaps, CAPABILITY_HIERARCHY, f"{prefix}unsupported instance {kind}")
        if kind in {"GenerateBlock", "GenerateBlockArray"}:
            if kind == "GenerateBlock" and not node.get("name") and not node.get("branchKind"):
                _add_gap(
                    gaps,
                    CAPABILITY_GENERATE_SCOPES,
                    f"{prefix}generate block has no stable name or branch identity",
                )


def _walk_expressions(value: RTLExpression) -> tuple[RTLExpression, ...]:
    return (value, *(item for child in value.children for item in _walk_expressions(child)))


def _dedupe_expressions(values: tuple[RTLExpression, ...]) -> tuple[RTLExpression, ...]:
    seen: set[str] = set()
    result: list[RTLExpression] = []
    for value in values:
        key = repr(_expression_node_signature(value))
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _first_signal(value: object) -> str | None:
    refs = _slang_signal_refs(value)
    return refs[0] if refs else None


def _event_edge(value: object) -> str | None:
    for item in _walk_json_objects(value):
        edge = str(item.get("edge", item.get("kind", ""))).lower()
        if "posedge" in edge:
            return "pos"
        if "negedge" in edge:
            return "neg"
    return None
