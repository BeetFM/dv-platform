#!/usr/bin/env python3
"""Run reproducible, board-independent Arty A7 implementation cells."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from dv_platform.boards.arty_a7 import (
    ARTY_A7_PROFILES,
    DIGILENT_XDC_REVISION,
    VIVADO_VERSION,
    parse_xdc,
    reconcile_constraints,
)

_XDC_NAMES = {
    "arty-a7-35t-rev-e": "Arty-A7-35-Master.xdc",
    "arty-a7-100t-rev-e": "Arty-A7-100-Master.xdc",
}
_PORTS = frozenset(
    {
        "CLK100MHZ",
        "sw[0]",
        "sw[1]",
        "sw[2]",
        "sw[3]",
        "btn[0]",
        "btn[1]",
        "btn[2]",
        "btn[3]",
        "led[0]",
        "led[1]",
        "led[2]",
        "led[3]",
        "ja[0]",
        "ja[1]",
        "ja[2]",
        "ja[3]",
        "ja[4]",
        "ja[5]",
        "ja[6]",
        "ja[7]",
        "uart_rxd_out",
        "uart_txd_in",
    }
)
_GET_PORT = re.compile(r"\[get_ports\s+\{\s*([^}]+?)\s*\}\]")


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=sorted(_XDC_NAMES), action="append")
    parser.add_argument("--vivado-bin", type=Path, required=True)
    parser.add_argument("--cmd-exe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    return parser.parse_args(argv)


def _download_constraints(profile_id: str) -> bytes:
    name = _XDC_NAMES[profile_id]
    url = f"https://raw.githubusercontent.com/Digilent/digilent-xdc/{DIGILENT_XDC_REVISION}/{name}"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - immutable HTTPS source
        return response.read()


def _active_constraints(source: bytes) -> str:
    selected: list[str] = []
    for raw in source.decode("utf-8").splitlines():
        match = _GET_PORT.search(raw)
        if match and match.group(1).strip() in _PORTS:
            selected.append(raw.removeprefix("#"))
    found = {match.group(1).strip() for line in selected if (match := _GET_PORT.search(line)) is not None}
    if found != _PORTS:
        raise ValueError(f"pinned XDC is missing fixture ports: {sorted(_PORTS - found)}")
    return "\n".join(selected) + "\n"


def _tcl(profile_id: str) -> str:
    profile = ARTY_A7_PROFILES[profile_id]
    return f"""set_part {{{profile.device}}}
read_verilog -sv {{board_top.sv}}
read_xdc {{active.xdc}}
synth_design -top {{board_top}} -part {{{profile.device}}}
report_cdc -details -file {{reports/post_synth_cdc.rpt}}
opt_design
place_design
phys_opt_design
route_design
report_drc -file {{reports/post_route_drc.rpt}}
report_timing_summary -delay_type min_max -report_unconstrained -file {{reports/timing_summary.rpt}}
report_utilization -file {{reports/utilization.rpt}}
report_methodology -file {{reports/methodology.rpt}}
write_checkpoint -force {{reports/implemented.dcp}}
write_bitstream -force {{reports/board_top.bit}}
set bitstream [file normalize {{reports/board_top.bit}}]
if {{![file exists $bitstream]}} {{ error "bitstream was not generated" }}
set timing_paths [get_timing_paths -quiet -delay_type max -max_paths 1]
if {{[llength $timing_paths] == 0}} {{ error "no timing path was analyzed" }}
set worst_slack [get_property SLACK [lindex $timing_paths 0]]
if {{$worst_slack < 0}} {{ error "negative setup slack: $worst_slack" }}
set drc_errors [get_drc_violations -quiet -filter {{IS_ENABLED == 1 && SEVERITY == Error}}]
if {{[llength $drc_errors] != 0}} {{ error "enabled DRC errors remain" }}
exit 0
"""


def _windows_path(path: Path) -> str:
    completed = subprocess.run(
        ("wslpath", "-w", str(path.resolve())),
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _run_vivado(
    workspace: Path,
    vivado_bin: Path,
    cmd_exe: Path | None,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    if cmd_exe is None:
        command = (
            str(vivado_bin / "vivado"),
            "-mode",
            "batch",
            "-nojournal",
            "-nolog",
            "-source",
            "run.tcl",
        )
        return subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    batch = _windows_path(vivado_bin / "vivado.bat")
    invocation = subprocess.list2cmdline((batch, "-mode", "batch", "-nojournal", "-nolog", "-source", "run.tcl"))
    windows_workspace = subprocess.list2cmdline((_windows_path(workspace),))
    command = f"cd /d {windows_workspace} && call {invocation}"
    return subprocess.run(
        (str(cmd_exe), "/d", "/c", command),
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _run_cell(
    profile_id: str,
    vivado_bin: Path,
    cmd_exe: Path | None,
    destination: Path,
    timeout_seconds: int,
) -> dict[str, object]:
    profile = ARTY_A7_PROFILES[profile_id]
    source = _download_constraints(profile_id)
    reconcile_constraints(profile, source, parse_xdc(source.decode("utf-8")))
    destination.mkdir(parents=True, exist_ok=False)
    reports = destination / "reports"
    reports.mkdir()
    (destination / "master.xdc").write_bytes(source)
    (destination / "active.xdc").write_text(_active_constraints(source), encoding="utf-8")
    fixture = Path(__file__).resolve().parents[2] / "qualification/fixtures/arty_a7/board_top.sv"
    shutil.copyfile(fixture, destination / "board_top.sv")
    (destination / "run.tcl").write_text(_tcl(profile_id), encoding="utf-8")
    completed = _run_vivado(destination, vivado_bin, cmd_exe, timeout_seconds)
    (destination / "vivado.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (destination / "vivado.stderr.log").write_text(completed.stderr, encoding="utf-8")
    expected = (
        "post_synth_cdc.rpt",
        "post_route_drc.rpt",
        "timing_summary.rpt",
        "utilization.rpt",
        "methodology.rpt",
        "implemented.dcp",
        "board_top.bit",
    )
    missing = [name for name in expected if not (reports / name).is_file()]
    if completed.returncode or missing:
        raise RuntimeError(
            f"{profile_id} failed (exit {completed.returncode}; missing={missing}); "
            f"see {destination / 'vivado.stdout.log'}"
        )
    return {
        "schema_version": 1,
        "evidence_kind": "board_independent_vivado_implementation",
        "profile_id": profile_id,
        "board_revision_scope": list(profile.revisions),
        "device": profile.device,
        "vivado_version": VIVADO_VERSION,
        "constraints_revision": profile.constraints_revision,
        "constraints_sha256": profile.constraints_sha256,
        "fixture_sha256": _digest(destination / "board_top.sv"),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "checks": {
            "synthesis": True,
            "implementation": True,
            "bitstream": True,
            "drc": True,
            "cdc_report": True,
            "timing": True,
            "utilization": True,
            "constraints": True,
            "provenance": True,
        },
        "artifacts": {name: _digest(reports / name) for name in expected},
        "physical_board_tests": "not_run",
    }


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if not 1 <= args.timeout_seconds <= 14_400:
        raise SystemExit("--timeout-seconds must be between 1 and 14400")
    profiles = args.profile or sorted(_XDC_NAMES)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "cells": [],
    }
    try:
        for profile_id in profiles:
            manifest["cells"].append(
                _run_cell(
                    profile_id,
                    args.vivado_bin,
                    args.cmd_exe,
                    output / profile_id,
                    args.timeout_seconds,
                )
            )
    except Exception as error:  # qualification boundary records concise failure
        print(str(error), file=sys.stderr)
        return 1
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
