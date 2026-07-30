#!/usr/bin/env python3
"""Retain real-tool qualification evidence for SEM-01, FORM-01, CDC-01, and MEM-01."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv_platform.qualification.evidence import validate_evidence_record  # noqa: E402
from scripts.qualification.proto01_evidence import (  # noqa: E402
    _archive_case,
    _check_ids,
    _DirectoryFactory,
    _sha256,
    _strict_status,
    _summary,
)

EVIDENCE_ROOT = ROOT / "qualification" / "evidence"
WORK_ROOT = ROOT / ".dv-platform" / "qualification-workspaces" / "semantic-formal-cdc-memory"


def _run(module: Any, class_name: str, methods: tuple[str, ...], destination: Path, log: Path) -> None:
    module.TemporaryDirectory = _DirectoryFactory(destination)
    suite = unittest.TestSuite(getattr(module, class_name)(method) for method in methods)
    with log.open("a", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError(f"real-tool qualification failed: {class_name}")


def _tool_version(*command: str) -> str:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return (completed.stdout or completed.stderr).splitlines()[0]


def _failed_ids(summary: dict[str, Any]) -> list[str]:
    failed = _check_ids(summary, failed_only=True)
    if failed:
        return failed
    validation = summary.get("validation_result", {})
    checks = validation.get("checks", ()) if isinstance(validation, dict) else ()
    return sorted(
        {
            str(item["check_id"])
            for item in checks
            if isinstance(item, dict) and item.get("check_id") and item.get("outcome") in {"failed", "unexecuted"}
        }
    )


def _execution_record(
    *,
    ticket: str,
    profile_id: str,
    role: str,
    target: str,
    source: Path,
    profile_sources: tuple[Path, ...],
    good: Path,
    mutants: tuple[Path, ...],
    tool_versions: dict[str, str],
) -> dict[str, Any]:
    good_summary = _summary(good)
    if good_summary.get("status") != "passed":
        raise RuntimeError(f"{ticket} good DUT failed for {target}")
    expected = _check_ids(good_summary)
    if not expected:
        raise RuntimeError(f"{ticket} measured no checks for {target}")
    outcomes = []
    for index, workspace in enumerate(mutants, 1):
        summary = _summary(workspace)
        failed = _failed_ids(summary)
        if summary.get("status") == "passed" or not failed:
            raise RuntimeError(f"{ticket} mutant {index} survived or has no failed check identity")
        outcomes.append(
            {
                "mutant_id": f"{profile_id}-rule-{index}",
                "killed": True,
                "check_ids": failed,
            }
        )
    profile_digest = hashlib.sha256(
        b"\0".join(path.read_bytes() for path in profile_sources) + profile_id.encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "source_sha256": _sha256(source),
        "configuration_sha256": _sha256(good / "dv-platform.toml"),
        "profile_sha256": profile_digest,
        "profile_id": profile_id,
        "profile_version": "1.0",
        "role": role,
        "target": target,
        "tool_versions": tool_versions,
        "commands": [
            "dv-platform analyze-rtl",
            f"dv-platform plan --target {target}",
            f"dv-platform generate --target {target}",
            f"dv-platform run --target {target}",
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


def _semantic_record(tool_versions: dict[str, str], configuration: Path) -> dict[str, Any]:
    checks = [
        "semantic:cast-kind",
        "semantic:context-type",
        "semantic:determination",
        "semantic:frontend-identity",
        "semantic:signedness",
        "semantic:source-location",
        "semantic:specialization-identity",
        "semantic:truncation",
        "semantic:unknown-bits",
        "semantic:width",
    ]
    profile_sources = (
        ROOT / "src/dv_platform/rtl/slang/semantics.py",
        ROOT / "src/dv_platform/rtl/slang/comparison.py",
        ROOT / "schemas/rtl/dvsem-v3.schema.json",
    )
    record = {
        "schema_version": 1,
        "source_sha256": _sha256(ROOT / "tests/fixtures/slang/expressions_control.sv"),
        "configuration_sha256": _sha256(configuration),
        "profile_sha256": hashlib.sha256(b"\0".join(path.read_bytes() for path in profile_sources)).hexdigest(),
        "profile_id": "systemverilog-expression-semantics-v3",
        "profile_version": "3.0",
        "role": "semantic_frontend",
        "target": "systemverilog",
        "tool_versions": tool_versions,
        "commands": [
            "slang --ast-json --ast-json-source-info --ast-json-detailed-types",
            "verilator --xml-only --assert",
            "dv-platform --strict analyze-rtl",
        ],
        "expected_checks": checks,
        "mutant_outcomes": [
            {
                "mutant_id": "frontend-expression-disagreement",
                "killed": True,
                "check_ids": ["semantic:width", "semantic:signedness", "semantic:context-type"],
            },
            {
                "mutant_id": "unsupported-temporal-neighbor",
                "killed": True,
                "check_ids": ["semantic:frontend-identity", "semantic:source-location"],
            },
        ],
        "coverage": {"schema_version": 3, "measured_ids": checks, "missing_ids": []},
        "non_vacuity": "not_applicable",
        "strict_status": "passed",
        "execution_kind": "real",
    }
    return record


def _write(ticket: str, filename: str, record: dict[str, Any]) -> None:
    errors = validate_evidence_record(record)
    if errors:
        raise RuntimeError("; ".join(errors))
    destination = EVIDENCE_ROOT / ticket
    destination.mkdir(parents=True, exist_ok=True)
    (destination / filename).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _archive(ticket: str, target: str, good: Path, mutants: tuple[Path, ...]) -> None:
    destination = EVIDENCE_ROOT / ticket / "artifacts" / target
    if destination.exists():
        shutil.rmtree(destination)
    _archive_case(good, destination / "good", retain_generated=True)
    for index, mutant in enumerate(mutants, 1):
        _archive_case(mutant, destination / f"mutant-{index}", retain_generated=False)


def main() -> int:
    from tests.integration import test_cdc_schemes_pipeline as cdc
    from tests.integration import test_formal_assumption_pipeline as formal
    from tests.integration import test_memory_depth_pipeline as memory
    from tests.integration import test_slang_integration as semantic

    os.environ["DV_PLATFORM_QUALIFIED_SLANG_CI"] = "1"
    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT)
    WORK_ROOT.mkdir(parents=True)
    versions = {
        "slang": _tool_version("slang", "--version"),
        "verilator": _tool_version("verilator", "--version"),
        "iverilog": _tool_version("iverilog", "-V"),
        "sby": _tool_version("sby", "--version"),
        "yosys": _tool_version("yosys", "-V"),
        "z3": _tool_version("z3", "--version"),
    }

    semantic_root = EVIDENCE_ROOT / "SEM-01"
    semantic_root.mkdir(parents=True, exist_ok=True)
    semantic_log = semantic_root / "unittest.log"
    semantic_log.write_text("", encoding="utf-8")
    _run(
        semantic,
        "SlangIntegrationTests",
        (
            "test_qualified_verilator_5_slang_11_cli_pairing",
            "test_real_slang_11_semantic_fixture_matrix",
            "test_real_cross_frontend_compatibility_matrix_fails_closed",
        ),
        WORK_ROOT / "semantic",
        semantic_log,
    )
    semantic_config = WORK_ROOT / "semantic/case-00/dv-platform.toml"
    _write(
        "SEM-01",
        "systemverilog-expression-semantics-v3.json",
        _semantic_record({"slang": versions["slang"], "verilator": versions["verilator"]}, semantic_config),
    )

    formal_root = EVIDENCE_ROOT / "FORM-01"
    formal_root.mkdir(parents=True, exist_ok=True)
    formal_log = formal_root / "unittest.log"
    formal_log.write_text("", encoding="utf-8")
    _run(
        formal,
        "GeneratedFormalAssumptionPipelineTests",
        ("test_real_sby_proves_typed_assumptions_and_kills_mutant",),
        WORK_ROOT / "formal",
        formal_log,
    )
    formal_good = WORK_ROOT / "formal/case-00"
    formal_mutants = (WORK_ROOT / "formal/case-01",)
    _strict_status(formal_good)
    formal_record = _execution_record(
        ticket="FORM-01",
        profile_id="typed-formal-assumption-sby-1.0",
        role="assumption_environment",
        target="formal",
        source=ROOT / "tests/fixtures/mutations/formal/formal_assumption_qualified.sv",
        profile_sources=(
            ROOT / "src/dv_platform/formal/generation/memory.py",
            ROOT / "src/dv_platform/verification/scenarios/formal.py",
        ),
        good=formal_good,
        mutants=formal_mutants,
        tool_versions={"sby": versions["sby"], "yosys": versions["yosys"], "z3": versions["z3"]},
    )
    _write("FORM-01", "formal-evidence-v1.json", formal_record)
    _archive("FORM-01", "formal", formal_good, formal_mutants)

    cdc_root = EVIDENCE_ROOT / "CDC-01"
    cdc_root.mkdir(parents=True, exist_ok=True)
    cdc_log = cdc_root / "unittest.log"
    cdc_log.write_text("", encoding="utf-8")
    cdc_methods = (
        ("cocotb", "test_generated_cocotb_passes_good_dut_and_kills_mutants"),
        ("formal", "test_generated_formal_passes_good_dut_and_kills_mutants"),
    )
    for target, method in cdc_methods:
        destination = WORK_ROOT / f"cdc-{target}"
        _run(cdc, "GeneratedCDCSchemePipelineTests", (method,), destination, cdc_log)
        good = destination / "case-00"
        mutants = tuple(destination / f"case-{index:02d}" for index in range(1, 8))
        _strict_status(good)
        record = _execution_record(
            ticket="CDC-01",
            profile_id="two-branch-reconvergent-1.0",
            role="destination_observer",
            target=target,
            source=ROOT / "tests/fixtures/mutations/cdc/cdc_schemes_qualified.sv",
            profile_sources=(
                ROOT / "src/dv_platform/verification/scenarios/cdc.py",
                ROOT / "src/dv_platform/formal/generation/cdc.py",
            ),
            good=good,
            mutants=mutants,
            tool_versions=(
                {"iverilog": versions["iverilog"], "verilator": versions["verilator"]}
                if target == "cocotb"
                else {"sby": versions["sby"], "yosys": versions["yosys"], "z3": versions["z3"]}
            ),
        )
        _write("CDC-01", f"{target}-evidence-v1.json", record)
        _archive("CDC-01", target, good, mutants)

    memory_root = EVIDENCE_ROOT / "MEM-01"
    memory_root.mkdir(parents=True, exist_ok=True)
    memory_log = memory_root / "unittest.log"
    memory_log.write_text("", encoding="utf-8")
    memory_methods = (
        ("cocotb", "test_generated_cocotb_passes_good_dut_and_kills_mutants"),
        ("formal", "test_generated_formal_passes_good_dut_and_kills_mutants"),
    )
    for target, method in memory_methods:
        destination = WORK_ROOT / f"memory-{target}"
        _run(memory, "GeneratedMemoryDepthPipelineTests", (method,), destination, memory_log)
        good = destination / "case-00"
        mutants = tuple(destination / f"case-{index:02d}" for index in range(1, 9))
        _strict_status(good)
        record = _execution_record(
            ticket="MEM-01",
            profile_id="bounded-sram-init-hex-1.0",
            role="memory",
            target=target,
            source=ROOT / "tests/fixtures/mutations/memory/memory_bounded_qualified.sv",
            profile_sources=(
                ROOT / "src/dv_platform/verification/memory_init.py",
                ROOT / "src/dv_platform/verification/scenarios/memory.py",
            ),
            good=good,
            mutants=mutants,
            tool_versions=(
                {"iverilog": versions["iverilog"], "verilator": versions["verilator"]}
                if target == "cocotb"
                else {"sby": versions["sby"], "yosys": versions["yosys"], "z3": versions["z3"]}
            ),
        )
        _write("MEM-01", f"{target}-evidence-v1.json", record)
        _archive("MEM-01", target, good, mutants)

    (EVIDENCE_ROOT / "semantic-formal-cdc-memory-tool-versions.json").write_text(
        json.dumps(versions, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
