"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import subprocess
from xml.etree import ElementTree

from dv_platform.analysis.discovery import ProjectInventory, build_verilator_dry_run_command
from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    RTLAssignment,
    RTLClock,
    RTLExpression,
    RTLInstance,
    RTLModule,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLReset,
)


RTL_FACTS_SCHEMA_VERSION = 2
MIN_READABLE_RTL_FACTS_SCHEMA_VERSION = 1


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

    completed = subprocess.run(
        command,
        cwd=config.repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout_log = logs_dir / "verilator.stdout.log"
    stderr_log = logs_dir / "verilator.stderr.log"
    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")

    return VerilatorRunResult(
        command=command,
        return_code=completed.returncode,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        version=version,
        version_log=version_log,
        xml_files=tuple(sorted(verilator_dir.glob("*.xml"), key=lambda path: path.as_posix())),
    )


def normalize_verilator_xml(xml_files: tuple[Path, ...]) -> tuple[RTLModule, ...]:
    """Extract conservative module facts from Verilator XML artifacts."""

    modules: dict[str, RTLModule] = {}
    for xml_file in xml_files:
        tree = ElementTree.parse(xml_file)
        for element in tree.getroot().iter():
            if _local_name(element.tag) != "module":
                continue

            name = element.attrib.get("origName") or element.attrib.get("name")
            if not name:
                continue

            ports = _port_names(element)
            port_details = _port_details(element, tree.getroot())
            modules[name] = RTLModule(
                name=name,
                ports=ports,
                port_details=port_details,
                parameters=_parameter_names(element),
                clocks=tuple(port for port in ports if _looks_like_clock(port)),
                resets=tuple(port for port in ports if _looks_like_reset(port)),
                clock_details=_clock_details(port_details),
                reset_details=_reset_details(port_details),
                instances=_instance_names(element),
                instance_details=_instance_details(element),
                continuous_assignments=_element_summaries(element, {"assign", "contassign"}),
                assignment_details=_assignment_details(element),
                procedural_blocks=_element_summaries(element, {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}),
                procedural_block_details=_procedural_block_details(element),
                assertions=_matching_element_summaries(element, "assert"),
                covers=_matching_element_summaries(element, "cover"),
                ast_refs=_evidence_refs(xml_file, element, name),
            )

    return tuple(modules[name] for name in sorted(modules))


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
        "modules": [
            {
                "name": module.name,
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
                "clocks": list(module.clocks),
                "resets": list(module.resets),
                "clock_details": [
                    {
                        "name": clock.name,
                        "direction": clock.direction,
                        "width": clock.width,
                        "source_location": clock.source_location,
                        "classification": clock.classification,
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
                    }
                    for reset in module.reset_details
                ],
                "instances": list(module.instances),
                "instance_details": [
                    {
                        "name": instance.name,
                        "module_name": instance.module_name,
                        "kind": instance.kind,
                        "source_location": instance.source_location,
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
                    }
                    for block in module.procedural_block_details
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
    facts_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        "module_count": len(modules),
        "totals": {
            "ports": sum(len(module.ports) for module in modules),
            "structured_ports": sum(len(module.port_details) for module in modules),
            "clocks": sum(len(module.clocks) for module in modules),
            "structured_clocks": sum(len(module.clock_details) for module in modules),
            "resets": sum(len(module.resets) for module in modules),
            "structured_resets": sum(len(module.reset_details) for module in modules),
            "instances": sum(len(module.instances) for module in modules),
            "structured_instances": sum(len(module.instance_details) for module in modules),
            "continuous_assignments": sum(len(module.continuous_assignments) for module in modules),
            "structured_assignments": sum(len(module.assignment_details) for module in modules),
            "procedural_blocks": sum(len(module.procedural_blocks) for module in modules),
            "structured_procedural_blocks": sum(len(module.procedural_block_details) for module in modules),
            "assertions": sum(len(module.assertions) for module in modules),
            "covers": sum(len(module.covers) for module in modules),
        },
        "modules": [
            {
                "name": module.name,
                "ports": len(module.ports),
                "structured_ports": len(module.port_details),
                "clocks": list(module.clocks),
                "resets": [
                    {
                        "name": reset.name,
                        "active_low": reset.active_low,
                        "classification": reset.classification,
                    }
                    for reset in module.reset_details
                ],
                "instances": len(module.instances),
                "child_modules": [
                    instance.module_name
                    for instance in module.instance_details
                    if instance.module_name is not None
                ],
                "continuous_assignments": len(module.continuous_assignments),
                "procedural_blocks": len(module.procedural_blocks),
                "assertions": len(module.assertions),
                "covers": len(module.covers),
            }
            for module in modules
        ],
    }
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def read_normalized_rtl_facts(config: CLIConfig) -> tuple[RTLModule, ...]:
    """Read normalized RTL facts from the configured work directory."""

    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    _validate_rtl_facts_schema(payload)
    return tuple(_module_from_json(item) for item in payload.get("modules", ()))


def _validate_rtl_facts_schema(payload: dict[str, object]) -> None:
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
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
                source_location=element.attrib.get("fl"),
            )
        )
    return tuple(ports)


def _clock_details(ports: tuple[RTLPort, ...]) -> tuple[RTLClock, ...]:
    return tuple(
        RTLClock(
            name=port.name,
            direction=port.direction,
            width=port.width,
            source_location=port.source_location,
        )
        for port in ports
        if port.direction == "input" and _looks_like_clock(port.name)
    )


def _reset_details(ports: tuple[RTLPort, ...]) -> tuple[RTLReset, ...]:
    return tuple(
        RTLReset(
            name=port.name,
            direction=port.direction,
            width=port.width,
            active_low=_reset_active_low(port.name),
            source_location=port.source_location,
        )
        for port in ports
        if port.direction == "input" and _looks_like_reset(port.name)
    )


def _text_tail(path: Path, max_lines: int = 20) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]


