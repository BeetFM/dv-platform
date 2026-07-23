# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dv_platform.core.models import VerificationTarget
from dv_platform.core.paths import is_within
from dv_platform.generators.artifacts import validate_generated_directory


def _generated_module_status(target: VerificationTarget, module_dir: Path) -> dict[str, Any]:
    provenance_path = module_dir / "provenance.json"
    result: dict[str, Any] = {
        "target": str(target),
        "module": module_dir.name,
        "path": str(module_dir),
        "provenance": str(provenance_path),
        "provenance_present": provenance_path.is_file(),
        "provenance_sha256": None,
        "provenance_invalid": 0,
        "artifacts": 0,
        "quality_total": 0,
        "quality_missing": 0,
        "quality_failed": 0,
        "artifacts_missing": 0,
        "integrity_missing": 0,
        "integrity_failed": 0,
        "tool_validation_missing": 0,
        "tool_validation_failed": 0,
        "traceability_missing": 0,
        "execution_manifest_invalid": 0,
        "status": "missing_provenance",
    }
    if module_dir.is_symlink() or not is_within(provenance_path, module_dir):
        result["provenance_invalid"] = 1
        result["status"] = "unsafe_module_path"
        return result
    if not provenance_path.is_file():
        result["provenance_invalid"] = 1
        return result
    try:
        provenance_bytes = provenance_path.read_bytes()
        provenance = json.loads(provenance_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = str(error)
        return result
    result["provenance_sha256"] = hashlib.sha256(provenance_bytes).hexdigest()
    if not isinstance(provenance, dict) or provenance.get("schema_version") != 2:
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = "unsupported or missing provenance schema"
        return result
    artifacts = provenance.get("artifacts", ())
    if not isinstance(artifacts, list):
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = "artifacts is not a list"
        return result
    if provenance.get("module") != module_dir.name or provenance.get("target") != str(target):
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = "module or target does not match provenance path"
        return result
    _apply_artifact_metrics(result, target, module_dir, provenance, artifacts)
    result["status"] = _generated_status_value(result)
    return result


def _apply_artifact_metrics(result, target, module_dir, provenance, artifacts) -> None:
    quality_requirements = [
        requirement
        for artifact in artifacts
        if isinstance(artifact, dict)
        for requirement in artifact.get("quality_requirements", ())
        if isinstance(requirement, dict)
    ]
    failed = tuple(requirement for requirement in quality_requirements if not bool(requirement.get("satisfied")))
    executable_kinds = {"testbench", "formal_harness", "assertion", "run_script"}
    executable_artifacts = tuple(
        artifact for artifact in artifacts if isinstance(artifact, dict) and artifact.get("kind") in executable_kinds
    )
    artifacts_without_quality = tuple(
        artifact for artifact in executable_artifacts if not artifact.get("quality_requirements")
    )
    artifacts_without_traceability = tuple(
        artifact for artifact in executable_artifacts if not artifact.get("traceability")
    )
    artifact_checks = tuple(
        _artifact_integrity(module_dir, artifact) for artifact in artifacts if isinstance(artifact, dict)
    )
    tool_validation = provenance.get("tool_validation")
    required_validation = isinstance(tool_validation, dict) and bool(tool_validation.get("required"))
    validation_status = str(tool_validation.get("status")) if isinstance(tool_validation, dict) else "missing"
    result["artifacts"] = len(artifacts)
    result["quality_total"] = len(quality_requirements)
    result["quality_missing"] = len(artifacts_without_quality)
    result["quality_failed"] = len(failed)
    result["artifacts_missing"] = sum(1 for check in artifact_checks if check == "missing")
    result["integrity_missing"] = sum(1 for check in artifact_checks if check == "integrity_missing")
    result["integrity_failed"] = sum(1 for check in artifact_checks if check == "integrity_failed")
    result["tool_validation_missing"] = int(
        not isinstance(tool_validation, dict) or (required_validation and validation_status not in {"passed", "failed"})
    )
    result["tool_validation_failed"] = int(required_validation and validation_status == "failed")
    result["traceability_missing"] = len(artifacts_without_traceability)
    try:
        validate_generated_directory(target, module_dir.name, module_dir)
    except (OSError, ValueError) as error:
        result["execution_manifest_invalid"] = 1
        result["execution_manifest_error"] = str(error)
    result["tool_validation"] = tool_validation


def _generated_status_value(result) -> str:
    if result["artifacts_missing"]:
        return "artifacts_missing"
    if result["integrity_failed"]:
        return "integrity_failed"
    if result["integrity_missing"]:
        return "integrity_missing"
    if result["tool_validation_failed"]:
        return "tool_validation_failed"
    if result["tool_validation_missing"]:
        return "tool_validation_missing"
    if result["execution_manifest_invalid"]:
        return "execution_manifest_invalid"
    if result["traceability_missing"]:
        return "traceability_missing"
    if result["quality_missing"]:
        return "quality_missing"
    if result["quality_failed"]:
        return "quality_failed"
    return "ok"


def _missing_expected_generated(
    plan_status: dict[str, Any],
    generated: dict[str, Any],
) -> list[dict[str, str]]:
    expected = {
        (str(item["target"]), str(item["module"]))
        for item in plan_status.get("expected_generated", ())
        if isinstance(item, dict)
    }
    actual = {
        (str(item["target"]), str(item["module"])) for item in generated.get("modules", ()) if isinstance(item, dict)
    }
    return [{"target": target, "module": module} for target, module in sorted(expected - actual)]


def _unexpected_generated(
    plan_status: dict[str, Any],
    generated: dict[str, Any],
) -> list[dict[str, str]]:
    expected = {
        (str(item["target"]), str(item["module"]))
        for item in plan_status.get("expected_generated", ())
        if isinstance(item, dict)
    }
    actual = {
        (str(item["target"]), str(item["module"])) for item in generated.get("modules", ()) if isinstance(item, dict)
    }
    return [{"target": target, "module": module} for target, module in sorted(actual - expected)]


def _artifact_integrity(module_dir: Path, artifact: dict[str, Any]) -> str:
    raw_path = artifact.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return "integrity_failed"
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return "integrity_failed"
    path = module_dir / relative
    if not is_within(path, module_dir):
        return "integrity_failed"
    if not path.is_file():
        return "missing"
    expected_hash = artifact.get("content_sha256")
    expected_size = artifact.get("size_bytes")
    if not isinstance(expected_hash, str) or not isinstance(expected_size, int):
        return "integrity_missing"
    try:
        content = path.read_bytes()
    except OSError:
        return "integrity_failed"
    if len(content) != expected_size or hashlib.sha256(content).hexdigest() != expected_hash:
        return "integrity_failed"
    return "ok"
