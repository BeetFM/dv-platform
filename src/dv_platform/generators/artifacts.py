"""Generated artifact writing and provenance manifests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path

from dv_platform.core.models import ArtifactKind, CLIConfig, GeneratedArtifact, VerificationTarget


@dataclass(frozen=True)
class ArtifactWriteResult:
    """Filesystem paths written for generated artifacts."""

    artifact_paths: tuple[Path, ...]
    provenance_paths: tuple[Path, ...]


def write_generated_artifacts(config: CLIConfig, artifacts: tuple[GeneratedArtifact, ...]) -> ArtifactWriteResult:
    """Write generated artifacts under the configured output directory."""

    artifact_paths: list[Path] = []
    manifests: dict[tuple[VerificationTarget, str], list[GeneratedArtifact]] = {}
    for artifact in artifacts:
        validate_generated_artifact(artifact)
        directory = _artifact_directory(config, artifact)
        directory.mkdir(parents=True, exist_ok=True)
        path = _safe_artifact_path(directory, artifact.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
        artifact_paths.append(path)
        manifests.setdefault((artifact.target, artifact.source_plan_module), []).append(artifact)

    provenance_paths = tuple(
        _write_provenance_manifest(config, target, module, tuple(module_artifacts))
        for (target, module), module_artifacts in sorted(manifests.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    )
    return ArtifactWriteResult(artifact_paths=tuple(artifact_paths), provenance_paths=provenance_paths)


def validate_generated_artifact(artifact: GeneratedArtifact) -> None:
    """Validate one generated artifact before it is written to disk."""

    _validate_relative_artifact_path(artifact.path)
    if not artifact.provenance_refs:
        raise ValueError(f"Generated artifact has no provenance refs: {artifact.path}")

    if artifact.target == VerificationTarget.COCOTB and artifact.kind == ArtifactKind.TESTBENCH:
        expected_name = f"test_{_safe_identifier(artifact.source_plan_module)}.py"
        if artifact.path != Path(expected_name):
            raise ValueError(f"cocotb test artifact must be named {expected_name}: {artifact.path}")
        _parse_python(artifact.content, artifact.path)


def validate_generated_directory(target: VerificationTarget, module: str, generated_dir: Path) -> None:
    """Validate generated files already on disk before running them."""

    if target == VerificationTarget.FORMAL:
        _validate_formal_directory(module, generated_dir)
        return
    if target != VerificationTarget.COCOTB:
        return

    test_path = generated_dir / f"test_{_safe_identifier(module)}.py"
    if not test_path.is_file():
        raise ValueError(f"Missing generated cocotb test: {test_path}")
    _parse_python(test_path.read_text(encoding="utf-8"), test_path)

    provenance_path = generated_dir / "provenance.json"
    if not provenance_path.is_file():
        raise ValueError(f"Missing generated provenance manifest: {provenance_path}")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid provenance manifest JSON: {provenance_path}: {error}") from error

    if provenance.get("module") != module:
        raise ValueError(f"Provenance manifest module mismatch: {provenance_path}")
    if provenance.get("target") != str(target):
        raise ValueError(f"Provenance manifest target mismatch: {provenance_path}")

    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"Provenance manifest has no artifacts: {provenance_path}")
    expected_name = test_path.name
    if not any(_manifest_artifact_has_provenance(item, expected_name) for item in artifacts):
        raise ValueError(f"Provenance manifest lacks refs for {expected_name}: {provenance_path}")


def _validate_formal_directory(module: str, generated_dir: Path) -> None:
    module_name = _safe_identifier(module)
    harness_path = generated_dir / f"formal_{module_name}.sv"
    if not harness_path.is_file():
        raise ValueError(f"Missing generated formal harness: {harness_path}")
    sby_path = generated_dir / f"{module_name}.sby"
    if not sby_path.is_file():
        raise ValueError(f"Missing generated SymbiYosys file: {sby_path}")

    provenance_path = generated_dir / "provenance.json"
    if not provenance_path.is_file():
        raise ValueError(f"Missing generated provenance manifest: {provenance_path}")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid provenance manifest JSON: {provenance_path}: {error}") from error

    if provenance.get("module") != module:
        raise ValueError(f"Provenance manifest module mismatch: {provenance_path}")
    if provenance.get("target") != str(VerificationTarget.FORMAL):
        raise ValueError(f"Provenance manifest target mismatch: {provenance_path}")

    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError(f"Provenance manifest has no artifacts: {provenance_path}")
    for expected_name in (harness_path.name, sby_path.name):
        if not any(_manifest_artifact_has_provenance(item, expected_name) for item in artifacts):
            raise ValueError(f"Provenance manifest lacks refs for {expected_name}: {provenance_path}")


def _artifact_directory(config: CLIConfig, artifact: GeneratedArtifact) -> Path:
    if artifact.target == VerificationTarget.FORMAL:
        return config.output_dir / "formal" / "modules" / artifact.source_plan_module
    return config.output_dir / "simulation" / str(artifact.target) / "modules" / artifact.source_plan_module


def _write_provenance_manifest(
    config: CLIConfig,
    target: VerificationTarget,
    module: str,
    artifacts: tuple[GeneratedArtifact, ...],
) -> Path:
    directory = _artifact_directory(config, artifacts[0])
    path = directory / "provenance.json"
    payload = {
        "module": module,
        "target": str(target),
        "artifacts": [
            {
                "path": str(artifact.path),
                "kind": str(artifact.kind),
                "source_plan_module": artifact.source_plan_module,
                "provenance_refs": [
                    {
                        "kind": str(ref.kind),
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in artifact.provenance_refs
                ],
            }
            for artifact in artifacts
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _safe_artifact_path(directory: Path, relative_path: Path) -> Path:
    _validate_relative_artifact_path(relative_path)
    path = directory / relative_path
    resolved_directory = directory.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if resolved_path != resolved_directory and resolved_directory not in resolved_path.parents:
        raise ValueError(f"Generated artifact path escapes output directory: {relative_path}")
    return path


def _validate_relative_artifact_path(path: Path) -> None:
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Generated artifact path must be relative and stay inside its module directory: {path}")


def _parse_python(content: str, path: Path) -> None:
    try:
        ast.parse(content, filename=str(path))
    except SyntaxError as error:
        raise ValueError(f"Generated Python artifact has invalid syntax: {path}: {error.msg}") from error


def _manifest_artifact_has_provenance(item: object, expected_name: str) -> bool:
    if not isinstance(item, dict):
        return False
    provenance_refs = item.get("provenance_refs")
    return item.get("path") == expected_name and isinstance(provenance_refs, list) and bool(provenance_refs)


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
