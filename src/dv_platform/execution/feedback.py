"""Normalize run outcomes into stable feedback events."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from dv_platform.agent.contracts import FeedbackEvent
from dv_platform.core.models import VerificationTarget

_OUTCOMES = {"pass", "fail", "timeout", "unexecuted", "unsupported", "uncovered"}


def normalize_feedback(
    records: Iterable[Mapping[str, Any]], *, target: VerificationTarget, module: str, source_run: str
) -> tuple[FeedbackEvent, ...]:
    events: list[FeedbackEvent] = []
    for index, record in enumerate(records):
        outcome = str(record.get("outcome", record.get("status", "unsupported"))).lower()
        if outcome not in _OUTCOMES:
            outcome = "unsupported"
        check_id = _optional(record.get("check_id"))
        requirement_id = _optional(record.get("requirement_id"))
        behavior_id = _optional(record.get("behavior_id"))
        locator = _optional(record.get("evidence_locator", record.get("locator")))
        category = _optional(record.get("failure_category")) or _category(outcome)
        identity = json.dumps([source_run, module, str(target), index, check_id, outcome], sort_keys=True)
        event_id = "feedback-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        artifacts = tuple(str(value) for value in record.get("affected_artifacts", ()) if isinstance(value, str))
        events.append(
            FeedbackEvent(
                event_id,
                source_run,
                target,
                module,
                outcome,
                check_id,
                requirement_id,
                behavior_id,
                locator,
                category,
                artifacts,
            )
        )
    return tuple(events)


def _optional(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


def _category(outcome: str) -> str | None:
    return {
        "fail": "assertion_failure",
        "timeout": "timeout",
        "unexecuted": "not_run",
        "unsupported": "unsupported_mapping",
        "uncovered": "coverage_gap",
    }.get(outcome)


__name__ = "dv_platform.analysis.feedback"
