"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.analysis.ai_planning import ai_readiness
from dv_platform.analysis.coverage import read_coverage_summary
from dv_platform.analysis.plan_store import read_plan_records
from dv_platform.analysis.revisions import read_revisions, revision_state_path
from dv_platform.core.models import CLIConfig, SimulatorConfig, VerificationTarget
from dv_platform.core.paths import is_within
from dv_platform.core.schema import (
    MIN_READABLE_PLAN_SCHEMA_VERSION,
    MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    RTL_FACTS_SCHEMA_VERSION,
)
from dv_platform.core.tool_versions import formal_dependency_qualifications, probe_tool_version
from dv_platform.enterprise.store import enterprise_status
from dv_platform.generators.artifacts import validate_generated_directory


def collect_platform_status(config: CLIConfig) -> dict[str, Any]:
    """Collect local dv-platform state without modifying project files."""

    rtl_status = _rtl_facts_status(config)
    plan_status = _plan_status(config)
    generated = _generated_status(config)
    generated["expected_missing"] = _missing_expected_generated(plan_status, generated)
    generated["unexpected"] = _unexpected_generated(plan_status, generated)
    runs = _run_status(config, generated)
    try:
        coverage = read_coverage_summary(config)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        coverage = {"passed": False, "invalid": str(error)}
    revisions = _revision_closure_status(config, generated, runs, coverage)
    return {
        "enterprise": enterprise_status(config),
        "schemas": {
            "rtl_facts": rtl_status,
            "plans": plan_status,
        },
        "tools": _tool_status(config, rtl_status, runs),
        "generated": generated,
        "runs": runs,
        "coverage": coverage,
        "revisions": revisions,
        "coverage_policy_enabled": any(
            value is not None
            for value in (
                config.coverage_policy.line_minimum,
                config.coverage_policy.branch_minimum,
                config.coverage_policy.toggle_minimum,
                config.coverage_policy.functional_minimum,
            )
        ),
        "ai": ai_readiness(config),
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
            "coverage_actionable": (
                int(coverage.get("closure", {}).get("counts", {}).get("actionable", 0))
                if isinstance(coverage, dict) and isinstance(coverage.get("closure"), dict)
                else 0
            ),
            "revision_closure_open": revisions["open"],
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
    rtl_schema = status["schemas"]["rtl_facts"]
    compatibility = rtl_schema.get("verilator_compatibility")
    normalization_frontends = rtl_schema.get("normalization_frontends", ())
    qualified_vhdl_only = bool(normalization_frontends) and all(
        isinstance(item, str) and (item.startswith("vhdl-source-normalizer/") or item == "ghdl-elaboration")
        for item in normalization_frontends
    )
    if (not isinstance(compatibility, dict) or compatibility.get("status") != "supported") and not qualified_vhdl_only:
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

    revisions = status.get("revisions")
    if isinstance(revisions, dict) and int(revisions.get("open", 0)) > 0:
        failures.append(
            {
                "code": "revision_closure_incomplete",
                "message": f"{revisions['open']} latest plan revisions lack fresh generate/run/coverage evidence",
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
    if isinstance(coverage, dict):
        if coverage.get("invalid"):
            failures.append(
                {"code": "coverage_schema_invalid", "message": f"Coverage state is invalid: {coverage['invalid']}"}
            )
        failures.extend(_coverage_closure_failures(coverage))

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
            elif simulator["qualification"]["status"] != "supported":
                failures.append(
                    {
                        "code": "simulator_version_unqualified",
                        "message": (
                            f"Configured simulator is outside its tested range: {simulator['name']} "
                            f"({simulator['qualification']['status']})"
                        ),
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
            elif tool["qualification"]["status"] != "supported":
                failures.append(
                    {
                        "code": "formal_tool_version_unqualified",
                        "message": (
                            f"Configured formal tool is outside its tested range: {tool['name']} "
                            f"({tool['qualification']['status']})"
                        ),
                    }
                )
            for dependency in tool["dependencies"]:
                if dependency["status"] != "supported":
                    failures.append(
                        {
                            "code": "formal_dependency_version_unqualified",
                            "message": (
                                f"Formal dependency is outside its tested range: {dependency['tool']} "
                                f"({dependency['status']})"
                            ),
                        }
                    )

    enterprise = status.get("enterprise", {})
    if isinstance(enterprise, dict):
        enterprise_failures = enterprise.get("failures", [])
        if isinstance(enterprise_failures, list):
            failures.extend(
                item
                for item in enterprise_failures
                if isinstance(item, dict) and isinstance(item.get("code"), str) and isinstance(item.get("message"), str)
            )
    return tuple(failures)


def _coverage_closure_failures(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    closure = coverage.get("closure")
    if not isinstance(closure, dict) or not bool(closure.get("present")):
        return []
    failures: list[dict[str, Any]] = []
    counts = closure.get("counts", {})
    failed = int(counts.get("failed", 0)) if isinstance(counts, dict) else 0
    uncovered = int(counts.get("uncovered", 0)) if isinstance(counts, dict) else 0
    if failed:
        failures.append({"code": "coverage_checks_failed", "message": f"{failed} verification checks failed"})
    if uncovered:
        failures.append({"code": "coverage_closure_open", "message": f"{uncovered} coverage points remain open"})
    if not bool(closure.get("traceability_complete", True)):
        failures.append(
            {"code": "coverage_traceability_incomplete", "message": "Coverage points lack plan traceability"}
        )
    if closure.get("stale_dispositions"):
        failures.append({"code": "coverage_dispositions_stale", "message": "Covered points retain stale dispositions"})
    feedback = coverage.get("plan_feedback")
    if isinstance(feedback, dict):
        unmeasured = feedback.get("unmeasured_checks", ())
        stale = feedback.get("stale_point_mappings", ())
        if unmeasured:
            failures.append(
                {
                    "code": "coverage_checks_unmeasured",
                    "message": f"{len(unmeasured)} executable plan checks lack coverage points",
                }
            )
        if stale:
            failures.append(
                {
                    "code": "coverage_plan_mappings_stale",
                    "message": f"{len(stale)} coverage points reference unknown checks",
                }
            )
        if not bool(feedback.get("plans_available", True)):
            failures.append(
                {"code": "coverage_plans_missing", "message": "Coverage closure was not reconciled with plans"}
            )
    sweeps = coverage.get("parameter_sweeps")
    if isinstance(sweeps, dict) and bool(sweeps.get("present")) and not bool(sweeps.get("passed")):
        failures.append(
            {
                "code": "parameter_sweep_coverage_incomplete",
                "message": f"{len(sweeps.get('gaps', ()))} parameter-sweep cross-point gaps remain",
            }
        )
    return failures


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
        "current": list(current_summaries.values()),
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
        "tool_qualification": None,
        "mtime_ns": summary_path.stat().st_mtime_ns if summary_path.is_file() else None,
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
    qualification = payload.get("tool_qualification")
    result["tool_qualification"] = qualification if isinstance(qualification, dict) else None
    return result


def _revision_closure_status(
    config: CLIConfig,
    generated: dict[str, Any],
    runs: dict[str, Any],
    coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    """Report the mandatory revision generation, rerun, and coverage sequence."""

    latest: dict[str, Any] = {}
    for revision in read_revisions(config.work_dir):
        if revision.schema_version >= 3:
            latest[revision.module] = revision
    generated_by_key = {
        (str(item.get("target")), str(item.get("module"))): item for item in generated.get("modules", ())
    }
    run_summaries = tuple(item for item in runs.get("summaries", ()) if isinstance(item, dict))
    coverage_sources = {
        str(Path(source).resolve())
        for source in (coverage.get("sources", ()) if isinstance(coverage, dict) else ())
        if isinstance(source, str)
    }
    records: list[dict[str, Any]] = []
    for module, revision in sorted(latest.items()):
        actionable = bool(
            revision.affected_check_ids
            or revision.affected_scenario_ids
            or revision.affected_artifact_paths
            or revision.required_rerun_targets
            or revision.accepted_operations
        )
        record: dict[str, Any] = {
            "revision_id": revision.revision_id,
            "module": module,
            "required_rerun_targets": list(revision.required_rerun_targets),
            "state": "no-op" if not actionable else "pending_generation",
            "reason": None,
            "run_summaries": [],
        }
        if not actionable:
            records.append(record)
            continue
        if not revision.required_rerun_targets:
            record["reason"] = "affected revision has no executable rerun target"
            records.append(record)
            continue
        path = revision_state_path(config.work_dir, revision.revision_id)
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            record["reason"] = f"revision generation state is unavailable: {error}"
            records.append(record)
            continue
        targets = state.get("generated_targets") if isinstance(state, dict) else None
        if (
            not isinstance(targets, dict)
            or state.get("resulting_plan_hash") != revision.resulting_plan_hash
            or state.get("module") != module
        ):
            record["reason"] = "revision generation state does not match its immutable snapshot"
            records.append(record)
            continue
        matching_runs: list[dict[str, Any]] = []
        generation_valid = True
        run_valid = True
        for target in revision.required_rerun_targets:
            target_state = targets.get(target)
            current = generated_by_key.get((target, module))
            if (
                not isinstance(target_state, dict)
                or not isinstance(current, dict)
                or target_state.get("provenance_sha256") != current.get("provenance_sha256")
            ):
                generation_valid = False
                break
            run = next(
                (
                    item
                    for item in run_summaries
                    if item.get("target") == target
                    and item.get("module") == module
                    and item.get("provenance_sha256") == target_state.get("provenance_sha256")
                ),
                None,
            )
            if run is None or run.get("status") not in {"pass", "passed"} or not bool(run.get("coverage_complete")):
                run_valid = False
                continue
            matching_runs.append(run)
        if not generation_valid:
            record["reason"] = "one or more required targets were not generated from this revision"
            records.append(record)
            continue
        if not run_valid or len(matching_runs) != len(revision.required_rerun_targets):
            record["state"] = "pending_run"
            record["reason"] = "one or more required targets lack a passing provenance-matched rerun"
            records.append(record)
            continue
        record["run_summaries"] = [str(item["path"]) for item in matching_runs]
        if (
            not isinstance(coverage, dict)
            or not bool(coverage.get("passed"))
            or any(str(Path(str(item["path"])).resolve()) not in coverage_sources for item in matching_runs)
        ):
            record["state"] = "pending_coverage"
            record["reason"] = "coverage was not rebuilt from every required fresh rerun"
            records.append(record)
            continue
        record["state"] = "closed"
        records.append(record)
    open_count = sum(item["state"] not in {"closed", "no-op"} for item in records)
    return {"schema_version": 1, "open": open_count, "records": records}


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
