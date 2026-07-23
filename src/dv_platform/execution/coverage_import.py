# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig
from dv_platform.execution.closure import apply_coverage_feedback_to_stored_plans

COVERAGE_SCHEMA_VERSION = 3
MIN_READABLE_COVERAGE_SCHEMA_VERSION = 1
METRICS = ("line", "branch", "toggle", "functional")
CLOSURE_STATES = (
    "covered",
    "uncovered",
    "bounded_pass",
    "unsupported",
    "failed",
    "waived",
    "unreachable",
    "excluded",
)
CLOSED_STATES = {"covered", "waived", "unreachable"}
TRACEABLE_POINT_KINDS = {"assertion", "cover", "covergroup", "coverpoint", "formal", "formal_property", "functional"}


class CoverageImporter(Protocol):
    """Versioned plugin surface for vendor coverage databases."""

    def supports(self, path: Path) -> bool:
        """Return whether this importer owns the supplied report."""

    def import_coverage(self, path: Path) -> dict[str, Any]:
        """Return the normalized public JSON coverage schema."""


def import_coverage_reports(
    config: CLIConfig,
    paths: tuple[Path, ...],
    coverage_importers: tuple[CoverageImporter, ...] = (),
    as_of: date | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Import supported local reports and persist a deterministic merged summary."""

    if not paths:
        raise ValueError("At least one coverage report is required")
    reports = tuple(_load_report(path.expanduser().resolve(strict=True), coverage_importers) for path in paths)
    merged = _merge_reports(reports)
    closure = _merge_closure_reports(reports, strict=config.strict or config.ci, as_of=as_of)
    gates = _evaluate_gates(merged["metrics"], config.coverage_policy)
    path = config.work_dir / "coverage" / "summary.json"
    markdown_path = path.with_name("summary.md")
    yaml_path = path.with_name("summary.yaml")
    sarif_path = path.with_name("closure.sarif")
    payload = {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "sources": [report["source"] for report in reports],
        "metrics": merged["metrics"],
        "modules": merged["modules"],
        "gates": gates,
        "passed": all(gate["passed"] for gate in gates) and closure["passed"],
        "gaps": _coverage_gaps(merged["modules"], config.coverage_policy),
        "closure": closure,
        "closure_gaps": closure["gaps"],
        "parameter_sweeps": {},
        "exports": {
            "json": str(path),
            "markdown": str(markdown_path),
            "yaml": str(yaml_path),
            "sarif": str(sarif_path),
        },
    }
    plan_feedback = apply_coverage_feedback_to_stored_plans(config, payload, path)
    payload["plan_feedback"] = plan_feedback
    parameter_sweeps = _parameter_sweep_coverage(config, closure)
    payload["parameter_sweeps"] = parameter_sweeps
    if closure["present"]:
        if not plan_feedback["plans_available"] and (config.strict or config.ci):
            closure["policy_failures"].append("verification plans are unavailable for closure reconciliation")
        if plan_feedback["unmeasured_checks"]:
            closure["policy_failures"].append("executable plan checks lack imported coverage points")
        if plan_feedback["stale_point_mappings"]:
            closure["policy_failures"].append("coverage points reference unknown plan checks")
        closure["policy_failures"] = list(dict.fromkeys(closure["policy_failures"]))
        closure["passed"] = not closure["policy_failures"]
        payload["passed"] = all(gate["passed"] for gate in gates) and closure["passed"]
    if parameter_sweeps["present"] and not parameter_sweeps["passed"]:
        closure["policy_failures"].append("parameter-sweep cross-point coverage is incomplete")
        closure["policy_failures"] = list(dict.fromkeys(closure["policy_failures"]))
        closure["passed"] = False
        payload["passed"] = False
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(markdown_path, _coverage_markdown(payload))
    atomic_write_text(yaml_path, _yaml_dump(payload))
    atomic_write_text(sarif_path, json.dumps(_coverage_sarif(payload), indent=2, sort_keys=True) + "\n")
    return path, payload


def read_coverage_summary(config: CLIConfig) -> dict[str, Any] | None:
    """Read the current imported coverage summary if one exists."""

    path = config.work_dir / "coverage" / "summary.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _migrate_coverage_summary(payload) if isinstance(payload, dict) else None


def _migrate_coverage_summary(payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = int(payload.get("schema_version", MIN_READABLE_COVERAGE_SCHEMA_VERSION))
    if schema_version > COVERAGE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported coverage schema version {schema_version}; this build reads up to {COVERAGE_SCHEMA_VERSION}"
        )
    if schema_version < MIN_READABLE_COVERAGE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported coverage schema version {schema_version}; minimum readable version is "
            f"{MIN_READABLE_COVERAGE_SCHEMA_VERSION}"
        )
    migrated = dict(payload)
    if schema_version == 1:
        migrated.setdefault(
            "closure",
            {
                "present": False,
                "passed": True,
                "counts": {
                    **{state: 0 for state in CLOSURE_STATES},
                    "total": 0,
                    "eligible": 0,
                    "actionable": 0,
                },
                "raw_percentage": None,
                "closure_percentage": None,
                "traceability_complete": True,
                "points": [],
                "gaps": [],
                "unmapped_points": [],
                "stale_dispositions": [],
                "policy_failures": [],
            },
        )
        migrated.setdefault("closure_gaps", [])
        migrated.setdefault(
            "plan_feedback",
            {
                "plans_available": False,
                "plans_updated": 0,
                "mapped_checks": 0,
                "unmeasured_checks": [],
                "stale_point_mappings": [],
            },
        )
        migrated.setdefault("exports", {})
    if schema_version <= 2:
        migrated.setdefault(
            "parameter_sweeps",
            {"present": False, "passed": True, "configured_points": 0, "groups": [], "gaps": []},
        )
    migrated["schema_version"] = COVERAGE_SCHEMA_VERSION
    return migrated


def _parameter_sweep_coverage(config: CLIConfig, closure: dict[str, Any]) -> dict[str, Any]:
    """Aggregate semantic check outcomes across every configured elaboration point."""

    if not config.parameter_sweeps:
        return {"present": False, "passed": True, "configured_points": 0, "groups": [], "gaps": []}
    from dv_platform.analysis.plan_store import read_stored_plans

    plans_path = config.work_dir / "plans" / "plans.sqlite"
    plans = read_stored_plans(plans_path) if plans_path.is_file() else ()
    states_by_check = _coverage_states_by_check(closure)
    grouped: dict[str, list[Any]] = {}
    for plan in plans:
        design_unit = plan.design_unit or plan.module.split("__sweep_", 1)[0]
        grouped.setdefault(design_unit, []).append(plan)
    groups: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    for design_unit, group_plans in sorted(grouped.items()):
        group, group_gaps = _parameter_sweep_group(
            design_unit, group_plans, states_by_check, len(config.parameter_sweeps)
        )
        groups.append(group)
        gaps.extend(group_gaps)
    return {
        "present": True,
        "passed": bool(groups) and all(group["passed"] for group in groups),
        "configured_points": len(config.parameter_sweeps),
        "groups": groups,
        "gaps": gaps,
    }


def _coverage_states_by_check(closure: dict[str, Any]) -> dict[str, list[str]]:
    states_by_check: dict[str, list[str]] = {}
    for point in closure.get("points", ()):
        if not isinstance(point, dict):
            continue
        state = str(point.get("status", "uncovered"))
        for check_id in point.get("check_ids", ()):
            states_by_check.setdefault(str(check_id), []).append(state)
    return states_by_check


def _parameter_sweep_group(design_unit, group_plans, states_by_check, configured_points):
    semantic_checks: dict[tuple[str, str], dict[str, Any]] = {}
    for plan in group_plans:
        for check in plan.check_details:
            if not check.executable:
                continue
            statement = " ".join(check.statement.replace(plan.module, design_unit).split())
            statement = re.sub(r"\b\d+'([sS]?[hHbBoOdD][0-9a-fA-F_xzXZ]+)", r"'\1", statement)
            semantic_checks.setdefault((check.category, statement), {})[plan.module] = check
    cross_points, gaps = _sweep_cross_points(
        design_unit, group_plans, semantic_checks, states_by_check, configured_points
    )
    points = [
        {
            "module": plan.module,
            "specialization_id": plan.specialization_id,
            "parameters": {parameter.name: parameter.default_value for parameter in plan.parameters},
        }
        for plan in sorted(group_plans, key=lambda item: item.module)
    ]
    passed = len(points) == configured_points and bool(cross_points) and all(item["passed"] for item in cross_points)
    if len(points) != configured_points:
        gaps.append(
            {
                "design_unit": design_unit,
                "cross_point_id": "sweep-point-count",
                "reason": f"expected {configured_points} sweep points, found {len(points)}",
            }
        )
    return {"design_unit": design_unit, "passed": passed, "points": points, "cross_points": cross_points}, gaps


def _sweep_cross_points(design_unit, group_plans, semantic_checks, states_by_check, configured_points):
    closed = {"covered", "waived", "unreachable"}
    priority = {
        "failed": 0,
        "uncovered": 1,
        "unsupported": 2,
        "bounded_pass": 3,
        "covered": 4,
        "waived": 5,
        "unreachable": 6,
    }
    cross_points = []
    gaps = []
    for (category, statement), checks_by_module in sorted(semantic_checks.items()):
        results = []
        for plan in sorted(group_plans, key=lambda item: item.module):
            check = checks_by_module.get(plan.module)
            states = states_by_check.get(check.check_id, ()) if check is not None else ()
            state = (
                min(states, key=lambda item: priority.get(item, -1))
                if states
                else ("unmeasured" if check is not None else "missing_check")
            )
            results.append({"module": plan.module, "status": state})
        passed = len(results) == configured_points and all(item["status"] in closed for item in results)
        cross_id = hashlib.sha256(f"{design_unit}\0{category}\0{statement}".encode()).hexdigest()[:16]
        cross_point_id = f"sweep:{design_unit}:{cross_id}"
        cross_points.append(
            {
                "cross_point_id": cross_point_id,
                "category": category,
                "statement": statement,
                "passed": passed,
                "results": results,
            }
        )
        if not passed:
            gaps.append(
                {
                    "design_unit": design_unit,
                    "cross_point_id": cross_point_id,
                    "reason": "not every configured sweep point has closed evidence",
                }
            )
    return cross_points, gaps


for _legacy_class in (CoverageImporter,):
    _legacy_class.__module__ = "dv_platform.analysis.coverage"
del _legacy_class
