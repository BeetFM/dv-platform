# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLParameter,
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


def unavailable_crosscheck_result(
    run_id: str,
    primary: FrontendMetadata,
    reference: FrontendMetadata,
    error: str,
) -> SemanticCrossCheckResult:
    """Create the same schema for execution failures as for disagreements."""

    issue = SemanticCrossCheckIssue(
        "*",
        "frontend",
        "available",
        error,
        capability=CAPABILITY_DESIGN_UNITS,
    )
    return SemanticCrossCheckResult(
        primary.name,
        reference.name,
        (),
        (issue,),
        run_id=run_id,
        status="unavailable",
        primary=primary,
        reference=reference,
        capabilities=tuple(
            CapabilityCoverage(item, "unsupported", item in CORE_REQUIRED_CAPABILITIES, error)
            for item in COMPARABLE_CAPABILITIES
        ),
        unsupported_capabilities=COMPARABLE_CAPABILITIES,
    )


def aggregate_crosscheck_results(
    results: tuple[SemanticCrossCheckResult, ...],
) -> SemanticCrossCheckResult:
    """Combine independently checked elaboration points without hiding a failed run."""

    if not results:
        raise ValueError("At least one semantic cross-check result is required")
    capabilities: list[CapabilityCoverage] = []
    for capability in COMPARABLE_CAPABILITIES:
        entries = tuple(item for result in results for item in result.capabilities if item.capability == capability)
        statuses = {item.status for item in entries}
        capabilities.append(
            CapabilityCoverage(
                capability,
                "checked" if statuses == {"checked"} else "unsupported",
                any(item.required for item in entries),
                "; ".join(sorted({item.reason for item in entries if item.reason})) or None,
            )
        )
    issues = tuple(issue for result in results for issue in result.issues)
    status = "passed" if all(result.passed for result in results) else "failed"
    if any(result.status == "unavailable" for result in results):
        status = "unavailable"
    first = results[0]
    return SemanticCrossCheckResult(
        first.primary_name,
        first.reference_name,
        tuple(module for result in results for module in result.checked_modules),
        issues,
        run_id="aggregate",
        status=status,
        primary=first.primary,
        reference=first.reference,
        capabilities=tuple(capabilities),
        unsupported_capabilities=tuple(
            sorted({capability for result in results for capability in result.unsupported_capabilities})
        ),
    )


def classify_slang_version(version: str | None) -> dict[str, str | int | None]:
    """Classify Slang against the qualified major-version compatibility window."""

    match = re.search(r"(?:slang\s+)?(\d+)(?:\.\d+)?", version or "", re.IGNORECASE)
    major = int(match.group(1)) if match else None
    status = (
        "supported"
        if major is not None and SLANG_MIN_TESTED_MAJOR <= major <= SLANG_MAX_TESTED_MAJOR
        else "unsupported"
    )
    return {
        "status": status,
        "major": major,
        "min_tested_major": SLANG_MIN_TESTED_MAJOR,
        "max_tested_major": SLANG_MAX_TESTED_MAJOR,
    }


def benchmark_slang_normalization(document: object) -> SlangNormalizationBenchmark:
    """Normalize a document while measuring the Stage 7 runtime / memory budget."""

    import time
    import tracemalloc

    nodes = sum(1 for _ in _walk_json_objects(document))
    tracemalloc.start()
    started = time.perf_counter()
    modules = _normalize_slang_document(document)[0]
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return SlangNormalizationBenchmark(nodes, elapsed, peak, len(modules))


def capabilities_for_modules(modules: tuple[RTLModule, ...]) -> tuple[str, ...]:
    """Return the Verilator normalizer's declared comparison profile.

    Capability support is independent of whether a particular design contains a
    construct.  Treating an empty fact list as an unsupported capability made it
    impossible to distinguish "there are no properties" from "properties were
    dropped by the mapper".
    """

    del modules
    return COMPARABLE_CAPABILITIES


