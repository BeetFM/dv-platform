"""Evidence-backed design review report generation."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dv_platform.core.models import CLIConfig, DesignDecision, EvidenceKind, EvidenceRef, RTLModule, Severity


def generate_design_decisions(modules: tuple[RTLModule, ...]) -> tuple[DesignDecision, ...]:
    """Generate deterministic design review findings from normalized RTL facts."""

    decisions: list[DesignDecision] = []
    for module in modules:
        decisions.extend(_module_decisions(module))
    return tuple(sorted(decisions, key=lambda decision: (_severity_rank(decision.severity), decision.scope, decision.title)))


def generate_run_feedback_decisions(config: CLIConfig) -> tuple[DesignDecision, ...]:
    """Generate review findings from persisted simulation and formal run summaries."""

    runs_dir = config.work_dir / "runs"
    if not runs_dir.is_dir():
        return ()
    decisions: list[DesignDecision] = []
    for summary_path in sorted(runs_dir.rglob("summary.json"), key=lambda path: path.as_posix()):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "modules" in summary:
            continue
        decision = _run_summary_decision(summary_path, summary)
        if decision is not None:
            decisions.append(decision)
    return tuple(sorted(decisions, key=lambda decision: (_severity_rank(decision.severity), decision.scope, decision.title)))


def write_review_outputs(
    config: CLIConfig,
    decisions: tuple[DesignDecision, ...],
) -> tuple[Path, Path, Path]:
    """Write canonical SQLite plus JSON and Markdown design review reports."""

    review_dir = config.work_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = review_dir / "review.sqlite"
    json_path = review_dir / "review.json"
    markdown_path = review_dir / "review.md"

    _write_sqlite(sqlite_path, decisions)
    json_path.write_text(json.dumps(_review_json(decisions), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_review_markdown(decisions), encoding="utf-8")
    return sqlite_path, json_path, markdown_path


def read_review_records(sqlite_path: Path) -> tuple[dict[str, object], ...]:
    """Read persisted design review records for tests and downstream tooling."""

    with sqlite3.connect(sqlite_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "select decision_id, scope, severity, title, decision_json from decisions order by severity_rank, scope, title"
        ).fetchall()
    return tuple(
        {
            "decision_id": str(row["decision_id"]),
            "scope": str(row["scope"]),
            "severity": str(row["severity"]),
            "title": str(row["title"]),
            "decision": json.loads(str(row["decision_json"])),
        }
        for row in rows
    )


def _module_decisions(module: RTLModule) -> tuple[DesignDecision, ...]:
    decisions: list[DesignDecision] = []
    procedural = bool(module.procedural_blocks or module.procedural_block_details)
    assignments = bool(module.continuous_assignments or module.assignment_details)
    output_ports = tuple(port for port in module.port_details if port.direction == "output") or tuple(
        port for port in module.ports if port.endswith(("_o", "_out"))
    )

    if procedural and not (module.clocks or module.clock_details):
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Procedural logic has no classified clock",
                rationale="The module contains procedural blocks, but no clock input was classified from RTL facts.",
                severity=Severity.HIGH,
                recommendation="Confirm whether this module is intended to be combinational, or configure/rename clock signals so checks can target the correct clock domain.",
                evidence_refs=_module_refs(module),
            )
        )

    if procedural and not (module.resets or module.reset_details):
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Procedural logic has no classified reset",
                rationale="The module contains procedural blocks, but no reset input was classified from RTL facts.",
                severity=Severity.MEDIUM,
                recommendation="Document resetless behavior or expose/reset-classify the reset signal used by sequential state.",
                evidence_refs=_module_refs(module),
            )
        )

    if len(module.clock_details or module.clocks) > 1:
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Multiple clocks require explicit verification strategy",
                rationale="More than one clock was classified for the module, which usually requires clock-domain-specific tests and CDC review.",
                severity=Severity.MEDIUM,
                recommendation="Document clock domains and add CDC or multi-clock verification intent before generating advanced tests.",
                evidence_refs=_clock_refs(module),
            )
        )

    if output_ports and not assignments and not procedural:
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Output ports have no extracted drive evidence",
                rationale="The module has output-like ports, but normalized RTL facts did not include continuous assignments or procedural blocks.",
                severity=Severity.HIGH,
                recommendation="Check whether the RTL parser captured all source files and generate blocks, or whether outputs are intentionally undriven stubs.",
                evidence_refs=_port_refs(module),
            )
        )

    if procedural and not module.assertions:
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Procedural module has no extracted assertions",
                rationale="No assertion constructs were extracted for a module with procedural behavior.",
                severity=Severity.LOW,
                recommendation="Consider adding local assertions for reset, illegal states, and interface protocol assumptions.",
                evidence_refs=_module_refs(module),
            )
        )

    if procedural and not module.covers:
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Procedural module has no extracted cover points",
                rationale="No cover constructs were extracted for a module with procedural behavior.",
                severity=Severity.LOW,
                recommendation="Consider adding cover points for reset release, normal transactions, and boundary cases.",
                evidence_refs=_module_refs(module),
            )
        )

    return tuple(decisions)


def _run_summary_decision(summary_path: Path, summary: dict[str, object]) -> DesignDecision | None:
    status = str(summary.get("status", "unknown"))
    return_code = int(summary.get("return_code", 0))
    if status == "passed" and return_code == 0:
        return None

    target = str(summary.get("target", "unknown"))
    module = str(summary.get("module", "unknown"))
    validation_error = summary.get("validation_error")
    results_error = summary.get("results_error")
    formal_error = summary.get("formal_error")
    detail = str(validation_error or results_error or formal_error or f"run exited with status {status} and return code {return_code}")
    severity = Severity.HIGH if status in {"failed", "timeout"} or return_code not in {0, 2} else Severity.MEDIUM
    title = f"{target} run {status}"
    return DesignDecision(
        scope=module,
        title=title,
        rationale=detail,
        severity=severity,
        recommendation="Inspect the run summary, stdout, stderr, and generated artifact provenance before regenerating or waiving the finding.",
        evidence_refs=(
            EvidenceRef(
                kind=EvidenceKind.TOOL_LOG,
                source_id=str(summary_path),
                locator=f"run-summary:{target}:{module}",
                summary=detail,
            ),
        ),
    )


def _write_sqlite(sqlite_path: Path, decisions: tuple[DesignDecision, ...]) -> None:
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            """
            create table if not exists decisions (
                decision_id text primary key,
                scope text not null,
                severity text not null,
                severity_rank integer not null,
                title text not null,
                decision_json text not null
            )
            """
        )
        connection.execute("delete from decisions")
        for decision in decisions:
            connection.execute(
                "insert into decisions(decision_id, scope, severity, severity_rank, title, decision_json) values (?, ?, ?, ?, ?, ?)",
                (
                    _decision_id(decision),
                    decision.scope,
                    str(decision.severity),
                    _severity_rank(decision.severity),
                    decision.title,
                    json.dumps(_decision_to_json(decision), sort_keys=True),
                ),
            )
        connection.commit()


def _review_json(decisions: tuple[DesignDecision, ...]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "finding_count": len(decisions),
        "findings": [_decision_to_json(decision) for decision in decisions],
    }


def _review_markdown(decisions: tuple[DesignDecision, ...]) -> str:
    lines = [
        "# Design Review",
        "",
        f"- findings: {len(decisions)}",
        "",
        "| severity | scope | title | recommendation | evidence refs |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for decision in decisions:
        lines.append(
            "| "
            + " | ".join(
                (
                    str(decision.severity),
                    _escape_markdown_cell(decision.scope),
                    _escape_markdown_cell(decision.title),
                    _escape_markdown_cell(decision.recommendation or ""),
                    str(len(decision.evidence_refs)),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _decision_to_json(decision: DesignDecision) -> dict[str, object]:
    return {
        "decision_id": _decision_id(decision),
        "scope": decision.scope,
        "title": decision.title,
        "rationale": decision.rationale,
        "severity": str(decision.severity),
        "recommendation": decision.recommendation,
        "evidence_refs": [
            {
                "kind": str(ref.kind),
                "source_id": ref.source_id,
                "locator": ref.locator,
                "summary": ref.summary,
            }
            for ref in decision.evidence_refs
        ],
    }


def _decision_id(decision: DesignDecision) -> str:
    return f"{_safe_identifier(decision.scope)}:{_safe_identifier(decision.title).lower()}"


def _module_refs(module: RTLModule) -> tuple[EvidenceRef, ...]:
    return tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0] == f"module:{module.name}") or module.ast_refs


def _port_refs(module: RTLModule) -> tuple[EvidenceRef, ...]:
    prefix = f"port:{module.name}."
    return tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].startswith(prefix)) or module.ast_refs


def _clock_refs(module: RTLModule) -> tuple[EvidenceRef, ...]:
    names = {clock.name for clock in module.clock_details} | set(module.clocks)
    prefix = f"port:{module.name}."
    return tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].removeprefix(prefix) in names) or module.ast_refs


def _severity_rank(severity: Severity) -> int:
    return {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }[severity]


def _safe_identifier(value: str) -> str:
    return "".join(character if character.isalnum() or character == "_" else "_" for character in value)


def _escape_markdown_cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")
