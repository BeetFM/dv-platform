"""Reproducible broad-GA benchmark runner and evidence codec."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from defusedxml import ElementTree
from pypdf import PdfReader

from dv_platform.core.io import atomic_write_json


def run_benchmark(
    *,
    repo_root: Path,
    rtl: Path,
    xml: Path,
    pdf: Path,
    output: Path,
    profile: str,
    wheel: Path | None = None,
) -> dict[str, Any]:
    """Measure fixed input identities using bounded streaming operations."""

    inputs = {"rtl": rtl.resolve(), "xml": xml.resolve(), "pdf": pdf.resolve()}
    for name, path in inputs.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"benchmark {name} input must be a regular file: {path}")
    fingerprints = {
        name: {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in inputs.items()
    }
    stages = {
        "rtl_scan": _measure(lambda: _line_count(inputs["rtl"])),
        "xml_parse": _measure(lambda: _xml_count(inputs["xml"])),
        "pdf_parse": _measure(lambda: _pdf_count(inputs["pdf"])),
    }
    rtl_lines = int(stages["rtl_scan"].pop("units"))
    stages["xml_parse"].pop("units")
    stages["pdf_parse"].pop("units")
    result: dict[str, Any] = {
        "schema_version": 2,
        "profile": profile,
        "platform": detect_platform(),
        "platform_identity": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "kernel": platform.version(),
        },
        "commit": _git(repo_root, "rev-parse", "HEAD"),
        "worktree_clean": _git_status_clean(repo_root),
        "wheel": None if wheel is None else {"path": str(wheel.resolve()), "sha256": _sha256(wheel)},
        "inputs": {
            "rtl_lines": rtl_lines,
            "xml_bytes": inputs["xml"].stat().st_size,
            "pdf_bytes": inputs["pdf"].stat().st_size,
        },
        "input_fingerprints": fingerprints,
        "tool_versions": {
            "python": platform.python_version(),
            "defusedxml": importlib.metadata.version("defusedxml"),
            "pypdf": importlib.metadata.version("pypdf"),
            **_tool_versions(("verilator", "slang", "surelog", "ghdl")),
        },
        "stages": stages,
        "reproducibility": {
            "hash_algorithm": "sha256",
            "python_hash_seed": os.environ.get("PYTHONHASHSEED", "unset"),
            "command": "dv-enterprise benchmark",
        },
    }
    atomic_write_json(output, result)
    return result


def detect_platform() -> str:
    release = platform.release().lower()
    os_release = Path("/etc/os-release").read_text(encoding="utf-8") if Path("/etc/os-release").is_file() else ""
    if "ubuntu" not in os_release.lower() or 'VERSION_ID="24.04"' not in os_release:
        raise ValueError("benchmark qualification requires Ubuntu 24.04")
    return "wsl2-ubuntu-24.04" if "microsoft" in release else "ubuntu-24.04"


def _measure(operation: Callable[[], int]) -> dict[str, float | int]:
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter_ns()
    units = operation()
    elapsed = max((time.perf_counter_ns() - started) / 1_000_000_000, 0.000001)
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 if sys.platform != "darwin" else 1024 * 1024
    return {"runtime_seconds": elapsed, "peak_rss_mb": max(after, before, 1) / divisor, "units": units}


def _line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def _xml_count(path: Path) -> int:
    count = 0
    for _event, element in ElementTree.iterparse(path, events=("end",)):
        count += 1
        element.clear()
    return count


def _pdf_count(path: Path) -> int:
    reader = PdfReader(path, strict=True)
    return sum(len(page.extract_text() or "") for page in reader.pages)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", *arguments), cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _git_status_clean(root: Path) -> bool:
    result = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0 and not result.stdout


def _tool_versions(names: tuple[str, ...]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in names:
        try:
            result = subprocess.run(
                (name, "--version"),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            versions[name] = "unavailable"
        else:
            versions[name] = result.stdout.splitlines()[0][:256] if result.stdout else f"exit-{result.returncode}"
    return versions


def load_benchmark(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark result must be an object")
    return value
