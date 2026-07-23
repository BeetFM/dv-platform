"""Content-free, commit-bound external-design semantic qualification."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.analysis.rtl import normalize_verilator_xml
from dv_platform.analysis.semantic_crosscheck import (
    CAPABILITY_HIERARCHY,
    CAPABILITY_TYPES,
    CORE_REQUIRED_CAPABILITIES,
    FrontendMetadata,
    NormalizedFactCrossChecker,
    SlangAnalyzer,
    capabilities_for_modules,
    write_crosscheck_result,
)
from dv_platform.core.io import atomic_write_text
from dv_platform.core.paths import is_within

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class SurelogStructuralFacts:
    """Conservative facts decoded from Surelog's UHDM text serializer."""

    module: str
    ports: tuple[tuple[str, str], ...]
    parameters: tuple[str, ...]


_VPI_DIRECTIONS = {"1": "input", "2": "output", "3": "inout"}


def qualify_external_design(
    *,
    design_id: str,
    repository: Path,
    sources: tuple[Path, ...],
    top: str,
    output: Path,
    verilator: str = "verilator",
    slang: str = "slang",
    surelog: str = "surelog",
) -> dict[str, object]:
    """Run three independent frontends and persist digest-bound evidence."""

    root, resolved, commit, input_digest, license_path = _external_design_inputs(design_id, repository, sources, top)
    output = output.resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    primary, verilator_command, verilator_run, verilator_xml = _run_external_verilator(
        root, resolved, top, output, verilator
    )
    slang_analyzer = SlangAnalyzer(slang)
    slang_result = slang_analyzer.run(resolved, output / "slang" / "ast.json", top_modules=(top,))
    if not slang_result.succeeded:
        raise ValueError("Slang failed external-design normalization: " + (slang_result.error or "unknown error"))
    required = (*CORE_REQUIRED_CAPABILITIES, CAPABILITY_TYPES, CAPABILITY_HIERARCHY)
    comparison = NormalizedFactCrossChecker(
        primary=FrontendMetadata("verilator", _tool_version(verilator), verilator_command, str(verilator_xml)),
        reference=FrontendMetadata("slang", slang_result.version, slang_result.command, str(slang_result.ast_path)),
        primary_capabilities=capabilities_for_modules(primary),
        reference_capabilities=slang_result.capabilities,
        required_capabilities=required,
        unsupported_reasons=dict(slang_result.capability_reasons),
        nonrequired_severity="warning",
    ).compare(primary, slang_result.modules)
    write_crosscheck_result(output / "comparison.json", comparison)
    surelog_status, surelog_match, surelog_issues, surelog_dir = _run_external_surelog(
        root, resolved, top, output, surelog, primary
    )
    payload = _external_design_payload(
        design_id,
        root,
        resolved,
        top,
        commit,
        input_digest,
        license_path,
        comparison,
        required,
        verilator,
        verilator_run,
        verilator_xml,
        slang_result,
        surelog,
        surelog_status,
        surelog_match,
        surelog_issues,
        surelog_dir,
    )
    atomic_write_text(output / "external-design-evidence.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _external_design_inputs(
    design_id: str, repository: Path, sources: tuple[Path, ...], top: str
) -> tuple[Path, tuple[Path, ...], str, str, Path | None]:
    root = repository.resolve(strict=True)
    if not _SAFE_ID.fullmatch(design_id) or not top.strip() or not sources:
        raise ValueError("external design requires a safe ID, top, and at least one source")
    resolved = tuple(path.resolve(strict=True) for path in sources)
    if any(not is_within(path, root) for path in resolved):
        raise ValueError("external design sources must remain within the repository")
    commit = _command(("git", "-C", str(root), "rev-parse", "HEAD")).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("external design repository must have a resolved Git commit")
    input_digest = _source_digest(root, resolved)
    license_path = next(
        (root / name for name in ("LICENSE", "LICENSE.txt", "COPYING") if (root / name).is_file()), None
    )
    return root, resolved, commit, input_digest, license_path