def required_capabilities_for_modules(modules: tuple[RTLModule, ...]) -> tuple[str, ...]:
    """Require the qualified semantic profile for an enabled cross-check."""

    del modules
    return COMPARABLE_CAPABILITIES


def write_crosscheck_result(path: Path, result: SemanticCrossCheckResult) -> Path:
    """Persist a stable semantic cross-check result artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": result.schema_version,
        "api_version": SEMANTIC_CROSSCHECK_API_VERSION,
        "run_id": result.run_id,
        "status": result.status,
        "passed": result.passed,
        "primary_name": result.primary_name,
        "reference_name": result.reference_name,
        "primary": _frontend_json(result.primary),
        "reference": _frontend_json(result.reference),
        "checked_modules": list(result.checked_modules),
        "capabilities": [
            {
                "capability": item.capability,
                "status": item.status,
                "required": item.required,
                "reason": item.reason,
            }
            for item in result.capabilities
        ],
        "unsupported_capabilities": list(result.unsupported_capabilities),
        "issues": [_issue_json(issue) for issue in result.issues],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _write_diagnostics(path: Path, return_code: int | None, status: str, text: str) -> None:
    atomic_write_text(
        path,
        json.dumps(
            {"schema_version": 1, "status": status, "return_code": return_code, "diagnostics": text},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def _frontend_json(value: FrontendMetadata | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "name": value.name,
        "version": value.version,
        "command": list(value.command),
        "artifact_path": value.artifact_path,
    }


def _issue_json(issue: SemanticCrossCheckIssue) -> dict[str, object]:
    return {
        "module": issue.module,
        "specialization": issue.specialization,
        "capability": issue.capability,
        "field": issue.field,
        "primary": issue.primary,
        "reference": issue.reference,
        "severity": issue.severity,
        "primary_location": issue.primary_location,
        "reference_location": issue.reference_location,
        "primary_evidence": [_evidence_json(item) for item in issue.primary_evidence],
        "reference_evidence": [_evidence_json(item) for item in issue.reference_evidence],
    }


def _evidence_json(value: EvidenceRef) -> dict[str, str | None]:
    return {
        "kind": value.kind.value,
        "source_id": value.source_id,
        "locator": value.locator,
        "summary": value.summary,
    }


def _normalize_slang_document(
    document: object,
    ast_path: Path | None = None,
    source_files: tuple[Path, ...] = (),
) -> tuple[
    tuple[RTLModule, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str], ...],
]:
    if not isinstance(document, dict) or not isinstance(document.get("design"), dict):
        raise SlangRunError("Slang AST JSON does not contain a design object")
    design = document["design"]
    gaps: dict[str, set[str]] = {}
    symbol_index = _slang_symbol_index(design)
    interface_ranges = _slang_instance_array_ranges(design)
    global_types = _slang_global_types(design, symbol_index)
    source_scopes = _slang_source_generate_scopes(source_files)
    modules = []
    seen_bodies: set[tuple[str, str]] = set()
    for body in _walk_json_objects(design):
        if body.get("kind") != "InstanceBody" or not body.get("name"):
            continue
        members = _json_dicts(body.get("members"))
        parameters = tuple(_slang_parameter(item) for item in members if item.get("kind") == "Parameter")
        original_name = _slang_original_name(body)
        body_key = (original_name, _specialization_from_parameters(parameters))
        if body_key in seen_bodies:
            continue
        seen_bodies.add(body_key)
        facts = _slang_body_facts(
            body,
            members,
            parameters,
            original_name,
            symbol_index,
            interface_ranges,
            global_types,
            source_scopes,
            ast_path,
        )
        modules.append(_slang_module_from_facts(facts))
        _record_slang_gaps(facts, gaps)
    if not modules:
        raise SlangRunError("Slang AST JSON contains no instance bodies")
    capabilities = set(COMPARABLE_CAPABILITIES) - set(gaps)
    unsupported = tuple(item for item in COMPARABLE_CAPABILITIES if item not in capabilities)
    reasons = tuple(
        (capability, "; ".join(sorted(gaps[capability])))
        for capability in COMPARABLE_CAPABILITIES
        if capability in gaps
    )
    return (
        tuple(modules),
        tuple(item for item in COMPARABLE_CAPABILITIES if item in capabilities),
        unsupported,
        reasons,
    )


def _slang_body_facts(
    body,
    members,
    parameters,
    original_name,
    symbol_index,
    interface_ranges,
    global_types,
    source_scopes,
    ast_path,
):
    name = str(body["name"])
    ports = tuple(_slang_port(item, interface_ranges) for item in members if _is_slang_port(item))
    parameter_names = {parameter.name for parameter in parameters}
    instances = _slang_instances_with_paths(members, symbol_index)
    continuous = tuple(
        _slang_assignment(item, parameter_names) for item in members if item.get("kind") == "ContinuousAssign"
    )
    procedure_nodes = tuple(item for item in members if item.get("kind") == "ProceduralBlock")
    procedures = tuple(_slang_procedure(item) for item in procedure_nodes)
    procedural = tuple(
        assignment
        for procedure in procedure_nodes
        for assignment in _slang_procedural_assignments(procedure, parameter_names)
    )
    assignments = (*continuous, *procedural)
    properties = _slang_properties(members)
    imports = _slang_imports(members)
    referenced_interfaces = {port.interface_name for port in ports if port.interface_name is not None}
    types = tuple(_slang_type(item, symbol_index) for item in members if _is_slang_type(item)) + tuple(
        item for item in global_types if item.package_name in imports or item.package_name in referenced_interfaces
    )
    memories = tuple(_slang_memory(item, symbol_index) for item in members if _is_slang_memory(item))
    generate_scopes = _merge_slang_generate_scopes(
        _slang_generate_scopes(members), source_scopes.get(original_name, ())
    )
    domains = tuple(
        domain
        for node, block in zip(procedure_nodes, procedures, strict=True)
        if (domain := _slang_control_domain(node, block)) is not None
    )
    memory_accesses = _slang_memory_accesses(members, memories, domains)
    memories = tuple(
        replace(
            memory,
            read_during_write=(
                "not_applicable"
                if not any(item.memory == memory.name and item.kind == "write" for item in memory_accesses)
                else "unknown"
            ),
        )
        for memory in memories
    )
    return {
        "body": body,
        "members": members,
        "name": name,
        "original_name": original_name,
        "parameters": parameters,
        "ports": ports,
        "instances": instances,
        "assignments": assignments,
        "procedures": procedures,
        "properties": properties,
        "imports": imports,
        "types": types,
        "memories": memories,
        "memory_accesses": memory_accesses,
        "generate_scopes": generate_scopes,
        "domains": domains,
        "ast_ref": _slang_ast_ref(body, ast_path, name, original_name),
    }


def _slang_ast_ref(body, ast_path, name, original_name):
    return EvidenceRef(
        EvidenceKind.SLANG_AST,
        str(ast_path or body.get("source_file") or "slang-ast"),
        _slang_source_location(body) or name,
        f"Slang instance body {original_name}",
    )


def _slang_module_from_facts(facts):
    body = facts["body"]
    members = facts["members"]
    name = facts["name"]
    parameters = facts["parameters"]
    procedures = facts["procedures"]
    properties = facts["properties"]
    instances = facts["instances"]
    return RTLModule(
        name=name,
        original_name=facts["original_name"],
        elaborated_name=name,
        specialization_id=_canonical_specialization_id(facts["original_name"], parameters),
        source=Path(str(body["source_file"])) if body.get("source_file") else None,
        ports=tuple(port.name for port in facts["ports"]),
        port_details=facts["ports"],
        parameters=tuple(parameter.name for parameter in parameters),
        parameter_details=parameters,
        type_details=facts["types"],
        memories=facts["memories"],
        memory_accesses=facts["memory_accesses"],
        instances=tuple(f"{item.name}:{item.module_name}" for item in instances),
        instance_details=instances,
        continuous_assignments=tuple(
            _slang_summary(item) for item in members if item.get("kind") == "ContinuousAssign"
        ),
        assignment_details=facts["assignments"],
        procedural_blocks=tuple(item.kind for item in procedures),
        procedural_block_details=procedures,
        control_domains=facts["domains"],
        assertions=tuple(item.name or item.kind for item in properties if item.kind != "cover"),
        covers=tuple(item.name or item.kind for item in properties if item.kind == "cover"),
        property_details=properties,
        generate_scopes=facts["generate_scopes"],
        imports=facts["imports"],
        ast_refs=(facts["ast_ref"],),
    )


def _record_slang_gaps(facts, gaps) -> None:
    _collect_slang_capability_gaps(facts["members"], gaps)
    expressions = tuple(expression for item in facts["assignments"] for expression in item.expressions) + tuple(
        expression for item in facts["procedures"] for expression in item.expressions
    )
    branches = tuple(branch for item in facts["procedures"] for branch in item.branches)
    if expressions and any(
        expression.kind == "unsupported" for root in expressions for expression in _walk_expressions(root)
    ):
        _add_gap(gaps, CAPABILITY_EXPRESSIONS, "an expression node could not be normalized")
    if branches and any(branch.condition is None and not branch.is_default for branch in branches):
        _add_gap(gaps, CAPABILITY_BRANCHES, "a branch condition could not be normalized")
    if any(item.condition is not None and item.condition.kind == "unsupported" for item in facts["generate_scopes"]):
        _add_gap(gaps, CAPABILITY_GENERATE_SCOPES, "a source generate condition could not be normalized")
    for prop in facts["properties"]:
        if prop.support_status != "normalized":
            _add_gap(
                gaps,
                CAPABILITY_PROPERTIES,
                f"{prop.source_location or prop.name or 'property'}: unsupported operators "
                + ", ".join(prop.unsupported_operators),
            )


def _modules_from_slang_json(document: object) -> tuple[RTLModule, ...]:
    """Compatibility wrapper used by unit tests and adapter clients."""

    return _normalize_slang_document(document)[0]


def _walk_json_objects(value: object) -> Iterator[dict[str, Any]]:
    """Iterate a large Slang document without recursive tuple materialization."""

    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(reversed(tuple(current.values())))
        elif isinstance(current, (list, tuple)):
            stack.extend(reversed(current))


def _json_dicts(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _slang_original_name(body: dict[str, Any]) -> str:
    for key in ("definitionName", "originalName", "definition", "moduleName"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return _canonical_symbol_name(value)
        if isinstance(value, dict) and value.get("name"):
            return str(value["name"])
    return str(body["name"])


def _specialization_from_parameters(parameters: tuple[RTLParameter, ...]) -> str:
    values = tuple(
        sorted((item.name, _canonical_constant(item.default_value)) for item in parameters if not item.local)
    )
    return repr(values)


def _slang_symbol_index(value: object) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for node in _walk_json_objects(value):
        address = node.get("addr")
        if address is not None:
            index[str(address)] = node
    return index


def _slang_instance_array_ranges(value: object) -> dict[str, tuple[str, ...]]:
    found: dict[str, set[str]] = {}
    for node in _walk_json_objects(value):
        if node.get("kind") != "InstanceArray" or not node.get("name") or not node.get("range"):
            continue
        found.setdefault(str(node["name"]), set()).add(str(node["range"]))
    return {
        name: tuple(_canonical_range(value) or value for value in sorted(ranges))
        for name, ranges in found.items()
        if len(ranges) == 1
    }


def _slang_link(value: object, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    return index.get(value.strip().split(" ", 1)[0])


def _is_slang_port(value: object) -> bool:
    return isinstance(value, dict) and value.get("kind") in {"Port", "InterfacePort"} and bool(value.get("name"))


def _is_slang_instance(value: dict[str, Any]) -> bool:
    return value.get("kind") == "Instance" and bool(value.get("name")) and value.get("body") is not None
