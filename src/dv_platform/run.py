"""Simulation run command construction and execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import subprocess
import sys
from xml.etree import ElementTree

from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.generators.artifacts import validate_generated_directory


@dataclass(frozen=True)
class CocotbResults:
    """Parsed cocotb JUnit result counts."""

    tests: int = 0
    passed: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
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
            "failed_testcases": list(self.failed_testcases),
        }


@dataclass(frozen=True)
class SimulationRun:
    """Prepared simulation run paths and command."""

    target: VerificationTarget
    module: str
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


def prepare_simulation_run(
    config: CLIConfig,
    simulator: SimulatorConfig,
    module: str,
    timeout_seconds: float = 120.0,
) -> SimulationRun:
    """Build deterministic run paths and command for one generated module."""

    generated_dir = config.output_dir / "simulation" / str(simulator.target) / "modules" / module
    run_dir = config.work_dir / "runs" / "simulation" / str(simulator.target) / module
    command_prefix = shlex.split(simulator.command)
    runner_script: Path | None = None
    if simulator.target == VerificationTarget.COCOTB and Path(command_prefix[0]).name == "iverilog":
        runner_script = run_dir / "run_cocotb.py"
        command = (sys.executable, str(runner_script))
    else:
        command = (*command_prefix, str(generated_dir))
    return SimulationRun(
        target=simulator.target,
        module=module,
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

    generated_dir = config.output_dir / "formal" / "modules" / module
    run_dir = config.work_dir / "runs" / "formal" / module
    run_sby = run_dir / f"{_safe_identifier(module)}.sby"
    command = (*shlex.split(tool.command), str(run_sby))
    return FormalRun(
        module=module,
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
        modules_dir = config.output_dir / "formal" / "modules"
    else:
        modules_dir = config.output_dir / "simulation" / str(target) / "modules"
    if not modules_dir.is_dir():
        return ()
    return tuple(path.name for path in sorted(modules_dir.iterdir(), key=lambda item: item.name) if path.is_dir())


def write_aggregate_run_summary(
    config: CLIConfig,
    target: VerificationTarget,
    module_summaries: tuple[dict[str, object], ...],
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
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def execute_simulation_run(run: SimulationRun) -> int:
    """Execute one prepared simulation run and persist command, logs, and summary."""

    run.run_dir.mkdir(parents=True, exist_ok=True)
    _write_command(run)
    if not run.generated_dir.is_dir():
        _write_summary(run, return_code=2, status="missing_artifacts")
        return 2
    if run.runner_script is not None:
        try:
            validate_generated_directory(run.target, run.module, run.generated_dir)
        except ValueError as error:
            _write_summary(run, return_code=2, status="invalid_artifacts", validation_error=str(error))
            return 2
        _write_cocotb_runner_script(run)

    try:
        completed = subprocess.run(
            run.command,
            cwd=run.generated_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=run.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        run.stdout_log.write_text(_process_output(error.stdout), encoding="utf-8")
        stderr = _process_output(error.stderr)
        stderr += f"\nSimulation timed out after {run.timeout_seconds:g} seconds.\n"
        run.stderr_log.write_text(stderr, encoding="utf-8")
        _write_summary(run, return_code=124, status="timeout")
        return 124

    run.stdout_log.write_text(completed.stdout, encoding="utf-8")
    run.stderr_log.write_text(completed.stderr, encoding="utf-8")
    results_path = run.run_dir / "results.xml"
    results_error: str | None = None
    results_parse_status: str | None = None
    try:
        results = None
        if run.runner_script is not None:
            if results_path.is_file():
                results = parse_cocotb_results(results_path)
                results_parse_status = "parsed"
            else:
                results_parse_status = "missing"
    except ElementTree.ParseError as error:
        results = None
        results_parse_status = "malformed"
        results_error = f"Could not parse cocotb results XML: {error}"
        run.stderr_log.write_text(completed.stderr + "\n" + results_error + "\n", encoding="utf-8")
    effective_return_code = completed.returncode
    if results is not None and results.failed:
        effective_return_code = 1
    if results_error is not None:
        effective_return_code = 1

    _write_summary(
        run,
        return_code=effective_return_code,
        status="passed" if effective_return_code == 0 else "failed",
        results=results,
        results_error=results_error,
        results_parse_status=results_parse_status,
    )
    return effective_return_code


def execute_formal_run(config: CLIConfig, run: FormalRun) -> int:
    """Execute one prepared formal run and persist command, logs, and summary."""

    run.run_dir.mkdir(parents=True, exist_ok=True)
    _write_formal_command(run)
    if not run.generated_dir.is_dir():
        _write_formal_summary(run, return_code=2, status="missing_artifacts")
        return 2
    try:
        validate_generated_directory(VerificationTarget.FORMAL, run.module, run.generated_dir)
    except ValueError as error:
        _write_formal_summary(run, return_code=2, status="invalid_artifacts", validation_error=str(error))
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

    _write_run_sby(run, manifest_path)
    try:
        completed = subprocess.run(
            run.command,
            cwd=run.run_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=run.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        run.stdout_log.write_text(_process_output(error.stdout), encoding="utf-8")
        stderr = _process_output(error.stderr)
        stderr += f"\nFormal run timed out after {run.timeout_seconds:g} seconds.\n"
        run.stderr_log.write_text(stderr, encoding="utf-8")
        _write_formal_summary(run, return_code=124, status="timeout")
        return 124

    run.stdout_log.write_text(completed.stdout, encoding="utf-8")
    run.stderr_log.write_text(completed.stderr, encoding="utf-8")
    _write_formal_summary(
        run,
        return_code=completed.returncode,
        status="passed" if completed.returncode == 0 else "failed",
    )
    return completed.returncode


def _write_command(run: SimulationRun) -> None:
    payload = {
        "target": str(run.target),
        "module": run.module,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "timeout_seconds": run.timeout_seconds,
    }
    run.command_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    }
    run.command_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_summary(
    run: SimulationRun,
    return_code: int,
    status: str,
    results: CocotbResults | None = None,
    results_error: str | None = None,
    validation_error: str | None = None,
    results_parse_status: str | None = None,
) -> None:
    payload = {
        "target": str(run.target),
        "module": run.module,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "timeout_seconds": run.timeout_seconds,
        "return_code": return_code,
        "status": status,
        "stdout_log": str(run.stdout_log),
        "stderr_log": str(run.stderr_log),
        "runner_script": str(run.runner_script) if run.runner_script is not None else None,
        "generated_artifact": str(_generated_test_path(run)) if run.runner_script is not None else None,
        "provenance_manifest": str(run.generated_dir / "provenance.json") if run.runner_script is not None else None,
        "results_xml": str(run.run_dir / "results.xml") if run.runner_script is not None else None,
        "results": results.as_dict() if results is not None else None,
        "results_parse_status": results_parse_status,
        "results_error": results_error,
        "validation_error": validation_error,
        "stdout_tail": _text_tail(run.stdout_log),
        "stderr_tail": _text_tail(run.stderr_log),
    }
    run.summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_formal_summary(
    run: FormalRun,
    return_code: int,
    status: str,
    validation_error: str | None = None,
) -> None:
    payload = {
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
        "timeout_seconds": run.timeout_seconds,
        "return_code": return_code,
        "status": status,
        "stdout_log": str(run.stdout_log),
        "stderr_log": str(run.stderr_log),
        "validation_error": validation_error,
        "stdout_tail": _text_tail(run.stdout_log),
        "stderr_tail": _text_tail(run.stderr_log),
    }
    run.summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_cocotb_runner_script(run: SimulationRun) -> None:
    manifest_path = run.run_dir.parents[3] / "project-manifest.json"
    test_module = f"test_{_safe_identifier(run.module)}"
    script = f"""from pathlib import Path
