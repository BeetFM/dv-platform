"""Generated artifact writing and provenance manifests."""

from __future__ import annotations

import ast
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dv_platform.agent.contracts import FeedbackEvent
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import ArtifactKind, CLIConfig, GeneratedArtifact, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.security import redact_value


@dataclass(frozen=True)
class ArtifactWriteResult:
    """Filesystem paths written for generated artifacts."""

    artifact_paths: tuple[Path, ...]
    provenance_paths: tuple[Path, ...]


def select_affected_artifacts(
    artifacts: tuple[GeneratedArtifact, ...], events: tuple[FeedbackEvent, ...]
) -> tuple[GeneratedArtifact, ...]:
    """Select only artifacts dependent on feedback-linked checks or artifact paths."""

    check_ids = {event.check_id for event in events if event.check_id}
    explicit_paths = {path for event in events for path in event.affected_artifacts}
    selected: list[GeneratedArtifact] = []
    for artifact in artifacts:
        if artifact.path.as_posix() in explicit_paths or str(artifact.path) in explicit_paths:
            selected.append(artifact)
            continue
        if any(check_ids.intersection(trace.check_ids) for trace in artifact.traceability):
            selected.append(artifact)
    return tuple(selected)


EXECUTION_MANIFEST_NAME = "execution-manifest.json"
EXECUTION_MANIFEST_SCHEMA_VERSION = 3


