"""Fail-closed cross-language binding manifest validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.core.models import RTLModule


@dataclass(frozen=True)
class CrossLanguageBinding:
    instance: str
    parent_language: str
    parent_unit: str
    child_language: str
    child_unit: str
    architecture: str | None
    library: str
    port_map: tuple[tuple[str, str], ...]
    generic_map: tuple[tuple[str, str], ...]


def load_cross_language_bindings(path: Path) -> tuple[CrossLanguageBinding, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported cross-language binding schema")
    raw_bindings = value.get("bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise ValueError("cross-language binding manifest requires bindings")
    bindings: list[CrossLanguageBinding] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_bindings:
        if not isinstance(raw, dict):
            raise ValueError("cross-language binding entries must be objects")
        binding = _binding(raw)
        key = (binding.parent_unit, binding.instance)
        if key in seen:
            raise ValueError(f"duplicate cross-language instance binding: {binding.parent_unit}.{binding.instance}")
        seen.add(key)
        if binding.parent_language == binding.child_language:
            raise ValueError("cross-language binding endpoints must use different languages")
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda item: (item.parent_unit, item.instance)))


def validate_cross_language_bindings(
    bindings: tuple[CrossLanguageBinding, ...], modules: tuple[RTLModule, ...]
) -> None:
    """Reconcile every declared endpoint and mapping against normalized facts."""

    by_unit: dict[str, list[RTLModule]] = {}
    for module in modules:
        by_unit.setdefault((module.original_name or module.name).lower(), []).append(module)
    for binding in bindings:
        parent = _unique_unit(by_unit, binding.parent_unit)
        child = _unique_unit(by_unit, binding.child_unit)
        parent_ports = {port.name.lower() for port in parent.port_details}
        child_ports = {port.name.lower() for port in child.port_details}
        missing_parent = sorted(name for name, _ in binding.port_map if name.lower() not in parent_ports)
        missing_child = sorted(name for _, name in binding.port_map if name.lower() not in child_ports)
        if missing_parent or missing_child:
            details = []
            if missing_parent:
                details.append("parent ports " + ", ".join(missing_parent))
            if missing_child:
                details.append("child ports " + ", ".join(missing_child))
            raise ValueError(f"binding {binding.parent_unit}.{binding.instance} has unknown " + "; ".join(details))
        child_generics = {parameter.name.lower() for parameter in child.parameter_details}
        missing_generics = sorted(name for name, _ in binding.generic_map if name.lower() not in child_generics)
        if missing_generics:
            raise ValueError(
                f"binding {binding.parent_unit}.{binding.instance} has unknown child generics: "
                + ", ".join(missing_generics)
            )
        if binding.child_language == "vhdl" and binding.architecture != child.elaborated_name:
            raise ValueError(
                f"binding {binding.parent_unit}.{binding.instance} selects architecture "
                f"{binding.architecture!r}, normalized {child.elaborated_name!r}"
            )


def binding_units(bindings: tuple[CrossLanguageBinding, ...], languages: set[str]) -> tuple[str, ...]:
    """Return deterministic design units participating in the selected languages."""

    units = {
        unit
        for binding in bindings
        for language, unit in (
            (binding.parent_language, binding.parent_unit),
            (binding.child_language, binding.child_unit),
        )
        if language in languages
    }
    return tuple(sorted(units, key=str.lower))


def _unique_unit(by_unit: dict[str, list[RTLModule]], unit: str) -> RTLModule:
    matches = by_unit.get(unit.lower(), [])
    if not matches:
        raise ValueError(f"cross-language binding unit was not normalized: {unit}")
    if len(matches) != 1:
        raise ValueError(f"cross-language binding unit is ambiguous after elaboration: {unit}")
    return matches[0]


def _binding(raw: dict[str, Any]) -> CrossLanguageBinding:
    languages = {"verilog", "systemverilog", "vhdl"}
    required = ("instance", "parent_language", "parent_unit", "child_language", "child_unit", "library")
    if any(not isinstance(raw.get(name), str) or not str(raw[name]).strip() for name in required):
        raise ValueError("cross-language binding identity fields are required")
    if raw["parent_language"] not in languages or raw["child_language"] not in languages:
        raise ValueError("unsupported cross-language binding language")
    port_map = raw.get("port_map")
    generic_map = raw.get("generic_map", {})
    if not isinstance(port_map, dict) or not port_map or not isinstance(generic_map, dict):
        raise ValueError("cross-language binding requires a non-empty port_map and object generic_map")
    if len(port_map.values()) != len(set(str(value) for value in port_map.values())):
        raise ValueError("cross-language port bindings must be one-to-one")
    return CrossLanguageBinding(
        instance=str(raw["instance"]),
        parent_language=str(raw["parent_language"]),
        parent_unit=str(raw["parent_unit"]),
        child_language=str(raw["child_language"]),
        child_unit=str(raw["child_unit"]),
        architecture=str(raw["architecture"]) if raw.get("architecture") is not None else None,
        library=str(raw["library"]),
        port_map=tuple(sorted((str(key), str(value)) for key, value in port_map.items())),
        generic_map=tuple(sorted((str(key), str(value)) for key, value in generic_map.items())),
    )


CrossLanguageBinding.__module__ = "dv_platform.analysis.bindings"
