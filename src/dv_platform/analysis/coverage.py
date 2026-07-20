"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree

from dv_platform.analysis.closure import apply_coverage_feedback_to_stored_plans
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, CoveragePolicy

COVERAGE_SCHEMA_VERSION = 2
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


class CoverageImporter(Protocol):
    """Versioned plugin surface for vendor coverage databases."""

    def supports(self, path: Path) -> bool:
        """Return whether this importer owns the supplied report."""

    def import_coverage(self, path: Path) -> dict[str, Any]:
        """Return the normalized public JSON coverage schema."""


def import_coverage_reports(
    config: CLIConfig,
    paths: tuple[Path, ...],
    coverage_importers: tuple[CoverageImporter, ...] = (),
    as_of: date | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Import supported local reports and persist a deterministic merged summary."""

    if not paths:
        raise ValueError("At least one coverage report is required")
    reports = tuple(_load_report(path.expanduser().resolve(strict=True), coverage_importers) for path in paths)
    merged = _merge_reports(reports)
    closure = _merge_closure_reports(reports, strict=config.strict or config.ci, as_of=as_of)
    gates = _evaluate_gates(merged["metrics"], config.coverage_policy)
    path = config.work_dir / "coverage" / "summary.json"
    markdown_path = path.with_name("summary.md")
    yaml_path = path.with_name("summary.yaml")
    sarif_path = path.with_name("closure.sarif")
    payload = {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "sources": [report["source"] for report in reports],
        "metrics": merged["metrics"],
        "modules": merged["modules"],
        "gates": gates,
        "passed": all(gate["passed"] for gate in gates) and closure["passed"],
        "gaps": _coverage_gaps(merged["modules"], config.coverage_policy),
        "closure": closure,
        "closure_gaps": closure["gaps"],
        "exports": {
            "json": str(path),
            "markdown": str(markdown_path),
            "yaml": str(yaml_path),
            "sarif": str(sarif_path),
        },
    }
    plan_feedback = apply_coverage_feedback_to_stored_plans(config, payload, path)
    payload["plan_feedback"] = plan_feedback
    if closure["present"]:
        if not plan_feedback["plans_available"] and (config.strict or config.ci):
            closure["policy_failures"].append("verification plans are unavailable for closure reconciliation")
        if plan_feedback["unmeasured_checks"]:
            closure["policy_failures"].append("executable plan checks lack imported coverage points")
        if plan_feedback["stale_point_mappings"]:
            closure["policy_failures"].append("coverage points reference unknown plan checks")
        closure["policy_failures"] = list(dict.fromkeys(closure["policy_failures"]))
        closure["passed"] = not closure["policy_failures"]
        payload["passed"] = all(gate["passed"] for gate in gates) and closure["passed"]
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(markdown_path, _coverage_markdown(payload))
    atomic_write_text(yaml_path, _yaml_dump(payload))
    atomic_write_text(sarif_path, json.dumps(_coverage_sarif(payload), indent=2, sort_keys=True) + "\n")
    return path, payload


def read_coverage_summary(config: CLIConfig) -> dict[str, Any] | None:
    """Read the current imported coverage summary if one exists."""

    path = config.work_dir / "coverage" / "summary.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _migrate_coverage_summary(payload) if isinstance(payload, dict) else None


def _migrate_coverage_summary(payload: dict[str, Any]) -> dict[str, Any]:
    schema_version = int(payload.get("schema_version", MIN_READABLE_COVERAGE_SCHEMA_VERSION))
    if schema_version > COVERAGE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported coverage schema version {schema_version}; this build reads up to {COVERAGE_SCHEMA_VERSION}"
        )
    if schema_version < MIN_READABLE_COVERAGE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported coverage schema version {schema_version}; minimum readable version is "
            f"{MIN_READABLE_COVERAGE_SCHEMA_VERSION}"
        )
    migrated = dict(payload)
    if schema_version == 1:
        migrated.setdefault(
            "closure",
            {
                "present": False,
                "passed": True,
                "counts": {
                    **{state: 0 for state in CLOSURE_STATES},
                    "total": 0,
                    "eligible": 0,
                    "actionable": 0,
                },
                "raw_percentage": None,
                "closure_percentage": None,
                "traceability_complete": True,
                "points": [],
                "gaps": [],
                "unmapped_points": [],
                "stale_dispositions": [],
                "policy_failures": [],
            },
        )
        migrated.setdefault("closure_gaps", [])
        migrated.setdefault(
            "plan_feedback",
            {
                "plans_available": False,
                "plans_updated": 0,
                "mapped_checks": 0,
                "unmeasured_checks": [],
                "stale_point_mappings": [],
            },
        )
        migrated.setdefault("exports", {})
    migrated["schema_version"] = COVERAGE_SCHEMA_VERSION
    return migrated


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


def _load_json_closure(payload: dict[str, Any], path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    points: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for key, default_kind in (("coverage_points", "functional"), ("points", "functional"), ("formal_points", "formal")):
        raw_points = payload.get(key)
        if raw_points is None:
            continue
        if not isinstance(raw_points, list):
            raise ValueError(f"Coverage JSON field {key!r} must contain a list: {path}")
        for raw_point in raw_points:
            point, embedded_disposition = _normalize_coverage_point(raw_point, default_kind, path)
            points.append(point)
            if embedded_disposition is not None:
                dispositions.append(embedded_disposition)

    for key, default_state in (
        ("dispositions", None),
        ("waivers", "waived"),
        ("unreachable", "unreachable"),
        ("exclusions", "excluded"),
    ):
        raw_dispositions = payload.get(key)
        if raw_dispositions is None:
            continue
        if not isinstance(raw_dispositions, list):
            raise ValueError(f"Coverage JSON field {key!r} must contain a list: {path}")
        dispositions.extend(_normalize_disposition(item, default_state, path) for item in raw_dispositions)
    return points, dispositions


def _normalize_coverage_point(
    raw_point: object,
    default_kind: str,
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not isinstance(raw_point, dict):
        raise ValueError(f"Coverage point must contain an object: {path}")
    module = _required_string(raw_point, ("module",), "coverage point module", path)
    point_id = _required_string(raw_point, ("point_id", "id", "name"), "coverage point ID", path)
    kind = str(raw_point.get("kind") or default_kind).strip().lower()
    if not kind:
        raise ValueError(f"Coverage point kind must not be empty for {module}/{point_id}: {path}")

    raw_status = raw_point.get("status")
    status = str(raw_status).strip().lower() if raw_status is not None else None
    if status is not None and status not in CLOSURE_STATES:
        raise ValueError(f"Unsupported coverage point status {status!r} for {module}/{point_id}: {path}")
    hits = raw_point.get("hits")
    if hits is not None and (isinstance(hits, bool) or not isinstance(hits, (int, float)) or hits < 0):
        raise ValueError(f"Coverage point hits must be a non-negative number for {module}/{point_id}: {path}")
    covered_value = raw_point.get("covered")
    if covered_value is not None and not isinstance(covered_value, bool):
        raise ValueError(f"Coverage point covered must be boolean for {module}/{point_id}: {path}")
    if status is None and hits is None and covered_value is None:
        raise ValueError(f"Coverage point must define status, covered, or hits for {module}/{point_id}: {path}")
    covered = status == "covered" or (status is None and (covered_value is True or bool(hits and hits > 0)))
    if status == "uncovered":
        covered = False

    point = {
        "module": module,
        "point_id": point_id,
        "kind": kind,
        "covered": covered,
        "failed": status == "failed",
        "hits": float(hits) if isinstance(hits, (int, float)) else (1.0 if covered else 0.0),
        "check_ids": _string_list(raw_point.get("check_ids"), "check_ids", module, point_id, path),
        "requirement_ids": _string_list(raw_point.get("requirement_ids"), "requirement_ids", module, point_id, path),
        "behavior_ids": _string_list(raw_point.get("behavior_ids"), "behavior_ids", module, point_id, path),
        "source_locator": str(raw_point["source_locator"]) if raw_point.get("source_locator") is not None else None,
        "evidence_states": [status] if status in {"bounded_pass", "unsupported"} else [],
    }
    embedded_disposition = None
    if status in {"waived", "unreachable", "excluded"}:
        raw_disposition = raw_point.get("disposition")
        if not isinstance(raw_disposition, dict):
            raw_disposition = raw_point
        embedded_disposition = _normalize_disposition(
            {**raw_disposition, "module": module, "point_id": point_id, "status": status}, None, path
        )
    return point, embedded_disposition


def _normalize_disposition(raw: object, default_state: str | None, path: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Coverage disposition must contain an object: {path}")
    module = _required_string(raw, ("module",), "coverage disposition module", path)
    point_id = _required_string(raw, ("point_id", "id"), "coverage disposition point ID", path)
    state = str(raw.get("status") or default_state or "").strip().lower()
    if state not in {"waived", "unreachable", "excluded"}:
        raise ValueError(f"Unsupported coverage disposition {state!r} for {module}/{point_id}: {path}")
    disposition_id = _required_string(raw, ("disposition_id", "waiver_id"), "disposition ID", path)
    reason = _required_string(raw, ("reason",), "coverage disposition reason", path)
    approved_by = str(raw.get("approved_by") or "").strip() or None
    expires_at = str(raw.get("expires_at") or "").strip() or None
    evidence_refs = raw.get("evidence_refs", ())
    if not isinstance(evidence_refs, (list, tuple)):
        raise ValueError(f"Coverage disposition evidence_refs must contain a list for {module}/{point_id}: {path}")
    if state == "waived" and approved_by is None:
        raise ValueError(f"Coverage waiver must identify approved_by for {module}/{point_id}: {path}")
    if state == "waived" and expires_at is None:
        raise ValueError(f"Coverage waiver must identify expires_at for {module}/{point_id}: {path}")
    if expires_at is not None:
        try:
            date.fromisoformat(expires_at)
        except ValueError as error:
            raise ValueError(
                f"Coverage disposition expires_at must be an ISO date for {module}/{point_id}: {path}"
            ) from error
    if state == "unreachable" and not evidence_refs:
        raise ValueError(f"Unreachable coverage point must include evidence_refs for {module}/{point_id}: {path}")
    return {
        "module": module,
        "point_id": point_id,
        "status": state,
        "disposition_id": disposition_id,
        "reason": reason,
        "approved_by": approved_by,
        "expires_at": expires_at,
        "evidence_refs": list(evidence_refs),
    }


def _merge_closure_reports(
    reports: tuple[dict[str, Any], ...],
    strict: bool,
    as_of: date | None,
) -> dict[str, Any]:
    points: dict[tuple[str, str], dict[str, Any]] = {}
    dispositions: dict[tuple[str, str], dict[str, Any]] = {}
    for report in reports:
        source = str(report["source"])
        for point in report.get("points", ()):
            key = (str(point["module"]), str(point["point_id"]))
            current = points.get(key)
            if current is None:
                current = {**point, "sources": [source]}
                points[key] = current
                continue
            if current["kind"] != point["kind"]:
                raise ValueError(f"Coverage point kind conflict for {key[0]}/{key[1]}")
            current["covered"] = bool(current["covered"] or point["covered"])
            current["failed"] = bool(current["failed"] or point["failed"])
            current["hits"] = float(current["hits"]) + float(point["hits"])
            current["evidence_states"] = sorted({*current["evidence_states"], *point["evidence_states"]})
            current["sources"] = sorted({*current["sources"], source})
            for field in ("check_ids", "requirement_ids", "behavior_ids"):
                current[field] = sorted({*current[field], *point[field]})
            if current.get("source_locator") is None:
                current["source_locator"] = point.get("source_locator")
        for disposition in report.get("dispositions", ()):
            key = (str(disposition["module"]), str(disposition["point_id"]))
            current = dispositions.get(key)
            candidate = {**disposition, "sources": [source]}
            if current is None:
                dispositions[key] = candidate
            elif {k: v for k, v in current.items() if k != "sources"} != disposition:
                raise ValueError(f"Conflicting coverage dispositions for {key[0]}/{key[1]}")
            else:
                current["sources"] = sorted({*current["sources"], source})

    orphaned = sorted(set(dispositions) - set(points))
    if orphaned:
        names = ", ".join(f"{module}/{point_id}" for module, point_id in orphaned)
        raise ValueError(f"Coverage dispositions reference unknown points: {names}")

    normalized: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    unmapped: list[dict[str, str]] = []
    stale_dispositions: list[dict[str, str]] = []
    expired_dispositions: list[dict[str, str]] = []
    counts = {state: 0 for state in CLOSURE_STATES}
    for key, point in sorted(points.items()):
        disposition = dispositions.get(key)
        disposition_expired = bool(
            disposition is not None
            and disposition.get("expires_at")
            and as_of is not None
            and date.fromisoformat(str(disposition["expires_at"])) < as_of
        )
        if disposition_expired and disposition is not None:
            expired_dispositions.append(
                {
                    "module": key[0],
                    "point_id": key[1],
                    "disposition_id": str(disposition["disposition_id"]),
                    "expires_at": str(disposition["expires_at"]),
                }
            )
        if disposition is not None and not disposition_expired and (point["failed"] or not point["covered"]):
            state = str(disposition["status"])
        elif point["failed"]:
            state = "failed"
        elif point["covered"]:
            state = "covered"
            if disposition is not None:
                stale_dispositions.append(
                    {"module": key[0], "point_id": key[1], "disposition_id": disposition["disposition_id"]}
                )
        elif "bounded_pass" in point["evidence_states"]:
            state = "bounded_pass"
        elif "unsupported" in point["evidence_states"]:
            state = "unsupported"
        else:
            state = "uncovered"
        counts[state] += 1
        record = {**point, "status": state, "disposition": disposition}
        normalized.append(record)
        if state in {"uncovered", "bounded_pass", "unsupported", "failed"}:
            gaps.append(
                {
                    "kind": "coverage_point",
                    "module": key[0],
                    "point_id": key[1],
                    "point_kind": point["kind"],
                    "status": state,
                    "check_ids": point["check_ids"],
                    "requirement_ids": point["requirement_ids"],
                    "behavior_ids": point["behavior_ids"],
                }
            )
        if point["kind"] in TRACEABLE_POINT_KINDS and not any(
            point[field] for field in ("check_ids", "requirement_ids", "behavior_ids")
        ):
            unmapped.append({"module": key[0], "point_id": key[1], "kind": point["kind"]})

    total = len(normalized)
    eligible = total - counts["excluded"]
    closure_covered = sum(counts[state] for state in CLOSED_STATES)
    raw_percentage = 100.0 * counts["covered"] / eligible if eligible else None
    closure_percentage = 100.0 * closure_covered / eligible if eligible else None
    policy_failures: list[str] = []
    if gaps:
        policy_failures.append("actionable coverage points remain uncovered")
    if strict and unmapped:
        policy_failures.append("traceable coverage points lack plan mappings")
    if strict and stale_dispositions:
        policy_failures.append("covered points retain stale dispositions")
    if any(disposition["status"] == "waived" for disposition in dispositions.values()) and as_of is None:
        policy_failures.append("waiver evaluation date is missing")
    if expired_dispositions:
        policy_failures.append("coverage dispositions have expired")
    if unmapped:
        policy_failures.append("coverage points lack requirement, behavior, or plan-check traceability")
    return {
        "present": bool(normalized),
        "passed": not policy_failures,
        "counts": {**counts, "total": total, "eligible": eligible, "actionable": len(gaps)},
        "raw_percentage": raw_percentage,
        "closure_percentage": closure_percentage,
        "traceability_complete": not unmapped,
        "points": normalized,
        "gaps": gaps,
        "unmapped_points": unmapped,
        "stale_dispositions": stale_dispositions,
        "expired_dispositions": expired_dispositions,
        "as_of": as_of.isoformat() if as_of is not None else None,
        "policy_failures": policy_failures,
    }


def _required_string(data: dict[str, Any], keys: tuple[str, ...], label: str, path: Path) -> str:
    value = next((data.get(key) for key in keys if data.get(key) is not None), None)
    normalized = str(value).strip() if value is not None else ""
    if not normalized:
        raise ValueError(f"{label} must not be empty: {path}")
    return normalized


def _string_list(value: object, field: str, module: str, point_id: str, path: Path) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"Coverage point {field} must contain non-empty strings for {module}/{point_id}: {path}")
    return sorted(set(value))


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


def _coverage_markdown(payload: dict[str, Any]) -> str:
    closure = payload["closure"]
    counts = closure["counts"]
    lines = [
        "# Coverage Closure",
        "",
        f"- passed: {str(payload['passed']).lower()}",
        f"- raw_percentage: {_display_percentage(closure['raw_percentage'])}",
        f"- closure_percentage: {_display_percentage(closure['closure_percentage'])}",
        f"- total_points: {counts['total']}",
        f"- actionable_points: {counts['actionable']}",
        f"- traceability_complete: {str(closure['traceability_complete']).lower()}",
        "",
        "## Point States",
        "",
        "| state | count |",
        "| --- | ---: |",
        *(f"| {state} | {counts[state]} |" for state in CLOSURE_STATES),
        "",
        "## Actionable Gaps",
        "",
        "| module | point | status | kind | checks | requirements |",
        "| --- | --- | --- | --- | --- | --- |",
        *(
            (
                f"| {_markdown_cell(gap['module'])} | {_markdown_cell(gap['point_id'])} | "
                f"{_markdown_cell(gap['status'])} | {_markdown_cell(gap['point_kind'])} | "
                f"{_markdown_cell(', '.join(gap['check_ids']) or 'none')} | "
                f"{_markdown_cell(', '.join(gap['requirement_ids']) or 'none')} |"
            )
            for gap in closure["gaps"]
        ),
    ]
    if not closure["gaps"]:
        lines.append("| none | none | none | none | none | none |")
    lines.extend(["", "## Policy Failures", ""])
    lines.extend(f"- {failure}" for failure in closure["policy_failures"])
    if not closure["policy_failures"]:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _coverage_sarif(payload: dict[str, Any]) -> dict[str, Any]:
    results = []
    for gap in payload["closure"]["gaps"]:
        status = str(gap["status"])
        results.append(
            {
                "ruleId": f"dv-platform.coverage.{status}",
                "level": "error" if status == "failed" else "warning",
                "message": {"text": f"Coverage point {gap['point_id']} is {status} in module {gap['module']}."},
                "locations": [{"logicalLocations": [{"fullyQualifiedName": str(gap["module"]), "kind": "module"}]}],
                "properties": {
                    "pointId": gap["point_id"],
                    "pointKind": gap["point_kind"],
                    "checkIds": gap["check_ids"],
                    "requirementIds": gap["requirement_ids"],
                    "behaviorIds": gap["behavior_ids"],
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "dv-platform",
                        "informationUri": "https://github.com/",
                        "rules": [
                            {
                                "id": f"dv-platform.coverage.{state}",
                                "shortDescription": {"text": f"Coverage point is {state}"},
                            }
                            for state in ("uncovered", "failed")
                        ],
                    }
                },
                "results": results,
            }
        ],
    }


def _yaml_dump(value: object) -> str:
    return "\n".join(_yaml_lines(value, 0)) + "\n"


def _yaml_lines(value: object, indent: int) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key in sorted(value, key=str):
            item = value[key]
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return lines or [f"{prefix}[]"]
    return [f"{prefix}{_yaml_scalar(value)}"]


def _yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=True)


def _display_percentage(value: object) -> str:
    return f"{float(value):.2f}%" if isinstance(value, (int, float)) and not isinstance(value, bool) else "n/a"


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
