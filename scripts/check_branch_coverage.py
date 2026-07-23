#!/usr/bin/env python3
"""Enforce global, per-file, and subsystem coverage ratchets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not 0 <= result <= 100:
        raise ValueError(f"{label} must be between 0 and 100")
    return result


def _summary_metric(summary: dict[str, Any], metric: str) -> float | None:
    if metric == "total":
        return _number(summary.get("percent_covered"), "coverage total percentage")
    branches = summary.get("num_branches")
    covered = summary.get("covered_branches")
    if not isinstance(branches, int) or isinstance(branches, bool) or branches < 0:
        raise ValueError("coverage num_branches must be a non-negative integer")
    if not isinstance(covered, int) or isinstance(covered, bool) or not 0 <= covered <= branches:
        raise ValueError("coverage covered_branches must be between zero and num_branches")
    return 100.0 * covered / branches if branches else None


def _coverage_sections(
    coverage: object, policy: object
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    if not isinstance(coverage, dict) or not isinstance(policy, dict):
        raise ValueError("coverage and policy documents must contain JSON objects")
    if policy.get("schema_version") != 1:
        raise ValueError("unsupported coverage ratchet schema_version")
    metadata = coverage.get("meta")
    if not isinstance(metadata, dict) or not metadata.get("branch_coverage"):
        raise ValueError("coverage data must be collected with branch coverage enabled")
    sections = (
        coverage.get("totals"),
        coverage.get("files"),
        policy.get("global", {}),
        policy.get("defaults", {}),
        policy.get("files", {}),
        policy.get("groups", {}),
        policy.get("default_exemptions", {}),
    )
    if any(not isinstance(section, dict) for section in sections):
        raise ValueError("coverage totals, files, and ratchet policies must be objects")
    return sections  # type: ignore[return-value]


def _check_thresholds(failures: list[str], label: str, summary: dict[str, Any], thresholds: dict[str, Any]) -> None:
    for metric in ("total", "branch"):
        if metric not in thresholds:
            continue
        minimum = _number(thresholds[metric], f"{label} {metric} threshold")
        actual = _summary_metric(summary, metric)
        if actual is None:
            if metric == "branch":
                continue
            raise ValueError(f"{label} has no {metric} coverage metric")
        if actual + 1e-9 < minimum:
            failures.append(f"{label}: {metric} coverage {actual:.2f}% is below {minimum:.2f}%")


def _check_file_defaults(
    failures: list[str],
    files: dict[str, Any],
    defaults: dict[str, Any],
    exemptions: dict[str, Any],
) -> None:
    for file_name, payload in sorted(files.items()):
        if (
            not isinstance(file_name, str)
            or not isinstance(payload, dict)
            or not isinstance(payload.get("summary"), dict)
        ):
            raise ValueError("coverage file records must contain a path and summary object")
        if file_name in exemptions:
            continue
        _check_thresholds(failures, file_name, payload["summary"], defaults)


def _check_file_policies(failures: list[str], files: dict[str, Any], file_policies: dict[str, Any]) -> None:
    for file_name, thresholds in sorted(file_policies.items()):
        if not isinstance(file_name, str) or not isinstance(thresholds, dict):
            raise ValueError("coverage ratchet file entries must map paths to threshold objects")
        payload = files.get(file_name)
        if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
            failures.append(f"{file_name}: required coverage record is missing")
            continue
        _check_thresholds(failures, file_name, payload["summary"], thresholds)


def _group_summary(files: dict[str, Any], names: list[object], label: str) -> dict[str, Any]:
    if not names or not all(isinstance(name, str) for name in names):
        raise ValueError(f"{label} files must be a non-empty string list")
    summaries = []
    for name in names:
        payload = files.get(name)
        if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
            raise ValueError(f"{label} required coverage record is missing: {name}")
        summaries.append(payload["summary"])
    statements = sum(int(item.get("num_statements", 0)) for item in summaries)
    missing = sum(int(item.get("missing_lines", 0)) for item in summaries)
    branches = sum(int(item.get("num_branches", 0)) for item in summaries)
    covered = sum(int(item.get("covered_branches", 0)) for item in summaries)
    return {
        "percent_covered": 100.0 * (statements - missing) / statements if statements else 100.0,
        "num_branches": branches,
        "covered_branches": covered,
    }


def _check_groups(failures: list[str], files: dict[str, Any], groups: dict[str, Any]) -> set[str]:
    governed: set[str] = set()
    for name, policy in sorted(groups.items()):
        if not isinstance(name, str) or not isinstance(policy, dict):
            raise ValueError("coverage groups must map names to policy objects")
        members = policy.get("files")
        if not isinstance(members, list):
            raise ValueError(f"coverage group {name} must define files")
        thresholds = {key: policy[key] for key in ("total", "branch") if key in policy}
        _check_thresholds(failures, f"GROUP {name}", _group_summary(files, members, name), thresholds)
        governed.update(str(member) for member in members)
    return governed


def _validate_exemptions(exemptions: dict[str, Any], files: dict[str, Any], governed: set[str]) -> None:
    for path, reason in exemptions.items():
        if not isinstance(path, str) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("default coverage exemptions must map paths to non-empty reasons")
        if path not in files:
            raise ValueError(f"default coverage exemption record is missing: {path}")
        if path not in governed:
            raise ValueError(f"default coverage exemption is not governed by a coverage group: {path}")


def evaluate_coverage(coverage: object, policy: object) -> tuple[str, ...]:
    """Return deterministic ratchet failures for a Coverage.py JSON document."""

    totals, files, global_policy, defaults, file_policies, groups, exemptions = _coverage_sections(coverage, policy)
    failures: list[str] = []
    _check_thresholds(failures, "TOTAL", totals, global_policy)
    governed = _check_groups(failures, files, groups)
    _validate_exemptions(exemptions, files, governed)
    _check_file_defaults(failures, files, defaults, exemptions)
    _check_file_policies(failures, files, file_policies)
    return tuple(failures)


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label} {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("coverage-ratchet.json"))
    arguments = parser.parse_args(argv)
    try:
        failures = evaluate_coverage(
            _load_json(arguments.coverage_json, "coverage JSON"),
            _load_json(arguments.policy, "coverage policy"),
        )
    except ValueError as error:
        print(f"coverage-ratchet: invalid input: {error}")
        return 2
    if failures:
        print("coverage-ratchet: failed")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("coverage-ratchet: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
