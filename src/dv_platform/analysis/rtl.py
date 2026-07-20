"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from dv_platform.analysis.discovery import ProjectInventory, build_verilator_dry_run_command
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    ProtocolProfile,
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
    RTLModule,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    VerificationTarget,
)
from dv_platform.core.security import append_audit_event, redact_text, redact_value

RTL_FACTS_SCHEMA_VERSION = 6
MIN_READABLE_RTL_FACTS_SCHEMA_VERSION = 1
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
    root: ElementTree.Element
    element: ElementTree.Element
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
) -> tuple[RTLModule, ...]:
    """Extract conservative, specialization-aware module facts from Verilator XML."""

    raw_candidates: list[tuple[Path, ElementTree.Element, ElementTree.Element, str, str, tuple[RTLParameter, ...]]] = []
    for xml_file in xml_files:
        tree = ElementTree.parse(xml_file)
        root = tree.getroot()
        for element in root.iter():
            if _local_name(element.tag) != "module":
                continue
            original_name = element.attrib.get("origName") or element.attrib.get("name")
            elaborated_name = element.attrib.get("name") or original_name
            if not original_name or not elaborated_name:
                continue
            parameters = _parameter_details(element, root)
            raw_candidates.append((xml_file, root, element, original_name, elaborated_name, parameters))

    unique: dict[
        tuple[str, str, tuple[tuple[str, str | None], ...]],
        tuple[Path, ElementTree.Element, ElementTree.Element, str, str, tuple[RTLParameter, ...]],
    ] = {}
    for item in raw_candidates:
        signature = tuple((parameter.name, parameter.default_value) for parameter in item[5] if not parameter.local)
        unique.setdefault((item[3], item[4], signature), item)
    original_counts: dict[str, int] = {}
    for item in unique.values():
        original_counts[item[3]] = original_counts.get(item[3], 0) + 1

    candidates: list[_ModuleCandidate] = []
    for xml_file, root, element, original_name, elaborated_name, parameters in unique.values():
        specialization_id = _specialization_id(original_name, elaborated_name, parameters)
        identity = (
            original_name if original_counts[original_name] == 1 else f"{original_name}__spec_{specialization_id[:8]}"
        )
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

    candidates_by_root: dict[int, dict[str, _ModuleCandidate]] = {}
    for candidate in candidates:
        candidates_by_root.setdefault(id(candidate.root), {})[candidate.elaborated_name] = candidate

    modules: dict[str, RTLModule] = {}
    for candidate in candidates:
        element = candidate.element
        root = candidate.root
        name = candidate.identity
        ports = _port_names(element)
        port_details = _port_details(element, root)
        clock_details = _clock_details(port_details, element)
        reset_details = _reset_details(port_details, element)
        ast_refs = _evidence_refs(candidate.xml_file, element, name)
        control_domains, procedural_blocks = _control_domains_and_blocks(element)
        assignments = _assignment_details(element)
        memories = _memory_details(element, root)
        memory_accesses = _memory_accesses(name, memories, assignments, procedural_blocks, ast_refs)
        memories = _memories_with_access_policy(memories, memory_accesses)
        root_candidates = candidates_by_root.get(id(root), {})
        instances = _instance_details(element, root, root_candidates)
        cdc_paths = _cdc_paths(name, procedural_blocks, control_domains, ast_refs)
        modules[name] = RTLModule(
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
            type_details=_type_details(element, root),
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
            generate_scopes=_generate_scopes(element, instances),
            imports=_imports(element),
            protocols=_protocols(name, port_details, control_domains, ast_refs, protocol_profiles),
            assertions=_matching_element_summaries(element, "assert"),
            covers=_matching_element_summaries(element, "cover"),
            ast_refs=ast_refs,
        )

    return tuple(modules[name] for name in sorted(modules))


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


def _design_unit_kind(element: ElementTree.Element) -> str:
    return str(element.attrib.get("designUnitKind") or element.attrib.get("kind") or "module").lower()


def write_normalized_rtl_facts(
    config: CLIConfig,
    modules: tuple[RTLModule, ...],
    verilator_version: str | None = None,
) -> Path:
    """Persist normalized RTL facts for planning and claim checking."""

    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    facts_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": RTL_FACTS_SCHEMA_VERSION,
        "min_reader_schema_version": MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
        "verilator_version": verilator_version,
        "verilator_compatibility": classify_verilator_version(verilator_version),
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
                "assertions": list(module.assertions),
                "covers": list(module.covers),
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


def write_rtl_facts_summary(
    config: CLIConfig,
    modules: tuple[RTLModule, ...],
    verilator_version: str | None = None,
) -> Path:
    """Persist a compact machine-readable summary of normalized RTL facts."""

    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": RTL_FACTS_SCHEMA_VERSION,
        "verilator_version": verilator_version,
        "verilator_compatibility": classify_verilator_version(verilator_version),
        "module_count": len(modules),
        "totals": {
            "ports": sum(len(module.ports) for module in modules),
            "structured_ports": sum(len(module.port_details) for module in modules),
            "parameters": sum(len(module.parameter_details) for module in modules),
            "types": sum(len(module.type_details) for module in modules),
            "memories": sum(len(module.memories) for module in modules),
            "memory_accesses": sum(len(module.memory_accesses) for module in modules),
            "clocks": sum(len(module.clocks) for module in modules),
            "structured_clocks": sum(len(module.clock_details) for module in modules),
            "resets": sum(len(module.resets) for module in modules),
            "structured_resets": sum(len(module.reset_details) for module in modules),
            "semantic_features": sum(len(module.semantic_features) for module in modules),
            "unsupported_semantic_features": sum(
                1
                for module in modules
                for feature in module.semantic_features
                if not feature.generation_supported and not feature.supported_targets
            ),
            "target_conditional_semantic_features": sum(
                1 for module in modules for feature in module.semantic_features if feature.supported_targets
            ),
            "instances": sum(len(module.instances) for module in modules),
            "structured_instances": sum(len(module.instance_details) for module in modules),
            "continuous_assignments": sum(len(module.continuous_assignments) for module in modules),
            "structured_assignments": sum(len(module.assignment_details) for module in modules),
            "procedural_blocks": sum(len(module.procedural_blocks) for module in modules),
            "structured_procedural_blocks": sum(len(module.procedural_block_details) for module in modules),
            "control_domains": sum(len(module.control_domains) for module in modules),
            "cdc_paths": sum(len(module.cdc_paths) for module in modules),
            "unsafe_cdc_paths": sum(1 for module in modules for path in module.cdc_paths if not path.safe),
            "generate_scopes": sum(len(module.generate_scopes) for module in modules),
            "protocols": sum(len(module.protocols) for module in modules),
            "assertions": sum(len(module.assertions) for module in modules),
            "covers": sum(len(module.covers) for module in modules),
        },
        "modules": [
            {
                "name": module.name,
                "original_name": module.original_name,
                "elaborated_name": module.elaborated_name,
                "specialization_id": module.specialization_id,
                "ports": len(module.ports),
                "structured_ports": len(module.port_details),
                "clocks": list(module.clocks),
                "resets": [
                    {
                        "name": reset.name,
                        "active_low": reset.active_low,
                        "classification": reset.classification,
                        "confidence": reset.confidence,
                    }
                    for reset in module.reset_details
                ],
                "semantic_features": [
                    {
                        "kind": feature.kind,
                        "name": feature.name,
                        "confidence": feature.confidence,
                        "generation_supported": feature.generation_supported,
                        "supported_targets": [str(target) for target in feature.supported_targets],
                    }
                    for feature in module.semantic_features
                ],
                "instances": len(module.instances),
                "child_modules": [
                    instance.module_name for instance in module.instance_details if instance.module_name is not None
                ],
                "parameters": [
                    {"name": parameter.name, "default_value": parameter.default_value}
                    for parameter in module.parameter_details
                ],
                "memories": [
                    {
                        "name": memory.name,
                        "element_width": memory.element_width,
                        "depth": memory.depth,
                        "read_during_write": memory.read_during_write,
                    }
                    for memory in module.memories
                ],
                "memory_accesses": [access.access_id for access in module.memory_accesses],
                "control_domains": [domain.domain_id for domain in module.control_domains],
                "cdc_paths": [path.path_id for path in module.cdc_paths],
                "generate_scopes": [scope.scope_id for scope in module.generate_scopes],
                "protocols": [protocol.protocol_id for protocol in module.protocols],
                "continuous_assignments": len(module.continuous_assignments),
                "procedural_blocks": len(module.procedural_blocks),
                "assertions": len(module.assertions),
                "covers": len(module.covers),
            }
            for module in modules
        ],
    }
    atomic_write_text(
        summary_path,
        json.dumps(redact_value(config, payload), indent=2, sort_keys=True) + "\n",
    )
    return summary_path


