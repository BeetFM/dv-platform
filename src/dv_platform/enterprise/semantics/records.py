# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Versioned, fail-closed semantic facts interchange."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dv_platform.core.models import (
    RTLAssignment,
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
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
)

SEMANTIC_MANIFEST_SCHEMA_VERSION = 3
MIN_READABLE_SEMANTIC_MANIFEST_SCHEMA_VERSION = 0
MAX_SEMANTIC_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_EXPRESSION_DEPTH = 64
SUPPORTED_LANGUAGES = frozenset({"systemverilog", "verilog", "vhdl"})
SUPPORTED_STANDARDS = {
    "systemverilog": frozenset({"1800-2005", "1800-2009", "1800-2012", "1800-2017", "1800-2023"}),
    "verilog": frozenset({"1364-1995", "1364-2001", "1364-2005"}),
    "vhdl": frozenset({"1076-1987", "1076-1993", "1076-2000", "1076-2002", "1076-2008", "1076-2019"}),
}
DESIGN_UNIT_KINDS = {
    "systemverilog": frozenset({"module", "interface", "program", "package", "checker"}),
    "verilog": frozenset({"module", "primitive", "configuration"}),
    "vhdl": frozenset({"entity", "architecture", "package", "configuration", "context"}),
}
COMPLETENESS_STATES = frozenset({"complete", "partial", "unsupported", "not_applicable"})
SEMANTIC_CATEGORIES = (
    "lexical_preprocessing",
    "libraries_compilation_units",
    "design_units",
    "declarations",
    "types",
    "expressions",
    "statements",
    "subprograms",
    "hierarchy",
    "elaboration",
    "parameters_generics",
    "ports",
    "packages_imports",
    "interfaces_modports",
    "classes_randomization",
    "assignments",
    "processes",
    "assertions",
    "functional_coverage",
    "generates",
    "memories",
    "timing_specify",
    "foreign_interfaces",
    "attributes_pragmas",
    "file_io",
    "clocks_resets",
    "cdc",
    "protocols",
)


def _completeness(value: Any, module: str, language: str, standard: str) -> SemanticCompleteness:
    mapping = _mapping(value, f"completeness for {module}")
    _known_keys(mapping, set(SEMANTIC_CATEGORIES), f"completeness for {module}")
    missing = [category for category in SEMANTIC_CATEGORIES if category not in mapping]
    if missing:
        raise SemanticImportError(f"semantic completeness ledger for {module} is missing: {', '.join(missing)}")
    categories: list[tuple[str, str]] = []
    for category in SEMANTIC_CATEGORIES:
        state = str(mapping[category]).strip().lower()
        if state not in COMPLETENESS_STATES:
            raise SemanticImportError(f"invalid completeness state {state!r} for {module}/{category}")
        categories.append((category, state))
    return SemanticCompleteness(module, language, standard, tuple(categories))


def _port(value: Mapping[str, Any], label: str) -> RTLPort:
    _keys(value, "name direction dtype_id data_type width signed packed_range source_location", label)
    return RTLPort(
        _required_string(value, "name", label),
        _required_string(value, "direction", label),
        _optional_string(value, "dtype_id"),
        _optional_string(value, "data_type"),
        _optional_int(value, "width", label),
        _bool(value, "signed", False, label),
        _optional_string(value, "packed_range"),
        _optional_string(value, "source_location"),
    )


def _parameter(value: Mapping[str, Any], label: str) -> RTLParameter:
    _keys(value, "name default_value dtype_id data_type width signed local source_location", label)
    return RTLParameter(
        _required_string(value, "name", label),
        _optional_string(value, "default_value"),
        _optional_string(value, "dtype_id"),
        _optional_string(value, "data_type"),
        _optional_int(value, "width", label),
        _bool(value, "signed", False, label),
        _bool(value, "local", False, label),
        _optional_string(value, "source_location"),
    )


def _type(value: Mapping[str, Any], label: str) -> RTLType:
    _keys(value, "type_id name kind width signed members enum_values source_location", label)
    return RTLType(
        _required_string(value, "type_id", label),
        _optional_string(value, "name"),
        _required_string(value, "kind", label),
        _optional_int(value, "width", label),
        _bool(value, "signed", False, label),
        _strings(value.get("members", []), f"{label}.members"),
        _strings(value.get("enum_values", []), f"{label}.enum_values"),
        _optional_string(value, "source_location"),
    )


