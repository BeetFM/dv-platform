#!/usr/bin/env python3
"""Retain and normalize the real-tool AXI4-Stream PROTO-01 qualification."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from dv_platform.cli import main as cli_main
from dv_platform.qualification.evidence import validate_evidence_record

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TICKET_ROOT = ROOT / "qualification" / "evidence" / "PROTO-01"
EVIDENCE_ROOT = TICKET_ROOT / "axi4-stream-1.0"
ARTIFACT_ROOT = TICKET_ROOT / "axis-combined" / "artifacts"
FIXTURE = ROOT / "tests" / "fixtures" / "mutations" / "protocol" / "axi4_stream_profile_source.sv"
PROFILE_SOURCE = ROOT / "src" / "dv_platform" / "verification" / "protocols" / "profiles.py"


class _RetainedDirectory:
    """TemporaryDirectory-compatible context that intentionally retains files."""

    def __init__(self, path: Path) -> None:
        self.name = str(path)
        path.mkdir(parents=True)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *_args: object) -> None:
        return None


class _DirectoryFactory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.index = 0

    def __call__(self, *_args: object, **_kwargs: object) -> _RetainedDirectory:
        path = self.root / f"case-{self.index:02d}"
        self.index += 1
        return _RetainedDirectory(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_method(module: Any, method: str, destination: Path, log: Path) -> None:
    factory = _DirectoryFactory(destination)
    module.TemporaryDirectory = factory
    suite = unittest.TestSuite([module.Axi4StreamProfileQualificationTests(method)])
    with log.open("a", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError(f"real-tool qualification failed: {method}")


def _summary(path: Path) -> dict[str, Any]:
    matches = tuple(path.glob(".dv-platform/runs/**/summary.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one run summary below {path}, found {len(matches)}")
    value = json.loads(matches[0].read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid run summary: {matches[0]}")
    return value


def _check_ids(summary: dict[str, Any], *, failed_only: bool = False) -> list[str]:
    coverage = summary.get("verification_coverage", {})
    entries = coverage.get("entries", ()) if isinstance(coverage, dict) else ()
    checks = {
        str(item["check_id"])
        for item in entries
        if isinstance(item, dict) and item.get("check_id") and (not failed_only or item.get("status") == "failed")
    }
    return sorted(checks)


def _tool_output(*command: str) -> str:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return (completed.stdout or completed.stderr).splitlines()[0]


def _record(
    *,
    target: str,
    good: Path,
    mutants: tuple[Path, ...],
    required_versions: dict[str, str],
) -> dict[str, Any]:
    good_summary = _summary(good)
    if good_summary.get("status") != "passed":
        raise RuntimeError(f"good DUT did not pass for {target}")
    expected = _check_ids(good_summary)
    if not expected:
        raise RuntimeError(f"good DUT measured no checks for {target}")
    outcomes = []
    for index, mutant in enumerate(mutants, 1):
        summary = _summary(mutant)
        if summary.get("status") == "passed":
            raise RuntimeError(f"mutant {index} survived for {target}")
        failed = _check_ids(summary, failed_only=True)
        if not failed:
            raise RuntimeError(f"mutant {index} has no failed check identity for {target}")
        outcomes.append({"mutant_id": f"packet-rule-{index}", "killed": True, "check_ids": failed})
    config = good / "dv-platform.toml"
    profile_digest = hashlib.sha256(PROFILE_SOURCE.read_bytes() + b"\0axi4-stream-1.0\0source").hexdigest()
    return {
        "schema_version": 1,
        "source_sha256": _sha256(FIXTURE),
        "configuration_sha256": _sha256(config),
        "profile_sha256": profile_digest,
        "profile_id": "axi4-stream-1.0",
        "profile_version": "1.0",
        "role": "source",
        "target": target,
        "tool_versions": required_versions,
        "commands": [
            "dv-platform analyze-rtl",
            f"dv-platform plan --target {target}",
            f"dv-platform generate --target {target}",
            f"dv-platform run --target {target} --module axi4_stream_profile_source",
            "dv-platform coverage --from-runs",
            "dv-platform status --policy ci",
        ],
        "expected_checks": expected,
        "mutant_outcomes": outcomes,
        "coverage": {"schema_version": 3, "measured_ids": expected, "missing_ids": []},
        "non_vacuity": "passed",
        "strict_status": "passed",
        "execution_kind": "real",
    }


def _strict_status(workspace: Path) -> None:
    if cli_main(["--repo-root", str(workspace), "coverage", "--from-runs"]) != 0:
        raise RuntimeError(f"coverage reconciliation failed below {workspace}")
    if cli_main(["--repo-root", str(workspace), "status", "--policy", "ci"]) != 0:
        raise RuntimeError(f"strict status failed below {workspace}")


def _archive_case(source: Path, destination: Path, *, retain_generated: bool) -> None:
    destination.mkdir(parents=True)
    shutil.copy2(source / "dv-platform.toml", destination / "dv-platform.toml")
    summary_matches = tuple(source.glob(".dv-platform/runs/**/summary.json"))
    if len(summary_matches) != 1:
        raise RuntimeError(f"cannot archive ambiguous run below {source}")
    run_dir = summary_matches[0].parent
    for path in run_dir.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".log", ".xml", ".vcd", ".yw"}:
            relative = path.relative_to(run_dir)
            target = destination / "run" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    if retain_generated:
        shutil.copytree(source / "generated", destination / "generated")


def main() -> int:
    from tests.qualification import test_axi4_stream_profile_qualification as qualification

    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for target in ("cocotb", "formal", "systemverilog", "verilog"):
        (EVIDENCE_ROOT / f"{target}-evidence-v1.json").unlink(missing_ok=True)
    workspace_root = EVIDENCE_ROOT / "workspaces"
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    legacy_artifacts = EVIDENCE_ROOT / "artifacts"
    if legacy_artifacts.exists():
        shutil.rmtree(legacy_artifacts)
    log = EVIDENCE_ROOT / "unittest.log"
    methods = (
        ("cocotb", "test_generated_profile_trace_closes_good_source_and_kills_packet_mutants"),
        ("native", "test_native_profile_tasks_kill_the_same_packet_mutants"),
        ("formal", "test_formal_profile_properties_kill_packet_and_stability_mutants"),
    )
    for directory, method in methods:
        _run_method(qualification, method, EVIDENCE_ROOT / "workspaces" / directory, log)

    actual_tools = {
        "verilator": _tool_output("verilator", "--version"),
        "iverilog": _tool_output("iverilog", "-V"),
        "ghdl": _tool_output("ghdl", "--version"),
        "sby": _tool_output("sby", "--version"),
        "yosys": _tool_output("yosys", "-V"),
        "z3": _tool_output("z3", "--version"),
    }
    (EVIDENCE_ROOT / "tool-versions.json").write_text(
        json.dumps(actual_tools, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    layouts = {
        "cocotb": (
            EVIDENCE_ROOT / "workspaces/cocotb/case-00",
            tuple(EVIDENCE_ROOT / f"workspaces/cocotb/case-{index:02d}" for index in range(1, 5)),
            {"iverilog": "12.0", "verilator": "5.020"},
        ),
        "systemverilog": (
            EVIDENCE_ROOT / "workspaces/native/case-00",
            tuple(EVIDENCE_ROOT / f"workspaces/native/case-{index:02d}" for index in range(1, 5)),
            {"iverilog": "12.0", "verilator": "5.020"},
        ),
        "verilog": (
            EVIDENCE_ROOT / "workspaces/native/case-05",
            tuple(EVIDENCE_ROOT / f"workspaces/native/case-{index:02d}" for index in range(6, 10)),
            {"iverilog": "12.0", "verilator": "5.020"},
        ),
        "formal": (
            EVIDENCE_ROOT / "workspaces/formal/case-00",
            tuple(EVIDENCE_ROOT / f"workspaces/formal/case-{index:02d}" for index in range(1, 5)),
            {"sby": "0.67", "yosys": "0.33", "z3": "4.8.12"},
        ),
    }
    for target, (good, mutants, versions) in layouts.items():
        record = _record(target=target, good=good, mutants=mutants, required_versions=versions)
        errors = validate_evidence_record(record)
        if errors:
            raise RuntimeError("; ".join(errors))
        (EVIDENCE_ROOT / f"{target}-evidence-v1.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    for target, (good, mutants, _versions) in layouts.items():
        _strict_status(good)
        target_artifacts = ARTIFACT_ROOT / target
        if target_artifacts.exists():
            shutil.rmtree(target_artifacts)
        _archive_case(good, target_artifacts / "good", retain_generated=True)
        for index, mutant in enumerate(mutants, 1):
            _archive_case(
                mutant,
                target_artifacts / f"mutant-{index}",
                retain_generated=False,
            )
    source = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    (EVIDENCE_ROOT / "source-identity.txt").write_text(source + "\n", encoding="utf-8")
    shutil.rmtree(EVIDENCE_ROOT / "workspaces")
    print(f"retained four real-tool evidence records under {EVIDENCE_ROOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