def read_normalized_rtl_facts(config: CLIConfig) -> tuple[RTLModule, ...]:
    """Read normalized RTL facts from the configured work directory."""

    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    _validate_rtl_facts_schema(payload)
    return tuple(_module_from_json(item) for item in payload.get("modules", ()))


def classify_verilator_version(version: str | None) -> dict[str, object]:
    """Classify a Verilator version against the XML adapter's tested major range."""

    match = re.search(r"\bVerilator\s+(\d+)(?:\.|\b)", version or "", flags=re.IGNORECASE)
    major = int(match.group(1)) if match else None
    status = (
        "supported"
        if major is not None and VERILATOR_MIN_TESTED_MAJOR <= major <= VERILATOR_MAX_TESTED_MAJOR
        else "unsupported"
        if major is not None
        else "unknown"
    )
    return {
        "status": status,
        "detected_major": major,
        "minimum_tested_major": VERILATOR_MIN_TESTED_MAJOR,
        "maximum_tested_major": VERILATOR_MAX_TESTED_MAJOR,
    }


def _validate_rtl_facts_schema(payload: dict[str, Any]) -> None:
    schema_version = int(payload.get("schema_version", MIN_READABLE_RTL_FACTS_SCHEMA_VERSION))
    min_reader_schema_version = int(payload.get("min_reader_schema_version", MIN_READABLE_RTL_FACTS_SCHEMA_VERSION))
    if schema_version < MIN_READABLE_RTL_FACTS_SCHEMA_VERSION:
        raise ValueError(
            "RTL facts schema is too old: "
            f"schema_version={schema_version}, minimum_supported={MIN_READABLE_RTL_FACTS_SCHEMA_VERSION}"
        )
    if min_reader_schema_version > RTL_FACTS_SCHEMA_VERSION:
        raise ValueError(
            "RTL facts require a newer reader: "
            f"min_reader_schema_version={min_reader_schema_version}, reader_schema_version={RTL_FACTS_SCHEMA_VERSION}"
        )
    if schema_version > RTL_FACTS_SCHEMA_VERSION:
        raise ValueError(
            "RTL facts were written by a newer schema: "
            f"schema_version={schema_version}, reader_schema_version={RTL_FACTS_SCHEMA_VERSION}"
        )


def write_verilator_failure_summary(config: CLIConfig, run_result: VerilatorRunResult) -> Path:
    """Persist a machine-readable Verilator failure summary."""

    summary_path = config.work_dir / "runs" / "analyze-rtl" / "verilator-failure.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": "verilator",
        "command": list(run_result.command),
        "return_code": run_result.return_code,
        "verilator_version": run_result.version,
        "stdout_log": str(run_result.stdout_log),
        "stderr_log": str(run_result.stderr_log),
        "version_log": str(run_result.version_log),
        "xml_files": [str(path) for path in run_result.xml_files],
        "stdout_tail": _text_tail(run_result.stdout_log),
        "stderr_tail": _text_tail(run_result.stderr_log),
    }
    atomic_write_text(
        summary_path,
        json.dumps(redact_value(config, payload), indent=2, sort_keys=True) + "\n",
    )
    return summary_path


def _port_names(module_element: ElementTree.Element) -> tuple[str, ...]:
    ports: list[str] = []
    for element in module_element.iter():
        tag = _local_name(element.tag)
        direction = element.attrib.get("dir") or element.attrib.get("direction")
        name = element.attrib.get("name") or element.attrib.get("origName")
        if tag in {"port", "var"} and direction in {"input", "output", "inout", "ref"} and name:
            ports.append(name)
    return tuple(dict.fromkeys(ports))


def _port_details(module_element: ElementTree.Element, root: ElementTree.Element) -> tuple[RTLPort, ...]:
    ports: list[RTLPort] = []
    seen: set[str] = set()
    for element in module_element.iter():
        tag = _local_name(element.tag)
        direction = element.attrib.get("dir") or element.attrib.get("direction")
        name = element.attrib.get("name") or element.attrib.get("origName")
        if tag not in {"port", "var"} or direction not in {"input", "output", "inout", "ref"} or not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        dtype_id = element.attrib.get("dtype_id")
        dtype = _dtype_by_id(root, dtype_id) if dtype_id else None
        left = dtype.attrib.get("left") if dtype is not None else None
        right = dtype.attrib.get("right") if dtype is not None else None
        packed_range = f"{left}:{right}" if left is not None and right is not None else None
        ports.append(
            RTLPort(
                name=name,
                direction=direction,
                dtype_id=dtype_id,
                data_type=_local_name(dtype.tag) if dtype is not None else None,
                width=_packed_width(left, right),
                signed=dtype is not None and dtype.attrib.get("signed") == "true",
                packed_range=packed_range,
                source_location=_source_location(element),
            )
        )
    return tuple(ports)


_UNSUPPORTED_FEATURE_TAGS = {
    "arraysel": "memory_or_unpacked_array",
    "case": "case_statement",
    "enumdtype": "enum_type",
    "ifacerefdtype": "interface_or_modport",
    "memberdtype": "struct_or_union",
    "structdtype": "struct_or_union",
    "unpackarraydtype": "memory_or_unpacked_array",
    "uniondtype": "struct_or_union",
}

_BLACK_BOX_SAFE_TARGETS = (
    VerificationTarget.COCOTB,
    VerificationTarget.SYSTEMVERILOG,
    VerificationTarget.UVM,
    VerificationTarget.VERILOG,
    VerificationTarget.FORMAL,
)
_FEATURE_TARGETS = {
    "case_statement": _BLACK_BOX_SAFE_TARGETS,
    "memory_or_unpacked_array": _BLACK_BOX_SAFE_TARGETS,
    "enum_type": (VerificationTarget.SYSTEMVERILOG, VerificationTarget.UVM),
    "struct_or_union": (VerificationTarget.SYSTEMVERILOG, VerificationTarget.UVM),
    "interface_or_modport": (VerificationTarget.SYSTEMVERILOG, VerificationTarget.UVM),
}


def _semantic_features(
    module_element: ElementTree.Element,
    root: ElementTree.Element,
) -> tuple[RTLSemanticFeature, ...]:
    candidates: list[ElementTree.Element] = list(module_element.iter())
    dtype_ids = {
        dtype_id for element in module_element.iter() if (dtype_id := element.attrib.get("dtype_id")) is not None
    }
    for dtype_id in sorted(dtype_ids):
        dtype = _dtype_by_id(root, dtype_id)
        if dtype is not None:
            candidates.extend(dtype.iter())

    features: list[RTLSemanticFeature] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for element in candidates:
        tag = _local_name(element.tag).lower()
        kind = _UNSUPPORTED_FEATURE_TAGS.get(tag)
        if kind is None:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        source_location = _source_location(element)
        key = (kind, name, source_location)
        if key in seen:
            continue
        seen.add(key)
        features.append(
            RTLSemanticFeature(
                kind=kind,
                name=name,
                source_location=source_location,
                confidence="parser",
                generation_supported=False,
                supported_targets=_FEATURE_TARGETS.get(kind, ()),
            )
        )
    return tuple(features)


def _clock_details(
    ports: tuple[RTLPort, ...],
    module_element: ElementTree.Element,
) -> tuple[RTLClock, ...]:
    edges, reset_controls = _sensitivity_controls(module_element)
    heuristic_names = {port.name for port in ports if port.direction == "input" and _looks_like_clock(port.name)}
    sensitivity_names = set(edges) - set(reset_controls)
    if not sensitivity_names and len(edges) == 1:
        sensitivity_names = set(edges)
    names = heuristic_names | sensitivity_names
    return tuple(
        RTLClock(
            name=port.name,
            direction=port.direction,
            width=port.width,
            source_location=port.source_location,
            classification="sensitivity" if port.name in sensitivity_names else "name_heuristic",
            confidence="high" if port.name in sensitivity_names else "low",
        )
        for port in ports
        if port.direction == "input" and port.name in names
    )


def _reset_details(
    ports: tuple[RTLPort, ...],
    module_element: ElementTree.Element,
) -> tuple[RTLReset, ...]:
    _edges, reset_controls = _sensitivity_controls(module_element)
    heuristic_names = {port.name for port in ports if port.direction == "input" and _looks_like_reset(port.name)}
    sensitivity_names = set(reset_controls)
    names = heuristic_names | sensitivity_names
    return tuple(
        RTLReset(
            name=port.name,
            direction=port.direction,
            width=port.width,
            active_low=reset_controls.get(port.name, _reset_active_low(port.name)),
            source_location=port.source_location,
            classification="sensitivity" if port.name in sensitivity_names else "name_heuristic",
            confidence="high" if port.name in sensitivity_names else "low",
        )
        for port in ports
        if port.direction == "input" and port.name in names
    )


