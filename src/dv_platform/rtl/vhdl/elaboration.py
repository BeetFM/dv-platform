"""GHDL-backed authoritative VHDL elaboration validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dv_platform.rtl.vhdl.normalization import VHDLNormalizationError


def validate_vhdl_elaboration(
    source_files: tuple[Path, ...], units: tuple[str, ...], work_dir: Path, executable: str = "ghdl"
) -> str:
    """Use GHDL as the authoritative VHDL analyzer/elaborator for mixed projects."""

    work_dir.mkdir(parents=True, exist_ok=True)
    version = subprocess.run((executable, "--version"), check=False, capture_output=True, text=True)
    if version.returncode != 0:
        raise VHDLNormalizationError(version.stderr.strip() or f"{executable} is unavailable")
    analyze = subprocess.run(
        (executable, "-a", "--std=08", f"--workdir={work_dir}", *(str(path) for path in source_files)),
        check=False,
        capture_output=True,
        text=True,
    )
    if analyze.returncode != 0:
        raise VHDLNormalizationError("GHDL analysis failed: " + (analyze.stderr.strip() or analyze.stdout.strip()))
    for unit in units:
        elaborate = subprocess.run(
            (executable, "-e", "--std=08", f"--workdir={work_dir}", unit),
            check=False,
            capture_output=True,
            text=True,
        )
        if elaborate.returncode != 0:
            raise VHDLNormalizationError(
                f"GHDL elaboration failed for {unit}: " + (elaborate.stderr.strip() or elaborate.stdout.strip())
            )
    return version.stdout.splitlines()[0].strip() or "GHDL unknown"
