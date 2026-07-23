"""Local audit logging and configured secret redaction."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol

from dv_platform.domain.models import CLIConfig
from dv_platform.infrastructure.io import atomic_write_text


class SecretProvider(Protocol):
    """Resolve a named secret without placing its value in project configuration."""

    def get(self, name: str) -> str | None: ...


class EnvironmentSecretProvider:
    """Default secret provider backed by the process environment."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = os.environ if environment is None else environment

    def get(self, name: str) -> str | None:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError(f"Invalid secret name: {name!r}")
        return self._environment.get(name)


def resolve_secret(config: CLIConfig, name: str) -> str | None:
    """Resolve a secret through the configured provider."""

    if config.secret_provider != "environment":
        raise ValueError(f"Unsupported secret provider: {config.secret_provider}")
    return EnvironmentSecretProvider().get(name)


def validate_export_destination(config: CLIConfig, destination: Path) -> Path:
    """Return an allowed export destination or fail closed on path/symlink escapes."""

    resolved = destination.expanduser().resolve(strict=False)
    roots = config.export_roots or (config.work_dir, config.output_dir)
    allowed = any(
        resolved == root.resolve(strict=False) or resolved.is_relative_to(root.resolve(strict=False)) for root in roots
    )
    if not allowed:
        raise ValueError(f"Export destination is outside configured security.export_roots: {resolved}")
    current = resolved
    while current != current.parent:
        if current.exists() and current.is_symlink():
            raise ValueError(f"Export destination traverses a symbolic link: {current}")
        if any(current == root.resolve(strict=False) for root in roots):
            break
        current = current.parent
    return resolved


def write_support_bundle(config: CLIConfig, status: Mapping[str, object]) -> Path:
    """Write redacted, content-free diagnostics suitable for a support ticket."""

    logs: list[dict[str, object]] = []
    if config.work_dir.is_dir():
        for index, path in enumerate(sorted(config.work_dir.rglob("*.log")), start=1):
            if path.is_symlink() or not path.is_file():
                continue
            content = path.read_bytes()
            logs.append(
                {
                    "id": f"log-{index:04d}",
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    try:
        package_version = metadata.version("dv-platform")
    except metadata.PackageNotFoundError:
        package_version = "unknown"
    payload = {
        "schema_version": 1,
        "product": "Veriforge",
        "package": {"name": "dv-platform", "version": package_version},
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": sys.platform,
        },
        "configuration_shape": {
            "documentation_paths": len(config.documentation_paths),
            "register_map_paths": len(config.register_map_paths),
            "rtl_filelists": len(config.rtl_filelists),
            "include_paths": len(config.include_paths),
            "top_modules": len(config.top_modules),
            "simulators": len(config.simulators),
            "formal_tools": len(config.formal_tools),
            "adapter_plugins": len(config.adapter_plugins),
            "allow_network": config.allow_network,
            "strict": config.strict,
            "ci": config.ci,
            "secret_provider": config.secret_provider,
            "retention_days": config.retention_days,
        },
        "status": {key: status[key] for key in ("schemas", "summary") if key in status},
        "log_digests": logs,
    }
    destination = validate_export_destination(config, config.work_dir / "support" / "bundle.json")
    atomic_write_text(destination, json.dumps(redact_value(config, payload), indent=2, sort_keys=True) + "\n")
    return destination


def purge_retained_files(config: CLIConfig, *, as_of: date, apply: bool = False) -> tuple[Path, ...]:
    """List or unlink expired transient files under a fixed work-directory allowlist."""

    work_root = config.work_dir.resolve(strict=False)
    cutoff = datetime.combine(as_of, time.min, tzinfo=UTC) - timedelta(days=config.retention_days)
    allowed = (
        work_root / "ai" / "cache",
        work_root / "ai" / "runs",
        work_root / "audit",
        work_root / "logs",
        work_root / "rag-index",
        work_root / "support",
    )
    expired: list[Path] = []
    for root in allowed:
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir() or not root.resolve(strict=False).is_relative_to(work_root):
            raise ValueError(f"Unsafe retention root: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Retention purge refuses symbolic links: {path}")
            if not path.is_file():
                continue
            modified = datetime.fromtimestamp(path.stat(follow_symlinks=False).st_mtime, tz=UTC)
            if modified < cutoff:
                expired.append(path)
    if apply:
        for path in expired:
            path.unlink()
    return tuple(expired)


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


for _value in tuple(globals().values()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.core.security"
del _value
