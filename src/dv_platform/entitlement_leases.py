"""Cross-process concurrency enforcement for entitlement-sensitive operations."""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dv_platform.product import CapabilityDeniedError, ResolvedProductPlan, require_operation


@dataclass
class CapabilityLease:
    path: Path

    def release(self) -> None:
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> CapabilityLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


def acquire_capability_lease(
    plan: ResolvedProductPlan,
    work_dir: Path,
    operation_id: str,
) -> CapabilityLease:
    """Atomically enforce the entitlement concurrency bound after authorization."""

    require_operation(plan, operation_id)
    root = work_dir / "entitlement" / "leases"
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _prune_stale(root)
        active = tuple(root.glob("*.json"))
        if len(active) >= plan.concurrency_limit:
            raise CapabilityDeniedError(
                operation_id,
                f"entitlement concurrency limit {plan.concurrency_limit} is exhausted",
            )
        path = root / f"{uuid.uuid4().hex}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pid": os.getpid(),
                    "operation": operation_id,
                    "created_at": datetime.now(UTC).isoformat(),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
    return CapabilityLease(path)


def _prune_stale(root: Path) -> None:
    for path in root.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            pid = int(value["pid"])
            os.kill(pid, 0)
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
