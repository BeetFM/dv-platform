"""Append-only plan revision records and feedback application."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

from dv_platform.agent.contracts import AgentProposal, FeedbackEvent, PlanRevision
from dv_platform.analysis.plan_store import plan_from_json, plan_to_json
from dv_platform.core.models import ScenarioCoverageGoal, VerificationCheck, VerificationPlan


def plan_hash(plan: VerificationPlan) -> str:
    payload = json.dumps(plan_to_json(plan), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def revision_store_path(work_dir: Path) -> Path:
    return work_dir / "plans" / "revisions.sqlite"


def record_revision(
    work_dir: Path,
    revision: PlanRevision,
    events: tuple[FeedbackEvent, ...] = (),
    resulting_plan: VerificationPlan | None = None,
) -> Path:
    path = revision_store_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "create table if not exists feedback_events (event_id text primary key, event_json text not null)"
        )
        connection.execute("""create table if not exists plan_revisions (
            revision_id text primary key, module text not null, revision_json text not null,
            created_at text not null, snapshot_json text)""")
        columns = {str(row[1]) for row in connection.execute("pragma table_info(plan_revisions)")}
        if "snapshot_json" not in columns:
            connection.execute("alter table plan_revisions add column snapshot_json text")
        for event in events:
            connection.execute(
                "insert or ignore into feedback_events values (?, ?)",
                (event.event_id, json.dumps(asdict(event), default=str, sort_keys=True)),
            )
        connection.execute(
            "insert into plan_revisions(revision_id, module, revision_json, created_at, snapshot_json) "
            "values (?, ?, ?, ?, ?)",
            (
                revision.revision_id,
                revision.module,
                json.dumps(asdict(revision), default=str, sort_keys=True),
                revision.created_at,
                json.dumps(plan_to_json(resulting_plan), sort_keys=True) if resulting_plan is not None else None,
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


def read_revision_plan(work_dir: Path, revision_id: str) -> VerificationPlan | None:
    """Load the immutable plan snapshot selected by a revision ID."""

    path = revision_store_path(work_dir)
    if not path.is_file():
        return None
    with sqlite3.connect(path) as connection:
        columns = {str(row[1]) for row in connection.execute("pragma table_info(plan_revisions)")}
        if "snapshot_json" not in columns:
            return None
        row = connection.execute(
            "select snapshot_json from plan_revisions where revision_id = ?", (revision_id,)
        ).fetchone()
    if row is None or row[0] is None:
        return None
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise ValueError(f"Revision {revision_id} has an invalid plan snapshot")
    return plan_from_json(payload)


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
    previous = read_revisions(work_dir, plan.module)
    parent_revision_id = previous[-1].revision_id if previous else None
    inherited = read_revision_plan(work_dir, parent_revision_id) if parent_revision_id is not None else None
    base_plan = inherited or plan
    input_hash = plan_hash(base_plan)
    accepted: list[str] = []
    rejected: list[str] = []
    rejected_reasons: list[tuple[str, str]] = []
    operations: list[str] = []
    allowed_evidence = evidence_ids or set()
    for proposal in proposals:
        valid = all(
            ref.source_id in allowed_evidence or ref.locator in allowed_evidence for ref in proposal.evidence_refs
        )
        if not valid:
            rejected.append(proposal.proposal_id)
            rejected_reasons.append((proposal.proposal_id, "evidence is outside the normalized task context"))
            continue
        accepted.append(proposal.proposal_id)
    resulting_plan = base_plan
    applied: list[AgentProposal] = []
    for proposal in proposals:
        if proposal.proposal_id not in accepted:
            continue
        resulting_plan, operation = _apply_safe_operation(resulting_plan, proposal)
        if operation is not None:
            operations.append(operation)
            applied.append(proposal)
    changed_requirements = tuple(
        sorted(
            str(proposal.payload["requirement_id"])
            for proposal in applied
            if proposal.payload.get("requirement_id") is not None
        )
    )
    changed_check_set = {
        str(proposal.payload["check_id"]) for proposal in applied if proposal.payload.get("check_id") is not None
    }
    changed_scenarios = {
        str(proposal.payload["scenario_id"]) for proposal in applied if proposal.payload.get("scenario_id") is not None
    }
    changed_check_set.update(
        check_id
        for scenario in resulting_plan.scenarios
        if scenario.scenario_id in changed_scenarios
        for check_id in scenario.check_ids
    )
    changed_checks = tuple(sorted(changed_check_set))
    resulting_hash = plan_hash(resulting_plan)
    revision_id = (
        "rev-"
        + hashlib.sha256(
            (
                input_hash
                + "|"
                + str(parent_revision_id)
                + "|"
                + "|".join(event.event_id for event in events)
                + "|"
                + "|".join(operations)
            ).encode()
        ).hexdigest()[:16]
    )
    revision = PlanRevision(
        revision_id=revision_id,
        module=plan.module,
        parent_revision_id=parent_revision_id,
        input_plan_hash=input_hash,
        trigger_event_ids=tuple(event.event_id for event in events),
        accepted_proposal_ids=tuple(accepted),
        rejected_proposal_ids=tuple(rejected),
        changed_requirement_ids=changed_requirements,
        changed_check_ids=changed_checks,
        skill_hash=skill_hash,
        model=model,
        resulting_plan_hash=resulting_hash,
        accepted_operations=tuple(operations),
        rejected_proposals=tuple(rejected_reasons),
    )
    if not dry_run:
        record_revision(work_dir, revision, events, resulting_plan)
    return revision


def _apply_safe_operation(plan: VerificationPlan, proposal: AgentProposal) -> tuple[VerificationPlan, str | None]:
    """Apply the bounded revision operations that cannot weaken existing intent."""

    operation = str(proposal.payload.get("operation", ""))
    if operation == "add_check":
        check_id = str(proposal.payload.get("check_id", "")).strip()
        if not check_id or any(check.check_id == check_id for check in plan.check_details):
            return plan, None
        check = VerificationCheck(
            check_id=check_id,
            statement=str(proposal.payload.get("statement") or proposal.statement),
            category=str(proposal.payload.get("category", "general")),
            # A check becomes executable only through a separately validated scenario mapping.
            executable=False,
            evidence_refs=proposal.evidence_refs,
        )
        updated = replace(plan, checks=(*plan.checks, check.statement), check_details=(*plan.check_details, check))
        return updated, json.dumps({"operation": operation, "check_id": check_id}, sort_keys=True)
    if operation == "add_coverage_goal":
        scenario_id = str(proposal.payload.get("scenario_id", ""))
        goal_id = str(proposal.payload.get("goal_id", ""))
        if not scenario_id or not goal_id:
            return plan, None
        changed = False
        scenarios = []
        for scenario in plan.scenarios:
            if scenario.scenario_id != scenario_id or any(goal.goal_id == goal_id for goal in scenario.coverage_goals):
                scenarios.append(scenario)
                continue
            goal = ScenarioCoverageGoal(goal_id, str(proposal.payload.get("kind", "functional")))
            scenarios.append(replace(scenario, coverage_goals=(*scenario.coverage_goals, goal)))
            changed = True
        if not changed:
            return plan, None
        return replace(plan, scenarios=tuple(scenarios)), json.dumps(
            {"operation": operation, "scenario_id": scenario_id, "goal_id": goal_id}, sort_keys=True
        )
    return plan, None


def _revision_from_json(data: dict[str, Any]) -> PlanRevision:
    tuple_fields = {
        "trigger_event_ids",
        "accepted_proposal_ids",
        "rejected_proposal_ids",
        "changed_requirement_ids",
        "changed_check_ids",
        "accepted_operations",
        "rejected_proposals",
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
        schema_version=cast(int, values.get("schema_version", 1)),
        accepted_operations=cast(tuple[str, ...], values.get("accepted_operations", ())),
        rejected_proposals=tuple((str(item[0]), str(item[1])) for item in values.get("rejected_proposals", ())),
    )
