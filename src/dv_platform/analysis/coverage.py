"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, CoveragePolicy

COVERAGE_SCHEMA_VERSION = 1
METRICS = ("line", "branch", "toggle", "functional")


def import_coverage_reports(config: CLIConfig, paths: tuple[Path, ...]) -> tuple[Path, dict[str, Any]]:
    """Import supported local reports and persist a deterministic merged summary."""

    if not paths:
        raise ValueError("At least one coverage report is required")
    reports = tuple(_load_report(path.expanduser().resolve(strict=True)) for path in paths)
    merged = _merge_reports(reports)
    gates = _evaluate_gates(merged["metrics"], config.coverage_policy)
    payload = {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "sources": [report["source"] for report in reports],
        "metrics": merged["metrics"],
        "modules": merged["modules"],
        "gates": gates,
        "passed": all(gate["passed"] for gate in gates),
        "gaps": _coverage_gaps(merged["modules"], config.coverage_policy),
    }
    path = config.work_dir / "coverage" / "summary.json"
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path, payload


def read_coverage_summary(config: CLIConfig) -> dict[str, Any] | None:
    """Read the current imported coverage summary if one exists."""

    path = config.work_dir / "coverage" / "summary.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _load_report(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".info", ".lcov"}:
        return _load_lcov(path)
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".xml":
        return _load_xml(path)
    raise ValueError(f"Unsupported coverage report format: {path}")


def _load_lcov(path: Path) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = raw_line.partition(":")
        if not separator:
            continue
        if key == "SF":
            if current is not None:
                modules.append(current)
            current = {"module": value, "counts": {}}
        elif current is not None and key in {"LF", "LH", "BRF", "BRH"}:
            current["counts"][key] = int(value)
        elif key == "end_of_record" and current is not None:
            modules.append(current)
            current = None
    if current is not None:
        modules.append(current)
    normalized = [
        {
            "module": item["module"],
            "metrics": {
                "line": _metric(item["counts"].get("LH", 0), item["counts"].get("LF", 0)),
                "branch": _metric(item["counts"].get("BRH", 0), item["counts"].get("BRF", 0)),
            },
        }
        for item in modules
    ]
    return {"source": str(path), "modules": normalized}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Coverage JSON must contain an object: {path}")
    raw_modules = payload.get("modules")
    if isinstance(raw_modules, dict):
        modules = [
            {"module": str(name), "metrics": _normalize_metrics(metrics)}
            for name, metrics in raw_modules.items()
            if isinstance(metrics, dict)
        ]
    elif isinstance(raw_modules, list):
        modules = [
            {
                "module": str(item.get("module") or item.get("name")),
                "metrics": _normalize_metrics(item.get("metrics", item)),
            }
            for item in raw_modules
            if isinstance(item, dict) and (item.get("module") or item.get("name"))
        ]
    else:
        modules = [{"module": "aggregate", "metrics": _normalize_metrics(payload.get("metrics", payload))}]
    return {"source": str(path), "modules": modules}


def _load_xml(path: Path) -> dict[str, Any]:
    root = ElementTree.parse(path).getroot()
    modules: list[dict[str, Any]] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in {"class", "package", "module"}:
            continue
        name = element.attrib.get("filename") or element.attrib.get("name")
        if not name:
            continue
        line_rate = element.attrib.get("line-rate")
        branch_rate = element.attrib.get("branch-rate")
        metrics: dict[str, Any] = {}
        if line_rate is not None:
            metrics["line"] = _percentage_metric(float(line_rate) * 100.0)
        if branch_rate is not None:
            metrics["branch"] = _percentage_metric(float(branch_rate) * 100.0)
        if metrics:
            modules.append({"module": name, "metrics": metrics})
    if not modules:
        metrics = {}
        if root.attrib.get("line-rate") is not None:
            metrics["line"] = _percentage_metric(float(root.attrib["line-rate"]) * 100.0)
        if root.attrib.get("branch-rate") is not None:
            metrics["branch"] = _percentage_metric(float(root.attrib["branch-rate"]) * 100.0)
        if not metrics:
            raise ValueError(f"Coverage XML has no supported metrics: {path}")
        modules.append({"module": "aggregate", "metrics": metrics})
    return {"source": str(path), "modules": modules}


def _normalize_metrics(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    metrics: dict[str, Any] = {}
    for name in METRICS:
        value = data.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[name] = _percentage_metric(float(value))
        elif isinstance(value, dict):
            covered = value.get("covered")
            total = value.get("total")
            if isinstance(covered, (int, float)) and isinstance(total, (int, float)):
                metrics[name] = _metric(float(covered), float(total))
    return metrics


def _merge_reports(reports: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    by_module: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for report in reports:
        for module in report["modules"]:
            target = by_module.setdefault(str(module["module"]), {})
            for name, metric in module["metrics"].items():
                target.setdefault(name, []).append(metric)
    modules: list[dict[str, Any]] = [
        {
            "module": module,
            "metrics": {name: _merge_metric(values) for name, values in sorted(metrics.items())},
        }
        for module, metrics in sorted(by_module.items())
    ]
    aggregate: dict[str, Any] = {}
    for name in METRICS:
        values = [module["metrics"][name] for module in modules if name in module["metrics"]]
        if values:
            aggregate[name] = _merge_metric(values)
    return {"metrics": aggregate, "modules": modules}


def _merge_metric(values: list[dict[str, Any]]) -> dict[str, Any]:
    return _metric(
        sum(float(value["covered"]) for value in values),
        sum(float(value["total"]) for value in values),
    )


def _metric(covered: float, total: float) -> dict[str, Any]:
    percentage = 100.0 * covered / total if total > 0 else None
    return {"covered": covered, "total": total, "percentage": percentage}


def _percentage_metric(percentage: float) -> dict[str, Any]:
    if not 0.0 <= percentage <= 100.0:
        raise ValueError(f"Coverage percentage must be between 0 and 100: {percentage}")
    return _metric(percentage, 100.0)


def _evaluate_gates(metrics: dict[str, Any], policy: CoveragePolicy) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for name, minimum in _policy_values(policy):
        if minimum is None:
            continue
        percentage = metrics.get(name, {}).get("percentage")
        gates.append(
            {
                "metric": name,
                "minimum": minimum,
                "actual": percentage,
                "passed": isinstance(percentage, (int, float)) and percentage >= minimum,
                "reason": "metric missing" if percentage is None else None,
            }
        )
    return gates


def _coverage_gaps(modules: list[dict[str, Any]], policy: CoveragePolicy) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for module in modules:
        for name, minimum in _policy_values(policy):
            if minimum is None:
                continue
            percentage = module["metrics"].get(name, {}).get("percentage")
            if percentage is None or percentage < minimum:
                gaps.append({"module": module["module"], "metric": name, "actual": percentage, "minimum": minimum})
    return gaps


def _policy_values(policy: CoveragePolicy) -> tuple[tuple[str, float | None], ...]:
    return (
        ("line", policy.line_minimum),
        ("branch", policy.branch_minimum),
        ("toggle", policy.toggle_minimum),
        ("functional", policy.functional_minimum),
    )