def _expression(value: Mapping[str, Any], label: str, depth: int = 0) -> RTLExpression:
    if depth > MAX_EXPRESSION_DEPTH:
        raise SemanticImportError(f"expression nesting exceeds {MAX_EXPRESSION_DEPTH}: {label}")
    _keys(
        value,
        "kind name value dtype_id source_location children width signed determination context_type "
        "cast_kind truncation unknown_bits packed_range frontend_identity specialization_identity",
        label,
    )
    children = tuple(
        _expression(item, f"{label}.children[{index}]", depth + 1)
        for index, item in enumerate(_record_list(value.get("children", []), f"{label}.children"))
    )
    determination = str(value.get("determination", "unknown"))
    truncation = str(value.get("truncation", "unknown"))
    unknown_bits = str(value.get("unknown_bits", "unknown"))
    if determination not in {"self", "context", "unknown"}:
        raise SemanticImportError(f"invalid expression determination {determination!r}: {label}")
    if truncation not in {"yes", "no", "unknown"}:
        raise SemanticImportError(f"invalid expression truncation {truncation!r}: {label}")
    if unknown_bits not in {"present", "absent", "unknown"}:
        raise SemanticImportError(f"invalid expression unknown_bits {unknown_bits!r}: {label}")
    return RTLExpression(
        kind=_required_string(value, "kind", label),
        name=_optional_string(value, "name"),
        value=_optional_string(value, "value"),
        dtype_id=_optional_string(value, "dtype_id"),
        source_location=_optional_string(value, "source_location"),
        children=children,
        width=_optional_int(value, "width", label),
        signed=_optional_bool(value, "signed", label),
        determination=determination,
        context_type=_optional_string(value, "context_type"),
        cast_kind=_optional_string(value, "cast_kind"),
        truncation=truncation,
        unknown_bits=unknown_bits,
        packed_range=_optional_string(value, "packed_range"),
        frontend_identity=_optional_string(value, "frontend_identity"),
        specialization_identity=_optional_string(value, "specialization_identity"),
    )


def _connection(value: Mapping[str, Any], label: str) -> RTLConnection:
    _keys(value, "port_name direction signal_refs expression source_location", label)
    raw_expression = value.get("expression")
    expression = (
        _expression(_mapping(raw_expression, f"{label}.expression"), f"{label}.expression")
        if raw_expression is not None
        else None
    )
    return RTLConnection(
        _required_string(value, "port_name", label),
        _optional_string(value, "direction"),
        _strings(value.get("signal_refs", []), f"{label}.signal_refs"),
        expression,
        _optional_string(value, "source_location"),
    )


def _instance(value: Mapping[str, Any], label: str) -> RTLInstance:
    _keys(
        value,
        "name module_name elaborated_module_name plan_module_name specialization_id parameter_bindings kind source_location connections",
        label,
    )
    bindings = tuple(
        RTLParameterBinding(_required_string(item, "name", item_label), _optional_string(item, "value"))
        for item, item_label in _labeled(value.get("parameter_bindings", []), f"{label}.parameter_bindings")
    )
    return RTLInstance(
        _required_string(value, "name", label),
        _optional_string(value, "module_name"),
        _optional_string(value, "elaborated_module_name"),
        _optional_string(value, "plan_module_name"),
        _optional_string(value, "specialization_id"),
        bindings,
        _optional_string(value, "kind"),
        _optional_string(value, "source_location"),
        _convert(value.get("connections", []), f"{label}.connections", _connection),
    )


def _assignment(value: Mapping[str, Any], label: str) -> RTLAssignment:
    _keys(value, "kind name source_location summary lhs_signals rhs_signals expressions", label)
    expressions = tuple(
        _expression(item, item_label)
        for item, item_label in _labeled(value.get("expressions", []), f"{label}.expressions")
    )
    return RTLAssignment(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "source_location"),
        _optional_string(value, "summary"),
        _strings(value.get("lhs_signals", []), f"{label}.lhs_signals"),
        _strings(value.get("rhs_signals", []), f"{label}.rhs_signals"),
        expressions,
    )


def _block(value: Mapping[str, Any], label: str) -> RTLProceduralBlock:
    _keys(
        value,
        "kind name source_location summary signal_refs expressions patterns domain_id",
        label,
    )
    expressions = tuple(
        _expression(item, item_label)
        for item, item_label in _labeled(value.get("expressions", []), f"{label}.expressions")
    )
    patterns = tuple(
        RTLProceduralPattern(
            _required_string(item, "kind", item_label),
            _required_string(item, "target", item_label),
            _optional_string(item, "control"),
            _optional_string(item, "value"),
            _optional_string(item, "source"),
            str(item.get("confidence", "shape")),
        )
        for item, item_label in _labeled(value.get("patterns", []), f"{label}.patterns")
    )
    return RTLProceduralBlock(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "source_location"),
        _optional_string(value, "summary"),
        _strings(value.get("signal_refs", []), f"{label}.signal_refs"),
        expressions,
        patterns,
        _optional_string(value, "domain_id"),
    )


def _memory(value: Mapping[str, Any], label: str) -> RTLMemory:
    _keys(
        value,
        "name dtype_id element_width depth address_width read_during_write source_location "
        "initialization_profile initialization_path initialization_sha256 initialization_default_policy",
        label,
    )
    return RTLMemory(
        _required_string(value, "name", label),
        _optional_string(value, "dtype_id"),
        _optional_int(value, "element_width", label),
        _optional_int(value, "depth", label),
        _optional_int(value, "address_width", label),
        str(value.get("read_during_write", "unknown")),
        _optional_string(value, "source_location"),
        (),
        str(value.get("initialization_profile", "unknown")),
        _optional_string(value, "initialization_path"),
        _optional_string(value, "initialization_sha256"),
        str(value.get("initialization_default_policy", "unknown")),
    )


