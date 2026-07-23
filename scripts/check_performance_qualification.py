"""Compare broad-GA performance evidence with a fail-closed 10% budget."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MIN_RTL_LINES = 2_000_000
MIN_XML_BYTES = 128 * 1024 * 1024
MIN_PDF_BYTES = 64 * 1024 * 1024


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _validate_v2_identity(result: dict[str, Any], require_ga_scale: bool) -> list[str]:
    errors = [
        f"performance v2 field is missing: {field}"
        for field in (
            "platform_identity",
            "commit",
            "worktree_clean",
            "input_fingerprints",
            "tool_versions",
            "reproducibility",
        )
        if field not in result
    ]
    if not re.fullmatch(r"[0-9a-f]{40}", str(result.get("commit", ""))):
        errors.append("performance commit identity is invalid")
    if require_ga_scale and result.get("worktree_clean") is not True:
        errors.append("GA scale qualification requires a clean worktree")
    wheel = result.get("wheel")
    if require_ga_scale and (
        not isinstance(wheel, dict) or re.fullmatch(r"[0-9a-f]{64}", str(wheel.get("sha256", ""))) is None
    ):
        errors.append("GA scale qualification requires a wheel digest")
    return errors


def _validate_v2_inputs(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fingerprints = result.get("input_fingerprints")
    if not isinstance(fingerprints, dict) or set(fingerprints) != {"rtl", "xml", "pdf"}:
        errors.append("performance input fingerprints are incomplete")
    else:
        for name, value in fingerprints.items():
            if (
                not isinstance(value, dict)
                or re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", ""))) is None
                or not isinstance(value.get("bytes"), int)
                or int(value["bytes"]) < 0
            ):
                errors.append(f"invalid performance input fingerprint: {name}")
    tools = result.get("tool_versions")
    if not isinstance(tools, dict) or any(
        not isinstance(tools.get(name), str) or not str(tools[name]).strip()
        for name in ("python", "defusedxml", "pypdf")
    ):
        errors.append("performance parser tool identities are incomplete")
    return errors


def _validate_input_sizes(result: dict[str, Any], require_ga_scale: bool) -> list[str]:
    inputs = result.get("inputs")
    if not isinstance(inputs, dict):
        return ["performance inputs must be an object"]
    errors: list[str] = []
    thresholds = {"rtl_lines": MIN_RTL_LINES, "xml_bytes": MIN_XML_BYTES, "pdf_bytes": MIN_PDF_BYTES}
    for name, minimum in thresholds.items():
        value = inputs.get(name)
        if not isinstance(value, int) or value < 0:
            errors.append(f"invalid performance input size: {name}")
        elif require_ga_scale and value < minimum:
            errors.append(f"performance input {name} is below GA scale: {value} < {minimum}")
    return errors


def _validate_stage_metrics(result: dict[str, Any]) -> list[str]:
    stages = result.get("stages")
    if not isinstance(stages, dict) or not stages:
        return ["performance stages must be a non-empty object"]
    errors: list[str] = []
    for name, metrics in stages.items():
        if not isinstance(metrics, dict):
            errors.append(f"invalid performance metrics: {name}")
            continue
        for metric in ("runtime_seconds", "peak_rss_mb"):
            value = metrics.get(metric)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                errors.append(f"invalid {metric} for stage {name}")
    return errors


def validate_result(result: object, *, require_ga_scale: bool = False) -> list[str]:
    if not isinstance(result, dict):
        return ["performance result must be an object"]
    errors: list[str] = []
    if result.get("schema_version") not in {1, 2}:
        errors.append("unsupported performance schema_version")
    if require_ga_scale and result.get("schema_version") != 2:
        errors.append("GA scale qualification requires performance schema v2")
    if result.get("schema_version") == 2:
        errors.extend(_validate_v2_identity(result, require_ga_scale))
        errors.extend(_validate_v2_inputs(result))
    if result.get("platform") not in {"ubuntu-24.04", "wsl2-ubuntu-24.04"}:
        errors.append("unsupported performance platform")
    if not isinstance(result.get("profile"), str) or not result.get("profile"):
        errors.append("performance profile is missing")
    errors.extend(_validate_input_sizes(result, require_ga_scale))
    errors.extend(_validate_stage_metrics(result))
    return errors


def _comparison_identity_error(baseline: dict[str, Any], current: dict[str, Any]) -> str | None:
    if baseline.get("profile") != current.get("profile") or baseline.get("platform") != current.get("platform"):
        return "baseline and current result are not comparable"
    if baseline.get("inputs") != current.get("inputs"):
        return "baseline and current input scales differ"
    if baseline.get("schema_version") == 2 and current.get("schema_version") == 2:
        for field in ("commit", "wheel", "input_fingerprints", "tool_versions", "reproducibility"):
            if baseline.get(field) != current.get(field):
                return f"baseline and current {field} differ"
    return None


def _metric_regressions(
    baseline_stages: dict[str, Any], current_stages: dict[str, Any], maximum_regression: float
) -> list[str]:
    errors: list[str] = []
    for stage in sorted(baseline_stages):
        baseline_metrics = baseline_stages[stage]
        current_metrics = current_stages[stage]
        if not isinstance(baseline_metrics, dict) or not isinstance(current_metrics, dict):
            continue
        for metric in ("runtime_seconds", "peak_rss_mb"):
            old = float(baseline_metrics[metric])
            new = float(current_metrics[metric])
            if new > old * (1 + maximum_regression):
                errors.append(f"{stage}.{metric} regressed by {(new / old - 1) * 100:.2f}% (limit 10.00%)")
    return errors


def compare_results(baseline: object, current: object, maximum_regression: float = 0.10) -> list[str]:
    errors = [*validate_result(baseline), *validate_result(current)]
    if errors or not isinstance(baseline, dict) or not isinstance(current, dict):
        return errors
    identity_error = _comparison_identity_error(baseline, current)
    if identity_error is not None:
        return [identity_error]
    baseline_stages = baseline["stages"]
    current_stages = current["stages"]
    if not isinstance(baseline_stages, dict) or not isinstance(current_stages, dict):
        return ["performance stages are invalid"]
    if set(baseline_stages) != set(current_stages):
        return ["baseline and current stage sets differ"]
    return [*errors, *_metric_regressions(baseline_stages, current_stages, maximum_regression)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--require-ga-scale", action="store_true")
    args = parser.parse_args()
    baseline = _load(args.baseline)
    current = _load(args.current)
    errors = [
        *validate_result(baseline, require_ga_scale=args.require_ga_scale),
        *validate_result(current, require_ga_scale=args.require_ga_scale),
    ]
    if not errors:
        errors.extend(compare_results(baseline, current))
    for error in errors:
        print(error)
    if errors:
        return 1
    print("performance qualification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
