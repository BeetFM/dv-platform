"""Packaged capability-ledger loading and runtime reconciliation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

from dv_platform.qualification.evidence import read_evidence_record

LEDGER_STATES = {"supported", "partial", "contract_verified", "scaffold", "unsupported", "regressed"}
TARGETS = {"cocotb", "formal", "systemverilog", "verilog", "vhdl", "uvm"}
EXECUTABLE_STATES = {"supported"}
DISPLAY_TARGETS = ("cocotb", "formal", "systemverilog", "verilog", "vhdl", "uvm")
LANGUAGE_TARGETS = ("systemverilog", "verilog", "vhdl")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_ID = re.compile(r"^[0-9a-f]{40,64}$")


def load_capability_ledger(repo_root: Path | None = None) -> tuple[dict[str, Any], str]:
    """Load the source ledger when present, otherwise the wheel-packaged copy."""

    source_path = repo_root / "qualification" / "policies" / "capability-ledger-v1.json" if repo_root else None
    if source_path is not None and source_path.is_file() and not source_path.is_symlink():
        path = source_path
        origin = str(path)
        raw = path.read_text(encoding="utf-8")
    else:
        resource = files("dv_platform").joinpath("policies/capability-ledger-v1.json")
        if resource.is_file():
            origin = str(resource)
            raw = resource.read_text(encoding="utf-8")
        else:
            development = (
                Path(__file__).resolve().parents[3] / "qualification" / "policies" / "capability-ledger-v1.json"
            )
            origin = str(development)
            raw = development.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("capability ledger root must be an object")
    return value, origin


def validate_capability_ledger(  # noqa: C901
    value: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
    runtime_cells: tuple[Mapping[str, Any], ...] = (),
) -> tuple[str, ...]:  # noqa: C901
    """Validate closed cells, evidence freshness, and runtime eligibility."""

    errors: list[str] = []
    if set(value) != {"schema_version", "authority", "cells"}:
        errors.append("capability ledger root is not closed-schema")
    if value.get("schema_version") != 1 or value.get("authority") != "current":
        errors.append("capability ledger authority/schema is unsupported")
    entries = value.get("cells")
    if not isinstance(entries, list) or not entries:
        return (*errors, "capability ledger cells must be a non-empty array")
    keys = {
        "profile_id",
        "profile_version",
        "role",
        "target",
        "bound",
        "state",
        "required_tool",
        "evidence_digest",
        "last_passing_source",
        "source",
    }
    optional_keys = {"evidence_path"}
    indexed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for index, cell in enumerate(entries):
        if not isinstance(cell, dict) or not keys <= set(cell) or set(cell) - keys - optional_keys:
            errors.append(f"cell[{index}] is not closed-schema")
            continue
        identity = (str(cell["profile_id"]), str(cell["role"]), str(cell["target"]))
        if identity in indexed:
            errors.append(f"duplicate capability cell: {identity!r}")
        indexed[identity] = cell
        if "|" in identity[1] or "/" in identity[1] or "|" in identity[2] or identity[2] not in TARGETS:
            errors.append(f"grouped or unknown capability cell: {identity!r}")
        if cell["state"] not in LEDGER_STATES:
            errors.append(f"invalid capability state: {identity!r}")
        bound = cell["bound"]
        if not isinstance(bound, dict) or set(bound) != {
            "maximum_burst_length",
            "maximum_outstanding",
            "timeout_cycles",
        }:
            errors.append(f"invalid capability bound: {identity!r}")
        if cell["state"] in EXECUTABLE_STATES:
            _validate_supported_evidence(cell, identity, repo_root, errors)
        elif any(cell.get(field) is not None for field in ("evidence_digest", "evidence_path", "last_passing_source")):
            errors.append(f"non-supported cell cites passing evidence: {identity!r}")
    _validate_language_target_parity(indexed, errors)
    for runtime in runtime_cells:
        identity = (str(runtime.get("profile_id")), str(runtime.get("role")), str(runtime.get("target")))
        cell = indexed.get(identity)
        if cell is None:
            errors.append(f"runtime capability cell is undeclared: {identity!r}")
            continue
        runtime_bound = runtime.get("bound")
        if cell["bound"] != runtime_bound or cell["profile_version"] != runtime.get("profile_version"):
            errors.append(f"runtime capability bound/version disagrees with ledger: {identity!r}")
        if bool(runtime.get("executable")) and cell["state"] != "supported":
            errors.append(f"runtime eligibility exceeds ledger state: {identity!r}")
    return tuple(errors)


def _validate_language_target_parity(
    indexed: Mapping[tuple[str, str, str], Mapping[str, Any]],
    errors: list[str],
) -> None:
    """Keep the three generated HDL targets at the same declared capability."""

    groups = {(profile_id, role) for profile_id, role, _target in indexed}
    for profile_id, role in sorted(groups):
        cells = [indexed.get((profile_id, role, target)) for target in LANGUAGE_TARGETS]
        if any(cell is None for cell in cells):
            errors.append(f"language target parity is incomplete: {(profile_id, role)!r}")
            continue
        signatures = {
            (
                str(cell["profile_version"]),
                json.dumps(cell["bound"], separators=(",", ":"), sort_keys=True),
                str(cell["state"]),
            )
            for cell in cells
            if cell is not None
        }
        if len(signatures) != 1:
            errors.append(f"SystemVerilog/Verilog/VHDL capability parity disagrees: {(profile_id, role)!r}")


def _validate_supported_evidence(  # noqa: C901
    cell: Mapping[str, Any],
    identity: tuple[str, str, str],
    repo_root: Path | None,
    errors: list[str],
) -> None:
    digest = cell.get("evidence_digest")
    source_identity = cell.get("last_passing_source")
    evidence_path = cell.get("evidence_path")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        errors.append(f"supported cell lacks evidence digest: {identity!r}")
    if not isinstance(source_identity, str) or SOURCE_ID.fullmatch(source_identity) is None:
        errors.append(f"supported cell lacks last-passing source: {identity!r}")
    if not isinstance(evidence_path, str):
        errors.append(f"supported cell lacks resolvable evidence path: {identity!r}")
        return
    if repo_root is None:
        return
    path = (repo_root / evidence_path).resolve(strict=False)
    packaged_prefix = "qualification/evidence/"
    if not path.is_file() and repo_root.name == "dv_platform" and evidence_path.startswith(packaged_prefix):
        path = (repo_root / "evidence" / evidence_path.removeprefix(packaged_prefix)).resolve(strict=False)
    if repo_root.resolve(strict=False) not in (path, *path.parents):
        errors.append(f"supported cell evidence escapes repository: {identity!r}")
        return
    evidence, evidence_errors, actual_digest = read_evidence_record(path)
    if evidence_errors:
        errors.append(f"supported cell evidence is invalid: {identity!r}: {'; '.join(evidence_errors)}")
    if actual_digest != digest:
        errors.append(f"supported cell evidence digest is stale: {identity!r}")
    if evidence.get("execution_kind") == "mocked":
        errors.append(f"mocked evidence cannot support a capability: {identity!r}")
    for field, expected in (
        ("profile_id", identity[0]),
        ("role", identity[1]),
        ("target", identity[2]),
        ("profile_version", cell.get("profile_version")),
    ):
        if evidence.get(field) != expected:
            errors.append(f"supported cell evidence {field} mismatch: {identity!r}")
    if evidence.get("strict_status") != "passed":
        errors.append(f"supported cell evidence did not pass strict status: {identity!r}")
    if evidence.get("non_vacuity") == "failed":
        errors.append(f"supported cell evidence failed non-vacuity: {identity!r}")
    mutants = evidence.get("mutant_outcomes")
    if not isinstance(mutants, list) or any(
        not isinstance(item, dict) or item.get("killed") is not True for item in mutants
    ):
        errors.append(f"supported cell evidence has surviving mutants: {identity!r}")
    coverage = evidence.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("missing_ids"):
        errors.append(f"supported cell evidence has missing coverage: {identity!r}")
    expected_checks = evidence.get("expected_checks")
    measured_ids = coverage.get("measured_ids", ()) if isinstance(coverage, dict) else ()
    if not isinstance(expected_checks, list) or not set(expected_checks) <= set(measured_ids):
        errors.append(f"supported cell evidence does not measure every expected check: {identity!r}")
    required_tool = cell.get("required_tool")
    if isinstance(required_tool, dict):
        tool_versions = evidence.get("tool_versions")
        if not isinstance(tool_versions, dict) or tool_versions.get(required_tool.get("name")) != required_tool.get(
            "version"
        ):
            errors.append(f"supported cell evidence tool/version mismatch: {identity!r}")


def capability_ledger_status(
    repo_root: Path,
    runtime_cells: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Return status-safe ledger details without raising on corrupt input."""

    try:
        value, origin = load_capability_ledger(repo_root)
        errors = validate_capability_ledger(
            value,
            repo_root=_ledger_evidence_root(origin, repo_root),
            runtime_cells=runtime_cells,
        )
        cells = value.get("cells", ())
        counts = {
            state: sum(1 for cell in cells if isinstance(cell, dict) and cell.get("state") == state)
            for state in sorted(LEDGER_STATES)
        }
        return {
            "status": "valid" if not errors else "invalid",
            "origin": origin,
            "errors": list(errors),
            "counts": counts,
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": "invalid", "origin": None, "errors": [str(error)], "counts": {}}


def _ledger_evidence_root(origin: str, requested_root: Path) -> Path:
    """Resolve evidence beside the ledger authority, not an unrelated project."""

    path = Path(origin)
    if path.parent.name == "policies" and path.parent.parent.name == "qualification":
        return path.parents[2]
    if path.parent.name == "policies" and path.parent.parent.name == "dv_platform":
        return path.parent.parent
    return requested_root


def render_capability_table(value: Mapping[str, Any]) -> str:
    """Render the conservative profile/role/target table from the ledger authority."""

    errors = validate_capability_ledger(value)
    if errors:
        raise ValueError("cannot render invalid capability ledger: " + "; ".join(errors))
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for cell in value["cells"]:
        identity = (str(cell["profile_id"]), str(cell["profile_version"]), str(cell["role"]))
        rows.setdefault(identity, {})[str(cell["target"])] = str(cell["state"])
    header = "| Profile | Version | Role | " + " | ".join(DISPLAY_TARGETS) + " |"
    divider = "| --- | --- | --- | " + " | ".join("---" for _ in DISPLAY_TARGETS) + " |"
    body = [
        "| "
        + " | ".join(
            (
                profile,
                version,
                role,
                *(targets.get(target, "undeclared") for target in DISPLAY_TARGETS),
            )
        )
        + " |"
        for (profile, version, role), targets in sorted(rows.items())
    ]
    return "\n".join((header, divider, *body)) + "\n"
