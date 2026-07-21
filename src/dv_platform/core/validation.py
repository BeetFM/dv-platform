"""Common, versioned validation results for every execution backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dv_platform.core.models import VerificationTarget
from dv_platform.core.schema import VALIDATION_RESULT_SCHEMA_VERSION

VALIDATION_OUTCOMES = {"pass", "fail", "timeout", "unexecuted", "unsupported", "bounded_pass"}


@dataclass(frozen=True)
class CheckValidationResult:
    check_id: str
    outcome: str
    evidence_locator: str | None = None
    diagnostic: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    module: str
    target: VerificationTarget
    status: str
    checks: tuple[CheckValidationResult, ...]
    tool_status: str
    return_code: int
    schema_version: int = VALIDATION_RESULT_SCHEMA_VERSION

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "module": self.module,
            "target": str(self.target),
            "status": self.status,
            "tool_status": self.tool_status,
            "return_code": self.return_code,
            "executed_checks": sum(1 for check in self.checks if check.outcome not in {"unexecuted", "unsupported"}),
            "checks": [
                {
                    "check_id": check.check_id,
                    "outcome": check.outcome,
                    "evidence_locator": check.evidence_locator,
                    "diagnostic": check.diagnostic,
                }
                for check in self.checks
            ],
        }


def validation_result_from_coverage(
    module: str,
    target: VerificationTarget,
    tool_status: str,
    return_code: int,
    entries: list[dict[str, Any]],
) -> ValidationResult:
    """Normalize existing trace outcomes without treating process success as check success."""

    outcome_map = {
        "passed": "pass",
        "failed": "fail",
        "bounded_pass": "bounded_pass",
        "unexecuted": "unexecuted",
        "unsupported": "unsupported",
    }
    checks = tuple(
        CheckValidationResult(
            check_id=str(entry.get("check_id") or entry.get("outcome_id") or entry.get("trace_id") or "unknown"),
            outcome=outcome_map.get(str(entry.get("status", "unexecuted")), "unexecuted"),
            evidence_locator=str(entry.get("generated_artifact") or entry.get("generated_symbol") or "") or None,
        )
        for entry in entries
    )
    executed = tuple(check for check in checks if check.outcome not in {"unexecuted", "unsupported"})
    if return_code != 0 or any(check.outcome == "fail" for check in checks):
        status = "failed"
    elif not executed:
        status = "unexecuted"
    elif any(check.outcome in {"bounded_pass", "unsupported", "unexecuted"} for check in checks):
        status = "incomplete"
    else:
        status = "passed"
    return ValidationResult(module, target, status, checks, tool_status, return_code)


def validation_result_from_json(payload: dict[str, Any]) -> ValidationResult:
    """Strictly parse the public validation-result contract."""

    if payload.get("schema_version") != VALIDATION_RESULT_SCHEMA_VERSION:
        raise ValueError("unsupported validation result schema_version")
    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, list):
        raise ValueError("validation result checks must be a list")
    checks: list[CheckValidationResult] = []
    for item in raw_checks:
        if not isinstance(item, dict) or not str(item.get("check_id", "")):
            raise ValueError("validation result check_id is required")
        outcome = str(item.get("outcome", ""))
        if outcome not in VALIDATION_OUTCOMES:
            raise ValueError(f"unsupported validation outcome: {outcome}")
        checks.append(
            CheckValidationResult(
                str(item["check_id"]),
                outcome,
                str(item["evidence_locator"]) if item.get("evidence_locator") is not None else None,
                str(item["diagnostic"]) if item.get("diagnostic") is not None else None,
            )
        )
    return ValidationResult(
        module=str(payload["module"]),
        target=VerificationTarget(str(payload["target"])),
        status=str(payload["status"]),
        checks=tuple(checks),
        tool_status=str(payload["tool_status"]),
        return_code=int(payload["return_code"]),
    )
