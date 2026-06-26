"""Plan persistence and derived review views."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dv_platform.analysis.claims import GenerationGate, gate_generation, write_claim_reports
from dv_platform.core.models import (
    CLIConfig,
    ClaimStatus,
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    RTLPort,
    Severity,
    VerificationBehavior,
    VerificationClaim,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)


PLAN_SCHEMA_VERSION = 2
MIN_READABLE_PLAN_SCHEMA_VERSION = 1


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

    _write_sqlite(sqlite_path, plans, strict=strict)
    gates = tuple((plan, gate_generation(plan.claims, strict=strict)) for plan in plans)
    module_paths = tuple(_write_module_markdown(module_dir, plan, gate) for plan, gate in gates)
    claim_report_paths = tuple(path for plan, gate in gates for path in write_claim_reports(gate, claims_dir / plan.module))
    index_path = _write_index_markdown(plans_dir, plans)
    return sqlite_path, module_paths, index_path, claim_report_paths


def read_plan_records(sqlite_path: Path) -> tuple[dict[str, object], ...]:
    """Read canonical plan records from SQLite for tests and downstream tooling."""

    with sqlite3.connect(sqlite_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "select module, plan_json, gate_json from plans order by module"
        ).fetchall()
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
    path = module_dir / f"{plan.module}.plan.md"
    lines = [
        f"# {plan.module} Verification Plan",
        "",
        f"- generation_allowed: {str(gate.allowed).lower()}",
        f"- targets: {', '.join(str(target) for target in plan.targets) or 'none'}",
        "",
        "## Checks",
        "",
        *(_bullet_lines(plan.checks) or ["- none"]),
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
        "| id | statement | evidence refs |",
        "| --- | --- | ---: |",
        *(
            [
                "| "
                + " | ".join(
                    (
                        _escape_markdown_cell(requirement.requirement_id),
                        _escape_markdown_cell(requirement.statement),
                        str(len(requirement.evidence_refs)),
                    )
                )
                + " |"
                for requirement in plan.structured_requirements
            ]
            or ["| none | none | 0 |"]
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_index_markdown(plans_dir: Path, plans: tuple[VerificationPlan, ...]) -> Path:
    path = plans_dir / "index.md"
    lines = ["# Verification Plans", "", "| module | checks | open questions |", "| --- | ---: | ---: |"]
    for plan in sorted(plans, key=lambda item: item.module):
        lines.append(f"| {plan.module} | {len(plan.checks)} | {len(plan.open_questions)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _plan_to_json(plan: VerificationPlan) -> dict[str, object]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "module": plan.module,
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
            }
            for port in plan.ports
        ],
        "requirements": list(plan.requirements),
        "structured_requirements": [
            {
                "requirement_id": requirement.requirement_id,
                "scope": requirement.scope,
                "statement": requirement.statement,
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
        "behaviors": [
            {
                "behavior_id": behavior.behavior_id,
                "scope": behavior.scope,
                "kind": behavior.kind,
                "target": behavior.target,
                "control": behavior.control,
                "value": behavior.value,
                "source": behavior.source,
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
        "assumptions": list(plan.assumptions),
        "open_questions": list(plan.open_questions),
    }


def _gate_to_json(gate: GenerationGate) -> dict[str, object]:
    return {
        "allowed": gate.allowed,
        "blocked": [validation.claim.claim_id for validation in gate.blocked],
        "warnings": [validation.claim.claim_id for validation in gate.warnings],
    }


def _plan_from_json(data: dict[str, object]) -> VerificationPlan:
    data = _migrate_plan_json(data)
    return VerificationPlan(
        module=str(data["module"]),
        targets=tuple(VerificationTarget(str(target)) for target in data.get("targets", ())),
        ports=tuple(_port_from_json(item) for item in data.get("ports", ())),
        requirements=tuple(str(item) for item in data.get("requirements", ())),
        structured_requirements=tuple(_requirement_from_json(item) for item in data.get("structured_requirements", ())),
        behaviors=tuple(_behavior_from_json(item) for item in data.get("behaviors", ())),
        claims=tuple(_claim_from_json(item) for item in data.get("claims", ())),
        checks=tuple(str(item) for item in data.get("checks", ())),
        assumptions=tuple(str(item) for item in data.get("assumptions", ())),
        open_questions=tuple(str(item) for item in data.get("open_questions", ())),
    )


def _migrate_plan_json(data: dict[str, object]) -> dict[str, object]:
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
        migrated["schema_version"] = PLAN_SCHEMA_VERSION
    return migrated


def _port_from_json(data: dict[str, object]) -> RTLPort:
    return RTLPort(
        name=str(data["name"]),
        direction=str(data.get("direction", "unknown")),
        dtype_id=str(data["dtype_id"]) if data.get("dtype_id") is not None else None,
        data_type=str(data["data_type"]) if data.get("data_type") is not None else None,
        width=int(data["width"]) if data.get("width") is not None else None,
        signed=bool(data.get("signed", False)),
        packed_range=str(data["packed_range"]) if data.get("packed_range") is not None else None,
        source_location=str(data["source_location"]) if data.get("source_location") is not None else None,
    )


def _requirement_from_json(data: dict[str, object]) -> VerificationRequirement:
    return VerificationRequirement(
        requirement_id=str(data["requirement_id"]),
        scope=str(data["scope"]),
        statement=str(data["statement"]),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _behavior_from_json(data: dict[str, object]) -> VerificationBehavior:
    return VerificationBehavior(
        behavior_id=str(data["behavior_id"]),
        scope=str(data["scope"]),
        kind=str(data["kind"]),
        target=str(data["target"]),
        control=str(data["control"]) if data.get("control") is not None else None,
        value=str(data["value"]) if data.get("value") is not None else None,
        source=str(data["source"]) if data.get("source") is not None else None,
        confidence=str(data.get("confidence", "shape")),
        evidence_refs=tuple(_evidence_from_json(item) for item in data.get("evidence_refs", ())),
    )


def _claim_from_json(data: dict[str, object]) -> VerificationClaim:
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


def _evidence_from_json(data: dict[str, object]) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind(str(data["kind"])),
        source_id=str(data["source_id"]),
        locator=str(data["locator"]),
        summary=str(data["summary"]) if data.get("summary") is not None else None,
    )


def _bullet_lines(items: tuple[str, ...]) -> list[str]:
    return [f"- {item}" for item in items]


def _escape_markdown_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