def _memory_access(value: Mapping[str, Any], label: str) -> RTLMemoryAccess:
    _keys(
        value,
        "access_id memory kind address_signals data_signals enable_signals domain_id synchronous source_location",
        label,
    )
    return RTLMemoryAccess(
        _required_string(value, "access_id", label),
        _required_string(value, "memory", label),
        _required_string(value, "kind", label),
        _strings(value.get("address_signals", []), f"{label}.address_signals"),
        _strings(value.get("data_signals", []), f"{label}.data_signals"),
        _strings(value.get("enable_signals", []), f"{label}.enable_signals"),
        _optional_string(value, "domain_id"),
        _bool(value, "synchronous", False, label),
        _optional_string(value, "source_location"),
    )


def _clock(value: Mapping[str, Any], label: str) -> RTLClock:
    _keys(value, "name direction width source_location classification confidence", label)
    return RTLClock(
        _required_string(value, "name", label),
        _required_string(value, "direction", label),
        _optional_int(value, "width", label),
        _optional_string(value, "source_location"),
        str(value.get("classification", "external")),
        str(value.get("confidence", "high")),
    )


def _reset(value: Mapping[str, Any], label: str) -> RTLReset:
    _keys(value, "name direction width active_low source_location classification confidence", label)
    return RTLReset(
        _required_string(value, "name", label),
        _required_string(value, "direction", label),
        _optional_int(value, "width", label),
        _optional_bool(value, "active_low", label),
        _optional_string(value, "source_location"),
        str(value.get("classification", "external")),
        str(value.get("confidence", "high")),
    )


def _feature(value: Mapping[str, Any], label: str) -> RTLSemanticFeature:
    _keys(
        value,
        "kind name source_location confidence generation_supported supported_targets",
        label,
    )
    targets = tuple(
        _target(item, f"{label}.supported_targets")
        for item in _strings(value.get("supported_targets", []), f"{label}.supported_targets")
    )
    return RTLSemanticFeature(
        _required_string(value, "kind", label),
        _optional_string(value, "name"),
        _optional_string(value, "source_location"),
        str(value.get("confidence", "external")),
        _bool(value, "generation_supported", False, label),
        targets,
    )


def _domain(value: Mapping[str, Any], label: str) -> RTLControlDomain:
    _keys(
        value,
        "domain_id clock clock_edge reset reset_edge reset_active_low asynchronous_reset source_location",
        label,
    )
    return RTLControlDomain(
        _required_string(value, "domain_id", label),
        _required_string(value, "clock", label),
        str(value.get("clock_edge", "pos")),
        _optional_string(value, "reset"),
        _optional_string(value, "reset_edge"),
        _optional_bool(value, "reset_active_low", label),
        _bool(value, "asynchronous_reset", False, label),
        _optional_string(value, "source_location"),
    )


def _cdc(value: Mapping[str, Any], label: str) -> RTLCDCPath:
    _keys(
        value,
        "path_id signal source_domain destination_domain classification synchronizer_stages stage_signals safe reset_compatible source_location",
        label,
    )
    return RTLCDCPath(
        _required_string(value, "path_id", label),
        _required_string(value, "signal", label),
        _required_string(value, "source_domain", label),
        _required_string(value, "destination_domain", label),
        str(value.get("classification", "direct")),
        _int(value, "synchronizer_stages", 0, label),
        _strings(value.get("stage_signals", []), f"{label}.stage_signals"),
        _bool(value, "safe", False, label),
        _optional_bool(value, "reset_compatible", label),
        _optional_string(value, "source_location"),
    )


def _generate(value: Mapping[str, Any], label: str) -> RTLGenerateScope:
    _keys(value, "scope_id name kind source_location instance_names", label)
    return RTLGenerateScope(
        _required_string(value, "scope_id", label),
        _required_string(value, "name", label),
        _required_string(value, "kind", label),
        _optional_string(value, "source_location"),
        _strings(value.get("instance_names", []), f"{label}.instance_names"),
    )


def _protocol(value: Mapping[str, Any], label: str) -> RTLProtocol:
    _keys(
        value,
        "protocol_id kind name role valid ready data data_width clock reset confidence profile signal_map",
        label,
    )
    signal_map: list[tuple[str, str]] = []
    for index, pair in enumerate(value.get("signal_map", [])):
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, str) for item in pair):
            raise SemanticImportError(f"{label}.signal_map[{index}] must be a string pair")
        signal_map.append((pair[0], pair[1]))
    return RTLProtocol(
        _required_string(value, "protocol_id", label),
        _required_string(value, "kind", label),
        _required_string(value, "name", label),
        _required_string(value, "role", label),
        _required_string(value, "valid", label),
        _required_string(value, "ready", label),
        _optional_string(value, "data"),
        _optional_int(value, "data_width", label),
        _optional_string(value, "clock"),
        _optional_string(value, "reset"),
        str(value.get("confidence", "external")),
        str(value.get("profile", "external")),
        tuple(signal_map),
    )
