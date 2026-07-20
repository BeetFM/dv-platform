"""Local audit logging and configured secret redaction."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dv_platform.core.models import CLIConfig


def redact_text(config: CLIConfig, text: str) -> str:
    """Replace configured sensitive patterns before text reaches persistent logs."""

    redacted = text
    for pattern in config.redact_patterns:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted


def redact_value(config: CLIConfig, value: object) -> object:
    """Recursively redact strings in JSON-compatible command and result records."""

    if isinstance(value, str):
        return redact_text(config, value)
    if isinstance(value, list):
        return [redact_value(config, item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(config, item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_value(config, item) for key, item in value.items()}
    return value


def append_audit_event(config: CLIConfig, action: str, details: dict[str, Any]) -> Path | None:
    """Append one redacted local audit event with owner-only permissions."""

    if not config.audit_enabled:
        return None
    path = config.work_dir / "audit" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "details": redact_value(config, details),
    }
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def audit_file_mode(path: Path) -> int | None:
    """Return permission bits for an audit file when present."""

    try:
        return path.stat().st_mode & 0o777
    except OSError:
        return None
