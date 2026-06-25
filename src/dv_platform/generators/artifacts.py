"""Generated artifact writing and provenance manifests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from dv_platform.core.models import CLIConfig, GeneratedArtifact, VerificationTarget


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
        directory = _artifact_directory(config, artifact)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / artifact.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")
        artifact_paths.append(path)
        manifests.setdefault((artifact.target, artifact.source_plan_module), []).append(artifact)

    provenance_paths = tuple(
        _write_provenance_manifest(config, target, module, tuple(module_artifacts))
        for (target, module), module_artifacts in sorted(manifests.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    )
    return ArtifactWriteResult(artifact_paths=tuple(artifact_paths), provenance_paths=provenance_paths)


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
