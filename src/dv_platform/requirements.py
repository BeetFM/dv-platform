"""Shared read-only access to normalized requirements evidence."""

from __future__ import annotations

import json

from dv_platform.domain.models import CLIConfig, EvidenceKind, EvidenceRef, VerificationRequirement


def read_requirements_baseline(config: CLIConfig) -> tuple[VerificationRequirement, ...]:
    """Read historical normalized requirements without requiring Enterprise code."""

    path = config.work_dir / "requirements" / "baseline.json"
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return ()
    requirements: list[VerificationRequirement] = []
    for raw in payload.get("requirements", []):
        if not isinstance(raw, dict):
            raise ValueError(f"invalid requirement record in {path}")
        evidence = tuple(
            EvidenceRef(
                EvidenceKind(item["kind"]),
                item["source_id"],
                item["locator"],
                item.get("summary"),
            )
            for item in raw.get("evidence", [])
            if isinstance(item, dict)
        )
        requirements.append(
            VerificationRequirement(
                requirement_id=str(raw["requirement_id"]),
                scope=str(raw["scope"]),
                statement=str(raw["statement"]),
                category=str(raw.get("category", "general")),
                signals=tuple(str(item) for item in raw.get("signals", [])),
                expected_value=raw.get("expected_value"),
                condition=raw.get("condition"),
                confidence="governed",
                evidence_refs=evidence,
            )
        )
    return tuple(requirements)
