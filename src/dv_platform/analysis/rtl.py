"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import subprocess
from xml.etree import ElementTree

from dv_platform.analysis.discovery import ProjectInventory, build_verilator_dry_run_command
from dv_platform.core.models import CLIConfig, EvidenceKind, EvidenceRef, RTLModule


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
            modules[name] = RTLModule(
                name=name,
                ports=ports,
                parameters=_parameter_names(element),
                clocks=tuple(port for port in ports if _looks_like_clock(port)),
                resets=tuple(port for port in ports if _looks_like_reset(port)),
                instances=_instance_names(element),
                continuous_assignments=_element_summaries(element, {"assign", "contassign"}),
                procedural_blocks=_element_summaries(element, {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}),
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
        "schema_version": 1,
        "verilator_version": verilator_version,
        "modules": [
            {
                "name": module.name,
                "ports": list(module.ports),
                "parameters": list(module.parameters),
                "clocks": list(module.clocks),
                "resets": list(module.resets),
                "instances": list(module.instances),
                "continuous_assignments": list(module.continuous_assignments),
                "procedural_blocks": list(module.procedural_blocks),
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


def read_normalized_rtl_facts(config: CLIConfig) -> tuple[RTLModule, ...]:
    """Read normalized RTL facts from the configured work directory."""

    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    return tuple(_module_from_json(item) for item in payload.get("modules", ()))


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
        instances=tuple(str(item) for item in data.get("instances", ())),
        continuous_assignments=tuple(str(item) for item in data.get("continuous_assignments", ())),
        procedural_blocks=tuple(str(item) for item in data.get("procedural_blocks", ())),
        assertions=tuple(str(item) for item in data.get("assertions", ())),
        covers=tuple(str(item) for item in data.get("covers", ())),
        ast_refs=tuple(_evidence_from_json(item) for item in data.get("ast_refs", ())),
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


def _element_summaries(module_element: ElementTree.Element, tags: set[str]) -> tuple[str, ...]:
    summaries: list[str] = []
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag in tags:
            summaries.append(_element_summary(tag, element))
    return tuple(dict.fromkeys(summaries))


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
    return normalized in {"rst", "reset", "rst_n", "reset_n"} or normalized.endswith("_rst") or normalized.endswith("_reset")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()
