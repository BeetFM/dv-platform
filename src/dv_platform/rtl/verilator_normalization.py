# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import parse

from dv_platform.analysis.discovery import ProjectInventory, build_verilator_dry_run_command
from dv_platform.analysis.protocols import recognize_protocols
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
    ProductionProtocolBinding,
    ProtocolProfile,
    RTLModule,
    RTLParameter,
)
from dv_platform.core.schema import MIN_READABLE_RTL_FACTS_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.core.security import append_audit_event, redact_text

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


@dataclass(frozen=True)
class VerilatorRunResult:
    """Result of one Verilator XML extraction attempt."""

    command: tuple[str, ...]
    return_code: int
    stdout_log: Path
    stderr_log: Path
    version: str | None
    version_log: Path
    xml_files: tuple[Path, ...]


@dataclass(frozen=True)
class _ModuleCandidate:
    xml_file: Path
    root: Element
    element: Element
    original_name: str
    elaborated_name: str
    parameters: tuple[RTLParameter, ...]
    specialization_id: str
    identity: str


def run_verilator_xml(config: CLIConfig, inventory: ProjectInventory) -> VerilatorRunResult:
    """Run Verilator XML extraction and persist logs under the work directory."""

    command = build_verilator_dry_run_command(config, inventory)
    verilator_dir = config.work_dir / "verilator"
    logs_dir = config.work_dir / "logs"
    verilator_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    version = _detect_verilator_version(config)
    version_log = verilator_dir / "verilator-version.txt"
    version_log.write_text((version or "unknown") + "\n", encoding="utf-8")
    append_audit_event(config, "rtl_analysis.start", {"command": list(command)})

    completed = subprocess.run(
        command,
        cwd=config.repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout_log = logs_dir / "verilator.stdout.log"
    stderr_log = logs_dir / "verilator.stderr.log"
    stdout_log.write_text(redact_text(config, completed.stdout), encoding="utf-8")
    stderr_log.write_text(redact_text(config, completed.stderr), encoding="utf-8")
    append_audit_event(
        config,
        "rtl_analysis.finish",
        {"command": list(command), "return_code": completed.returncode},
    )

    return VerilatorRunResult(
        command=command,
        return_code=completed.returncode,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        version=version,
        version_log=version_log,
        xml_files=tuple(sorted(verilator_dir.glob("*.xml"), key=lambda path: path.as_posix())),
    )


def normalize_verilator_xml(
    xml_files: tuple[Path, ...],
    protocol_profiles: tuple[ProtocolProfile, ...] = (),
    production_protocol_bindings: tuple[ProductionProtocolBinding, ...] = (),
    identity_suffix: str | None = None,
) -> tuple[RTLModule, ...]:
    """Extract conservative, specialization-aware module facts from Verilator XML."""

    candidates = _verilator_module_candidates(xml_files, identity_suffix)
    by_root: dict[int, dict[str, _ModuleCandidate]] = {}
    for candidate in candidates:
        by_root.setdefault(id(candidate.root), {})[candidate.elaborated_name] = candidate
    modules = {
        candidate.identity: _normalized_verilator_module(
            candidate,
            by_root.get(id(candidate.root), {}),
            protocol_profiles,
            production_protocol_bindings,
        )
        for candidate in candidates
    }
    return tuple(modules[name] for name in sorted(modules))


def _verilator_module_candidates(
    xml_files: tuple[Path, ...],
    identity_suffix: str | None,
) -> list[_ModuleCandidate]:
    raw = []
    for xml_file in xml_files:
        tree = parse(xml_file)
        root = tree.getroot()
        if root is None:
            raise ValueError(f"Verilator XML has no root element: {xml_file}")
        for element in root.iter():
            if _local_name(element.tag) != "module":
                continue
            original_name = element.attrib.get("origName") or element.attrib.get("name")
            elaborated_name = element.attrib.get("name") or original_name
            if original_name and elaborated_name:
                raw.append(
                    (
                        xml_file,
                        root,
                        element,
                        original_name,
                        elaborated_name,
                        _parameter_details(element, root),
                    )
                )
    unique: dict[
        tuple[str, str, tuple[tuple[str, str | None], ...]],
        tuple[Path, Element, Element, str, str, tuple[RTLParameter, ...]],
    ] = {}
    for item in raw:
        signature = tuple((parameter.name, parameter.default_value) for parameter in item[5] if not parameter.local)
        unique.setdefault((item[3], item[4], signature), item)
    counts: dict[str, int] = {}
    for item in unique.values():
        counts[item[3]] = counts.get(item[3], 0) + 1
    candidates = []
    for xml_file, root, element, original_name, elaborated_name, parameters in unique.values():
        specialization_id = _specialization_id(original_name, elaborated_name, parameters)
        identity = original_name if counts[original_name] == 1 else f"{original_name}__spec_{specialization_id[:8]}"
        if identity_suffix:
            identity = f"{identity}__{identity_suffix}"
        candidates.append(
            _ModuleCandidate(
                xml_file,
                root,
                element,
                original_name,
                elaborated_name,
                parameters,
                specialization_id,
                identity,
            )
        )
    return candidates


def _normalized_verilator_module(
    candidate: _ModuleCandidate,
    root_candidates: dict[str, _ModuleCandidate],
    protocol_profiles: tuple[ProtocolProfile, ...],
    production_protocol_bindings: tuple[ProductionProtocolBinding, ...],
) -> RTLModule:
    element, root, name = candidate.element, candidate.root, candidate.identity
    ports = _port_names(element)
    port_details = _port_details(element, root)
    clock_details = _clock_details(port_details, element)
    reset_details = _reset_details(port_details, element)
    ast_refs = _evidence_refs(candidate.xml_file, element, name)
    control_domains, procedural_blocks = _control_domains_and_blocks(element, root)
    assignments = _assignment_details(element, root)
    type_details = _type_details(element, root)
    raw_memories = _memory_details(element, root)
    memory_accesses = _memory_accesses(name, raw_memories, assignments, procedural_blocks, ast_refs)
    memories = _memories_with_access_policy(raw_memories, memory_accesses)
    instances = _instance_details(element, root, root_candidates)
    cdc_paths = _cdc_paths(name, procedural_blocks, control_domains, ast_refs, port_details)
    return RTLModule(
        name=name,
        original_name=candidate.original_name,
        elaborated_name=candidate.elaborated_name,
        specialization_id=candidate.specialization_id,
        design_unit_kind=_design_unit_kind(element),
        source=_module_source(root, element),
        ports=ports,
        port_details=port_details,
        parameters=_parameter_names(element),
        parameter_details=candidate.parameters,
        type_details=type_details,
        memories=memories,
        memory_accesses=memory_accesses,
        clocks=tuple(clock.name for clock in clock_details),
        resets=tuple(reset.name for reset in reset_details),
        clock_details=clock_details,
        reset_details=reset_details,
        semantic_features=_semantic_features(element, root),
        instances=tuple(
            f"{instance.name}:{instance.module_name}" if instance.module_name else instance.name
            for instance in instances
        ),
        instance_details=instances,
        continuous_assignments=_element_summaries(element, {"assign", "contassign"}),
        assignment_details=assignments,
        procedural_blocks=_element_summaries(element, {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}),
        procedural_block_details=procedural_blocks,
        control_domains=control_domains,
        cdc_paths=cdc_paths,
        generate_scopes=_generate_scopes(element, instances, root),
        imports=tuple(
            dict.fromkeys(
                (
                    *_imports(element),
                    *(item.package_name for item in type_details if item.package_name and item.kind != "modport"),
                )
            )
        ),
        protocols=_protocols(name, port_details, control_domains, ast_refs, protocol_profiles),
        protocol_models=recognize_protocols(
            RTLModule(
                name=name,
                original_name=candidate.original_name,
                port_details=port_details,
                ast_refs=ast_refs,
            ),
            production_protocol_bindings,
        ),
        assertions=_matching_element_summaries(element, "assert"),
        covers=_matching_element_summaries(element, "cover"),
        property_details=_property_details(element, root),
        ast_refs=ast_refs,
    )


def _specialization_id(
    original_name: str,
    elaborated_name: str,
    parameters: tuple[RTLParameter, ...],
) -> str:
    signature = "\0".join(
        (
            original_name,
            elaborated_name,
            *(f"{parameter.name}={parameter.default_value}" for parameter in parameters if not parameter.local),
        )
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]


def _design_unit_kind(element: Element) -> str:
    return str(element.attrib.get("designUnitKind") or element.attrib.get("kind") or "module").lower()


def write_normalized_rtl_facts(
    config: CLIConfig,
    modules: tuple[RTLModule, ...],
    verilator_version: str | None = None,
    normalization_frontends: tuple[str, ...] = (),
) -> Path:
    """Persist normalized RTL facts for planning and claim checking."""

    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    facts_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": RTL_FACTS_SCHEMA_VERSION,
        "min_reader_schema_version": MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
        "verilator_version": verilator_version,
        "verilator_compatibility": classify_verilator_version(verilator_version),
        "normalization_frontends": list(normalization_frontends or (("verilator",) if verilator_version else ())),
        "modules": [
            {
                "name": module.name,
                "original_name": module.original_name,
                "elaborated_name": module.elaborated_name,
                "specialization_id": module.specialization_id,
                "design_unit_kind": module.design_unit_kind,
                "source": str(module.source) if module.source is not None else None,
                "ports": list(module.ports),
                "port_details": [
                    {
                        "name": port.name,
                        "direction": port.direction,
                        "dtype_id": port.dtype_id,
                        "data_type": port.data_type,
                        "width": port.width,
                        "signed": port.signed,
                        "packed_range": port.packed_range,
                        "source_location": port.source_location,
                        "interface_name": port.interface_name,
                        "modport": port.modport,
                        "interface_direction": port.interface_direction,
                        "packed_dimensions": list(port.packed_dimensions),
                        "unpacked_dimensions": list(port.unpacked_dimensions),
                    }
                    for port in module.port_details
                ],
                "parameters": list(module.parameters),
                "parameter_details": [
                    {
                        "name": parameter.name,
                        "default_value": parameter.default_value,
                        "dtype_id": parameter.dtype_id,
                        "data_type": parameter.data_type,
                        "width": parameter.width,
                        "signed": parameter.signed,
                        "local": parameter.local,
                        "source_location": parameter.source_location,
                    }
                    for parameter in module.parameter_details
                ],
                "type_details": [_type_to_json(item) for item in module.type_details],
                "memories": [
                    {
                        "name": memory.name,
                        "dtype_id": memory.dtype_id,
                        "element_width": memory.element_width,
                        "depth": memory.depth,
                        "address_width": memory.address_width,
                        "read_during_write": memory.read_during_write,
                        "source_location": memory.source_location,
                        "unpacked_dimensions": list(memory.unpacked_dimensions),
                    }
                    for memory in module.memories
                ],
                "memory_accesses": [_memory_access_to_json(item) for item in module.memory_accesses],
                "clocks": list(module.clocks),
                "resets": list(module.resets),
                "clock_details": [
                    {
                        "name": clock.name,
                        "direction": clock.direction,
                        "width": clock.width,
                        "source_location": clock.source_location,
                        "classification": clock.classification,
                        "confidence": clock.confidence,
                    }
                    for clock in module.clock_details
                ],
                "reset_details": [
                    {
                        "name": reset.name,
                        "direction": reset.direction,
                        "width": reset.width,
                        "active_low": reset.active_low,
                        "source_location": reset.source_location,
                        "classification": reset.classification,
                        "confidence": reset.confidence,
                    }
                    for reset in module.reset_details
                ],
                "semantic_features": [
                    {
                        "kind": feature.kind,
                        "name": feature.name,
                        "source_location": feature.source_location,
                        "confidence": feature.confidence,
                        "generation_supported": feature.generation_supported,
                        "supported_targets": [str(target) for target in feature.supported_targets],
                    }
                    for feature in module.semantic_features
                ],
                "instances": list(module.instances),
                "instance_details": [
                    {
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
                        "connections": [
                            {
                                "port_name": connection.port_name,
                                "direction": connection.direction,
                                "signal_refs": list(connection.signal_refs),
                                "expression": _expression_to_json(connection.expression)
                                if connection.expression is not None
                                else None,
                                "source_location": connection.source_location,
                            }
                            for connection in instance.connections
                        ],
                    }
                    for instance in module.instance_details
                ],
                "continuous_assignments": list(module.continuous_assignments),
                "assignment_details": [
                    {
                        "kind": assignment.kind,
                        "name": assignment.name,
                        "source_location": assignment.source_location,
                        "summary": assignment.summary,
                        "lhs_signals": list(assignment.lhs_signals),
                        "rhs_signals": list(assignment.rhs_signals),
                        "expressions": [_expression_to_json(expression) for expression in assignment.expressions],
                    }
                    for assignment in module.assignment_details
                ],
                "procedural_blocks": list(module.procedural_blocks),
                "procedural_block_details": [
                    {
                        "kind": block.kind,
                        "name": block.name,
                        "source_location": block.source_location,
                        "summary": block.summary,
                        "signal_refs": list(block.signal_refs),
                        "expressions": [_expression_to_json(expression) for expression in block.expressions],
                        "branches": [
                            {
                                "kind": branch.kind,
                                "source_location": branch.source_location,
                                "condition": (
                                    _expression_to_json(branch.condition) if branch.condition is not None else None
                                ),
                                "labels": [_expression_to_json(label) for label in branch.labels],
                                "is_default": branch.is_default,
                                "mutually_exclusive": branch.mutually_exclusive,
                            }
                            for branch in block.branches
                        ],
                        "patterns": [
                            {
                                "kind": pattern.kind,
                                "target": pattern.target,
                                "control": pattern.control,
                                "value": pattern.value,
                                "source": pattern.source,
                                "confidence": pattern.confidence,
                            }
                            for pattern in block.patterns
                        ],
                        "domain_id": block.domain_id,
                    }
                    for block in module.procedural_block_details
                ],
                "control_domains": [
                    {
                        "domain_id": domain.domain_id,
                        "clock": domain.clock,
                        "clock_edge": domain.clock_edge,
                        "reset": domain.reset,
                        "reset_edge": domain.reset_edge,
                        "reset_active_low": domain.reset_active_low,
                        "asynchronous_reset": domain.asynchronous_reset,
                        "source_location": domain.source_location,
                    }
                    for domain in module.control_domains
                ],
                "cdc_paths": [_cdc_path_to_json(item) for item in module.cdc_paths],
                "generate_scopes": [_generate_scope_to_json(item) for item in module.generate_scopes],
                "imports": list(module.imports),
                "protocols": [
                    {
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
                    for protocol in module.protocols
                ],
                "protocol_models": [_protocol_model_to_json(protocol) for protocol in module.protocol_models],
                "register_models": [_register_model_to_json(register) for register in module.register_models],
                "register_conflicts": [_register_conflict_to_json(conflict) for conflict in module.register_conflicts],
                "assertions": list(module.assertions),
                "covers": list(module.covers),
                "property_details": [_property_to_json(item) for item in module.property_details],
                "ast_refs": [
                    {
                        "kind": ref.kind,
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in module.ast_refs
                ],
            }
            for module in modules
        ],
    }
    atomic_write_text(facts_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return facts_path
