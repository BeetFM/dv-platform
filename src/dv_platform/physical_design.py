"""Validated OpenROAD projects, bounded repair requests, and measured timing evidence."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from dv_platform.core.io import atomic_write_text

REPAIR_BOUNDS = {
    "cap_margin_percent": (0.0, 30.0),
    "slew_margin_percent": (0.0, 30.0),
    "setup_margin_ns": (0.0, 0.1),
    "hold_margin_ns": (0.0, 0.1),
}
METRICS = (
    "setup_wns_ns",
    "hold_wns_ns",
    "setup_tns_ns",
    "cap_slack_percent",
    "slew_slack_percent",
    "fanout_slack_percent",
    "area_um2",
    "routed",
    "drc_violations",
    "antenna_violations",
    "clock_count",
    "instance_count",
    "view_count",
    "constraints_ok",
    "repair_design_calls",
    "repair_timing_calls",
)


def write_document(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    path.chmod(0o600)


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resolved_constraints_digest(path: Path) -> str:
    # write_sdc adds a timestamp comment; preserve every executable constraint byte.
    commands = "\n".join(
        line for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    )
    return hashlib.sha256(commands.encode()).hexdigest()


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or any(ord(char) < 32 for char in value):
        raise ValueError("physical project paths must be non-empty relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." == value or path.as_posix() != value:
        raise ValueError(f"physical project path escapes its root or is not normalized: {value}")
    return value


def load_physical_project(path: Path) -> dict[str, Any]:
    from dv_platform.signoff import read_document

    if path.stat().st_size > 1_048_576:
        raise ValueError("physical project manifest exceeds 1 MiB")
    project = read_document(path, maximum=1_048_576)
    version = project.get("schema_version") if isinstance(project, dict) else None
    if (
        not isinstance(project, dict)
        or set(project) != _project_fields(version)
        or type(project["schema_version"]) is not int
        or project["schema_version"] not in (1, 2)
    ):
        raise ValueError("physical project has unknown, missing, or unsupported fields")
    if not isinstance(project["design"], str) or not project["design"] or len(project["design"]) > 256:
        raise ValueError("physical project design must be a bounded non-empty string")
    for key in ("inputs", "constraints", "libraries"):
        values = project[key]
        bound = 4096 if version == 2 else 128
        if not isinstance(values, list) or not 1 <= len(values) <= bound:
            raise ValueError(f"physical project {key} must contain 1..{bound} paths")
        normalized = [_relative(value) for value in values]
        if len(set(normalized)) != len(values):
            raise ValueError(f"physical project {key} contains duplicate paths")
    for key in ("flow", "parasitics"):
        _relative(project[key])
    inputs = set(project["inputs"])
    if not {project["flow"], *project["constraints"], *project["libraries"]} <= inputs:
        raise ValueError("flow, constraints, and libraries must be explicit project inputs")
    if project["parasitics"] in inputs:
        raise ValueError("parasitics must be produced by this run, not copied from an earlier run")
    reserved = {
        "pd-driver.tcl",
        "pd-metrics.json",
        "pd-result.json",
        "pd-summary.json",
        "pd-timing.rpt",
        "pd-power.rpt",
        "pd-power.json",
        "pd-export.v",
        "pd-export.sdc",
        "pd-final.odb",
        "pd-final.def",
        "analysis.json",
        "sta-driver.tcl",
        "sta-result.json",
        "openroad.stdout.log",
        "openroad.stderr.log",
        "sta.stdout.log",
        "sta.stderr.log",
    }
    if inputs & reserved or project["parasitics"] in reserved:
        raise ValueError("physical project overlaps runner-owned artifacts")
    root = path.resolve().parent
    for relative in inputs:
        project_input(root, relative)
    _validate_project_extension(project, root)
    return project


def _project_fields(version: object) -> set[str]:
    fields = {"schema_version", "design", "flow", "inputs", "constraints", "libraries", "parasitics"}
    if version == 2:
        fields |= {"technology_lock", "reference_netlist", "scenarios", "signoff_policy", "deliverables", "activity"}
    return fields


def _validate_project_extension(project: dict[str, Any], root: Path) -> None:
    if project["schema_version"] == 2:
        from dv_platform.signoff import validate_project_v2

        validate_project_v2(project, root)


def project_input(root: Path, relative: str) -> Path:
    candidate = root / _relative(relative)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError(f"physical project input is missing, linked, or outside its root: {relative}")
    return candidate


def validate_repair(value: object) -> dict[str, Any]:
    fields = {*REPAIR_BOUNDS, "allow_gate_cloning"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("repair request has unknown or missing fields")
    for name, (minimum, maximum) in REPAIR_BOUNDS.items():
        number = value[name]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"repair {name} must be a finite number")
        if not minimum <= number <= maximum:
            raise ValueError(f"repair {name} must be between {minimum} and {maximum}")
    if not isinstance(value["allow_gate_cloning"], bool):
        raise ValueError("allow_gate_cloning must be a boolean")
    return dict(value)


def tcl_string(value: str) -> str:
    for character in ("\\", "$", "[", "]", '"'):
        value = value.replace(character, "\\" + character)
    return '"' + value + '"'


def physical_driver(project: dict[str, Any], repair: dict[str, Any] | None) -> str:
    header = "proc cpu_count {} { return 4 }\nset pd_design_calls 0\nset pd_timing_calls 0\n"
    if repair is not None:
        repair = validate_repair(repair)
        header += (
            "\n".join(
                f"set pd_{key} {int(value) if isinstance(value, bool) else value}" for key, value in repair.items()
            )
            + "\n"
        )
        header += _REPAIR_HOOKS
    exporter = Path(__file__).with_name("physical_design.tcl").read_text(encoding="utf-8")
    return header + f"source {tcl_string(project['flow'])}\n" + exporter


_REPAIR_HOOKS = r"""
proc pd_without {arguments flags} {
  foreach flag $flags {
    while {[set index [lsearch -exact $arguments $flag]] >= 0} {
      set arguments [lreplace $arguments $index [expr {$index + 1}]]
    }
  }
  return $arguments
}
rename repair_design pd_original_repair_design
proc repair_design {args} {
  incr ::pd_design_calls
  set args [pd_without $args {-cap_margin -slew_margin}]
  pd_original_repair_design {*}$args -cap_margin $::pd_cap_margin_percent -slew_margin $::pd_slew_margin_percent
}
rename repair_timing pd_original_repair_timing
proc repair_timing {args} {
  incr ::pd_timing_calls
  set args [pd_without $args {-setup_margin -hold_margin}]
  set index [lsearch -exact $args -skip_gate_cloning]
  if {$index >= 0} {set args [lreplace $args $index $index]}
  if {!$::pd_allow_gate_cloning} {lappend args -skip_gate_cloning}
  set setup [sta::time_sta_ui [expr {$::pd_setup_margin_ns * 1e-9}]]
  set hold [sta::time_sta_ui [expr {$::pd_hold_margin_ns * 1e-9}]]
  pd_original_repair_timing {*}$args -setup_margin $setup -hold_margin $hold
}
"""


def finite_metric(metrics: dict[str, Any], key: str) -> float:
    raw = metrics.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise ValueError(f"missing or non-numeric physical metric: {key}")
    try:
        number = float(raw)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"invalid physical metric: {key}") from error
    if not math.isfinite(number):
        raise ValueError(f"non-finite physical metric: {key}")
    return number


def read_physical_analysis(path: Path, *, expected_view_count: int = 1) -> dict[str, Any]:
    if type(expected_view_count) is not int or not 1 <= expected_view_count <= 128:
        raise ValueError("invalid expected timing-view count")
    metrics = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metrics, dict):
        raise ValueError("OpenROAD metrics must be an object")
    measured = {name: finite_metric(metrics, f"PD::{name}") for name in METRICS}
    if finite_metric(metrics, "flow__errors__count") != 0:
        raise ValueError("OpenROAD reported tool errors")
    counts = (
        "clock_count",
        "instance_count",
        "view_count",
        "drc_violations",
        "antenna_violations",
        "repair_design_calls",
        "repair_timing_calls",
        "routed",
        "constraints_ok",
    )
    if any(not measured[name].is_integer() or measured[name] < 0 for name in counts):
        raise ValueError("physical analysis counters must be non-negative integers")
    if measured["clock_count"] > 128 or measured["setup_tns_ns"] > 0:
        raise ValueError("physical clock count is outside its bound or total negative slack is invalid")
    if measured["view_count"] != expected_view_count or measured["clock_count"] < 1 or measured["instance_count"] < 1:
        raise ValueError("physical analysis requires declared timing views, constrained clocks, and a non-empty design")
    measured["power_watts"] = _read_power(path.with_name("pd-power.json"))
    clocks = {}
    for index in range(int(measured["clock_count"])):
        name = _metric_name(metrics, f"PD::clock/{index}/name")
        period = finite_metric(metrics, f"PD::clock/{index}/period_ns")
        if name in clocks or period <= 0:
            raise ValueError("physical clock identity is duplicated or its period is invalid")
        clocks[name] = period
    paths: list[dict[str, Any]] = []
    for mode in ("setup", "hold"):
        count = finite_metric(metrics, f"PD::path/{mode}/count")
        if not count.is_integer() or not 1 <= count <= 5:
            raise ValueError(f"physical analysis has no complete bounded {mode} paths")
        paths.extend(_timing_path(metrics, mode, index) for index in range(int(count)))
    failures = [
        key
        for key in (
            "setup_wns_ns",
            "hold_wns_ns",
            "setup_tns_ns",
            "cap_slack_percent",
            "slew_slack_percent",
            "fanout_slack_percent",
        )
        if measured[key] < 0
    ]
    failures += [key for key in ("drc_violations", "antenna_violations") if measured[key] != 0]
    failures += [key for key in ("routed", "constraints_ok") if measured[key] != 1]
    if measured["area_um2"] <= 0:
        raise ValueError("physical design area must be positive")
    return {
        "schema_version": 1,
        "metrics": measured,
        "clocks": clocks,
        "paths": paths,
        "failures": failures,
        "timing_closed": not failures,
    }


def _read_power(path: Path) -> float:
    power = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(power, dict) or not isinstance(power.get("Total"), dict):
        raise ValueError("OpenROAD power report is incomplete")
    total = finite_metric(power["Total"], "total")
    if total < 0:
        raise ValueError("estimated physical power must be non-negative")
    return total


def _metric_name(metrics: dict[str, Any], key: str) -> str:
    value = metrics.get(key)
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError(f"missing or invalid physical identity: {key}")
    return value


def _timing_path(metrics: dict[str, Any], mode: str, index: int) -> dict[str, Any]:
    prefix = f"PD::path/{mode}/{index}"
    count = finite_metric(metrics, prefix + "/point_count")
    total = finite_metric(metrics, prefix + "/point_total_count")
    if not count.is_integer() or not 1 <= count <= 64:
        raise ValueError("timing path point count is missing or outside its bound")
    if not total.is_integer() or total < count:
        raise ValueError("timing path total point count is invalid")
    points = [
        {
            "pin": _metric_name(metrics, f"{prefix}/point/{point}/pin"),
            "arrival_ns": finite_metric(metrics, f"{prefix}/point/{point}/arrival_ns"),
        }
        for point in range(int(count))
    ]
    slack = finite_metric(metrics, prefix + "/slack_ns")
    arrival = finite_metric(metrics, prefix + "/arrival_ns")
    required = finite_metric(metrics, prefix + "/required_arrival_ns")
    implied_slack = required - arrival if mode == "setup" else arrival - required
    if abs(implied_slack - slack) > 1e-6:
        raise ValueError("timing path arrival and requirement disagree with its slack")
    return {
        "evidence_id": f"{mode}:{index}",
        "mode": mode,
        "startpoint": _metric_name(metrics, prefix + "/startpoint"),
        "endpoint": _metric_name(metrics, prefix + "/endpoint"),
        "slack_ns": slack,
        "arrival_ns": arrival,
        "required_arrival_ns": required,
        "required_relation": "<=" if mode == "setup" else ">=",
        "points": points,
        "total_point_count": int(total),
        "points_truncated": total > count,
    }


def physical_requirements(baseline: dict[str, Any]) -> dict[str, Any]:
    """Freeze closure thresholds from the original constrained analysis."""
    minimums = (
        "setup_wns_ns",
        "hold_wns_ns",
        "setup_tns_ns",
        "cap_slack_percent",
        "slew_slack_percent",
        "fanout_slack_percent",
    )
    gates = {name: {"operator": ">=", "target": 0.0} for name in minimums}
    gates.update({name: {"operator": "==", "target": 0.0} for name in ("drc_violations", "antenna_violations")})
    gates.update({name: {"operator": "==", "target": 1.0} for name in ("routed", "constraints_ok")})
    if "production_limits" in baseline:
        limits = baseline["production_limits"]
        for name, policy_name in (("area_um2", "area_max_um2"), ("power_watts", "power_max_watts")):
            if limits[policy_name] is not None:
                gates[name] = {"operator": "<=", "target": limits[policy_name]}
        for name in baseline["metrics"]:
            if name.startswith("scenario:"):
                metric = name.rsplit(":", 1)[-1]
                target = limits.get(
                    {"setup_wns_ns": "setup_margin_ns", "hold_wns_ns": "hold_margin_ns"}.get(metric, "")
                )
                gates[name] = {"operator": ">=", "target": target or 0.0}
    else:
        gates.update(
            {
                name: {"operator": "<=", "target": baseline["metrics"][name] * 1.2}
                for name in ("area_um2", "power_watts")
            }
        )
    return {
        "clocks": dict(baseline["clocks"]),
        "resolved_constraints_sha256": baseline["resolved_constraints_sha256"],
        "metrics": gates,
    }


def assess_physical_requirements(requirements: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    checks = {}
    for name, gate in requirements["metrics"].items():
        actual = finite_metric(analysis["metrics"], name)
        target = gate["target"]
        operator = gate["operator"]
        difference = target - actual if operator == ">=" else actual - target
        gap = abs(difference) if operator == "==" else max(0.0, difference)
        checks[name] = {**gate, "actual": actual, "gap": gap, "met": gap == 0}
    unmet = [name for name, check in checks.items() if not check["met"]]
    return {"checks": checks, "unmet_requirements": unmet, "timing_closed": not unmet}


def evaluate_physical_candidate(
    baseline: dict[str, Any], reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    if (
        baseline["clocks"] != candidate["clocks"]
        or baseline["resolved_constraints_sha256"] != candidate["resolved_constraints_sha256"]
    ):
        raise ValueError("candidate changed the timing specification")
    requirements = physical_requirements(baseline)
    before = assess_physical_requirements(requirements, reference)
    after = assess_physical_requirements(requirements, candidate)
    regressions = [name for name in after["checks"] if after["checks"][name]["gap"] > before["checks"][name]["gap"]]
    improvements = [
        name for name in after["checks"] if before["checks"][name]["gap"] - after["checks"][name]["gap"] > 1e-6
    ]
    return {
        "selected": not regressions and (bool(improvements) or after["timing_closed"] and not before["timing_closed"]),
        "improvements": improvements,
        "regressions": regressions,
        "metric_deltas": {name: candidate["metrics"][name] - reference["metrics"][name] for name in after["checks"]},
        "assessment": after,
    }


def physical_improvement(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return bool(evaluate_physical_candidate(baseline, baseline, candidate)["selected"])
