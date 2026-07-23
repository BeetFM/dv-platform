# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Plan persistence and derived review views."""

from __future__ import annotations

import shutil
from pathlib import Path

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    VerificationPlan,
)
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.verification.planning.claims import GenerationGate


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


def _bullet_lines(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


def _escape_markdown_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
