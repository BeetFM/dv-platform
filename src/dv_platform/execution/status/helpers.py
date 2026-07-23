# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path


def _schema_status(stored: int, current: int, minimum: int) -> str:
    if stored > current:
        return "future"
    if stored < minimum:
        return "unsupported"
    if stored < current:
        return "legacy"
    return "current"


def _command_available(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    executable = parts[0]
    if Path(executable).is_absolute() or "/" in executable:
        return Path(executable).exists()
    return shutil.which(executable) is not None
