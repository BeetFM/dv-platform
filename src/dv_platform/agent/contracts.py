"""Runtime contracts at the boundary between deterministic analysis and agents."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dv_platform.core.models import EvidenceRef, VerificationTarget


def _check_text(value: str, label: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be non-empty and at most {limit} characters")
    return value


@dataclass(frozen=True)
class SkillDescriptor:
    name: str
    version: str
    path: Path
    content_hash: str
    instructions: str

    @classmethod
    def load(cls, path: Path) -> SkillDescriptor:
        skill_file = path if path.name == "SKILL.md" else path / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        match = re.search(r"^name:\s*([^\n]+)\s*$", content, re.MULTILINE)
        version = re.search(r"^version:\s*([^\n]+)\s*$", content, re.MULTILINE)
        if match is None or version is None:
            raise ValueError(f"Skill metadata is incomplete: {skill_file}")
        return cls(
            match.group(1).strip(),
            version.group(1).strip(),
            skill_file.parent,
            hashlib.sha256(content.encode("utf-8")).hexdigest(),
            content,
        )


@dataclass(frozen=True)
class AgentTask:
    task_id: str
    module: str
    skill: SkillDescriptor
    context: Mapping[str, Any]
    evidence_ids: tuple[str, ...] = ()
    target: VerificationTarget | None = None

    def __post_init__(self) -> None:
        _check_text(self.task_id, "task_id", 256)
        _check_text(self.module, "module", 256)
        if any(not isinstance(item, str) or not item for item in self.evidence_ids):
            raise ValueError("evidence_ids must contain non-empty strings")
        object.__setattr__(self, "context", json.loads(json.dumps(dict(self.context))))


@dataclass(frozen=True)
class AgentProposal:
    proposal_id: str
    task_id: str
    kind: str
    statement: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    executable: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.proposal_id, "proposal_id"),
            (self.task_id, "task_id"),
            (self.kind, "kind"),
            (self.statement, "statement"),
        ):
            _check_text(value, label)
        if not self.evidence_refs:
            raise ValueError("agent proposals require evidence references")
        object.__setattr__(self, "payload", json.loads(json.dumps(dict(self.payload))))


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    task_id: str
    status: str
    skill_hash: str
    model: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    proposal_ids: tuple[str, ...] = ()
    error_category: str | None = None


@dataclass(frozen=True)
class FeedbackEvent:
    event_id: str
    source_run: str
    target: VerificationTarget
    module: str
    outcome: str
    check_id: str | None = None
    requirement_id: str | None = None
    behavior_id: str | None = None
    evidence_locator: str | None = None
    failure_category: str | None = None
    affected_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanRevision:
    revision_id: str
    module: str
    parent_revision_id: str | None
    input_plan_hash: str
    trigger_event_ids: tuple[str, ...]
    accepted_proposal_ids: tuple[str, ...]
    rejected_proposal_ids: tuple[str, ...]
    changed_requirement_ids: tuple[str, ...]
    changed_check_ids: tuple[str, ...]
    skill_hash: str | None
    model: str | None
    resulting_plan_hash: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def revision_hash(self) -> str:
        payload = {key: value for key, value in self.__dict__.items() if key != "created_at"}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
