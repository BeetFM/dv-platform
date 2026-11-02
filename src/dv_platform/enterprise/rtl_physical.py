"""Map proven RTL into an operator-authored physical flow without relaxing constraints."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.enterprise.physical_design import _run_physical_optimization
from dv_platform.enterprise.rtl_frontend import validate_frontend
from dv_platform.enterprise.transition_equivalence import prove_mapped_equivalence as prove_equivalence
from dv_platform.physical_design import (
    _relative,
    file_digest,
    load_physical_project,
    project_input,
    tcl_string,
    write_document,
)
from dv_platform.signoff import identity, read_document


def load_rtl_project(path: Path) -> dict[str, Any]:
    project = read_document(path, maximum=1048576)
    fields = {
        "schema_version",
        "design",
        "sources",
        "documents",
        "physical_project",
        "netlist",
        "mapping_library",
        "objective",
    }
    optional = {"frontend", "editable_sources", "memory_mb"}
    if (
        not fields <= set(project) <= fields | optional
        or type(project["schema_version"]) is not int
        or project["schema_version"] != 1
    ):
        raise ValueError("RTL project has unknown, missing, or unsupported fields")
    identity(project["design"])
    for key in ("sources", "documents"):
        values = project[key]
        if not isinstance(values, list) or not 1 <= len(values) <= 256:
            raise ValueError("RTL project needs bounded source and document lists")
        for name in values:
            project_input(path.parent, name)
    _validate_execution(project, path.parent)
    physical_path = project_input(path.parent, project["physical_project"])
    physical = load_physical_project(physical_path)
    if physical["design"] != project["design"]:
        raise ValueError("RTL and physical design names differ")
    if project["mapping_library"] not in physical["libraries"]:
        raise ValueError("RTL mapping library must be a declared physical timing library")
    protected = {physical["flow"], *physical["libraries"], *physical["constraints"]}
    protected.update(physical.get(key) for key in ("technology_lock", "signoff_policy", "reference_netlist"))
    if project["netlist"] not in physical["inputs"] or project["netlist"] in protected:
        raise ValueError("RTL netlist must name an unprotected physical input")
    if project["objective"] not in {"setup_wns_ns", "area_um2", "power_watts"}:
        raise ValueError("RTL objective must be setup_wns_ns, area_um2, or power_watts")
    return project


def _validate_execution(project, root: Path) -> None:
    if "frontend" in project:
        validate_frontend(root, project["frontend"])
    editable = project.get("editable_sources", project["sources"])
    if (
        not isinstance(editable, list)
        or not editable
        or any(not isinstance(name, str) for name in editable)
        or len(set(editable)) != len(editable)
        or not set(editable) <= set(project["sources"])
    ):
        raise ValueError("RTL editable_sources must uniquely select declared sources")
    memory = project.get("memory_mb", 6144)
    if type(memory) is not int or not 256 <= memory <= 262144:
        raise ValueError("RTL memory_mb must be within 256..262144 MiB")


def freeze_physical_project(project_path: Path, output: Path) -> dict[str, Any]:
    project = load_physical_project(project_path)
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in project["inputs"]:
        source = project_input(project_path.parent, name)
        expected = file_digest(source)
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if file_digest(destination) != expected or file_digest(source) != expected:
            raise ValueError("physical inputs changed during RTL snapshot capture")
        hashes[name] = expected
    write_document(output / "project.json", project)
    return hashes


def measure_rtl(
    config,
    project,
    template,
    logical: Path,
    output: Path,
    *,
    reference: Path | None = None,
    rtl_inputs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Prove logical-to-mapped and mapped-to-routed with an exact shared checkpoint."""
    physical = load_physical_project(template / "project.json")
    freeze_physical_project(template / "project.json", output / "project")
    workspace = output / "mapping"
    library = template / project["mapping_library"]
    _map_netlist(logical, library, project, workspace, physical["schema_version"] == 2)
    mapping_proof = prove_equivalence(
        logical,
        workspace / "mapped.v",
        [library],
        project["design"],
        output / "mapping-proof",
        ports_only=True,
        memory_mb=project.get("memory_mb", 6144),
    )
    shutil.copyfile(workspace / "mapped.v", output / "project" / project["netlist"])
    if physical["schema_version"] == 2:
        shutil.copyfile(reference or logical, output / "project" / physical["reference_netlist"])
    if rtl_inputs is not None:
        _attach_source_identity(output / "project", physical, reference or logical, logical, rtl_inputs)
    # The enclosing RTL run holds the entitlement lease across synthesis and replay.
    run = _run_physical_optimization(config, output / "project/project.json", False, 1, None)
    final = Path(run["best"]["directory"]) / "pd-export.v"
    final_proof = prove_equivalence(
        workspace / "mapped.v",
        final,
        [library],
        project["design"],
        output / "final-proof",
        ports_only=True,
        memory_mb=project.get("memory_mb", 6144),
    )
    if (
        mapping_proof["candidate_sha256"] != final_proof["reference_sha256"]
        or mapping_proof["libraries_sha256"] != final_proof["libraries_sha256"]
    ):
        raise ValueError("RTL proof chain changed the mapped netlist or functional libraries")
    return {
        "analysis": run["best"],
        "project": str((output / "project/project.json").resolve()),
        "run": str(Path(run["output"]) / "run.json"),
        "mapping_proof": mapping_proof,
        "final_proof": final_proof,
    }


