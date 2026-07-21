#!/usr/bin/env python3
"""Enforce global, default per-file, and explicit coverage ratchets."""

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


def evaluate_coverage(coverage: object, policy: object) -> tuple[str, ...]:
    """Return deterministic ratchet failures for a Coverage.py JSON document."""

    if not isinstance(coverage, dict) or not isinstance(policy, dict):
        raise ValueError("coverage and policy documents must contain JSON objects")
    if policy.get("schema_version") != 1:
        raise ValueError("unsupported coverage ratchet schema_version")
    metadata = coverage.get("meta")
    if not isinstance(metadata, dict) or not metadata.get("branch_coverage"):
        raise ValueError("coverage data must be collected with branch coverage enabled")
    totals = coverage.get("totals")
    files = coverage.get("files")
    if not isinstance(totals, dict) or not isinstance(files, dict):
        raise ValueError("coverage data is missing totals or files")
    global_policy = policy.get("global", {})
    defaults = policy.get("defaults", {})
    file_policies = policy.get("files", {})
    if not isinstance(global_policy, dict) or not isinstance(defaults, dict) or not isinstance(file_policies, dict):
        raise ValueError("coverage ratchet global, defaults, and files must be objects")

    failures: list[str] = []

    def check(label: str, summary: dict[str, Any], thresholds: dict[str, Any]) -> None:
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

    check("TOTAL", totals, global_policy)
    for file_name, payload in sorted(files.items()):
        if (
            not isinstance(file_name, str)
            or not isinstance(payload, dict)
            or not isinstance(payload.get("summary"), dict)
        ):
            raise ValueError("coverage file records must contain a path and summary object")
        check(file_name, payload["summary"], defaults)
    for file_name, thresholds in sorted(file_policies.items()):
        if not isinstance(file_name, str) or not isinstance(thresholds, dict):
            raise ValueError("coverage ratchet file entries must map paths to threshold objects")
        payload = files.get(file_name)
        if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
            failures.append(f"{file_name}: required coverage record is missing")
            continue
        check(file_name, payload["summary"], thresholds)
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
