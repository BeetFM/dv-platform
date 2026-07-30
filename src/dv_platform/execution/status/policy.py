# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import json
from typing import Any

from dv_platform.ai.code_graph import code_graph_status
from dv_platform.ai.optimization import optimizer_readiness
from dv_platform.analysis.ai_planning import ai_readiness
from dv_platform.core.models import CLIConfig
from dv_platform.enterprise.store import enterprise_status
from dv_platform.execution.coverage import read_coverage_summary
from dv_platform.qualification import capability_ledger_status


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
    optimizer_status = optimizer_readiness(config)
    optimizer_status["code_graph"] = code_graph_status(config)
    capability_status = capability_ledger_status(
        config.repo_root,
        tuple(plan_status.get("runtime_capability_cells", ())),
    )
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
        "context_optimization": optimizer_status,
        "capability_ledger": capability_status,
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
            "capability_ledger_status": capability_status["status"],
        },
    }


def evaluate_status_policy(
    status: dict[str, Any],
    require_tools: bool = True,
) -> tuple[dict[str, Any], ...]:
    """Return CI policy failures for a collected platform status report."""

    failures = _schema_policy_failures(status)
    failures.extend(_generated_policy_failures(status["generated"]))
    failures.extend(_run_coverage_policy_failures(status))
    if require_tools:
        failures.extend(_tool_policy_failures(status["tools"]))
        failures.extend(_optimizer_policy_failures(status.get("context_optimization", {})))
    failures.extend(_enterprise_policy_failures(status.get("enterprise", {})))
    capability = status.get("capability_ledger", {})
    if not isinstance(capability, dict) or capability.get("status") != "valid":
        errors = capability.get("errors", ()) if isinstance(capability, dict) else ()
        failures.append(
            {
                "code": "capability_ledger_invalid",
                "message": "Capability ledger is invalid"
                + (f": {'; '.join(str(item) for item in errors)}" if errors else ""),
            }
        )
    return tuple(failures)


def _schema_policy_failures(status: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    schemas = status["schemas"]
    for name, schema in (("rtl_facts", schemas["rtl_facts"]), ("plans", schemas["plans"])):
        schema_status = schema["status"]
        if schema_status != "current":
            failures.append(
                {"code": f"{name}_schema_{schema_status}", "message": f"{name} schema status is {schema_status}"}
            )
    if int(schemas["rtl_facts"]["modules"]) == 0:
        failures.append({"code": "rtl_facts_empty", "message": "RTL facts contain no modules"})
    if int(schemas["plans"]["plans"]) == 0:
        failures.append({"code": "plans_empty", "message": "Plan store contains no plans"})
    rtl_schema = schemas["rtl_facts"]
    compatibility = rtl_schema.get("verilator_compatibility")
    frontends = rtl_schema.get("normalization_frontends", ())
    vhdl_only = bool(frontends) and all(
        isinstance(item, str) and (item.startswith("vhdl-source-normalizer/") or item == "ghdl-elaboration")
        for item in frontends
    )
    if (not isinstance(compatibility, dict) or compatibility.get("status") != "supported") and not vhdl_only:
        failures.append(
            {
                "code": "verilator_version_unsupported",
                "message": "Stored RTL facts were not produced by a tested Verilator major version",
            }
        )
    return failures


def _optimizer_policy_failures(optimizer: object) -> list[dict[str, Any]]:
    if not isinstance(optimizer, dict) or not bool(optimizer.get("enabled")):
        return []
    failures: list[dict[str, Any]] = []
    headroom = optimizer.get("headroom", {})
    if isinstance(headroom, dict) and bool(headroom.get("enabled")) and headroom.get("health") != "available":
        failures.append({"code": "headroom_unavailable", "message": "Headroom optimization is enabled but unavailable"})
    code_graph = optimizer.get("code_graph", {})
    if isinstance(code_graph, dict) and bool(code_graph.get("enabled")):
        if not bool(code_graph.get("available")):
            failures.append(
                {
                    "code": "code_graph_unavailable",
                    "message": "code-review-graph optimization is enabled but unavailable",
                }
            )
        if not bool(code_graph.get("graph_present")):
            failures.append(
                {"code": "code_graph_missing", "message": "code-review-graph state is not built for this repository"}
            )
    return failures


def _generated_policy_failures(generated: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    count_rules = (
        ("quality_missing", "generated_quality_missing", "generated executable modules lack quality metadata"),
        ("quality_failed", "generated_quality_failed", "generated artifact quality requirements failed"),
        ("artifacts_missing", "generated_artifacts_missing", "generated artifacts listed in provenance are missing"),
        ("provenance_invalid", "generated_provenance_invalid", "generated modules have invalid provenance"),
        ("integrity_missing", "generated_integrity_missing", "generated artifacts lack integrity metadata"),
        ("integrity_failed", "generated_integrity_failed", "generated artifacts fail integrity verification"),
        (
            "tool_validation_missing",
            "generated_tool_validation_missing",
            "generated modules lack required tool validation",
        ),
        ("tool_validation_failed", "generated_tool_validation_failed", "generated modules failed tool validation"),
        (
            "traceability_missing",
            "generated_traceability_missing",
            "generated executable artifacts lack plan traceability",
        ),
        (
            "execution_manifest_invalid",
            "generated_execution_manifest_invalid",
            "generated modules have invalid execution manifests or inputs",
        ),
    )
    for field, code, description in count_rules:
        if int(generated[field]) > 0:
            failures.append({"code": code, "message": f"{generated[field]} {description}"})
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
    return failures


def _run_coverage_policy_failures(status: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    runs = status["runs"]
    if int(runs["failed"]) > 0:
        failures.append({"code": "runs_failed", "message": f"{runs['failed']} run summaries are not passing"})
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
    coverage = status.get("coverage")
    if bool(status.get("coverage_policy_enabled")) and not isinstance(coverage, dict):
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
    return failures


def _tool_policy_failures(tools: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not bool(tools["verilator"]["available"]):
        failures.append({"code": "verilator_missing", "message": "Configured Verilator command is not available"})
    for simulator in tools["simulators"]:
        if not bool(simulator["available"]):
            failures.append(
                {"code": "simulator_missing", "message": f"Configured simulator is not available: {simulator['name']}"}
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
    failures.extend(_formal_tool_policy_failures(tools["formal_tools"]))
    return failures


def _formal_tool_policy_failures(formal_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for tool in formal_tools:
        if not bool(tool["available"]):
            failures.append(
                {"code": "formal_tool_missing", "message": f"Configured formal tool is not available: {tool['name']}"}
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
    return failures


def _enterprise_policy_failures(enterprise: object) -> list[dict[str, Any]]:
    if not isinstance(enterprise, dict):
        return []
    failures = enterprise.get("failures", [])
    if not isinstance(failures, list):
        return []
    return [
        item
        for item in failures
        if isinstance(item, dict) and isinstance(item.get("code"), str) and isinstance(item.get("message"), str)
    ]


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
