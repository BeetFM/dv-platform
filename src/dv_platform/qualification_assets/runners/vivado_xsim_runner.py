#!/usr/bin/env python3
"""Run a generated-UVM qualification bundle with AMD Vivado Simulator."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    return_code: int
    output: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vivado-bin",
        type=Path,
        required=True,
        help="Vivado bin directory containing xvlog, xelab, and xsim",
    )
    parser.add_argument(
        "--cmd-exe",
        type=Path,
        help="Windows cmd.exe path when invoking a Windows Vivado installation from WSL",
    )
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 < args.timeout_seconds <= 3600:
        raise SystemExit("--timeout-seconds must be within 1..3600")
    root = _environment_path("DV_PLATFORM_QUALIFICATION_ROOT")
    result_path = _environment_path("DV_PLATFORM_RESULT_PATH")
    fixtures = root / "fixtures"
    generated = fixtures / "generated_uvm"
    tools = _resolve_tools(args.vivado_bin, windows=args.cmd_exe is not None)
    diagnostics: list[str] = []

    simulator = _run_pipeline(
        tools,
        fixtures,
        ("surrogate.sv",),
        "dv_qualification",
        "veriforge_sim_snapshot",
        args.cmd_exe,
        args.timeout_seconds,
        uvm=False,
    )
    simulator_passed = simulator.return_code == 0 and "dv-platform qualification passed" in simulator.output
    if not simulator_passed:
        diagnostics.append("Vivado Simulator reference fixture did not produce its completion marker")

    uvm = _run_pipeline(
        tools,
        generated,
        (
            "uvm_stream_loopback_if.sv",
            "uvm_stream_loopback_pkg.sv",
            "uvm_stream_loopback.sv",
            "tb_uvm_stream_loopback_uvm.sv",
        ),
        "tb_uvm_stream_loopback_uvm",
        "veriforge_uvm_snapshot",
        args.cmd_exe,
        args.timeout_seconds,
        uvm=True,
    )
    uvm_passed = uvm.return_code == 0 and _uvm_passed(uvm.output)
    if not uvm_passed:
        diagnostics.append("Vivado Simulator UVM fixture did not report a non-vacuous zero-error completion")

    checks = [
        _check("QUAL-SIM-001", "dv_qualification", simulator_passed, "reference event-scheduling fixture"),
        _check("QUAL-UVM-001", "uvm_stream_loopback", uvm_passed, "generated UVM scoreboard fixture"),
    ]
    passed = simulator_passed and uvm_passed
    payload = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "checks": checks,
        "artifacts": [],
        "diagnostics": diagnostics,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if passed else 1


def _run_pipeline(
    tools: dict[str, Path],
    cwd: Path,
    sources: tuple[str, ...],
    top: str,
    snapshot: str,
    cmd_exe: Path | None,
    timeout_seconds: float,
    *,
    uvm: bool,
) -> CommandResult:
    library = ("-L", "uvm") if uvm else ()
    commands = (
        (tools["xvlog"], ("-sv", *library, *sources)),
        (
            tools["xelab"],
            (
                *library,
                "-timescale",
                "1ns/1ps",
                "-override_timeunit",
                "-override_timeprecision",
                top,
                "-s",
                snapshot,
            ),
        ),
        (tools["xsim"], (snapshot, "-R")),
    )
    output: list[str] = []
    for executable, arguments in commands:
        result = _run_tool(executable, arguments, cwd, cmd_exe, timeout_seconds)
        output.append(result.output)
        if result.return_code != 0:
            return CommandResult(result.return_code, "\n".join(output))
    return CommandResult(0, "\n".join(output))


def _run_tool(
    executable: Path,
    arguments: tuple[str, ...],
    cwd: Path,
    cmd_exe: Path | None,
    timeout_seconds: float,
) -> CommandResult:
    use_cmd = executable.suffix.lower() in {".bat", ".cmd"}
    command: tuple[str, ...]
    if use_cmd:
        if cmd_exe is None or not cmd_exe.is_file():
            raise SystemExit("--cmd-exe is required for Windows Vivado batch files")
        windows_executable = _windows_path(executable)
        windows_arguments = tuple(_windows_argument(argument) for argument in arguments)
        windows_cwd = _windows_path(cwd)
        invocation = subprocess.list2cmdline((windows_executable, *windows_arguments))
        quoted_cwd = subprocess.list2cmdline((windows_cwd,))
        command = (str(cmd_exe), "/d", "/c", f"cd /d {quoted_cwd} && call {invocation}")
        process_cwd = cwd
    else:
        command = (str(executable), *arguments)
        process_cwd = cwd
    try:
        completed = subprocess.run(
            command,
            cwd=process_cwd,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return CommandResult(124, str(error))
    return CommandResult(completed.returncode, completed.stdout + "\n" + completed.stderr)


def _windows_path(path: Path) -> str:
    completed = subprocess.run(
        ("wslpath", "-w", str(path.resolve())),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit(f"cannot translate path for Windows Vivado: {path}")
    return completed.stdout.strip()


def _windows_argument(argument: str) -> str:
    """Translate absolute WSL paths while preserving ordinary tool switches."""

    candidate = Path(argument)
    if candidate.is_absolute() and not re.match(r"^[A-Za-z]:[\\/]", argument):
        return _windows_path(candidate)
    return argument


def _resolve_tools(vivado_bin: Path, *, windows: bool) -> dict[str, Path]:
    if not vivado_bin.is_dir():
        raise SystemExit(f"Vivado bin directory does not exist: {vivado_bin}")
    resolved: dict[str, Path] = {}
    for name in ("xvlog", "xelab", "xsim"):
        candidates = (vivado_bin / f"{name}.bat", vivado_bin / f"{name}.cmd") if windows else (vivado_bin / name,)
        tool = next((candidate for candidate in candidates if candidate.is_file()), None)
        if tool is None:
            raise SystemExit(f"Vivado tool is unavailable: {name}")
        resolved[name] = tool
    return resolved


def _uvm_passed(output: str) -> bool:
    return all(
        (
            "Running test uvm_stream_loopback_test" in output,
            "[TEST_DONE]" in output,
            re.search(r"UVM_ERROR\s*:\s*0\b", output) is not None,
            re.search(r"UVM_FATAL\s*:\s*0\b", output) is not None,
        )
    )


def _check(check_id: str, module: str, passed: bool, description: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "module": module,
        "kind": "simulation",
        "status": "passed" if passed else "failed",
        "message": ("Passed " if passed else "Failed ") + description,
    }


def _environment_path(name: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return Path(value).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
