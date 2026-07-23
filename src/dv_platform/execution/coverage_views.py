# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Coverage report import, merge, gating, and gap reporting."""

from __future__ import annotations

import json
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
    sweeps = payload.get("parameter_sweeps", {})
    if isinstance(sweeps, dict) and sweeps.get("present"):
        lines.extend(
            [
                "",
                "## Parameter Sweep Cross-Points",
                "",
                f"- configured_points: {sweeps.get('configured_points', 0)}",
                f"- passed: {str(bool(sweeps.get('passed'))).lower()}",
                "",
                "| design unit | cross point | category | passed |",
                "| --- | --- | --- | --- |",
            ]
        )
        for group in sweeps.get("groups", ()):
            for cross_point in group.get("cross_points", ()):
                lines.append(
                    f"| {_markdown_cell(group['design_unit'])} | {_markdown_cell(cross_point['cross_point_id'])} | "
                    f"{_markdown_cell(cross_point['category'])} | {str(bool(cross_point['passed'])).lower()} |"
                )
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
