# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Optional, evidence-bounded AI augmentation for deterministic plans."""

from __future__ import annotations

from dataclasses import replace

from dv_platform.core.models import (
    AgentPlanningNote,
    EvidenceRef,
    RTLModule,
    VerificationCheck,
    VerificationPlan,
    VerificationRequirement,
)
from dv_platform.verification.planning import (
    _build_check_details,
    _check_category,
    _conflict_claim,
    _conflict_open_question,
    _find_requirement_conflicts,
    _requirement_category,
    _requirement_driven_checks,
    _requirement_open_questions,
)
from dv_platform.verification.scenarios import link_scenario_coverage, validate_scenario

AGENT_VERSION = "litellm-gateway-v2"
PROMPT_VERSION = "planning-proposal-v2"
PROPOSAL_SCHEMA_VERSION = 2
RUN_RECORD_SCHEMA_VERSION = 2
CACHE_SCHEMA_VERSION = 1
MAX_PROPOSAL_ITEMS = 100
MAX_STATEMENT_CHARS = 4096
MAX_SMALL_VALUE_CHARS = 512
SOURCE_CONTEXT_RADIUS = 3
MAX_SOURCE_SNIPPETS = 24
MAX_SOURCE_SNIPPET_LINES = 12


def merge_proposal(
    module: RTLModule,
    baseline: VerificationPlan,
    proposal: PlanningProposal,
    evidence_by_id: dict[str, EvidenceRef],
) -> tuple[VerificationPlan, tuple[str, ...], tuple[str, ...]]:
    """Merge only additive proposal content and re-run deterministic planning gates."""

    merged_requirements, new_requirements, requirement_map, accepted_requirements = _merge_requirements(
        module, baseline, proposal, evidence_by_id
    )
    derived_checks, requirement_claims = _requirement_driven_checks(module, new_requirements)
    old_conflict_ids = {conflict.conflict_id for conflict in baseline.requirement_conflicts}
    new_conflicts = tuple(
        conflict
        for conflict in _find_requirement_conflicts(module, merged_requirements)
        if conflict.conflict_id not in old_conflict_ids
    )
    checks, details, check_map, accepted_checks, questions = _merge_checks(
        module,
        baseline,
        proposal,
        evidence_by_id,
        merged_requirements,
        new_requirements,
        requirement_map,
        derived_checks,
    )
    scenarios, details = _merge_scenarios(
        baseline,
        proposal,
        evidence_by_id,
        merged_requirements,
        requirement_map,
        check_map,
        details,
        questions,
    )
    assumptions, agent_assumptions, agent_questions = _merge_notes(
        module, baseline, proposal, evidence_by_id, questions, new_requirements, new_conflicts
    )
    requirement_statements = list(baseline.requirements)
    requirement_statements.extend(
        item.statement for item in new_requirements if item.statement not in requirement_statements
    )
    merged = replace(
        baseline,
        requirements=tuple(requirement_statements),
        structured_requirements=merged_requirements,
        requirement_conflicts=(*baseline.requirement_conflicts, *new_conflicts),
        claims=(*baseline.claims, *requirement_claims, *(_conflict_claim(item) for item in new_conflicts)),
        checks=tuple(checks),
        check_details=tuple(details),
        scenarios=tuple(scenarios),
        assumptions=tuple(assumptions),
        open_questions=tuple(questions),
        agent_assumptions=(*baseline.agent_assumptions, *agent_assumptions),
        agent_open_questions=(*baseline.agent_open_questions, *agent_questions),
    )
    return merged, tuple(dict.fromkeys(accepted_requirements)), tuple(dict.fromkeys(accepted_checks))


def _merge_requirements(module, baseline, proposal, evidence_by_id):
    requirements = list(baseline.structured_requirements)
    by_statement = {_canonical_statement(item.statement): item for item in requirements}
    proposal_map = {}
    accepted = []
    new = []
    for item in proposal.requirements:
        canonical = _canonical_statement(item.statement)
        existing = by_statement.get(canonical)
        if existing is not None:
            proposal_map[item.proposal_id] = existing
            accepted.append(existing.requirement_id)
            continue
        category = _requirement_category(item.statement)
        identity = "|".join(
            (
                module.name,
                canonical,
                ",".join(sorted(item.signals)),
                _canonical_statement(item.condition or ""),
                _canonical_statement(item.expected_value or ""),
            )
        )
        requirement = VerificationRequirement(
            requirement_id=f"{module.name}:aireq:{_sha256_text(identity)[:12]}",
            scope=module.name,
            statement=item.statement,
            category=category,
            signals=tuple(sorted(item.signals)),
            expected_value=item.expected_value,
            condition=item.condition,
            confidence="agent-proposed",
            evidence_refs=tuple(evidence_by_id[evidence_id] for evidence_id in item.evidence_ids),
        )
        requirements.append(requirement)
        new.append(requirement)
        by_statement[canonical] = requirement
        proposal_map[item.proposal_id] = requirement
        accepted.append(requirement.requirement_id)
    return tuple(requirements), tuple(new), proposal_map, accepted


