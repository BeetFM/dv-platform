"""Plan persistence and derived review views."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.agent.protocols import ProtocolChannel, ProtocolModel, RegisterConflict, RegisterField, RegisterModel
from dv_platform.analysis.claims import GenerationGate, gate_generation, write_claim_reports
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    AgentPlanningNote,
    AgentPlanProvenance,
    ClaimStatus,
    ClaimType,
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    RTLCDCPath,
    RTLClock,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProperty,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    RTLTypeMember,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    Severity,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationRequirement,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.schema import MIN_READABLE_PLAN_SCHEMA_VERSION, PLAN_SCHEMA_VERSION


def write_plan_outputs(
    config: CLIConfig,
    plans: tuple[VerificationPlan, ...],
    strict: bool = False,
) -> tuple[Path, tuple[Path, ...], Path, tuple[Path, ...]]:
    """Write canonical SQLite plans and derived Markdown views."""

    plans_dir = config.work_dir / "plans"
    sqlite_path = plans_dir / "plans.sqlite"
    module_dir = plans_dir / "modules"
    claims_dir = plans_dir / "claims"
    plans_dir.mkdir(parents=True, exist_ok=True)
    module_dir.mkdir(parents=True, exist_ok=True)
    claims_dir.mkdir(parents=True, exist_ok=True)

    modules = tuple(validate_path_component(plan.module, "plan module") for plan in plans)
    if len(set(modules)) != len(modules):
        raise ValueError("Verification plans contain duplicate module names")

    _write_sqlite(sqlite_path, plans, strict=strict)
    gates = tuple((plan, gate_generation(plan.claims, strict=strict)) for plan in plans)
    module_paths = tuple(_write_module_markdown(module_dir, plan, gate) for plan, gate in gates)
    claim_report_paths = tuple(
        path for plan, gate in gates for path in write_claim_reports(gate, contained_path(claims_dir, plan.module))
    )
    _remove_stale_plan_views(module_dir, claims_dir, set(modules))
    index_path = _write_index_markdown(plans_dir, plans)
    return sqlite_path, module_paths, index_path, claim_report_paths


def read_plan_records(sqlite_path: Path) -> tuple[dict[str, Any], ...]:
    """Read canonical plan records from SQLite for tests and downstream tooling."""

    with sqlite3.connect(sqlite_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("select module, plan_json, gate_json from plans order by module").fetchall()
    return tuple(
        {
            "module": str(row["module"]),
            "plan": json.loads(str(row["plan_json"])),
            "gate": json.loads(str(row["gate_json"])),
        }
        for row in rows
    )


def read_stored_plans(sqlite_path: Path) -> tuple[VerificationPlan, ...]:
    """Read canonical plan records as VerificationPlan objects."""

    return tuple(_plan_from_json(record["plan"]) for record in read_plan_records(sqlite_path))


def _write_sqlite(sqlite_path: Path, plans: tuple[VerificationPlan, ...], strict: bool) -> None:
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            """
            create table if not exists plans (
                module text primary key,
                plan_json text not null,
                gate_json text not null
            )
            """
        )
        connection.execute("delete from plans")
        for plan in plans:
            gate = gate_generation(plan.claims, strict=strict)
            connection.execute(
                "insert into plans(module, plan_json, gate_json) values (?, ?, ?)",
                (
                    plan.module,
                    json.dumps(_plan_to_json(plan), sort_keys=True),
                    json.dumps(_gate_to_json(gate), sort_keys=True),
                ),
            )
        connection.commit()


def _write_module_markdown(module_dir: Path, plan: VerificationPlan, gate: GenerationGate) -> Path:
    module = validate_path_component(plan.module, "plan module")
    path = contained_path(module_dir, f"{module}.plan.md")
    lines = [
        f"# {plan.module} Verification Plan",
        "",
        f"- generation_allowed: {str(gate.allowed).lower()}",
        f"- targets: {', '.join(str(target) for target in plan.targets) or 'none'}",
        f"- design_unit: {plan.design_unit or plan.module}",
        f"- design_unit_kind: {plan.design_unit_kind}",
        f"- elaborated_design_unit: {plan.elaborated_design_unit or 'unknown'}",
        f"- specialization_id: {plan.specialization_id or 'none'}",
        f"- imports: {', '.join(plan.imports) or 'none'}",
        f"- ai_augmentation: {plan.agent_provenance.status if plan.agent_provenance else 'not-requested'}",
        "",
        "## Checks",
        "",
        "| id | category | executable | closure | points | statement | evidence refs |",
        "| --- | --- | --- | --- | ---: | --- | ---: |",
        *(
            [
                f"| {_escape_markdown_cell(check.check_id)} | {_escape_markdown_cell(check.category)} | "
                f"{str(check.executable).lower()} | {_escape_markdown_cell(check.closure_status or 'unmeasured')} | "
                f"{len(check.coverage_point_ids)} | {_escape_markdown_cell(check.statement)} | "
                f"{len(check.evidence_refs)} |"
                for check in plan.check_details
            ]
            or [
                f"| legacy-{index} | general | false | unmeasured | 0 | {_escape_markdown_cell(check)} | 0 |"
                for index, check in enumerate(plan.checks, 1)
            ]
            or ["| none | none | false | none | 0 | none | 0 |"]
        ),
        "",
        "## Executable Scenarios",
        "",
        "| id | kind | executable | target states | checks | requirements | coverage goals |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
        *(
            [
                f"| {_escape_markdown_cell(scenario.scenario_id)} | {_escape_markdown_cell(scenario.kind)} | "
                f"{str(scenario.executable).lower()} | "
                f"{_escape_markdown_cell(', '.join(f'{item.target}:{item.state}' for item in scenario.target_states))} | "
                f"{len(scenario.check_ids)} | {len(scenario.requirement_ids)} | {len(scenario.coverage_goals)} |"
                for scenario in plan.scenarios
            ]
            or ["| none | none | false | none | 0 | 0 | 0 |"]
        ),
        "",
        "## Requirements",
        "",
        *(_bullet_lines(plan.requirements) or ["- none"]),
        "",
        "## Ports",
        "",
        "| name | direction | width | signed |",
        "| --- | --- | ---: | --- |",
        *(
            [
                "| "
                + " | ".join(
                    (
                        _escape_markdown_cell(port.name),
                        _escape_markdown_cell(port.direction),
                        str(port.width if port.width is not None else ""),
                        str(port.signed).lower(),
                    )
                )
                + " |"
                for port in plan.ports
            ]
            or ["| none | none |  | false |"]
        ),
        "",
        "## Structured Requirements",
        "",
        "| id | category | signals | expected | confidence | statement | evidence refs |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
        *(
            [
                "| "
                + " | ".join(
                    (
                        _escape_markdown_cell(requirement.requirement_id),
                        _escape_markdown_cell(requirement.category),
                        _escape_markdown_cell(", ".join(requirement.signals)),
                        _escape_markdown_cell(requirement.expected_value or ""),
                        _escape_markdown_cell(requirement.confidence),
                        _escape_markdown_cell(requirement.statement),
                        str(len(requirement.evidence_refs)),
                    )
                )
                + " |"
                for requirement in plan.structured_requirements
            ]
            or ["| none | none | none | none | none | none | 0 |"]
        ),
        "",
        "## Elaborated Parameters",
        "",
        "| name | value | width | signed | local |",
        "| --- | --- | ---: | --- | --- |",
        *(
            [
                f"| {_escape_markdown_cell(parameter.name)} | "
                f"{_escape_markdown_cell(parameter.default_value or '')} | "
                f"{parameter.width or ''} | {str(parameter.signed).lower()} | {str(parameter.local).lower()} |"
                for parameter in plan.parameters
            ]
            or ["| none | none |  | false | false |"]
        ),
        "",
        "## Memories",
        "",
        "| name | element width | depth | address width | read-during-write | accesses |",
        "| --- | ---: | ---: | ---: | --- | ---: |",
        *(
            [
                f"| {_escape_markdown_cell(memory.name)} | {memory.element_width or ''} | {memory.depth or ''} | "
                f"{memory.address_width or ''} | {_escape_markdown_cell(memory.read_during_write)} | "
                f"{sum(1 for access in plan.memory_accesses if access.memory == memory.name)} |"
                for memory in plan.memories
            ]
            or ["| none |  |  |  | none | 0 |"]
        ),
        "",
        "## Hierarchy",
        "",
        "| instance | source module | elaborated module | connections |",
        "| --- | --- | --- | ---: |",
        *(
            [
                f"| {_escape_markdown_cell(instance.name)} | "
                f"{_escape_markdown_cell(instance.module_name or '')} | "
                f"{_escape_markdown_cell(instance.elaborated_module_name or '')} | "
                f"{len(instance.connections)} |"
                for instance in plan.instances
            ]
            or ["| none | none | none | 0 |"]
        ),
        "",
        "## Control Domains",
        "",
        "| id | clock | edge | reset | reset edge | asynchronous |",
        "| --- | --- | --- | --- | --- | --- |",
        *(
            [
                f"| {_escape_markdown_cell(domain.domain_id)} | {_escape_markdown_cell(domain.clock)} | "
                f"{_escape_markdown_cell(domain.clock_edge)} | {_escape_markdown_cell(domain.reset or '')} | "
                f"{_escape_markdown_cell(domain.reset_edge or '')} | "
                f"{str(domain.asynchronous_reset).lower()} |"
                for domain in plan.control_domains
            ]
            or ["| none | none | none | none | none | false |"]
        ),
        "",
        "## Protocol Channels",
        "",
        "| id | role | valid | ready | data | clock |",
        "| --- | --- | --- | --- | --- | --- |",
        *(
            [
                f"| {_escape_markdown_cell(protocol.protocol_id)} | {_escape_markdown_cell(protocol.role)} | "
                f"{_escape_markdown_cell(protocol.valid)} | {_escape_markdown_cell(protocol.ready)} | "
                f"{_escape_markdown_cell(protocol.data or '')} | {_escape_markdown_cell(protocol.clock or '')} |"
                for protocol in plan.protocols
            ]
            or ["| none | none | none | none | none | none |"]
        ),
        "",
        "## Register Models",
        "",
        "| name | offset | width | fields | source | evidence refs |",
        "| --- | ---: | ---: | ---: | --- | ---: |",
        *(
            [
                f"| {_escape_markdown_cell(register.name)} | {register.offset if register.offset is not None else 'unknown'} | "
                f"{register.width} | {len(register.fields)} | {_escape_markdown_cell(register.source)} | "
                f"{len(register.evidence_refs)} |"
                for register in plan.register_models
            ]
            or ["| none |  |  | 0 | none | 0 |"]
        ),
        *(
            [
                f"- conflict: {_escape_markdown_cell(conflict.register_name)}.{_escape_markdown_cell(conflict.property_name)}: "
                f"{_escape_markdown_cell(conflict.reason)}"
                for conflict in plan.register_conflicts
            ]
        ),
        "",
        "## CDC Paths",
        "",
        "| signal | source | destination | classification | stages | safe | reset compatible |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
        *(
            [
                f"| {_escape_markdown_cell(path.signal)} | {_escape_markdown_cell(path.source_domain)} | "
                f"{_escape_markdown_cell(path.destination_domain)} | {_escape_markdown_cell(path.classification)} | "
                f"{path.synchronizer_stages} | {str(path.safe).lower()} | "
                f"{str(path.reset_compatible).lower() if path.reset_compatible is not None else 'unknown'} |"
                for path in plan.cdc_paths
            ]
            or ["| none | none | none | none | 0 | false | unknown |"]
        ),
        "",
        "## Requirement Conflicts",
        "",
        "| id | requirement ids | reason | evidence refs |",
        "| --- | --- | --- | ---: |",
        *(
            [
                "| "
                + " | ".join(
                    (
                        _escape_markdown_cell(conflict.conflict_id),
                        _escape_markdown_cell(", ".join(conflict.requirement_ids)),
                        _escape_markdown_cell(conflict.reason),
                        str(len(conflict.evidence_refs)),
                    )
                )
                + " |"
                for conflict in plan.requirement_conflicts
            ]
            or ["| none | none | none | 0 |"]
        ),
        "",
        "## Behaviors",
        "",
        "| id | kind | target | control | value | evidence refs |",
        "| --- | --- | --- | --- | --- | ---: |",
        *(
            [
                "| "
                + " | ".join(
                    (
                        _escape_markdown_cell(behavior.behavior_id),
                        _escape_markdown_cell(behavior.kind),
                        _escape_markdown_cell(behavior.target),
                        _escape_markdown_cell(behavior.control or ""),
                        _escape_markdown_cell(behavior.value or ""),
                        str(len(behavior.evidence_refs)),
                    )
                )
                + " |"
                for behavior in plan.behaviors
            ]
            or ["| none | none | none | none | none | 0 |"]
        ),
        "",
        "## Assumptions",
        "",
        *(_bullet_lines(plan.assumptions) or ["- none"]),
        "",
        "## Open Questions",
        "",
        *(_bullet_lines(plan.open_questions) or ["- none"]),
        "",
        "## AI Evidence-Linked Notes",
        "",
        "| kind | id | statement | evidence refs |",
        "| --- | --- | --- | ---: |",
        *(
            [
                f"| assumption | {_escape_markdown_cell(note.note_id)} | "
                f"{_escape_markdown_cell(note.statement)} | {len(note.evidence_refs)} |"
                for note in plan.agent_assumptions
            ]
            + [
                f"| open question | {_escape_markdown_cell(note.note_id)} | "
                f"{_escape_markdown_cell(note.statement)} | {len(note.evidence_refs)} |"
                for note in plan.agent_open_questions
            ]
            or ["| none | none | none | 0 |"]
        ),
        "",
        "## Claims",
        "",
        "| status | severity | id | statement |",
        "| --- | --- | --- | --- |",
    ]
    for claim in plan.claims:
        lines.append(
            "| "
            + " | ".join(
                (
                    str(claim.status),
                    str(claim.severity),
                    _escape_markdown_cell(claim.claim_id),
                    _escape_markdown_cell(claim.statement),
                )
            )
            + " |"
        )
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path


def _write_index_markdown(plans_dir: Path, plans: tuple[VerificationPlan, ...]) -> Path:
    path = plans_dir / "index.md"
    lines = ["# Verification Plans", "", "| module | checks | open questions |", "| --- | ---: | ---: |"]
    for plan in sorted(plans, key=lambda item: item.module):
        lines.append(f"| {plan.module} | {len(plan.checks)} | {len(plan.open_questions)} |")
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path


def _remove_stale_plan_views(module_dir: Path, claims_dir: Path, expected_modules: set[str]) -> None:
    expected_files = {f"{module}.plan.md" for module in expected_modules}
    for path in module_dir.glob("*.plan.md"):
        if path.name not in expected_files:
            path.unlink()
    for path in claims_dir.iterdir():
        if path.name in expected_modules:
            continue
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)


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
    migrated = dict(data)
    if schema_version == 1:
        migrated.setdefault("ports", ())
        migrated.setdefault("behaviors", ())
    if schema_version <= 2:
        migrated.setdefault("clocks", ())
        migrated.setdefault("resets", ())
    if schema_version <= 3:
        migrated.setdefault("requirement_conflicts", ())
        migrated.setdefault("semantic_features", ())
    if schema_version <= 4:
        migrated.setdefault("parameters", ())
        migrated.setdefault("memories", ())
        migrated.setdefault("instances", ())
        migrated.setdefault("control_domains", ())
        migrated.setdefault("protocols", ())
    if schema_version <= 5:
        migrated.setdefault("design_unit", None)
        migrated.setdefault("elaborated_design_unit", None)
        migrated.setdefault("specialization_id", None)
        migrated.setdefault("memory_accesses", ())
        migrated.setdefault("type_details", ())
        migrated.setdefault("cdc_paths", ())
        migrated.setdefault("generate_scopes", ())
        migrated.setdefault("check_details", ())
    if schema_version <= 6:
        migrated.setdefault("design_unit_kind", "module")
        migrated.setdefault("imports", ())
    if schema_version <= 8:
        migrated.setdefault("depth_policies", ())
    if schema_version <= 10:
        migrated.setdefault("agent_assumptions", ())
        migrated.setdefault("agent_open_questions", ())
        migrated.setdefault("agent_provenance", None)
    if schema_version <= 11:
        migrated.setdefault("protocol_models", ())
        migrated.setdefault("register_models", ())
    if schema_version <= 12:
        migrated.setdefault("register_conflicts", ())
    if schema_version <= 13:
        migrated.setdefault("property_details", ())
    if schema_version <= 15:
        # Older prose checks are intentionally not promoted to executable intent.
        migrated.setdefault("scenarios", ())
    if schema_version <= 16:
        # v16 target lists came from a static mapping table. Preserve intent but
        # never promote it without a v17 renderer/validator/trace/decoder record.
        conservative_scenarios: list[dict[str, Any]] = []
        plan_targets = tuple(str(item) for item in migrated.get("targets", ()))
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
                for target in plan_targets
            ]
            scenario["executable"] = False
            conservative_scenarios.append(scenario)
        migrated["scenarios"] = conservative_scenarios
    migrated["schema_version"] = PLAN_SCHEMA_VERSION
    return migrated


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


def _port_from_json(data: dict[str, Any]) -> RTLPort:
    return RTLPort(
        name=str(data["name"]),
        direction=str(data.get("direction", "unknown")),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        packed_range=str(data["packed_range"]) if data.get("packed_range") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        interface_name=str(data["interface_name"]) if data.get("interface_name") is not None else None,
        modport=str(data["modport"]) if data.get("modport") is not None else None,
        interface_direction=(str(data["interface_direction"]) if data.get("interface_direction") is not None else None),
        packed_dimensions=tuple(str(item) for item in data.get("packed_dimensions", ())),
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
    )


def _clock_from_json(data: dict[str, Any]) -> RTLClock:
    return RTLClock(
        name=str(data["name"]),
        direction=str(data.get("direction", "input")),
        width=int(data["width"]) if data.get("width") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
        confidence=str(data.get("confidence", "low")),
    )


def _reset_from_json(data: dict[str, Any]) -> RTLReset:
    return RTLReset(
        name=str(data["name"]),
        direction=str(data.get("direction", "input")),
        width=int(data["width"]) if data.get("width") is not None else None,
        active_low=bool(data["active_low"]) if data.get("active_low") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        classification=str(data.get("classification", "name_heuristic")),
        confidence=str(data.get("confidence", "low")),
    )


def _semantic_feature_from_json(data: dict[str, Any]) -> RTLSemanticFeature:
    return RTLSemanticFeature(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        confidence=str(data.get("confidence", "parser")),
        generation_supported=bool(data.get("generation_supported", False)),
        supported_targets=tuple(VerificationTarget(str(item)) for item in data.get("supported_targets", ())),
    )


def _parameter_to_json(parameter: RTLParameter) -> dict[str, object]:
    return {
        "name": parameter.name,
        "default_value": parameter.default_value,
        "dtype_id": parameter.dtype_id,
        "data_type": parameter.data_type,
        "width": parameter.width,
        "signed": parameter.signed,
        "local": parameter.local,
        "source_location": parameter.source_location,
    }


def _parameter_from_json(data: dict[str, Any]) -> RTLParameter:
    return RTLParameter(
        name=str(data["name"]),
        default_value=str(data["default_value"]) if data.get("default_value") is not None else None,
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        local=bool(data.get("local", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _memory_to_json(memory: RTLMemory) -> dict[str, object]:
    return {
        "name": memory.name,
        "dtype_id": memory.dtype_id,
        "element_width": memory.element_width,
        "depth": memory.depth,
        "address_width": memory.address_width,
        "read_during_write": memory.read_during_write,
        "source_location": memory.source_location,
        "unpacked_dimensions": list(memory.unpacked_dimensions),
    }


def _memory_from_json(data: dict[str, Any]) -> RTLMemory:
    return RTLMemory(
        name=str(data["name"]),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        element_width=int(data["element_width"]) if data.get("element_width") is not None else None,
        depth=int(data["depth"]) if data.get("depth") is not None else None,
        address_width=int(data["address_width"]) if data.get("address_width") is not None else None,
        read_during_write=str(data.get("read_during_write", "unknown")),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
    )


def _memory_access_to_json(access: RTLMemoryAccess) -> dict[str, object]:
    return {
        "access_id": access.access_id,
        "memory": access.memory,
        "kind": access.kind,
        "address_signals": list(access.address_signals),
        "data_signals": list(access.data_signals),
        "enable_signals": list(access.enable_signals),
        "domain_id": access.domain_id,
        "synchronous": access.synchronous,
        "source_location": access.source_location,
        "evidence_refs": [_evidence_to_json(ref) for ref in access.evidence_refs],
    }


def _memory_access_from_json(data: dict[str, Any]) -> RTLMemoryAccess:
    return RTLMemoryAccess(
        access_id=str(data["access_id"]),
        memory=str(data["memory"]),
        kind=str(data["kind"]),
        address_signals=tuple(str(item) for item in data.get("address_signals", ())),
        data_signals=tuple(str(item) for item in data.get("data_signals", ())),
        enable_signals=tuple(str(item) for item in data.get("enable_signals", ())),
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
        synchronous=bool(data.get("synchronous", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _type_to_json(type_detail: RTLType) -> dict[str, object]:
    return {
        "type_id": type_detail.type_id,
        "name": type_detail.name,
        "kind": type_detail.kind,
        "width": type_detail.width,
        "signed": type_detail.signed,
        "members": list(type_detail.members),
        "enum_values": list(type_detail.enum_values),
        "source_location": type_detail.source_location,
        "member_details": [
            {
                "name": member.name,
                "dtype_id": member.dtype_id,
                "width": member.width,
                "signed": member.signed,
                "packed_range": member.packed_range,
                "bit_offset": member.bit_offset,
                "packed_dimensions": list(member.packed_dimensions),
                "unpacked_dimensions": list(member.unpacked_dimensions),
                "source_location": member.source_location,
            }
            for member in type_detail.member_details
        ],
        "packed_dimensions": list(type_detail.packed_dimensions),
        "unpacked_dimensions": list(type_detail.unpacked_dimensions),
        "package_name": type_detail.package_name,
    }


def _type_from_json(data: dict[str, Any]) -> RTLType:
    return RTLType(
        type_id=str(data["type_id"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        kind=str(data["kind"]),
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        members=tuple(str(item) for item in data.get("members", ())),
        enum_values=tuple(str(item) for item in data.get("enum_values", ())),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        member_details=tuple(
            RTLTypeMember(
                name=str(item["name"]),
                dtype_id=str(item["dtype_id"]) if item.get("dtype_id") is not None else None,
                width=int(item["width"]) if item.get("width") is not None else None,
                signed=bool(item["signed"]) if item.get("signed") is not None else None,
                packed_range=str(item["packed_range"]) if item.get("packed_range") is not None else None,
                bit_offset=int(item["bit_offset"]) if item.get("bit_offset") is not None else None,
                packed_dimensions=tuple(str(value) for value in item.get("packed_dimensions", ())),
                unpacked_dimensions=tuple(str(value) for value in item.get("unpacked_dimensions", ())),
                source_location=str(item["source_location"]) if item.get("source_location") is not None else None,
            )
            for item in data.get("member_details", ())
        ),
        packed_dimensions=tuple(str(item) for item in data.get("packed_dimensions", ())),
        unpacked_dimensions=tuple(str(item) for item in data.get("unpacked_dimensions", ())),
        package_name=str(data["package_name"]) if data.get("package_name") is not None else None,
    )


def _expression_to_json(expression: RTLExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "value": expression.value,
        "dtype_id": expression.dtype_id,
        "source_location": expression.source_location,
        "children": [_expression_to_json(child) for child in expression.children],
        "width": expression.width,
        "signed": expression.signed,
        "cast_kind": expression.cast_kind,
        "packed_range": expression.packed_range,
    }


def _expression_from_json(data: dict[str, Any]) -> RTLExpression:
    return RTLExpression(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        children=tuple(_expression_from_json(item) for item in data.get("children", ())),
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data["signed"]) if data.get("signed") is not None else None,
        cast_kind=str(data["cast_kind"]) if data.get("cast_kind") is not None else None,
        packed_range=str(data["packed_range"]) if data.get("packed_range") is not None else None,
    )


def _connection_to_json(connection: RTLConnection) -> dict[str, object]:
    return {
        "port_name": connection.port_name,
        "direction": connection.direction,
        "signal_refs": list(connection.signal_refs),
        "expression": _expression_to_json(connection.expression) if connection.expression is not None else None,
        "source_location": connection.source_location,
    }


def _connection_from_json(data: dict[str, Any]) -> RTLConnection:
    expression = data.get("expression")
    return RTLConnection(
        port_name=str(data["port_name"]),
        direction=str(data["direction"]) if data.get("direction") is not None else None,
        signal_refs=tuple(str(item) for item in data.get("signal_refs", ())),
        expression=_expression_from_json(expression) if isinstance(expression, dict) else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _instance_to_json(instance: RTLInstance) -> dict[str, object]:
    return {
        "name": instance.name,
        "module_name": instance.module_name,
        "elaborated_module_name": instance.elaborated_module_name,
        "plan_module_name": instance.plan_module_name,
        "specialization_id": instance.specialization_id,
        "parameter_bindings": [
            {"name": binding.name, "value": binding.value} for binding in instance.parameter_bindings
        ],
        "kind": instance.kind,
        "source_location": instance.source_location,
        "connections": [_connection_to_json(connection) for connection in instance.connections],
    }


def _instance_from_json(data: dict[str, Any]) -> RTLInstance:
    return RTLInstance(
        name=str(data["name"]),
        module_name=str(data["module_name"]) if data.get("module_name") is not None else None,
        elaborated_module_name=(
            str(data["elaborated_module_name"]) if data.get("elaborated_module_name") is not None else None
        ),
        plan_module_name=str(data["plan_module_name"]) if data.get("plan_module_name") is not None else None,
        specialization_id=str(data["specialization_id"]) if data.get("specialization_id") is not None else None,
        parameter_bindings=tuple(
            RTLParameterBinding(
                name=str(item["name"]),
                value=str(item["value"]) if item.get("value") is not None else None,
            )
            for item in data.get("parameter_bindings", ())
        ),
        kind=str(data["kind"]) if data.get("kind") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        connections=tuple(_connection_from_json(item) for item in data.get("connections", ())),
    )


def _control_domain_to_json(domain: RTLControlDomain) -> dict[str, object]:
    return {
        "domain_id": domain.domain_id,
        "clock": domain.clock,
        "clock_edge": domain.clock_edge,
        "reset": domain.reset,
        "reset_edge": domain.reset_edge,
        "reset_active_low": domain.reset_active_low,
        "asynchronous_reset": domain.asynchronous_reset,
        "source_location": domain.source_location,
    }


def _control_domain_from_json(data: dict[str, Any]) -> RTLControlDomain:
    return RTLControlDomain(
        domain_id=str(data["domain_id"]),
        clock=str(data["clock"]),
        clock_edge=str(data.get("clock_edge", "pos")),
        reset=str(data["reset"]) if data.get("reset") is not None else None,
        reset_edge=str(data["reset_edge"]) if data.get("reset_edge") is not None else None,
        reset_active_low=bool(data["reset_active_low"]) if data.get("reset_active_low") is not None else None,
        asynchronous_reset=bool(data.get("asynchronous_reset", False)),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _cdc_path_to_json(path: RTLCDCPath) -> dict[str, object]:
    return {
        "path_id": path.path_id,
        "signal": path.signal,
        "source_domain": path.source_domain,
        "destination_domain": path.destination_domain,
        "classification": path.classification,
        "synchronizer_stages": path.synchronizer_stages,
        "stage_signals": list(path.stage_signals),
        "safe": path.safe,
        "reset_compatible": path.reset_compatible,
        "source_location": path.source_location,
        "evidence_refs": [_evidence_to_json(ref) for ref in path.evidence_refs],
    }


def _cdc_path_from_json(data: dict[str, Any]) -> RTLCDCPath:
    return RTLCDCPath(
        path_id=str(data["path_id"]),
        signal=str(data["signal"]),
        source_domain=str(data["source_domain"]),
        destination_domain=str(data["destination_domain"]),
        classification=str(data.get("classification", "direct")),
        synchronizer_stages=int(data.get("synchronizer_stages", 0)),
        stage_signals=tuple(str(item) for item in data.get("stage_signals", ())),
        safe=bool(data.get("safe", False)),
        reset_compatible=(bool(data["reset_compatible"]) if data.get("reset_compatible") is not None else None),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _generate_scope_to_json(scope: RTLGenerateScope) -> dict[str, object]:
    return {
        "scope_id": scope.scope_id,
        "name": scope.name,
        "kind": scope.kind,
        "source_location": scope.source_location,
        "instance_names": list(scope.instance_names),
        "condition": _expression_to_json(scope.condition) if scope.condition is not None else None,
        "selected": scope.selected,
        "iteration_index": scope.iteration_index,
    }


def _generate_scope_from_json(data: dict[str, Any]) -> RTLGenerateScope:
    condition = data.get("condition")
    return RTLGenerateScope(
        scope_id=str(data["scope_id"]),
        name=str(data["name"]),
        kind=str(data["kind"]),
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        instance_names=tuple(str(item) for item in data.get("instance_names", ())),
        condition=_expression_from_json(condition) if isinstance(condition, dict) else None,
        selected=bool(data["selected"]) if data.get("selected") is not None else None,
        iteration_index=int(data["iteration_index"]) if data.get("iteration_index") is not None else None,
    )


def _property_to_json(prop: RTLProperty) -> dict[str, object]:
    return {
        "kind": prop.kind,
        "name": prop.name,
        "concurrent": prop.concurrent,
        "clock": prop.clock,
        "clock_edge": prop.clock_edge,
        "disable_condition": (
            _expression_to_json(prop.disable_condition) if prop.disable_condition is not None else None
        ),
        "body": _expression_to_json(prop.body) if prop.body is not None else None,
        "source_location": prop.source_location,
        "support_status": prop.support_status,
        "unsupported_operators": list(prop.unsupported_operators),
    }


def _property_from_json(data: dict[str, Any]) -> RTLProperty:
    disable = data.get("disable_condition")
    body = data.get("body")
    return RTLProperty(
        kind=str(data["kind"]),
        name=str(data["name"]) if data.get("name") is not None else None,
        concurrent=bool(data.get("concurrent", False)),
        clock=str(data["clock"]) if data.get("clock") is not None else None,
        clock_edge=str(data["clock_edge"]) if data.get("clock_edge") is not None else None,
        disable_condition=_expression_from_json(disable) if isinstance(disable, dict) else None,
        body=_expression_from_json(body) if isinstance(body, dict) else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
        support_status=str(data.get("support_status", "unsupported")),
        unsupported_operators=tuple(str(item) for item in data.get("unsupported_operators", ())),
    )


def _protocol_to_json(protocol: RTLProtocol) -> dict[str, object]:
    return {
        "protocol_id": protocol.protocol_id,
        "kind": protocol.kind,
        "name": protocol.name,
        "role": protocol.role,
        "valid": protocol.valid,
        "ready": protocol.ready,
        "data": protocol.data,
        "data_width": protocol.data_width,
        "clock": protocol.clock,
        "reset": protocol.reset,
        "confidence": protocol.confidence,
        "profile": protocol.profile,
        "signal_map": [list(item) for item in protocol.signal_map],
        "evidence_refs": [_evidence_to_json(ref) for ref in protocol.evidence_refs],
    }


def _protocol_from_json(data: dict[str, Any]) -> RTLProtocol:
    return RTLProtocol(
        protocol_id=str(data["protocol_id"]),
        kind=str(data["kind"]),
        name=str(data["name"]),
        role=str(data["role"]),
        valid=str(data["valid"]),
        ready=str(data["ready"]),
        data=str(data["data"]) if data.get("data") is not None else None,
        data_width=int(data["data_width"]) if data.get("data_width") is not None else None,
        clock=str(data["clock"]) if data.get("clock") is not None else None,
        reset=str(data["reset"]) if data.get("reset") is not None else None,
        confidence=str(data.get("confidence", "naming")),
        profile=str(data.get("profile", "builtin")),
        signal_map=tuple((str(item[0]), str(item[1])) for item in data.get("signal_map", ())),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _protocol_model_to_json(protocol: ProtocolModel) -> dict[str, object]:
    return {
        "name": protocol.name,
        "version": protocol.version,
        "channels": [
            {
                "name": channel.name,
                "signals": list(channel.signals),
                "direction": channel.direction,
                "transfer_condition": channel.transfer_condition,
                "payload_fields": list(channel.payload_fields),
                "completion_condition": channel.completion_condition,
                "evidence_refs": [_evidence_to_json(ref) for ref in channel.evidence_refs],
            }
            for channel in protocol.channels
        ],
        "signal_bindings": [list(item) for item in protocol.signal_bindings],
        "signal_directions": [list(item) for item in protocol.signal_directions],
        "clock_domain": protocol.clock_domain,
        "reset_domain": protocol.reset_domain,
        "ordering_rules": list(protocol.ordering_rules),
        "response_rules": list(protocol.response_rules),
        "error_behavior": protocol.error_behavior,
        "confidence": protocol.confidence,
        "unsupported_semantics": list(protocol.unsupported_semantics),
        "evidence_refs": [_evidence_to_json(ref) for ref in protocol.evidence_refs],
        "profile_id": protocol.profile_id,
        "instance_id": protocol.instance_id,
        "role": protocol.role,
        "maximum_burst_length": protocol.maximum_burst_length,
        "maximum_outstanding": protocol.maximum_outstanding,
        "timeout_cycles": protocol.timeout_cycles,
        "scoreboard_keys": list(protocol.scoreboard_keys),
        "coverage_bins": list(protocol.coverage_bins),
        "formal_properties": list(protocol.formal_properties),
        "result_traces": list(protocol.result_traces),
    }


def _protocol_model_from_json(data: dict[str, Any]) -> ProtocolModel:
    return ProtocolModel(
        name=str(data["name"]),
        version=str(data["version"]),
        channels=tuple(
            ProtocolChannel(
                name=str(item["name"]),
                signals=tuple(str(value) for value in item.get("signals", ())),
                direction=str(item["direction"]),
                transfer_condition=str(item["transfer_condition"]),
                evidence_refs=tuple(_evidence_from_json(ref) for ref in item.get("evidence_refs", ())),
                payload_fields=tuple(str(value) for value in item.get("payload_fields", ())),
                completion_condition=(
                    str(item["completion_condition"]) if item.get("completion_condition") is not None else None
                ),
            )
            for item in data.get("channels", ())
        ),
        signal_bindings=tuple((str(item[0]), str(item[1])) for item in data.get("signal_bindings", ())),
        signal_directions=tuple((str(item[0]), str(item[1])) for item in data.get("signal_directions", ())),
        clock_domain=str(data["clock_domain"]) if data.get("clock_domain") is not None else None,
        reset_domain=str(data["reset_domain"]) if data.get("reset_domain") is not None else None,
        ordering_rules=tuple(str(item) for item in data.get("ordering_rules", ())),
        response_rules=tuple(str(item) for item in data.get("response_rules", ())),
        error_behavior=str(data.get("error_behavior", "unknown")),
        confidence=str(data.get("confidence", "unknown")),
        unsupported_semantics=tuple(str(item) for item in data.get("unsupported_semantics", ())),
        evidence_refs=tuple(_evidence_from_json(ref) for ref in data.get("evidence_refs", ())),
        profile_id=str(data["profile_id"]) if data.get("profile_id") is not None else None,
        instance_id=str(data["instance_id"]) if data.get("instance_id") is not None else None,
        role=str(data.get("role", "subordinate")),
        maximum_burst_length=int(data.get("maximum_burst_length", 1)),
        maximum_outstanding=int(data.get("maximum_outstanding", 1)),
        timeout_cycles=int(data.get("timeout_cycles", 32)),
        scoreboard_keys=tuple(str(item) for item in data.get("scoreboard_keys", ("sequence",))),
        coverage_bins=tuple(str(item) for item in data.get("coverage_bins", ())),
        formal_properties=tuple(str(item) for item in data.get("formal_properties", ())),
        result_traces=tuple(str(item) for item in data.get("result_traces", ())),
    )


def _register_model_to_json(register: RegisterModel) -> dict[str, object]:
    return {
        "name": register.name,
        "offset": register.offset,
        "width": register.width,
        "fields": [
            {
                "name": field.name,
                "msb": field.msb,
                "lsb": field.lsb,
                "reset_value": field.reset_value,
                "access": field.access,
                "side_effect": field.side_effect,
                "reserved": field.reserved,
                "evidence_refs": [_evidence_to_json(ref) for ref in field.evidence_refs],
            }
            for field in register.fields
        ],
        "invalid_address_behavior": register.invalid_address_behavior,
        "byte_enable_behavior": register.byte_enable_behavior,
        "source": register.source,
        "evidence_refs": [_evidence_to_json(ref) for ref in register.evidence_refs],
    }


def _register_model_from_json(data: dict[str, Any]) -> RegisterModel:
    return RegisterModel(
        name=str(data["name"]),
        offset=int(data["offset"]) if data.get("offset") is not None else None,
        width=int(data["width"]),
        fields=tuple(
            RegisterField(
                name=str(item["name"]),
                msb=int(item["msb"]),
                lsb=int(item["lsb"]),
                reset_value=str(item["reset_value"]) if item.get("reset_value") is not None else None,
                access=str(item.get("access", "unknown")),
                side_effect=str(item["side_effect"]) if item.get("side_effect") is not None else None,
                reserved=bool(item.get("reserved", False)),
                evidence_refs=tuple(_evidence_from_json(ref) for ref in item.get("evidence_refs", ())),
            )
            for item in data.get("fields", ())
        ),
        invalid_address_behavior=str(data.get("invalid_address_behavior", "unknown")),
        byte_enable_behavior=str(data.get("byte_enable_behavior", "unknown")),
        source=str(data.get("source", "unknown")),
        evidence_refs=tuple(_evidence_from_json(ref) for ref in data.get("evidence_refs", ())),
    )


def _register_conflict_to_json(conflict: RegisterConflict) -> dict[str, object]:
    return {
        "register_name": conflict.register_name,
        "property_name": conflict.property_name,
        "values": list(conflict.values),
        "reason": conflict.reason,
        "evidence_refs": [_evidence_to_json(ref) for ref in conflict.evidence_refs],
    }


def _register_conflict_from_json(data: dict[str, Any]) -> RegisterConflict:
    return RegisterConflict(
        str(data["register_name"]),
        str(data["property_name"]),
        tuple(str(item) for item in data.get("values", ())),
        str(data["reason"]),
        tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _check_to_json(check: VerificationCheck) -> dict[str, object]:
    return {
        "check_id": check.check_id,
        "statement": check.statement,
        "category": check.category,
        "executable": check.executable,
        "evidence_refs": [_evidence_to_json(ref) for ref in check.evidence_refs],
        "closure_status": check.closure_status,
        "coverage_point_ids": list(check.coverage_point_ids),
    }


def _check_from_json(data: dict[str, Any]) -> VerificationCheck:
    return VerificationCheck(
        check_id=str(data["check_id"]),
        statement=str(data["statement"]),
        category=str(data.get("category", "general")),
        executable=bool(data.get("executable", False)),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
        closure_status=str(data["closure_status"]) if data.get("closure_status") is not None else None,
        coverage_point_ids=tuple(str(item) for item in data.get("coverage_point_ids", ())),
    )


def _scenario_to_json(scenario: VerificationScenario) -> dict[str, object]:
    return {
        "scenario_id": scenario.scenario_id,
        "kind": scenario.kind,
        "stimulus": [
            {
                "kind": item.kind,
                "signal": item.signal,
                "value": item.value,
                "parameters": [list(pair) for pair in item.parameters],
            }
            for item in scenario.stimulus
        ],
        "oracle": {
            "kind": scenario.oracle.kind,
            "actual": scenario.oracle.actual,
            "expected": scenario.oracle.expected,
            "condition": scenario.oracle.condition,
        },
        "completion": {
            "kind": scenario.completion.kind,
            "signal": scenario.completion.signal,
            "value": scenario.completion.value,
            "timeout_cycles": scenario.completion.timeout_cycles,
        },
        "coverage_goals": [
            {"goal_id": goal.goal_id, "kind": goal.kind, "bins": list(goal.bins)} for goal in scenario.coverage_goals
        ],
        "supported_targets": [str(target) for target in scenario.supported_targets],
        "target_states": [
            {
                "target": str(item.target),
                "state": str(item.state),
                "renderer_id": item.renderer_id,
                "reason": item.reason,
            }
            for item in scenario.target_states
        ],
        "requirement_ids": list(scenario.requirement_ids),
        "check_ids": list(scenario.check_ids),
        "evidence_refs": [_evidence_to_json(ref) for ref in scenario.evidence_refs],
        "executable": scenario.executable,
    }


def _scenario_from_json(data: dict[str, Any]) -> VerificationScenario:
    oracle = data.get("oracle", {})
    completion = data.get("completion", {})
    if not isinstance(oracle, dict) or not isinstance(completion, dict):
        raise ValueError("Plan scenario oracle and completion must be objects")
    return VerificationScenario(
        scenario_id=str(data["scenario_id"]),
        kind=str(data["kind"]),
        stimulus=tuple(
            ScenarioStimulus(
                kind=str(item["kind"]),
                signal=str(item["signal"]) if item.get("signal") is not None else None,
                value=str(item["value"]) if item.get("value") is not None else None,
                parameters=tuple((str(pair[0]), str(pair[1])) for pair in item.get("parameters", ())),
            )
            for item in data.get("stimulus", ())
        ),
        oracle=ScenarioOracle(
            kind=str(oracle["kind"]),
            actual=str(oracle["actual"]) if oracle.get("actual") is not None else None,
            expected=str(oracle["expected"]) if oracle.get("expected") is not None else None,
            condition=str(oracle["condition"]) if oracle.get("condition") is not None else None,
        ),
        completion=ScenarioCompletion(
            kind=str(completion["kind"]),
            signal=str(completion["signal"]) if completion.get("signal") is not None else None,
            value=str(completion["value"]) if completion.get("value") is not None else None,
            timeout_cycles=int(completion.get("timeout_cycles", 32)),
        ),
        coverage_goals=tuple(
            ScenarioCoverageGoal(
                str(item["goal_id"]), str(item["kind"]), tuple(str(value) for value in item.get("bins", ()))
            )
            for item in data.get("coverage_goals", ())
        ),
        supported_targets=tuple(VerificationTarget(str(item)) for item in data.get("supported_targets", ())),
        target_states=tuple(
            ScenarioTargetSupport(
                VerificationTarget(str(item["target"])),
                ScenarioTargetState(str(item["state"])),
                str(item["renderer_id"]) if item.get("renderer_id") is not None else None,
                str(item["reason"]) if item.get("reason") is not None else None,
            )
            for item in data.get("target_states", ())
        ),
        requirement_ids=tuple(str(item) for item in data.get("requirement_ids", ())),
        check_ids=tuple(str(item) for item in data.get("check_ids", ())),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
        executable=bool(data.get("executable", False)),
    )


def plan_to_json(plan: VerificationPlan) -> dict[str, object]:
    """Return the canonical, versioned representation used by snapshots and hashing."""

    return _plan_to_json(plan)


def plan_from_json(data: dict[str, Any]) -> VerificationPlan:
    """Read a canonical plan representation with all supported migrations."""

    return _plan_from_json(data)


def _requirement_from_json(data: dict[str, Any]) -> VerificationRequirement:
    return VerificationRequirement(
        requirement_id=str(data["requirement_id"]),
        scope=str(data["scope"]),
        statement=str(data["statement"]),
        category=str(data.get("category", "general")),
        signals=tuple(str(item) for item in data.get("signals", ())),
        expected_value=str(data["expected_value"]) if data.get("expected_value") is not None else None,
        condition=str(data["condition"]) if data.get("condition") is not None else None,
        confidence=str(data.get("confidence", "lexical")),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _conflict_from_json(data: dict[str, Any]) -> RequirementConflict:
    return RequirementConflict(
        conflict_id=str(data["conflict_id"]),
        scope=str(data["scope"]),
        requirement_ids=tuple(str(item) for item in data.get("requirement_ids", ())),
        reason=str(data["reason"]),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _behavior_from_json(data: dict[str, Any]) -> VerificationBehavior:
    return VerificationBehavior(
        behavior_id=str(data["behavior_id"]),
        scope=str(data["scope"]),
        kind=str(data["kind"]),
        target=str(data["target"]),
        control=str(data["control"]) if data.get("control") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        source=str(data["source"]) if data.get("source") is not None else None,
        domain_id=str(data["domain_id"]) if data.get("domain_id") is not None else None,
        confidence=str(data.get("confidence", "shape")),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _claim_from_json(data: dict[str, Any]) -> VerificationClaim:
    return VerificationClaim(
        claim_id=str(data["claim_id"]),
        scope=str(data["scope"]),
        statement=str(data["statement"]),
        claim_type=ClaimType(str(data["claim_type"])),
        severity=Severity(str(data["severity"])),
        generation_precondition=bool(data["generation_precondition"]),
        status=ClaimStatus(str(data["status"])),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _evidence_from_json(data: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind(str(data["kind"])),
        source_id=str(data["source_id"]),
        locator=str(data["locator"]),
        summary=str(data["summary"]) if data.get("summary") is not None else None,
    )


def _evidence_to_json(ref: EvidenceRef) -> dict[str, object]:
    return {
        "kind": str(ref.kind),
        "source_id": ref.source_id,
        "locator": ref.locator,
        "summary": ref.summary,
    }


def _bullet_lines(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


def _escape_markdown_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