def _sensitivity_controls(module_element: ElementTree.Element) -> tuple[dict[str, str], dict[str, bool]]:
    edges: dict[str, str] = {}
    reset_controls: dict[str, bool] = {}
    for block in module_element.iter():
        if _local_name(block.tag) not in {"always", "alwaysff"}:
            continue
        block_edges: dict[str, str] = {}
        for item in block.iter():
            if _local_name(item.tag) != "senitem":
                continue
            signal = next(
                (
                    child.attrib.get("name") or child.attrib.get("origName")
                    for child in item.iter()
                    if _local_name(child.tag) == "varref"
                ),
                None,
            )
            if signal:
                edge = str(item.attrib.get("edgeType", "")).lower()
                block_edges[signal] = edge
                edges[signal] = edge
        first_if = next((item for item in block.iter() if _local_name(item.tag) == "if"), None)
        if first_if is None or len(block_edges) < 2 or not list(first_if):
            continue
        condition = list(first_if)[0]
        signal = next(
            (
                item.attrib.get("name") or item.attrib.get("origName")
                for item in condition.iter()
                if _local_name(item.tag) == "varref"
            ),
            None,
        )
        if signal not in block_edges:
            continue
        condition_kind = _local_name(condition.tag)
        active_low = condition_kind in {"not", "lognot"} or block_edges[signal] == "neg"
        reset_controls[signal] = active_low
    return edges, reset_controls


def _text_tail(path: Path, max_lines: int = 20) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]


def _module_from_json(data: dict[str, Any]) -> RTLModule:
    return RTLModule(
        name=str(data["name"]),
        original_name=str(data["original_name"]) if data.get("original_name") is not None else None,
        elaborated_name=str(data["elaborated_name"]) if data.get("elaborated_name") is not None else None,
        specialization_id=(str(data["specialization_id"]) if data.get("specialization_id") is not None else None),
        design_unit_kind=str(data.get("design_unit_kind", "module")),
        source=Path(str(data["source"])) if data.get("source") is not None else None,
        ports=tuple(str(item) for item in data.get("ports", ())),
        parameters=tuple(str(item) for item in data.get("parameters", ())),
        parameter_details=tuple(_parameter_from_json(item) for item in data.get("parameter_details", ())),
        type_details=tuple(_type_from_json(item) for item in data.get("type_details", ())),
        memories=tuple(_memory_from_json(item) for item in data.get("memories", ())),
        memory_accesses=tuple(_memory_access_from_json(item) for item in data.get("memory_accesses", ())),
        clocks=tuple(str(item) for item in data.get("clocks", ())),
        resets=tuple(str(item) for item in data.get("resets", ())),
        clock_details=tuple(_clock_from_json(item) for item in data.get("clock_details", ())),
        reset_details=tuple(_reset_from_json(item) for item in data.get("reset_details", ())),
        semantic_features=tuple(_semantic_feature_from_json(item) for item in data.get("semantic_features", ())),
        instances=tuple(str(item) for item in data.get("instances", ())),
        instance_details=tuple(_instance_from_json(item) for item in data.get("instance_details", ())),
        continuous_assignments=tuple(str(item) for item in data.get("continuous_assignments", ())),
        assignment_details=tuple(_assignment_from_json(item) for item in data.get("assignment_details", ())),
        procedural_blocks=tuple(str(item) for item in data.get("procedural_blocks", ())),
        procedural_block_details=tuple(
            _procedural_block_from_json(item) for item in data.get("procedural_block_details", ())
        ),
        control_domains=tuple(_control_domain_from_json(item) for item in data.get("control_domains", ())),
        cdc_paths=tuple(_cdc_path_from_json(item) for item in data.get("cdc_paths", ())),
        generate_scopes=tuple(_generate_scope_from_json(item) for item in data.get("generate_scopes", ())),
        imports=tuple(str(item) for item in data.get("imports", ())),
        protocols=tuple(_protocol_from_json(item) for item in data.get("protocols", ())),
        assertions=tuple(str(item) for item in data.get("assertions", ())),
        covers=tuple(str(item) for item in data.get("covers", ())),
        ast_refs=tuple(_evidence_from_json(item) for item in data.get("ast_refs", ())),
        port_details=tuple(_port_from_json(item) for item in data.get("port_details", ())),
    )


