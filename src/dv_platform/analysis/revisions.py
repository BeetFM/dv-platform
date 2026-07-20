"""Append-only plan revision records and feedback application."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from dv_platform.agent.contracts import AgentProposal, FeedbackEvent, PlanRevision
from dv_platform.core.models import VerificationPlan


def plan_hash(plan: VerificationPlan) -> str:
    payload = repr(plan).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def revision_store_path(work_dir: Path) -> Path:
    return work_dir / "plans" / "revisions.sqlite"


def record_revision(work_dir: Path, revision: PlanRevision, events: tuple[FeedbackEvent, ...] = ()) -> Path:
    path = revision_store_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table if not exists feedback_events (event_id text primary key, event_json text not null)"
        )
        connection.execute("""create table if not exists plan_revisions (
            revision_id text primary key, module text not null, revision_json text not null,
            created_at text not null)""")
        for event in events:
            connection.execute(
                "insert or ignore into feedback_events values (?, ?)",
                (event.event_id, json.dumps(asdict(event), default=str, sort_keys=True)),
            )
        connection.execute(
            "insert into plan_revisions values (?, ?, ?, ?)",
            (
                revision.revision_id,
                revision.module,
                json.dumps(asdict(revision), default=str, sort_keys=True),
                revision.created_at,
            ),
        )
        connection.commit()
    return path


def read_revisions(work_dir: Path, module: str | None = None) -> tuple[PlanRevision, ...]:
    path = revision_store_path(work_dir)
    if not path.is_file():
        return ()
    with sqlite3.connect(path) as connection:
        query = "select revision_json from plan_revisions"
        values: tuple[str, ...] = ()
        if module is not None:
            query += " where module = ?"
            values = (module,)
        rows = connection.execute(query + " order by created_at, revision_id", values).fetchall()
    return tuple(_revision_from_json(json.loads(row[0])) for row in rows)


def create_feedback_revision(
    work_dir: Path,
    plan: VerificationPlan,
    events: tuple[FeedbackEvent, ...],
    *,
    dry_run: bool = False,
    proposals: tuple[AgentProposal, ...] = (),
    evidence_ids: set[str] | None = None,
    skill_hash: str | None = None,
    model: str | None = None,
) -> PlanRevision:
    input_hash = plan_hash(plan)
    affected_checks = tuple(sorted({event.check_id for event in events if event.check_id}))
    accepted: list[str] = []
    rejected: list[str] = []
    allowed_evidence = evidence_ids or set()
    for proposal in proposals:
        valid = all(
            ref.source_id in allowed_evidence or ref.locator in allowed_evidence for ref in proposal.evidence_refs
        )
        (accepted if valid else rejected).append(proposal.proposal_id)
    changed_requirements = tuple(
        sorted(
            str(proposal.payload["requirement_id"])
            for proposal in proposals
            if proposal.proposal_id in accepted and proposal.payload.get("requirement_id") is not None
        )
    )
    changed_checks = tuple(
        sorted(
            set(affected_checks).union(
                str(proposal.payload["check_id"])
                for proposal in proposals
                if proposal.proposal_id in accepted and proposal.payload.get("check_id") is not None
            )
        )
    )
    previous = read_revisions(work_dir, plan.module)
    parent_revision_id = previous[-1].revision_id if previous else None
    revision = PlanRevision(
        "rev-"
        + hashlib.sha256(
            (input_hash + "|" + str(parent_revision_id) + "|" + "|".join(event.event_id for event in events)).encode()
        ).hexdigest()[:16],
        plan.module,
        parent_revision_id,
        input_hash,
        tuple(event.event_id for event in events),
        tuple(accepted),
        tuple(rejected),
        changed_requirements,
        changed_checks,
        skill_hash,
        model,
        input_hash,
    )
    if not dry_run:
        record_revision(work_dir, revision, events)
    return revision


def _revision_from_json(data: dict[str, Any]) -> PlanRevision:
    tuple_fields = {
        "trigger_event_ids",
        "accepted_proposal_ids",
        "rejected_proposal_ids",
        "changed_requirement_ids",
        "changed_check_ids",
    }
    values = {
        key: tuple(data[key]) if key in tuple_fields else data[key]
        for key in PlanRevision.__dataclass_fields__
        if key in data
    }
    return PlanRevision(
        revision_id=cast(str, values["revision_id"]),
        module=cast(str, values["module"]),
        parent_revision_id=cast(str | None, values.get("parent_revision_id")),
        input_plan_hash=cast(str, values["input_plan_hash"]),
        trigger_event_ids=cast(tuple[str, ...], values.get("trigger_event_ids", ())),
        accepted_proposal_ids=cast(tuple[str, ...], values.get("accepted_proposal_ids", ())),
        rejected_proposal_ids=cast(tuple[str, ...], values.get("rejected_proposal_ids", ())),
        changed_requirement_ids=cast(tuple[str, ...], values.get("changed_requirement_ids", ())),
        changed_check_ids=cast(tuple[str, ...], values.get("changed_check_ids", ())),
        skill_hash=cast(str | None, values.get("skill_hash")),
        model=cast(str | None, values.get("model")),
        resulting_plan_hash=cast(str, values["resulting_plan_hash"]),
        created_at=cast(str, values.get("created_at")),
    )
