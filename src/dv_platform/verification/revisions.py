"""Append-only plan revision records and feedback application."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import ScenarioCoverageGoal, VerificationCheck, VerificationPlan
from dv_platform.domain.agent_contracts import AgentProposal, FeedbackEvent, PlanRevision
from dv_platform.verification.storage import plan_from_json, plan_to_json


def plan_hash(plan: VerificationPlan) -> str:
    payload = json.dumps(plan_to_json(plan), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def project_manifest_hash(work_dir: Path) -> str | None:
    """Hash the analyzed RTL/project identity bound to a revision."""

    path = work_dir / "project-manifest.json"
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision_store_path(work_dir: Path) -> Path:
    return work_dir / "plans" / "revisions.sqlite"


def revision_state_path(work_dir: Path, revision_id: str) -> Path:
    return work_dir / "plans" / "revision-state" / f"{revision_id}.json"


def record_revision_generation(
    work_dir: Path,
    revision: PlanRevision,
    target: str,
    provenance_path: Path,
) -> Path:
    """Record the generated provenance that subsequent runs must match."""

    path = revision_state_path(work_dir, revision.revision_id)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "revision_id": revision.revision_id,
        "module": revision.module,
        "resulting_plan_hash": revision.resulting_plan_hash,
        "generated_targets": {},
    }
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("revision_id") != revision.revision_id:
            raise ValueError(f"Revision generation state is invalid: {path}")
        payload.update(current)
    targets = payload.get("generated_targets")
    if not isinstance(targets, dict):
        raise ValueError(f"Revision generation target state is invalid: {path}")
    provenance_bytes = provenance_path.read_bytes()
    targets[target] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provenance_path": str(provenance_path),
        "provenance_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
    }
    payload["generated_targets"] = targets
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


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
    fork_on_input_change: bool = False,
    selected_scenario_ids: tuple[str, ...] = (),
    scenario_selections: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (),
    affected_artifact_paths: tuple[str, ...] = (),
) -> PlanRevision:
    parent, parent_revision_id, canonical_hash, rtl_hash, base_plan = _revision_base(
        work_dir, plan, fork_on_input_change
    )
    selected_scenario_ids = _validated_scenario_selections(base_plan, selected_scenario_ids, scenario_selections)
    input_hash = plan_hash(base_plan)
    accepted, rejected, rejected_reasons, operation_states = _validated_proposals(proposals, evidence_ids or set())
    resulting_plan, applied, operations = _apply_proposals(base_plan, proposals, accepted, operation_states)
    changed_requirements, changed_checks, impact = _revision_impact(
        resulting_plan,
        applied,
        events,
        selected_scenario_ids,
        affected_artifact_paths,
        operations,
    )
    affected_check_ids, affected_scenario_ids, affected_artifact_paths, required_rerun_targets = impact
    resulting_hash = plan_hash(resulting_plan)
    revision_id = _revision_identifier(
        input_hash,
        parent_revision_id,
        events,
        operations,
        selected_scenario_ids,
        scenario_selections,
        affected_artifact_paths,
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
        canonical_plan_hash=canonical_hash,
        rtl_manifest_hash=rtl_hash,
        parent_snapshot_hash=parent.resulting_plan_hash if parent_revision_id is not None and parent else None,
        affected_check_ids=affected_check_ids,
        affected_scenario_ids=affected_scenario_ids,
        affected_artifact_paths=affected_artifact_paths,
        required_rerun_targets=required_rerun_targets,
        operation_states=tuple(operation_states),
        scenario_selections=tuple(sorted(scenario_selections)),
    )
    if not dry_run:
        record_revision(work_dir, revision, events, resulting_plan)
    return revision


def _revision_base(work_dir, plan, fork_on_input_change):
    previous = read_revisions(work_dir, plan.module)
    parent = previous[-1] if previous else None
    canonical_hash = plan_hash(plan)
    rtl_hash = project_manifest_hash(work_dir)
    input_changed = bool(
        parent
        and (
            (parent.canonical_plan_hash is not None and parent.canonical_plan_hash != canonical_hash)
            or (parent.rtl_manifest_hash is not None and parent.rtl_manifest_hash != rtl_hash)
        )
    )
    if input_changed and not fork_on_input_change:
        raise ValueError("Canonical plan or RTL/project-manifest inputs changed; explicitly fork the revision chain")
    parent_revision_id = None if input_changed else (parent.revision_id if parent else None)
    inherited = read_revision_plan(work_dir, parent_revision_id) if parent_revision_id is not None else None
    base_plan = inherited or plan
    return parent, parent_revision_id, canonical_hash, rtl_hash, base_plan


def _validated_scenario_selections(base_plan, selected_scenario_ids, scenario_selections):
    scenarios_by_id = {scenario.scenario_id: scenario for scenario in base_plan.scenarios}
    if len({scenario_id for scenario_id, _parameters in scenario_selections}) != len(scenario_selections):
        raise ValueError("Scenario selections must reference each deterministic template at most once")
    for scenario_id, parameters in scenario_selections:
        scenario = scenarios_by_id.get(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario selection references an unknown deterministic template: {scenario_id}")
        allowed = {
            f"{index}:{stimulus.kind}:{key}": value
            for index, stimulus in enumerate(scenario.stimulus)
            for key, value in stimulus.parameters
        }
        if any(allowed.get(key) != value for key, value in parameters):
            raise ValueError(f"Scenario selection changes undeclared template parameters: {scenario_id}")
    selected_scenario_ids = tuple(
        sorted({*selected_scenario_ids, *(scenario_id for scenario_id, _parameters in scenario_selections)})
    )
    unknown_scenarios = set(selected_scenario_ids) - set(scenarios_by_id)
    if unknown_scenarios:
        raise ValueError(f"Scenario selections reference unknown templates: {', '.join(sorted(unknown_scenarios))}")
    return selected_scenario_ids


def _validated_proposals(proposals, allowed_evidence):
    accepted: list[str] = []
    rejected: list[str] = []
    rejected_reasons: list[tuple[str, str]] = []
    operation_states: list[tuple[str, str, str]] = []
    for proposal in proposals:
        operation_states.append((proposal.proposal_id, "proposed", "candidate received"))
        valid = all(
            ref.source_id in allowed_evidence or ref.locator in allowed_evidence for ref in proposal.evidence_refs
        )
        if not valid:
            rejected.append(proposal.proposal_id)
            reason = "evidence is outside the normalized task context"
            rejected_reasons.append((proposal.proposal_id, reason))
            operation_states.append((proposal.proposal_id, "rejected", reason))
            continue
        accepted.append(proposal.proposal_id)
        operation_states.append((proposal.proposal_id, "validated", "evidence and schema accepted"))
    return accepted, rejected, rejected_reasons, operation_states


def _apply_proposals(base_plan, proposals, accepted, operation_states):
    resulting_plan = base_plan
    applied: list[AgentProposal] = []
    operations: list[str] = []
    for proposal in proposals:
        if proposal.proposal_id not in accepted:
            continue
        resulting_plan, operation = _apply_safe_operation(resulting_plan, proposal)
        if operation is not None:
            operations.append(operation)
            applied.append(proposal)
            operation_states.append((proposal.proposal_id, "applied", operation))
        else:
            operation_states.append((proposal.proposal_id, "no-op", "operation made no canonical plan change"))
    return resulting_plan, applied, operations


def _revision_impact(resulting_plan, applied, events, selected_scenario_ids, affected_artifact_paths, operations):
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
    actionable_events = tuple(event for event in events if event.outcome not in {"pass", "passed"})
    affected_check_ids = tuple(
        sorted({*changed_check_set, *(event.check_id for event in actionable_events if event.check_id is not None)})
    )
    affected_scenario_ids = tuple(
        sorted(
            {
                *changed_scenarios,
                *selected_scenario_ids,
                *(
                    scenario.scenario_id
                    for scenario in resulting_plan.scenarios
                    if set(scenario.check_ids).intersection(affected_check_ids)
                ),
            }
        )
    )
    affected_artifact_paths = tuple(
        sorted({*affected_artifact_paths, *(path for event in actionable_events for path in event.affected_artifacts)})
    )
    selected_targets = {
        target.value
        for scenario in resulting_plan.scenarios
        if scenario.scenario_id in selected_scenario_ids
        for target in scenario.supported_targets
    }
    required_rerun_targets = tuple(
        sorted(
            {
                *(event.target.value for event in actionable_events),
                *(target.value for target in resulting_plan.targets if operations and not actionable_events),
                *selected_targets,
            }
        )
    )
    impact = (affected_check_ids, affected_scenario_ids, affected_artifact_paths, required_rerun_targets)
    return changed_requirements, changed_checks, impact


def _revision_identifier(
    input_hash,
    parent_revision_id,
    events,
    operations,
    selected_scenario_ids,
    scenario_selections,
    affected_artifact_paths,
):
    return (
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
                + "|"
                + "|".join(sorted(selected_scenario_ids))
                + "|"
                + json.dumps(scenario_selections, sort_keys=True)
                + "|"
                + "|".join(sorted(affected_artifact_paths))
            ).encode()
        ).hexdigest()[:16]
    )


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
        "affected_check_ids",
        "affected_scenario_ids",
        "affected_artifact_paths",
        "required_rerun_targets",
        "operation_states",
        "scenario_selections",
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
        canonical_plan_hash=cast(str | None, values.get("canonical_plan_hash")),
        rtl_manifest_hash=cast(str | None, values.get("rtl_manifest_hash")),
        parent_snapshot_hash=cast(str | None, values.get("parent_snapshot_hash")),
        affected_check_ids=cast(tuple[str, ...], values.get("affected_check_ids", ())),
        affected_scenario_ids=cast(tuple[str, ...], values.get("affected_scenario_ids", ())),
        affected_artifact_paths=cast(tuple[str, ...], values.get("affected_artifact_paths", ())),
        required_rerun_targets=cast(tuple[str, ...], values.get("required_rerun_targets", ())),
        operation_states=tuple(
            (str(item[0]), str(item[1]), str(item[2])) for item in values.get("operation_states", ())
        ),
        scenario_selections=tuple(
            (str(item[0]), tuple((str(pair[0]), str(pair[1])) for pair in item[1]))
            for item in values.get("scenario_selections", ())
        ),
    )
