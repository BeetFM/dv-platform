# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Simulation run command construction and execution."""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, SimulatorConfig, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.security import append_audit_event, redact_text, redact_value
from dv_platform.core.tool_versions import (
    TOOL_VERSION_POLICIES,
    classify_tool_output,
    probe_tool_version,
)
from dv_platform.generators.artifacts import EXECUTION_MANIFEST_NAME, validate_generated_directory
from dv_platform.generators.signals import vhdl_identifier


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


def execute_simulation_run(run: SimulationRun) -> int:
    """Execute one prepared simulation run and persist command, logs, and summary."""

    run.run_dir.mkdir(parents=True, exist_ok=True)
    append_audit_event(
        run.config,
        "simulation.start",
        {"target": str(run.target), "module": run.module, "command": list(run.command)},
    )
    _write_command(run)
    preparation_code = _prepare_simulation_artifacts(run)
    if preparation_code is not None:
        return preparation_code
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
    results, native_results, results_parse_status, results_error = _parse_simulation_results(run, completed)
    effective_return_code, results_error = _simulation_return_code(
        completed.returncode, results, native_results, results_error
    )
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


def _prepare_simulation_artifacts(run: SimulationRun) -> int | None:
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
    return None


def _parse_simulation_results(run, completed):
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
    return results, native_results, results_parse_status, results_error


def _simulation_return_code(completed_return_code, results, native_results, results_error):
    effective_return_code = completed_return_code
    if results is not None and results.failed:
        effective_return_code = completed_return_code or 1
    if results is not None and results.tests == 0:
        effective_return_code = completed_return_code or 1
        results_error = "Cocotb results XML contains zero testcases."
    elif results is not None and results.passed == 0:
        effective_return_code = completed_return_code or 1
        results_error = "Cocotb results XML contains no passing testcases."
    if results_error is not None:
        effective_return_code = completed_return_code or 1
    if native_results is not None and native_results.failed:
        effective_return_code = completed_return_code or 1
    return effective_return_code, results_error


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


def _simulation_tool_qualification(run: SimulationRun) -> dict[str, Any]:
    direct = probe_tool_version(run.tool_command)
    if direct.get("status") == "supported":
        return direct
    if run.tool_name in TOOL_VERSION_POLICIES and run.stdout_log.is_file():
        return classify_tool_output(run.tool_name, run.stdout_log.read_text(encoding="utf-8", errors="replace"))
    return direct


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


for _legacy_class in (
    CocotbResults,
    NativeResults,
    SimulationRun,
):
    _legacy_class.__module__ = "dv_platform.run"
del _legacy_class
