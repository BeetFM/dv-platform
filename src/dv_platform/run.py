"""Simulation run command construction and execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.sandbox import sandbox_command
from dv_platform.core.security import append_audit_event, redact_text, redact_value
from dv_platform.core.tool_versions import (
    TOOL_VERSION_POLICIES,
    classify_tool_output,
    formal_dependency_qualifications,
    probe_tool_version,
)
from dv_platform.core.validation import validation_result_from_coverage
from dv_platform.generators.artifacts import EXECUTION_MANIFEST_NAME, validate_generated_directory
from dv_platform.generators.signals import vhdl_identifier


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
class CocotbResults:
    """Parsed cocotb JUnit result counts."""

    tests: int = 0
    passed: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    testcases: tuple[str, ...] = ()
    failed_testcases: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        return self.failures > 0 or self.errors > 0

    def as_dict(self) -> dict[str, object]:
        return {
            "tests": self.tests,
            "passed": self.passed,
            "failures": self.failures,
            "errors": self.errors,
            "skipped": self.skipped,
            "testcases": list(self.testcases),
            "failed_testcases": list(self.failed_testcases),
        }


@dataclass(frozen=True)
class NativeResults:
    """Versioned per-trace outcomes emitted by native HDL testbenches."""

    outcomes: tuple[tuple[str, str], ...] = ()

    @property
    def failed(self) -> bool:
        return any(status == "failed" for _trace_id, status in self.outcomes)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "outcomes": [{"trace_id": trace_id, "status": status} for trace_id, status in self.outcomes],
        }


@dataclass(frozen=True)
class SimulationRun:
    """Prepared simulation run paths and command."""

    target: VerificationTarget
    config: CLIConfig
    module: str
    tool_name: str
    tool_command: str
    command: tuple[str, ...]
    generated_dir: Path
    run_dir: Path
    command_path: Path
    stdout_log: Path
    stderr_log: Path
    summary_path: Path
    timeout_seconds: float = 120.0
    runner_script: Path | None = None


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


@dataclass(frozen=True)
class _ProcessResult:
    """Bounded result from a tool process and all of its descendants."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


def _set_process_memory_limit(pid: int, memory_limit_mb: int) -> None:
    """Apply an address-space limit to a running POSIX process and its descendants."""

    if os.name != "posix" or memory_limit_mb <= 0:
        return
    try:
        import resource

        limit = memory_limit_mb * 1024 * 1024
        prlimit = getattr(resource, "prlimit", None)
        if prlimit is not None:
            prlimit(pid, resource.RLIMIT_AS, (limit, limit))
    except (ImportError, OSError, ValueError):
        # The parent still has timeout and process-group containment if this
        # platform does not expose RLIMIT_AS.
        return


def _terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: float = 2.0) -> None:
    """Terminate a process and its descendants, escalating after a short grace period."""

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def _capture_process_stream(
    stream: Any,
    output_path: Path,
    max_output_bytes: int,
    truncated_result: list[bool],
) -> None:
    """Drain a pipe without allowing an unbounded tool log to consume RAM."""

    max_output_bytes = max(1, max_output_bytes)
    head_limit = max_output_bytes // 2
    tail_limit = max_output_bytes - head_limit
    head = bytearray()
    tail = bytearray()
    truncated = False
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            head_remaining = max(0, head_limit - len(head))
            if head_remaining:
                head.extend(chunk[:head_remaining])
            tail_chunk = chunk[head_remaining:]
            if tail_chunk:
                truncated = True
                tail.extend(tail_chunk)
                if len(tail) > tail_limit:
                    del tail[: len(tail) - tail_limit]
    finally:
        stream.close()
        truncated_result.append(truncated)
        payload = bytes(head)
        if truncated:
            payload += b"\n... output truncated by dv-platform ...\n" + bytes(tail)
        output_path.write_bytes(payload)


