# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Simulation run command construction and execution."""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, FormalToolConfig, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.security import append_audit_event, redact_value
from dv_platform.core.tool_versions import (
    formal_dependency_qualifications,
    probe_tool_version,
)
from dv_platform.core.validation import validation_result_from_coverage
from dv_platform.generators.artifacts import EXECUTION_MANIFEST_NAME, validate_generated_directory


@dataclass(frozen=True)
class FormalResults:
    """Parsed SymbiYosys result status from run output."""

    formal_status: str = "unknown"
    engine_status: dict[str, str] | None = None
    task_status: dict[str, str] | None = None
    proof_method: str | None = None
    formal_error: str | None = None
    trace_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "formal_status": self.formal_status,
            "engine_status": self.engine_status or {},
            "task_status": self.task_status or {},
            "proof_method": self.proof_method,
            "formal_error": self.formal_error,
            "trace_paths": list(self.trace_paths),
        }


@dataclass(frozen=True)
class FormalRun:
    """Prepared formal run paths and command."""

    module: str
    config: CLIConfig
    tool: FormalToolConfig
    command: tuple[str, ...]
    generated_dir: Path
    run_dir: Path
    command_path: Path
    stdout_log: Path
    stderr_log: Path
    summary_path: Path
    run_sby: Path
    timeout_seconds: float = 120.0


def prepare_formal_run(
    config: CLIConfig,
    tool: FormalToolConfig,
    module: str,
    timeout_seconds: float = 120.0,
) -> FormalRun:
    """Build deterministic run paths and command for one generated formal module."""

    module = validate_path_component(module, "run module")
    generated_dir = contained_path(config.output_dir, "formal", "modules", module)
    run_dir = contained_path(config.work_dir, "runs", "formal", module)
    run_sby = run_dir / f"{_safe_identifier(module)}.sby"
    command_prefix = tuple(shlex.split(tool.command))
    if not command_prefix:
        raise ValueError(f"Formal tool command is empty for {tool.name}")
    if Path(command_prefix[0]).name == "sby":
        if "-f" not in command_prefix:
            command_prefix = (*command_prefix, "-f")
        # SBY otherwise launches prove and cover concurrently. A formal
        # module already launches heavyweight solver processes, so sequential
        # task execution keeps peak memory predictable.
        if "--sequential" not in command_prefix:
            command_prefix = (*command_prefix, "--sequential")
    command = (*command_prefix, str(run_sby))
    return FormalRun(
        module=module,
        config=config,
        tool=tool,
        command=command,
        generated_dir=generated_dir,
        run_dir=run_dir,
        command_path=run_dir / "command.json",
        stdout_log=run_dir / "stdout.log",
        stderr_log=run_dir / "stderr.log",
        summary_path=run_dir / "summary.json",
        run_sby=run_sby,
        timeout_seconds=timeout_seconds,
    )


def execute_formal_run(config: CLIConfig, run: FormalRun) -> int:
    """Execute one prepared formal run and persist command, logs, and summary."""

    run.run_dir.mkdir(parents=True, exist_ok=True)
    append_audit_event(config, "formal.start", {"module": run.module, "command": list(run.command)})
    _write_formal_command(run)
    if not run.generated_dir.is_dir():
        _write_formal_summary(run, return_code=2, status="missing_artifacts")
        return 2
    manifest_path = config.work_dir / "project-manifest.json"
    if not manifest_path.is_file():
        _write_formal_summary(
            run,
            return_code=2,
            status="missing_manifest",
            validation_error=f"Project manifest is missing; run analyze-rtl first: {manifest_path}",
        )
        return 2
    try:
        validate_generated_directory(VerificationTarget.FORMAL, run.module, run.generated_dir)
    except ValueError as error:
        _write_formal_summary(run, return_code=2, status="invalid_artifacts", validation_error=str(error))
        return 2

    _write_run_sby(run)
    completed = _run_bounded_process(
        run.command,
        cwd=run.run_dir,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout_seconds=run.timeout_seconds,
        stdout_path=run.stdout_log,
        stderr_path=run.stderr_log,
        max_output_bytes=config.max_output_bytes,
        memory_limit_mb=config.max_process_memory_mb,
        config=config,
    )
    run.stdout_log.write_text(
        _redact_process_output(config, completed.stdout, completed.stdout_truncated, "stdout"),
        encoding="utf-8",
    )
    stderr = _redact_process_output(config, completed.stderr, completed.stderr_truncated, "stderr")
    if completed.timed_out:
        stderr += f"\nFormal run timed out after {run.timeout_seconds:g} seconds.\n"
        _write_formal_summary(run, return_code=124, status="timeout")
        append_audit_event(config, "formal.finish", {"module": run.module, "return_code": 124})
        run.stderr_log.write_text(stderr, encoding="utf-8")
        return 124
    run.stderr_log.write_text(stderr, encoding="utf-8")
    formal_results = parse_formal_results(completed.stdout + "\n" + completed.stderr)
    effective_return_code = completed.returncode
    if effective_return_code == 0 and formal_results.formal_status != "pass":
        effective_return_code = 1
    _write_formal_summary(
        run,
        return_code=effective_return_code,
        status="passed" if effective_return_code == 0 else "failed",
        formal_results=formal_results,
    )
    append_audit_event(config, "formal.finish", {"module": run.module, "return_code": effective_return_code})
    return effective_return_code


