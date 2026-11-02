"""Write the active physical-design configuration without credentials."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dv_platform.configuration.loading import normalize_config
from dv_platform.domain.models import CLIConfig
from dv_platform.infrastructure.io import atomic_write_text


def write_config(config: CLIConfig, path: Path) -> None:
    config = normalize_config(config)
    tables: dict[str, dict[str, Any]] = {
        "paths": {key: getattr(config, key) for key in ("repo_root", "work_dir", "output_dir")},
        "policy": {key: getattr(config, key) for key in ("allow_network", "strict", "ci")},
        "security": {
            key: getattr(config, key)
            for key in (
                "audit_enabled",
                "redact_patterns",
                "approved_plugin_publishers",
                "export_roots",
                "secret_provider",
                "retention_days",
            )
        },
        "product": asdict(config.product),
        "ai": asdict(config.ai),
        "context_optimization": asdict(config.context_optimization),
    }
    lines: list[str] = []
    for section, values in tables.items():
        lines.append(f"[{section}]")
        lines.extend(f"{key} = {_toml(value)}" for key, value in values.items() if value is not None)
        lines.append("")
    for plugin in config.adapter_plugins:
        lines.append("[[adapter_plugins]]")
        lines.extend(f"{key} = {_toml(value)}" for key, value in asdict(plugin).items() if value is not None)
        lines.append("")
    atomic_write_text(path, "\n".join(lines))


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)
