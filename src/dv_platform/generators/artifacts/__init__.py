"""Generated artifact writing and provenance manifests."""

# ruff: noqa: F401

from __future__ import annotations

import ast
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from dv_platform.agent.contracts import FeedbackEvent
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import ArtifactKind, CLIConfig, GeneratedArtifact, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.security import redact_value
from dv_platform.generators.artifacts import persistence as _artifact_persistence
from dv_platform.generators.artifacts.constants import EXECUTION_MANIFEST_NAME, EXECUTION_MANIFEST_SCHEMA_VERSION
from dv_platform.generators.artifacts.persistence import (
    _command_available,
    _manifest_artifact_has_provenance,
    _module_directory,
    _parse_python,
    _project_manifest,
    _remove_path,
    _remove_stale_module_directories,
    _replace_module_directory,
    _replace_validation_path,
    _run_validator,
    _safe_artifact_path,
    _safe_identifier,
    _target_modules_directory,
    _validate_hdl_structure,
    _validate_module_with_tool,
    _validate_quality_requirements,
    _validate_relative_artifact_path,
    _validate_verilog_family,
    _validate_vhdl,
    _validator_version,
    _write_provenance_manifest,
)
from dv_platform.generators.signals import vhdl_identifier


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


def write_generated_artifacts(
    config: CLIConfig,
    artifacts: tuple[GeneratedArtifact, ...],
    *,
    replace_target: VerificationTarget | None = None,
    expected_modules: tuple[str, ...] | None = None,
    affected_paths: dict[tuple[VerificationTarget, str], set[str]] | None = None,
) -> ArtifactWriteResult:
    """Write generated artifacts under the configured output directory."""

    # Preserve the legacy monkeypatch seam after moving filesystem implementation.
    _artifact_persistence._validate_module_with_tool = _validate_module_with_tool
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
        written, provenance = _replace_module_directory(
            config,
            target,
            module,
            complete_artifacts,
            affected_paths=None if affected_paths is None else affected_paths.get((target, module), set()),
        )
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

    _validate_artifact_target(artifact)
    _validate_artifact_traceability(artifact)


def _validate_artifact_target(artifact: GeneratedArtifact) -> None:
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
        expected_name = f"tb_{vhdl_identifier(artifact.source_plan_module)}.vhd"
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


def _validate_artifact_traceability(artifact: GeneratedArtifact) -> None:
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
    provenance_items = _validate_manifest_file_records(payload, provenance, path)
    _validate_manifest_traceability(provenance_items, path)
    _validate_manifest_project(payload, path)


def _validate_manifest_file_records(
    payload: dict[str, Any],
    provenance: dict[str, Any],
    path: Path,
) -> tuple[dict[str, Any], ...]:
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
    return provenance_items


def _validate_manifest_traceability(provenance_items: tuple[dict[str, Any], ...], path: Path) -> None:
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


def _validate_manifest_project(payload: dict[str, Any], path: Path) -> None:
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
