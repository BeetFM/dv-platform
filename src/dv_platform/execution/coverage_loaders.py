# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from defusedxml.ElementTree import parse

COVERAGE_SCHEMA_VERSION = 3
MIN_READABLE_COVERAGE_SCHEMA_VERSION = 1
METRICS = ("line", "branch", "toggle", "functional")
CLOSURE_STATES = (
    "covered",
    "uncovered",
    "bounded_pass",
    "unsupported",
    "failed",
    "waived",
    "unreachable",
    "excluded",
)
CLOSED_STATES = {"covered", "waived", "unreachable"}
TRACEABLE_POINT_KINDS = {"assertion", "cover", "covergroup", "coverpoint", "formal", "formal_property", "functional"}


def _load_report(path: Path, coverage_importers: tuple[CoverageImporter, ...] = ()) -> dict[str, Any]:
    for importer in coverage_importers:
        try:
            supported = importer.supports(path)
        except Exception as error:
            raise ValueError(f"Coverage importer failed while probing {path}: {error}") from error
        if not supported:
            continue
        try:
            payload = importer.import_coverage(path)
        except Exception as error:
            raise ValueError(f"Coverage importer failed for {path}: {error}") from error
        return _normalize_json_report(payload, path)
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
    return _normalize_json_report(payload, path)


def _normalize_json_report(payload: object, path: Path) -> dict[str, Any]:
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
    points, dispositions = _load_json_closure(payload, path)
    return {"source": str(path), "modules": modules, "points": points, "dispositions": dispositions}


def _load_xml(path: Path) -> dict[str, Any]:
    root = parse(path).getroot()
    if root is None:
        raise ValueError(f"Coverage XML has no root element: {path}")
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
