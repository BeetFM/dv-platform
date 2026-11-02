"""Bounded native verification with fresh outputs and process-group cleanup."""

from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dv_platform.enterprise.adapters import _stop_process, _wait_process
from dv_platform.physical_design import file_digest, project_input, write_document


def address_space_limit(memory_mb: int) -> int:
    """Keep the requested native ceiling within both inherited AS limits."""
    import resource

    inherited = resource.getrlimit(resource.RLIMIT_AS)
    return min([memory_mb * 1024 * 1024, *(value for value in inherited if value != resource.RLIM_INFINITY)])


def run_native(
    command: tuple[str, ...],
    work: Path,
    name: str,
    *,
    timeout: float = 3600,
    expected: tuple[str, ...] = (),
    check_output_errors: bool = True,
) -> dict[str, Any]:
    if not 0 < timeout <= 86400 or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("invalid native timeout or stage name")
    work.mkdir(parents=True, exist_ok=True)
    for relative in expected:
        target = work / relative
        if target.is_symlink() or not target.resolve().is_relative_to(work.resolve()):
            raise ValueError("native output escapes its workspace")
        target.unlink(missing_ok=True)
    stdout, stderr = work / f"{name}.stdout.log", work / f"{name}.stderr.log"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "HOME",
            "LD_LIBRARY_PATH",
            "TCL_LIBRARY",
            "TK_LIBRARY",
            "DISPLAY",
            "LANG",
            "LC_ALL",
        }
    }
    environment.update(OMP_NUM_THREADS="2", QT_QPA_PLATFORM="offscreen")
    status, code = "error", None
    try:
        with stdout.open("w") as out, stderr.open("w") as err:
            process = subprocess.Popen(
                command,
                cwd=work,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=environment,
                start_new_session=True,
                text=True,
            )
            try:
                code = _wait_process(process, timeout)
            except BaseException:
                _stop_process(process)
                raise
        if code != 0 or check_output_errors and (_tool_error(stdout) or _tool_error(stderr)):
            raise ValueError(f"native {name} failed (exit {code}); inspect {work}")
        for relative in expected:
            if project_input(work, relative).stat().st_size == 0:
                raise ValueError(f"native {name} produced an empty report: {relative}")
        status = "passed"
    finally:
        receipt = _write_receipt(work, name, status, code, command, expected)
    return receipt


def _write_receipt(
    work: Path, name: str, status: str, code: int | None, command: tuple[str, ...], expected: tuple[str, ...]
) -> dict[str, Any]:
    logs = (work / f"{name}.stdout.log", work / f"{name}.stderr.log")
    artifacts = {path.name: file_digest(path) for path in logs if path.is_file()}
    artifacts.update(
        {
            relative: file_digest(work / relative)
            for relative in expected
            if (work / relative).is_file() and not (work / relative).is_symlink()
        }
    )
    receipt = {"status": status, "returncode": code, "command": list(command), "artifacts": artifacts}
    write_document(work / f"{name}.receipt.json", receipt)
    return receipt


def _tool_error(path: Path) -> bool:
    with path.open("r", errors="replace") as stream:
        return any(re.match(r"\s*(?:ERROR:|Error:|\[ERROR\b)", line) for line in stream)


_WORKFLOW_MODULES = (
    "physical_design",
    "sky130",
    "signoff",
    "release",
    "signing",
    "product",
    "entitlement",
    "entitlement_leases",
    "ai.physical_design",
    "ai.rtl",
    "ai.gateway",
    "ai.model_client",
    "ai.optimization",
    "ai.code_graph",
    "ai.routing",
    "infrastructure.io",
    "infrastructure.security",
    "configuration.loading",
    "configuration.validation",
    "enterprise.physical_design",
    "enterprise.adapters",
    "enterprise.profiles",
    "enterprise.native",
    "enterprise.timing",
    "enterprise.equivalence",
    "enterprise.transition_equivalence",
    "enterprise.boolean_cones",
    "enterprise.cone_equivalence",
    "enterprise.layout",
    "enterprise.power",
    "enterprise.signoff",
    "enterprise.cpu",
    "enterprise.rtl",
    "enterprise.rtl_frontend",
    "enterprise.rtl_physical",
    "enterprise.rtl_optimization",
)


def _workflow_sources() -> dict[str, Path]:
    sources = {}
    for name in _WORKFLOW_MODULES:
        module = importlib.import_module("dv_platform." + name)
        if module.__file__ is None:
            raise ValueError("versioned implementation workflow requires inspectable module sources")
        sources[name.replace(".", "/") + ".py"] = Path(module.__file__)
    root = sources["physical_design.py"].parent
    sources.update({name: root / name for name in ("physical_design.tcl", "sky130_flow.tcl", "sky130-pin.json")})
    return sources


def snapshot_workflow(destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, mode=0o700)
    result = {}
    for name, source in _workflow_sources().items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        result[name] = file_digest(target)
    return result


def verify_current_workflow(expected: dict[str, str]) -> None:
    actual = {name: file_digest(source) for name, source in _workflow_sources().items()}
    if actual != expected:
        raise ValueError("implementation workflow changed after measurement; re-run the versioned flow")
