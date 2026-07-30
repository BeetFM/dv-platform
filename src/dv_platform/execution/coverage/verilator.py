"""Bounded importer for Verilator 5.020 ``coverage.dat`` files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

FORMAT_VERSION = "verilator-coverage-dat-5.020-v1"
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_LINES = 2_000_000
MAX_LINE_BYTES = 64 * 1024
MAX_COUNTER = (1 << 64) - 1
_RECORD = re.compile(r"^C '(.*)' ([0-9]+)$")


class VerilatorCoverageImportError(ValueError):
    """Raised when a coverage.dat file cannot be normalized unambiguously."""


class VerilatorCoverageDatImporter:
    """Import Verilator 5.020 counters as canonical closure points."""

    kind = "coverage_importer"
    api_version = 1

    def supports(self, path: Path) -> bool:
        return path.name.lower() == "coverage.dat" or path.name.lower().endswith(".coverage.dat")

    def import_coverage(self, path: Path) -> dict[str, Any]:
        if path.is_symlink():
            raise VerilatorCoverageImportError(f"coverage.dat input must not be a symbolic link: {path}")
        raw = path.read_bytes()
        if len(raw) > MAX_INPUT_BYTES:
            raise VerilatorCoverageImportError(f"coverage.dat exceeds {MAX_INPUT_BYTES} byte safety limit: {path}")
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise VerilatorCoverageImportError(f"coverage.dat is not UTF-8: {path}") from exc
        if len(lines) > MAX_LINES:
            raise VerilatorCoverageImportError(f"coverage.dat exceeds {MAX_LINES} line safety limit: {path}")

        digest = hashlib.sha256(raw).hexdigest()
        merged: dict[str, dict[str, Any]] = {}
        for line_number, line in enumerate(lines, 1):
            if not line or line.startswith("#"):
                continue
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                raise VerilatorCoverageImportError(f"coverage.dat line {line_number} exceeds {MAX_LINE_BYTES} bytes")
            point = _parse_record(line, line_number, path, digest)
            existing = merged.get(str(point["point_id"]))
            if existing is None:
                merged[str(point["point_id"])] = point
            else:
                _merge_duplicate(existing, point)
        if not merged:
            raise VerilatorCoverageImportError(f"coverage.dat contains no counters: {path}")
        return {
            "schema_version": 3,
            "source_format": FORMAT_VERSION,
            "source_sha256": digest,
            "coverage_points": [merged[key] for key in sorted(merged)],
            "formal_points": [],
        }


def _parse_record(line: str, line_number: int, path: Path, source_sha256: str) -> dict[str, Any]:
    match = _RECORD.fullmatch(line)
    if match is None:
        raise VerilatorCoverageImportError(f"invalid coverage.dat record at {path}:{line_number}")
    metadata = _metadata(match.group(1), line_number)
    count = int(match.group(2))
    overflow = count > MAX_COUNTER
    hits = min(count, MAX_COUNTER)
    source = metadata.get("f") or metadata.get("filename")
    source_line = metadata.get("l") or metadata.get("line")
    if not source or not source_line or not source_line.isdigit():
        raise VerilatorCoverageImportError(
            f"coverage.dat record {line_number} lacks a source filename and numeric line"
        )
    hierarchy = metadata.get("h") or metadata.get("hier") or metadata.get("hierarchy") or "<unknown>"
    specialization = metadata.get("s") or metadata.get("specialization") or "<unknown>"
    point_kind = _normalize(metadata.get("t") or metadata.get("type") or "unknown")
    name = _normalize(metadata.get("o") or metadata.get("name") or metadata.get("comment") or point_kind)
    locator = f"{source}:{source_line}"
    identity = "\0".join((FORMAT_VERSION, locator, hierarchy, specialization, point_kind, name))
    point_id = "verilator:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    excluded = _truthy(metadata.get("x") or metadata.get("excluded"))
    module = hierarchy.split(".", 1)[0] if hierarchy != "<unknown>" else Path(source).stem
    return {
        "point_id": point_id,
        "module": module,
        "name": name,
        "kind": point_kind,
        "hits": hits,
        "status": "excluded" if excluded else ("covered" if hits else "uncovered"),
        "vendor_provenance": {
            "format": FORMAT_VERSION,
            "source_sha256": source_sha256,
            "source_locator": locator,
            "hierarchy": hierarchy,
            "specialization": specialization,
            "counter_overflow": str(overflow).lower(),
            "record_lines": str(line_number),
        },
    }


def _metadata(encoded: str, line_number: int) -> dict[str, str]:
    if "\x01" not in encoded:
        raise VerilatorCoverageImportError(f"coverage.dat record {line_number} lacks tagged metadata")
    result: dict[str, str] = {}
    for segment in encoded.split("\x01"):
        if not segment:
            continue
        if "\x02" not in segment:
            raise VerilatorCoverageImportError(f"coverage.dat record {line_number} has malformed tagged metadata")
        key, value = segment.split("\x02", 1)
        if not key or key in result:
            raise VerilatorCoverageImportError(
                f"coverage.dat record {line_number} has empty or duplicate metadata keys"
            )
        result[key.strip().lower()] = value.strip()
    return result


def _merge_duplicate(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    total = int(existing["hits"]) + int(incoming["hits"])
    overflow = total > MAX_COUNTER
    existing["hits"] = min(total, MAX_COUNTER)
    existing["status"] = (
        "excluded"
        if existing["status"] == "excluded" or incoming["status"] == "excluded"
        else ("covered" if total else "uncovered")
    )
    provenance = existing["vendor_provenance"]
    incoming_provenance = incoming["vendor_provenance"]
    provenance["counter_overflow"] = str(
        overflow or provenance["counter_overflow"] == "true" or incoming_provenance["counter_overflow"] == "true"
    ).lower()
    provenance["record_lines"] += "," + incoming_provenance["record_lines"]


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split()) or "unknown"


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "excluded"}
