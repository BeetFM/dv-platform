"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.analysis.coverage import read_coverage_summary
from dv_platform.analysis.plan_store import MIN_READABLE_PLAN_SCHEMA_VERSION, PLAN_SCHEMA_VERSION, read_plan_records
from dv_platform.analysis.rtl import MIN_READABLE_RTL_FACTS_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.core.models import CLIConfig, VerificationTarget
from dv_platform.core.paths import is_within
from dv_platform.generators.artifacts import validate_generated_directory


def collect_platform_status(config: CLIConfig) -> dict[str, Any]:
    """Collect local dv-platform state without modifying project files."""

    rtl_status = _rtl_facts_status(config)
    plan_status = _plan_status(config)
    generated = _generated_status(config)
    generated["expected_missing"] = _missing_expected_generated(plan_status, generated)
    generated["unexpected"] = _unexpected_generated(plan_status, generated)
    runs = _run_status(config, generated)
    coverage = read_coverage_summary(config)
    return {
        "schemas": {
            "rtl_facts": rtl_status,
            "plans": plan_status,
        },
        "tools": _tool_status(config, rtl_status),
        "generated": generated,
        "runs": runs,
        "coverage": coverage,
        "coverage_policy_enabled": any(
            value is not None
            for value in (
                config.coverage_policy.line_minimum,
                config.coverage_policy.branch_minimum,
                config.coverage_policy.toggle_minimum,
                config.coverage_policy.functional_minimum,
            )
        ),
        "summary": {
            "rtl_facts_status": rtl_status["status"],
            "plan_status": plan_status["status"],
            "generated_modules": len(generated["modules"]),
            "generated_artifacts": sum(int(module["artifacts"]) for module in generated["modules"]),
            "quality_missing": generated["quality_missing"],
            "quality_failed": generated["quality_failed"],
            "artifacts_missing": generated["artifacts_missing"],
            "provenance_invalid": generated["provenance_invalid"],
            "integrity_missing": generated["integrity_missing"],
            "integrity_failed": generated["integrity_failed"],
            "tool_validation_missing": generated["tool_validation_missing"],
            "tool_validation_failed": generated["tool_validation_failed"],
            "traceability_missing": generated["traceability_missing"],
            "execution_manifest_invalid": generated["execution_manifest_invalid"],
            "expected_generated_missing": len(generated["expected_missing"]),
            "unexpected_generated": len(generated["unexpected"]),
            "unsafe_generated_roots": generated["unsafe_roots"],
            "run_summaries": len(runs["summaries"]),
            "failed_runs": runs["failed"],
            "expected_runs_missing": len(runs["expected_missing"]),
            "coverage_status": "missing" if coverage is None else "passed" if coverage.get("passed") else "failed",
        },
    }