def _module_from_json(data: dict[str, object]) -> RTLModule:
    return RTLModule(
        name=str(data["name"]),
        ports=tuple(str(item) for item in data.get("ports", ())),
        parameters=tuple(str(item) for item in data.get("parameters", ())),
        clocks=tuple(str(item) for item in data.get("clocks", ())),
        resets=tuple(str(item) for item in data.get("resets", ())),
        clock_details=tuple(_clock_from_json(item) for item in data.get("clock_details", ())),
        reset_details=tuple(_reset_from_json(item) for item in data.get("reset_details", ())),
        instances=tuple(str(item) for item in data.get("instances", ())),
        instance_details=tuple(_instance_from_json(item) for item in data.get("instance_details", ())),
        continuous_assignments=tuple(str(item) for item in data.get("continuous_assignments", ())),
        assignment_details=tuple(_assignment_from_json(item) for item in data.get("assignment_details", ())),
        procedural_blocks=tuple(str(item) for item in data.get("procedural_blocks", ())),
        procedural_block_details=tuple(_procedural_block_from_json(item) for item in data.get("procedural_block_details", ())),
        assertions=tuple(str(item) for item in data.get("assertions", ())),
        covers=tuple(str(item) for item in data.get("covers", ())),
        ast_refs=tuple(_evidence_from_json(item) for item in data.get("ast_refs", ())),
        port_details=tuple(_port_from_json(item) for item in data.get("port_details", ())),
    )


def _port_from_json(data: dict[str, object]) -> RTLPort:
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


