"""Strict validation for reusable qualification evidence records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_KEYS = {
    "schema_version",
    "source_sha256",
    "configuration_sha256",
    "profile_sha256",
    "profile_id",
    "profile_version",
    "role",
    "target",
    "tool_versions",
    "commands",
    "expected_checks",
    "mutant_outcomes",
    "coverage",
    "non_vacuity",
    "strict_status",
    "execution_kind",
}


def validate_evidence_record(value: Mapping[str, Any]) -> tuple[str, ...]:  # noqa: C901
    """Return every closed-schema and promotion-safety error in one record."""

    errors: list[str] = []
    unknown = set(value) - EVIDENCE_KEYS
    missing = EVIDENCE_KEYS - set(value)
    if unknown:
        errors.append(f"unknown evidence fields: {', '.join(sorted(unknown))}")
    if missing:
        errors.append(f"missing evidence fields: {', '.join(sorted(missing))}")
    if value.get("schema_version") != 1:
        errors.append("unsupported evidence schema version")
    for field in ("source_sha256", "configuration_sha256", "profile_sha256"):
        if not isinstance(value.get(field), str) or SHA256.fullmatch(str(value.get(field))) is None:
            errors.append(f"{field} must be a lowercase SHA-256 digest")
    for field in ("profile_id", "profile_version", "role"):
        if not isinstance(value.get(field), str) or not str(value.get(field)).strip():
            errors.append(f"{field} must be a non-empty string")
    if value.get("target") not in {"cocotb", "formal", "systemverilog", "verilog", "vhdl", "uvm"}:
        errors.append("target is not recognized")
    tools = value.get("tool_versions")
    if not isinstance(tools, dict) or not tools or any(not str(key) or not str(item) for key, item in tools.items()):
        errors.append("tool_versions must be a non-empty string map")
    for field in ("commands", "expected_checks"):
        items = value.get(field)
        if not isinstance(items, list) or not items or any(not isinstance(item, str) or not item for item in items):
            errors.append(f"{field} must be a non-empty string array")
        elif field == "expected_checks" and len(items) != len(set(items)):
            errors.append("expected_checks must be unique")
    mutants = value.get("mutant_outcomes")
    if not isinstance(mutants, list):
        errors.append("mutant_outcomes must be an array")
    else:
        for index, mutant in enumerate(mutants):
            if not isinstance(mutant, dict) or set(mutant) != {"mutant_id", "killed", "check_ids"}:
                errors.append(f"mutant_outcomes[{index}] is not closed-schema")
                continue
            if not mutant["mutant_id"] or not isinstance(mutant["killed"], bool):
                errors.append(f"mutant_outcomes[{index}] has invalid identity/outcome")
            checks = mutant["check_ids"]
            if not isinstance(checks, list) or not checks or len(checks) != len(set(checks)):
                errors.append(f"mutant_outcomes[{index}].check_ids must be non-empty and unique")
    coverage = value.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != {"schema_version", "measured_ids", "missing_ids"}:
        errors.append("coverage is not closed-schema")
    elif coverage.get("schema_version") != 3:
        errors.append("coverage schema version must be 3")
    elif any(not isinstance(coverage.get(field), list) for field in ("measured_ids", "missing_ids")):
        errors.append("coverage identifiers must be arrays")
    if value.get("non_vacuity") not in {"passed", "failed", "not_applicable"}:
        errors.append("non_vacuity is invalid")
    if value.get("strict_status") not in {"passed", "failed"}:
        errors.append("strict_status is invalid")
    if value.get("execution_kind") not in {"real", "mocked"}:
        errors.append("execution_kind is invalid")
    return tuple(errors)


def read_evidence_record(path: Path) -> tuple[dict[str, Any], tuple[str, ...], str | None]:
    """Read, validate, and digest a regular evidence JSON file."""

    if not path.is_file() or path.is_symlink():
        return {}, ("evidence path is not a regular file",), None
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        return {}, (f"evidence is unreadable: {error}",), None
    if not isinstance(value, dict):
        return {}, ("evidence root must be an object",), None
    return value, validate_evidence_record(value), hashlib.sha256(raw).hexdigest()