import json
import sys

from cocotb_tools.runner import get_runner

manifest = json.loads(Path({str(manifest_path)!r}).read_text(encoding="utf-8"))
sources = [Path(item["path"]) for item in manifest["hdl_files"]]
includes = [Path(item) for item in manifest.get("include_paths", [])]
defines = {{}}
for item in manifest.get("defines", []):
    if "=" in item:
        name, value = item.split("=", 1)
        defines[name] = value
    else:
        defines[item] = 1

generated_dir = Path({str(run.generated_dir)!r})
run_dir = Path({str(run.run_dir)!r})
build_dir = run_dir / "build"
sys.path.insert(0, str(generated_dir))

runner = get_runner("icarus")
runner.build(
    sources=sources,
    includes=includes,
    defines=defines,
    hdl_toplevel={run.module!r},
    build_dir=build_dir,
    always=True,
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel={run.module!r},
    test_module={test_module!r},
    build_dir=build_dir,
    results_xml=str(run_dir / "results.xml"),
    timescale=("1ns", "1ps"),
)
"""
    run.runner_script.write_text(script, encoding="utf-8")


def _write_run_sby(run: FormalRun, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hdl_files = tuple(Path(str(item["path"])) for item in manifest.get("hdl_files", ()))
    harness_path = run.generated_dir / f"formal_{_safe_identifier(run.module)}.sv"
    source_lines = [f"read -formal -sv {path}" for path in hdl_files]
    source_lines.append(f"read -formal -sv {harness_path}")
    file_lines = [str(path) for path in hdl_files]
    file_lines.append(str(harness_path))
    run.run_sby.write_text(
        "\n".join(
            [
                "[options]",
                "mode prove",
                "depth 20",
                "",
                "[engines]",
                "smtbmc",
                "",
                "[script]",
                *source_lines,
                f"prep -top formal_{_safe_identifier(run.module)}",
                "",
                "[files]",
                *file_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_cocotb_results(results_path: Path) -> CocotbResults | None:
    """Parse cocotb JUnit XML counts when a results file exists."""

    if not results_path.is_file():
        return None
    root = ElementTree.parse(results_path).getroot()
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
        failed_testcases=failed_testcases,
    )


def _testcase_failed(testcase: ElementTree.Element) -> bool:
    return any(_strip_namespace(child.tag) in {"failure", "error"} for child in testcase)


def _testcase_name(testcase: ElementTree.Element) -> str:
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