def _clock_from_json(data: dict[str, object]) -> RTLClock:
    return RTLClock(
        name=str(data["name"]),
        direction=str(data["direction"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
    )


def _reset_from_json(data: dict[str, object]) -> RTLReset:
    return RTLReset(
        name=str(data["name"]),
        direction=str(data["direction"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        active_low=bool(data["active_low"]) if data.get("active_low") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
    )


def _instance_from_json(data: dict[str, object]) -> RTLInstance:
    return RTLInstance(
        name=str(data["name"]),
        module_name=str(data["module_name"]) if data.get("module_name") is not None else None,
        kind=str(data["kind"]) if data.get("kind") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _assignment_from_json(data: dict[str, object]) -> RTLAssignment:
    return RTLAssignment(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        lhs_signals=tuple(str(item) for item in data.get("lhs_signals", ())),
        rhs_signals=tuple(str(item) for item in data.get("rhs_signals", ())),
        expressions=tuple(_expression_from_json(item) for item in data.get("expressions", ())),
    )


def _expression_from_json(data: dict[str, object]) -> RTLExpression:
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


def _procedural_block_from_json(data: dict[str, object]) -> RTLProceduralBlock:
    return RTLProceduralBlock(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        summary=str(data["summary"]) if data.get("summary") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expressions=tuple(_expression_from_json(item) for item in data.get("expressions", ())),
        patterns=tuple(_procedural_pattern_from_json(item) for item in data.get("patterns", ())),
    )


def _procedural_pattern_from_json(data: dict[str, object]) -> RTLProceduralPattern:
    return RTLProceduralPattern(
        kind=str(data["kind"]),
        target=str(data["target"]),
        control=str(data["control"]) if data.get("control") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        source=str(data["source"]) if data.get("source") is not None else None,
        confidence=str(data.get("confidence", "shape")),
    )


def _evidence_from_json(data: dict[str, object]) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind(str(data["kind"])),
        source_id=str(data["source_id"]),
        locator=str(data["locator"]),
        summary=str(data["summary"]) if data.get("summary") is not None else None,
    )


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
                _evidence_ref(xml_file, "parameter", f"{module_name}.{name}", element, f"{module_name}.{name} parameter")
            )
        elif tag in {"instance", "cell"} and name:
            refs.append(
                _evidence_ref(xml_file, "instance", f"{module_name}.{name}", element, f"{module_name}.{name} instance")
            )
        elif tag in {"assign", "contassign"}:
            refs.append(_evidence_ref(xml_file, "assignment", f"{module_name}.{tag}", element, f"{module_name} assignment"))
        elif tag in {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}:
            refs.append(_evidence_ref(xml_file, "procedure", f"{module_name}.{tag}", element, f"{module_name} procedure"))
        elif "assert" in tag:
            refs.append(_evidence_ref(xml_file, "assertion", f"{module_name}.{tag}", element, f"{module_name} assertion"))
        elif "cover" in tag:
            refs.append(_evidence_ref(xml_file, "cover", f"{module_name}.{tag}", element, f"{module_name} cover"))
    return tuple(refs)


def _evidence_ref(
    xml_file: Path,
    category: str,
    key: str,
    element: ElementTree.Element,
    summary: str,
) -> EvidenceRef:
    location = element.attrib.get("fl")
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


def _is_parameter(element: ElementTree.Element) -> bool:
    return element.attrib.get("param") == "true" or element.attrib.get("localparam") == "true"


def _instance_names(module_element: ElementTree.Element) -> tuple[str, ...]:
    instances: list[str] = []
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"instance", "cell"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        module_name = (
            element.attrib.get("moduleName")
            or element.attrib.get("modulename")
            or element.attrib.get("submodname")
            or element.attrib.get("dtypeName")
        )
        if name and module_name:
            instances.append(f"{name}:{module_name}")
        elif name:
            instances.append(name)
    return tuple(dict.fromkeys(instances))


def _instance_details(module_element: ElementTree.Element) -> tuple[RTLInstance, ...]:
    instances: list[RTLInstance] = []
    seen: set[tuple[str, str | None]] = set()
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"instance", "cell"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        module_name = _instance_module_name(element)
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
                kind=tag,
                source_location=element.attrib.get("fl"),
            )
        )
    return tuple(instances)


def _instance_module_name(element: ElementTree.Element) -> str | None:
    return (
        element.attrib.get("moduleName")
        or element.attrib.get("modulename")
        or element.attrib.get("submodname")
        or element.attrib.get("dtypeName")
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
        source_location = element.attrib.get("fl")
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
        children = tuple(_expression_from_element(child, depth=depth + 1, max_depth=max_depth) for child in list(element))
    return RTLExpression(
        kind=kind,
        name=element.attrib.get("name") or element.attrib.get("origName"),
        value=_expression_value(element, kind),
        dtype_id=element.attrib.get("dtype_id"),
        source_location=element.attrib.get("fl"),
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
    signal_refs = tuple(dict.fromkeys(ref for expression in expressions for ref in _expression_signal_refs(expression)))
    if not signal_refs:
        return (), ()
    return (signal_refs[0],), signal_refs[1:]


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


def _procedural_block_details(module_element: ElementTree.Element) -> tuple[RTLProceduralBlock, ...]:
    blocks: list[RTLProceduralBlock] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        source_location = element.attrib.get("fl")
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
                signal_refs=tuple(dict.fromkeys(ref for expression in expressions for ref in _expression_signal_refs(expression))),
                expressions=expressions,
                patterns=_procedural_patterns(expressions),
            )
        )
    return tuple(blocks)


def _procedural_patterns(expressions: tuple[RTLExpression, ...]) -> tuple[RTLProceduralPattern, ...]:
    patterns: list[RTLProceduralPattern] = []
    for expression in expressions:
        patterns.extend(_patterns_from_expression(expression, control=None))
    return tuple(dict.fromkeys(patterns))


def _patterns_from_expression(expression: RTLExpression, control: str | None) -> tuple[RTLProceduralPattern, ...]:
    patterns: list[RTLProceduralPattern] = []
    current_control = control
    if expression.kind == "if":
        condition = expression.children[0] if expression.children else None
        current_control = _first_signal_ref(condition) if condition is not None else control
    if expression.kind in {"assign", "assigndly"}:
        pattern = _pattern_from_assign(expression, current_control)
        if pattern is not None:
            patterns.append(pattern)
    for child in expression.children:
        patterns.extend(_patterns_from_expression(child, current_control))
    return tuple(patterns)


def _pattern_from_assign(expression: RTLExpression, control: str | None) -> RTLProceduralPattern | None:
    if len(expression.children) < 2:
        return None
    if expression.kind == "assigndly":
        target = _first_signal_ref(expression.children[1])
        value_expression = expression.children[0]
    else:
        target = _first_signal_ref(expression.children[0])
        value_expression = expression.children[1]
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
    location = element.attrib.get("fl")
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
