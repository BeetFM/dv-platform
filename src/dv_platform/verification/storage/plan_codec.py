# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Plan persistence and derived review views."""

from __future__ import annotations

from typing import Any

from dv_platform.core.models import (
    AgentPlanningNote,
    AgentPlanProvenance,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.core.schema import MIN_READABLE_PLAN_SCHEMA_VERSION, PLAN_SCHEMA_VERSION
from dv_platform.verification.planning.claims import GenerationGate


def _plan_to_json(plan: VerificationPlan) -> dict[str, object]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "module": plan.module,
        "design_unit": plan.design_unit,
        "elaborated_design_unit": plan.elaborated_design_unit,
        "specialization_id": plan.specialization_id,
        "design_unit_kind": plan.design_unit_kind,
        "targets": [str(target) for target in plan.targets],
        "ports": [
            {
                "name": port.name,
                "direction": port.direction,
                "dtype_id": port.dtype_id,
                "data_type": port.data_type,
                "width": port.width,
                "signed": port.signed,
                "packed_range": port.packed_range,
                "source_location": port.source_location,
                "interface_name": port.interface_name,
                "modport": port.modport,
                "interface_direction": port.interface_direction,
                "packed_dimensions": list(port.packed_dimensions),
                "unpacked_dimensions": list(port.unpacked_dimensions),
            }
            for port in plan.ports
        ],
        "clocks": [
            {
                "name": clock.name,
                "direction": clock.direction,
                "width": clock.width,
                "source_location": clock.source_location,
                "classification": clock.classification,
                "confidence": clock.confidence,
            }
            for clock in plan.clocks
        ],
        "resets": [
            {
                "name": reset.name,
                "direction": reset.direction,
                "width": reset.width,
                "active_low": reset.active_low,
                "source_location": reset.source_location,
                "classification": reset.classification,
                "confidence": reset.confidence,
            }
            for reset in plan.resets
        ],
        "semantic_features": [
            {
                "kind": feature.kind,
                "name": feature.name,
                "source_location": feature.source_location,
                "confidence": feature.confidence,
                "generation_supported": feature.generation_supported,
                "supported_targets": [str(target) for target in feature.supported_targets],
            }
            for feature in plan.semantic_features
        ],
        "parameters": [_parameter_to_json(parameter) for parameter in plan.parameters],
        "memories": [_memory_to_json(memory) for memory in plan.memories],
        "memory_accesses": [_memory_access_to_json(access) for access in plan.memory_accesses],
        "type_details": [_type_to_json(type_detail) for type_detail in plan.type_details],
        "instances": [_instance_to_json(instance) for instance in plan.instances],
        "control_domains": [_control_domain_to_json(domain) for domain in plan.control_domains],
        "cdc_paths": [_cdc_path_to_json(path) for path in plan.cdc_paths],
        "generate_scopes": [_generate_scope_to_json(scope) for scope in plan.generate_scopes],
        "imports": list(plan.imports),
        "protocols": [_protocol_to_json(protocol) for protocol in plan.protocols],
        "protocol_models": [_protocol_model_to_json(protocol) for protocol in plan.protocol_models],
        "register_models": [_register_model_to_json(register) for register in plan.register_models],
        "register_conflicts": [_register_conflict_to_json(conflict) for conflict in plan.register_conflicts],
        "property_details": [_property_to_json(prop) for prop in plan.property_details],
        "depth_policies": [
            {
                "kind": policy.kind,
                "module": policy.module,
                "subject": policy.subject,
                "parameters": [list(item) for item in policy.parameters],
            }
            for policy in plan.depth_policies
        ],
        "requirements": list(plan.requirements),
        "structured_requirements": [
            {
                "requirement_id": requirement.requirement_id,
                "scope": requirement.scope,
                "statement": requirement.statement,
                "category": requirement.category,
                "signals": list(requirement.signals),
                "expected_value": requirement.expected_value,
                "condition": requirement.condition,
                "confidence": requirement.confidence,
                "evidence_refs": [
                    {
                        "kind": str(ref.kind),
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in requirement.evidence_refs
                ],
            }
            for requirement in plan.structured_requirements
        ],
        "requirement_conflicts": [
            {
                "conflict_id": conflict.conflict_id,
                "scope": conflict.scope,
                "requirement_ids": list(conflict.requirement_ids),
                "reason": conflict.reason,
                "evidence_refs": [
                    {
                        "kind": str(ref.kind),
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in conflict.evidence_refs
                ],
            }
            for conflict in plan.requirement_conflicts
        ],
        "behaviors": [
            {
                "behavior_id": behavior.behavior_id,
                "scope": behavior.scope,
                "kind": behavior.kind,
                "target": behavior.target,
                "control": behavior.control,
                "value": behavior.value,
                "source": behavior.source,
                "domain_id": behavior.domain_id,
                "confidence": behavior.confidence,
                "evidence_refs": [
                    {
                        "kind": str(ref.kind),
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in behavior.evidence_refs
                ],
            }
            for behavior in plan.behaviors
        ],
        "claims": [
            {
                "claim_id": claim.claim_id,
                "scope": claim.scope,
                "statement": claim.statement,
                "claim_type": str(claim.claim_type),
                "severity": str(claim.severity),
                "generation_precondition": claim.generation_precondition,
                "status": str(claim.status),
                "evidence_refs": [
                    {
                        "kind": str(ref.kind),
                        "source_id": ref.source_id,
                        "locator": ref.locator,
                        "summary": ref.summary,
                    }
                    for ref in claim.evidence_refs
                ],
            }
            for claim in plan.claims
        ],
        "checks": list(plan.checks),
        "check_details": [_check_to_json(check) for check in plan.check_details],
        "scenarios": [_scenario_to_json(scenario) for scenario in plan.scenarios],
        "assumptions": list(plan.assumptions),
        "open_questions": list(plan.open_questions),
        "agent_assumptions": [_agent_note_to_json(note) for note in plan.agent_assumptions],
        "agent_open_questions": [_agent_note_to_json(note) for note in plan.agent_open_questions],
        "agent_provenance": _agent_provenance_to_json(plan.agent_provenance),
    }


def _gate_to_json(gate: GenerationGate) -> dict[str, object]:
    return {
        "allowed": gate.allowed,
        "blocked": [validation.claim.claim_id for validation in gate.blocked],
        "warnings": [validation.claim.claim_id for validation in gate.warnings],
    }


def _plan_from_json(data: dict[str, Any]) -> VerificationPlan:
    data = _migrate_plan_json(data)
    return VerificationPlan(
        module=str(data["module"]),
        targets=tuple(VerificationTarget(str(target)) for target in data.get("targets", ())),
        design_unit=str(data["design_unit"]) if data.get("design_unit") is not None else None,
        elaborated_design_unit=(
            str(data["elaborated_design_unit"]) if data.get("elaborated_design_unit") is not None else None
        ),
        specialization_id=str(data["specialization_id"]) if data.get("specialization_id") is not None else None,
        design_unit_kind=str(data.get("design_unit_kind", "module")),
        ports=tuple(_port_from_json(item) for item in data.get("ports", ())),
        clocks=tuple(_clock_from_json(item) for item in data.get("clocks", ())),
        resets=tuple(_reset_from_json(item) for item in data.get("resets", ())),
        semantic_features=tuple(_semantic_feature_from_json(item) for item in data.get("semantic_features", ())),
        parameters=tuple(_parameter_from_json(item) for item in data.get("parameters", ())),
        memories=tuple(_memory_from_json(item) for item in data.get("memories", ())),
        memory_accesses=tuple(_memory_access_from_json(item) for item in data.get("memory_accesses", ())),
        type_details=tuple(_type_from_json(item) for item in data.get("type_details", ())),
        instances=tuple(_instance_from_json(item) for item in data.get("instances", ())),
        control_domains=tuple(_control_domain_from_json(item) for item in data.get("control_domains", ())),
        cdc_paths=tuple(_cdc_path_from_json(item) for item in data.get("cdc_paths", ())),
        generate_scopes=tuple(_generate_scope_from_json(item) for item in data.get("generate_scopes", ())),
        imports=tuple(str(item) for item in data.get("imports", ())),
        protocols=tuple(_protocol_from_json(item) for item in data.get("protocols", ())),
        protocol_models=tuple(_protocol_model_from_json(item) for item in data.get("protocol_models", ())),
        register_models=tuple(_register_model_from_json(item) for item in data.get("register_models", ())),
        register_conflicts=tuple(_register_conflict_from_json(item) for item in data.get("register_conflicts", ())),
        property_details=tuple(_property_from_json(item) for item in data.get("property_details", ())),
        depth_policies=tuple(
            VerificationDepthPolicy(
                kind=str(item["kind"]),
                module=str(item["module"]),
                subject=str(item["subject"]),
                parameters=tuple((str(pair[0]), str(pair[1])) for pair in item.get("parameters", ())),
            )
            for item in data.get("depth_policies", ())
        ),
        requirements=tuple(str(item) for item in data.get("requirements", ())),
        structured_requirements=tuple(_requirement_from_json(item) for item in data.get("structured_requirements", ())),
        requirement_conflicts=tuple(_conflict_from_json(item) for item in data.get("requirement_conflicts", ())),
        behaviors=tuple(_behavior_from_json(item) for item in data.get("behaviors", ())),
        claims=tuple(_claim_from_json(item) for item in data.get("claims", ())),
        checks=tuple(str(item) for item in data.get("checks", ())),
        check_details=tuple(_check_from_json(item) for item in data.get("check_details", ())),
        scenarios=tuple(_scenario_from_json(item) for item in data.get("scenarios", ())),
        assumptions=tuple(str(item) for item in data.get("assumptions", ())),
        open_questions=tuple(str(item) for item in data.get("open_questions", ())),
        agent_assumptions=tuple(_agent_note_from_json(item) for item in data.get("agent_assumptions", ())),
        agent_open_questions=tuple(_agent_note_from_json(item) for item in data.get("agent_open_questions", ())),
        agent_provenance=_agent_provenance_from_json(data.get("agent_provenance")),
    )


def _migrate_plan_json(data: dict[str, Any]) -> dict[str, Any]:
    schema_version = int(data.get("schema_version", 1))
    if schema_version > PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported plan schema version {schema_version}; "
            f"this dv-platform build reads up to {PLAN_SCHEMA_VERSION}"
        )
    if schema_version < MIN_READABLE_PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported plan schema version {schema_version}; "
            f"minimum readable version is {MIN_READABLE_PLAN_SCHEMA_VERSION}"
        )
    migrated = _apply_plan_defaults(data, schema_version)
    if schema_version <= 16:
        migrated["scenarios"] = _conservative_legacy_scenarios(migrated)
    migrated["schema_version"] = PLAN_SCHEMA_VERSION
    return migrated


def _apply_plan_defaults(data: dict[str, Any], schema_version: int) -> dict[str, Any]:
    migrated = dict(data)
    defaults_by_version: tuple[tuple[int, dict[str, object]], ...] = (
        (1, {"ports": (), "behaviors": ()}),
        (2, {"clocks": (), "resets": ()}),
        (3, {"requirement_conflicts": (), "semantic_features": ()}),
        (4, {"parameters": (), "memories": (), "instances": (), "control_domains": (), "protocols": ()}),
        (
            5,
            {
                "design_unit": None,
                "elaborated_design_unit": None,
                "specialization_id": None,
                "memory_accesses": (),
                "type_details": (),
                "cdc_paths": (),
                "generate_scopes": (),
                "check_details": (),
            },
        ),
        (6, {"design_unit_kind": "module", "imports": ()}),
        (8, {"depth_policies": ()}),
        (10, {"agent_assumptions": (), "agent_open_questions": (), "agent_provenance": None}),
        (11, {"protocol_models": (), "register_models": ()}),
        (12, {"register_conflicts": ()}),
        (13, {"property_details": ()}),
        (15, {"scenarios": ()}),
    )
    for maximum_version, defaults in defaults_by_version:
        if schema_version <= maximum_version:
            for name, value in defaults.items():
                migrated.setdefault(name, value)
    return migrated


def _conservative_legacy_scenarios(migrated: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    targets = tuple(str(item) for item in migrated.get("targets", ()))
    for raw_scenario in migrated.get("scenarios", ()):
        if not isinstance(raw_scenario, dict):
            continue
        scenario = dict(raw_scenario)
        scenario["supported_targets"] = []
        scenario["target_states"] = [
            {
                "target": target,
                "state": "unsupported",
                "renderer_id": None,
                "reason": "legacy v16 plan predates renderer contract registration; re-plan to qualify",
            }
            for target in targets
        ]
        scenario["executable"] = False
        scenarios.append(scenario)
    return scenarios


def _agent_provenance_to_json(provenance: AgentPlanProvenance | None) -> dict[str, object] | None:
    if provenance is None:
        return None
    return {
        "agent_version": provenance.agent_version,
        "prompt_version": provenance.prompt_version,
        "run_id": provenance.run_id,
        "model": provenance.model,
        "provider": provenance.provider,
        "context_hash": provenance.context_hash,
        "prompt_hash": provenance.prompt_hash,
        "proposal_hash": provenance.proposal_hash,
        "cache_key": provenance.cache_key,
        "cache_status": provenance.cache_status,
        "status": provenance.status,
        "error_category": provenance.error_category,
        "accepted_requirement_ids": list(provenance.accepted_requirement_ids),
        "accepted_check_ids": list(provenance.accepted_check_ids),
    }


def _agent_note_to_json(note: AgentPlanningNote) -> dict[str, object]:
    return {
        "note_id": note.note_id,
        "statement": note.statement,
        "evidence_refs": [
            {
                "kind": str(ref.kind),
                "source_id": ref.source_id,
                "locator": ref.locator,
                "summary": ref.summary,
            }
            for ref in note.evidence_refs
        ],
    }


def _agent_note_from_json(data: dict[str, Any]) -> AgentPlanningNote:
    return AgentPlanningNote(
        note_id=str(data["note_id"]),
        statement=str(data["statement"]),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _agent_provenance_from_json(data: object) -> AgentPlanProvenance | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("Plan agent_provenance must be an object or null")
    return AgentPlanProvenance(
        agent_version=str(data["agent_version"]),
        prompt_version=str(data["prompt_version"]),
        run_id=str(data["run_id"]),
        model=str(data["model"]),
        provider=str(data["provider"]),
        context_hash=str(data["context_hash"]),
        prompt_hash=str(data["prompt_hash"]),
        proposal_hash=str(data["proposal_hash"]) if data.get("proposal_hash") is not None else None,
        cache_key=str(data["cache_key"]) if data.get("cache_key") is not None else None,
        cache_status=str(data.get("cache_status", "disabled")),
        status=str(data.get("status", "fallback")),
        error_category=str(data["error_category"]) if data.get("error_category") is not None else None,
        accepted_requirement_ids=tuple(str(item) for item in data.get("accepted_requirement_ids", ())),
        accepted_check_ids=tuple(str(item) for item in data.get("accepted_check_ids", ())),
    )


def plan_to_json(plan: VerificationPlan) -> dict[str, object]:
    """Return the canonical, versioned representation used by snapshots and hashing."""

    return _plan_to_json(plan)


def plan_from_json(data: dict[str, Any]) -> VerificationPlan:
    """Read a canonical plan representation with all supported migrations."""

    return _plan_from_json(data)
