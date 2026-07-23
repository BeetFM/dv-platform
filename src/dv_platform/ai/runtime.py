"""Small deterministic runtime for loading skills and validating model output."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from dv_platform.core.models import EvidenceKind, EvidenceRef
from dv_platform.domain.agent_contracts import AgentProposal, AgentRun, AgentTask, SkillDescriptor

_INJECTION_MARKERS = ("ignore previous", "system message", "developer message", "</untrusted")


def load_skills(root: Path) -> tuple[SkillDescriptor, ...]:
    return tuple(SkillDescriptor.load(path) for path in sorted(root.glob("*/SKILL.md")))


def invoke_task(
    task: AgentTask, response: str | dict[str, Any], *, known_signals: set[str]
) -> tuple[AgentRun, tuple[AgentProposal, ...]]:
    serialized = response if isinstance(response, str) else json.dumps(response, sort_keys=True)
    lowered = serialized.lower()
    if any(marker in lowered for marker in _INJECTION_MARKERS):
        raise ValueError("agent response contains prompt-injection content")
    try:
        payload = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise ValueError("agent response must be valid JSON") from error
    if not isinstance(payload, list):
        payload = payload.get("proposals") if isinstance(payload, dict) else None
    if not isinstance(payload, list):
        raise ValueError("agent response must contain a proposals array")
    if len(payload) > 100:
        raise ValueError("agent response contains too many proposals")
    proposals: list[AgentProposal] = []
    for item in payload:
        if not isinstance(item, dict) or set(item) - {
            "proposal_id",
            "kind",
            "statement",
            "evidence_ids",
            "payload",
            "executable",
            "signals",
        }:
            raise ValueError("malformed agent proposal")
        evidence_ids = tuple(item.get("evidence_ids", ()))
        if not evidence_ids or any(value not in task.evidence_ids for value in evidence_ids):
            raise ValueError("proposal references unknown evidence")
        signals = tuple(item.get("signals", ()))
        if any(signal not in known_signals for signal in signals):
            raise ValueError("proposal references unknown signal")
        refs = tuple(
            EvidenceRef(EvidenceKind.SEMANTIC_MANIFEST, evidence_id, evidence_id) for evidence_id in evidence_ids
        )
        proposals.append(
            AgentProposal(
                str(item.get("proposal_id", uuid.uuid4())),
                task.task_id,
                str(item.get("kind", "unknown")),
                str(item.get("statement", "")),
                refs,
                item.get("payload", {}),
                bool(item.get("executable", False)),
            )
        )
    run = AgentRun(str(uuid.uuid4()), task.task_id, "completed", task.skill.content_hash, "mock")
    return run, tuple(proposals)


def invoke_task_with_model(
    task: AgentTask,
    *,
    known_signals: set[str],
    gateway: object,
) -> tuple[AgentRun, tuple[AgentProposal, ...]]:
    """Connect the generic runtime to the gated model service without expanding its authority."""

    from dv_platform.ai.gateway import LiteLLMGateway

    if not isinstance(gateway, LiteLLMGateway):
        raise TypeError("gateway must be a LiteLLMGateway")
    schema = {
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
                    "required": ["proposal_id", "kind", "statement", "evidence_ids", "payload", "signals"],
                    "properties": {
                        "proposal_id": {"type": "string"},
                        "kind": {"type": "string"},
                        "statement": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "payload": {"type": "object"},
                        "signals": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }
    context = json.dumps(dict(task.context), sort_keys=True)

    def validate(raw: str) -> None:
        invoke_task(task, raw, known_signals=known_signals)

    result = gateway.execute(
        stage="feedback_analysis",
        system_prompt=task.skill.instructions,
        user_prompt=context,
        response_schema=schema,
        context=context,
        validate=validate,
    )
    if result.response is None:
        run = AgentRun(
            str(uuid.uuid4()),
            task.task_id,
            "fallback",
            task.skill.content_hash,
            gateway.config.ai.model,
            error_category=result.fallback_reason,
        )
        return run, ()
    run, proposals = invoke_task(task, result.response.content, known_signals=known_signals)
    return replace_agent_run_model(run, gateway.config.ai.model), proposals


def replace_agent_run_model(run: AgentRun, model: str) -> AgentRun:
    return AgentRun(
        run.run_id,
        run.task_id,
        run.status,
        run.skill_hash,
        model,
        run.started_at,
        run.finished_at,
        run.proposal_ids,
        run.error_category,
    )


__name__ = "dv_platform.agent.runtime"
