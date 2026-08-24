"""Pinned Arty A7 cells; no family-wide promotion from one subrevision."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

VIVADO_VERSION = "2025.2"
REQUIRED_BUILD_CHECKS = frozenset(
    {"synthesis", "implementation", "bitstream", "drc", "cdc", "timing", "utilization", "constraints", "provenance"}
)
REQUIRED_LAB_CHECKS = frozenset(
    {
        "ddr_bist",
        "qspi_preserve_restore",
        "ethernet_peer",
        "uart",
        "gpio",
        "pmod_arduino_loopback",
        "interrupts_watchdog",
        "reset_clock_recovery",
        "xadc_calibrated",
        "guided_io",
    }
)


@dataclass(frozen=True)
class ArtyA7Profile:
    profile_id: str
    device: str
    revisions: tuple[str, ...]
    constraints_revision: str
    constraints_sha256: str
    state: str = "partial"


DIGILENT_XDC_REVISION = "00a3404901f35aa9567b01ecb3f2c233b6efe9f4"
ARTY_A7_PROFILES = {
    "arty-a7-35t-rev-c": ArtyA7Profile(
        "arty-a7-35t-rev-c",
        "XC7A35TICSG324-1L",
        ("C",),
        "digilent:exact-rev-c-constraints-unavailable",
        "0" * 64,
    ),
    "arty-a7-35t-rev-e": ArtyA7Profile(
        "arty-a7-35t-rev-e",
        "XC7A35TICSG324-1L",
        ("E", "E.2"),
        f"digilent-xdc:{DIGILENT_XDC_REVISION}:Arty-A7-35-Master.xdc",
        "3884f49d657924e2903e7cc275ee6d4acc6e5b17a55b818ed742fc59a0818492",
    ),
    "arty-a7-100t-rev-e": ArtyA7Profile(
        "arty-a7-100t-rev-e",
        "XC7A100TCSG324-1",
        ("E", "E.2"),
        f"digilent-xdc:{DIGILENT_XDC_REVISION}:Arty-A7-100-Master.xdc",
        "5c0c84302cbce49ac85f4812e8f1f7371e686964ec2eb29fd67307da9ed6835f",
    ),
}


class BoardEvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class ConstraintFact:
    port: str
    package_pin: str
    io_standard: str
    clock_period_ns: float | None = None


@dataclass(frozen=True)
class LabRunRequest:
    request_id: str
    profile_id: str
    board_revision: str
    bom_variant: str
    usb_jtag_serial: str
    fixture_id: str
    bitstream_sha256: str
    source_revision: str
    expires_at: str

    @property
    def digest(self) -> str:
        return sha256(json.dumps(self.__dict__, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class VivadoProjectSpec:
    profile_id: str
    top: str
    rtl_files: tuple[str, ...]
    constraints_file: str
    output_directory: str = "vivado-output"


_PROPERTY = re.compile(
    r"set_property\s+-dict\s+\{\s*PACKAGE_PIN\s+(?P<pin>\S+)\s+"
    r"IOSTANDARD\s+(?P<standard>\S+)\s*\}\s+\[get_ports\s+\{\s*(?P<port>[^}]+?)\s*\}\]"
)
_CLOCK = re.compile(r"create_clock\b.*?-period\s+(?P<period>[0-9.]+).*?\[get_ports\s+\{\s*(?P<port>[^}]+?)\s*\}\]")


def parse_xdc(text: str) -> tuple[ConstraintFact, ...]:
    """Parse the closed pin/clock subset without executing Tcl."""

    pins: dict[str, tuple[str, str]] = {}
    clocks: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip().removeprefix("#").strip()
        if not line or line.startswith("##"):
            continue
        property_match = _PROPERTY.search(line)
        if property_match:
            port = property_match.group("port").strip()
            if port in pins:
                raise BoardEvidenceError(f"duplicate XDC port constraint: {port}")
            pins[port] = (property_match.group("pin"), property_match.group("standard"))
            continue
        clock_match = _CLOCK.search(line)
        if clock_match:
            clocks[clock_match.group("port").strip()] = float(clock_match.group("period"))
    if not pins:
        raise BoardEvidenceError("XDC contains no parseable pin constraints")
    return tuple(
        ConstraintFact(port, pin, standard, clocks.get(port)) for port, (pin, standard) in sorted(pins.items())
    )


def reconcile_constraints(profile: ArtyA7Profile, xdc: bytes, facts: tuple[ConstraintFact, ...]) -> None:
    if profile.constraints_sha256 == "0" * 64:
        raise BoardEvidenceError("exact legal constraints are unavailable for this board revision")
    if sha256(xdc).hexdigest() != profile.constraints_sha256:
        raise BoardEvidenceError("Digilent XDC digest does not match the pinned profile")
    ports = {fact.port for fact in facts}
    required_prefixes = ("CLK100MHZ", "sw[0]", "btn[0]", "led[0]", "ja[0]", "uart_rxd_out")
    if any(required not in ports for required in required_prefixes):
        raise BoardEvidenceError("XDC is missing a required clock or board interface")


def generate_vivado_tcl(spec: VivadoProjectSpec) -> str:
    """Return deterministic, closed Vivado 2025.2 batch Tcl."""

    if spec.profile_id not in ARTY_A7_PROFILES:
        raise BoardEvidenceError("unknown Arty A7 profile")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", spec.top):
        raise BoardEvidenceError("Vivado top name is unsafe")
    if not spec.rtl_files:
        raise BoardEvidenceError("Vivado project requires RTL inputs")
    paths = (*spec.rtl_files, spec.constraints_file, spec.output_directory)
    if any(
        not path
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        or any(character in path for character in ("{", "}", "[", "]", "$", ";", "\n", "\r", "\0"))
        for path in paths
    ):
        raise BoardEvidenceError("Vivado project path is unsafe")
    profile = ARTY_A7_PROFILES[spec.profile_id]
    rtl_commands = "\n".join(f"read_verilog {{{path}}}" for path in sorted(spec.rtl_files))
    output = spec.output_directory
    return (
        f"# generated for Vivado {VIVADO_VERSION}; do not edit\n"
        f"set_part {{{profile.device}}}\n"
        f"file mkdir {{{output}}}\n"
        f"{rtl_commands}\n"
        f"read_xdc {{{spec.constraints_file}}}\n"
        f"synth_design -top {{{spec.top}}} -part {{{profile.device}}}\n"
        f"report_cdc -details -file {{{output}/post_synth_cdc.rpt}}\n"
        f"opt_design\nplace_design\nphys_opt_design\nroute_design\n"
        f"report_drc -file {{{output}/post_route_drc.rpt}}\n"
        f"report_timing_summary -delay_type min_max -report_unconstrained "
        f"-file {{{output}/timing_summary.rpt}}\n"
        f"report_utilization -file {{{output}/utilization.rpt}}\n"
        f"report_methodology -file {{{output}/methodology.rpt}}\n"
        f"write_checkpoint -force {{{output}/implemented.dcp}}\n"
        f"write_bitstream -force {{{output}/{spec.top}.bit}}\n"
        "exit\n"
    )


def validate_board_evidence(
    evidence: dict[str, Any],
    profile: ArtyA7Profile,
    *,
    expected_source_revision: str,
    expected_bitstream_sha256: str,
    max_age: timedelta,
    verify_signature: Callable[[dict[str, Any]], bool],
    now: datetime | None = None,
) -> None:
    required = {
        "schema_version",
        "profile_id",
        "board_revision",
        "bom_variant",
        "device",
        "usb_jtag_serial",
        "fixture_id",
        "vivado_version",
        "constraints_revision",
        "constraints_sha256",
        "source_revision",
        "bitstream_sha256",
        "completed_at",
        "build_checks",
        "lab_checks",
        "mutants",
        "flash_restored",
        "signature",
    }
    if set(evidence) != required or evidence.get("schema_version") != 1:
        raise BoardEvidenceError("board evidence has unknown, missing, or unsupported fields")
    if (
        evidence["profile_id"] != profile.profile_id
        or evidence["device"] != profile.device
        or evidence["board_revision"] not in profile.revisions
        or not evidence["bom_variant"]
    ):
        raise BoardEvidenceError("wrong board, exact subrevision, BOM, or device identity")
    identity = {
        "vivado_version": VIVADO_VERSION,
        "constraints_revision": profile.constraints_revision,
        "constraints_sha256": profile.constraints_sha256,
        "source_revision": expected_source_revision,
        "bitstream_sha256": expected_bitstream_sha256,
    }
    if any(evidence[key] != value for key, value in identity.items()):
        raise BoardEvidenceError("tool, constraints, source, or bitstream identity mismatch")
    if not evidence["usb_jtag_serial"] or not evidence["fixture_id"] or not evidence["flash_restored"]:
        raise BoardEvidenceError("board serial, fixture identity, and flash restoration are mandatory")
    if set(evidence["build_checks"]) != REQUIRED_BUILD_CHECKS or set(evidence["lab_checks"]) != REQUIRED_LAB_CHECKS:
        raise BoardEvidenceError("partial build or hardware-lab run")
    if not all(evidence["build_checks"].values()) or not all(evidence["lab_checks"].values()):
        raise BoardEvidenceError("board qualification contains a failing check")
    if not evidence["mutants"] or not all(item.get("killed") is True for item in evidence["mutants"]):
        raise BoardEvidenceError("intended board mutants were not all killed")
    completed = datetime.fromisoformat(evidence["completed_at"].replace("Z", "+00:00"))
    if (now or datetime.now(UTC)) - completed > max_age:
        raise BoardEvidenceError("board evidence is stale")
    if not verify_signature(evidence):
        raise BoardEvidenceError("board evidence signature is missing or untrusted")


def constraint_digest(data: bytes) -> str:
    return sha256(data).hexdigest()
