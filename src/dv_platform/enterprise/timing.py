"""Complete PVT/RC replay of a final routed design in OpenROAD and OpenSTA."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import run_native
from dv_platform.physical_design import (
    _metric_name,
    assess_physical_requirements,
    file_digest,
    finite_metric,
    physical_requirements,
    project_input,
    resolved_constraints_digest,
    tcl_string,
    write_document,
)
from dv_platform.signoff import load_requirements, read_document

TIMING_FIELDS = (
    "setup_wns_ns",
    "hold_wns_ns",
    "setup_tns_ns",
    "hold_tns_ns",
    "cap_slack_percent",
    "slew_slack_percent",
    "fanout_slack_percent",
    "special_check_slack",
    "constraint_slack",
)


def export_logical_netlist(work: Path, project: dict[str, Any], executable: str) -> list[str]:
    # A fresh DB avoids the implementation process's cached STA supply ports.
    script = work / "logical-export.tcl"
    script.write_text(
        f"read_db {tcl_string(project['deliverables']['odb'])}\n"
        "foreach terminal [[ord::get_db_block] getBTerms] {\n"
        "  if {[$terminal getSigType] in {POWER GROUND}} { odb::dbBTerm_destroy $terminal }\n}\n"
        f"write_verilog {tcl_string(project['deliverables']['netlist'])}\n"
    )
    run_native(
        (executable, "-no_init", "-exit", script.name),
        work,
        "logical-export",
        expected=(project["deliverables"]["netlist"],),
    )
    return [script.name, "logical-export.receipt.json", "logical-export.stdout.log", "logical-export.stderr.log"]


def analyze_scenarios(
    work: Path, project: dict[str, Any], tools: dict[str, str], *, prefix: str = "scenario"
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", prefix):
        raise ValueError("invalid scenario replay prefix")
    views = {}
    for scenario in project["scenarios"]:
        outputs = {}
        for kind in ("openroad", "sta"):
            stem = f"{prefix}-{scenario['name']}-{kind}"
            script = work / f"{stem}.tcl"
            script.write_text(_scenario_script(project, scenario, stem, embedded=kind == "openroad"))
            expected = tuple(
                f"{stem}.{suffix}" for suffix in ("json", "checks.rpt", "power.json", "activity.rpt", "sdc")
            )
            run_native((tools[kind], "-no_init", "-exit", script.name), work, stem, timeout=3600, expected=expected)
            outputs[kind] = _read_scenario(work, stem, scenario["name"])
        for field in (*TIMING_FIELDS, "power_watts"):
            if abs(outputs["openroad"]["metrics"][field] - outputs["sta"]["metrics"][field]) > 1e-6:
                raise ValueError(f"standalone OpenSTA disagrees in {scenario['name']}: {field}")
        if outputs["openroad"]["clocks"] != outputs["sta"]["clocks"]:
            raise ValueError("standalone OpenSTA disagrees about scenario clocks")
        if outputs["openroad"]["resolved_constraints_sha256"] != outputs["sta"]["resolved_constraints_sha256"]:
            raise ValueError("standalone OpenSTA disagrees about resolved timing exceptions")
        conservative = {
            key: (
                max(outputs[kind]["metrics"][key] for kind in outputs)
                if key == "power_watts"
                else min(outputs[kind]["metrics"][key] for kind in outputs)
            )
            for key in outputs["openroad"]["metrics"]
        }
        views[scenario["name"]] = {
            **outputs["openroad"],
            "metrics": conservative,
            "embedded_metrics": outputs["openroad"]["metrics"],
            "standalone_sta": outputs["sta"]["metrics"],
        }
    write_document(work / ("scenarios.json" if prefix == "scenario" else prefix + ".json"), views)
    return views


def replay_period_proposal(
    work: Path, project: dict[str, Any], analysis: dict[str, Any], tools: dict[str, str], limits: dict[str, Any]
) -> dict[str, Any]:
    clocks = analysis["clocks"]
    if len(clocks) != 1 or any(view["clocks"] != clocks for view in analysis["scenarios"].values()):
        return {"status": "requires_engineering_input", "reason": "period exploration requires one common clock"}
    name, period = next(iter(clocks.items()))
    slack = min(view["metrics"]["setup_wns_ns"] for view in analysis["scenarios"].values())
    margin = limits["setup_margin_ns"] or 0
    proposed = math.ceil(max(0.001, period - slack + margin) * 1.1 * 1000) / 1000
    stage = work / "characterization-period"
    stage.mkdir()
    trial = deepcopy(project)
    for scenario in trial["scenarios"]:
        path = stage / (scenario["name"] + ".sdc")
        original = "".join(f"source {tcl_string(str(work / file))}\n" for file in scenario["constraints"])
        path.write_text(original + _PERIOD_PROPOSAL.replace("@CLOCK@", tcl_string(name)).replace("@NS@", str(proposed)))
        scenario["constraints"] = [path.relative_to(work).as_posix()]
    views = analyze_scenarios(work, trial, tools, prefix="characterization")
    targets = {
        field: limits["hold_margin_ns"] or 0 if field == "hold_wns_ns" else margin if field == "setup_wns_ns" else 0
        for field in TIMING_FIELDS
    }
    return {
        "status": "replayed",
        "clock": name,
        "original_period_ns": period,
        "proposed_period_ns": proposed,
        "proposed_frequency_mhz": 1000 / proposed,
        "timing_closed": all(
            view["metrics"][field] >= target for view in views.values() for field, target in targets.items()
        ),
        "scenarios": views,
        "requirements_changed": False,
        "basis": "single-clock post-route estimate with 10 percent period headroom, verified by independent replay; engineering approval is still required",
    }


def augment_analysis(analysis: dict[str, Any], work: Path, project: dict[str, Any], tools: dict[str, str]) -> None:
    _extract_corners(work, project, tools["openroad"])
    views = analyze_scenarios(work, project, tools)
    policy = load_requirements(work / project["signoff_policy"], project)
    analysis.update(scenarios=views, production_limits=policy["limits"])
    analysis["metrics"]["view_count"] = len(views)
    for field in TIMING_FIELDS:
        for name, view in views.items():
            analysis["metrics"][f"scenario:{name}:{field}"] = view["metrics"][field]
        if field in analysis["metrics"]:
            analysis["metrics"][field] = min(view["metrics"][field] for view in views.values())
    analysis["metrics"]["power_watts"] = max(view["metrics"]["power_watts"] for view in views.values())
    paths = [path for view in views.values() for path in view["paths"]]
    analysis["paths"] = [
        path
        for mode in ("setup", "hold")
        for path in sorted((p for p in paths if p["mode"] == mode), key=lambda p: p["slack_ns"])[:5]
    ]
    identity = {
        name: {
            "clocks": view["clocks"],
            "resolved_constraints_sha256": view["resolved_constraints_sha256"],
            "constraints": {
                field: file_digest(work / field)
                for field in next(s["constraints"] for s in project["scenarios"] if s["name"] == name)
            },
        }
        for name, view in views.items()
    }
    identity["primary"] = {"resolved_constraints_sha256": analysis["resolved_constraints_sha256"]}
    analysis["resolved_constraints_sha256"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    assessment = assess_physical_requirements(physical_requirements(analysis), analysis)
    analysis.update(failures=assessment["unmet_requirements"], timing_closed=assessment["timing_closed"])


def _extract_corners(work: Path, project: dict[str, Any], executable: str) -> None:
    for rc in ("min", "nom", "max"):
        output = next(view["parasitics"] for view in project["scenarios"] if view["rc"] == rc)
        lines = [
            f"read_db {tcl_string(project['deliverables']['odb'])}",
            f"extract_parasitics -ext_model_file technology/rules.{rc}",
            f"write_spef {tcl_string(output)}",
        ]
        stem = f"scenario-extraction-{rc}"
        (work / f"{stem}.tcl").write_text("\n".join(lines) + "\n")
        run_native((executable, "-no_init", "-exit", f"{stem}.tcl"), work, stem, timeout=3600, expected=(output,))


def _scenario_script(project: dict[str, Any], scenario: dict[str, Any], stem: str, *, embedded: bool) -> str:
    lines = [f"read_liberty {tcl_string(name)}" for name in scenario["libraries"]]
    if embedded:
        lines.append(f"read_db {tcl_string(project['deliverables']['odb'])}")
    else:
        lines += [
            f"read_verilog {tcl_string(project['deliverables']['netlist'])}",
            f"link_design {tcl_string(project['design'])}",
        ]
    lines += [f"read_sdc {tcl_string(name)}" for name in scenario["constraints"]]
    lines += ["set_propagated_clock [all_clocks]", f"read_spef {tcl_string(scenario['parasitics'])}"]
    if project["activity"] is not None:
        activity = project["activity"]
        lines.append(f"read_vcd -scope {tcl_string(activity['scope'])} {tcl_string(activity['file'])}")
    lines += [f"set so_stem {tcl_string(stem)}", _COLLECTOR, "exit"]
    return "\n".join(lines) + "\n"


def _read_scenario(work: Path, stem: str, name: str) -> dict[str, Any]:
    data = read_document(work / f"{stem}.json")
    metrics = {field: finite_metric(data, field) for field in TIMING_FIELDS}
    for field in ("setup_tns_ns", "hold_tns_ns", "special_check_slack", "constraint_slack"):
        if metrics[field] > 0:
            raise ValueError("invalid timing violation metric")
    checks = (work / f"{stem}.checks.rpt").read_text()
    if "analysis_complete=1" not in checks:
        raise ValueError("scenario special-check report is incomplete")
    metrics["special_check_slack"] = -float(checks.count("(VIOLATED)"))
    metrics["power_watts"] = finite_metric(read_document(work / f"{stem}.power.json")["Total"], "total")
    count = _bounded_count(data, "clock_count", 256)
    clocks = {_metric_name(data, f"clock/{i}/name"): finite_metric(data, f"clock/{i}/period_ns") for i in range(count)}
    if len(clocks) != count or any(value <= 0 for value in clocks.values()):
        raise ValueError("scenario clock identities or periods are invalid")
    paths = [
        _path(data, name, mode, i)
        for mode in ("setup", "hold")
        for i in range(_bounded_count(data, f"{mode}/count", 5))
    ]
    if not paths or not {"setup", "hold"} <= {path["mode"] for path in paths}:
        raise ValueError("scenario has no complete setup and hold paths")
    counts = dict(
        re.findall(r"^(vcd|saif|input|unannotated)\s+(\d+)\s*$", (work / f"{stem}.activity.rpt").read_text(), re.M)
    )
    if "unannotated" not in counts or sum(map(int, counts.values())) < 1:
        raise ValueError("activity annotation report is incomplete")
    coverage = 100 * int(counts.get("vcd", 0)) / sum(map(int, counts.values()))
    return {
        "metrics": metrics,
        "clocks": clocks,
        "paths": paths,
        "activity_coverage_percent": coverage,
        "resolved_constraints_sha256": resolved_constraints_digest(work / f"{stem}.sdc"),
    }


def _bounded_count(data: dict[str, Any], field: str, maximum: int) -> int:
    count = finite_metric(data, field)
    if not count.is_integer() or not 1 <= count <= maximum:
        raise ValueError("scenario timing count is incomplete or exceeds its bound")
    return int(count)


def _path(data: dict[str, Any], scenario: str, mode: str, index: int) -> dict[str, Any]:
    if index >= 5:
        raise ValueError("scenario path collection exceeds its bound")
    prefix = f"{mode}/{index}"
    values = {key: finite_metric(data, f"{prefix}/{key}") for key in ("slack_ns", "arrival_ns", "required_arrival_ns")}
    if (
        abs(
            (
                values["required_arrival_ns"] - values["arrival_ns"]
                if mode == "setup"
                else values["arrival_ns"] - values["required_arrival_ns"]
            )
            - values["slack_ns"]
        )
        > 1e-6
    ):
        raise ValueError("scenario path requirements disagree with slack")
    count = _bounded_count(data, f"{prefix}/point_count", 64)
    total = finite_metric(data, f"{prefix}/point_total_count")
    if not total.is_integer() or total < count:
        raise ValueError("scenario timing total point count is invalid")
    points = [
        {
            "pin": _metric_name(data, f"{prefix}/point/{point}/pin"),
            "arrival_ns": finite_metric(data, f"{prefix}/point/{point}/arrival_ns"),
        }
        for point in range(count)
    ]
    return {
        "evidence_id": f"scenario:{scenario}:{prefix}",
        "scenario": scenario,
        "mode": mode,
        **values,
        "startpoint": _metric_name(data, f"{prefix}/startpoint"),
        "endpoint": _metric_name(data, f"{prefix}/endpoint"),
        "required_relation": "<=" if mode == "setup" else ">=",
        "points": points,
        "total_point_count": int(total),
        "points_truncated": total > count,
    }


def scenario_artifacts(work: Path, project: dict[str, Any]) -> dict[str, str]:
    paths = {view["parasitics"] for view in project["scenarios"]}
    paths.update(p.name for p in work.glob("scenario-*.*") if p.is_file())
    paths.add("scenarios.json")
    return {name: file_digest(project_input(work, name)) for name in sorted(paths)}


_PERIOD_PROPOSAL = r"""
set exploration_clock [lindex [get_clocks @CLOCK@] 0]
if {[sta::Clock_is_generated $exploration_clock] || [sta::Clock_is_virtual $exploration_clock]} {
  error "period exploration requires a primary clock with physical sources"
}
set exploration_sources [get_property $exploration_clock sources]
set exploration_period [expr {@NS@ / ([sta::time_ui_sta 1.0] * 1e9)}]
set exploration_waveform [list]
foreach edge [sta::Clock_waveform $exploration_clock] {
  lappend exploration_waveform [expr {$edge / [sta::Clock_period $exploration_clock] * $exploration_period}]
}
create_clock -name @CLOCK@ -period $exploration_period -waveform $exploration_waveform $exploration_sources
"""


_COLLECTOR = r"""
set so_fields [list]
proc so_quote {value} {
  return "\"[string map [list \\ \\\\ \" \\\" \n \\n \r \\r \t \\t] $value]\""
}
proc so_metric {name value} {
  lappend ::so_fields "[so_quote $name]:[so_quote $value]"
}
set scale [expr {[sta::time_ui_sta 1.0] * 1e9}]
so_metric setup_wns_ns [expr {[sta::worst_slack -max] * $scale}]
so_metric hold_wns_ns [expr {[sta::worst_slack -min] * $scale}]
so_metric setup_tns_ns [expr {[sta::total_negative_slack -max] * $scale}]
so_metric hold_tns_ns [expr {[sta::total_negative_slack -min] * $scale}]
so_metric cap_slack_percent [expr {[sta::max_capacitance_check_slack_limit] * 100}]
so_metric slew_slack_percent [expr {[sta::max_slew_check_slack_limit] * 100}]
so_metric fanout_slack_percent [expr {[sta::max_fanout_check_slack_limit] * 100}]
so_metric constraint_slack [expr {[check_setup -verbose] ? 0 : -1}]
so_metric special_check_slack 0
set i 0
foreach clock [all_clocks] {
  so_metric clock/$i/name [get_full_name $clock]
  so_metric clock/$i/period_ns [expr {[get_property $clock period] * $scale}]
  incr i
}
so_metric clock_count $i
foreach {mode delay} {setup max hold min} {
  set paths [lrange [find_timing_paths -path_delay $delay -group_path_count 5 -sort_by_slack] 0 4]
  so_metric $mode/count [llength $paths]
  set i 0
  foreach path $paths {
    set prefix $mode/$i
    set slack [get_property $path slack]
    set all_points [get_property $path points]
    set arrival [get_property [lindex $all_points end] arrival]
    so_metric $prefix/slack_ns [expr {$slack * $scale}]
    so_metric $prefix/arrival_ns [expr {$arrival * $scale}]
    so_metric $prefix/required_arrival_ns [expr {($mode eq "setup" ? $arrival + $slack : $arrival - $slack) * $scale}]
    so_metric $prefix/startpoint [get_full_name [get_property $path startpoint]]
    so_metric $prefix/endpoint [get_full_name [get_property $path endpoint]]
    so_metric $prefix/point_total_count [llength $all_points]
    set points [lrange $all_points 0 63]
    so_metric $prefix/point_count [llength $points]
    set point_index 0
    foreach point $points {
      so_metric $prefix/point/$point_index/pin [get_full_name [get_property $point pin]]
      so_metric $prefix/point/$point_index/arrival_ns [expr {[get_property $point arrival] * $scale}]
      incr point_index
    }
    incr i
  }
}
report_check_types -violators -recovery -removal -min_pulse_width -min_period -clock_gating_setup -clock_gating_hold > $so_stem.checks.rpt
set check_output [open $so_stem.checks.rpt a]
puts $check_output "analysis_complete=1"
close $check_output
report_power -digits 12 -format json > $so_stem.power.json
report_activity_annotation > $so_stem.activity.rpt
write_sdc $so_stem.sdc
set output [open $so_stem.json w]
puts $output "\{[join $so_fields ,]\}"
close $output
"""