def evaluate_status_policy(
    status: dict[str, Any],
    require_tools: bool = True,
) -> tuple[dict[str, Any], ...]:
    """Return CI policy failures for a collected platform status report."""

    failures: list[dict[str, Any]] = []
    schemas = status["schemas"]
    for name, schema in (("rtl_facts", schemas["rtl_facts"]), ("plans", schemas["plans"])):
        schema_status = schema["status"]
        if schema_status != "current":
            failures.append(
                {
                    "code": f"{name}_schema_{schema_status}",
                    "message": f"{name} schema status is {schema_status}",
                }
            )

    if int(status["schemas"]["rtl_facts"]["modules"]) == 0:
        failures.append({"code": "rtl_facts_empty", "message": "RTL facts contain no modules"})
    if int(status["schemas"]["plans"]["plans"]) == 0:
        failures.append({"code": "plans_empty", "message": "Plan store contains no plans"})
    compatibility = status["schemas"]["rtl_facts"].get("verilator_compatibility")
    if not isinstance(compatibility, dict) or compatibility.get("status") != "supported":
        failures.append(
            {
                "code": "verilator_version_unsupported",
                "message": "Stored RTL facts were not produced by a tested Verilator major version",
            }
        )

    generated = status["generated"]
    if int(generated["quality_missing"]) > 0:
        failures.append(
            {
                "code": "generated_quality_missing",
                "message": f"{generated['quality_missing']} generated executable modules lack quality metadata",
            }
        )
    if int(generated["quality_failed"]) > 0:
        failures.append(
            {
                "code": "generated_quality_failed",
                "message": f"{generated['quality_failed']} generated artifact quality requirements failed",
            }
        )
    if int(generated["artifacts_missing"]) > 0:
        failures.append(
            {
                "code": "generated_artifacts_missing",
                "message": f"{generated['artifacts_missing']} generated artifacts listed in provenance are missing",
            }
        )
    if int(generated["provenance_invalid"]) > 0:
        failures.append(
            {
                "code": "generated_provenance_invalid",
                "message": f"{generated['provenance_invalid']} generated modules have invalid provenance",
            }
        )
    if int(generated["integrity_missing"]) > 0:
        failures.append(
            {
                "code": "generated_integrity_missing",
                "message": f"{generated['integrity_missing']} generated artifacts lack integrity metadata",
            }
        )
    if int(generated["integrity_failed"]) > 0:
        failures.append(
            {
                "code": "generated_integrity_failed",
                "message": f"{generated['integrity_failed']} generated artifacts fail integrity verification",
            }
        )
    if int(generated["tool_validation_missing"]) > 0:
        failures.append(
            {
                "code": "generated_tool_validation_missing",
                "message": f"{generated['tool_validation_missing']} generated modules lack required tool validation",
            }
        )
    if int(generated["tool_validation_failed"]) > 0:
        failures.append(
            {
                "code": "generated_tool_validation_failed",
                "message": f"{generated['tool_validation_failed']} generated modules failed tool validation",
            }
        )
    if int(generated["traceability_missing"]) > 0:
        failures.append(
            {
                "code": "generated_traceability_missing",
                "message": f"{generated['traceability_missing']} generated executable artifacts lack plan traceability",
            }
        )
    if int(generated["execution_manifest_invalid"]) > 0:
        failures.append(
            {
                "code": "generated_execution_manifest_invalid",
                "message": f"{generated['execution_manifest_invalid']} generated modules have invalid execution manifests or inputs",
            }
        )
    if generated["expected_missing"]:
        failures.append(
            {
                "code": "expected_generated_modules_missing",
                "message": f"{len(generated['expected_missing'])} planned target/module outputs are missing",
            }
        )
    if generated["unexpected"]:
        failures.append(
            {
                "code": "unexpected_generated_modules",
                "message": f"{len(generated['unexpected'])} generated target/module outputs are not in current plans",
            }
        )
    if int(generated["unsafe_roots"]) > 0:
        failures.append(
            {
                "code": "unsafe_generated_roots",
                "message": f"{generated['unsafe_roots']} generated target roots escape the configured output directory",
            }
        )

    runs = status["runs"]
    if int(runs["failed"]) > 0:
        failures.append(
            {
                "code": "runs_failed",
                "message": f"{runs['failed']} run summaries are not passing",
            }
        )
    if runs["expected_missing"]:
        failures.append(
            {
                "code": "expected_runs_missing",
                "message": f"{len(runs['expected_missing'])} generated executable modules have no run summary",
            }
        )

    coverage_policy_enabled = bool(status.get("coverage_policy_enabled"))
    coverage = status.get("coverage")
    if coverage_policy_enabled and not isinstance(coverage, dict):
        failures.append(
            {"code": "coverage_missing", "message": "Coverage thresholds are configured but no report was imported"}
        )
    elif isinstance(coverage, dict) and not bool(coverage.get("passed")):
        failures.append({"code": "coverage_gate_failed", "message": "Imported coverage does not meet policy"})

    if require_tools:
        tools = status["tools"]
        if not bool(tools["verilator"]["available"]):
            failures.append(
                {
                    "code": "verilator_missing",
                    "message": "Configured Verilator command is not available",
                }
            )
        for simulator in tools["simulators"]:
            if not bool(simulator["available"]):
                failures.append(
                    {
                        "code": "simulator_missing",
                        "message": f"Configured simulator is not available: {simulator['name']}",
                    }
                )
        for tool in tools["formal_tools"]:
            if not bool(tool["available"]):
                failures.append(
                    {
                        "code": "formal_tool_missing",
                        "message": f"Configured formal tool is not available: {tool['name']}",
                    }
                )

    return tuple(failures)


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


def _tool_status(config: CLIConfig, rtl_status: dict[str, Any]) -> dict[str, Any]:
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
            }
            for simulator in config.simulators
        ],
        "formal_tools": [
            {
                "name": tool.name,
                "command": tool.command,
                "available": _command_available(tool.command),
            }
            for tool in config.formal_tools
        ],
    }


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