def _merge_checks(
    module,
    baseline,
    proposal,
    evidence_by_id,
    merged_requirements,
    new_requirements,
    requirement_map,
    derived_checks,
):
    checks = list(baseline.checks)
    details = list(baseline.check_details)
    by_statement = {_canonical_statement(item.statement): item for item in details}
    accepted = []
    stable_by_proposal = {}
    derived_details = _build_check_details(
        module,
        baseline.targets,
        tuple(statement for statement in derived_checks if _canonical_statement(statement) not in by_statement),
        merged_requirements,
        baseline.behaviors,
    )
    for detail in derived_details:
        canonical = _canonical_statement(detail.statement)
        if canonical not in by_statement:
            details.append(detail)
            by_statement[canonical] = detail
            checks.append(detail.statement)
    questions = list(baseline.open_questions)
    for item in proposal.checks:
        canonical = _canonical_statement(item.statement)
        existing = by_statement.get(canonical)
        if existing is not None:
            accepted.append(existing.check_id)
            stable_by_proposal[item.proposal_id] = existing.check_id
            continue
        linked = tuple(requirement_map[identifier] for identifier in item.requirement_ids)
        refs = tuple(
            dict.fromkeys(
                (
                    *(evidence_by_id[evidence_id] for evidence_id in item.evidence_ids),
                    *(ref for requirement in linked for ref in requirement.evidence_refs),
                )
            )
        )
        category = _check_category(canonical)
        check_id = f"{module.name}:check:{_sha256_text('|'.join((module.name, category, canonical)))[:12]}"
        detail = VerificationCheck(
            check_id=check_id,
            statement=item.statement,
            category=category,
            executable=False,
            evidence_refs=refs,
        )
        details.append(detail)
        by_statement[canonical] = detail
        checks.append(item.statement)
        accepted.append(check_id)
        stable_by_proposal[item.proposal_id] = check_id
        question = f"AI-proposed check {check_id} is non-executable; define a deterministic backend mapping and pass/fail contract."
        if question not in questions:
            questions.append(question)
    return checks, details, stable_by_proposal, accepted, questions


def _merge_scenarios(
    baseline,
    proposal,
    evidence_by_id,
    merged_requirements,
    requirement_map,
    check_map,
    details,
    questions,
):
    scenarios = list(baseline.scenarios)
    executable_checks: set[str] = set()
    for proposed in proposal.scenarios:
        candidates = [scenario for scenario in scenarios if scenario.kind == proposed.kind]
        if not candidates:
            question = (
                f"AI-proposed scenario {proposed.proposal_id} is non-executable; "
                "no deterministic scenario exists for the normalized RTL facts."
            )
            if question not in questions:
                questions.append(question)
            continue
        selected = candidates[0]
        linked_checks = tuple(check_map[item] for item in proposed.check_ids)
        linked_requirements = tuple(requirement_map[item].requirement_id for item in proposed.requirement_ids)
        updated = replace(
            selected,
            check_ids=tuple(dict.fromkeys((*selected.check_ids, *linked_checks))),
            requirement_ids=tuple(dict.fromkeys((*selected.requirement_ids, *linked_requirements))),
            evidence_refs=tuple(
                dict.fromkeys((*selected.evidence_refs, *(evidence_by_id[item] for item in proposed.evidence_ids)))
            ),
        )
        validation_plan = replace(baseline, structured_requirements=merged_requirements, check_details=tuple(details))
        if updated.executable and not validate_scenario(validation_plan, updated):
            scenarios[scenarios.index(selected)] = updated
            executable_checks.update(linked_checks)
        else:
            question = f"AI-proposed scenario {proposed.proposal_id} failed deterministic semantic validation."
            if question not in questions:
                questions.append(question)
    if executable_checks:
        details = [replace(item, executable=True) if item.check_id in executable_checks else item for item in details]
    return scenarios, list(link_scenario_coverage(tuple(details), tuple(scenarios)))


def _merge_notes(module, baseline, proposal, evidence_by_id, questions, new_requirements, new_conflicts):
    questions.extend(item.statement for item in proposal.open_questions if item.statement not in questions)
    for question in _requirement_open_questions(module, new_requirements):
        if question not in questions:
            questions.append(question)
    for conflict in new_conflicts:
        question = _conflict_open_question(conflict)
        if question not in questions:
            questions.append(question)
    assumptions = list(baseline.assumptions)
    assumptions.extend(item.statement for item in proposal.assumptions if item.statement not in assumptions)
    agent_assumptions = tuple(
        AgentPlanningNote(
            note_id=f"{module.name}:ai-assumption:{_sha256_text(_canonical_statement(item.statement))[:12]}",
            statement=item.statement,
            evidence_refs=tuple(evidence_by_id[evidence_id] for evidence_id in item.evidence_ids),
        )
        for item in proposal.assumptions
    )
    agent_questions = tuple(
        AgentPlanningNote(
            note_id=f"{module.name}:ai-question:{_sha256_text(_canonical_statement(item.statement))[:12]}",
            statement=item.statement,
            evidence_refs=tuple(evidence_by_id[evidence_id] for evidence_id in item.evidence_ids),
        )
        for item in proposal.open_questions
    )
    return assumptions, agent_assumptions, agent_questions