def _run_bounded_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    timeout_seconds: float,
    stdout_path: Path,
    stderr_path: Path,
    max_output_bytes: int,
    memory_limit_mb: int,
    config: CLIConfig | None = None,
) -> _ProcessResult:
    """Run a tool with bounded logs, memory, timeout, and descendant cleanup."""

    if config is not None:
        command = sandbox_command(
            config,
            command,
            cwd,
            readonly_paths=(config.repo_root, config.output_dir),
            writable_paths=(stdout_path.parent,),
        )
    popen_kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "bufsize": 0,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags

    process = subprocess.Popen(command, **popen_kwargs)
    _set_process_memory_limit(process.pid, memory_limit_mb)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_truncated: list[bool] = []
    stderr_truncated: list[bool] = []
    stdout_thread = threading.Thread(
        target=_capture_process_stream,
        args=(process.stdout, stdout_path, max_output_bytes, stdout_truncated),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_capture_process_stream,
        args=(process.stderr, stderr_path, max_output_bytes, stderr_truncated),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
    except BaseException:
        # Ctrl-C and unexpected parent-side failures must not orphan solver
        # descendants while the caller unwinds.
        _terminate_process_group(process)
        stdout_thread.join()
        stderr_thread.join()
        raise
    stdout_thread.join()
    stderr_thread.join()
    return _ProcessResult(
        returncode=124 if timed_out else process.returncode,
        stdout=_process_output(stdout_path.read_bytes()),
        stderr=_process_output(stderr_path.read_bytes()),
        timed_out=timed_out,
        stdout_truncated=bool(stdout_truncated and stdout_truncated[0]),
        stderr_truncated=bool(stderr_truncated and stderr_truncated[0]),
    )


def _redact_process_output(config: CLIConfig, output: str, truncated: bool, stream_name: str) -> str:
    """Redact bounded tool output and make truncation visible to the user."""

    if truncated:
        output += f"\n{stream_name.capitalize()} was truncated after {config.max_output_bytes} bytes.\n"
    return redact_text(config, output)


def prepare_simulation_run(
    config: CLIConfig,
    simulator: SimulatorConfig,
    module: str,
    timeout_seconds: float = 120.0,
) -> SimulationRun:
    """Build deterministic run paths and command for one generated module."""

    module = validate_path_component(module, "run module")
    generated_dir = contained_path(config.output_dir, "simulation", str(simulator.target), "modules", module)
    run_dir = contained_path(config.work_dir, "runs", "simulation", str(simulator.target), module)
    command_prefix = tuple(shlex.split(simulator.command))
    if not command_prefix:
        raise ValueError(f"Simulator command is empty for target {simulator.target}")
    runner_script: Path | None = None
    command: tuple[str, ...]
    executable_name = Path(command_prefix[0]).name
    if simulator.target == VerificationTarget.COCOTB and executable_name == "iverilog":
        runner_script = run_dir / "run_cocotb.py"
        command = (sys.executable, str(runner_script))
    elif (
        simulator.target in {VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG}
        and executable_name == "iverilog"
    ):
        runner_script = run_dir / "run_native.py"
        command = (sys.executable, str(runner_script))
    elif simulator.target == VerificationTarget.VHDL and executable_name == "ghdl":
        runner_script = run_dir / "run_native.py"
        command = (sys.executable, str(runner_script))
    else:
        command = (*command_prefix, str(generated_dir))
    return SimulationRun(
        target=simulator.target,
        config=config,
        module=module,
        tool_name=simulator.name,
        tool_command=simulator.command,
        command=command,
        generated_dir=generated_dir,
        run_dir=run_dir,
        command_path=run_dir / "command.json",
        stdout_log=run_dir / "stdout.log",
        stderr_log=run_dir / "stderr.log",
        summary_path=run_dir / "summary.json",
        timeout_seconds=timeout_seconds,
        runner_script=runner_script,
    )


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


def execute_simulation_run(run: SimulationRun) -> int:
    """Execute one prepared simulation run and persist command, logs, and summary."""

    run.run_dir.mkdir(parents=True, exist_ok=True)
    append_audit_event(
        run.config,
        "simulation.start",
        {"target": str(run.target), "module": run.module, "command": list(run.command)},
    )
    _write_command(run)
    if not run.generated_dir.is_dir():
        _write_summary(run, return_code=2, status="missing_artifacts")
        return 2
    try:
        validate_generated_directory(run.target, run.module, run.generated_dir)
    except ValueError as error:
        _write_summary(run, return_code=2, status="invalid_artifacts", validation_error=str(error))
        return 2
    if run.runner_script is not None:
        if run.target == VerificationTarget.COCOTB:
            _write_cocotb_runner_script(run)
        elif run.target in {VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG}:
            _write_iverilog_runner_script(run)
        elif run.target == VerificationTarget.VHDL:
            _write_ghdl_runner_script(run)
    if run.target == VerificationTarget.COCOTB:
        (run.run_dir / "results.xml").unlink(missing_ok=True)

    completed = _run_bounded_process(
        run.command,
        cwd=run.generated_dir,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout_seconds=run.timeout_seconds,
        stdout_path=run.stdout_log,
        stderr_path=run.stderr_log,
        max_output_bytes=run.config.max_output_bytes,
        memory_limit_mb=run.config.max_process_memory_mb,
        config=run.config,
    )
    run.stdout_log.write_text(
        _redact_process_output(run.config, completed.stdout, completed.stdout_truncated, "stdout"),
        encoding="utf-8",
    )
    stderr = _redact_process_output(run.config, completed.stderr, completed.stderr_truncated, "stderr")
    if completed.timed_out:
        stderr += f"\nSimulation timed out after {run.timeout_seconds:g} seconds.\n"
        _write_summary(run, return_code=124, status="timeout")
        append_audit_event(run.config, "simulation.finish", {"module": run.module, "return_code": 124})
        run.stderr_log.write_text(stderr, encoding="utf-8")
        return 124
    run.stderr_log.write_text(stderr, encoding="utf-8")
    results_path = run.run_dir / "results.xml"
    results_error: str | None = None
    results_parse_status: str | None = None
    native_results: NativeResults | None = None
    native_targets = {
        VerificationTarget.SYSTEMVERILOG,
        VerificationTarget.VERILOG,
        VerificationTarget.VHDL,
        VerificationTarget.UVM,
    }
    try:
        results = None
        if run.target == VerificationTarget.COCOTB:
            if results_path.is_file():
                results = parse_cocotb_results(results_path)
                results_parse_status = "parsed"
            else:
                results_parse_status = "missing"
                results_error = "Cocotb results XML was not produced; no test outcome can be verified."
        elif run.target in native_targets:
            expected_trace_ids = tuple(
                str(item["trace_id"]) for item in _generated_traceability(run.generated_dir) if item.get("trace_id")
            )
            native_results = parse_native_results(completed.stdout, expected_trace_ids)
            results_parse_status = "parsed"
            if not native_results.outcomes:
                results_parse_status = "missing"
                results_error = "Native simulation produced no normalized per-trace outcomes."
    except ParseError as error:
        results = None
        results_parse_status = "malformed"
        results_error = f"Could not parse cocotb results XML: {error}"
        run.stderr_log.write_text(
            redact_text(run.config, completed.stderr + "\n" + results_error + "\n"), encoding="utf-8"
        )
    except ValueError as error:
        results = None
        results_parse_status = "malformed"
        if run.target == VerificationTarget.COCOTB:
            results_error = f"Could not parse cocotb results XML: {error}"
        else:
            results_error = f"Could not validate native simulation outcomes: {error}"
        run.stderr_log.write_text(
            redact_text(run.config, completed.stderr + "\n" + results_error + "\n"), encoding="utf-8"
        )
    effective_return_code = completed.returncode
    if results is not None and results.failed:
        effective_return_code = completed.returncode or 1
    if results is not None and results.tests == 0:
        effective_return_code = completed.returncode or 1
        results_error = "Cocotb results XML contains zero testcases."
    elif results is not None and results.passed == 0:
        effective_return_code = completed.returncode or 1
        results_error = "Cocotb results XML contains no passing testcases."
    if results_error is not None:
        effective_return_code = completed.returncode or 1
    if native_results is not None and native_results.failed:
        effective_return_code = completed.returncode or 1

    _write_summary(
        run,
        return_code=effective_return_code,
        status="passed" if effective_return_code == 0 else "failed",
        results=results,
        native_results=native_results,
        results_error=results_error,
        results_parse_status=results_parse_status,
    )
    append_audit_event(
        run.config,
        "simulation.finish",
        {"target": str(run.target), "module": run.module, "return_code": effective_return_code},
    )
    return effective_return_code


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


def _write_command(run: SimulationRun) -> None:
    payload = {
        "target": str(run.target),
        "module": run.module,
        "tool_name": run.tool_name,
        "tool_command": run.tool_command,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "timeout_seconds": run.timeout_seconds,
        "max_process_memory_mb": run.config.max_process_memory_mb,
        "max_output_bytes": run.config.max_output_bytes,
    }
    atomic_write_text(run.command_path, json.dumps(redact_value(run.config, payload), indent=2, sort_keys=True) + "\n")


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


def _simulation_tool_qualification(run: SimulationRun) -> dict[str, Any]:
    direct = probe_tool_version(run.tool_command)
    if direct.get("status") == "supported":
        return direct
    if run.tool_name in TOOL_VERSION_POLICIES and run.stdout_log.is_file():
        return classify_tool_output(run.tool_name, run.stdout_log.read_text(encoding="utf-8", errors="replace"))
    return direct


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


def _cocotb_trace_statuses(
    traceability: list[dict[str, Any]],
    results: CocotbResults | None,
) -> dict[str, str] | None:
    if results is None:
        return None
    testcase_names = {name.rsplit(".", 1)[-1] for name in results.testcases}
    failed_names = {name.rsplit(".", 1)[-1] for name in results.failed_testcases}
    generated_symbols = {
        str(record.get("generated_symbol", "")) for record in traceability if record.get("generated_symbol")
    }
    if not (generated_symbols & testcase_names):
        return {str(record["trace_id"]): "unexecuted" for record in traceability}
    return {
        str(record["trace_id"]): (
            "failed"
            if str(record.get("generated_symbol", "")) in failed_names
            else "passed"
            if str(record.get("generated_symbol", "")) in testcase_names
            else "unexecuted"
        )
        for record in traceability
    }


def _native_trace_statuses(
    traceability: list[dict[str, Any]],
    results: NativeResults | None,
) -> dict[str, str] | None:
    if results is None:
        return None
    statuses = dict(results.outcomes)
    return {str(record["trace_id"]): statuses.get(str(record["trace_id"]), "unexecuted") for record in traceability}


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


def _write_cocotb_runner_script(run: SimulationRun) -> None:
    if run.runner_script is None:
        raise ValueError("Cannot write a cocotb runner script for a generic simulation run")
    test_module = f"test_{_safe_identifier(run.module)}"
    script = f"""from pathlib import Path
import json
import sys

from cocotb_tools.runner import get_runner

sys.dont_write_bytecode = True

manifest = json.loads((Path({str(run.generated_dir)!r}) / {EXECUTION_MANIFEST_NAME!r}).read_text(encoding="utf-8"))
project = manifest["project"]
design_unit = manifest.get("design_unit", manifest["module"])
sources = [Path(item["path"]) for item in project["hdl_files"]]
includes = [Path(item) for item in project.get("include_paths", [])]
defines = {{}}
for item in project.get("defines", []):
    if "=" in item:
        name, value = item.split("=", 1)
        defines[name] = value
    else:
        defines[item] = 1
parameters = {{}}
for item in manifest.get("elaborated_parameters", []):
    name, value = item["name"], item["value"]
    if "'" in value:
        _width, encoded = value.lower().split("'", 1)
        encoded = encoded.removeprefix("s")
        base = {{"b": 2, "o": 8, "d": 10, "h": 16}}.get(encoded[:1])
        if base is not None:
            parameters[name] = int(encoded[1:], base)
            continue
    try:
        parameters[name] = int(value, 0)
    except ValueError:
        parameters[name] = value

generated_dir = Path({str(run.generated_dir)!r})
run_dir = Path({str(run.run_dir)!r})
build_dir = run_dir / "build"
sys.path.insert(0, str(generated_dir))

runner = get_runner("icarus")
runner.build(
    sources=sources,
    includes=includes,
    defines=defines,
    parameters=parameters,
    hdl_toplevel=design_unit,
    build_dir=build_dir,
    always=True,
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel=design_unit,
    test_module={test_module!r},
    build_dir=build_dir,
    results_xml=str(run_dir / "results.xml"),
    timescale=("1ns", "1ps"),
)
"""
    atomic_write_text(run.runner_script, script)


def _write_iverilog_runner_script(run: SimulationRun) -> None:
    if run.runner_script is None:
        raise ValueError("Cannot write an Icarus runner script without a path")
    simulator = next(
        (
            item
            for item in run.config.simulators
            if item.target == run.target and Path(shlex.split(item.command)[0]).name == "iverilog"
        ),
        None,
    )
    if simulator is None:
        raise ValueError(f"No Icarus simulator configuration is available for {run.target}")
    command_prefix = tuple(shlex.split(simulator.command))
    top = f"tb_{_safe_identifier(run.module)}"
    script = f"""from pathlib import Path
import json
import subprocess

manifest = json.loads((Path({str(run.generated_dir)!r}) / {EXECUTION_MANIFEST_NAME!r}).read_text(encoding="utf-8"))
project = manifest["project"]
standard = "-g2012" if any(item.get("language") == "systemverilog" for item in project["hdl_files"]) else "-g2005"
sources = [str(Path(item["path"])) for item in project["hdl_files"] if item.get("language") != "vhdl"]
generated = [
    str(Path({str(run.generated_dir)!r}) / item["path"])
    for item in manifest["generated_files"]
    if item.get("kind") == "testbench"
]
includes = ["-I" + str(Path(item)) for item in project.get("include_paths", [])]
defines = ["-D" + str(item) for item in project.get("defines", [])]
output = Path({str(run.run_dir / "native.vvp")!r})
compile_command = [
    *{list(command_prefix)!r},
    standard,
    "-s",
    {top!r},
    "-o",
    str(output),
    *includes,
    *defines,
    *sources,
    *generated,
]
compiled = subprocess.run(compile_command, check=False)
if compiled.returncode != 0:
    raise SystemExit(compiled.returncode)
completed = subprocess.run(["vvp", str(output)], check=False)
raise SystemExit(completed.returncode)
"""
    atomic_write_text(run.runner_script, script)


def _write_ghdl_runner_script(run: SimulationRun) -> None:
    if run.runner_script is None:
        raise ValueError("Cannot write a GHDL runner script without a path")
    simulator = next(
        (
            item
            for item in run.config.simulators
            if item.target == VerificationTarget.VHDL and Path(shlex.split(item.command)[0]).name == "ghdl"
        ),
        None,
    )
    if simulator is None:
        raise ValueError("No GHDL simulator configuration is available for vhdl")
    command_prefix = tuple(shlex.split(simulator.command))
    top = f"tb_{vhdl_identifier(run.module)}"
    script = f"""from pathlib import Path
import json
import subprocess

manifest = json.loads((Path({str(run.generated_dir)!r}) / {EXECUTION_MANIFEST_NAME!r}).read_text(encoding="utf-8"))
project = manifest["project"]
sources = [str(Path(item["path"])) for item in project["hdl_files"] if item.get("language") == "vhdl"]
generated = [
    str(Path({str(run.generated_dir)!r}) / item["path"])
    for item in manifest["generated_files"]
    if item.get("kind") == "testbench"
]
prefix = {list(command_prefix)!r}
for source in [*sources, *generated]:
    completed = subprocess.run([*prefix, "-a", "--std=08", source], check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
elaborated = subprocess.run([*prefix, "-e", "--std=08", {top!r}], check=False)
if elaborated.returncode != 0:
    raise SystemExit(elaborated.returncode)
completed = subprocess.run(
    [*prefix, "-r", "--std=08", {top!r}, "--assert-level=error", "--stop-time=1us"],
    check=False,
)
raise SystemExit(completed.returncode)
"""
    atomic_write_text(run.runner_script, script)


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
        normalized = line.lower()
        task_match = re.search(r"\b(cdc_bmc|prove|cover)\b.*\bdone \((pass|fail|unknown|error)", normalized)
        if task_match is not None:
            task_status[task_match.group(1)] = task_match.group(2)
        if "done (error" in normalized:
            observed_statuses.add("error")
        elif "done (fail" in normalized:
            observed_statuses.add("fail")
        elif "done (unknown" in normalized:
            observed_statuses.add("unknown")
        elif "done (pass" in normalized:
            observed_statuses.add("pass")
        if "successful proof by k-induction" in normalized:
            proof_method = "k-induction"
        if "returned pass for basecase" in normalized or "for basecase: pass" in normalized:
            engine_status["basecase"] = "pass"
        elif "returned fail for basecase" in normalized or "for basecase: fail" in normalized:
            engine_status["basecase"] = "fail"
        elif "returned pass for induction" in normalized or "for induction: pass" in normalized:
            engine_status["induction"] = "pass"
        elif "returned fail for induction" in normalized or "for induction: fail" in normalized:
            engine_status["induction"] = "fail"
        if formal_error is None and "error" in normalized:
            formal_error = line.strip()
        trace_path = _trace_path_from_line(line, normalized)
        if trace_path is not None and trace_path not in trace_paths:
            trace_paths.append(trace_path)

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


def parse_cocotb_results(results_path: Path) -> CocotbResults | None:
    """Parse cocotb JUnit XML counts when a results file exists."""

    if not results_path.is_file():
        return None
    if results_path.is_symlink():
        raise ValueError("cocotb results XML must not be a symbolic link")
    max_results_bytes = 64 * 1024 * 1024
    raw = results_path.read_bytes()
    if len(raw) > max_results_bytes:
        raise ValueError(f"cocotb results XML exceeds {max_results_bytes} byte safety limit")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("cocotb results XML must not contain DTD or entity declarations")
    try:
        root = fromstring(raw)
    except ParseError as error:
        raise ValueError(f"invalid cocotb results XML: {error}") from error
    testcases = tuple(element for element in root.iter() if _strip_namespace(element.tag) == "testcase")
    failures = sum(1 for testcase in testcases if any(_strip_namespace(child.tag) == "failure" for child in testcase))
    errors = sum(1 for testcase in testcases if any(_strip_namespace(child.tag) == "error" for child in testcase))
    skipped = sum(1 for testcase in testcases if any(_strip_namespace(child.tag) == "skipped" for child in testcase))
    tests = len(testcases)
    passed = max(0, tests - failures - errors - skipped)
    failed_testcases = tuple(_testcase_name(testcase) for testcase in testcases if _testcase_failed(testcase))
    return CocotbResults(
        tests=tests,
        passed=passed,
        failures=failures,
        errors=errors,
        skipped=skipped,
        testcases=tuple(_testcase_name(testcase) for testcase in testcases),
        failed_testcases=failed_testcases,
    )


def parse_native_results(output: str, expected_trace_ids: tuple[str, ...]) -> NativeResults:
    """Parse and strictly reconcile native-result-v1 JSON line records."""

    prefix = "DV_PLATFORM_RESULT_V1 "
    outcomes: dict[str, str] = {}
    expected = set(expected_trace_ids)
    for line in output.splitlines():
        marker_offset = line.find(prefix)
        if marker_offset < 0:
            continue
        raw = line[marker_offset + len(prefix) :]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid native-result-v1 JSON: {error}") from error
        if not isinstance(payload, dict) or set(payload) != {"trace_id", "status"}:
            raise ValueError("native-result-v1 requires exactly trace_id and status")
        trace_id = payload.get("trace_id")
        status = payload.get("status")
        if not isinstance(trace_id, str) or not trace_id:
            raise ValueError("native-result-v1 trace_id must be a non-empty string")
        if status not in {"passed", "failed"}:
            raise ValueError("native-result-v1 status must be passed or failed")
        if trace_id in outcomes:
            raise ValueError(f"duplicate native-result-v1 trace_id: {trace_id}")
        if trace_id not in expected:
            raise ValueError(f"native-result-v1 references an unknown or stale trace_id: {trace_id}")
        outcomes[trace_id] = str(status)
    missing = sorted(expected - set(outcomes))
    if outcomes and missing:
        raise ValueError("native-result-v1 is missing generated trace IDs: " + ", ".join(missing))
    return NativeResults(tuple(sorted(outcomes.items())))


def _testcase_failed(testcase: Element) -> bool:
    return any(_strip_namespace(child.tag) in {"failure", "error"} for child in testcase)


def _testcase_name(testcase: Element) -> str:
    name = testcase.attrib.get("name", "unknown")
    classname = testcase.attrib.get("classname")
    if classname:
        return f"{classname}.{name}"
    return name


def _generated_test_path(run: SimulationRun) -> Path:
    return run.generated_dir / f"test_{_safe_identifier(run.module)}.py"


def _text_tail(path: Path, max_lines: int = 20) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]


def _process_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)


def _yosys_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
