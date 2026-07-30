# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dv_platform.core.models import CLIConfig

if TYPE_CHECKING:
    pass


def _parameter_sweep_configs(config: CLIConfig) -> tuple[tuple[CLIConfig, tuple[str, ...] | None], ...]:
    """Return isolated analysis configs for the selected elaboration points."""

    if not config.parameter_sweeps:
        return ((config, None),)
    return tuple(
        (
            replace(
                config,
                work_dir=config.work_dir / "sweeps" / _sweep_identity(overrides),
                parameter_overrides=overrides,
                parameter_sweeps=(),
            ),
            overrides,
        )
        for overrides in config.parameter_sweeps
    )


def _sweep_identity(overrides: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\0".join(overrides).encode("utf-8")).hexdigest()[:12]
    return f"sweep_{digest}"


def _rtl_input_fingerprint(manifest_path: Path, inventory: Any, config: CLIConfig | None = None) -> str:
    manifest_bytes = manifest_path.read_bytes()
    digest = hashlib.sha256(manifest_bytes)
    inputs = {hdl.path for hdl in inventory.hdl_files}
    try:
        manifest = json.loads(manifest_bytes)
        inputs.update(
            path
            for item in manifest.get("verilator_command", ())
            if isinstance(item, str) and (path := Path(item).expanduser().resolve(strict=False)).is_file()
        )
    except (json.JSONDecodeError, AttributeError):
        pass
    for include_path in inventory.include_paths:
        if include_path.is_dir():
            inputs.update(
                path
                for path in include_path.rglob("*")
                if path.is_file() and path.suffix.lower() in {".v", ".vh", ".sv", ".svh"}
            )
    for path in sorted(inputs, key=lambda item: item.as_posix()):
        digest.update(str(path).encode("utf-8"))
        digest.update(path.read_bytes())
    if config is not None:
        policies = [
            {
                "kind": policy.kind,
                "module": policy.module,
                "subject": policy.subject,
                "parameters": list(policy.parameters),
            }
            for policy in config.depth_policies
        ]
        digest.update(json.dumps(policies, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        for policy in config.depth_policies:
            if policy.kind != "memory" or policy.parameter("profile") != "bounded_sram_init_hex":
                continue
            relative = policy.parameter("path")
            if relative:
                init_path = config.repo_root / relative
                if init_path.is_file() and not init_path.is_symlink():
                    digest.update(relative.encode("utf-8"))
                    digest.update(init_path.read_bytes())
    return digest.hexdigest()


def _rtl_cache_matches(config: CLIConfig, cache_path: Path, fingerprint: str) -> bool:
    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    if not cache_path.is_file() or not facts_path.is_file() or not summary_path.is_file():
        return False
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if config.semantic_crosscheck != "off" and not (config.work_dir / "semantic-crosscheck" / "result.json").is_file():
        frontends = payload.get("normalization_frontends", ()) if isinstance(payload, dict) else ()
        if not isinstance(frontends, list) or not any(
            isinstance(item, str) and item.startswith("vhdl-source-normalizer/") for item in frontends
        ):
            return False
    return isinstance(payload, dict) and payload.get("input_fingerprint") == fingerprint


def _semantic_crosscheck_enforced(config: CLIConfig) -> bool:
    return config.semantic_crosscheck == "required" or (
        config.semantic_crosscheck == "report" and (config.strict or config.ci)
    )


def _read_crosscheck_payload(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _semantic_crosscheck_gate(args: argparse.Namespace, config: CLIConfig, command: str) -> bool:
    if not _semantic_crosscheck_enforced(config):
        return True
    path = config.work_dir / "semantic-crosscheck" / "result.json"
    payload = _read_crosscheck_payload(path)
    if payload.get("schema_version") in {2, 3} and payload.get("status") == "passed" and payload.get("passed") is True:
        return True
    _emit_error(
        args,
        command,
        "semantic_crosscheck_gate_failed",
        "Generation trust policy requires a passing Slang cross-check; run analyze-rtl successfully first.",
        data={
            "semantic_crosscheck_mode": config.semantic_crosscheck,
            "semantic_crosscheck_status": payload.get("status", "missing"),
            "semantic_crosscheck": str(path),
        },
    )
    return False
