"""Governed requirements-baseline interchange adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dv_platform.core.models import EvidenceKind, EvidenceRef, VerificationRequirement

REQUIREMENTS_SCHEMA_VERSION = 1
MAX_REQUIREMENTS_BYTES = 64 * 1024 * 1024


class RequirementsImportError(ValueError):
    """Raised when an enterprise requirements export is not governed or valid."""


@dataclass(frozen=True)
class EnterpriseRequirement:
    requirement: VerificationRequirement
    status: str
    verification_method: str
    parent_ids: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RequirementsImportResult:
    producer: str
    baseline_id: str
    exported_at: str
    requirements: tuple[EnterpriseRequirement, ...]


class RequirementsManifestImporter:
    kind = "requirements_importer"
    api_version = 1

    def supports(self, path: Path) -> bool:
        return path.name.lower().endswith((".dvreq.json", ".requirements.json"))

    def import_requirements(self, path: Path, *, strict: bool = False) -> RequirementsImportResult:
        raw = path.read_bytes()
        if len(raw) > MAX_REQUIREMENTS_BYTES:
            raise RequirementsImportError(f"requirements export exceeds {MAX_REQUIREMENTS_BYTES} byte limit: {path}")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RequirementsImportError(f"invalid requirements JSON in {path}: {exc}") from exc
        root = _validated_root(document)
        producer = _string(root, "producer", "requirements export")
        baseline_id = _string(root, "baseline_id", "requirements export")
        exported_at = _exported_at(root)
        records = root.get("requirements")
        if not isinstance(records, list) or not records:
            raise RequirementsImportError("requirements export must contain requirements")
        result = _import_records(records, path, producer, baseline_id, strict)
        known_ids = {item.requirement.requirement_id for item in result}
        missing_parents = sorted({parent for item in result for parent in item.parent_ids if parent not in known_ids})
        if missing_parents:
            raise RequirementsImportError("requirements reference missing parents: " + ", ".join(missing_parents))
        return RequirementsImportResult(producer, baseline_id, exported_at, tuple(result))


def _validated_root(document: object) -> Mapping[str, Any]:
    root = _object(document, "requirements export")
    allowed = {"schema_version", "producer", "baseline_id", "exported_at", "requirements"}
    unknown = set(root) - allowed
    if unknown:
        raise RequirementsImportError(f"unknown requirements export fields: {', '.join(sorted(unknown))}")
    if root.get("schema_version") != REQUIREMENTS_SCHEMA_VERSION:
        raise RequirementsImportError("unsupported requirements schema_version")
    return root


def _exported_at(root: Mapping[str, Any]) -> str:
    exported_at = _string(root, "exported_at", "requirements export")
    try:
        timestamp = datetime.fromisoformat(exported_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RequirementsImportError("requirements exported_at must be ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise RequirementsImportError("requirements exported_at must include a timezone")
    return exported_at


def _import_records(
    records: list[object],
    path: Path,
    producer: str,
    baseline_id: str,
    strict: bool,
) -> list[EnterpriseRequirement]:
    result: list[EnterpriseRequirement] = []
    identities: set[str] = set()
    for index, raw_record in enumerate(records):
        record = _validated_record(raw_record, index)
        requirement_id = _string(record, "requirement_id", f"requirements[{index}]")
        if requirement_id in identities:
            raise RequirementsImportError(f"duplicate requirement_id: {requirement_id}")
        identities.add(requirement_id)
        result.append(_enterprise_requirement(record, index, path, producer, baseline_id, strict))
    return result


def _validated_record(raw_record: object, index: int) -> Mapping[str, Any]:
    root = _object(raw_record, f"requirements[{index}]")
    allowed = {
        "requirement_id",
        "scope",
        "statement",
        "category",
        "signals",
        "expected_value",
        "condition",
        "status",
        "verification_method",
        "parent_ids",
        "tags",
    }
    unknown = set(root) - allowed
    if unknown:
        raise RequirementsImportError(f"unknown fields at requirements[{index}]: {', '.join(sorted(unknown))}")
    return root


def _enterprise_requirement(
    record: Mapping[str, Any],
    index: int,
    path: Path,
    producer: str,
    baseline_id: str,
    strict: bool,
) -> EnterpriseRequirement:
    label = f"requirements[{index}]"
    requirement_id = _string(record, "requirement_id", label)
    status = _string(record, "status", label).lower()
    if strict and status not in {"approved", "released"}:
        raise RequirementsImportError(f"strict requirements import rejects status {status!r}: {requirement_id}")
    evidence = EvidenceRef(
        EvidenceKind.REQUIREMENTS_EXPORT,
        f"{producer}:{baseline_id}",
        f"{path}:{requirement_id}",
        "governed requirements baseline",
    )
    requirement = VerificationRequirement(
        requirement_id,
        _string(record, "scope", label),
        _string(record, "statement", label),
        str(record.get("category", "general")),
        _strings(record.get("signals", []), f"{label}.signals"),
        _optional_string(record, "expected_value"),
        _optional_string(record, "condition"),
        "governed",
        (evidence,),
    )
    return EnterpriseRequirement(
        requirement,
        status,
        _string(record, "verification_method", label),
        _strings(record.get("parent_ids", []), f"{label}.parent_ids"),
        _strings(record.get("tags", []), f"{label}.tags"),
    )


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise RequirementsImportError(f"{label} must be an object")
    return value


def _string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise RequirementsImportError(f"{label}.{key} must be a non-empty string")
    return item.strip()


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise RequirementsImportError(f"{key} must be a non-empty string when provided")
    return item.strip()


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise RequirementsImportError(f"{label} must be a list of non-empty strings")
    return tuple(dict.fromkeys(item.strip() for item in value))
