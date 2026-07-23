# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from dv_platform.analysis.plan_store import read_plan_records
from dv_platform.core.models import CLIConfig, SimulatorConfig, VerificationTarget
from dv_platform.core.paths import is_within
from dv_platform.core.schema import (
    MIN_READABLE_PLAN_SCHEMA_VERSION,
    MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    RTL_FACTS_SCHEMA_VERSION,
)
from dv_platform.core.tool_versions import formal_dependency_qualifications, probe_tool_version


def _rtl_facts_status(config: CLIConfig) -> dict[str, Any]:
    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    result: dict[str, Any] = {
        "current_schema_version": RTL_FACTS_SCHEMA_VERSION,
        "min_readable_schema_version": MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
        "path": str(facts_path),
        "summary_path": str(summary_path),
        "present": facts_path.is_file(),
        "stored_schema_version": None,
        "verilator_version": None,
        "verilator_compatibility": None,
        "normalization_frontends": [],
        "modules": 0,
        "status": "missing",
    }
    if not facts_path.is_file():
        return result
    try:
        payload = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["status"] = "invalid"
        result["error"] = str(error)
        return result
    if not isinstance(payload, dict):
        result["status"] = "invalid"
        result["error"] = "RTL facts must contain a JSON object"
        return result
    try:
        stored_version = int(payload.get("schema_version", 1))
    except (TypeError, ValueError) as error:
        result["status"] = "invalid"
        result["error"] = str(error)
        return result
    result["stored_schema_version"] = stored_version
    result["verilator_version"] = payload.get("verilator_version")
    result["verilator_compatibility"] = payload.get("verilator_compatibility")
    frontends = payload.get("normalization_frontends", ())
    result["normalization_frontends"] = [str(item) for item in frontends] if isinstance(frontends, list) else []
    modules = payload.get("modules", ())
    result["modules"] = len(modules) if isinstance(modules, list) else 0
    result["status"] = _schema_status(
        stored_version,
        current=RTL_FACTS_SCHEMA_VERSION,
        minimum=MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
    )
    return result


def _plan_status(config: CLIConfig) -> dict[str, Any]:
    plans_path = config.work_dir / "plans" / "plans.sqlite"
    result: dict[str, Any] = {
        "current_schema_version": PLAN_SCHEMA_VERSION,
        "min_readable_schema_version": MIN_READABLE_PLAN_SCHEMA_VERSION,
        "path": str(plans_path),
        "present": plans_path.is_file(),
        "stored_schema_versions": [],
        "modules": [],
        "expected_generated": [],
        "plans": 0,
        "status": "missing",
    }
    if not plans_path.is_file():
        return result
    try:
        records = read_plan_records(plans_path)
    except (OSError, ValueError, sqlite3.Error) as error:
        result["status"] = "invalid"
        result["error"] = str(error)
        return result
    try:
        versions = tuple(sorted({int(record["plan"].get("schema_version", 1)) for record in records}))
        expected_generated = tuple(
            sorted(
                (
                    {"target": str(target), "module": str(record["module"])}
                    for record in records
                    for target in record["plan"].get("targets", ())
                ),
                key=lambda item: (item["target"], item["module"]),
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        result["status"] = "invalid"
        result["error"] = str(error)
        return result
    result["stored_schema_versions"] = list(versions)
    result["modules"] = [str(record["module"]) for record in records]
    result["expected_generated"] = list(expected_generated)
    result["plans"] = len(records)
    statuses = tuple(
        _schema_status(version, current=PLAN_SCHEMA_VERSION, minimum=MIN_READABLE_PLAN_SCHEMA_VERSION)
        for version in versions
    )
    if not statuses:
        result["status"] = "empty"
    elif any(status == "future" for status in statuses):
        result["status"] = "future"
    elif any(status == "unsupported" for status in statuses):
        result["status"] = "unsupported"
    elif any(status == "legacy" for status in statuses):
        result["status"] = "legacy"
    else:
        result["status"] = "current"
    return result


def _tool_status(config: CLIConfig, rtl_status: dict[str, Any], runs: dict[str, Any]) -> dict[str, Any]:
    return {
        "verilator": {
            "command": config.verilator_executable,
            "available": _command_available(config.verilator_executable),
            "stored_version": rtl_status.get("verilator_version"),
        },
        "simulators": [
            {
                "target": str(simulator.target),
                "name": simulator.name,
                "command": simulator.command,
                "available": _command_available(simulator.command),
                "qualification": _simulator_qualification(simulator, runs),
            }
            for simulator in config.simulators
        ],
        "formal_tools": [
            {
                "name": tool.name,
                "command": tool.command,
                "available": _command_available(tool.command),
                "qualification": probe_tool_version(tool.command),
                "dependencies": list(formal_dependency_qualifications(tool.command)),
            }
            for tool in config.formal_tools
        ],
    }


def _simulator_qualification(simulator: SimulatorConfig, runs: dict[str, Any]) -> dict[str, Any]:
    direct = probe_tool_version(simulator.command)
    if direct.get("status") == "supported":
        return direct
    candidates = tuple(
        item
        for item in runs.get("current", ())
        if isinstance(item, dict)
        and item.get("target") == str(simulator.target)
        and item.get("status") in {"pass", "passed"}
        and isinstance(item.get("tool_qualification"), dict)
        and item["tool_qualification"].get("tool") == simulator.name
        and item["tool_qualification"].get("status") == "supported"
    )
    return (
        max(candidates, key=lambda item: int(item.get("mtime_ns") or 0))["tool_qualification"] if candidates else direct
    )


def _generated_status(config: CLIConfig) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    unsafe_roots = 0
    for target in VerificationTarget:
        modules_dir = (
            config.output_dir / "formal" / "modules"
            if target == VerificationTarget.FORMAL
            else config.output_dir / "simulation" / str(target) / "modules"
        )
        if not is_within(modules_dir, config.output_dir):
            unsafe_roots += 1
            continue
        if not modules_dir.is_dir():
            continue
        for module_dir in sorted((path for path in modules_dir.iterdir() if path.is_dir()), key=lambda path: path.name):
            modules.append(_generated_module_status(target, module_dir))
    quality_failed = sum(int(module["quality_failed"]) for module in modules)
    quality_missing = sum(int(module["quality_missing"]) for module in modules)
    artifacts_missing = sum(int(module["artifacts_missing"]) for module in modules)
    provenance_invalid = sum(int(module["provenance_invalid"]) for module in modules)
    integrity_missing = sum(int(module["integrity_missing"]) for module in modules)
    integrity_failed = sum(int(module["integrity_failed"]) for module in modules)
    tool_validation_missing = sum(int(module["tool_validation_missing"]) for module in modules)
    tool_validation_failed = sum(int(module["tool_validation_failed"]) for module in modules)
    traceability_missing = sum(int(module["traceability_missing"]) for module in modules)
    execution_manifest_invalid = sum(int(module["execution_manifest_invalid"]) for module in modules)
    return {
        "modules": modules,
        "quality_missing": quality_missing,
        "quality_failed": quality_failed,
        "artifacts_missing": artifacts_missing,
        "provenance_invalid": provenance_invalid,
        "integrity_missing": integrity_missing,
        "integrity_failed": integrity_failed,
        "tool_validation_missing": tool_validation_missing,
        "tool_validation_failed": tool_validation_failed,
        "traceability_missing": traceability_missing,
        "execution_manifest_invalid": execution_manifest_invalid,
        "unsafe_roots": unsafe_roots,
    }
