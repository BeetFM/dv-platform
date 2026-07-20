"""Reconcile imported coverage closure with canonical verification plans."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
from dv_platform.core.models import CLIConfig, EvidenceKind, EvidenceRef, VerificationCheck, VerificationPlan

_STATUS_PRIORITY = {
    "failed": 0,
    "uncovered": 1,
    "unmeasured": 2,
    "waived": 3,
    "unreachable": 4,
    "covered": 5,
    "excluded": 6,
}


def apply_coverage_feedback_to_stored_plans(
    config: CLIConfig,
    coverage_summary: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    """Attach point closure to stable checks and republish canonical plans."""

    plans_path = config.work_dir / "plans" / "plans.sqlite"
    if not plans_path.is_file():
        return {
            "plans_available": False,
            "plans_updated": 0,
            "mapped_checks": 0,
            "unmeasured_checks": [],
            "stale_point_mappings": [],
        }

    plans = read_stored_plans(plans_path)
    points = coverage_summary.get("closure", {}).get("points", ())
    updated: list[VerificationPlan] = []
    mapped_checks = 0
    unmeasured_checks: list[dict[str, str]] = []
    stale_point_mappings: list[dict[str, str]] = []
    for plan in plans:
        reconciled, plan_mapped, plan_unmeasured, plan_stale = _apply_plan_feedback(plan, points, summary_path)
        updated.append(reconciled)
        mapped_checks += plan_mapped
        unmeasured_checks.extend(plan_unmeasured)
        stale_point_mappings.extend(plan_stale)

    changed = tuple(updated) != plans
    if changed:
        write_plan_outputs(config, tuple(updated), strict=config.strict or config.ci)
    return {
        "plans_available": True,
        "plans_updated": len(updated) if changed else 0,
        "mapped_checks": mapped_checks,
        "unmeasured_checks": unmeasured_checks,
        "stale_point_mappings": stale_point_mappings,
    }


def _apply_plan_feedback(
    plan: VerificationPlan,
    raw_points: object,
    summary_path: Path,
) -> tuple[VerificationPlan, int, list[dict[str, str]], list[dict[str, str]]]:
    module_points = (
        tuple(point for point in raw_points if isinstance(point, dict) and str(point.get("module")) == plan.module)
        if isinstance(raw_points, (list, tuple))
        else ()
    )
    if not module_points:
        return plan, 0, [], []

    by_check: dict[str, list[dict[str, Any]]] = {}
    for point in module_points:
        for check_id in point.get("check_ids", ()):
            by_check.setdefault(str(check_id), []).append(point)

    known_check_ids = {check.check_id for check in plan.check_details}
    stale = [
        {"module": plan.module, "point_id": str(point["point_id"]), "check_id": str(check_id)}
        for point in module_points
        for check_id in point.get("check_ids", ())
        if str(check_id) not in known_check_ids
    ]
    unmeasured: list[dict[str, str]] = []
    checks: list[VerificationCheck] = []
    mapped = 0
    for check in plan.check_details:
        mapped_points = by_check.get(check.check_id, ())
        if mapped_points:
            mapped += 1
            point_ids = tuple(sorted({str(point["point_id"]) for point in mapped_points}))
            status = _combined_status(tuple(str(point["status"]) for point in mapped_points))
            refs = tuple(_point_evidence_ref(summary_path, plan.module, point_id, status) for point_id in point_ids)
            checks.append(
                replace(
                    check,
                    closure_status=status,
                    coverage_point_ids=point_ids,
                    evidence_refs=tuple(dict.fromkeys((*check.evidence_refs, *refs))),
                )
            )
        elif check.executable:
            unmeasured.append({"module": plan.module, "check_id": check.check_id})
            checks.append(replace(check, closure_status="unmeasured", coverage_point_ids=()))
        else:
            checks.append(check)

    questions = list(plan.open_questions)
    for item in unmeasured:
        question = (
            f"Executable check {item['check_id']} has no imported coverage point; map generated execution evidence."
        )
        if question not in questions:
            questions.append(question)
    for item in stale:
        question = f"Coverage point {item['point_id']} maps to unknown check {item['check_id']}; regenerate or migrate the report."
        if question not in questions:
            questions.append(question)
    return replace(plan, check_details=tuple(checks), open_questions=tuple(questions)), mapped, unmeasured, stale


def _combined_status(statuses: tuple[str, ...]) -> str:
    return min(statuses, key=lambda status: _STATUS_PRIORITY.get(status, -1))


def _point_evidence_ref(summary_path: Path, module: str, point_id: str, status: str) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind.TOOL_LOG,
        source_id=str(summary_path),
        locator=f"coverage-point:{module}.{point_id}",
        summary=f"Imported coverage status: {status}",
    )
