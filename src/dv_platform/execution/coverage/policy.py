# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dv_platform.core.models import CoveragePolicy

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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _string_mapping(value: object, field: str, module: str, point_id: str, path: Path) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not key.strip() or not isinstance(item, str) or not item.strip()
        for key, item in value.items()
    ):
        raise ValueError(
            f"Coverage point {field} must contain non-empty string mappings for {module}/{point_id}: {path}"
        )
    return {key: value[key] for key in sorted(value)}


def _protocol_transaction(value: object, module: str, point_id: str, path: Path) -> dict[str, str | int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Coverage point protocol_transaction must be an object for {module}/{point_id}: {path}")
    allowed = {"profile_id", "instance_id", "channel", "trace_id", "sequence", "beat", "packet", "transaction_id"}
    if set(value) - allowed or any(
        isinstance(item, bool) or not isinstance(item, (str, int)) or isinstance(item, str) and not item.strip()
        for item in value.values()
    ):
        raise ValueError(f"Coverage point protocol_transaction is invalid for {module}/{point_id}: {path}")
    return {str(key): value[key] for key in sorted(value)}


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
