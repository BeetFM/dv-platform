"""Pinned full-layout DRC, transistor LVS, and density verification."""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import run_native
from dv_platform.physical_design import project_input, tcl_string
from dv_platform.signoff import read_document
from dv_platform.sky130 import validate_tool_fingerprints


def stream_layout(work: Path, project: dict[str, Any], stage: Path) -> list[str]:
    validate_tool_fingerprints(work, project, ("klayout",))
    script = stage / "stream.rb"
    mapping = stage / "stream.map"
    mapping.write_text(
        (work / "technology/klayout/sky130A.map").read_text()
        + "\n"
        + "\n".join(f"met{index} FILL {67 + index} 20" for index in range(1, 6))
        + "\n"
    )
    script.write_text(
        _STREAM.replace("@DEF@", repr(str(work / project["deliverables"]["def"])))
        .replace("@TOP@", repr(project["design"]))
        .replace("@ROOT@", repr(str(work)))
        .replace("@GDS@", repr(str(work / project["deliverables"]["gds"])))
        .replace("@MAP@", repr(str(mapping)))
    )
    output = project["deliverables"]["gds"]
    run_native((_tool("klayout"), "-b", "-r", str(script)), work, stage.name + "-stream", expected=(output,))
    return [
        output,
        script.relative_to(work).as_posix(),
        mapping.relative_to(work).as_posix(),
        f"{stage.name}-stream.receipt.json",
    ]


def klayout_drc(work: Path, project: dict[str, Any], stage: Path) -> dict[str, Any]:
    validate_tool_fingerprints(work, project, ("klayout",))
    report = stage / "drc.rdb"
    relative = report.relative_to(work).as_posix()
    command = (
        _tool("klayout"),
        "-b",
        "-r",
        "technology/klayout/sky130A_mr.drc",
        "-rd",
        "input=" + project["deliverables"]["gds"],
        "-rd",
        "top_cell=" + project["design"],
        "-rd",
        "report=" + str(report.resolve()),
        "-rd",
        "feol=true",
        "-rd",
        "beol=true",
        "-rd",
        "offgrid=true",
        "-rd",
        "floating_met=true",
        "-rd",
        "sram_exclude=false",
        "-rd",
        "seal=false",
        "-rd",
        "thr=2",
    )
    run_native(command, work, stage.name + "-drc", timeout=86400, expected=(relative,))
    count = parse_drc_report(report)
    return {"violations": count}


def parse_drc_report(path: Path) -> int:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("layout DRC report exceeds the parsing bound")
    root = ET.fromstring(path.read_bytes())
    items = root.find("items")
    if root.tag != "report-database" or items is None or root.find("cells") is None:
        raise ValueError("layout DRC report is incomplete")
    return len(items)


def magic_extract(work: Path, project: dict[str, Any], stage: Path) -> dict[str, Any]:
    validate_tool_fingerprints(work, project, ("magic",))
    script = stage / "magic.tcl"
    output = (stage / "magic.json").relative_to(work).as_posix()
    spice = (stage / "layout.spice").relative_to(work).as_posix()
    details = (stage / "drc-details.txt").relative_to(work).as_posix()
    feedback = (stage / "antenna-feedback.tcl").relative_to(work).as_posix()
    script.write_text(
        "\n".join(
            [
                "crashbackups stop",
                "drc off",
                f"tech load {tcl_string(str(work / 'technology/magic/sky130A.tech'))}",
                f"gds read {tcl_string(project['deliverables']['gds'])}",
                f"load {tcl_string(project['design'])}",
                "select top cell",
                "expand",
                "drc euclidean on",
                "drc style drc(full)",
                "drc check",
                "drc catchup",
                "set violations [drc list count total]",
                f"set details [open {tcl_string(details)} w]",
                "puts $details [drc listall why]",
                "close $details",
                "drc off",
                "extract do all",
                # LVS discards these capacitances; timing uses independent OpenRCX SPEFs.
                "extract no capacitance",
                "extract no coupling",
                "extract do local",
                "extract unique",
                "extract all",
                "ext2spice lvs",
                f"ext2spice -o {tcl_string(spice)}",
                "feedback clear",
                "antennacheck",
                "set antennas [feedback count]",
                f"feedback save {tcl_string(feedback)}",
                f"set antenna_details [open {tcl_string(feedback)} a]",
                'puts $antenna_details "# Total antenna feedback entries: $antennas"',
                "close $antenna_details",
                f"set report [open {tcl_string(output)} w]",
                'puts $report [format {{"drc_violations":%d,"antenna_violations":%d,"complete":true}} $violations $antennas]',
                "close $report",
                "quit -noprompt",
                "",
            ]
        )
    )
    run_native(
        (_tool("magic"), "-dnull", "-noconsole", "-rcfile", "/dev/null", str(script)),
        work,
        stage.name + "-magic",
        timeout=86400,
        expected=(output, spice, details, feedback),
    )
    metrics = read_document(work / output)
    if metrics.get("complete") is not True:
        raise ValueError("Magic verification did not finish")
    for key in ("drc_violations", "antenna_violations"):
        if type(metrics.get(key)) is not int or metrics[key] < 0:
            raise ValueError("invalid Magic violation count")
    return metrics


