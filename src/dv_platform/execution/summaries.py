# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Simulation run command construction and execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, VerificationTarget
from dv_platform.core.paths import contained_path
from dv_platform.core.security import redact_value
from dv_platform.core.validation import validation_result_from_coverage


def discover_generated_modules(config: CLIConfig, target: VerificationTarget) -> tuple[str, ...]:
    """Return generated module names for one target in deterministic order."""

    if target == VerificationTarget.FORMAL:
        modules_dir = contained_path(config.output_dir, "formal", "modules")
    else:
        modules_dir = contained_path(config.output_dir, "simulation", str(target), "modules")
    if not modules_dir.is_dir():
        return ()
    return tuple(
        path.name
        for path in sorted(modules_dir.iterdir(), key=lambda item: item.name)
        if path.is_dir() and not path.name.startswith(".")
    )


def write_aggregate_run_summary(
    config: CLIConfig,
    target: VerificationTarget,
    module_summaries: tuple[dict[str, Any], ...],
) -> Path:
    """Write an aggregate summary for a target-level run."""

    if target == VerificationTarget.FORMAL:
        summary_path = config.work_dir / "runs" / "formal" / "summary.json"
    else:
        summary_path = config.work_dir / "runs" / "simulation" / str(target) / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    failed = tuple(summary for summary in module_summaries if int(summary["return_code"]) != 0)
    payload = {
        "target": str(target),
        "status": "passed" if not failed else "failed",
        "total": len(module_summaries),
        "passed": len(module_summaries) - len(failed),
        "failed": len(failed),
        "modules": list(module_summaries),
    }
    atomic_write_text(summary_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return summary_path


def _write_summary(
    run: SimulationRun,
    return_code: int,
    status: str,
    results: CocotbResults | None = None,
    native_results: NativeResults | None = None,
    results_error: str | None = None,
    validation_error: str | None = None,
    results_parse_status: str | None = None,
) -> None:
    traceability = _generated_traceability(run.generated_dir)
    trace_statuses = (
        _cocotb_trace_statuses(traceability, results)
        if run.target == VerificationTarget.COCOTB
        else _native_trace_statuses(traceability, native_results)
    )
    coverage = _verification_coverage(
        traceability,
        passed=(run.target == VerificationTarget.COCOTB and status == "passed" and return_code == 0),
        failed=(run.target == VerificationTarget.COCOTB and status == "failed" and return_code != 0),
        trace_statuses=trace_statuses,
    )
    triage = _triage(status, return_code, validation_error or results_error)
    validation_result = validation_result_from_coverage(
        run.module, run.target, status, return_code, coverage["entries"]
    )
    payload = {
        "schema_version": 1,
        "target": str(run.target),
        "module": run.module,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "timeout_seconds": run.timeout_seconds,
        "max_process_memory_mb": run.config.max_process_memory_mb,
        "max_output_bytes": run.config.max_output_bytes,
        "return_code": return_code,
        "status": status,
        "stdout_log": str(run.stdout_log),
        "stderr_log": str(run.stderr_log),
        "runner_script": str(run.runner_script) if run.runner_script is not None else None,
        "generated_artifact": str(_generated_test_path(run)) if run.target == VerificationTarget.COCOTB else None,
        "provenance_manifest": str(run.generated_dir / "provenance.json"),
        "provenance_sha256": _provenance_sha256(run.generated_dir),
        "results_xml": str(run.run_dir / "results.xml") if run.target == VerificationTarget.COCOTB else None,
        "results": results.as_dict() if results is not None else None,
        "native_results": native_results.as_dict() if native_results is not None else None,
        "results_parse_status": results_parse_status,
        "results_error": results_error,
        "validation_error": validation_error,
        "tool_qualification": _simulation_tool_qualification(run),
        "traceability": traceability,
        "failure_traceability": [record for record in coverage["entries"] if record.get("status") == "failed"],
        "verification_coverage": coverage,
        "validation_result": validation_result.to_json(),
        "coverage_points": _normalized_coverage_points(run.module, run.target, coverage),
        "triage": triage,
        "repair_suggestions": _repair_suggestions(triage["category"], run.target, run.module),
        "stdout_tail": _text_tail(run.stdout_log),
        "stderr_tail": _text_tail(run.stderr_log),
    }
    atomic_write_text(
        run.summary_path,
        json.dumps(redact_value(run.config, payload), indent=2, sort_keys=True) + "\n",
    )


def _generated_traceability(generated_dir: Path) -> list[dict[str, Any]]:
    provenance_path = generated_dir / "provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    records: dict[str, dict[str, Any]] = {}
    for artifact in provenance.get("artifacts", ()) if isinstance(provenance, dict) else ():
        if not isinstance(artifact, dict):
            continue
        for trace in artifact.get("traceability", ()):
            if not isinstance(trace, dict) or not isinstance(trace.get("trace_id"), str):
                continue
            record = dict(trace)
            record["generated_artifact"] = str(generated_dir / str(artifact.get("path", "")))
            records.setdefault(str(trace["trace_id"]), record)
    return [records[key] for key in sorted(records)]


def _verification_coverage(
    traceability: list[dict[str, Any]],
    *,
    passed: bool,
    failed: bool,
    trace_statuses: dict[str, str] | None = None,
    check_statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    status = "passed" if passed else "failed" if failed else "unexecuted"
    entries_by_id: dict[str, dict[str, Any]] = {}
    status_rank = {"unexecuted": 0, "passed": 1, "bounded_pass": 2, "unsupported": 3, "failed": 4}
    for record in traceability:
        trace_id = str(record.get("trace_id", ""))
        record_status = (trace_statuses or {}).get(trace_id, status)
        check_ids = tuple(str(item) for item in record.get("check_ids", ()) if item)
        check_indexes = tuple(int(item) for item in record.get("check_indexes", ()) if isinstance(item, int))
        outcome_ids = tuple(f"check:{item}" for item in check_ids)
        if not outcome_ids:
            outcome_ids = tuple(f"legacy-check:{item}" for item in check_indexes) or (f"trace:{trace_id}",)
        for outcome_id in outcome_ids:
            check_id = outcome_id.removeprefix("check:") if outcome_id.startswith("check:") else None
            outcome_status = (check_statuses or {}).get(check_id, record_status) if check_id else record_status
            existing = entries_by_id.get(outcome_id)
            entry = {
                **record,
                "outcome_id": outcome_id,
                "check_id": check_id,
                "status": outcome_status,
            }
            if existing is None or status_rank[outcome_status] > status_rank[str(existing["status"])]:
                entries_by_id[outcome_id] = entry
    entries = [entries_by_id[key] for key in sorted(entries_by_id)]
    passed_count = sum(1 for entry in entries if entry["status"] == "passed")
    failed_count = sum(1 for entry in entries if entry["status"] == "failed")
    unexecuted_count = sum(1 for entry in entries if entry["status"] == "unexecuted")
    bounded_count = sum(1 for entry in entries if entry["status"] == "bounded_pass")
    unsupported_count = sum(1 for entry in entries if entry["status"] == "unsupported")
    return {
        "complete": bool(entries) and unexecuted_count == 0 and unsupported_count == 0,
        "closure_complete": bool(entries) and not (unexecuted_count or bounded_count or unsupported_count),
        "total": len(entries),
        "passed": passed_count,
        "failed": failed_count,
        "unexecuted": unexecuted_count,
        "bounded_pass": bounded_count,
        "unsupported": unsupported_count,
        "entries": entries,
    }


def _normalized_coverage_points(
    module: str,
    target: VerificationTarget,
    coverage: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert per-check execution outcomes into the normalized closure schema."""

    status_map = {
        "passed": "covered",
        "failed": "failed",
        "unexecuted": "uncovered",
        "bounded_pass": "bounded_pass",
        "unsupported": "unsupported",
    }
    points: list[dict[str, Any]] = []
    for entry in coverage.get("entries", ()):
        if not isinstance(entry, dict):
            continue
        outcome_id = str(entry.get("outcome_id") or entry.get("trace_id") or "unknown")
        execution_status = str(entry.get("status", "unexecuted"))
        point = {
            "module": module,
            "point_id": f"{target}:{module}:{outcome_id}",
            "kind": "formal" if target == VerificationTarget.FORMAL else "functional",
            "status": status_map.get(execution_status, "uncovered"),
            "hits": 1 if execution_status in {"passed", "failed", "bounded_pass"} else 0,
            "check_ids": [str(entry["check_id"])] if entry.get("check_id") else [],
            "requirement_ids": sorted({str(item) for item in entry.get("requirement_ids", ()) if item}),
            "behavior_ids": sorted({str(item) for item in entry.get("behavior_ids", ()) if item}),
            "source_locator": str(entry.get("generated_symbol") or entry.get("trace_id") or outcome_id),
        }
        points.append(point)
    return points


def _triage(status: str, return_code: int, detail: str | None) -> dict[str, str]:
    normalized_detail = (detail or "").lower()
    if status in {"missing_artifacts", "invalid_artifacts", "missing_manifest"}:
        category = "generation_or_state"
        rationale = "Generated collateral or its input state is missing, stale, or invalid."
    elif status == "timeout":
        category = "tool_or_complexity"
        rationale = "The configured tool did not complete within the run budget."
    elif "parse" in normalized_detail or "syntax" in normalized_detail or "compile" in normalized_detail:
        category = "generation_or_tooling"
        rationale = "The tool reported a parse, syntax, or compilation failure."
    elif status == "failed" or return_code != 0:
        category = "rtl_or_requirement_mismatch"
        rationale = "Validated executable checks disagree with the observed RTL behavior."
    else:
        category = "none"
        rationale = "No failure requires triage."
    return {"category": category, "rationale": rationale}


def _repair_suggestions(category: str, target: VerificationTarget, module: str) -> list[str]:
    if category == "generation_or_state":
        return [f"Re-run analyze-rtl, plan, and generate for {target}/{module} before executing again."]
    if category == "generation_or_tooling":
        return ["Inspect the generated artifact, execution manifest, and tool log before changing RTL intent."]
    if category == "tool_or_complexity":
        return ["Inspect progress logs and proof/simulation depth before increasing the timeout."]
    if category == "rtl_or_requirement_mismatch":
        return ["Compare the failed trace IDs with their plan requirements and RTL evidence before regenerating."]
    return []


def _provenance_sha256(generated_dir: Path) -> str | None:
    provenance_path = generated_dir / "provenance.json"
    if not provenance_path.is_file():
        return None
    try:
        return hashlib.sha256(provenance_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _text_tail(path: Path, max_lines: int = 20) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
