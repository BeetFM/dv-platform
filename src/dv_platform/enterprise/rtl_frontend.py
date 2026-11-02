"""Pinned SystemVerilog conversion for package-based RTL experiments."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.physical_design import file_digest, project_input
from dv_platform.signoff import digest


def validate_frontend(root: Path, spec: object) -> dict[str, Any]:
    if not isinstance(spec, dict) or set(spec) != {"kind", "executable", "sha256", "defines"}:
        raise ValueError("RTL frontend has unknown or missing fields")
    if spec["kind"] != "sv2v":
        raise ValueError("RTL frontend must be the pinned sv2v converter")
    digest(spec["sha256"])
    tool = project_input(root, spec["executable"])
    if not 0 < tool.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError("RTL frontend executable exceeds its 64 MiB size bound")
    if file_digest(tool) != spec["sha256"]:
        raise ValueError("RTL frontend executable does not match its declared digest")
    defines = spec["defines"]
    if (
        not isinstance(defines, list)
        or not 1 <= len(defines) <= 32
        or any(
            not isinstance(item, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_]+)?", item) is None
            for item in defines
        )
        or len(set(defines)) != len(defines)
        or "SYNTHESIS" not in defines
    ):
        raise ValueError("RTL frontend needs unique bounded macro definitions including SYNTHESIS")
    return spec


def freeze_frontend(root: Path, spec: dict[str, Any], output: Path) -> dict[str, Any]:
    validate_frontend(root, spec)
    output.mkdir(parents=True, exist_ok=False)
    target = output / "sv2v"
    shutil.copyfile(root / spec["executable"], target)
    target.chmod(0o700)
    if file_digest(target) != spec["sha256"]:
        raise ValueError("RTL frontend changed during snapshot capture")
    return {**spec, "executable": str(target.resolve())}


def synthesis_source(text: str) -> str:
    # sv2v parses simulation-only text before Yosys can honor synthesis pragmas.
    return re.sub(
        r"(?ms)^[ \t]*//\s*(?:pragma|synopsys|synthesis)\s+translate_off\b.*?"
        r"^[ \t]*//\s*(?:pragma|synopsys|synthesis)\s+translate_on[^\n]*",
        "",
        text,
    )


def convert_sources(
    work: Path, sources: list[str], design: str, frontend: dict[str, Any], *, memory_mb: int = 6144
) -> Path:
    executable = Path(frontend["executable"])
    if file_digest(executable) != frontend["sha256"]:
        raise ValueError("pinned RTL frontend changed before conversion")
    limiter = shutil.which("prlimit")
    if limiter is None:
        raise ValueError("RTL conversion requires prlimit")
    directories = sorted({str(Path("inputs") / parent) for name in sources for parent in Path(name).parents})
    command = (
        limiter,
        f"--as={address_space_limit(memory_mb)}",
        "--core=0",
        "--",
        str(executable),
        "-w",
        "converted.v",
        "--top=" + design,
        *("-I" + name for name in directories),
        *("-D" + value for value in frontend["defines"]),
        *("inputs/" + name for name in sources if Path(name).suffix in {".v", ".sv"}),
        "+RTS",
        "-N2",
        f"-M{min(2048, memory_mb // 2)}m",
        "-RTS",
    )
    run_native(command, work, "sv2v", expected=("converted.v",))
    if file_digest(executable) != frontend["sha256"]:
        raise ValueError("pinned RTL frontend changed during conversion")
    return work / "converted.v"
