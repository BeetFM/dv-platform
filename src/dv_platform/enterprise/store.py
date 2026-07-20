"""Persistence and status for enterprise semantic, requirements, and run evidence."""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any

from dv_platform.analysis.rtl import write_normalized_rtl_facts, write_rtl_facts_summary
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    VerificationRequirement,
)
from dv_platform.enterprise.qualification import qualification_status
from dv_platform.enterprise.requirements import RequirementsImportResult
from dv_platform.enterprise.semantics import SemanticImportResult

ENTERPRISE_STATE_SCHEMA_VERSION = 1


def persist_semantic_import(config: CLIConfig, result: SemanticImportResult, source: Path) -> tuple[Path, Path, Path]:
    modules_path = write_normalized_rtl_facts(config, result.modules)
    summary_path = write_rtl_facts_summary(config, result.modules)
    compatibility = {
        "status": "supported" if result.complete else "incomplete",
        "detected_major": None,
        "minimum_tested_major": None,
        "maximum_tested_major": None,
        "evidence": "complete_external_semantic_manifest" if result.complete else "partial_manifest",
    }
    producer = {"name": result.producer_name, "version": result.producer_version}
    for path in (modules_path, summary_path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["semantic_analyzer"] = producer
        payload["semantic_complete"] = result.complete
        payload["semantic_manifest_schema_version"] = result.schema_version
        payload["verilator_compatibility"] = compatibility
        atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    archive_path = config.work_dir / "rtl-facts" / "semantic-manifest.json"
    source_bytes = source.read_bytes()
    atomic_write_text(archive_path, source_bytes.decode("utf-8"))
    state_path = config.work_dir / "rtl-facts" / "semantic-import.json"
    state = {
        "schema_version": ENTERPRISE_STATE_SCHEMA_VERSION,
        "source": str(source.resolve()),
        "archive": str(archive_path),
        "sha256": sha256(source_bytes).hexdigest(),
        "producer": producer,
        "complete": result.complete,
        "modules": [
            {
                "module": item.module,
                "language": item.language,
                "standard": item.standard,
                "complete": item.complete,
                "categories": dict(item.categories),
            }
            for item in result.completeness
        ],
        "diagnostics": [asdict(item) for item in result.diagnostics],
    }
    atomic_write_text(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")
    return modules_path, summary_path, state_path


def persist_requirements_import(config: CLIConfig, result: RequirementsImportResult, source: Path) -> Path:
    path = config.work_dir / "requirements" / "baseline.json"
    source_bytes = source.read_bytes()
    payload = {
        "schema_version": ENTERPRISE_STATE_SCHEMA_VERSION,
        "source": str(source.resolve()),
        "sha256": sha256(source_bytes).hexdigest(),
        "producer": result.producer,
        "baseline_id": result.baseline_id,
        "exported_at": result.exported_at,
        "requirements": [
            {
                "requirement_id": item.requirement.requirement_id,
                "scope": item.requirement.scope,
                "statement": item.requirement.statement,
                "category": item.requirement.category,
                "signals": list(item.requirement.signals),
                "expected_value": item.requirement.expected_value,
                "condition": item.requirement.condition,
                "status": item.status,
                "verification_method": item.verification_method,
                "parent_ids": list(item.parent_ids),
                "tags": list(item.tags),
                "evidence": [
                    {
                        "kind": ref.kind.value,
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in item.requirement.evidence_refs
                ],
            }
            for item in result.requirements
        ],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def enterprise_status(config: CLIConfig) -> dict[str, Any]:
    semantic_path = config.work_dir / "rtl-facts" / "semantic-import.json"
    requirements_path = config.work_dir / "requirements" / "baseline.json"
    semantic = _read_state(semantic_path)
    requirements = _read_state(requirements_path)
    qualification = qualification_status(config)
    configured_kinds = {item.kind for item in config.adapter_plugins}
    runs: list[dict[str, Any]] = []
    run_root = config.work_dir / "enterprise-runs"
    if run_root.is_dir():
        for path in sorted(run_root.glob("*/summary.json")):
            payload = _read_state(path)
            runs.append(
                {
                    "path": str(path),
                    "valid": payload is not None,
                    "adapter": payload.get("adapter") if payload else None,
                    "family": payload.get("family") if payload else None,
                    "status": payload.get("status") if payload else "invalid",
                    "traceability_complete": bool(payload and payload.get("traceability_complete")),
                }
            )
    configured_runners = {
        (item.kind.removesuffix("_runner"), item.name)
        for item in config.adapter_plugins
        if item.kind in {"simulator_runner", "formal_runner", "analyzer_runner"}
    }
    observed_runners = {(str(run["family"]), str(run["adapter"])) for run in runs if run["valid"]}
    failures: list[dict[str, str]] = list(qualification["failures"])
    if "semantic_importer" in configured_kinds:
        if semantic is None:
            failures.append({"code": "semantic_import_missing", "message": "Semantic import is missing."})
        elif not semantic.get("complete"):
            failures.append(
                {
                    "code": "semantic_completeness_open",
                    "message": "Semantic capability ledger is incomplete.",
                }
            )
    if "requirements_importer" in configured_kinds and requirements is None:
        failures.append({"code": "requirements_baseline_missing", "message": "Requirements baseline is missing."})
    for family, name in sorted(configured_runners - observed_runners):
        failures.append(
            {
                "code": "enterprise_run_missing",
                "message": f"Configured enterprise runner has no result: {family}/{name}",
            }
        )
    for run in runs:
        if not run["valid"]:
            failures.append({"code": "enterprise_run_invalid", "message": f"Invalid run summary: {run['path']}"})
        elif run["status"] != "passed":
            failures.append({"code": "enterprise_run_failed", "message": f"Enterprise run failed: {run['path']}"})
        elif not run["traceability_complete"]:
            failures.append(
                {
                    "code": "enterprise_run_untraceable",
                    "message": f"Enterprise run lacks check identity: {run['path']}",
                }
            )
    return {
        "schema_version": ENTERPRISE_STATE_SCHEMA_VERSION,
        "semantic": {
            "present": semantic is not None,
            "path": str(semantic_path),
            "complete": bool(semantic and semantic.get("complete")),
            "modules": semantic.get("modules", []) if semantic else [],
        },
        "requirements": {
            "present": requirements is not None,
            "path": str(requirements_path),
            "baseline_id": requirements.get("baseline_id") if requirements else None,
            "count": len(requirements.get("requirements", [])) if requirements else 0,
        },
        "runs": runs,
        "qualification": qualification,
        "failures": failures,
        "passed": not failures,
    }


def read_requirements_baseline(config: CLIConfig) -> tuple[VerificationRequirement, ...]:
    path = config.work_dir / "requirements" / "baseline.json"
    payload = _read_state(path)
    if payload is None:
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


def _read_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != ENTERPRISE_STATE_SCHEMA_VERSION:
        return None
    return payload
