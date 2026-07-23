"""Small filesystem primitives for durable generated state."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text through a sibling temporary file and atomically replace the target."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: Any, encoding: str = "utf-8") -> None:
    """Atomically write the platform's canonical human-readable JSON form."""

    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n", encoding=encoding)


def backup_sqlite_database(source: Path, destination: Path) -> None:
    """Create and integrity-check a SQLite backup without replacing an existing file."""

    if not source.is_file() or source.is_symlink():
        raise ValueError(f"SQLite source must be a regular file: {source}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"SQLite backup destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as destination_db:
            source_db.backup(destination_db)
            result = destination_db.execute("PRAGMA integrity_check").fetchone()
            if result != ("ok",):
                raise ValueError(f"SQLite backup failed integrity_check: {result}")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def sqlite_integrity_check(path: Path) -> None:
    """Fail unless *path* is a regular, internally consistent SQLite database."""

    if not path.is_file() or path.is_symlink():
        raise ValueError(f"SQLite database must be a regular file: {path}")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as database:
        result = database.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise ValueError(f"SQLite integrity_check failed for {path}: {result}")


def restore_sqlite_database(source: Path, destination: Path) -> None:
    """Restore a verified backup without overwriting existing state."""

    sqlite_integrity_check(source)
    backup_sqlite_database(source, destination)
