# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Versioned, fail-closed semantic facts interchange."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from dv_platform.core.models import (
    RTLModule,
    VerificationTarget,
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


def _diagnostic(value: Mapping[str, Any], index: int) -> SemanticDiagnostic:
    label = f"diagnostics[{index}]"
    _keys(value, "severity code message source_location", label)
    severity = _required_string(value, "severity", label).lower()
    if severity not in {"info", "warning", "error"}:
        raise SemanticImportError(f"invalid diagnostic severity {severity!r} at {label}")
    return SemanticDiagnostic(
        severity,
        _required_string(value, "code", label),
        _required_string(value, "message", label),
        _optional_string(value, "source_location"),
    )


def _convert(value: Any, label: str, converter: Callable[[Mapping[str, Any], str], T]) -> tuple[T, ...]:
    return tuple(converter(item, item_label) for item, item_label in _labeled(value, label))


def _labeled(value: Any, label: str) -> tuple[tuple[Mapping[str, Any], str], ...]:
    return tuple((item, f"{label}[{index}]") for index, item in enumerate(_record_list(value, label)))


def _record_list(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise SemanticImportError(f"{label} must be a list")
    return tuple(_mapping(item, f"{label}[{index}]") for index, item in enumerate(value))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SemanticImportError(f"{label} must be an object with string keys")
    return value


def _keys(value: Mapping[str, Any], allowed: str, label: str) -> None:
    _known_keys(value, set(allowed.split()), label)


def _known_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SemanticImportError(f"unknown fields in {label}: {', '.join(unknown)}")


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise SemanticImportError(f"{label}.{key} must be a non-empty string")
    return item.strip()


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise SemanticImportError(f"{key} must be a non-empty string when provided")
    return item.strip()


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SemanticImportError(f"{label} must be a list of non-empty strings")
    return tuple(dict.fromkeys(item.strip() for item in value))


def _optional_int(value: Mapping[str, Any], key: str, label: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise SemanticImportError(f"{label}.{key} must be a non-negative integer")
    return item


def _int(value: Mapping[str, Any], key: str, default: int, label: str) -> int:
    item = value.get(key, default)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise SemanticImportError(f"{label}.{key} must be a non-negative integer")
    return item


def _bool(value: Mapping[str, Any], key: str, default: bool, label: str) -> bool:
    item = value.get(key, default)
    if not isinstance(item, bool):
        raise SemanticImportError(f"{label}.{key} must be a boolean")
    return item


def _optional_bool(value: Mapping[str, Any], key: str, label: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise SemanticImportError(f"{label}.{key} must be a boolean")
    return item


def _target(value: str, label: str) -> VerificationTarget:
    try:
        return VerificationTarget(value)
    except ValueError as exc:
        raise SemanticImportError(f"unsupported verification target {value!r} at {label}") from exc


def _safe_source(value: str, repo_root: Path, module: str) -> Path:
    source = Path(value)
    resolved = (repo_root / source).resolve() if not source.is_absolute() else source.resolve()
    if not resolved.is_relative_to(repo_root):
        raise SemanticImportError(f"semantic source for {module} escapes repository root: {value}")
    if not resolved.is_file():
        raise SemanticImportError(f"semantic source for {module} does not exist: {value}")
    return resolved


def _validate_module_semantics(module: RTLModule) -> None:
    _unique((item.name for item in module.port_details), "port", module.name)
    _unique((item.name for item in module.parameter_details), "parameter", module.name)
    _unique((item.type_id for item in module.type_details), "type_id", module.name)
    _unique((item.name for item in module.memories), "memory", module.name)
    _unique((item.access_id for item in module.memory_accesses), "memory access", module.name)
    _unique((item.name for item in module.instance_details), "instance", module.name)
    _unique((item.domain_id for item in module.control_domains), "control domain", module.name)
    _unique((item.path_id for item in module.cdc_paths), "CDC path", module.name)
    _unique((item.scope_id for item in module.generate_scopes), "generate scope", module.name)
    _unique((item.protocol_id for item in module.protocols), "protocol", module.name)
    memories = {item.name for item in module.memories}
    domains = {item.domain_id for item in module.control_domains}
    for access in module.memory_accesses:
        if access.memory not in memories:
            raise SemanticImportError(
                f"memory access {module.name}/{access.access_id} references unknown memory {access.memory}"
            )
        if access.domain_id is not None and access.domain_id not in domains:
            raise SemanticImportError(
                f"memory access {module.name}/{access.access_id} references unknown domain {access.domain_id}"
            )
    for path in module.cdc_paths:
        if path.source_domain not in domains or path.destination_domain not in domains:
            raise SemanticImportError(f"CDC path {module.name}/{path.path_id} references unknown control domain")
        if path.safe and (
            path.synchronizer_stages < 2
            or len(path.stage_signals) != path.synchronizer_stages
            or len(set(path.stage_signals)) != len(path.stage_signals)
        ):
            raise SemanticImportError(f"safe CDC path {module.name}/{path.path_id} lacks a valid ordered stage chain")
    for instance in module.instance_details:
        _unique(
            (connection.port_name for connection in instance.connections),
            f"connection in {instance.name}",
            module.name,
        )


def _unique(values: Any, label: str, module: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise SemanticImportError(f"duplicate {label} in {module}: {value}")
        seen.add(value)
