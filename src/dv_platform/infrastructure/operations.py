"""Governed backup and adjacent-schema migration operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dv_platform.domain.models import CLIConfig
from dv_platform.domain.schema import PLAN_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.infrastructure.io import atomic_write_json, backup_sqlite_database, sqlite_integrity_check

DESTRUCTION_CLASSES = {"run-evidence", "counterexamples", "generated-collateral", "backups"}


@dataclass(frozen=True)
class OperationItem:
    source: Path
    destination: Path | None
    action: str
    sha256: str
    size: int


def backup_project_state(config: CLIConfig, destination: Path, *, apply: bool = False) -> tuple[OperationItem, ...]:
    """Plan or create a content-addressed backup of durable platform state."""

    destination = destination.expanduser().resolve(strict=False)
    work = config.work_dir.resolve(strict=False)
    if destination == work or work in destination.parents:
        raise ValueError("backup destination must be outside the work directory")
    if destination.exists():
        raise FileExistsError(f"backup destination already exists: {destination}")
    sources = (
        tuple(
            path
            for path in sorted(work.rglob("*"))
            if path.is_file()
            and not path.is_symlink()
            and (
                path.suffix in {".sqlite", ".json", ".jsonl"}
                or path.name in {"project-manifest.json", "qualification-policy.json"}
            )
        )
        if work.is_dir()
        else ()
    )
    items = tuple(
        OperationItem(path, destination / path.relative_to(work), "backup", _sha256(path), path.stat().st_size)
        for path in sources
    )
    if not apply:
        return items
    destination.mkdir(parents=True)
    try:
        for item in items:
            assert item.destination is not None
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            if item.source.suffix == ".sqlite":
                backup_sqlite_database(item.source, item.destination)
            else:
                item.destination.write_bytes(item.source.read_bytes())
            if _sha256(item.destination) != item.sha256:
                raise ValueError(f"backup digest mismatch: {item.source}")
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "repo_root": str(config.repo_root),
            "items": [
                {
                    "path": str(item.source.relative_to(work)),
                    "sha256": item.sha256,
                    "size": item.size,
                }
                for item in items
            ],
        }
        atomic_write_json(destination / "backup-manifest.json", manifest)
        verify_project_backup(destination)
    except Exception:
        # Preserve partial state for forensic inspection; it is never considered
        # valid without the final verified manifest.
        raise
    return items


def verify_project_backup(directory: Path) -> dict[str, Any]:
    manifest_path = directory / "backup-manifest.json"
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("items"), list):
        raise ValueError("invalid backup manifest")
    for raw in value["items"]:
        if not isinstance(raw, dict):
            raise ValueError("invalid backup manifest item")
        relative = Path(str(raw["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("backup manifest path escapes backup root")
        path = directory / relative
        if not path.is_file() or path.is_symlink() or _sha256(path) != raw.get("sha256"):
            raise ValueError(f"backup item failed verification: {relative}")
        if path.suffix == ".sqlite":
            sqlite_integrity_check(path)
    return value


def plan_state_migration(config: CLIConfig) -> tuple[OperationItem, ...]:
    """Find readable JSON state that would be advanced to current schemas."""

    items: list[OperationItem] = []
    for path in sorted(config.work_dir.rglob("*.json")) if config.work_dir.is_dir() else ():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict) or not isinstance(value.get("schema_version"), int):
            continue
        current = _current_schema_for(path, value)
        if current is not None and value["schema_version"] < current:
            items.append(
                OperationItem(
                    path, None, f"schema {value['schema_version']} -> {current}", _sha256(path), path.stat().st_size
                )
            )
    return tuple(items)


def migrate_project_state(config: CLIConfig, *, backup: Path, apply: bool = False) -> tuple[OperationItem, ...]:
    """Dry-run or apply safe adjacent migrations after a verified backup."""

    items = plan_state_migration(config)
    if not apply:
        return items
    verify_project_backup(backup)
    for item in items:
        value = json.loads(item.source.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        current = _current_schema_for(item.source, value)
        assert current is not None
        if current - int(value["schema_version"]) > 1:
            raise ValueError(f"migration must proceed one adjacent schema at a time: {item.source}")
        value["schema_version"] = current
        atomic_write_json(item.source, value)
    return items


def governed_destruction(
    config: CLIConfig,
    *,
    retention_class: str,
    target: Path,
    authorization: str,
    legal_holds: Path,
    recovery_backup: Path,
    apply: bool = False,
) -> tuple[OperationItem, ...]:
    """Plan or remove one governed evidence tree after hold and backup checks."""

    if retention_class not in DESTRUCTION_CLASSES:
        raise ValueError(f"unsupported destruction retention class: {retention_class}")
    if not authorization.strip() or len(authorization) > 256:
        raise ValueError("destruction requires a bounded non-empty authorization reference")
    target = target.expanduser().resolve(strict=True)
    expected_roots = {
        "run-evidence": config.work_dir / "runs",
        "counterexamples": config.work_dir / "formal" / "counterexamples",
        "generated-collateral": config.output_dir,
    }
    if retention_class in expected_roots and target != expected_roots[retention_class].resolve(strict=False):
        raise ValueError(f"destruction target does not match the configured {retention_class} root")
    if retention_class == "backups":
        verify_project_backup(target)
    if target.is_symlink() or not target.is_dir():
        raise ValueError("destruction target must be a real directory")
    verify_project_backup(recovery_backup.expanduser().resolve(strict=True))
    holds = _legal_holds(legal_holds.expanduser().resolve(strict=True))
    if any(
        hold.get("active") is True
        and hold.get("retention_class") in {retention_class, "*"}
        and hold.get("target") in {str(target), "*"}
        for hold in holds
    ):
        raise ValueError(f"active legal hold blocks destruction of {retention_class}: {target}")
    files = tuple(path for path in sorted(target.rglob("*")) if path.is_file() and not path.is_symlink())
    unsafe = tuple(path for path in target.rglob("*") if path.is_symlink())
    if unsafe:
        raise ValueError(f"destruction refuses symbolic links: {unsafe[0]}")
    items = tuple(
        OperationItem(path, None, f"destroy:{retention_class}", _sha256(path), path.stat().st_size) for path in files
    )
    if apply:
        for item in items:
            item.source.unlink()
        for directory in sorted((path for path in target.rglob("*") if path.is_dir()), reverse=True):
            directory.rmdir()
        target.rmdir()
    return items


def _legal_holds(path: Path) -> tuple[dict[str, Any], ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("holds"), list):
        raise ValueError("invalid legal-hold registry")
    holds = tuple(item for item in value["holds"] if isinstance(item, dict))
    if len(holds) != len(value["holds"]):
        raise ValueError("invalid legal-hold record")
    return holds


def _current_schema_for(path: Path, value: dict[str, Any]) -> int | None:
    if "modules" in value and "tool" in value:
        return RTL_FACTS_SCHEMA_VERSION
    if "module" in value and "targets" in value:
        return PLAN_SCHEMA_VERSION
    if path.name == "coverage-summary.json":
        return 3
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


for _value in tuple(globals().values()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.core.operations"
del _value
