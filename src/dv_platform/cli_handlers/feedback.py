# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dv_platform.core.models import CLIConfig, VerificationTarget

if TYPE_CHECKING:
    from dv_platform.analysis.ai_feedback import propose_feedback_operations
    from dv_platform.analysis.ai_gateway import LiteLLMGateway
    from dv_platform.analysis.ai_scenarios import synthesize_scenario_selections
    from dv_platform.analysis.feedback import normalize_feedback
    from dv_platform.analysis.plan_store import read_stored_plans
    from dv_platform.analysis.revisions import (
        create_feedback_revision,
        read_revision_plan,
        read_revisions,
    )


def _feedback(args: argparse.Namespace, config: CLIConfig) -> int:
    plans_db = config.work_dir / "plans" / "plans.sqlite"
    if not plans_db.is_file():
        _emit_error(args, "feedback", "missing_plans", f"Plans are missing; run plan first: {plans_db}")
        return 2
    try:
        plans = read_stored_plans(plans_db)
        selected = tuple(plan for plan in plans if args.all or plan.module == args.module)
        if not selected:
            _emit_error(args, "feedback", "module_not_found", "No stored plan matches the requested module.")
            return 2
        input_paths = tuple(args.input or ())
        if args.from_runs:
            input_paths = tuple(dict.fromkeys((*input_paths, *_feedback_run_summaries(config))))
        records = _load_feedback_records(input_paths)
        target = VerificationTarget(args.target)
        revisions = []
        ai_results: list[Any] = []
        for plan in selected:
            revision, results = _feedback_revision(args, config, plan, records, target)
            revisions.append(revision)
            ai_results.extend(results)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(args, "feedback", "feedback_failed", str(error))
        return 2
    _emit_success(
        args,
        "feedback",
        {
            "modules": len(revisions),
            "dry_run": args.dry_run,
            "revisions": [revision.revision_id for revision in revisions],
            "ai": [
                {
                    "purpose": result.stage,
                    "status": result.status,
                    "attempts": result.attempts,
                    "fallback_reason": result.fallback_reason,
                    "run_record": str(result.run_record_path) if result.run_record_path is not None else None,
                }
                for result in ai_results
            ],
        },
        (
            "command=feedback",
            f"modules={len(revisions)}",
            f"dry_run={str(args.dry_run).lower()}",
            *(f"revision={revision.revision_id}" for revision in revisions),
        ),
    )
    return 0


def _load_feedback_records(paths: tuple[Path, ...]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records.extend(item for item in payload if isinstance(item, dict))
            continue
        if not isinstance(payload, dict):
            continue
        validation = payload.get("validation_result")
        checks = (
            validation.get("checks", ())
            if isinstance(validation, dict)
            else payload.get("checks", payload.get("results", ()))
        )
        if isinstance(checks, list):
            records.extend(
                {**item, "module": item.get("module", payload.get("module"))}
                for item in checks
                if isinstance(item, dict)
            )
        records.extend(_nested_feedback_records(payload))
    return records


def _nested_feedback_records(payload: dict[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    modules = payload.get("modules", ())
    if not isinstance(modules, list):
        return records
    for summary in modules:
        if not isinstance(summary, dict):
            continue
        validation = summary.get("validation_result")
        checks = validation.get("checks", ()) if isinstance(validation, dict) else ()
        if isinstance(checks, list):
            records.extend(
                {**item, "module": item.get("module", summary.get("module"))}
                for item in checks
                if isinstance(item, dict)
            )
    return records


def _feedback_revision(
    args: argparse.Namespace,
    config: CLIConfig,
    plan: Any,
    records: list[dict[str, object]],
    target: VerificationTarget,
) -> tuple[Any, tuple[Any, ...]]:
    plan_revisions = read_revisions(config.work_dir, plan.module)
    revision_context = read_revision_plan(config.work_dir, plan_revisions[-1].revision_id) if plan_revisions else None
    context_plan = revision_context or plan
    scoped = tuple(record for record in records if not record.get("module") or record.get("module") == plan.module)
    if not scoped:
        scoped = tuple({"check_id": check.check_id, "outcome": "unexecuted"} for check in context_plan.check_details)
    events = normalize_feedback(scoped, target=target, module=plan.module, source_run="cli-feedback")
    proposals: tuple[Any, ...] = ()
    evidence_ids: set[str] | None = None
    results: list[Any] = []
    if args.ai:
        proposals, evidence_ids, gateway_result = propose_feedback_operations(
            LiteLLMGateway(config), context_plan, events
        )
        results.append(gateway_result)
    selections: tuple[Any, ...] = ()
    if args.ai and "scenario_synthesis" in config.ai.allowed_stages:
        selections, synthesis_result = synthesize_scenario_selections(LiteLLMGateway(config), context_plan)
        results.append(synthesis_result)
    selected_ids = tuple(selection.scenario_id for selection in selections)
    revision = create_feedback_revision(
        config.work_dir,
        plan,
        events,
        dry_run=args.dry_run,
        proposals=proposals,
        evidence_ids=evidence_ids,
        model=config.ai.model if args.ai else None,
        fork_on_input_change=args.fork_input_change,
        selected_scenario_ids=selected_ids,
        scenario_selections=tuple((selection.scenario_id, selection.parameters) for selection in selections),
        affected_artifact_paths=_known_affected_artifact_paths(config, context_plan, events, selected_ids),
    )
    return revision, tuple(results)


def _known_affected_artifact_paths(
    config: CLIConfig,
    plan: Any,
    events: tuple[Any, ...],
    selected_scenario_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve already-generated artifact dependencies for revision metadata."""

    check_ids = {
        event.check_id for event in events if event.outcome not in {"pass", "passed"} and event.check_id is not None
    }
    requirement_ids = {
        event.requirement_id
        for event in events
        if event.outcome not in {"pass", "passed"} and event.requirement_id is not None
    }
    for scenario in plan.scenarios:
        if scenario.scenario_id in selected_scenario_ids:
            check_ids.update(scenario.check_ids)
            requirement_ids.update(scenario.requirement_ids)
    paths = {path for event in events if event.outcome not in {"pass", "passed"} for path in event.affected_artifacts}
    for target in plan.targets:
        module_dir = (
            config.output_dir / "formal" / "modules" / plan.module
            if target == VerificationTarget.FORMAL
            else config.output_dir / "simulation" / target.value / "modules" / plan.module
        )
        provenance_path = module_dir / "provenance.json"
        if not provenance_path.is_file():
            continue
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        artifacts = provenance.get("artifacts", ()) if isinstance(provenance, dict) else ()
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
                continue
            traces = artifact.get("traceability", ())
            if not isinstance(traces, list):
                continue
            if any(
                isinstance(trace, dict)
                and (
                    check_ids.intersection(str(value) for value in trace.get("check_ids", ()))
                    or requirement_ids.intersection(str(value) for value in trace.get("requirement_ids", ()))
                )
                for trace in traces
            ):
                paths.add(str(artifact["path"]))
    return tuple(sorted(paths))


def _feedback_run_summaries(config: CLIConfig) -> tuple[Path, ...]:
    runs_dir = config.work_dir / "runs"
    if not runs_dir.is_dir():
        return ()
    return tuple(sorted(runs_dir.rglob("summary.json"), key=lambda item: item.as_posix()))
