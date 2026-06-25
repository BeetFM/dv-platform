"""Simulation run command construction and execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import subprocess
import sys
from xml.etree import ElementTree

from dv_platform.core.models import CLIConfig, SimulatorConfig, VerificationTarget


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
    runner_script: Path | None = None


def prepare_simulation_run(
    config: CLIConfig,
    simulator: SimulatorConfig,
    module: str,
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
        runner_script=runner_script,
    )


def execute_simulation_run(run: SimulationRun) -> int:
    """Execute one prepared simulation run and persist command, logs, and summary."""

    run.run_dir.mkdir(parents=True, exist_ok=True)
    _write_command(run)
    if not run.generated_dir.is_dir():
        _write_summary(run, return_code=2, status="missing_artifacts")
        return 2
    if run.runner_script is not None:
        _write_cocotb_runner_script(run)

    completed = subprocess.run(
        run.command,
        cwd=run.generated_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    run.stdout_log.write_text(completed.stdout, encoding="utf-8")
    run.stderr_log.write_text(completed.stderr, encoding="utf-8")
    results_path = run.run_dir / "results.xml"
    effective_return_code = completed.returncode
    if run.runner_script is not None and _cocotb_results_failed(results_path):
        effective_return_code = 1

    _write_summary(
        run,
        return_code=effective_return_code,
        status="passed" if effective_return_code == 0 else "failed",
    )
    return effective_return_code


def _write_command(run: SimulationRun) -> None:
    payload = {
        "target": str(run.target),
        "module": run.module,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
    }
    run.command_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_summary(run: SimulationRun, return_code: int, status: str) -> None:
    payload = {
        "target": str(run.target),
        "module": run.module,
        "command": list(run.command),
        "generated_dir": str(run.generated_dir),
        "run_dir": str(run.run_dir),
        "return_code": return_code,
        "status": status,
        "stdout_log": str(run.stdout_log),
        "stderr_log": str(run.stderr_log),
        "runner_script": str(run.runner_script) if run.runner_script is not None else None,
        "results_xml": str(run.run_dir / "results.xml") if run.runner_script is not None else None,
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


def _cocotb_results_failed(results_path: Path) -> bool:
    if not results_path.is_file():
        return False
    root = ElementTree.parse(results_path).getroot()
    return any(element.tag in {"failure", "error"} for element in root.iter())


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)
