# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

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
        "check_ids": _string_list(
            raw_point.get("check_ids", [raw_point["check_id"]] if raw_point.get("check_id") is not None else None),
            "check_ids",
            module,
            point_id,
            path,
        ),
        "requirement_ids": _string_list(raw_point.get("requirement_ids"), "requirement_ids", module, point_id, path),
        "behavior_ids": _string_list(raw_point.get("behavior_ids"), "behavior_ids", module, point_id, path),
        "source_locator": str(raw_point["source_locator"]) if raw_point.get("source_locator") is not None else None,
        "evidence_states": [status] if status in {"bounded_pass", "unsupported"} else [],
        "vendor_provenance": _string_mapping(
            raw_point.get("vendor_provenance"), "vendor_provenance", module, point_id, path
        ),
        "protocol_transaction": _protocol_transaction(raw_point.get("protocol_transaction"), module, point_id, path),
        "cross_members": _string_list(raw_point.get("cross_members"), "cross_members", module, point_id, path),
        "severity": _optional_string(raw_point.get("severity")),
        "confidence": _optional_string(raw_point.get("confidence")),
        "target": _optional_string(raw_point.get("target")),
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
    points, dispositions = _merged_coverage_inputs(reports)
    orphaned = sorted(set(dispositions) - set(points))
    if orphaned:
        names = ", ".join(f"{module}/{point_id}" for module, point_id in orphaned)
        raise ValueError(f"Coverage dispositions reference unknown points: {names}")
    normalized, gaps, unmapped, stale, expired, counts = _normalized_closure_points(points, dispositions, as_of)
    total = len(normalized)
    eligible = total - counts["excluded"]
    closure_covered = sum(counts[state] for state in CLOSED_STATES)
    raw_percentage = 100.0 * counts["covered"] / eligible if eligible else None
    closure_percentage = 100.0 * closure_covered / eligible if eligible else None
    policy_failures = _closure_policy_failures(gaps, strict, unmapped, stale, expired, dispositions, as_of)
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
        "stale_dispositions": stale,
        "expired_dispositions": expired,
        "as_of": as_of.isoformat() if as_of is not None else None,
        "policy_failures": policy_failures,
    }


def _merged_coverage_inputs(reports):
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
    return points, dispositions


def _normalized_closure_points(points, dispositions, as_of):
    normalized: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    unmapped: list[dict[str, str]] = []
    stale_dispositions: list[dict[str, str]] = []
    expired_dispositions: list[dict[str, str]] = []
    counts = {state: 0 for state in CLOSURE_STATES}
    for key, point in sorted(points.items()):
        disposition = dispositions.get(key)
        disposition_expired = _disposition_expired(disposition, as_of)
        if disposition_expired and disposition is not None:
            expired_dispositions.append(
                {
                    "module": key[0],
                    "point_id": key[1],
                    "disposition_id": str(disposition["disposition_id"]),
                    "expires_at": str(disposition["expires_at"]),
                }
            )
        state = _closure_point_state(point, disposition, disposition_expired)
        if state == "covered":
            if disposition is not None:
                stale_dispositions.append(
                    {"module": key[0], "point_id": key[1], "disposition_id": disposition["disposition_id"]}
                )
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
    return normalized, gaps, unmapped, stale_dispositions, expired_dispositions, counts


def _disposition_expired(disposition, as_of):
    return bool(
        disposition is not None
        and disposition.get("expires_at")
        and as_of is not None
        and date.fromisoformat(str(disposition["expires_at"])) < as_of
    )


def _closure_point_state(point, disposition, disposition_expired):
    if disposition is not None and not disposition_expired and (point["failed"] or not point["covered"]):
        return str(disposition["status"])
    if point["failed"]:
        return "failed"
    if point["covered"]:
        return "covered"
    if "bounded_pass" in point["evidence_states"]:
        return "bounded_pass"
    if "unsupported" in point["evidence_states"]:
        return "unsupported"
    return "uncovered"


def _closure_policy_failures(gaps, strict, unmapped, stale_dispositions, expired_dispositions, dispositions, as_of):
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
    return policy_failures