def _port_from_json(data: dict[str, Any]) -> RTLPort:
    return RTLPort(
        name=str(data["name"]),
        direction=str(data["direction"]),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        packed_range=str(data["packed_range"]) if data.get("packed_range") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _clock_from_json(data: dict[str, Any]) -> RTLClock:
    return RTLClock(
        name=str(data["name"]),
        direction=str(data["direction"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
        confidence=str(data.get("confidence", "low")),
    )


def _reset_from_json(data: dict[str, Any]) -> RTLReset:
    return RTLReset(
        name=str(data["name"]),
        direction=str(data["direction"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        active_low=bool(data["active_low"]) if data.get("active_low") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
        confidence=str(data.get("confidence", "low")),
    )


def _parameter_from_json(data: dict[str, Any]) -> RTLParameter:
    return RTLParameter(
        name=str(data["name"]),
        default_value=str(data["default_value"]) if data.get("default_value") is not None else None,
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        local=bool(data.get("local", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _memory_from_json(data: dict[str, Any]) -> RTLMemory:
    return RTLMemory(
        name=str(data["name"]),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        element_width=int(data["element_width"]) if data.get("element_width") is not None else None,
        depth=int(data["depth"]) if data.get("depth") is not None else None,
        address_width=int(data["address_width"]) if data.get("address_width") is not None else None,
        read_during_write=str(data.get("read_during_write", "unknown")),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _memory_access_to_json(access: RTLMemoryAccess) -> dict[str, object]:
    return {
        "access_id": access.access_id,
        "memory": access.memory,
        "kind": access.kind,
        "address_signals": list(access.address_signals),
        "data_signals": list(access.data_signals),
        "enable_signals": list(access.enable_signals),
        "domain_id": access.domain_id,
        "synchronous": access.synchronous,
        "source_location": access.source_location,
        "evidence_refs": [_evidence_to_json(ref) for ref in access.evidence_refs],
    }


def _memory_access_from_json(data: dict[str, Any]) -> RTLMemoryAccess:
    return RTLMemoryAccess(
        access_id=str(data["access_id"]),
        memory=str(data["memory"]),
        kind=str(data["kind"]),
        address_signals=tuple(str(item) for item in data.get("address_signals", ())),
        data_signals=tuple(str(item) for item in data.get("data_signals", ())),
        enable_signals=tuple(str(item) for item in data.get("enable_signals", ())),
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
        synchronous=bool(data.get("synchronous", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _type_to_json(item: RTLType) -> dict[str, object]:
    return {
        "type_id": item.type_id,
        "name": item.name,
        "kind": item.kind,
        "width": item.width,
        "signed": item.signed,
        "members": list(item.members),
        "enum_values": list(item.enum_values),
        "source_location": item.source_location,
    }


def _type_from_json(data: dict[str, Any]) -> RTLType:
    return RTLType(
        type_id=str(data["type_id"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        kind=str(data["kind"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        members=tuple(str(item) for item in data.get("members", ())),
        enum_values=tuple(str(item) for item in data.get("enum_values", ())),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _semantic_feature_from_json(data: dict[str, Any]) -> RTLSemanticFeature:
    return RTLSemanticFeature(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        confidence=str(data.get("confidence", "parser")),
        generation_supported=bool(data.get("generation_supported", False)),
        supported_targets=tuple(VerificationTarget(str(item)) for item in data.get("supported_targets", ())),
    )


def _instance_from_json(data: dict[str, Any]) -> RTLInstance:
    return RTLInstance(
        name=str(data["name"]),
        module_name=str(data["module_name"]) if data.get("module_name") is not None else None,
        elaborated_module_name=(
            str(data["elaborated_module_name"]) if data.get("elaborated_module_name") is not None else None
        ),
        plan_module_name=str(data["plan_module_name"]) if data.get("plan_module_name") is not None else None,
        specialization_id=(str(data["specialization_id"]) if data.get("specialization_id") is not None else None),
        parameter_bindings=tuple(
            RTLParameterBinding(
                name=str(item["name"]),
                value=str(item["value"]) if item.get("value") is not None else None,
            )
            for item in data.get("parameter_bindings", ())
        ),
        kind=str(data["kind"]) if data.get("kind") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        connections=tuple(_connection_from_json(item) for item in data.get("connections", ())),
    )


def _connection_from_json(data: dict[str, Any]) -> RTLConnection:
    expression_data = data.get("expression")
    return RTLConnection(
        port_name=str(data["port_name"]),
        direction=str(data["direction"]) if data.get("direction") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expression=_expression_from_json(expression_data) if isinstance(expression_data, dict) else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _assignment_from_json(data: dict[str, Any]) -> RTLAssignment:
    return RTLAssignment(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        lhs_signals=tuple(str(item) for item in data.get("lhs_signals", ())),
        rhs_signals=tuple(str(item) for item in data.get("rhs_signals", ())),
        expressions=tuple(_expression_from_json(item) for item in data.get("expressions", ())),
    )


def _expression_from_json(data: dict[str, Any]) -> RTLExpression:
    return RTLExpression(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        children=tuple(_expression_from_json(item) for item in data.get("children", ())),
    )


def _expression_to_json(expression: RTLExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "value": expression.value,
        "dtype_id": expression.dtype_id,
        "source_location": expression.source_location,
        "children": [_expression_to_json(child) for child in expression.children],
    }


def _procedural_block_from_json(data: dict[str, Any]) -> RTLProceduralBlock:
    return RTLProceduralBlock(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expressions=tuple(_expression_from_json(item) for item in data.get("expressions", ())),
        patterns=tuple(_procedural_pattern_from_json(item) for item in data.get("patterns", ())),
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
    )


def _procedural_pattern_from_json(data: dict[str, Any]) -> RTLProceduralPattern:
    return RTLProceduralPattern(
        kind=str(data["kind"]),
        target=str(data["target"]),
        control=str(data["control"]) if data.get("control") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        source=str(data["source"]) if data.get("source") is not None else None,
        confidence=str(data.get("confidence", "shape")),
    )


def _control_domain_from_json(data: dict[str, Any]) -> RTLControlDomain:
    return RTLControlDomain(
        domain_id=str(data["domain_id"]),
        clock=str(data["clock"]),
        clock_edge=str(data.get("clock_edge", "pos")),
        reset=str(data["reset"]) if data.get("reset") is not None else None,
        reset_edge=str(data["reset_edge"]) if data.get("reset_edge") is not None else None,
        reset_active_low=bool(data["reset_active_low"]) if data.get("reset_active_low") is not None else None,
        asynchronous_reset=bool(data.get("asynchronous_reset", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _cdc_path_to_json(path: RTLCDCPath) -> dict[str, object]:
    return {
        "path_id": path.path_id,
        "signal": path.signal,
        "source_domain": path.source_domain,
        "destination_domain": path.destination_domain,
        "classification": path.classification,
        "synchronizer_stages": path.synchronizer_stages,
        "stage_signals": list(path.stage_signals),
        "safe": path.safe,
        "reset_compatible": path.reset_compatible,
        "source_location": path.source_location,
        "evidence_refs": [_evidence_to_json(ref) for ref in path.evidence_refs],
    }


def _cdc_path_from_json(data: dict[str, Any]) -> RTLCDCPath:
    return RTLCDCPath(
        path_id=str(data["path_id"]),
        signal=str(data["signal"]),
        source_domain=str(data["source_domain"]),
        destination_domain=str(data["destination_domain"]),
        classification=str(data.get("classification", "direct")),
        synchronizer_stages=int(data.get("synchronizer_stages", 0)),
        stage_signals=tuple(str(item) for item in data.get("stage_signals", ())),
        safe=bool(data.get("safe", False)),
        reset_compatible=bool(data["reset_compatible"]) if data.get("reset_compatible") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _generate_scope_to_json(scope: RTLGenerateScope) -> dict[str, object]:
    return {
        "scope_id": scope.scope_id,
        "name": scope.name,
        "kind": scope.kind,
        "source_location": scope.source_location,
        "instance_names": list(scope.instance_names),
    }


def _generate_scope_from_json(data: dict[str, Any]) -> RTLGenerateScope:
    return RTLGenerateScope(
        scope_id=str(data["scope_id"]),
        name=str(data["name"]),
        kind=str(data["kind"]),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        instance_names=tuple(str(item) for item in data.get("instance_names", ())),
    )


def _protocol_from_json(data: dict[str, Any]) -> RTLProtocol:
    return RTLProtocol(
        protocol_id=str(data["protocol_id"]),
        kind=str(data["kind"]),
        name=str(data["name"]),
        role=str(data["role"]),
        valid=str(data["valid"]),
        ready=str(data["ready"]),
        data=str(data["data"]) if data.get("data") is not None else None,
        data_width=int(data["data_width"]) if data.get("data_width") is not None else None,
        clock=str(data["clock"]) if data.get("clock") is not None else None,
        reset=str(data["reset"]) if data.get("reset") is not None else None,
        confidence=str(data.get("confidence", "naming")),
        profile=str(data.get("profile", "builtin")),
        signal_map=tuple((str(item[0]), str(item[1])) for item in data.get("signal_map", ())),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _evidence_from_json(data: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind(str(data["kind"])),
        source_id=str(data["source_id"]),
        locator=str(data["locator"]),
        summary=str(data["summary"]) if data.get("summary") is not None else None,
    )


def _evidence_to_json(ref: EvidenceRef) -> dict[str, object]:
    return {
        "kind": str(ref.kind),
        "source_id": ref.source_id,
        "locator": ref.locator,
        "summary": ref.summary,
    }


def _evidence_refs(xml_file: Path, module_element: ElementTree.Element, module_name: str) -> tuple[EvidenceRef, ...]:
    refs = [
        _evidence_ref(
            xml_file,
            "module",
            module_name,
            module_element,
            f"{module_name} module declaration",
        )
    ]
    for element in module_element.iter():
        if element is module_element:
            continue

        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        direction = element.attrib.get("dir") or element.attrib.get("direction")
        if tag in {"port", "var"} and direction in {"input", "output", "inout", "ref"} and name:
            refs.append(_evidence_ref(xml_file, "port", f"{module_name}.{name}", element, f"{module_name}.{name} port"))
        elif tag in {"var", "parameter", "localparam"} and _is_parameter(element) and name:
            refs.append(
                _evidence_ref(
                    xml_file, "parameter", f"{module_name}.{name}", element, f"{module_name}.{name} parameter"
                )
            )
        elif tag in {"instance", "cell"} and name:
            refs.append(
                _evidence_ref(xml_file, "instance", f"{module_name}.{name}", element, f"{module_name}.{name} instance")
            )
        elif tag in {"assign", "contassign"}:
            refs.append(
                _evidence_ref(xml_file, "assignment", f"{module_name}.{tag}", element, f"{module_name} assignment")
            )
        elif tag in {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}:
            refs.append(
                _evidence_ref(xml_file, "procedure", f"{module_name}.{tag}", element, f"{module_name} procedure")
            )
        elif "assert" in tag:
            refs.append(
                _evidence_ref(xml_file, "assertion", f"{module_name}.{tag}", element, f"{module_name} assertion")
            )
        elif "cover" in tag:
            refs.append(_evidence_ref(xml_file, "cover", f"{module_name}.{tag}", element, f"{module_name} cover"))
        elif tag in _UNSUPPORTED_FEATURE_TAGS:
            feature = _UNSUPPORTED_FEATURE_TAGS[tag]
            refs.append(
                _evidence_ref(
                    xml_file,
                    "semantic-feature",
                    f"{module_name}.{feature}",
                    element,
                    f"{module_name} uses {feature}",
                )
            )
    return tuple(refs)


def _evidence_ref(
    xml_file: Path,
    category: str,
    key: str,
    element: ElementTree.Element,
    summary: str,
) -> EvidenceRef:
    location = _source_location(element)
    locator = f"{category}:{key}"
    if location:
        locator = f"{locator}@{location}"
    return EvidenceRef(
        kind=EvidenceKind.VERILATOR_AST,
        source_id=str(xml_file),
        locator=locator,
        summary=summary,
    )


def _detect_verilator_version(config: CLIConfig) -> str | None:
    command = (*shlex.split(config.verilator_executable), "--version")
    try:
        completed = subprocess.run(
            command,
            cwd=config.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if completed.returncode != 0:
        return None
    output = completed.stdout.strip() or completed.stderr.strip()
    return output.splitlines()[0] if output else None


def _parameter_names(module_element: ElementTree.Element) -> tuple[str, ...]:
    parameters: list[str] = []
    for element in module_element.iter():
        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        if tag in {"var", "parameter", "localparam"} and _is_parameter(element) and name:
            parameters.append(name)
    return tuple(dict.fromkeys(parameters))


def _parameter_details(
    module_element: ElementTree.Element,
    root: ElementTree.Element,
) -> tuple[RTLParameter, ...]:
    parameters: list[RTLParameter] = []
    seen: set[str] = set()
    for element in module_element.iter():
        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        if tag not in {"var", "parameter", "localparam"} or not _is_parameter(element) or not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        dtype_id = element.attrib.get("dtype_id")
        dtype = _dtype_by_id(root, dtype_id)
        default_expression = next(iter(element), None)
        parameters.append(
            RTLParameter(
                name=name,
                default_value=(
                    _expression_value(default_expression, _local_name(default_expression.tag))
                    if default_expression is not None
                    else None
                ),
                dtype_id=dtype_id,
                data_type=_local_name(dtype.tag) if dtype is not None else None,
                width=_dtype_width(dtype),
                signed=dtype is not None and dtype.attrib.get("signed") == "true",
                local=element.attrib.get("localparam") == "true" or tag == "localparam",
                source_location=_source_location(element),
            )
        )
    return tuple(parameters)


def _memory_details(
    module_element: ElementTree.Element,
    root: ElementTree.Element,
) -> tuple[RTLMemory, ...]:
    memories: list[RTLMemory] = []
    seen: set[str] = set()
    for element in list(module_element):
        if _local_name(element.tag) != "var":
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        dtype_id = element.attrib.get("dtype_id")
        dtype = _dtype_by_id(root, dtype_id)
        if not name or name in seen or dtype is None or _local_name(dtype.tag) != "unpackarraydtype":
            continue
        seen.add(name)
        element_dtype = _dtype_by_id(root, dtype.attrib.get("sub_dtype_id"))
        memories.append(
            RTLMemory(
                name=name,
                dtype_id=dtype_id,
                element_width=_dtype_width(element_dtype),
                depth=_unpacked_depth(dtype),
                address_width=_address_width(_unpacked_depth(dtype)),
                source_location=_source_location(element),
            )
        )
    return tuple(memories)


def _type_details(module_element: ElementTree.Element, root: ElementTree.Element) -> tuple[RTLType, ...]:
    dtype_ids = tuple(
        dict.fromkeys(
            dtype_id for element in module_element.iter() if (dtype_id := element.attrib.get("dtype_id")) is not None
        )
    )
    details: list[RTLType] = []
    for dtype_id in dtype_ids:
        dtype = _dtype_by_id(root, dtype_id)
        if dtype is None:
            continue
        kind = _local_name(dtype.tag)
        members = tuple(
            dict.fromkeys(
                name
                for child in dtype.iter()
                if _local_name(child.tag) in {"memberdtype", "member"}
                and (name := child.attrib.get("name") or child.attrib.get("origName")) is not None
            )
        )
        enum_values = tuple(
            dict.fromkeys(
                name
                for child in dtype.iter()
                if _local_name(child.tag) in {"enumitem", "enumitemref"}
                and (name := child.attrib.get("name") or child.attrib.get("origName")) is not None
            )
        )
        details.append(
            RTLType(
                type_id=dtype_id,
                name=dtype.attrib.get("name") or dtype.attrib.get("origName"),
                kind=kind,
                width=_dtype_width(dtype),
                signed=dtype.attrib.get("signed") == "true",
                members=members,
                enum_values=enum_values,
                source_location=_source_location(dtype),
            )
        )
    return tuple(details)


def _address_width(depth: int | None) -> int | None:
    if depth is None or depth < 1:
        return None
    return max(1, (depth - 1).bit_length())


def _is_parameter(element: ElementTree.Element) -> bool:
    return element.attrib.get("param") == "true" or element.attrib.get("localparam") == "true"


def _instance_names(
    module_element: ElementTree.Element,
    root: ElementTree.Element | None = None,
) -> tuple[str, ...]:
    instances: list[str] = []
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"instance", "cell"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        elaborated_name = _instance_module_name(element)
        module_name = _original_module_name(root, elaborated_name) or elaborated_name
        if name and module_name:
            instances.append(f"{name}:{module_name}")
        elif name:
            instances.append(name)
    return tuple(dict.fromkeys(instances))


def _instance_details(
    module_element: ElementTree.Element,
    root: ElementTree.Element | None = None,
    candidates: dict[str, _ModuleCandidate] | None = None,
) -> tuple[RTLInstance, ...]:
    instances: list[RTLInstance] = []
    seen: set[tuple[str, str | None]] = set()
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"instance", "cell"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        elaborated_name = _instance_module_name(element)
        module_name = _original_module_name(root, elaborated_name) or elaborated_name
        candidate = (candidates or {}).get(elaborated_name or "")
        if not name:
            continue
        key = (name, module_name)
        if key in seen:
            continue
        seen.add(key)
        instances.append(
            RTLInstance(
                name=name,
                module_name=module_name,
                elaborated_module_name=elaborated_name,
                plan_module_name=candidate.identity if candidate is not None else module_name,
                specialization_id=candidate.specialization_id if candidate is not None else None,
                parameter_bindings=(
                    tuple(
                        RTLParameterBinding(parameter.name, parameter.default_value)
                        for parameter in candidate.parameters
                        if not parameter.local
                    )
                    if candidate is not None
                    else ()
                ),
                kind=tag,
                source_location=_source_location(element),
                connections=_instance_connections(element),
            )
        )
    return tuple(instances)


def _instance_module_name(element: ElementTree.Element) -> str | None:
    return (
        element.attrib.get("moduleName")
        or element.attrib.get("modulename")
        or element.attrib.get("submodname")
        or element.attrib.get("dtypeName")
        or element.attrib.get("defName")
    )


def _original_module_name(root: ElementTree.Element | None, elaborated_name: str | None) -> str | None:
    if root is None or elaborated_name is None:
        return None
    return next(
        (
            element.attrib.get("origName")
            for element in root.iter()
            if _local_name(element.tag) == "module"
            and element.attrib.get("name") == elaborated_name
            and element.attrib.get("origName")
        ),
        None,
    )


def _instance_connections(element: ElementTree.Element) -> tuple[RTLConnection, ...]:
    connections: list[RTLConnection] = []
    for port in list(element):
        if _local_name(port.tag) != "port":
            continue
        port_name = port.attrib.get("name") or port.attrib.get("origName")
        if not port_name:
            continue
        expression_element = next(iter(port), None)
        expression = _expression_from_element(expression_element) if expression_element is not None else None
        direction = port.attrib.get("direction") or port.attrib.get("dir")
        direction = {"in": "input", "out": "output"}.get(str(direction), direction)
        connections.append(
            RTLConnection(
                port_name=port_name,
                direction=direction,
                signal_refs=_expression_signal_refs(expression) if expression is not None else (),
                expression=expression,
                source_location=_source_location(port),
            )
        )
    return tuple(connections)


def _generate_scopes(
    module_element: ElementTree.Element,
    instances: tuple[RTLInstance, ...],
) -> tuple[RTLGenerateScope, ...]:
    scopes: dict[str, RTLGenerateScope] = {}
    for element in module_element.iter():
        tag = _local_name(element.tag)
        if tag not in {"begin", "genfor", "genif", "generate", "scope"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        if not name or name.startswith("unnamedblk"):
            continue
        scopes.setdefault(
            name,
            RTLGenerateScope(
                scope_id=name,
                name=name,
                kind=tag,
                source_location=_source_location(element),
                instance_names=tuple(
                    instance.name
                    for instance in instances
                    if instance.name.startswith((f"{name}.", f"{name}__DOT__", f"{name}["))
                ),
            ),
        )
    for instance in instances:
        separator = "__DOT__" if "__DOT__" in instance.name else "." if "." in instance.name else None
        if separator is None:
            continue
        name = instance.name.split(separator, 1)[0]
        existing = scopes.get(name)
        members = tuple(
            item.name for item in instances if item.name.startswith((f"{name}.", f"{name}__DOT__", f"{name}["))
        )
        scopes[name] = RTLGenerateScope(
            scope_id=existing.scope_id if existing is not None else name,
            name=name,
            kind=existing.kind if existing is not None else "elaborated_scope",
            source_location=existing.source_location if existing is not None else instance.source_location,
            instance_names=members,
        )
    return tuple(scopes[name] for name in sorted(scopes))


def _imports(module_element: ElementTree.Element) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name
            for element in module_element.iter()
            if _local_name(element.tag) in {"import", "packageimport", "imported"}
            and (name := element.attrib.get("name") or element.attrib.get("package")) is not None
        )
    )


def _element_summaries(module_element: ElementTree.Element, tags: set[str]) -> tuple[str, ...]:
    summaries: list[str] = []
    for element in _module_child_elements(module_element, tags):
        tag = _local_name(element.tag)
        summaries.append(_element_summary(tag, element))
    return tuple(dict.fromkeys(summaries))


def _assignment_details(module_element: ElementTree.Element) -> tuple[RTLAssignment, ...]:
    assignments: list[RTLAssignment] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for element in _module_child_elements(module_element, {"assign", "contassign"}):
        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        source_location = _source_location(element)
        key = (tag, name, source_location)
        if key in seen:
            continue
        seen.add(key)
        expressions = _child_expressions(element)
        lhs_signals, rhs_signals = _assignment_signal_refs(expressions)
        assignments.append(
            RTLAssignment(
                kind=tag,
                name=name,
                source_location=source_location,
                summary=_element_summary(tag, element),
                lhs_signals=lhs_signals,
                rhs_signals=rhs_signals,
                expressions=expressions,
            )
        )
    return tuple(assignments)


def _module_child_elements(module_element: ElementTree.Element, tags: set[str]) -> tuple[ElementTree.Element, ...]:
    return tuple(child for child in list(module_element) if _local_name(child.tag) in tags)


def _child_expressions(element: ElementTree.Element) -> tuple[RTLExpression, ...]:
    return tuple(_expression_from_element(child) for child in list(element))


def _expression_from_element(element: ElementTree.Element, depth: int = 0, max_depth: int = 8) -> RTLExpression:
    kind = _local_name(element.tag)
    children: tuple[RTLExpression, ...] = ()
    if depth < max_depth:
        children = tuple(
            _expression_from_element(child, depth=depth + 1, max_depth=max_depth) for child in list(element)
        )
    return RTLExpression(
        kind=kind,
        name=element.attrib.get("name") or element.attrib.get("origName"),
        value=_expression_value(element, kind),
        dtype_id=element.attrib.get("dtype_id"),
        source_location=_source_location(element),
        children=children,
    )


def _expression_value(element: ElementTree.Element, kind: str) -> str | None:
    for key in ("value", "num", "text", "string"):
        value = element.attrib.get(key)
        if value is not None:
            return value
    if kind in {"const", "constint", "constant"}:
        value = element.attrib.get("name")
        if value is not None:
            return value
    text = (element.text or "").strip()
    return text or None


def _assignment_signal_refs(expressions: tuple[RTLExpression, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not expressions:
        return (), ()
    lhs = _written_signal_refs(expressions[-1])
    rhs = tuple(dict.fromkeys(ref for expression in expressions[:-1] for ref in _expression_signal_refs(expression)))
    return lhs, rhs


def _expression_signal_refs(expression: RTLExpression) -> tuple[str, ...]:
    refs: list[str] = []
    if expression.name is not None and _looks_like_signal_ref(expression):
        refs.append(expression.name)
    for child in expression.children:
        refs.extend(_expression_signal_refs(child))
    return tuple(refs)


def _looks_like_signal_ref(expression: RTLExpression) -> bool:
    kind = expression.kind.lower()
    if kind in {"varref", "ref", "sel", "arraysel", "bitsel"}:
        return expression.name is not None
    return kind.endswith("ref") and expression.name is not None


def _control_domains_and_blocks(
    module_element: ElementTree.Element,
) -> tuple[tuple[RTLControlDomain, ...], tuple[RTLProceduralBlock, ...]]:
    raw_blocks: list[ElementTree.Element] = []
    for element in module_element.iter():
        if element is not module_element and _local_name(element.tag) in {
            "always",
            "alwaysff",
            "alwayscomb",
            "alwayslat",
            "initial",
        }:
            raw_blocks.append(element)

    domains: list[RTLControlDomain] = []
    domain_keys: dict[tuple[object, ...], str] = {}
    block_domains: dict[int, str] = {}
    for element in raw_blocks:
        spec = _control_domain_spec(element)
        if spec is None:
            continue
        key = (
            spec.clock,
            spec.clock_edge,
            spec.reset,
            spec.reset_edge,
            spec.reset_active_low,
            spec.asynchronous_reset,
        )
        domain_id = domain_keys.get(key)
        if domain_id is None:
            domain_id = f"domain_{len(domains) + 1}"
            domain_keys[key] = domain_id
            domains.append(
                RTLControlDomain(
                    domain_id=domain_id,
                    clock=spec.clock,
                    clock_edge=spec.clock_edge,
                    reset=spec.reset,
                    reset_edge=spec.reset_edge,
                    reset_active_low=spec.reset_active_low,
                    asynchronous_reset=spec.asynchronous_reset,
                    source_location=spec.source_location,
                )
            )
        block_domains[id(element)] = domain_id
    return tuple(domains), _procedural_block_details(module_element, block_domains)


def _control_domain_spec(element: ElementTree.Element) -> RTLControlDomain | None:
    edges: dict[str, str] = {}
    for item in element.iter():
        if _local_name(item.tag) != "senitem":
            continue
        signal = next(
            (
                child.attrib.get("name") or child.attrib.get("origName")
                for child in item.iter()
                if _local_name(child.tag) == "varref"
            ),
            None,
        )
        if signal:
            edges[signal] = str(item.attrib.get("edgeType", "POS")).lower()
    if not edges:
        return None

    first_if = next((item for item in list(element) if _local_name(item.tag) == "if"), None)
    condition = list(first_if)[0] if first_if is not None and list(first_if) else None
    condition_signal = _first_signal_ref(_expression_from_element(condition)) if condition is not None else None
    reset = condition_signal if condition_signal in edges and len(edges) > 1 else None
    clock_candidates = tuple(signal for signal in edges if signal != reset)
    if len(clock_candidates) != 1:
        return None
    clock = clock_candidates[0]
    if (
        reset is None
        and condition_signal is not None
        and condition_signal != clock
        and _looks_like_reset(condition_signal)
    ):
        reset = condition_signal
    reset_edge = edges.get(reset) if reset is not None else None
    condition_kind = _local_name(condition.tag) if condition is not None else ""
    reset_active_low = None
    if reset is not None:
        reset_active_low = condition_kind in {"not", "lognot"} or reset_edge == "neg"
        if reset_edge is None and condition_kind not in {"not", "lognot"}:
            reset_active_low = _reset_active_low(reset)
    return RTLControlDomain(
        domain_id="",
        clock=clock,
        clock_edge=edges[clock] or "pos",
        reset=reset,
        reset_edge=reset_edge,
        reset_active_low=reset_active_low,
        asynchronous_reset=reset is not None and reset in edges,
        source_location=_source_location(element),
    )


def _procedural_block_details(
    module_element: ElementTree.Element,
    block_domains: dict[int, str] | None = None,
) -> tuple[RTLProceduralBlock, ...]:
    blocks: list[RTLProceduralBlock] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        source_location = _source_location(element)
        key = (tag, name, source_location)
        if key in seen:
            continue
        seen.add(key)
        expressions = _child_expressions(element)
        blocks.append(
            RTLProceduralBlock(
                kind=tag,
                name=name,
                source_location=source_location,
                summary=_element_summary(tag, element),
                signal_refs=tuple(
                    dict.fromkeys(ref for expression in expressions for ref in _expression_signal_refs(expression))
                ),
                expressions=expressions,
                patterns=_procedural_patterns(expressions),
                domain_id=(block_domains or {}).get(id(element)),
            )
        )
    return tuple(blocks)


def _memory_accesses(
    module_name: str,
    memories: tuple[RTLMemory, ...],
    assignments: tuple[RTLAssignment, ...],
    blocks: tuple[RTLProceduralBlock, ...],
    ast_refs: tuple[EvidenceRef, ...],
) -> tuple[RTLMemoryAccess, ...]:
    memory_names = {memory.name for memory in memories}
    if not memory_names:
        return ()
    raw: list[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None]] = []
    for assignment in assignments:
        raw.extend(
            _memory_accesses_from_assignment(
                assignment.expressions,
                memory_names,
                (),
                None,
                False,
                assignment.source_location,
            )
        )
    for block in blocks:
        for expression in block.expressions:
            raw.extend(
                _memory_accesses_from_expression(
                    expression,
                    memory_names,
                    (),
                    block.domain_id,
                    block.domain_id is not None,
                )
            )
    seen: set[tuple[object, ...]] = set()
    accesses: list[RTLMemoryAccess] = []
    for memory, kind, addresses, data, enables, domain_id, synchronous, location in raw:
        key = (memory, kind, addresses, data, enables, domain_id, location)
        if key in seen:
            continue
        seen.add(key)
        index = 1 + sum(1 for access in accesses if access.memory == memory and access.kind == kind)
        evidence = tuple(
            ref
            for ref in ast_refs
            if ref.locator.split("@", 1)[0].startswith(
                (f"procedure:{module_name}.", f"assignment:{module_name}.", f"semantic-feature:{module_name}.")
            )
        )
        accesses.append(
            RTLMemoryAccess(
                access_id=f"{module_name}:memory:{memory}:{kind}:{index}",
                memory=memory,
                kind=kind,
                address_signals=addresses,
                data_signals=data,
                enable_signals=enables,
                domain_id=domain_id,
                synchronous=synchronous,
                source_location=location,
                evidence_refs=evidence,
            )
        )
    return tuple(accesses)


def _memory_accesses_from_expression(
    expression: RTLExpression,
    memory_names: set[str],
    controls: tuple[str, ...],
    domain_id: str | None,
    synchronous: bool,
) -> tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None], ...]:
    if expression.kind in {"assign", "assigndly"}:
        return _memory_accesses_from_assignment(
            expression.children,
            memory_names,
            controls,
            domain_id,
            synchronous,
            expression.source_location,
        )
    if expression.kind == "if" and expression.children:
        condition_refs = _expression_signal_refs(expression.children[0])
        nested_controls = tuple(dict.fromkeys((*controls, *condition_refs)))
        return tuple(
            access
            for child in expression.children[1:]
            for access in _memory_accesses_from_expression(
                child,
                memory_names,
                nested_controls,
                domain_id,
                synchronous,
            )
        )
    selected = _memory_selection(expression, memory_names)
    accesses: list[
        tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None]
    ] = []
    if selected is not None:
        memory, addresses = selected
        accesses.append((memory, "read", addresses, (), controls, domain_id, synchronous, expression.source_location))
        return tuple(accesses)
    for child in expression.children:
        accesses.extend(_memory_accesses_from_expression(child, memory_names, controls, domain_id, synchronous))
    return tuple(accesses)


def _memory_accesses_from_assignment(
    expressions: tuple[RTLExpression, ...],
    memory_names: set[str],
    controls: tuple[str, ...],
    domain_id: str | None,
    synchronous: bool,
    source_location: str | None,
) -> tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None], ...]:
    if len(expressions) < 2:
        return ()
    rhs = expressions[:-1]
    lhs = expressions[-1]
    accesses: list[
        tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None]
    ] = []
    selected_lhs = _memory_selection(lhs, memory_names)
    if selected_lhs is not None:
        memory, addresses = selected_lhs
        rhs_refs = tuple(dict.fromkeys(ref for expression in rhs for ref in _expression_signal_refs(expression)))
        data = tuple(
            ref for ref in rhs_refs if ref not in memory_names and ref not in addresses and ref not in controls
        )
        accesses.append((memory, "write", addresses, data, controls, domain_id, synchronous, source_location))
    for expression in rhs:
        accesses.extend(_memory_accesses_from_expression(expression, memory_names, controls, domain_id, synchronous))
    if selected_lhs is None:
        accesses.extend(_memory_accesses_from_expression(lhs, memory_names, controls, domain_id, synchronous))
    return tuple(accesses)


def _memory_selection(expression: RTLExpression, memory_names: set[str]) -> tuple[str, tuple[str, ...]] | None:
    if expression.kind not in {"arraysel", "arrayselect"} or not expression.children:
        return None
    base_refs = _expression_signal_refs(expression.children[0])
    memory = next((name for name in base_refs if name in memory_names), None)
    if memory is None:
        return None
    addresses = tuple(dict.fromkeys(ref for child in expression.children[1:] for ref in _expression_signal_refs(child)))
    return memory, addresses


def _memories_with_access_policy(
    memories: tuple[RTLMemory, ...],
    accesses: tuple[RTLMemoryAccess, ...],
) -> tuple[RTLMemory, ...]:
    updated: list[RTLMemory] = []
    for memory in memories:
        reads = tuple(access for access in accesses if access.memory == memory.name and access.kind == "read")
        writes = tuple(access for access in accesses if access.memory == memory.name and access.kind == "write")
        policy = "not_applicable" if not reads or not writes else "unknown"
        updated.append(replace(memory, read_during_write=policy))
    return tuple(updated)


def _cdc_paths(
    module_name: str,
    blocks: tuple[RTLProceduralBlock, ...],
    domains: tuple[RTLControlDomain, ...],
    ast_refs: tuple[EvidenceRef, ...],
) -> tuple[RTLCDCPath, ...]:
    domain_by_id = {domain.domain_id: domain for domain in domains}
    flows: dict[str, tuple[set[str], set[str], tuple[tuple[str, tuple[str, ...]], ...]]] = {}
    for block in blocks:
        if block.domain_id is None:
            continue
        writes: set[str] = set()
        reads: set[str] = set()
        block_pairs: list[tuple[str, tuple[str, ...]]] = []
        for expression in block.expressions:
            _collect_signal_flow(expression, writes, reads, block_pairs)
        existing_writes, existing_reads, existing_pairs = flows.get(block.domain_id, (set(), set(), ()))
        flows[block.domain_id] = (
            existing_writes | writes,
            existing_reads | reads,
            (*existing_pairs, *block_pairs),
        )

    paths: list[RTLCDCPath] = []
    seen: set[tuple[str, str, str]] = set()
    for source_domain, (writes, _source_reads, _source_pairs) in flows.items():
        for destination_domain, (_destination_writes, reads, destination_pairs) in flows.items():
            if source_domain == destination_domain:
                continue
            for signal in sorted(writes & reads):
                key = (signal, source_domain, destination_domain)
                if key in seen:
                    continue
                seen.add(key)
                stage_signals = _synchronizer_chain(signal, destination_pairs)
                stages = len(stage_signals)
                source = domain_by_id.get(source_domain)
                destination = domain_by_id.get(destination_domain)
                reset_compatible = (
                    None
                    if source is None or destination is None
                    else source.reset == destination.reset and source.reset_active_low == destination.reset_active_low
                )
                evidence = tuple(
                    ref for ref in ast_refs if ref.locator.split("@", 1)[0].startswith(f"procedure:{module_name}.")
                )
                paths.append(
                    RTLCDCPath(
                        path_id=f"{module_name}:cdc:{signal}:{source_domain}:{destination_domain}",
                        signal=signal,
                        source_domain=source_domain,
                        destination_domain=destination_domain,
                        classification="synchronizer" if stages >= 2 else "direct",
                        synchronizer_stages=stages,
                        stage_signals=stage_signals,
                        safe=stages >= 2 and reset_compatible is not False,
                        reset_compatible=reset_compatible,
                        source_location=destination.source_location if destination is not None else None,
                        evidence_refs=evidence,
                    )
                )
    return tuple(paths)


def _collect_signal_flow(
    expression: RTLExpression,
    writes: set[str],
    reads: set[str],
    pairs: list[tuple[str, tuple[str, ...]]],
) -> None:
    if expression.kind in {"assign", "assigndly"} and len(expression.children) >= 2:
        lhs = expression.children[-1]
        rhs = expression.children[:-1]
        lhs_refs = _written_signal_refs(lhs)
        rhs_refs = tuple(dict.fromkeys(ref for item in rhs for ref in _expression_signal_refs(item)))
        writes.update(lhs_refs)
        reads.update(rhs_refs)
        reads.update(ref for ref in _expression_signal_refs(lhs) if ref not in lhs_refs)
        for lhs_ref in lhs_refs:
            pairs.append((lhs_ref, rhs_refs))
        return
    if expression.kind == "sentree":
        return
    if expression.kind == "if" and expression.children:
        reads.update(_expression_signal_refs(expression.children[0]))
        for child in expression.children[1:]:
            _collect_signal_flow(child, writes, reads, pairs)
        return
    for child in expression.children:
        _collect_signal_flow(child, writes, reads, pairs)


def _written_signal_refs(expression: RTLExpression) -> tuple[str, ...]:
    if expression.kind in {"arraysel", "arrayselect", "bitsel", "sel"} and expression.children:
        refs = _expression_signal_refs(expression.children[0])
        return refs[:1]
    refs = _expression_signal_refs(expression)
    return refs[:1]


def _synchronizer_chain(
    signal: str,
    pairs: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    frontier = {signal}
    visited: set[str] = set()
    chain: list[str] = []
    while frontier:
        next_frontier = sorted(
            {lhs for lhs, rhs in pairs if lhs not in visited and any(source in frontier for source in rhs)}
        )
        if len(next_frontier) != 1:
            break
        chain.append(next_frontier[0])
        visited.update(next_frontier)
        frontier = set(next_frontier)
    return tuple(chain)


def _protocols(
    module_name: str,
    ports: tuple[RTLPort, ...],
    control_domains: tuple[RTLControlDomain, ...],
    ast_refs: tuple[EvidenceRef, ...],
    configured_profiles: tuple[ProtocolProfile, ...],
) -> tuple[RTLProtocol, ...]:
    profiles = (
        ProtocolProfile(name="builtin_ready_valid"),
        *configured_profiles,
    )
    by_name = {port.name: port for port in ports}
    protocols: list[RTLProtocol] = []
    seen: set[tuple[str, str, str]] = set()
    for profile in profiles:
        for valid in ports:
            if valid.name == profile.valid_suffix.removeprefix("_"):
                prefix = ""
            elif valid.name.endswith(profile.valid_suffix):
                prefix = valid.name.removesuffix(profile.valid_suffix)
            else:
                continue
            ready_name = f"{prefix}{profile.ready_suffix}" if prefix else profile.ready_suffix.removeprefix("_")
            ready = by_name.get(ready_name)
            if ready is None:
                continue
            if valid.direction == "input" and ready.direction == "output":
                role = "sink"
            elif valid.direction == "output" and ready.direction == "input":
                role = "source"
            else:
                continue
            key = (profile.kind, valid.name, ready.name)
            if key in seen:
                continue
            seen.add(key)
            data_names = tuple(
                f"{prefix}{suffix}" if prefix else suffix.removeprefix("_") for suffix in profile.data_suffixes
            )
            data = next(
                (
                    by_name[name]
                    for name in data_names
                    if name in by_name and by_name[name].direction == valid.direction
                ),
                None,
            )
            domain = control_domains[0] if len(control_domains) == 1 else None
            channel_name = prefix or "channel"
            evidence = tuple(
                ref
                for ref in ast_refs
                if ref.locator.split("@", 1)[0]
                in {
                    f"port:{module_name}.{valid.name}",
                    f"port:{module_name}.{ready.name}",
                    *(set() if data is None else {f"port:{module_name}.{data.name}"}),
                }
            )
            protocols.append(
                RTLProtocol(
                    protocol_id=f"{module_name}:{profile.kind}:{channel_name}",
                    kind=profile.kind,
                    name=channel_name,
                    role=role,
                    valid=valid.name,
                    ready=ready.name,
                    data=data.name if data is not None else None,
                    data_width=data.width if data is not None else None,
                    clock=domain.clock if domain is not None else None,
                    reset=domain.reset if domain is not None else None,
                    confidence="configured_profile" if profile.name != "builtin_ready_valid" else "structured_ports",
                    profile=profile.name,
                    signal_map=tuple(
                        (role_name, signal_name)
                        for role_name, signal_name in (
                            ("valid" if profile.kind == "ready_valid" else "request", valid.name),
                            ("ready" if profile.kind == "ready_valid" else "acknowledge", ready.name),
                            ("data", data.name if data is not None else None),
                        )
                        if signal_name is not None
                    ),
                    evidence_refs=evidence,
                )
            )
    return tuple(protocols)


def _procedural_patterns(expressions: tuple[RTLExpression, ...]) -> tuple[RTLProceduralPattern, ...]:
    patterns: list[RTLProceduralPattern] = []
    for expression in expressions:
        patterns.extend(_patterns_from_expression(expression, control=None))
    return tuple(dict.fromkeys(patterns))


def _patterns_from_expression(expression: RTLExpression, control: str | None) -> tuple[RTLProceduralPattern, ...]:
    patterns: list[RTLProceduralPattern] = []
    if expression.kind == "if":
        condition = expression.children[0] if expression.children else None
        branch_control = _first_signal_ref(condition) if condition is not None else control
        for child in expression.children[1:]:
            patterns.extend(_patterns_from_expression(child, branch_control))
        return tuple(patterns)
    if expression.kind == "case":
        for child in expression.children:
            patterns.extend(_patterns_from_expression(child, None))
        return tuple(patterns)
    if expression.kind in {"assign", "assigndly"}:
        pattern = _pattern_from_assign(expression, control)
        if pattern is not None:
            patterns.append(pattern)
    for child in expression.children:
        patterns.extend(_patterns_from_expression(child, control))
    return tuple(patterns)


def _pattern_from_assign(expression: RTLExpression, control: str | None) -> RTLProceduralPattern | None:
    if len(expression.children) < 2:
        return None
    target = _first_signal_ref(expression.children[-1])
    value_expression = expression.children[0]
    if target is None:
        return None
    constant = _constant_value(value_expression)
    if constant is not None and control is not None:
        return RTLProceduralPattern(kind="reset_to_constant", target=target, control=control, value=constant)
    increment_source = _increment_source(target, value_expression)
    if increment_source is not None:
        return RTLProceduralPattern(kind="increment", target=target, control=control, source=increment_source)
    return None


def _first_signal_ref(expression: RTLExpression | None) -> str | None:
    if expression is None:
        return None
    refs = _expression_signal_refs(expression)
    return refs[0] if refs else None


def _constant_value(expression: RTLExpression) -> str | None:
    if expression.kind in {"const", "constint", "constant"}:
        return expression.value
    return None


def _increment_source(target: str, expression: RTLExpression) -> str | None:
    if expression.kind not in {"add", "plus"}:
        return None
    signal_refs = _expression_signal_refs(expression)
    constants = tuple(_constant_value(child) for child in expression.children)
    if target not in signal_refs:
        return None
    if not any(_is_one_constant(value) for value in constants if value is not None):
        return None
    return target


def _is_one_constant(value: str) -> bool:
    normalized = value.lower().replace("&apos;", "'")
    return normalized == "1" or normalized.endswith("'h1") or normalized.endswith("'b1") or normalized.endswith("'d1")


def _matching_element_summaries(module_element: ElementTree.Element, pattern: str) -> tuple[str, ...]:
    summaries: list[str] = []
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if pattern in tag:
            summaries.append(_element_summary(tag, element))
    return tuple(dict.fromkeys(summaries))


def _element_summary(tag: str, element: ElementTree.Element) -> str:
    name = element.attrib.get("name") or element.attrib.get("origName")
    location = _source_location(element)
    parts = [tag]
    if name:
        parts.append(name)
    if location:
        parts.append(f"@{location}")
    return ":".join(parts)


def _looks_like_clock(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"clk", "clock"} or normalized.endswith("_clk") or normalized.endswith("_clock")


def _looks_like_reset(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"rst", "reset", "rst_n", "reset_n"} or normalized.endswith(
        ("_rst", "_reset", "_rst_n", "_reset_n")
    )


def _reset_active_low(name: str) -> bool:
    normalized = name.lower()
    return normalized in {"rst_n", "reset_n"} or normalized.endswith("_rst_n") or normalized.endswith("_reset_n")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _source_location(element: ElementTree.Element) -> str | None:
    return element.attrib.get("fl") or element.attrib.get("loc")


def _module_source(root: ElementTree.Element, module_element: ElementTree.Element) -> Path | None:
    location = _source_location(module_element)
    if not location or "," not in location:
        return None
    file_id = location.split(",", 1)[0]
    filename = next(
        (
            element.attrib.get("filename")
            for element in root.iter()
            if _local_name(element.tag) == "file" and element.attrib.get("id") == file_id
        ),
        None,
    )
    return Path(filename) if filename else None


def _dtype_by_id(root: ElementTree.Element, dtype_id: str | None) -> ElementTree.Element | None:
    if dtype_id is None:
        return None
    for element in root.iter():
        if element.attrib.get("id") == dtype_id and _local_name(element.tag).endswith("dtype"):
            return element
    return None


def _packed_width(left: str | None, right: str | None) -> int | None:
    if left is None or right is None:
        return None
    if not left.isdecimal() or not right.isdecimal():
        return None
    return abs(int(left) - int(right)) + 1


def _dtype_width(dtype: ElementTree.Element | None) -> int | None:
    if dtype is None:
        return None
    width = _packed_width(dtype.attrib.get("left"), dtype.attrib.get("right"))
    if width is not None:
        return width
    if _local_name(dtype.tag) == "basicdtype":
        return 1
    return None


def _unpacked_depth(dtype: ElementTree.Element) -> int | None:
    range_element = next((child for child in list(dtype) if _local_name(child.tag) == "range"), None)
    if range_element is None:
        return None
    bounds = tuple(
        value
        for child in list(range_element)
        if (value := _verilator_integer(_expression_value(child, _local_name(child.tag)))) is not None
    )
    if len(bounds) < 2:
        return None
    return abs(bounds[0] - bounds[1]) + 1


def _verilator_integer(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.lower().replace("&apos;", "'").replace("_", "")
    if "'" not in normalized:
        try:
            return int(normalized, 0)
        except ValueError:
            return None
    _width, encoded = normalized.split("'", 1)
    encoded = encoded.removeprefix("s")
    if not encoded:
        return None
    base_code, digits = encoded[0], encoded[1:]
    if any(character in digits for character in "xz?"):
        return None
    base = {"b": 2, "o": 8, "d": 10, "h": 16}.get(base_code)
    if base is None:
        return None
    try:
        return int(digits, base)
    except ValueError:
        return None
