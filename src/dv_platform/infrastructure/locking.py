"""Small cross-process directory lock with bounded stale-lock recovery."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


class DirectoryLock:
    """Own a lock directory exclusively for a bounded interval."""

    def __init__(self, path: Path, *, timeout_seconds: float = 10.0, stale_seconds: float = 300.0) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self._owned = False

    def __enter__(self) -> DirectoryLock:
        deadline = time.monotonic() + self.timeout_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.path.mkdir(mode=0o700)
                owner = self.path / "owner.json"
                owner.write_text(
                    json.dumps({"pid": os.getpid(), "created_ns": time.time_ns()}, sort_keys=True),
                    encoding="utf-8",
                )
                owner.chmod(0o600)
                self._owned = True
                return self
            except FileExistsError:
                if self._stale():
                    self._recover_stale()
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out acquiring lock: {self.path}") from None
                time.sleep(0.01)

    def __exit__(self, *_args: object) -> None:
        if not self._owned:
            return
        (self.path / "owner.json").unlink(missing_ok=True)
        try:
            self.path.rmdir()
        except FileNotFoundError:
            pass
        self._owned = False

    def _stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age < self.stale_seconds:
            return False
        try:
            value = json.loads((self.path / "owner.json").read_text(encoding="utf-8"))
            pid = int(value["pid"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def _recover_stale(self) -> None:
        (self.path / "owner.json").unlink(missing_ok=True)
        try:
            self.path.rmdir()
        except (FileNotFoundError, OSError):
            pass