def _write_formal_command(run: FormalRun) -> None:
    payload = {
        "target": str(VerificationTarget.FORMAL),
        "module": run.module,
        "tool": run.tool.name,
        "tool_command": run.tool.command,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "run_sby": str(run.run_sby),
        "timeout_seconds": run.timeout_seconds,
        "max_process_memory_mb": run.config.max_process_memory_mb,
        "max_output_bytes": run.config.max_output_bytes,
    }
    atomic_write_text(
        run.command_path,
        json.dumps(redact_value(run.config, payload), indent=2, sort_keys=True) + "\n",
    )


def _write_formal_summary(
    run: FormalRun,
    return_code: int,
    status: str,
    validation_error: str | None = None,
    formal_results: FormalResults | None = None,
) -> None:
    parsed_results = formal_results or FormalResults()
    traceability = _generated_traceability(run.generated_dir)
    cdc_verification = _formal_cdc_verification(run, parsed_results)
    coverage = _verification_coverage(
        traceability,
        passed=status == "passed" and return_code == 0 and parsed_results.formal_status == "pass",
        failed=status == "failed" and return_code != 0,
        check_statuses=_formal_check_statuses(run, parsed_results, cdc_verification),
    )
    triage = _triage(status, return_code, validation_error or parsed_results.formal_error)
    validation_result = validation_result_from_coverage(
        run.module, VerificationTarget.FORMAL, status, return_code, coverage["entries"]
    )
    payload = {
        "schema_version": 1,
        "target": str(VerificationTarget.FORMAL),
        "module": run.module,
        "tool": run.tool.name,
        "tool_command": run.tool.command,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "run_sby": str(run.run_sby),
        "generated_harness": str(run.generated_dir / f"formal_{_safe_identifier(run.module)}.sv"),
        "generated_sby": str(run.generated_dir / f"{_safe_identifier(run.module)}.sby"),
        "provenance_manifest": str(run.generated_dir / "provenance.json"),
        "provenance_sha256": _provenance_sha256(run.generated_dir),
        "timeout_seconds": run.timeout_seconds,
        "max_process_memory_mb": run.config.max_process_memory_mb,
        "max_output_bytes": run.config.max_output_bytes,
        "return_code": return_code,
        "status": status,
        "stdout_log": str(run.stdout_log),
        "stderr_log": str(run.stderr_log),
        "validation_error": validation_error,
        "tool_qualification": probe_tool_version(run.tool.command),
        "tool_dependencies": list(formal_dependency_qualifications(run.tool.command)),
        "formal_status": parsed_results.formal_status,
        "engine_status": parsed_results.engine_status or {},
        "task_status": parsed_results.task_status or {},
        "proof_method": parsed_results.proof_method,
        "formal_error": parsed_results.formal_error,
        "cdc_verification": cdc_verification,
        "trace_paths": _formal_trace_paths(run, parsed_results.trace_paths),
        "traceability": traceability,
        "failure_traceability": traceability if return_code != 0 else [],
        "verification_coverage": coverage,
        "validation_result": validation_result.to_json(),
        "formal_points": _normalized_coverage_points(run.module, VerificationTarget.FORMAL, coverage),
        "triage": triage,
        "repair_suggestions": _repair_suggestions(triage["category"], VerificationTarget.FORMAL, run.module),
        "stdout_tail": _text_tail(run.stdout_log),
        "stderr_tail": _text_tail(run.stderr_log),
    }
    atomic_write_text(
        run.summary_path,
        json.dumps(redact_value(run.config, payload), indent=2, sort_keys=True) + "\n",
    )