def netgen_lvs(work: Path, project: dict[str, Any], stage: Path) -> dict[str, Any]:
    validate_tool_fingerprints(work, project, ("netgen", "openroad"))
    script, cdl = stage / "reference.tcl", stage / "reference.cdl"
    script.write_text(
        f"read_db {tcl_string(project['deliverables']['odb'])}\n"
        f"write_cdl -include_fillers -masters technology/cells.cdl {tcl_string(str(cdl))}\n"
    )
    run_native(
        (_tool("openroad"), "-no_init", "-exit", str(script)),
        work,
        stage.name + "-cdl",
        expected=(cdl.relative_to(work).as_posix(),),
    )
    reference = stage / "reference.spice"
    reference.write_text(f'.include "{work / "technology/cells.spice"}"\n.include "{cdl}"\n')
    setup = stage / "lvs-setup.tcl"
    setup.write_text(
        "source technology/netgen/setup.tcl\n"
        "foreach {dev kind} {sky130_fd_pr__nfet_01v8 nmos sky130_fd_pr__special_nfet_01v8 nmos "
        "sky130_fd_pr__pfet_01v8_hvt pmos sky130_fd_pr__diode_pw2nd_05v5 diode} {\n"
        "  foreach circuit {1 2} {\n"
        '    if {[lsearch [set cells$circuit] $dev] >= 0} { model "-circuit$circuit $dev" $kind }\n'
        "  }\n}\n"
    )
    report = stage / "lvs.log"
    run_native(
        (
            _tool("netgen"),
            "-batch",
            "lvs",
            f"{stage / 'layout.spice'} {project['design']}",
            f"{reference} {project['design']}",
            str(setup),
            str(report),
        ),
        work,
        stage.name + "-lvs",
        timeout=86400,
        expected=(report.relative_to(work).as_posix(),),
    )
    text = report.read_text()
    if not _matched_netgen_report(text):
        raise ValueError("transistor layout-versus-schematic equivalence did not pass")
    return {"matched_uniquely": True}


def _matched_netgen_report(text: str) -> bool:
    matched = len(re.findall(r"^Final result: (?:Circuits|Netlists) match uniquely\.[ \t]*$", text, re.M)) == 1
    return matched and not any(
        error in text.lower() for error in ("do not match", "black box", "placeholder", "property errors")
    )


def density_check(work: Path, project: dict[str, Any], stage: Path) -> dict[str, Any]:
    validate_tool_fingerprints(work, project, ("magic",))
    gds = project_input(work, project["deliverables"]["gds"])
    temporary = stage / f"{project['design']}.gds"
    shutil.copyfile(gds, temporary)
    rc = stage / ".magicrc"
    rc.write_text(f"tech load {tcl_string(str(work / 'technology/magic/sky130A.tech'))}\n")
    log = work / f"{stage.name}-density.stdout.log"
    try:
        run_native(
            (_tool("python3"), "technology/magic/check_density.py", temporary.relative_to(work).as_posix()),
            work,
            stage.name + "-density",
            timeout=86400,
            check_output_errors=False,
        )
    except ValueError as error:
        output = log.read_text() if log.exists() else ""
        if "Layout is < 700um x 700um" in output and "couldn't be read" not in output:
            raise RuntimeError("block is below the pinned density deck's supported window") from error
        raise
    finally:
        temporary.unlink(missing_ok=True)
    text = log.read_text()
    if "Whole-chip density results:" not in text or "Density results (total tiles = " not in text:
        raise ValueError("density analysis is incomplete or the block is below the deck's supported window")
    return {"complete": True, "violations": len(re.findall(r"(?:ERROR|FAILURE):", text, re.IGNORECASE))}


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"native sign-off requires {name}")
    return executable


_STREAM = r"""
root = @ROOT@
layout = RBA::Layout.new
options = RBA::LoadLayoutOptions.new
options.lefdef_config.lef_files = [root + "/technology/tech.lef", root + "/technology/cells.lef"]
options.lefdef_config.read_lef_with_def = true
options.lefdef_config.map_file = @MAP@
options.lefdef_config.produce_pins = true
options.lefdef_config.produce_labels = true
options.lefdef_config.produce_blockages = false
options.lefdef_config.produce_cell_outlines = false
layout.read(@DEF@, options)
library = RBA::Layout.new
library.read(root + "/technology/cells.gds")
library.each_cell do |cell|
  target = layout.cell(cell.name)
  target.clear if target
end
layout.read(root + "/technology/cells.gds")
top = layout.cell(@TOP@)
raise "missing or empty implementation top" if top.nil? || top.bbox.empty?
empty = []
layout.each_cell { |cell| empty << cell.name if cell.is_empty? }
raise "unresolved layout cells: #{empty.join(',')}" unless empty.empty?
# Materialize routed vias so extraction sees their cross-layer connectivity before uniquifying labels.
vias = []
top.each_inst { |inst| vias << inst if inst.cell.name.start_with?("VIA_") }
layout.update
layout.start_changes
begin
  vias.each { |inst| inst.flatten }
ensure
  layout.end_changes
end
layout.update
top.write(@GDS@)
"""
