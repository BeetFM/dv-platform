# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Plan persistence and derived review views."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.core.models import (
    CLIConfig,
    VerificationPlan,
)
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.verification.planning.claims import gate_generation, write_claim_reports


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