def write_generated_artifacts(
    config: CLIConfig,
    artifacts: tuple[GeneratedArtifact, ...],
    *,
    replace_target: VerificationTarget | None = None,
    expected_modules: tuple[str, ...] | None = None,
) -> ArtifactWriteResult:
    """Write generated artifacts under the configured output directory."""

    manifests: dict[tuple[VerificationTarget, str], list[GeneratedArtifact]] = {}
    for artifact in artifacts:
        if artifact.path == Path(EXECUTION_MANIFEST_NAME):
            raise ValueError(f"Generated artifact path is reserved: {artifact.path}")
        validate_generated_artifact(artifact)
        validate_path_component(artifact.source_plan_module, "source plan module")
        manifests.setdefault((artifact.target, artifact.source_plan_module), []).append(artifact)

    if replace_target is not None:
        if any(target != replace_target for target, _module in manifests):
            raise ValueError(f"Cannot replace {replace_target} with artifacts for another target")
        expected = tuple(validate_path_component(module, "expected module") for module in (expected_modules or ()))
        if set(expected) != {module for _target, module in manifests}:
            raise ValueError("Generated artifacts do not match the expected module set")

    artifact_paths: list[Path] = []
    provenance_paths: list[Path] = []
    for (target, module), module_artifacts in sorted(manifests.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        complete_artifacts = (*module_artifacts, _execution_manifest_artifact(config, target, module, module_artifacts))
        written, provenance = _replace_module_directory(config, target, module, complete_artifacts)
        artifact_paths.extend(written)
        provenance_paths.append(provenance)

    if replace_target is not None:
        _remove_stale_module_directories(config, replace_target, set(expected_modules or ()))

    return ArtifactWriteResult(artifact_paths=tuple(artifact_paths), provenance_paths=tuple(provenance_paths))


def validate_generated_artifact(artifact: GeneratedArtifact) -> None:
    """Validate one generated artifact before it is written to disk."""

    _validate_relative_artifact_path(artifact.path)
    if not artifact.provenance_refs:
        raise ValueError(f"Generated artifact has no provenance refs: {artifact.path}")
    if artifact.kind in {
        ArtifactKind.TESTBENCH,
        ArtifactKind.ASSERTION,
        ArtifactKind.FORMAL_HARNESS,
        ArtifactKind.RUN_SCRIPT,
    }:
        _validate_quality_requirements(artifact)

    if artifact.target == VerificationTarget.COCOTB and artifact.kind == ArtifactKind.TESTBENCH:
        expected_name = f"test_{_safe_identifier(artifact.source_plan_module)}.py"
        if artifact.path != Path(expected_name):
            raise ValueError(f"cocotb test artifact must be named {expected_name}: {artifact.path}")
        _parse_python(artifact.content, artifact.path)
    if artifact.target == VerificationTarget.FORMAL and artifact.kind == ArtifactKind.FORMAL_HARNESS:
        _validate_hdl_structure(artifact.content, "module", "endmodule", artifact.path)
    if artifact.target == VerificationTarget.SYSTEMVERILOG and artifact.kind == ArtifactKind.TESTBENCH:
        expected_name = f"tb_{_safe_identifier(artifact.source_plan_module)}.sv"
        if artifact.path != Path(expected_name):
            raise ValueError(f"SystemVerilog test artifact must be named {expected_name}: {artifact.path}")
        _validate_hdl_structure(artifact.content, "module", "endmodule", artifact.path)
    if artifact.target == VerificationTarget.VERILOG and artifact.kind == ArtifactKind.TESTBENCH:
        expected_name = f"tb_{_safe_identifier(artifact.source_plan_module)}.v"
        if artifact.path != Path(expected_name):
            raise ValueError(f"Verilog test artifact must be named {expected_name}: {artifact.path}")
        _validate_hdl_structure(artifact.content, "module", "endmodule", artifact.path)
    if artifact.target == VerificationTarget.VHDL and artifact.kind == ArtifactKind.TESTBENCH:
        expected_name = f"tb_{_safe_identifier(artifact.source_plan_module)}.vhd"
        if artifact.path != Path(expected_name):
            raise ValueError(f"VHDL test artifact must be named {expected_name}: {artifact.path}")
        _validate_hdl_structure(artifact.content.lower(), "entity ", "end architecture", artifact.path)
    if artifact.target == VerificationTarget.UVM:
        allowed_names = {
            f"{_safe_identifier(artifact.source_plan_module)}_pkg.sv",
            f"{_safe_identifier(artifact.source_plan_module)}_if.sv",
            f"tb_{_safe_identifier(artifact.source_plan_module)}_uvm.sv",
            "README.md",
        }
        if artifact.path not in {Path(name) for name in allowed_names}:
            raise ValueError(f"UVM artifact has unexpected name: {artifact.path}")

    if artifact.kind in {
        ArtifactKind.TESTBENCH,
        ArtifactKind.ASSERTION,
        ArtifactKind.FORMAL_HARNESS,
        ArtifactKind.RUN_SCRIPT,
    }:
        if not artifact.traceability:
            raise ValueError(f"Generated executable artifact has no plan traceability: {artifact.path}")
        for trace in artifact.traceability:
            if not trace.trace_id or not trace.generated_symbol:
                raise ValueError(f"Generated executable artifact has invalid plan traceability: {artifact.path}")
            if not (
                trace.check_indexes
                or trace.check_ids
                or trace.requirement_ids
                or trace.behavior_ids
                or trace.claim_ids
                or trace.protocol_ids
                or trace.register_ids
            ):
                raise ValueError(f"Generated executable trace has no plan record identifiers: {artifact.path}")
            if not trace.evidence_refs:
                raise ValueError(f"Generated executable trace has no evidence refs: {artifact.path}")


def validate_generated_directory(target: VerificationTarget, module: str, generated_dir: Path) -> None:
    """Validate generated files already on disk before running them."""

    module = validate_path_component(module, "generated module")
    if target == VerificationTarget.FORMAL:
        _validate_formal_directory(module, generated_dir)
        return

    if target == VerificationTarget.COCOTB:
        test_path = generated_dir / f"test_{_safe_identifier(module)}.py"
        if not test_path.is_file():
            raise ValueError(f"Missing generated cocotb test: {test_path}")
        _parse_python(test_path.read_text(encoding="utf-8"), test_path)

    provenance = _load_and_validate_provenance(target, module, generated_dir)
    _validate_manifest_artifacts(generated_dir, provenance)
    _validate_execution_manifest(target, module, generated_dir, provenance)

    if target == VerificationTarget.COCOTB:
        if not any(_manifest_artifact_has_provenance(item, test_path.name) for item in provenance["artifacts"]):
            raise ValueError(
                f"Provenance manifest lacks refs for {test_path.name}: {generated_dir / 'provenance.json'}"
            )


def _validate_formal_directory(module: str, generated_dir: Path) -> None:
    module_name = _safe_identifier(module)
    harness_path = generated_dir / f"formal_{module_name}.sv"
    if not harness_path.is_file():
        raise ValueError(f"Missing generated formal harness: {harness_path}")
    sby_path = generated_dir / f"{module_name}.sby"
    if not sby_path.is_file():
        raise ValueError(f"Missing generated SymbiYosys file: {sby_path}")

    provenance = _load_and_validate_provenance(VerificationTarget.FORMAL, module, generated_dir)
    _validate_manifest_artifacts(generated_dir, provenance)
    _validate_execution_manifest(VerificationTarget.FORMAL, module, generated_dir, provenance)
    provenance_path = generated_dir / "provenance.json"
    artifacts = provenance["artifacts"]
    for expected_name in (harness_path.name, sby_path.name):
        if not any(_manifest_artifact_has_provenance(item, expected_name) for item in artifacts):
            raise ValueError(f"Provenance manifest lacks refs for {expected_name}: {provenance_path}")


def _load_and_validate_provenance(
    target: VerificationTarget,
    module: str,
    generated_dir: Path,
) -> dict[str, Any]:
    provenance_path = generated_dir / "provenance.json"
    if not provenance_path.is_file():
        raise ValueError(f"Missing generated provenance manifest: {provenance_path}")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid provenance manifest JSON: {provenance_path}: {error}") from error
    if not isinstance(provenance, dict):
        raise ValueError(f"Provenance manifest must contain an object: {provenance_path}")
    if provenance.get("schema_version") != 2:
        raise ValueError(f"Unsupported provenance schema in {provenance_path}")
    if provenance.get("module") != module:
        raise ValueError(f"Provenance manifest module mismatch: {provenance_path}")
    if provenance.get("target") != str(target):
        raise ValueError(f"Provenance manifest target mismatch: {provenance_path}")
    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"Provenance manifest has no artifacts: {provenance_path}")
    return provenance


