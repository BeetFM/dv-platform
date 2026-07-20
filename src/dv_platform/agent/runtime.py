"""Small deterministic runtime for loading skills and validating model output."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from dv_platform.agent.contracts import AgentProposal, AgentRun, AgentTask, SkillDescriptor
from dv_platform.core.models import EvidenceKind, EvidenceRef

_INJECTION_MARKERS = ("ignore previous", "system message", "developer message", "</untrusted")


def load_skills(root: Path) -> tuple[SkillDescriptor, ...]:
    return tuple(SkillDescriptor.load(path) for path in sorted(root.glob("*/SKILL.md")))


def invoke_task(
    task: AgentTask, response: str | dict[str, Any], *, known_signals: set[str]
) -> tuple[AgentRun, tuple[AgentProposal, ...]]:
    serialized = json.dumps(response, sort_keys=True)
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
