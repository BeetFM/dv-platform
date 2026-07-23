"""Artifact filesystem publication and tool validation."""

from __future__ import annotations

import ast
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, GeneratedArtifact, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.security import redact_value
from dv_platform.generators.artifact_constants import EXECUTION_MANIFEST_NAME


def _module_directory(config: CLIConfig, target: VerificationTarget, module: str) -> Path:
    module = validate_path_component(module, "module")
    if target == VerificationTarget.FORMAL:
        return contained_path(config.output_dir, "formal", "modules", module)
    return contained_path(config.output_dir, "simulation", str(target), "modules", module)


def _target_modules_directory(config: CLIConfig, target: VerificationTarget) -> Path:
    if target == VerificationTarget.FORMAL:
        return contained_path(config.output_dir, "formal", "modules")
    return contained_path(config.output_dir, "simulation", str(target), "modules")


def _replace_module_directory(
    config: CLIConfig,
    target: VerificationTarget,
    module: str,
    artifacts: tuple[GeneratedArtifact, ...],
    affected_paths: set[str] | None = None,
) -> tuple[tuple[Path, ...], Path]:
    destination = _module_directory(config, target, module)
    parent = _target_modules_directory(config, target)
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{module}.staging-", dir=parent))
    backup: Path | None = None
    try:
        effective_artifacts: list[GeneratedArtifact] = []
        for artifact in artifacts:
            path = _safe_artifact_path(staging, artifact.path)
            existing = _safe_artifact_path(destination, artifact.path)
            preserve = (
                affected_paths is not None
                and artifact.path.as_posix() not in affected_paths
                and artifact.path.name != EXECUTION_MANIFEST_NAME
                and existing.is_file()
                and not existing.is_symlink()
            )
            if preserve:
                content = existing.read_text(encoding="utf-8")
                atomic_write_text(path, content)
                effective_artifacts.append(replace(artifact, content=content))
            else:
                atomic_write_text(path, artifact.content)
                effective_artifacts.append(artifact)
        effective = tuple(effective_artifacts)
        tool_validation = _validate_module_with_tool(config, staging, target, module, effective)
        tool_validation = _replace_validation_path(tool_validation, staging, destination)
        persisted_validation = cast(dict[str, Any], redact_value(config, tool_validation))
        if tool_validation["status"] == "failed":
            raise ValueError(
                f"Generated {target} artifacts failed tool validation for {module}: "
                f"{persisted_validation.get('stderr_tail') or persisted_validation.get('stdout_tail')}"
            )
        if config.strict and tool_validation.get("required") and tool_validation["status"] != "passed":
            raise ValueError(
                f"Strict generation requires tool validation for {target}/{module}: "
                f"{persisted_validation.get('reason', persisted_validation['status'])}"
            )
        _write_provenance_manifest(staging, target, module, effective, persisted_validation)

        if destination.exists() or destination.is_symlink():
            backup = Path(tempfile.mkdtemp(prefix=f".{module}.backup-", dir=parent))
            backup.rmdir()
            destination.replace(backup)
        try:
            staging.replace(destination)
        except BaseException:
            if backup is not None and backup.exists():
                backup.replace(destination)
            raise
        if backup is not None:
            _remove_path(backup)
    except BaseException:
        _remove_path(staging)
        raise

    written = tuple(destination / artifact.path for artifact in artifacts)
    return written, destination / "provenance.json"


