"""Isolated CPU source conversion and resource-bounded SKY130 technology mapping."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.physical_design import file_digest, tcl_string, write_document
from dv_platform.signoff import read_document, verify_artifacts
from dv_platform.sky130 import create_project, snapshot_cpu


def prepare_cpu_project(
    source: Path,
    pdk: Path,
    output: Path,
    *,
    memory_mb: int = 6144,
    timeout: float = 86400,
    resume: bool = False,
) -> Path:
    if not 512 <= memory_mb <= 262144:
        raise ValueError("CPU synthesis needs a bounded memory budget")
    work = output / "source"
    metadata = _source_snapshot(source, output, resume)
    record: dict[str, Any] = {
        "status": "running",
        "source": metadata,
        "memory_mb": memory_mb,
        "signoff_approved": False,
        "stage": "synthesis",
    }
    write_document(output / "preparation.json", record)
    try:
        command = f"CPU_YOSYS=prlimit --as={address_space_limit(memory_mb)} --core=0 -- yosys"
        if not _completed_stage(work, "cpu-synthesis"):
            run_native(
                ("make", "cpu-synth", f"CPU_SYNTH_MEMORY_MB={memory_mb}", command),
                work,
                "cpu-synthesis",
                timeout=timeout,
                expected=("build/cpu/core.json", "build/cpu/optimized.il", "build/cpu/core.v"),
            )
        library = pdk / "libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
        library = library.resolve(strict=True)
        _map_cpu(work, library, memory_mb, timeout, output, record)
        metadata["mapped_sha256"] = file_digest(work / "mapped.v")
        source_files = {name: work / name for name in metadata["source_sha256"]}
        source_files.update(
            {
                "tools/synthesis.receipt.json": work / "cpu-synthesis.receipt.json",
                "tools/mapping-statistics.json": work / "mapping-statistics.json",
            }
        )
        source_files.update({path.name: path for path in work.glob("cpu-map*") if path.is_file()})
        path = create_project(
            output / "project",
            pdk,
            design="cpu_top",
            reference=work / "build/cpu/core.v",
            mapped=work / "mapped.v",
            source_files=source_files,
            source_metadata=metadata,
        )
        record.update(status="prepared", stage="complete", project=str(path))
        return path
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record.update(status="incomplete", error=str(error))
        raise
    finally:
        write_document(output / "preparation.json", record)


def _source_snapshot(source: Path, output: Path, resume: bool) -> dict[str, Any]:
    if resume:
        work = output / "source"
        metadata = read_document(work / "source-snapshot.json")
        verify_artifacts(work, metadata["source_sha256"])
        return metadata
    output.mkdir(parents=True, exist_ok=False)
    return snapshot_cpu(source, output / "source")


def _completed_stage(work: Path, name: str, inputs: dict[str, str] | None = None) -> bool:
    path = work / f"{name}.receipt.json"
    if not path.exists():
        return False
    receipt = read_document(path)
    if receipt["status"] != "passed":
        return False
    if inputs is not None and receipt.get("inputs") != inputs:
        return False
    verify_artifacts(work, receipt["artifacts"])
    return True


def _mapping_script(rtlil: Path, library: Path) -> str:
    return "\n".join(
        [
            f"read_rtlil {tcl_string(str(rtlil.resolve()))}",
            "hierarchy -check -top cpu_top",
            f"dfflibmap -liberty {tcl_string(str(library))}",
            f"abc -liberty {tcl_string(str(library))}",
            "hilomap -hicell sky130_fd_sc_hd__conb_1 HI -locell sky130_fd_sc_hd__conb_1 LO",
            "clean -purge",
            f"read_liberty -lib {tcl_string(str(library))}",
            "check -mapped -assert",
            f"tee -o mapping-statistics.json stat -json -liberty {tcl_string(str(library))} -top cpu_top",
            "write_verilog -noattr mapped.v",
            "write_json mapped.json",
            "",
        ]
    )


def _map_cpu(work, library, memory_mb, timeout, output, record) -> None:
    stages = (
        (
            "cpu-map-coarse",
            "build/cpu/optimized.il",
            ("mapped-coarse.il",),
            "opt_clean -purge\nsynth -top cpu_top -noshare -noabc -run begin:coarse\nwrite_rtlil mapped-coarse.il\n",
        ),
        (
            "cpu-map-memory",
            "mapped-coarse.il",
            ("mapped-memory.il",),
            "opt -fast -full\nmemory_map\nopt -full\nwrite_rtlil mapped-memory.il\n",
        ),
        (
            "cpu-map-fine",
            "mapped-memory.il",
            ("mapped-generic.il",),
            "techmap -extern\ntechmap\nopt -fast\nflatten N:$extern:*\nopt -fast -keepdc\n"
            "hierarchy -check -top cpu_top\ncheck -assert\n"
            # Allow generic bit gates and defined hierarchy, but reject unresolved coarse cells.
            "select -assert-none t:$* t:$_* %d t:$* %M %C %d\nwrite_rtlil mapped-generic.il\n",
        ),
        ("cpu-mapping", "mapped-generic.il", ("mapped.v", "mapped.json", "mapping-statistics.json"), None),
    )
    for name, source, expected, commands in stages:
        record["stage"] = name
        write_document(output / "preparation.json", record)
        script = (
            f"read_rtlil {tcl_string(str((work / source).resolve()))}\nhierarchy -check -top cpu_top\n" + commands
            if commands is not None
            else _mapping_script(work / source, library)
        )
        _mapping_stage(work, name, source, library, script, expected, memory_mb, timeout)


def _mapping_stage(work, name, source, library, commands, expected, memory_mb, timeout) -> None:
    limiter, yosys = shutil.which("prlimit"), shutil.which("yosys")
    if limiter is None or yosys is None:
        raise ValueError("CPU mapping requires prlimit and Yosys")
    script = work / f"{name}.ys"
    script.write_text(commands)
    files = {source: work / source, script.name: script, "library": library, "yosys": Path(yosys)}
    inputs = {key: file_digest(path) for key, path in files.items()}
    if _completed_stage(work, name, inputs):
        return
    receipt = run_native(
        (limiter, f"--as={address_space_limit(memory_mb)}", "--core=0", "--", yosys, "-Q", "-T", "-s", script.name),
        work,
        name,
        timeout=timeout,
        expected=expected,
    )
    if any(file_digest(path) != inputs[key] for key, path in files.items()):
        raise ValueError("CPU mapping inputs changed during execution")
    receipt["inputs"] = inputs
    write_document(work / f"{name}.receipt.json", receipt)
