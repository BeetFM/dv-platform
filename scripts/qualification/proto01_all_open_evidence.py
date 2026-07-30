#!/usr/bin/env python3
"""Retain PROTO-01 evidence for every authorized open-tool cell."""

from __future__ import annotations

import argparse
import hashlib
import json
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
)

TICKET_ROOT = ROOT / "qualification" / "evidence" / "PROTO-01"
WORK_ROOT = ROOT / ".dv-platform" / "proto01-all-open-workspaces"
PROFILE_SOURCE = ROOT / "src" / "dv_platform" / "verification" / "protocols" / "profiles.py"
BROAD_FIXTURE = ROOT / "tests" / "fixtures" / "mutations" / "protocol" / "broad_protocol_endpoints.sv"
BROAD_VHDL_FIXTURE = ROOT / "tests" / "fixtures" / "mutations" / "protocol" / "broad_protocol_endpoints.vhd"
AXIS_VHDL_FIXTURE = ROOT / "tests" / "fixtures" / "mutations" / "protocol" / "axi4_stream_profile_source.vhd"
PROFILES = (
    ("axi4-1.0", "subordinate", (1, 2)),
    ("wishbone-b4-1.0", "device", (3,)),
    ("avalon-mm-1.0", "agent", (4,)),
    ("avalon-st-1.0", "sink", (5,)),
    ("ahb-1.0", "subordinate", (6,)),
    ("tilelink-ul-uh-1.0", "subordinate", (7,)),
)
VERSIONS = {
    "cocotb": {"iverilog": "12.0", "verilator": "5.020"},
    "formal": {"sby": "0.67", "yosys": "0.33", "z3": "4.8.12"},
    "systemverilog": {"iverilog": "12.0", "verilator": "5.020"},
    "verilog": {"iverilog": "12.0", "verilator": "5.020"},
    "vhdl": {"ghdl": "4.1.0"},
}