def _formal_check_statuses(
    run: FormalRun,
    results: FormalResults,
    cdc_verification: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Attribute prove and cover task results to their corresponding stable checks."""

    task_status = results.task_status or {}
    if not task_status:
        return None
    plans_path = run.config.work_dir / "plans" / "plans.sqlite"
    if not plans_path.is_file():
        return None
    try:
        plan = next((item for item in read_stored_plans(plans_path) if item.module == run.module), None)
    except (OSError, ValueError):
        return None
    if plan is None:
        return None
    normalized = {"pass": "passed", "fail": "failed", "error": "failed", "unknown": "unexecuted"}
    statuses: dict[str, str] = {}
    for check in plan.check_details:
        if not check.executable and check.category != "cdc":
            continue
        if check.category == "cdc":
            paths = (cdc_verification or {}).get("paths", ())
            matching = [
                item
                for item in paths
                if isinstance(item, dict)
                and (
                    str(item.get("signal", "")).lower() in check.statement.lower()
                    or str(item.get("path_id", "")).lower() in check.statement.lower()
                )
            ]
            outcomes = [str(item.get("outcome_status", "unsupported")) for item in matching]
            rank = {"passed": 0, "unexecuted": 1, "bounded_pass": 2, "unsupported": 3, "failed": 4}
            statuses[check.check_id] = max(outcomes, key=lambda item: rank.get(item, 3)) if outcomes else "unsupported"
            continue
        task = "cover" if check.statement.lower().startswith("cover ") else "prove"
        if task in task_status:
            statuses[check.check_id] = normalized.get(task_status[task], "unexecuted")
    return statuses


def _formal_cdc_verification(run: FormalRun, results: FormalResults) -> dict[str, Any]:
    path = run.generated_dir / f"formal_{_safe_identifier(run.module)}_cdc.json"
    if not path.is_file():
        return {"present": False, "policy": "fail-closed", "closure_complete": False, "paths": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "present": True,
            "policy": "fail-closed",
            "closure_complete": False,
            "error": f"Invalid CDC evidence report: {error}",
            "paths": [],
        }
    raw_paths = payload.get("paths", ()) if isinstance(payload, dict) else ()
    if not isinstance(raw_paths, list):
        raw_paths = []
    task_status = results.task_status or {}
    paths: list[dict[str, Any]] = []
    for raw in raw_paths:
        if not isinstance(raw, dict):
            continue
        level = str(raw.get("evidence_level", "unsupported"))
        task = str(raw.get("formal_task")) if raw.get("formal_task") else None
        observed = task_status.get(task, "unknown") if task else "unsupported"
        if level == "unsupported":
            outcome = "unsupported"
        elif observed in {"fail", "error"}:
            outcome = "failed"
        elif observed != "pass":
            outcome = "unexecuted"
        elif level == "bounded":
            outcome = "bounded_pass"
        else:
            outcome = "passed"
        paths.append({**raw, "task_status": observed, "outcome_status": outcome})
    return {
        "present": True,
        "policy": str(payload.get("policy", "fail-closed")) if isinstance(payload, dict) else "fail-closed",
        "bounded_depth": payload.get("bounded_depth") if isinstance(payload, dict) else None,
        "closure_complete": bool(paths) and all(item["outcome_status"] == "passed" for item in paths),
        "paths": paths,
    }


def _write_run_sby(run: FormalRun) -> None:
    manifest = json.loads((run.generated_dir / EXECUTION_MANIFEST_NAME).read_text(encoding="utf-8"))
    project = manifest["project"]
    hdl_files = tuple(Path(str(item["path"])) for item in project.get("hdl_files", ()))
    harness_path = run.generated_dir / f"formal_{_safe_identifier(run.module)}.sv"
    include_options = [f"-I{_yosys_quote(str(path))}" for path in project.get("include_paths", ())]
    define_options = [f"-D{_yosys_quote(str(item))}" for item in project.get("defines", ())]
    read_options = " ".join(("read -formal -sv", *include_options, *define_options))
    generated_sby = run.generated_dir / f"{_safe_identifier(run.module)}.sby"
    generated_content = generated_sby.read_text(encoding="utf-8")
    if "[script]" not in generated_content or "[files]" not in generated_content:
        generated_content = "\n".join(
            (
                "[tasks]",
                "prove",
                "cover",
                "",
                "[options]",
                "prove: mode prove",
                "cover: mode cover",
                "depth 20",
                "",
                "[engines]",
                "smtbmc z3",
                "",
                "[script]",
                "",
                "[files]",
                "",
            )
        )
    bounded_cdc = "cdc_bmc" in generated_content
    source_paths = (*hdl_files, harness_path)
    if bounded_cdc:
        source_lines = [
            f"{task}: {options} {_yosys_quote(str(path))}"
            for task, options in (
                ("prove", read_options),
                ("cover", read_options),
                ("cdc_bmc", f"{read_options} -DDV_CDC_BOUNDED"),
            )
            for path in source_paths
        ]
    else:
        source_lines = [f"{read_options} {_yosys_quote(str(path))}" for path in source_paths]
    source_lines.append(f"prep -top formal_{_safe_identifier(run.module)}")
    file_lines = [str(path) for path in hdl_files]
    file_lines.append(str(harness_path))
    atomic_write_text(
        run.run_sby,
        _replace_sby_section(
            _replace_sby_section(generated_content, "script", source_lines),
            "files",
            file_lines,
        ),
    )


def _replace_sby_section(content: str, section: str, lines: list[str]) -> str:
    source = content.splitlines()
    header = f"[{section}]"
    start = source.index(header)
    end = next((index for index in range(start + 1, len(source)) if source[index].startswith("[")), len(source))
    replacement = [header, *lines, ""]
    return "\n".join((*source[:start], *replacement, *source[end:])).rstrip() + "\n"


def parse_formal_results(output: str) -> FormalResults:
    """Parse coarse SymbiYosys status fields from combined process output."""

    observed_statuses: set[str] = set()
    engine_status: dict[str, str] = {}
    task_status: dict[str, str] = {}
    proof_method: str | None = None
    formal_error: str | None = None
    trace_paths: list[str] = []

    for line in output.splitlines():
        line_proof, line_error = _parse_formal_line(line, observed_statuses, engine_status, task_status, trace_paths)
        if line_proof is not None:
            proof_method = "k-induction"
        if formal_error is None:
            formal_error = line_error

    formal_status = next(
        (status for status in ("error", "fail", "unknown", "pass") if status in observed_statuses),
        "unknown",
    )
    if formal_status == "pass" and any(status == "fail" for status in engine_status.values()):
        formal_status = "unknown"

    return FormalResults(
        formal_status=formal_status,
        engine_status=engine_status,
        task_status=task_status,
        proof_method=proof_method,
        formal_error=formal_error,
        trace_paths=tuple(trace_paths),
    )


def _parse_formal_line(
    line: str,
    observed_statuses: set[str],
    engine_status: dict[str, str],
    task_status: dict[str, str],
    trace_paths: list[str],
) -> tuple[str | None, str | None]:
    normalized = line.lower()
    task_match = re.search(r"\b(cdc_bmc|prove|cover)\b.*\bdone \((pass|fail|unknown|error)", normalized)
    if task_match is not None:
        task_status[task_match.group(1)] = task_match.group(2)
    for status in ("error", "fail", "unknown", "pass"):
        if f"done ({status}" in normalized:
            observed_statuses.add(status)
            break
    _record_engine_status(normalized, engine_status)
    trace_path = _trace_path_from_line(line, normalized)
    if trace_path is not None and trace_path not in trace_paths:
        trace_paths.append(trace_path)
    proof = "k-induction" if "successful proof by k-induction" in normalized else None
    error = line.strip() if "error" in normalized else None
    return proof, error


def _record_engine_status(normalized: str, engine_status: dict[str, str]) -> None:
    for phase in ("basecase", "induction"):
        for status in ("pass", "fail"):
            if f"returned {status} for {phase}" in normalized or f"for {phase}: {status}" in normalized:
                engine_status[phase] = status
                return


def _trace_path_from_line(line: str, normalized: str) -> str | None:
    trace_markers = (
        "counterexample trace",
        "writing trace to vcd file",
        "writing trace to yosys witness file",
    )
    if not any(marker in normalized for marker in trace_markers):
        return None
    if ":" not in line:
        return None
    path = line.rsplit(":", 1)[-1].strip()
    return path or None


def _formal_trace_paths(run: FormalRun, raw_paths: tuple[str, ...]) -> list[str]:
    work_dir = run.run_dir / run.run_sby.stem
    paths: list[str] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        normalized = str(path if path.is_absolute() else work_dir / path)
        if normalized not in paths:
            paths.append(normalized)
    if work_dir.is_dir():
        for path in sorted(work_dir.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_file() and path.suffix.lower() in {".vcd", ".fst", ".yw", ".smtc"}:
                normalized = str(path)
                if normalized not in paths:
                    paths.append(normalized)
    return paths


def _yosys_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


for _legacy_class in (
    FormalResults,
    FormalRun,
):
    _legacy_class.__module__ = "dv_platform.run"
del _legacy_class
