# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dv_platform.analysis.revisions import read_revisions, revision_state_path
from dv_platform.core.models import CLIConfig, VerificationTarget


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
        records.append(
            _revision_record(config, module, revision, generated_by_key, run_summaries, coverage, coverage_sources)
        )
    open_count = sum(item["state"] not in {"closed", "no-op"} for item in records)
    return {"schema_version": 1, "open": open_count, "records": records}


def _revision_record(config, module, revision, generated_by_key, run_summaries, coverage, coverage_sources):
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
        return record
    if not revision.required_rerun_targets:
        record["reason"] = "affected revision has no executable rerun target"
        return record
    path = revision_state_path(config.work_dir, revision.revision_id)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        record["reason"] = f"revision generation state is unavailable: {error}"
        return record
    targets = state.get("generated_targets") if isinstance(state, dict) else None
    if (
        not isinstance(targets, dict)
        or state.get("resulting_plan_hash") != revision.resulting_plan_hash
        or state.get("module") != module
    ):
        record["reason"] = "revision generation state does not match its immutable snapshot"
        return record
    generation_valid, matching_runs = _matching_revision_runs(
        module, revision, targets, generated_by_key, run_summaries
    )
    if not generation_valid:
        record["reason"] = "one or more required targets were not generated from this revision"
        return record
    if len(matching_runs) != len(revision.required_rerun_targets):
        record["state"] = "pending_run"
        record["reason"] = "one or more required targets lack a passing provenance-matched rerun"
        return record
    record["run_summaries"] = [str(item["path"]) for item in matching_runs]
    if not _revision_coverage_closed(coverage, coverage_sources, matching_runs):
        record["state"] = "pending_coverage"
        record["reason"] = "coverage was not rebuilt from every required fresh rerun"
        return record
    record["state"] = "closed"
    return record


def _matching_revision_runs(module, revision, targets, generated_by_key, run_summaries):
    matching_runs: list[dict[str, Any]] = []
    for target in revision.required_rerun_targets:
        target_state = targets.get(target)
        current = generated_by_key.get((target, module))
        if (
            not isinstance(target_state, dict)
            or not isinstance(current, dict)
            or target_state.get("provenance_sha256") != current.get("provenance_sha256")
        ):
            return False, matching_runs
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
        if run is not None and run.get("status") in {"pass", "passed"} and bool(run.get("coverage_complete")):
            matching_runs.append(run)
    return True, matching_runs


def _revision_coverage_closed(coverage, coverage_sources, matching_runs):
    return (
        isinstance(coverage, dict)
        and bool(coverage.get("passed"))
        and all(str(Path(str(item["path"])).resolve()) in coverage_sources for item in matching_runs)
    )