def _validate_manifest_artifacts(generated_dir: Path, provenance: dict[str, Any]) -> None:
    provenance_path = generated_dir / "provenance.json"
    for item in provenance["artifacts"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"Invalid artifact entry in provenance manifest: {provenance_path}")
        relative_path = Path(item["path"])
        artifact_path = _safe_artifact_path(generated_dir, relative_path)
        if not artifact_path.is_file():
            raise ValueError(f"Generated artifact is missing: {artifact_path}")
        try:
            content = artifact_path.read_bytes()
        except OSError as error:
            raise ValueError(f"Could not read generated artifact: {artifact_path}: {error}") from error
        if item.get("size_bytes") != len(content):
            raise ValueError(f"Generated artifact size does not match provenance: {artifact_path}")
        if item.get("content_sha256") != hashlib.sha256(content).hexdigest():
            raise ValueError(f"Generated artifact content does not match provenance: {artifact_path}")


def _execution_manifest_artifact(
    config: CLIConfig,
    target: VerificationTarget,
    module: str,
    artifacts: list[GeneratedArtifact],
) -> GeneratedArtifact:
    elaborated_parameters = (
        tuple(
            parameter
            for parameter in artifacts[0].elaborated_parameters
            if not parameter.local and parameter.default_value is not None
        )
        if artifacts
        else ()
    )
    if any(artifact.elaborated_parameters != artifacts[0].elaborated_parameters for artifact in artifacts[1:]):
        raise ValueError(f"Generated artifacts disagree on elaborated parameters for {module}")
    identities = {
        (artifact.design_unit, artifact.elaborated_design_unit, artifact.specialization_id) for artifact in artifacts
    }
    if len(identities) > 1:
        raise ValueError(f"Generated artifacts disagree on design-unit identity for {module}")
    design_unit, elaborated_design_unit, specialization_id = next(iter(identities), (module, None, None))
    project_manifest_path = config.work_dir / "project-manifest.json"
    project_manifest = _project_manifest(config)
    project_manifest_sha256: str | None = None
    project_manifest_text_path: str | None = None
    if project_manifest is not None and project_manifest_path.is_file():
        project_manifest_sha256 = hashlib.sha256(project_manifest_path.read_bytes()).hexdigest()
        project_manifest_text_path = str(project_manifest_path)

    hdl_files: list[dict[str, Any]] = []
    if project_manifest is not None:
        for item in project_manifest.get("hdl_files", ()):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            source = Path(item["path"])
            if not source.is_file():
                raise ValueError(f"Project source listed in manifest is missing: {source}")
            content = source.read_bytes()
            hdl_files.append(
                {
                    "path": str(source),
                    "language": item.get("language"),
                    "library": item.get("library"),
                    "size_bytes": len(content),
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    if config.strict and (project_manifest_sha256 is None or not hdl_files):
        raise ValueError("Strict generation requires a current project manifest with at least one HDL input")

    adapter: dict[str, Any]
    if target == VerificationTarget.FORMAL:
        tool = config.formal_tools[0] if len(config.formal_tools) == 1 else None
        adapter = {
            "kind": "formal",
            "name": tool.name if tool is not None else None,
            "command": tool.command if tool is not None else None,
        }
    else:
        simulators = tuple(simulator for simulator in config.simulators if simulator.target == target)
        simulator = simulators[0] if len(simulators) == 1 else None
        adapter = {
            "kind": "simulation",
            "name": simulator.name if simulator is not None else None,
            "command": simulator.command if simulator is not None else None,
        }

    payload = {
        "schema_version": EXECUTION_MANIFEST_SCHEMA_VERSION,
        "module": module,
        "design_unit": design_unit or module,
        "elaborated_design_unit": elaborated_design_unit,
        "specialization_id": specialization_id,
        "target": str(target),
        "adapter": adapter,
        "elaborated_parameters": [
            {"name": parameter.name, "value": parameter.default_value} for parameter in elaborated_parameters
        ],
        "generated_files": [
            {
                "path": str(artifact.path),
                "kind": str(artifact.kind),
                "trace_ids": [trace.trace_id for trace in artifact.traceability],
            }
            for artifact in artifacts
        ],
        "project": {
            "manifest_path": project_manifest_text_path,
            "manifest_sha256": project_manifest_sha256,
            "hdl_files": hdl_files,
            "include_paths": list(project_manifest.get("include_paths", ())) if project_manifest is not None else [],
            "defines": list(project_manifest.get("defines", ())) if project_manifest is not None else [],
            "parameter_overrides": list(project_manifest.get("parameter_overrides", ()))
            if project_manifest is not None
            else [],
            "top_modules": list(project_manifest.get("top_modules", ())) if project_manifest is not None else [],
        },
    }
    refs = tuple(dict.fromkeys(ref for artifact in artifacts for ref in artifact.provenance_refs))
    return GeneratedArtifact(
        path=Path(EXECUTION_MANIFEST_NAME),
        kind=ArtifactKind.REPORT,
        target=target,
        content=json.dumps(payload, indent=2, sort_keys=True) + "\n",
        source_plan_module=module,
        design_unit=design_unit or module,
        elaborated_design_unit=elaborated_design_unit,
        specialization_id=specialization_id,
        provenance_refs=refs,
    )


def _validate_execution_manifest(
    target: VerificationTarget,
    module: str,
    generated_dir: Path,
    provenance: dict[str, Any],
) -> None:
    path = generated_dir / EXECUTION_MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid generated execution manifest: {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") not in {2, EXECUTION_MANIFEST_SCHEMA_VERSION}:
        raise ValueError(f"Unsupported generated execution manifest schema: {path}")
    if payload.get("target") != str(target) or payload.get("module") != module:
        raise ValueError(f"Generated execution manifest identity mismatch: {path}")
    if payload.get("schema_version") == EXECUTION_MANIFEST_SCHEMA_VERSION and (
        not isinstance(payload.get("design_unit"), str) or not payload["design_unit"]
    ):
        raise ValueError(f"Generated execution manifest has no design-unit identity: {path}")

    generated_files = payload.get("generated_files")
    if not isinstance(generated_files, list):
        raise ValueError(f"Generated execution manifest has no generated file list: {path}")
    declared_files = {
        item.get("path"): item
        for item in generated_files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if len(declared_files) != len(generated_files):
        raise ValueError(f"Generated execution manifest has invalid or duplicate file records: {path}")
    provenance_items = tuple(item for item in provenance["artifacts"] if isinstance(item, dict))
    expected_paths = {
        item.get("path")
        for item in provenance_items
        if isinstance(item.get("path"), str) and item.get("path") != EXECUTION_MANIFEST_NAME
    }
    if set(declared_files) != expected_paths:
        raise ValueError(f"Generated execution manifest file set does not match provenance: {path}")

    for item in provenance_items:
        artifact_path = item.get("path")
        if artifact_path == EXECUTION_MANIFEST_NAME or not isinstance(artifact_path, str):
            continue
        declared = declared_files[artifact_path]
        expected_trace_ids = [
            trace.get("trace_id")
            for trace in item.get("traceability", ())
            if isinstance(trace, dict) and isinstance(trace.get("trace_id"), str)
        ]
        if declared.get("kind") != item.get("kind") or declared.get("trace_ids") != expected_trace_ids:
            raise ValueError(f"Generated execution manifest metadata does not match provenance: {path}")

    executable_kinds = {
        str(ArtifactKind.TESTBENCH),
        str(ArtifactKind.ASSERTION),
        str(ArtifactKind.FORMAL_HARNESS),
        str(ArtifactKind.RUN_SCRIPT),
    }
    for item in provenance_items:
        if item.get("kind") not in executable_kinds:
            continue
        traceability = item.get("traceability")
        if not isinstance(traceability, list) or not traceability:
            raise ValueError(f"Generated executable artifact lacks plan traceability: {path}")

    project = payload.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"Generated execution manifest has no project input record: {path}")
    manifest_path = project.get("manifest_path")
    manifest_sha256 = project.get("manifest_sha256")
    if not isinstance(manifest_path, str) or not isinstance(manifest_sha256, str):
        raise ValueError(f"Generated execution manifest is not bound to a project manifest: {path}")
    current_manifest = Path(manifest_path)
    if not current_manifest.is_file() or hashlib.sha256(current_manifest.read_bytes()).hexdigest() != manifest_sha256:
        raise ValueError(f"Project manifest changed after generation: {current_manifest}")
    sources = project.get("hdl_files")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"Generated execution manifest has no HDL input list: {path}")
    for item in sources:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"Generated execution manifest has an invalid HDL input record: {path}")
        source = Path(item["path"])
        if not source.is_file():
            raise ValueError(f"Generated execution input is missing: {source}")
        content = source.read_bytes()
        if item.get("size_bytes") != len(content) or item.get("content_sha256") != hashlib.sha256(content).hexdigest():
            raise ValueError(f"Generated execution input changed after generation: {source}")


def _artifact_directory(config: CLIConfig, artifact: GeneratedArtifact) -> Path:
    return _module_directory(config, artifact.target, artifact.source_plan_module)


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
) -> tuple[tuple[Path, ...], Path]:
    destination = _module_directory(config, target, module)
    parent = _target_modules_directory(config, target)
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{module}.staging-", dir=parent))
    backup: Path | None = None
    try:
        for artifact in artifacts:
            path = _safe_artifact_path(staging, artifact.path)
            atomic_write_text(path, artifact.content)
        tool_validation = _validate_module_with_tool(config, staging, target, module, artifacts)
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
        _write_provenance_manifest(staging, target, module, artifacts, persisted_validation)

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
            "required": True,
            "status": "unavailable",
            "validator": None,
            "reason": "no UVM-capable compile adapter is configured",
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
    with tempfile.TemporaryDirectory(prefix="dv-platform-ghdl-") as work_dir:
        return _run_validator(
            [*command_prefix, "-s", "--std=08", f"--workdir={work_dir}", *sources, *generated],
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
