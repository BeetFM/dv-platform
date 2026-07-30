# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Versioned, fail-closed semantic facts interchange."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLSemanticFeature,
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


def _module(
    record: Mapping[str, Any],
    repo_root: Path,
    manifest_path: Path,
    source_id: str,
    index: int,
) -> tuple[RTLModule, SemanticCompleteness]:
    label = f"modules[{index}]"
    _known_keys(
        record,
        {
            "name",
            "original_name",
            "elaborated_name",
            "specialization_id",
            "design_unit_kind",
            "language",
            "standard",
            "library",
            "source",
            "completeness",
            "ports",
            "parameters",
            "types",
            "memories",
            "memory_accesses",
            "clocks",
            "resets",
            "semantic_features",
            "instances",
            "continuous_assignments",
            "procedural_blocks",
            "assertions",
            "covers",
            "generate_scopes",
            "imports",
            "control_domains",
            "cdc_paths",
            "protocols",
            "documentation_refs",
        },
        label,
    )
    name = _required_string(record, "name", label)
    language = _required_string(record, "language", label).lower()
    if language not in SUPPORTED_LANGUAGES:
        raise SemanticImportError(f"unsupported RTL language {language!r} for {name}")
    standard = _required_string(record, "standard", label)
    if standard not in SUPPORTED_STANDARDS[language]:
        raise SemanticImportError(f"unsupported {language} standard {standard!r} for {name}")
    source = _safe_source(_required_string(record, "source", label), repo_root, name)
    default_kind = "entity" if language == "vhdl" else "module"
    design_unit_kind = str(record.get("design_unit_kind", default_kind))
    if design_unit_kind not in DESIGN_UNIT_KINDS[language]:
        raise SemanticImportError(f"unsupported {language} design unit kind {design_unit_kind!r} for {name}")
    ledger = _completeness(record.get("completeness"), name, language, standard)
    evidence = EvidenceRef(
        kind=EvidenceKind.SEMANTIC_MANIFEST,
        source_id=source_id,
        locator=f"{manifest_path}:{name}",
        summary=f"{language} {standard} normalized semantic facts",
    )

    ports = _convert(record.get("ports", []), f"{label}.ports", _port)
    parameters = _convert(record.get("parameters", []), f"{label}.parameters", _parameter)
    types = _convert(record.get("types", []), f"{label}.types", _type)
    memories = _convert(record.get("memories", []), f"{label}.memories", _memory)
    memory_accesses = _convert(record.get("memory_accesses", []), f"{label}.memory_accesses", _memory_access)
    clocks = _convert(record.get("clocks", []), f"{label}.clocks", _clock)
    resets = _convert(record.get("resets", []), f"{label}.resets", _reset)
    features = _convert(record.get("semantic_features", []), f"{label}.semantic_features", _feature)
    features = (
        RTLSemanticFeature(kind=f"language:{language}", confidence="external", generation_supported=True),
        RTLSemanticFeature(kind=f"standard:{standard}", confidence="external"),
        *features,
    )
    instances = _convert(record.get("instances", []), f"{label}.instances", _instance)
    assignments = _convert(record.get("continuous_assignments", []), f"{label}.continuous_assignments", _assignment)
    blocks = _convert(record.get("procedural_blocks", []), f"{label}.procedural_blocks", _block)
    domains = _convert(record.get("control_domains", []), f"{label}.control_domains", _domain)
    cdc_paths = _convert(record.get("cdc_paths", []), f"{label}.cdc_paths", _cdc)
    generates = _convert(record.get("generate_scopes", []), f"{label}.generate_scopes", _generate)
    protocols = _convert(record.get("protocols", []), f"{label}.protocols", _protocol)
    module = RTLModule(
        name=name,
        original_name=_optional_string(record, "original_name"),
        elaborated_name=_optional_string(record, "elaborated_name"),
        specialization_id=_optional_string(record, "specialization_id"),
        design_unit_kind=design_unit_kind,
        source=source,
        ports=tuple(item.name for item in ports),
        parameters=tuple(item.name for item in parameters),
        parameter_details=parameters,
        type_details=types,
        memories=memories,
        memory_accesses=memory_accesses,
        clocks=tuple(item.name for item in clocks),
        resets=tuple(item.name for item in resets),
        clock_details=clocks,
        reset_details=resets,
        semantic_features=features,
        instances=tuple(item.name for item in instances),
        continuous_assignments=tuple(item.summary or item.name or item.kind for item in assignments),
        procedural_blocks=tuple(item.summary or item.name or item.kind for item in blocks),
        assertions=_strings(record.get("assertions", []), f"{label}.assertions"),
        covers=_strings(record.get("covers", []), f"{label}.covers"),
        documentation_refs=_strings(record.get("documentation_refs", []), f"{label}.documentation_refs"),
        ast_refs=(evidence,),
        port_details=ports,
        instance_details=instances,
        assignment_details=assignments,
        procedural_block_details=blocks,
        control_domains=domains,
        cdc_paths=cdc_paths,
        generate_scopes=generates,
        imports=_strings(record.get("imports", []), f"{label}.imports"),
        protocols=protocols,
    )
    _validate_module_semantics(module)
    return (
        module,
        ledger,
    )
