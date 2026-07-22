"""Explicit compatibility ranges for the qualified open-source toolchain."""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolVersionPolicy:
    """One tested tool range and the command used to identify it."""

    tool: str
    pattern: str
    version_args: tuple[str, ...]
    minimum: tuple[int, ...]
    maximum: tuple[int, ...]


TOOL_VERSION_POLICIES = {
    "verilator": ToolVersionPolicy("verilator", r"\bVerilator\s+(\d+)(?:\.(\d+))?", ("--version",), (5,), (5,)),
    "iverilog": ToolVersionPolicy("iverilog", r"\bIcarus Verilog version\s+(\d+)(?:\.(\d+))?", ("-V",), (12,), (12,)),
    "ghdl": ToolVersionPolicy("ghdl", r"\bGHDL\s+(\d+)(?:\.(\d+))?", ("--version",), (4,), (5,)),
    "sby": ToolVersionPolicy("sby", r"\bSBY\s+v?(\d+)\.(\d+)", ("--version",), (0, 67), (0, 67)),
    "yosys": ToolVersionPolicy("yosys", r"\bYosys\s+(\d+)\.(\d+)", ("-V",), (0, 33), (0, 33)),
    "z3": ToolVersionPolicy("z3", r"\bZ3 version\s+(\d+)\.(\d+)", ("--version",), (4, 8), (4, 8)),
}


def classify_tool_version(tool: str, version: str | None) -> dict[str, Any]:
    """Classify a version banner against the repository-tested range."""

    canonical = Path(tool).name
    policy = TOOL_VERSION_POLICIES.get(canonical)
    if policy is None:
        return {
            "tool": canonical,
            "status": "unqualified",
            "version": version,
            "detected": None,
            "minimum_tested": None,
            "maximum_tested": None,
            "reason": "no built-in tested version range is registered",
        }
    match = re.search(policy.pattern, version or "", flags=re.IGNORECASE)
    detected = tuple(int(item) for item in match.groups() if item is not None) if match else ()
    comparison_width = max(len(policy.minimum), len(policy.maximum))
    comparable = detected[:comparison_width]
    status = (
        "supported"
        if comparable
        and _pad(comparable, comparison_width) >= _pad(policy.minimum, comparison_width)
        and _pad(comparable, comparison_width) <= _pad(policy.maximum, comparison_width)
        else "unsupported"
        if detected
        else "unknown"
    )
    return {
        "tool": canonical,
        "status": status,
        "version": version,
        "detected": ".".join(str(item) for item in detected) if detected else None,
        "minimum_tested": ".".join(str(item) for item in policy.minimum),
        "maximum_tested": ".".join(str(item) for item in policy.maximum),
        "reason": None if status == "supported" else "detected version is outside the tested range",
    }


def probe_tool_version(command: str, *, timeout_seconds: float = 10.0) -> dict[str, Any]:
    """Read a configured executable's version without invoking a shell."""

    try:
        parts = shlex.split(command)
    except ValueError:
        parts = []
    if not parts:
        return classify_tool_version("", None)
    executable = parts[0]
    canonical = Path(executable).name
    policy = TOOL_VERSION_POLICIES.get(canonical)
    if policy is None:
        return classify_tool_version(canonical, None)
    try:
        completed = subprocess.run(
            (executable, *policy.version_args),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return classify_tool_version(canonical, None)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    banner = next((line.strip() for line in output.splitlines() if re.search(policy.pattern, line, re.I)), None)
    return classify_tool_version(canonical, banner)


def formal_dependency_qualifications(command: str) -> tuple[dict[str, Any], ...]:
    """Return the open-source tools implicitly used by a formal frontend."""

    try:
        parts = shlex.split(command)
    except ValueError:
        return ()
    if not parts or Path(parts[0]).name != "sby":
        return ()
    return (probe_tool_version("yosys"), probe_tool_version("z3"))


def _pad(value: tuple[int, ...], length: int) -> tuple[int, ...]:
    return value + (0,) * (length - len(value))