def _remove_stale_module_directories(
    config: CLIConfig,
    target: VerificationTarget,
    expected_modules: set[str],
) -> None:
    modules_dir = _target_modules_directory(config, target)
    if not modules_dir.is_dir():
        return
    for candidate in modules_dir.iterdir():
        if candidate.name.startswith(".") or candidate.name in expected_modules:
            continue
        if candidate.is_dir() or candidate.is_symlink():
            _remove_path(candidate)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _write_provenance_manifest(
    directory: Path,
    target: VerificationTarget,
    module: str,
    artifacts: tuple[GeneratedArtifact, ...],
    tool_validation: dict[str, Any],
) -> Path:
    path = directory / "provenance.json"
    payload = {
        "schema_version": 2,
        "module": module,
        "target": str(target),
        "tool_validation": tool_validation,
        "artifacts": [
            {
                "path": str(artifact.path),
                "kind": str(artifact.kind),
                "source_plan_module": artifact.source_plan_module,
                "design_unit": artifact.design_unit or artifact.source_plan_module,
                "elaborated_design_unit": artifact.elaborated_design_unit,
                "specialization_id": artifact.specialization_id,
                "content_sha256": hashlib.sha256(artifact.content.encode("utf-8")).hexdigest(),
                "size_bytes": len(artifact.content.encode("utf-8")),
                "provenance_refs": [
                    {
                        "kind": str(ref.kind),
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in artifact.provenance_refs
                ],
                "quality_requirements": [
                    {
                        "requirement_id": requirement.requirement_id,
                        "description": requirement.description,
                        "satisfied": requirement.satisfied,
                        "reason": requirement.reason,
                    }
                    for requirement in artifact.quality_requirements
                ],
                "traceability": [
                    {
                        "trace_id": trace.trace_id,
                        "generated_symbol": trace.generated_symbol,
                        "check_indexes": list(trace.check_indexes),
                        "check_ids": list(trace.check_ids),
                        "requirement_ids": list(trace.requirement_ids),
                        "behavior_ids": list(trace.behavior_ids),
                        "claim_ids": list(trace.claim_ids),
                        "protocol_ids": list(trace.protocol_ids),
                        "register_ids": list(trace.register_ids),
                        "evidence_refs": [
                            {
                                "kind": str(ref.kind),
                                "source_id": ref.source_id,
                                "locator": ref.locator,
                                "summary": ref.summary,
                            }
                            for ref in trace.evidence_refs
                        ],
                    }
                    for trace in artifact.traceability
                ],
            }
            for artifact in artifacts
        ],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _validate_module_with_tool(
    config: CLIConfig,
    directory: Path,
    target: VerificationTarget,
    module: str,
    artifacts: tuple[GeneratedArtifact, ...],
) -> dict[str, Any]:
    if target == VerificationTarget.COCOTB:
        return {
            "required": True,
            "status": "passed",
            "validator": "python-ast",
            "validator_version": sys.version.split()[0],
        }
    if target == VerificationTarget.FORMAL:
        return {
            "required": False,
            "status": "deferred_to_run",
            "validator": "configured-formal-tool",
            "reason": "formal compilation and proof are validated by dv-platform run",
        }
    if target == VerificationTarget.UVM:
        return {
            "required": False,
            "status": "deferred_to_run",
            "validator": "configured-uvm-simulator",
            "reason": "UVM compilation, elaboration, and execution are validated by dv-platform run",
        }
    if target in {VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG}:
        return _validate_verilog_family(config, directory, target, module, artifacts)
    if target == VerificationTarget.VHDL:
        return _validate_vhdl(config, directory, artifacts)
    return {"required": True, "status": "unavailable", "validator": None, "reason": "no validator exists"}


def _validate_verilog_family(
    config: CLIConfig,
    directory: Path,
    target: VerificationTarget,
    module: str,
    artifacts: tuple[GeneratedArtifact, ...],
) -> dict[str, Any]:
    command_prefix = shlex.split(config.verilator_executable)
    if not command_prefix or not _command_available(command_prefix[0]):
        return {
            "required": True,
            "status": "unavailable",
            "validator": config.verilator_executable,
            "reason": "configured Verilator executable is unavailable",
        }
    manifest = _project_manifest(config)
    if manifest is None:
        return {
            "required": True,
            "status": "unavailable",
            "validator": config.verilator_executable,
            "reason": "project manifest is missing or invalid; run analyze-rtl first",
        }
    sources = [
        str(item["path"])
        for item in manifest.get("hdl_files", ())
        if isinstance(item, dict) and Path(str(item.get("path", ""))).suffix.lower() in {".v", ".sv"}
    ]
    generated = [
        str(directory / artifact.path) for artifact in artifacts if artifact.path.suffix.lower() in {".v", ".sv"}
    ]
    if not sources or not generated:
        return {
            "required": True,
            "status": "unavailable",
            "validator": config.verilator_executable,
            "reason": "no Verilog/SystemVerilog sources were available to lint",
        }
    top = f"tb_{_safe_identifier(module)}"
    command = [
        *command_prefix,
        "--lint-only",
        "--timing",
        "-Wno-fatal",
        "--top-module",
        top,
    ]
    command.extend(f"-I{path}" for path in manifest.get("include_paths", ()))
    command.extend(f"-D{define}" for define in manifest.get("defines", ()))
    command.extend((*sources, *generated))
    return _run_validator(command, config.repo_root, validator=f"verilator-{target}")


def _validate_vhdl(
    config: CLIConfig,
    directory: Path,
    artifacts: tuple[GeneratedArtifact, ...],
) -> dict[str, Any]:
    configured = next(
        (simulator for simulator in config.simulators if simulator.target == VerificationTarget.VHDL), None
    )
    command_prefix = shlex.split(configured.command) if configured is not None else ["ghdl"]
    if not command_prefix or Path(command_prefix[0]).name != "ghdl" or not _command_available(command_prefix[0]):
        return {
            "required": True,
            "status": "unavailable",
            "validator": command_prefix[0] if command_prefix else None,
            "reason": "GHDL is unavailable or the configured VHDL adapter is not GHDL",
        }
    manifest = _project_manifest(config)
    sources = (
        []
        if manifest is None
        else [
            str(item["path"])
            for item in manifest.get("hdl_files", ())
            if isinstance(item, dict) and Path(str(item.get("path", ""))).suffix.lower() in {".vhd", ".vhdl"}
        ]
    )
    generated = [
        str(directory / artifact.path) for artifact in artifacts if artifact.path.suffix.lower() in {".vhd", ".vhdl"}
    ]
    if not sources or not generated:
        return {
            "required": True,
            "status": "unavailable",
            "validator": command_prefix[0],
            "reason": "no VHDL DUT sources and generated testbench were available to analyze",
        }
    return _run_validator(
        [*command_prefix, "-s", "--std=08", *sources, *generated],
        config.repo_root,
        validator="ghdl",
    )


def _project_manifest(config: CLIConfig) -> dict[str, Any] | None:
    path = config.work_dir / "project-manifest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _command_available(executable: str) -> bool:
    if Path(executable).is_absolute() or "/" in executable:
        return Path(executable).is_file()
    return shutil.which(executable) is not None


def _run_validator(command: list[str], cwd: Path, validator: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "required": True,
            "status": "failed",
            "validator": validator,
            "command": command,
            "reason": str(error),
        }
    return {
        "required": True,
        "status": "passed" if completed.returncode == 0 else "failed",
        "validator": validator,
        "validator_version": _validator_version(command[0]),
        "command": command,
        "return_code": completed.returncode,
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }


def _validator_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            (executable, "--version"),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = completed.stdout.strip() or completed.stderr.strip()
    return output.splitlines()[0] if output else None


def _replace_validation_path(
    validation: dict[str, Any],
    source: Path,
    destination: Path,
) -> dict[str, Any]:
    source_text = str(source)
    destination_text = str(destination)
    normalized: dict[str, Any] = {}
    for key, value in validation.items():
        if isinstance(value, str):
            normalized[key] = value.replace(source_text, destination_text)
        elif isinstance(value, list):
            normalized[key] = [
                item.replace(source_text, destination_text) if isinstance(item, str) else item for item in value
            ]
        else:
            normalized[key] = value
    return normalized


def _safe_artifact_path(directory: Path, relative_path: Path) -> Path:
    _validate_relative_artifact_path(relative_path)
    path = directory / relative_path
    resolved_directory = directory.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path != resolved_directory and resolved_directory not in resolved_path.parents:
        raise ValueError(f"Generated artifact path escapes output directory: {relative_path}")
    return path


def _validate_relative_artifact_path(path: Path) -> None:
    raw_path = str(path)
    if (
        path.is_absolute()
        or raw_path in {"", "."}
        or ".." in path.parts
        or "\\" in raw_path
        or (path.parts and ":" in path.parts[0])
        or any(ord(character) < 32 or ord(character) == 127 for character in raw_path)
    ):
        raise ValueError(f"Generated artifact path must be relative and stay inside its module directory: {path}")


def _validate_quality_requirements(artifact: GeneratedArtifact) -> None:
    if not artifact.quality_requirements:
        raise ValueError(f"Generated executable artifact has no quality requirements: {artifact.path}")
    failed = tuple(requirement for requirement in artifact.quality_requirements if not requirement.satisfied)
    if failed:
        reasons = "; ".join(
            requirement.requirement_id + ": " + (requirement.reason or requirement.description)
            for requirement in failed
        )
        raise ValueError(f"Generated executable artifact failed quality gate: {artifact.path}: {reasons}")


def _parse_python(content: str, path: Path) -> None:
    try:
        ast.parse(content, filename=str(path))
    except SyntaxError as error:
        raise ValueError(f"Generated Python artifact has invalid syntax: {path}: {error.msg}") from error


def _validate_hdl_structure(content: str, opening: str, closing: str, path: Path) -> None:
    if opening not in content or closing not in content:
        raise ValueError(f"Generated HDL artifact is structurally incomplete: {path}")


def _manifest_artifact_has_provenance(item: object, expected_name: str) -> bool:
    if not isinstance(item, dict):
        return False
    provenance_refs = item.get("provenance_refs")
    return item.get("path") == expected_name and isinstance(provenance_refs, list) and bool(provenance_refs)


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