def _map_netlist(logical, library, project, workspace, sky130: bool) -> None:
    workspace.mkdir()
    executable, limiter = shutil.which("yosys"), shutil.which("prlimit")
    if executable is None or limiter is None:
        raise ValueError("RTL mapping requires Yosys and prlimit")
    script = workspace / "map.ys"
    tie_mapping = "hilomap -hicell sky130_fd_sc_hd__conb_1 HI -locell sky130_fd_sc_hd__conb_1 LO\n" if sky130 else ""
    script.write_text(
        f"read_verilog -sv {tcl_string(str(logical.resolve()))}\n"
        f"synth -top {project['design']} -noabc\n"
        f"dfflibmap -liberty {tcl_string(str(library.resolve()))}\n"
        f"abc -liberty {tcl_string(str(library.resolve()))}\n"
        f"{tie_mapping}"
        "clean -purge\n"
        f"read_liberty -lib {tcl_string(str(library.resolve()))}\n"
        "check -mapped -assert\nwrite_verilog -noattr mapped.v\n"
    )
    run_native(
        (
            limiter,
            f"--as={address_space_limit(project.get('memory_mb', 6144))}",
            "--core=0",
            "--",
            executable,
            "-Q",
            "-T",
            "-s",
            script.name,
        ),
        workspace,
        "mapping",
        expected=("mapped.v",),
    )


def _attach_source_identity(root, physical, reference, logical, rtl_inputs) -> None:
    destination = root / "source/rtl-optimization"
    if destination.exists():
        raise ValueError("physical template overlaps RTL provenance inputs")
    hashes = {}
    for name, source in rtl_inputs.items():
        # These names originate in the validated source manifest, never in model prose.
        relative = "source/rtl-optimization/" + _relative(name)
        expected = file_digest(source)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if file_digest(target) != expected or file_digest(source) != expected:
            raise ValueError("RTL provenance changed during physical input capture")
        physical["inputs"].append(relative)
        hashes[relative] = expected
    metadata = {
        "kind": "rtl_optimization",
        "baseline_reference_sha256": file_digest(reference),
        "candidate_logical_sha256": file_digest(logical),
        "rtl_inputs_sha256": hashes,
    }
    if physical["schema_version"] == 2:
        path = root / "source-snapshot.json"
        if path.is_file():
            metadata["template_source_metadata"] = read_document(path)
        else:
            physical["inputs"].append("source-snapshot.json")
    else:
        path = destination / "source-snapshot.json"
        physical["inputs"].append(path.relative_to(root).as_posix())
    write_document(path, metadata)
    write_document(root / "project.json", physical)