def _run_external_verilator(
    root: Path, resolved: tuple[Path, ...], top: str, output: Path, verilator: str
) -> tuple[tuple[Any, ...], tuple[str, ...], int, Path]:
    verilator_xml = output / "verilator.xml"
    verilator_command = (
        verilator,
        "--xml-only",
        "--xml-output",
        str(verilator_xml),
        "--top-module",
        top,
        "-Wno-fatal",
        *(str(path) for path in resolved),
    )
    verilator_run = _run(verilator_command, root, output / "verilator.stdout.log", output / "verilator.stderr.log")
    if verilator_run != 0 or not verilator_xml.is_file():
        raise ValueError("Verilator failed external-design elaboration")
    return normalize_verilator_xml((verilator_xml,)), verilator_command, verilator_run, verilator_xml


def _run_external_surelog(
    root: Path, resolved: tuple[Path, ...], top: str, output: Path, surelog: str, primary: tuple[Any, ...]
) -> tuple[int, bool, tuple[str, ...], Path]:
    surelog_dir = output / "surelog"
    surelog_dir.mkdir(parents=True, exist_ok=True)
    surelog_command = (surelog, "-parse", "-sverilog", "-top", top, "-d", "uhdm", *(str(path) for path in resolved))
    surelog_stdout = surelog_dir / "stdout.log"
    surelog_status = _run(surelog_command, surelog_dir, surelog_stdout, surelog_dir / "stderr.log")
    surelog_text = surelog_stdout.read_text(encoding="utf-8", errors="replace")
    surelog_facts = decode_surelog_uhdm_text(surelog_text, top)
    primary_top = next(
        (module for module in primary if top in {module.name, module.original_name, module.elaborated_name}),
        None,
    )
    if primary_top is None:
        raise ValueError(f"Verilator did not normalize requested top {top!r}")
    surelog_issues = compare_surelog_structure(primary_top, surelog_facts)
    return surelog_status, not surelog_issues, surelog_issues, surelog_dir


def _external_design_payload(
    design_id: str,
    root: Path,
    resolved: tuple[Path, ...],
    top: str,
    commit: str,
    input_digest: str,
    license_path: Path | None,
    comparison: Any,
    required: tuple[str, ...],
    verilator: str,
    verilator_run: int,
    verilator_xml: Path,
    slang_result: Any,
    surelog: str,
    surelog_status: int,
    surelog_structural_match: bool,
    surelog_issues: tuple[str, ...],
    surelog_dir: Path,
) -> dict[str, object]:
    frontends = [
        _frontend("verilator", _tool_version(verilator), verilator_run == 0, verilator_xml),
        _frontend("slang", slang_result.version or "unknown", slang_result.succeeded, slang_result.ast_path),
        _frontend("surelog", _tool_version(surelog), surelog_status == 0, _surelog_artifact(surelog_dir)),
    ]
    passed = comparison.passed and surelog_status == 0 and surelog_structural_match
    payload: dict[str, object] = {
        "schema_version": 1,
        "design_id": design_id,
        "repository": _repository_identity(root),
        "commit": commit,
        "input_sha256": input_digest,
        "license_sha256": _sha256(license_path) if license_path else None,
        "top": top,
        "sources": [path.relative_to(root).as_posix() for path in resolved],
        "status": "passed" if passed else "failed",
        "frontends": frontends,
        "comparison": {
            "status": "passed" if comparison.passed else "failed",
            "issues": len(comparison.issues),
            "required_capabilities": list(required),
            "surelog_structural_match": surelog_structural_match,
            "surelog_capabilities": ["design_units", "ports", "port_directions", "parameters"],
            "surelog_issues": list(surelog_issues),
        },
    }
    payload["evidence_sha256"] = _payload_digest(payload)
    return payload


