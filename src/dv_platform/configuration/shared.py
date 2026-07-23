from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CONFIG_FILENAME = "dv-platform.toml"


@dataclass(frozen=True)
class ConfigDiagnostic:
    """A validation message for local project configuration."""

    severity: str
    message: str


ConfigDiagnostic.__module__ = "dv_platform.core.config"
