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
    Severity,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)


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
        "module": plan.module,
        "targets": [str(target) for target in plan.targets],
        "requirements": list(plan.requirements),
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
    return VerificationPlan(
        module=str(data["module"]),
        targets=tuple(VerificationTarget(str(target)) for target in data.get("targets", ())),
        requirements=tuple(str(item) for item in data.get("requirements", ())),
        claims=tuple(_claim_from_json(item) for item in data.get("claims", ())),
        checks=tuple(str(item) for item in data.get("checks", ())),
        assumptions=tuple(str(item) for item in data.get("assumptions", ())),
        open_questions=tuple(str(item) for item in data.get("open_questions", ())),
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