def verify_external_design_evidence(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported external-design evidence schema")
    expected = payload.get("evidence_sha256")
    unsigned = dict(payload)
    unsigned.pop("evidence_sha256", None)
    if expected != _payload_digest(unsigned):
        raise ValueError("external-design evidence digest mismatch")
    if payload.get("status") != "passed":
        raise ValueError("external-design evidence did not pass")
    if not _SAFE_ID.fullmatch(str(payload.get("design_id", ""))) or not str(payload.get("top", "")).strip():
        raise ValueError("external-design evidence identity is invalid")
    for field in ("commit", "input_sha256"):
        if re.fullmatch(r"[0-9a-f]{40}" if field == "commit" else r"[0-9a-f]{64}", str(payload.get(field, ""))) is None:
            raise ValueError(f"external-design evidence {field} is invalid")
    frontends = payload.get("frontends")
    if not isinstance(frontends, list) or {item.get("name") for item in frontends if isinstance(item, dict)} != {
        "verilator",
        "slang",
        "surelog",
    }:
        raise ValueError("external-design evidence frontend set is incomplete")
    if any(
        not isinstance(item, dict)
        or item.get("status") != "passed"
        or not str(item.get("version", "")).strip()
        or re.fullmatch(r"[0-9a-f]{64}", str(item.get("artifact_sha256", ""))) is None
        for item in frontends
    ):
        raise ValueError("external-design frontend evidence is incomplete")
    comparison = payload.get("comparison")
    if (
        not isinstance(comparison, dict)
        or comparison.get("status") != "passed"
        or comparison.get("surelog_structural_match") is not True
        or comparison.get("surelog_capabilities") != ["design_units", "ports", "port_directions", "parameters"]
        or comparison.get("surelog_issues") != []
        or not isinstance(comparison.get("required_capabilities"), list)
        or not comparison.get("required_capabilities")
        or not isinstance(comparison.get("issues"), int)
    ):
        raise ValueError("external-design comparison evidence is incomplete")
    return payload


def decode_surelog_uhdm_text(text: str, top: str) -> SurelogStructuralFacts:
    """Decode exact top-level structural facts from a Surelog ``-d uhdm`` dump.

    The serializer repeats objects under relationship nodes. Only records at the
    indentation of the module's direct children are accepted, preventing nested
    references from being mistaken for additional ports or parameters.
    """

    marker = "|uhdmallModules:"
    try:
        section = text[text.index(marker) + len(marker) :]
    except ValueError as error:
        raise ValueError("Surelog output has no elaborated UHDM module section") from error
    modules = tuple(re.finditer(r"^\\_module_inst: (?:[^@\s]+@)?([^\s(]+)", section, re.MULTILINE))
    module_match = next((match for match in modules if match.group(1) == top), None)
    if module_match is None:
        found = sorted({match.group(1) for match in modules})
        raise ValueError(f"Surelog elaborated top mismatch: expected {top!r}, found {found!r}")
    module = module_match.group(1)
    next_module = next((match for match in modules if match.start() > module_match.start()), None)
    section = section[module_match.start() : next_module.start() if next_module else None]

    lines = section.splitlines()
    ports: list[tuple[str, str]] = []
    parameters: list[str] = []
    for index, line in enumerate(lines):
        if line == "  |vpiPort:" and index + 1 < len(lines):
            ports.append(_decode_surelog_port(lines, index))
        elif line == "  |vpiParameter:" and index + 1 < len(lines):
            parameter = _decode_surelog_parameter(lines, index)
            if parameter is not None:
                parameters.append(parameter)
    if not ports:
        raise ValueError("Surelog UHDM top has no directly serialized ports")
    return SurelogStructuralFacts(module, tuple(ports), tuple(parameters))


def _relationship_lines(lines: list[str], index: int) -> tuple[str, ...]:
    result: list[str] = []
    cursor = index + 2
    while cursor < len(lines) and not lines[cursor].startswith("  |"):
        result.append(lines[cursor])
        cursor += 1
    return tuple(result)


def _decode_surelog_port(lines: list[str], index: int) -> tuple[str, str]:
    port_match = re.match(r"^  \\_port: \(([^)]+)\)", lines[index + 1])
    if port_match is None:
        raise ValueError("Surelog UHDM port relationship is malformed")
    direction = next(
        (
            _VPI_DIRECTIONS.get(match.group(1))
            for line in _relationship_lines(lines, index)
            if (match := re.match(r"^    \|vpiDirection:(\d+)\s*$", line))
        ),
        None,
    )
    if direction is None:
        raise ValueError(f"Surelog UHDM port {port_match.group(1)!r} has unsupported direction")
    return port_match.group(1), direction


def _decode_surelog_parameter(lines: list[str], index: int) -> str | None:
    match = re.match(r"^  \\_parameter: \([^.)]+\.([^)]+)\)", lines[index + 1])
    if match is None:
        raise ValueError("Surelog UHDM parameter relationship is malformed")
    if "    |vpiLocalParam:1" in _relationship_lines(lines, index):
        return None
    return match.group(1)


def compare_surelog_structure(module: object, facts: SurelogStructuralFacts) -> tuple[str, ...]:
    """Compare Surelog facts with a normalized Verilator top module."""

    port_details = getattr(module, "port_details", ())
    actual_ports = {(port.name, port.direction) for port in port_details}
    expected_ports = set(facts.ports)
    issues: list[str] = []
    if actual_ports != expected_ports:
        missing = sorted(actual_ports - expected_ports)
        extra = sorted(expected_ports - actual_ports)
        issues.append(f"port/direction mismatch: missing={missing!r}, extra={extra!r}")
    actual_parameters = {
        parameter.name for parameter in getattr(module, "parameter_details", ()) if not parameter.local
    }
    if actual_parameters != set(facts.parameters):
        missing_parameters = sorted(actual_parameters - set(facts.parameters))
        extra_parameters = sorted(set(facts.parameters) - actual_parameters)
        issues.append(f"parameter mismatch: missing={missing_parameters!r}, extra={extra_parameters!r}")
    return tuple(issues)


def _frontend(name: str, version: str, passed: bool, artifact: Path | None) -> dict[str, object]:
    return {
        "name": name,
        "version": version,
        "status": "passed" if passed else "failed",
        "artifact_sha256": _sha256(artifact) if artifact and artifact.is_file() else None,
    }


def _run(command: tuple[str, ...], cwd: Path, stdout: Path, stderr: Path) -> int:
    try:
        completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True, timeout=1800)
    except OSError as error:
        raise ValueError(f"frontend unavailable: {command[0]}: {error}") from error
    atomic_write_text(stdout, completed.stdout)
    atomic_write_text(stderr, completed.stderr)
    return completed.returncode


def _command(command: tuple[str, ...]) -> str:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or "command failed")
    return completed.stdout


def _tool_version(executable: str) -> str:
    for arguments in (("--version",), ("-version",), ("-V",)):
        try:
            completed = subprocess.run(
                (executable, *arguments), check=False, capture_output=True, text=True, timeout=30
            )
        except OSError:
            return "unavailable"
        text = (completed.stdout or completed.stderr).strip()
        if completed.returncode == 0 and text:
            return text.splitlines()[0]
    return "unknown"


def _source_digest(root: Path, sources: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(sources):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _repository_identity(root: Path) -> str:
    try:
        return _command(("git", "-C", str(root), "remote", "get-url", "origin")).strip()
    except ValueError:
        return root.name


def _surelog_artifact(root: Path) -> Path | None:
    return next((path for path in sorted(root.rglob("*.uhdm")) if path.is_file()), None)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_digest(payload: dict[str, object]) -> str:
    unsigned = dict(payload)
    unsigned.pop("evidence_sha256", None)
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
