# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
    RTLClock,
    RTLMemory,
    RTLMemoryAccess,
    RTLModule,
    RTLParameter,
    RTLPort,
    RTLReset,
    RTLSemanticFeature,
    VerificationTarget,
)
from dv_platform.core.schema import MIN_READABLE_RTL_FACTS_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.core.security import redact_value

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


def write_rtl_facts_summary(
    config: CLIConfig,
    modules: tuple[RTLModule, ...],
    verilator_version: str | None = None,
    normalization_frontends: tuple[str, ...] = (),
) -> Path:
    """Persist a compact machine-readable summary of normalized RTL facts."""

    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": RTL_FACTS_SCHEMA_VERSION,
        "verilator_version": verilator_version,
        "verilator_compatibility": classify_verilator_version(verilator_version),
        "normalization_frontends": list(normalization_frontends or (("verilator",) if verilator_version else ())),
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


def _port_names(module_element: Element) -> tuple[str, ...]:
    ports: list[str] = []
    for element in module_element.iter():
        tag = _local_name(element.tag)
        direction = element.attrib.get("dir") or element.attrib.get("direction")
        name = element.attrib.get("name") or element.attrib.get("origName")
        is_interface = tag == "var" and element.attrib.get("vartype") == "ifaceref"
        if tag in {"port", "var"} and (direction in {"input", "output", "inout", "ref"} or is_interface) and name:
            ports.append(name)
    return tuple(dict.fromkeys(ports))


def _port_details(module_element: Element, root: Element) -> tuple[RTLPort, ...]:
    ports: list[RTLPort] = []
    seen: set[str] = set()
    for element in module_element.iter():
        tag = _local_name(element.tag)
        direction = element.attrib.get("dir") or element.attrib.get("direction")
        name = element.attrib.get("name") or element.attrib.get("origName")
        is_interface = tag == "var" and element.attrib.get("vartype") == "ifaceref"
        if (
            tag not in {"port", "var"}
            or (direction not in {"input", "output", "inout", "ref"} and not is_interface)
            or not name
        ):
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
                direction=direction or "interface",
                dtype_id=dtype_id,
                data_type=_local_name(dtype.tag) if dtype is not None else None,
                width=_packed_width(left, right),
                signed=dtype is not None and dtype.attrib.get("signed") == "true",
                packed_range=packed_range,
                source_location=_source_location(element),
                interface_name=_interface_name(dtype, root),
                modport=_modport_name(dtype),
                interface_direction=_interface_direction(dtype) or ("modport" if is_interface else None),
                packed_dimensions=tuple(
                    value
                    for value in (f"[{left}:{right}]" if left is not None and right is not None else None,)
                    if value
                ),
                unpacked_dimensions=tuple(value for value in (_unpacked_range(dtype),) if value is not None)
                if dtype is not None
                else (),
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
    module_element: Element,
    root: Element,
) -> tuple[RTLSemanticFeature, ...]:
    candidates: list[Element] = list(module_element.iter())
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
    module_element: Element,
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
    module_element: Element,
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


def _sensitivity_controls(module_element: Element) -> tuple[dict[str, str], dict[str, bool]]:
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
        protocol_models=tuple(_protocol_model_from_json(item) for item in data.get("protocol_models", ())),
        register_models=tuple(_register_model_from_json(item) for item in data.get("register_models", ())),
        register_conflicts=tuple(_register_conflict_from_json(item) for item in data.get("register_conflicts", ())),
        property_details=tuple(_property_from_json(item) for item in data.get("property_details", ())),
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
        interface_name=str(data["interface_name"]) if data.get("interface_name") is not None else None,
        modport=str(data["modport"]) if data.get("modport") is not None else None,
        interface_direction=(str(data["interface_direction"]) if data.get("interface_direction") is not None else None),
        packed_dimensions=tuple(str(item) for item in data.get("packed_dimensions", ())),
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
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
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
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