def _generated_module_status(target: VerificationTarget, module_dir: Path) -> dict[str, Any]:
    provenance_path = module_dir / "provenance.json"
    result: dict[str, Any] = {
        "target": str(target),
        "module": module_dir.name,
        "path": str(module_dir),
        "provenance": str(provenance_path),
        "provenance_present": provenance_path.is_file(),
        "provenance_sha256": None,
        "provenance_invalid": 0,
        "artifacts": 0,
        "quality_total": 0,
        "quality_missing": 0,
        "quality_failed": 0,
        "artifacts_missing": 0,
        "integrity_missing": 0,
        "integrity_failed": 0,
        "tool_validation_missing": 0,
        "tool_validation_failed": 0,
        "traceability_missing": 0,
        "execution_manifest_invalid": 0,
        "status": "missing_provenance",
    }
    if module_dir.is_symlink() or not is_within(provenance_path, module_dir):
        result["provenance_invalid"] = 1
        result["status"] = "unsafe_module_path"
        return result
    if not provenance_path.is_file():
        result["provenance_invalid"] = 1
        return result
    try:
        provenance_bytes = provenance_path.read_bytes()
        provenance = json.loads(provenance_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = str(error)
        return result
    result["provenance_sha256"] = hashlib.sha256(provenance_bytes).hexdigest()
    if not isinstance(provenance, dict) or provenance.get("schema_version") != 2:
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = "unsupported or missing provenance schema"
        return result
    artifacts = provenance.get("artifacts", ())
    if not isinstance(artifacts, list):
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = "artifacts is not a list"
        return result
    if provenance.get("module") != module_dir.name or provenance.get("target") != str(target):
        result["provenance_invalid"] = 1
        result["status"] = "invalid_provenance"
        result["error"] = "module or target does not match provenance path"
        return result
    quality_requirements = [
        requirement
        for artifact in artifacts
        if isinstance(artifact, dict)
        for requirement in artifact.get("quality_requirements", ())
        if isinstance(requirement, dict)
    ]
    failed = tuple(requirement for requirement in quality_requirements if not bool(requirement.get("satisfied")))
    executable_kinds = {"testbench", "formal_harness", "assertion", "run_script"}
    executable_artifacts = tuple(
        artifact for artifact in artifacts if isinstance(artifact, dict) and artifact.get("kind") in executable_kinds
    )
    artifacts_without_quality = tuple(
        artifact for artifact in executable_artifacts if not artifact.get("quality_requirements")
    )
    artifacts_without_traceability = tuple(
        artifact for artifact in executable_artifacts if not artifact.get("traceability")
    )
    artifact_checks = tuple(
        _artifact_integrity(module_dir, artifact) for artifact in artifacts if isinstance(artifact, dict)
    )
    tool_validation = provenance.get("tool_validation")
    required_validation = isinstance(tool_validation, dict) and bool(tool_validation.get("required"))
    validation_status = str(tool_validation.get("status")) if isinstance(tool_validation, dict) else "missing"
    result["artifacts"] = len(artifacts)
    result["quality_total"] = len(quality_requirements)
    result["quality_missing"] = len(artifacts_without_quality)
    result["quality_failed"] = len(failed)
    result["artifacts_missing"] = sum(1 for check in artifact_checks if check == "missing")
    result["integrity_missing"] = sum(1 for check in artifact_checks if check == "integrity_missing")
    result["integrity_failed"] = sum(1 for check in artifact_checks if check == "integrity_failed")
    result["tool_validation_missing"] = int(
        not isinstance(tool_validation, dict) or (required_validation and validation_status not in {"passed", "failed"})
    )
    result["tool_validation_failed"] = int(required_validation and validation_status == "failed")
    result["traceability_missing"] = len(artifacts_without_traceability)
    try:
        validate_generated_directory(target, module_dir.name, module_dir)
    except (OSError, ValueError) as error:
        result["execution_manifest_invalid"] = 1
        result["execution_manifest_error"] = str(error)
    result["tool_validation"] = tool_validation
    if result["artifacts_missing"]:
        result["status"] = "artifacts_missing"
    elif result["integrity_failed"]:
        result["status"] = "integrity_failed"
    elif result["integrity_missing"]:
        result["status"] = "integrity_missing"
    elif result["tool_validation_failed"]:
        result["status"] = "tool_validation_failed"
    elif result["tool_validation_missing"]:
        result["status"] = "tool_validation_missing"
    elif result["execution_manifest_invalid"]:
        result["status"] = "execution_manifest_invalid"
    elif result["traceability_missing"]:
        result["status"] = "traceability_missing"
    elif result["quality_missing"]:
        result["status"] = "quality_missing"
    elif failed:
        result["status"] = "quality_failed"
    else:
        result["status"] = "ok"
    return result


def _missing_expected_generated(
    plan_status: dict[str, Any],
    generated: dict[str, Any],
) -> list[dict[str, str]]:
    expected = {
        (str(item["target"]), str(item["module"]))
        for item in plan_status.get("expected_generated", ())
        if isinstance(item, dict)
    }
    actual = {
        (str(item["target"]), str(item["module"])) for item in generated.get("modules", ()) if isinstance(item, dict)
    }
    return [{"target": target, "module": module} for target, module in sorted(expected - actual)]


def _unexpected_generated(
    plan_status: dict[str, Any],
    generated: dict[str, Any],
) -> list[dict[str, str]]:
    expected = {
        (str(item["target"]), str(item["module"]))
        for item in plan_status.get("expected_generated", ())
        if isinstance(item, dict)
    }
    actual = {
        (str(item["target"]), str(item["module"])) for item in generated.get("modules", ()) if isinstance(item, dict)
    }
    return [{"target": target, "module": module} for target, module in sorted(actual - expected)]


def _artifact_integrity(module_dir: Path, artifact: dict[str, Any]) -> str:
    raw_path = artifact.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return "integrity_failed"
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return "integrity_failed"
    path = module_dir / relative
    if not is_within(path, module_dir):
        return "integrity_failed"
    if not path.is_file():
        return "missing"
    expected_hash = artifact.get("content_sha256")
    expected_size = artifact.get("size_bytes")
    if not isinstance(expected_hash, str) or not isinstance(expected_size, int):
        return "integrity_missing"
    try:
        content = path.read_bytes()
    except OSError:
        return "integrity_failed"
    if len(content) != expected_size or hashlib.sha256(content).hexdigest() != expected_hash:
        return "integrity_failed"
    return "ok"


def _run_status(config: CLIConfig, generated: dict[str, Any]) -> dict[str, Any]:
    runs_dir = config.work_dir / "runs"
    summaries: list[dict[str, Any]] = []
    if runs_dir.is_dir():
        for summary_path in sorted(runs_dir.rglob("summary.json"), key=lambda path: path.as_posix()):
            summaries.append(_run_summary_status(summary_path))
    runnable_targets = {str(VerificationTarget.COCOTB), str(VerificationTarget.FORMAL)} | {
        str(simulator.target) for simulator in config.simulators
    }
    expected = {
        (str(module["target"]), str(module["module"])): module.get("provenance_sha256")
        for module in generated["modules"]
        if str(module["target"]) in runnable_targets
    }
    current_summaries = {
        (str(summary.get("target")), str(summary.get("module"))): summary
        for summary in summaries
        if summary.get("module") is not None
        and isinstance(expected.get((str(summary.get("target")), str(summary.get("module")))), str)
        and summary.get("provenance_sha256") == expected.get((str(summary.get("target")), str(summary.get("module"))))
    }
    failed = sum(
        1
        for summary in current_summaries.values()
        if summary.get("status") not in {"passed", "pass"} or not bool(summary.get("coverage_complete"))
    )
    expected_missing = [
        {"target": target, "module": module} for target, module in sorted(set(expected) - set(current_summaries))
    ]
    return {
        "summaries": summaries,
        "failed": failed,
        "expected_missing": expected_missing,
    }


def _run_summary_status(summary_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(summary_path),
        "target": None,
        "module": None,
        "status": "invalid",
        "return_code": None,
        "provenance_sha256": None,
        "coverage_complete": False,
    }
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["error"] = str(error)
        return result
    if not isinstance(payload, dict):
        result["error"] = "run summary must contain a JSON object"
        return result
    result["target"] = payload.get("target")
    result["module"] = payload.get("module")
    result["status"] = payload.get("status", payload.get("formal_status", "unknown"))
    result["return_code"] = payload.get("return_code")
    result["provenance_sha256"] = payload.get("provenance_sha256")
    coverage = payload.get("verification_coverage")
    result["coverage_complete"] = bool(coverage.get("complete")) if isinstance(coverage, dict) else False
    return result


def _schema_status(stored: int, current: int, minimum: int) -> str:
    if stored > current:
        return "future"
    if stored < minimum:
        return "unsupported"
    if stored < current:
        return "legacy"
    return "current"


def _command_available(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    executable = parts[0]
    if Path(executable).is_absolute() or "/" in executable:
        return Path(executable).exists()
    return shutil.which(executable) is not None
