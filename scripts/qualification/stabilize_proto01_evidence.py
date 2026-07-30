#!/usr/bin/env python3
"""Create or verify the deterministic PROTO-01 evidence-retention manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv_platform.infrastructure.io import atomic_write_text  # noqa: E402
from dv_platform.qualification import capability_ledger_status  # noqa: E402
from dv_platform.qualification.evidence import validate_evidence_record  # noqa: E402

EVIDENCE_ROOT = ROOT / "qualification" / "evidence" / "PROTO-01"
MANIFEST_PATH = EVIDENCE_ROOT / "artifact-retention-manifest-v1.json"
TARGETS = {"cocotb", "formal", "systemverilog", "verilog", "vhdl"}
ARTIFACT_ROOTS = (
    EVIDENCE_ROOT / "axis-combined" / "artifacts",
    EVIDENCE_ROOT / "broad-combined" / "artifacts",
)
SUPPORTING_FILES = (
    EVIDENCE_ROOT / "axi4-stream-1.0" / "source-identity.txt",
    EVIDENCE_ROOT / "axi4-stream-1.0" / "tool-versions.json",
    EVIDENCE_ROOT / "axi4-stream-1.0" / "unittest.log",
    EVIDENCE_ROOT / "broad-open-source-identity.txt",
    EVIDENCE_ROOT / "broad-open-unittest.log",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _retained_file(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"retained evidence file is missing or symbolic: {path}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
    }


def _artifact_set(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"retained artifact root is missing or symbolic: {path}")
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if any(item.is_symlink() for item in files):
        raise ValueError(f"retained artifact root contains a symbolic link: {path}")
    digest = hashlib.sha256()
    total_bytes = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        size = item.stat().st_size
        item_digest = _sha256(item)
        total_bytes += size
        digest.update(f"{relative}\0{size}\0{item_digest}\n".encode())
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "sha256": digest.hexdigest(),
    }


def build_manifest(*, require_artifacts: bool = True) -> dict[str, object]:
    """Build a closed snapshot of the 35 records and retained raw tool artifacts."""

    records: list[dict[str, object]] = []
    identities: set[tuple[str, str, str]] = set()
    for path in sorted(EVIDENCE_ROOT.glob("*/*-evidence-v1.json")):
        raw = path.read_bytes()
        record: dict[str, Any] = json.loads(raw)
        errors = validate_evidence_record(record)
        if errors:
            raise ValueError(f"{path}: {'; '.join(errors)}")
        identity = (str(record["profile_id"]), str(record["role"]), str(record["target"]))
        if identity[2] not in TARGETS:
            continue
        if identity in identities:
            raise ValueError(f"duplicate PROTO-01 evidence identity: {identity!r}")
        identities.add(identity)
        records.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "profile_id": identity[0],
                "role": identity[1],
                "target": identity[2],
            }
        )
    if len(records) != 35:
        raise ValueError(f"expected 35 PROTO-01 open-tool evidence records, found {len(records)}")
    status = capability_ledger_status(ROOT)
    if status["status"] != "valid" or status["counts"].get("supported") != 35:
        raise ValueError(f"PROTO-01 capability ledger is not stable: {status}")
    artifact_sets = [_artifact_set(path) for path in ARTIFACT_ROOTS if path.is_dir() or require_artifacts]
    return {
        "schema_version": 1,
        "ticket": "PROTO-01",
        "record_count": len(records),
        "records": records,
        "artifact_sets": artifact_sets,
        "supporting_files": [_retained_file(path) for path in SUPPORTING_FILES if path.is_file()],
    }


def _render(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def verify_manifest(*, require_artifacts: bool) -> None:
    """Verify distributable records and, when retained, the raw artifact trees."""

    if not MANIFEST_PATH.is_file():
        raise ValueError("PROTO-01 artifact-retention manifest is missing")
    retained = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    current = build_manifest(require_artifacts=require_artifacts)
    fields = (
        ("schema_version", "ticket", "record_count", "records", "artifact_sets", "supporting_files")
        if require_artifacts
        else ("schema_version", "ticket", "record_count", "records")
    )
    if any(retained.get(field) != current.get(field) for field in fields):
        raise ValueError("PROTO-01 artifact-retention manifest is stale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify the retained manifest without rewriting it")
    parser.add_argument(
        "--allow-missing-artifacts",
        action="store_true",
        help="verify packaged records when raw local tool artifacts are not present",
    )
    args = parser.parse_args()
    if args.check:
        verify_manifest(require_artifacts=not args.allow_missing_artifacts)
        print("PROTO-01 evidence-retention manifest is stable")
        return 0
    value = build_manifest(require_artifacts=not args.allow_missing_artifacts)
    rendered = _render(value)
    atomic_write_text(MANIFEST_PATH, rendered)
    print("retained deterministic PROTO-01 evidence manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