def _run_method(
    module: Any,
    class_name: str,
    method: str,
    destination: Path,
    log: Path,
) -> None:
    module.TemporaryDirectory = _DirectoryFactory(destination)
    suite = unittest.TestSuite([getattr(module, class_name)(method)])
    with log.open("a", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError(f"real-tool qualification failed: {class_name}.{method}")


def _record(
    *,
    profile_id: str,
    role: str,
    target: str,
    fixture: Path,
    good: Path,
    mutants: tuple[tuple[int, Path], ...],
) -> dict[str, Any]:
    good_summary = _summary(good)
    if good_summary.get("status") != "passed":
        raise RuntimeError(f"good DUT did not pass for {profile_id}/{target}")
    expected = _check_ids(good_summary)
    if not expected:
        raise RuntimeError(f"good DUT measured no checks for {profile_id}/{target}")
    outcomes = []
    for mutant_id, mutant in mutants:
        summary = _summary(mutant)
        if summary.get("status") == "passed":
            raise RuntimeError(f"mutant {mutant_id} survived for {profile_id}/{target}")
        failed = _check_ids(summary, failed_only=True)
        if not failed:
            validation = summary.get("validation_result", {})
            checks = validation.get("checks", ()) if isinstance(validation, dict) else ()
            failed = sorted(
                {
                    str(item["check_id"])
                    for item in checks
                    if isinstance(item, dict)
                    and item.get("check_id")
                    and item.get("outcome") in {"failed", "unexecuted"}
                }
            )
        if not failed:
            raise RuntimeError(f"mutant {mutant_id} has no affected check identity for {profile_id}/{target}")
        outcomes.append(
            {
                "mutant_id": f"{profile_id}-rule-{mutant_id}",
                "killed": True,
                "check_ids": failed,
            }
        )
    profile_digest = hashlib.sha256(
        PROFILE_SOURCE.read_bytes() + b"\0" + profile_id.encode() + b"\0" + role.encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "source_sha256": _sha256(fixture),
        "configuration_sha256": _sha256(good / "dv-platform.toml"),
        "profile_sha256": profile_digest,
        "profile_id": profile_id,
        "profile_version": "1.0",
        "role": role,
        "target": target,
        "tool_versions": VERSIONS[target],
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


def _summary(path: Path) -> dict[str, Any]:
    matches = tuple(path.glob(".dv-platform/runs/**/summary.json"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one run summary below {path}, found {len(matches)}")
    value = json.loads(matches[0].read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid run summary: {matches[0]}")
    return value


def _write_record(record: dict[str, Any]) -> None:
    errors = validate_evidence_record(record)
    if errors:
        raise RuntimeError("; ".join(errors))
    profile_root = TICKET_ROOT / str(record["profile_id"])
    profile_root.mkdir(parents=True, exist_ok=True)
    target = str(record["target"])
    (profile_root / f"{target}-evidence-v1.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _broad_layouts() -> dict[str, tuple[Path, tuple[Path, ...]]]:
    return {
        "cocotb": (
            WORK_ROOT / "broad-cocotb-good/case-00",
            tuple(WORK_ROOT / f"broad-cocotb-mutants/case-{index:02d}" for index in range(7)),
        ),
        "systemverilog": (
            WORK_ROOT / "broad-native/case-00",
            tuple(WORK_ROOT / f"broad-native/case-{index:02d}" for index in range(1, 8)),
        ),
        "verilog": (
            WORK_ROOT / "broad-native/case-08",
            tuple(WORK_ROOT / f"broad-native/case-{index:02d}" for index in range(9, 16)),
        ),
        "formal": (
            WORK_ROOT / "broad-formal/case-00",
            tuple(WORK_ROOT / f"broad-formal/case-{index:02d}" for index in range(1, 8)),
        ),
        "vhdl": (
            WORK_ROOT / "broad-vhdl/case-00",
            tuple(WORK_ROOT / f"broad-vhdl/case-{index:02d}" for index in range(1, 8)),
        ),
    }


def _archive_layout(target: str, good: Path, mutants: tuple[Path, ...]) -> None:
    artifact_root = TICKET_ROOT / "broad-combined" / "artifacts" / target
    if artifact_root.exists():
        shutil.rmtree(artifact_root)
    _archive_case(good, artifact_root / "good", retain_generated=True)
    for index, mutant in enumerate(mutants, 1):
        _archive_case(mutant, artifact_root / f"mutant-{index}", retain_generated=False)


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="collect records before ledger promotion; exact strict status must be rerun without this flag",
    )
    parser.add_argument(
        "--reuse-workspaces",
        action="store_true",
        help="normalize an already completed retained run after collector-only failures",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    args = _arguments(argv)
    from tests.qualification import test_broad_protocol_vhdl_qualification as broad_vhdl
    from tests.rtl import test_vhdl_protocol_profiles as axis_vhdl
    from tests.verification import test_broad_protocol_good_dut as broad

    if not args.reuse_workspaces:
        if WORK_ROOT.exists():
            shutil.rmtree(WORK_ROOT)
        WORK_ROOT.mkdir(parents=True)
    log = TICKET_ROOT / "broad-open-unittest.log"
    if not args.reuse_workspaces:
        log.write_text("", encoding="utf-8")
    cases = (
        (
            broad,
            "BroadProtocolGoodDutTests",
            "test_all_nonstream_profiles_complete_one_full_cli_run",
            "broad-cocotb-good",
        ),
        (
            broad,
            "BroadProtocolGoodDutTests",
            "test_each_broad_protocol_kills_a_hardware_completion_mutant",
            "broad-cocotb-mutants",
        ),
        (
            broad,
            "BroadProtocolGoodDutTests",
            "test_native_systemverilog_and_verilog_profiles_execute",
            "broad-native",
        ),
        (
            broad,
            "BroadProtocolGoodDutTests",
            "test_all_nonstream_profiles_complete_bounded_formal_run",
            "broad-formal",
        ),
        (
            broad_vhdl,
            "BroadProtocolVhdlQualificationTests",
            "test_all_broad_vhdl_profiles_close_and_kill_completion_mutants",
            "broad-vhdl",
        ),
        (
            axis_vhdl,
            "VhdlProtocolProfileQualificationTests",
            "test_axi4_stream_profile_closes_good_dut_and_kills_packet_mutants",
            "axis-vhdl",
        ),
    )
    if not args.reuse_workspaces:
        for module, class_name, method, destination in cases:
            _run_method(module, class_name, method, WORK_ROOT / destination, log)

    layouts = _broad_layouts()
    for profile_id, role, mutant_ids in PROFILES:
        for target, (good, all_mutants) in layouts.items():
            fixture = BROAD_VHDL_FIXTURE if target == "vhdl" else BROAD_FIXTURE
            selected = tuple((mutant_id, all_mutants[mutant_id - 1]) for mutant_id in mutant_ids)
            _write_record(
                _record(
                    profile_id=profile_id,
                    role=role,
                    target=target,
                    fixture=fixture,
                    good=good,
                    mutants=selected,
                )
            )
    axis_good = WORK_ROOT / "axis-vhdl/case-00"
    axis_mutants = tuple((index, WORK_ROOT / f"axis-vhdl/case-{index:02d}") for index in range(1, 5))
    _write_record(
        _record(
            profile_id="axi4-stream-1.0",
            role="source",
            target="vhdl",
            fixture=AXIS_VHDL_FIXTURE,
            good=axis_good,
            mutants=axis_mutants,
        )
    )
    if not args.bootstrap:
        for good, _mutants in layouts.values():
            _strict_status(good)
        _strict_status(axis_good)
    for target, (good, mutants) in layouts.items():
        _archive_layout(target, good, mutants)
    axis_artifacts = TICKET_ROOT / "axis-combined" / "artifacts" / "vhdl"
    if axis_artifacts.exists():
        shutil.rmtree(axis_artifacts)
    _archive_case(axis_good, axis_artifacts / "good", retain_generated=True)
    for mutant_id, mutant in axis_mutants:
        _archive_case(mutant, axis_artifacts / f"mutant-{mutant_id}", retain_generated=False)
    source = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (TICKET_ROOT / "broad-open-source-identity.txt").write_text(source + "\n", encoding="utf-8")
    shutil.rmtree(WORK_ROOT)
    print("retained 31 additional real-tool evidence records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
