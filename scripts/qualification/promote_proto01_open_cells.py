#!/usr/bin/env python3
"""Promote exactly the digest-bound PROTO-01 open-tool evidence cells."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv_platform.infrastructure.io import atomic_write_text  # noqa: E402
from dv_platform.qualification import render_capability_table  # noqa: E402
from dv_platform.qualification.evidence import validate_evidence_record  # noqa: E402

LEDGER_PATH = ROOT / "qualification" / "policies" / "capability-ledger-v1.json"
EVIDENCE_ROOT = ROOT / "qualification" / "evidence" / "PROTO-01"
DOC_PATH = ROOT / "docs" / "verification.md"
TARGETS = {"cocotb", "formal", "systemverilog", "verilog", "vhdl"}


def _records() -> dict[tuple[str, str, str], tuple[dict[str, Any], Path, str]]:
    records: dict[tuple[str, str, str], tuple[dict[str, Any], Path, str]] = {}
    for path in sorted(EVIDENCE_ROOT.glob("*/*-evidence-v1.json")):
        raw = path.read_bytes()
        record = json.loads(raw)
        errors = validate_evidence_record(record)
        if errors:
            raise ValueError(f"{path}: {'; '.join(errors)}")
        identity = (str(record["profile_id"]), str(record["role"]), str(record["target"]))
        if identity[2] not in TARGETS or record["execution_kind"] != "real":
            continue
        if record["strict_status"] != "passed" or record["coverage"]["missing_ids"]:
            raise ValueError(f"{path}: evidence is non-closing")
        if any(not item["killed"] for item in record["mutant_outcomes"]):
            raise ValueError(f"{path}: evidence has a surviving mutant")
        if identity in records:
            raise ValueError(f"duplicate evidence identity: {identity!r}")
        records[identity] = (record, path, hashlib.sha256(raw).hexdigest())
    if len(records) != 35:
        raise ValueError(f"expected 35 open-tool records, found {len(records)}")
    return records


def _source_identity(record: dict[str, Any]) -> str:
    payload = record["source_sha256"] + record["configuration_sha256"] + record["profile_sha256"]
    return hashlib.sha256(payload.encode()).hexdigest()


def _render_ledger(value: dict[str, Any]) -> str:
    lines = ["{", '  "schema_version": 1,', '  "authority": "current",', '  "cells": [']
    cells = value["cells"]
    previous: tuple[str, str] | None = None
    for index, cell in enumerate(cells):
        group = (str(cell["profile_id"]), str(cell["role"]))
        if previous is not None and group != previous:
            lines.append("")
        suffix = "," if index + 1 < len(cells) else ""
        lines.append("    " + json.dumps(cell, separators=(",", ":")) + suffix)
        previous = group
    lines.extend(("  ]", "}", ""))
    return "\n".join(lines)


def _update_document(ledger: dict[str, Any]) -> None:
    document = DOC_PATH.read_text(encoding="utf-8")
    start_marker = "<!-- generated: capability-ledger-v1 -->"
    end_marker = "<!-- /generated: capability-ledger-v1 -->"
    start = document.index(start_marker) + len(start_marker)
    end = document.index(end_marker, start)
    table = "\n" + render_capability_table(ledger) + end_marker
    atomic_write_text(DOC_PATH, document[:start] + table + document[end + len(end_marker) :])


def main() -> int:
    records = _records()
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    seen: set[tuple[str, str, str]] = set()
    for cell in ledger["cells"]:
        identity = (str(cell["profile_id"]), str(cell["role"]), str(cell["target"]))
        item = records.get(identity)
        if item is None:
            continue
        record, path, digest = item
        cell["state"] = "supported"
        cell["evidence_digest"] = digest
        cell["evidence_path"] = path.relative_to(ROOT).as_posix()
        cell["last_passing_source"] = _source_identity(record)
        seen.add(identity)
    if seen != set(records):
        raise ValueError(f"ledger lacks evidence cells: {sorted(set(records) - seen)!r}")
    atomic_write_text(LEDGER_PATH, _render_ledger(ledger))
    _update_document(ledger)
    print("promoted 35 PROTO-01 open-tool cells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
