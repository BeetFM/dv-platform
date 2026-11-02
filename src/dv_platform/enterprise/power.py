"""Single-domain SKY130 power connectivity, static IR, and conservative grid EM bounds."""

from __future__ import annotations

import csv
import math
import shutil
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import run_native
from dv_platform.physical_design import finite_metric, project_input, tcl_string
from dv_platform.signoff import number, read_document
from dv_platform.sky130 import validate_tool_fingerprints


def electrical_connectivity(work: Path, project: dict[str, Any], stage: Path) -> dict[str, Any]:
    validate_tool_fingerprints(work, project, ("openroad",))
    script = stage / "electrical.py"
    report = stage / "electrical.json"
    script.write_text(
        _ELECTRICAL.replace("@ODB@", repr(str(work / project["deliverables"]["odb"]))).replace(
            "@REPORT@", repr(str(report))
        )
    )
    executable = shutil.which("openroad")
    if executable is None:
        raise FileNotFoundError("OpenROAD is unavailable")
    run_native(
        (executable, "-no_init", "-exit", "-python", str(script)),
        work,
        stage.name + "-erc",
        expected=(report.relative_to(work).as_posix(),),
    )
    data = read_document(report)
    if type(data.get("checked_power_pins")) is not int or data["checked_power_pins"] < 1:
        raise ValueError("electrical analysis inspected no power pins")
    if type(data.get("violations")) is not int or data["violations"] < 0:
        raise ValueError("invalid electrical violation count")
    return data


def analyze_power(work: Path, project: dict[str, Any], policy: dict[str, Any], stage: Path) -> dict[str, Any]:
    validate_tool_fingerprints(work, project, ("openroad",))
    supplies = policy["supplies"]
    if set(supplies) != {"VPWR", "VGND"} or any(supply["sources"] is None for supply in supplies.values()):
        raise FileNotFoundError("approved VPWR/VGND source locations are required for power integrity analysis")
    if number(supplies["VPWR"]["voltage"]) != 1.8 or number(supplies["VGND"]["voltage"]) != 0:
        raise ValueError("SKY130 HD power analysis requires a nominal 1.8 V supply and 0 V ground")
    for supply in supplies.values():
        if supply["sources"] not in project["inputs"]:
            raise ValueError("power source locations must be immutable project inputs")
        project_input(work, supply["sources"])
    views = {view["name"]: _analyze_power_view(work, project, supplies, view, stage) for view in project["scenarios"]}
    return {
        "worst_ir_drop_v": max(view["worst_ir_drop_v"] for view in views.values()),
        "max_current_a": max(view["max_current_a"] for view in views.values()),
        "em_segments": sum(view["em_segments"] for view in views.values()),
        "scenarios": views,
    }


def _analyze_power_view(
    work: Path, project: dict[str, Any], supplies: dict[str, Any], view: dict[str, Any], stage: Path
) -> dict[str, Any]:
    stage = stage / view["name"]
    stage.mkdir()
    lines = [f"read_liberty {tcl_string(name)}" for name in view["libraries"]]
    lines += [f"read_db {tcl_string(project['deliverables']['odb'])}"]
    lines += [f"read_sdc {tcl_string(name)}" for name in view["constraints"]]
    lines += [
        "set_propagated_clock [all_clocks]",
        f"read_spef {tcl_string(view['parasitics'])}",
        "set_wire_rc -signal -layer met2",
        "set_wire_rc -clock -layer met3",
    ]
    if project["activity"] is not None:
        activity = project["activity"]
        lines.append(f"read_vcd -scope {tcl_string(activity['scope'])} {tcl_string(activity['file'])}")
    for net, supply in supplies.items():
        voltage = number(supply["voltage"])
        if net == "VPWR":
            voltage = {"tt_025C_1v80": 1.8, "ss_100C_1v60": 1.6, "ff_n40C_1v95": 1.95}[view["pvt"]]
        source = stage / f"{net}.loc"
        locations = _source_locations(project_input(work, supply["sources"]), number(supply["voltage"]))
        with source.open("w", newline="") as stream:
            csv.writer(stream).writerows([*position, voltage] for position in locations)
        lines += [
            f"check_power_grid -net {net}",
            f"set_pdnsim_net_voltage -net {net} -voltage {voltage}",
            f"analyze_power_grid -net {net} -vsrc {tcl_string(str(source))} -enable_em "
            f"-em_outfile {tcl_string(str(stage / (net + '.em.csv')))}",
        ]
    lines += ["utl::metric signoff_power_complete 1", "exit"]
    script, metrics_path = stage / "power.tcl", stage / "power.json"
    script.write_text("\n".join(lines) + "\n")
    executable = shutil.which("openroad")
    if executable is None:
        raise FileNotFoundError("OpenROAD is unavailable")
    expected = tuple(
        p.relative_to(work).as_posix() for p in (metrics_path, stage / "VPWR.em.csv", stage / "VGND.em.csv")
    )
    run_native(
        (executable, "-no_init", "-exit", "-metrics", str(metrics_path), str(script)),
        work,
        stage.parent.name + "-" + stage.name + "-power",
        timeout=86400,
        expected=expected,
    )
    raw = read_document(metrics_path)
    if finite_metric(raw, "signoff_power_complete") != 1:
        raise ValueError("power-grid analysis did not complete")
    drops = {net: _net_metric(raw, "design_powergrid__drop__worst", net) for net in supplies}
    currents = {net: read_em_current(stage / f"{net}.em.csv") for net in supplies}
    return {
        "worst_ir_drop_v": max(drops.values()),
        "nets": drops,
        "max_current_a": max(item["max_current_a"] for item in currents.values()),
        "em_segments": sum(item["segments"] for item in currents.values()),
    }


