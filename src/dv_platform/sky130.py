"""Materialize pinned SKY130 projects and explicit, initially unsigned requirements."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dv_platform.physical_design import _relative, file_digest, project_input, tcl_string, write_document
from dv_platform.signoff import LIMIT_FIELDS, PVT_CORNERS, RC_CORNERS, REQUIRED_CHECKS, SKY130_REVISION, identity

PDK_ASSETS = {
    "technology/tech.lef": "libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef",
    "technology/cells.lef": "libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef",
    "technology/cells.gds": "libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds",
    "technology/cells.cdl": "libs.ref/sky130_fd_sc_hd/cdl/sky130_fd_sc_hd.cdl",
    "technology/cells.spice": "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice",
    "technology/magic/sky130A.tech": "libs.tech/magic/sky130A.tech",
    "technology/magic/sky130A-GDS.tech": "libs.tech/magic/sky130A-GDS.tech",
    "technology/magic/check_density.py": "libs.tech/magic/check_density.py",
    "technology/netgen/setup.tcl": "libs.tech/netgen/sky130A_setup.tcl",
    "technology/klayout/sky130A_mr.drc": "libs.tech/klayout/drc/sky130A_mr.drc",
    "technology/klayout/sky130A.map": "libs.tech/klayout/tech/sky130A.map",
    "technology/tracks.info": "libs.tech/openlane/sky130_fd_sc_hd/tracks.info",
    "technology/no_synth.cells": "libs.tech/openlane/sky130_fd_sc_hd/no_synth.cells",
}
PDK_ASSETS.update(
    {f"technology/lib/{pvt}.lib": f"libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__{pvt}.lib" for pvt in PVT_CORNERS}
)
PDK_ASSETS.update(
    {f"technology/rules.{rc}": f"libs.tech/openlane/rules.openrcx.sky130A.{rc}.spef_extractor" for rc in RC_CORNERS}
)


def materialize_technology(pdk: Path, target: Path) -> dict[str, str]:
    files = {}
    for name, relative in PDK_ASSETS.items():
        source = pdk / relative
        if not source.is_file() or not source.resolve().is_relative_to(pdk.resolve()):
            raise ValueError(f"pinned SKY130 asset is missing or escapes the PDK: {relative}")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        files[name] = file_digest(destination)
    return files


def tool_fingerprints() -> dict[str, Any]:
    tools = {}
    for name in ("openroad", "sta", "yosys", "magic", "klayout", "netgen"):
        executable = shutil.which(name)
        if executable is None:
            if name in {"openroad", "sta", "yosys"}:
                raise ValueError(f"SKY130 preparation requires {name}")
            continue
        options = {
            "magic": ("--version",),
            "yosys": ("-V",),
            "netgen": ("-batch",),
            "klayout": ("-v",),
            "sta": ("-no_init", "-exit", os.devnull),
        }.get(name, ("-version",))
        result = subprocess.run(
            (executable, *options),
            input="quit\n",
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env={
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "HOME", "LD_LIBRARY_PATH", "TCL_LIBRARY", "TK_LIBRARY", "LANG", "LC_ALL"}
            },
        )
        version = (result.stdout or result.stderr).strip()
        if not version:
            raise ValueError(f"{name} returned no tool identity")
        tools[name] = {"version": version.splitlines()[0], "sha256": file_digest(Path(executable))}
    return tools


def create_project(
    output: Path,
    pdk: Path,
    *,
    design: str,
    reference: Path,
    mapped: Path,
    source_files: dict[str, Path] | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> Path:
    identity(design)
    for name in source_files or {}:
        _relative(name)
    output.mkdir(parents=True, exist_ok=False)
    assets = materialize_technology(pdk, output)
    assets.update(_write_flow_assets(output))
    tools = tool_fingerprints()
    write_document(
        output / "technology-lock.json",
        {
            "schema_version": 1,
            "pdk": "sky130A",
            "library": "sky130_fd_sc_hd",
            "revision": SKY130_REVISION,
            "files": assets,
            "tools": tools,
        },
    )
    shutil.copyfile(reference, output / "reference.v")
    shutil.copyfile(mapped, output / "mapped.v")
    inputs = [
        *assets,
        "technology-lock.json",
        "reference.v",
        "mapped.v",
        "flow.tcl",
        "functional.sdc",
        "requirements.json",
    ]
    for name, source in (source_files or {}).items():
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        inputs.append("source/" + name)
    write_document(output / "source-snapshot.json", source_metadata or {"design": design})
    inputs.append("source-snapshot.json")
    (output / "functional.sdc").write_text(_CHARACTERIZATION_SDC)
    (output / "flow.tcl").write_text(
        Path(__file__).with_name("sky130_flow.tcl").read_text().replace("@DESIGN@", design)
    )
    project = {
        "schema_version": 2,
        "design": design,
        "flow": "flow.tcl",
        "inputs": inputs,
        "constraints": ["functional.sdc"],
        "libraries": [f"technology/lib/{pvt}.lib" for pvt in PVT_CORNERS],
        "parasitics": "results/design.nom.spef",
        "technology_lock": "technology-lock.json",
        "reference_netlist": "reference.v",
        "signoff_policy": "requirements.json",
        "activity": None,
        "deliverables": {
            "gds": "results/design.gds",
            "netlist": "pd-export.v",
            "def": "pd-final.def",
            "odb": "pd-final.odb",
        },
        "scenarios": [
            {
                "name": f"functional_{pvt}_{rc}",
                "mode": "functional",
                "pvt": pvt,
                "rc": rc,
                "libraries": [f"technology/lib/{pvt}.lib"],
                "constraints": ["functional.sdc"],
                "parasitics": f"results/design.{rc}.spef",
            }
            for pvt in PVT_CORNERS
            for rc in RC_CORNERS
        ],
    }
    write_document(output / "requirements.json", draft_requirements(output, project))
    path = output / "project.json"
    write_document(path, project)
    return path


def _write_flow_assets(root: Path) -> dict[str, str]:
    tracks: dict[str, dict[str, tuple[float, float]]] = {}
    for line in (root / "technology/tracks.info").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        layer, direction, offset, pitch = line.split()
        axis = direction.lower()
        if axis not in {"x", "y"} or float(pitch) <= 0 or float(offset) < 0:
            raise ValueError("invalid pinned routing track specification")
        tracks.setdefault(layer, {})[axis] = (float(offset), float(pitch))
    commands = []
    for layer, axes in tracks.items():
        if set(axes) != {"x", "y"}:
            raise ValueError("routing tracks must cover both axes")
        options = " ".join(f"-{axis}_offset {offset} -{axis}_pitch {pitch}" for axis, (offset, pitch) in axes.items())
        commands.append(f"make_tracks {tcl_string(layer)} {options}")
    (root / "tracks.tcl").write_text("\n".join(commands) + "\n")
    layers = {
        name: {
            "layer": layer,
            "name": name,
            "dir": direction,
            "datatype": 20,
            "space_to_outline": 10,
            "non-opc": {
                "datatype": 20,
                "width": [width],
                "height": [width],
                "space_to_fill": gap,
                "space_to_non_fill": 3.0,
            },
        }
        for name, layer, direction, width, gap in (
            ("met1", 68, "H", 0.58, 0.3),
            ("met2", 69, "V", 0.58, 0.3),
            ("met3", 70, "H", 0.58, 0.3),
            ("met4", 71, "V", 0.58, 0.3),
            ("met5", 72, "H", 3.0, 1.6),
        )
    }
    write_document(root / "technology/fill.json", {"layers": layers, "outline": {"layer": 235, "datatype": 4}})
    return {name: file_digest(root / name) for name in ("tracks.tcl", "technology/fill.json")}


def draft_requirements(root: Path, project: dict[str, Any]) -> dict[str, Any]:
    current = datetime.now(UTC)
    limits: dict[str, float | None] = {key: None for key in LIMIT_FIELDS}
    limits.update(setup_margin_ns=0.0, hold_margin_ns=0.0)
    return {
        "schema_version": 1,
        "design": project["design"],
        "technology_sha256": file_digest(root / project["technology_lock"]),
        "scenarios": [scenario["name"] for scenario in project["scenarios"]],
        "limits": limits,
        "boundary": {
            "complete": False,
            "constraints_sha256": {name: file_digest(root / name) for name in project["constraints"]},
            "assumptions": [
                "100 ns exploratory clock; boundary delays and loads require engineering specification",
                "50 percent initial core utilization; standard-cell memory implementation",
                "No clock exceptions, functional certification, or manufacturing acceptance inferred",
            ],
        },
        "supplies": {"VPWR": {"voltage": 1.8, "sources": None}, "VGND": {"voltage": 0.0, "sources": None}},
        "activity_min_coverage_percent": 95.0,
        "metal_thickness_um": {},
        "required_checks": list(REQUIRED_CHECKS),
        "generated_at": current.isoformat(),
        "expires_at": (current + timedelta(days=7)).isoformat(),
        "signature": None,
    }


def validate_tool_fingerprints(project_root: Path, project: dict[str, Any], names: tuple[str, ...]) -> None:
    from dv_platform.signoff import read_document

    locked = read_document(project_root / project["technology_lock"])["tools"]
    for name in names:
        executable = shutil.which(name)
        if name not in locked or executable is None:
            raise FileNotFoundError(f"native tool {name} is unavailable or has not been pinned")
        if file_digest(Path(executable)) != locked[name]["sha256"]:
            raise ValueError(f"native tool {name} is missing or differs from the technology lock")


def snapshot_cpu(source: Path, destination: Path) -> dict[str, Any]:
    source = source.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    names = {"Makefile", "tools.lock.json"}
    names.update(
        p.relative_to(source).as_posix()
        for folder in ("rtl", "third_party", "synth")
        for p in (source / folder).rglob("*")
        if p.is_file() and p.suffix in {".sv", ".svh", ".v", ".vh", ".py", ".ys"}
    )
    before = {name: file_digest(project_input(source, name)) for name in sorted(names)}
    for name in sorted(names):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    if any(
        file_digest(source / name) != expected or file_digest(destination / name) != expected
        for name, expected in before.items()
    ):
        raise ValueError("CPU sources changed while creating their immutable snapshot")
    revision = subprocess.check_output(("git", "-C", str(source), "rev-parse", "HEAD"), text=True, timeout=10).strip()
    metadata = {
        "repository": "https://github.com/varrahan/cpu",
        "base_revision": revision,
        "design": "cpu_top",
        "scope": "cpu_block",
        "source_sha256": before,
    }
    write_document(destination / "source-snapshot.json", metadata)
    return metadata


_CHARACTERIZATION_SDC = """# Provisional characterization only; no approved boundary assumptions.
create_clock -name clk -period 100.000 [get_ports clk]
set_clock_uncertainty 0.100 [get_clocks clk]
set data_inputs [list]
foreach port [all_inputs] {
  if {[get_full_name $port] ne "clk"} { lappend data_inputs $port }
}
set_input_delay 0.000 -clock clk $data_inputs
set_output_delay 0.000 -clock clk [all_outputs]
set_input_transition 0.100 [all_inputs]
set_load 0.010 [all_outputs]
"""
