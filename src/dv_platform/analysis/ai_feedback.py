"""Evidence-bounded feedback revision proposals through the reusable AI gateway."""

from __future__ import annotations

import json

from dv_platform.agent.contracts import AgentProposal, FeedbackEvent
from dv_platform.analysis.ai_gateway import GatewayResult, LiteLLMGateway
from dv_platform.core.models import EvidenceKind, EvidenceRef, VerificationPlan


def propose_feedback_operations(
    gateway: LiteLLMGateway,
    plan: VerificationPlan,
    events: tuple[FeedbackEvent, ...],
) -> tuple[tuple[AgentProposal, ...], set[str], GatewayResult]:
    """Ask only for additive plan operations; never source, commands, waivers, or RTL changes."""

    evidence = {
        event.event_id: EvidenceRef(
            EvidenceKind.TOOL_LOG,
            event.event_id,
            event.evidence_locator or f"run:{event.source_run}",
            f"{event.outcome}:{event.check_id or 'unlinked'}",
        )
        for event in events
    }
    context = json.dumps(
        {
            "module": plan.module,
            "events": [
                {
                    "evidence_id": event.event_id,
                    "outcome": event.outcome,
                    "check_id": event.check_id,
                    "requirement_id": event.requirement_id,
                    "failure_category": event.failure_category,
                }
                for event in events
            ],
            "scenarios": [scenario.scenario_id for scenario in plan.scenarios],
        },
        sort_keys=True,
    )
    schema = _feedback_schema()
    parsed: list[dict[str, object]] = []

    def validate(raw: str) -> None:
        parsed.clear()
        parsed.extend(_validate_feedback_response(raw, set(evidence), plan))

    result = gateway.execute(
        stage="feedback_analysis",
        system_prompt=(
            "Propose only additive verification-plan operations backed by supplied evidence. "
            "Never delete requirements, weaken oracles, waive failures, choose files/commands, or alter RTL."
        ),
        user_prompt=context,
        response_schema=schema,
        context=context,
        validate=validate,
    )
    proposals: list[AgentProposal] = []
    for item in parsed:
        linked = item["evidence_ids"]
        if not isinstance(linked, list):
            raise ValueError("validated feedback evidence_ids changed type")
        proposals.append(
            AgentProposal(
                proposal_id=str(item["proposal_id"]),
                task_id=f"feedback:{plan.module}",
                kind=str(item["operation"]),
                statement=str(item["statement"]),
                evidence_refs=tuple(evidence[str(value)] for value in linked),
                payload={key: value for key, value in item.items() if key not in {"proposal_id", "evidence_ids"}},
            )
        )
    return tuple(proposals), set(evidence), result


def _feedback_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["proposals"],
        "properties": {
            "proposals": {
                "type": "array",
                "maxItems": 100,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "proposal_id",
                        "operation",
                        "statement",
                        "check_id",
                        "scenario_id",
                        "goal_id",
                        "category",
                        "kind",
                        "evidence_ids",
                    ],
                    "properties": {
                        "proposal_id": {"type": "string"},
                        "operation": {"type": "string", "enum": ["add_check", "add_coverage_goal"]},
                        "statement": {"type": "string"},
                        "check_id": {"type": ["string", "null"]},
                        "scenario_id": {"type": ["string", "null"]},
                        "goal_id": {"type": ["string", "null"]},
                        "category": {"type": ["string", "null"]},
                        "kind": {"type": ["string", "null"]},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                    },
                },
            }
        },
    }


def _validate_feedback_response(
    raw: str, evidence_ids: set[str], plan: VerificationPlan
) -> tuple[dict[str, object], ...]:
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {"proposals"} or not isinstance(payload["proposals"], list):
        raise ValueError("feedback response must contain only a proposals list")
    scenarios = {scenario.scenario_id for scenario in plan.scenarios}
    result: list[dict[str, object]] = []
    for item in payload["proposals"]:
        if not isinstance(item, dict) or set(item) != {
            "proposal_id",
            "operation",
            "statement",
            "check_id",
            "scenario_id",
            "goal_id",
            "category",
            "kind",
            "evidence_ids",
        }:
            raise ValueError("feedback proposal has unknown or missing fields")
        linked = item["evidence_ids"]
        if not isinstance(linked, list) or not linked or any(value not in evidence_ids for value in linked):
            raise ValueError("feedback proposal contains invented evidence")
        operation = item["operation"]
        if operation == "add_check" and not item.get("check_id"):
            raise ValueError("add_check requires check_id")
        if operation == "add_coverage_goal" and (item.get("scenario_id") not in scenarios or not item.get("goal_id")):
            raise ValueError("add_coverage_goal requires an existing scenario and goal_id")
        result.append(item)
    return tuple(result)