def _source_locations(path: Path, voltage: float) -> list[list[float]]:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("supply source locations exceed their parsing bound")
    positions: list[list[float]] = []
    with path.open(newline="") as stream:
        for row in csv.reader(stream):
            if len(row) != 4 or len(positions) >= 1_000_000:
                raise ValueError("supply locations require x,y,bump-edge-length,nominal-voltage CSV rows")
            x, y, size, actual = (number(float(value)) for value in row)
            if size == 0 or abs(actual - voltage) > 1e-9:
                raise ValueError("supply location size or voltage differs from the approved nominal supply")
            positions.append([x, y, size])
    if not positions:
        raise ValueError("supply source locations are empty")
    return positions


def _net_metric(metrics: dict[str, Any], prefix: str, net: str) -> float:
    keys = [key for key in metrics if key.startswith(f"{prefix}__net:{net}__corner:")]
    if not keys:
        raise ValueError("power analysis is missing a net/corner result")
    values = [finite_metric(metrics, key) for key in keys]
    if any(value < 0 for value in values):
        raise ValueError("power analysis contains negative physical magnitudes")
    return max(values)


def read_em_current(path: Path) -> dict[str, Any]:
    expected = [
        "Node0 Layer",
        "Node0 X location",
        "Node0 Y location",
        "Node1 Layer",
        "Node1 X location",
        "Node1 Y location",
        "Current",
    ]
    largest, count = 0.0, 0
    with path.open(newline="") as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != expected:
            raise ValueError("EM CSV does not match the pinned PDNSim report format")
        for row in rows:
            if count >= 5_000_000 or None in row or any(value is None for value in row.values()):
                raise ValueError("EM CSV is truncated or exceeds its bound")
            values = [float(row[field]) for field in (*expected[1:3], *expected[4:])]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("EM CSV contains non-finite values")
            largest = max(largest, abs(values[-1]))
            count += 1
    if count == 0:
        raise ValueError("EM analysis contains no conductor segments")
    return {"max_current_a": largest, "segments": count}


def current_density_bound(electrical: dict[str, Any], power: dict[str, Any], policy: dict[str, Any]) -> float:
    widths, thickness = electrical["minimum_width_um"], policy["metal_thickness_um"]
    if not widths or set(widths) - set(thickness):
        raise FileNotFoundError("approved conductor thickness is missing for analyzed power-grid layers")
    areas = [number(width, positive=True) * number(thickness[layer], positive=True) for layer, width in widths.items()]
    if electrical["via_count"]:
        areas.append(number(electrical["minimum_via_cut_area_um2"], positive=True))
    # The largest segment current over the smallest cross-section bounds every segment conservatively.
    return number(number(power["max_current_a"]) / number(min(areas), positive=True))


_ELECTRICAL = r"""
import json
import odb
db = odb.dbDatabase.create()
odb.read_db(db, @ODB@)
block = db.getChip().getBlock()
dbu = block.getDbUnitsPerMicron()
result = {"checked_power_pins": 0, "violations": 0, "minimum_width_um": {}, "via_count": 0,
          "minimum_via_cut_area_um2": None, "scope": "single-domain PG pins, body ties, and grid conductor geometry"}
def record_width(shape):
    layer = shape.getTechLayer()
    if layer is None or str(layer.getType()) != "ROUTING":
        return
    width = min(shape.xMax() - shape.xMin(), shape.yMax() - shape.yMin()) / dbu
    name = layer.getName()
    result["minimum_width_um"][name] = min(result["minimum_width_um"].get(name, width), width)
for inst in block.getInsts():
    for term in inst.getITerms():
        master = term.getMTerm()
        if str(master.getSigType()) not in ("POWER", "GROUND"):
            continue
        result["checked_power_pins"] += 1
        net = term.getNet()
        expected = "VPWR" if master.getName() in ("VPWR", "VPB") else "VGND"
        if master.getName() not in ("VPWR", "VPB", "VGND", "VNB") or net is None or net.getName() != expected:
            result["violations"] += 1
        for pin in master.getMPins():
            for shape in pin.getGeometry():
                record_width(shape)
for net_name in ("VPWR", "VGND"):
    net = block.findNet(net_name)
    if net is None:
        result["violations"] += 1
        continue
    for wire in net.getSWires():
        for shape in wire.getWires():
            if shape.isVia():
                via = shape.getTechVia() or shape.getBlockVia()
                if via is None:
                    result["violations"] += 1
                    continue
                for box in via.getBoxes():
                    if str(box.getTechLayer().getType()) == "CUT":
                        area = (box.xMax() - box.xMin()) * (box.yMax() - box.yMin()) / (dbu * dbu)
                        previous = result["minimum_via_cut_area_um2"]
                        result["minimum_via_cut_area_um2"] = area if previous is None else min(previous, area)
                        result["via_count"] += 1
            else:
                record_width(shape)
with open(@REPORT@, "w") as stream:
    json.dump(result, stream, allow_nan=False)
"""
