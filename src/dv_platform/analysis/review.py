"""Evidence-backed design review report generation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, DesignDecision, EvidenceKind, EvidenceRef, RTLModule, Severity


def generate_design_decisions(modules: tuple[RTLModule, ...]) -> tuple[DesignDecision, ...]:
    """Generate deterministic design review findings from normalized RTL facts."""

    decisions: list[DesignDecision] = []
    for module in modules:
        decisions.extend(_module_decisions(module))
    return tuple(
        sorted(decisions, key=lambda decision: (_severity_rank(decision.severity), decision.scope, decision.title))
    )


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
        if not _run_summary_is_current(config, summary):
            continue
        decision = _run_summary_decision(summary_path, summary)
        if decision is not None:
            decisions.append(decision)
    return tuple(
        sorted(decisions, key=lambda decision: (_severity_rank(decision.severity), decision.scope, decision.title))
    )


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
    atomic_write_text(json_path, json.dumps(_review_json(decisions), indent=2, sort_keys=True) + "\n")
    atomic_write_text(markdown_path, _review_markdown(decisions))
    return sqlite_path, json_path, markdown_path


def read_review_records(sqlite_path: Path) -> tuple[dict[str, Any], ...]:
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
    has_output_ports = any(port.direction == "output" for port in module.port_details) or any(
        port.endswith(("_o", "_out")) for port in module.ports
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

    incomplete_instances = tuple(
        instance for instance in module.instance_details if instance.module_name is None or not instance.connections
    )
    if incomplete_instances:
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Hierarchy connection metadata is incomplete",
                rationale=(
                    f"{len(incomplete_instances)} child instance(s) lack a resolved source module or structured port "
                    "connections, limiting wrapper connectivity checks."
                ),
                severity=Severity.HIGH,
                recommendation="Confirm the configured top and complete source list, then inspect the Verilator hierarchy facts before generating wrapper-level checks.",
                evidence_refs=_module_refs(module),
            )
        )

    if module.memories:
        unknown_shape = any(memory.element_width is None or memory.depth is None for memory in module.memories)
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Memory boundary behavior needs verification",
                rationale=(
                    "One or more unpacked memories were extracted"
                    + (", and at least one memory has an unresolved element width or depth." if unknown_shape else ".")
                ),
                severity=Severity.HIGH if unknown_shape else Severity.MEDIUM,
                recommendation="Verify empty/full boundaries, simultaneous read/write behavior, pointer wrap, and overflow/underflow policy for every extracted memory.",
                evidence_refs=_module_refs(module),
            )
        )

    if module.protocols and not module.assertions:
        channel_names = ", ".join(protocol.name for protocol in module.protocols)
        decisions.append(
            DesignDecision(
                scope=module.name,
                title="Ready/valid channels need protocol closure",
                rationale=f"Structured ready/valid channels ({channel_names}) were extracted without local RTL assertions.",
                severity=Severity.MEDIUM,
                recommendation="Close transfer, backpressure stability, reset, latency, and data-integrity checks in generated tests and add local protocol assertions where practical.",
                evidence_refs=tuple(
                    dict.fromkeys(ref for protocol in module.protocols for ref in protocol.evidence_refs)
                )
                or _module_refs(module),
            )
        )

    if has_output_ports and not assignments and not procedural:
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


def _run_summary_decision(summary_path: Path, summary: dict[str, Any]) -> DesignDecision | None:
    status = str(summary.get("status", "unknown"))
    return_code = int(summary.get("return_code", 0))
    coverage = summary.get("verification_coverage")
    coverage_complete = bool(coverage.get("complete")) if isinstance(coverage, dict) else False
    if status == "passed" and return_code == 0 and coverage_complete:
        return None

    target = str(summary.get("target", "unknown"))
    module = str(summary.get("module", "unknown"))
    validation_error = summary.get("validation_error")
    results_error = summary.get("results_error")
    formal_error = summary.get("formal_error")
    if status == "passed" and return_code == 0:
        detail = "The run passed, but generated plan traceability was absent or not fully executed."
    else:
        detail = str(
            validation_error
            or results_error
            or formal_error
            or f"run exited with status {status} and return code {return_code}"
        )
    triage = summary.get("triage")
    triage_category = str(triage.get("category")) if isinstance(triage, dict) else "unclassified"
    severity = Severity.HIGH if status in {"failed", "timeout"} or return_code not in {0, 2} else Severity.MEDIUM
    title = (
        f"{target} run {status}" if not (status == "passed" and return_code == 0) else f"{target} coverage incomplete"
    )
    repair_suggestions = summary.get("repair_suggestions")
    recommendation = (
        " ".join(str(item) for item in repair_suggestions)
        if isinstance(repair_suggestions, list) and repair_suggestions
        else "Inspect the run summary, stdout, stderr, and generated artifact provenance before regenerating or waiving the finding."
    )
    trace_refs = _trace_evidence_refs(summary)
    return DesignDecision(
        scope=module,
        title=title,
        rationale=f"Triage: {triage_category}. {detail}",
        severity=severity,
        recommendation=recommendation,
        evidence_refs=(
            EvidenceRef(
                kind=EvidenceKind.TOOL_LOG,
                source_id=str(summary_path),
                locator=f"run-summary:{target}:{module}",
                summary=detail,
            ),
            *trace_refs,
        ),
    )


def _run_summary_is_current(config: CLIConfig, summary: dict[str, Any]) -> bool:
    target = str(summary.get("target", ""))
    module = str(summary.get("module", ""))
    if not target or not module:
        return False
    module_dir = (
        config.output_dir / "formal" / "modules" / module
        if target == "formal"
        else config.output_dir / "simulation" / target / "modules" / module
    )
    provenance_path = module_dir / "provenance.json"
    if not provenance_path.is_file():
        return False
    try:
        current_hash = hashlib.sha256(provenance_path.read_bytes()).hexdigest()
    except OSError:
        return False
    return summary.get("provenance_sha256") == current_hash


def _trace_evidence_refs(summary: dict[str, Any]) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    traces = summary.get("failure_traceability")
    if not isinstance(traces, list):
        return ()
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        for item in trace.get("evidence_refs", ()):
            if not isinstance(item, dict):
                continue
            try:
                ref = EvidenceRef(
                    kind=EvidenceKind(str(item["kind"])),
                    source_id=str(item["source_id"]),
                    locator=str(item["locator"]),
                    summary=str(item["summary"]) if item.get("summary") is not None else None,
                )
            except (KeyError, ValueError):
                continue
            if ref not in refs:
                refs.append(ref)
    return tuple(refs)


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
    return (
        tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0] == f"module:{module.name}")
        or module.ast_refs
    )


def _port_refs(module: RTLModule) -> tuple[EvidenceRef, ...]:
    prefix = f"port:{module.name}."
    return tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].startswith(prefix)) or module.ast_refs


def _clock_refs(module: RTLModule) -> tuple[EvidenceRef, ...]:
    names = {clock.name for clock in module.clock_details} | set(module.clocks)
    prefix = f"port:{module.name}."
    return (
        tuple(ref for ref in module.ast_refs if ref.locator.split("@", 1)[0].removeprefix(prefix) in names)
        or module.ast_refs
    )


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
