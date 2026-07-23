# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Auditable enterprise qualification without requiring proprietary licenses."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any

from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    RTLClock,
    RTLPort,
    RTLProtocol,
    RTLReset,
    VerificationClaim,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.enterprise.profiles import EnterpriseToolProfile
from dv_platform.generators.uvm import UvmGenerator

QUALIFICATION_SCHEMA_VERSION = 1
QUALIFICATION_POLICY_SCHEMA_VERSION = 1
QUALIFICATION_ATTESTATION_SCHEMA_VERSION = 1
QUALIFICATION_REQUEST_SCHEMA_VERSION = 1
MAX_QUALIFICATION_BYTES = 32 * 1024 * 1024
MAX_PROBE_OUTPUT_BYTES = 1024 * 1024
MAX_PROBE_TIMEOUT_SECONDS = 1800.0
QUALIFICATION_LEVELS = (
    "unverified",
    "contract_verified",
    "surrogate_verified",
    "vendor_verified",
    "independently_signed",
)
_LEVEL_RANK = {level: index for index, level in enumerate(QUALIFICATION_LEVELS)}
_SAFE_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_FAMILY_FIXTURES = {
    "simulator": "contract-simulator.json",
    "formal": "contract-formal.json",
    "analyzer": "contract-analyzer.json",
}
_FAMILY_CHECKS = {
    "simulator": "QUAL-SIM-001",
    "formal": "QUAL-FORMAL-001",
    "analyzer": "QUAL-ANALYZER-001",
}
_GENERATED_UVM_CHECK = "QUAL-UVM-001"
_FAMILY_SOURCE_FIXTURES = {
    "simulator": ("surrogate.sv", "surrogate.vhd"),
    "formal": ("formal.sv", "surrogate.sby"),
    "analyzer": ("surrogate.sv", "surrogate.vhd"),
}


def _required_families(profile: EnterpriseToolProfile) -> tuple[str, ...]:
    families = tuple(family for family in ("simulator", "formal", "analyzer") if family in profile.families)
    if not families:
        raise QualificationError(f"profile {profile.name} has no qualifiable execution family")
    return families


def _asset_bytes(name: str) -> bytes:
    return resources.files("dv_platform.qualification_assets").joinpath(name).read_bytes()


def _generated_uvm_fixture_bytes() -> dict[str, bytes]:
    """Render the exact UVM qualification environment shipped to a licensed host."""

    evidence = EvidenceRef(EvidenceKind.CONFIGURATION, "qualification", "generated_uvm")
    ports = (
        RTLPort("clk", "input", width=1),
        RTLPort("rst_n", "input", width=1),
        RTLPort("in_valid", "input", width=1),
        RTLPort("in_ready", "output", width=1),
        RTLPort("in_data", "input", width=8),
        RTLPort("out_valid", "output", width=1),
        RTLPort("out_ready", "input", width=1),
        RTLPort("out_data", "output", width=8),
    )
    protocols = (
        RTLProtocol(
            "uvm_stream_loopback:ready_valid:in",
            "ready_valid",
            "in",
            "sink",
            "in_valid",
            "in_ready",
            "in_data",
            8,
            "clk",
            "rst_n",
            evidence_refs=(evidence,),
        ),
        RTLProtocol(
            "uvm_stream_loopback:ready_valid:out",
            "ready_valid",
            "out",
            "source",
            "out_valid",
            "out_ready",
            "out_data",
            8,
            "clk",
            "rst_n",
            evidence_refs=(evidence,),
        ),
    )
    plan = VerificationPlan(
        "uvm_stream_loopback",
        (VerificationTarget.UVM,),
        ports=ports,
        clocks=(RTLClock("clk", "input", width=1, confidence="high"),),
        resets=(RTLReset("rst_n", "input", width=1, active_low=True, confidence="high"),),
        protocols=protocols,
        claims=(
            VerificationClaim("qual:uvm", "uvm_stream_loopback", "qualified UVM fixture", evidence_refs=(evidence,)),
        ),
    )
    rendered = {
        f"generated_uvm/{artifact.path.as_posix()}": artifact.content.encode("utf-8")
        for artifact in UvmGenerator().generate(plan)
    }
    rendered["generated_uvm/uvm_stream_loopback.sv"] = (
        b"module uvm_stream_loopback(\n"
        b"    input logic clk, input logic rst_n,\n"
        b"    input logic in_valid, output logic in_ready, input logic [7:0] in_data,\n"
        b"    output logic out_valid, input logic out_ready, output logic [7:0] out_data\n"
        b");\n"
        b"    assign in_ready = out_ready;\n"
        b"    assign out_valid = in_valid;\n"
        b"    assign out_data = in_data;\n"
        b"endmodule\n"
    )
    return rendered


def _schema_bytes(name: str) -> bytes:
    packaged = resources.files("dv_platform").joinpath("schemas").joinpath(name)
    try:
        return packaged.read_bytes()
    except FileNotFoundError:
        return (Path(__file__).resolve().parents[3] / "schemas" / name).read_bytes()


def _bundle_readme(profile: EnterpriseToolProfile) -> str:
    return (
        f"dv-platform vendor qualification bundle for {profile.display_name}\n\n"
        "Run the included HDL fixtures through a site-approved wrapper which emits the included "
        "enterprise-result-v1 contract. Then execute:\n\n"
        "  python run_qualification.py --tool-name TOOL --tool-version VERSION -- WRAPPER COMMAND\n\n"
        "The runner verifies fixture hashes, supplies DV_PLATFORM_RESULT_PATH and "
        "DV_PLATFORM_QUALIFICATION_ROOT, and writes qualification-attestation.json. "
        "Return only that sanitized attestation to the dv-platform host.\n"
    )


def _record_path(config: CLIConfig, profile: str) -> Path:
    return config.work_dir / "qualification" / "records" / f"{_profile_name(profile)}.json"


def _policy_path(config: CLIConfig) -> Path:
    return config.work_dir / "qualification" / "policy.json"


def _default_policy() -> dict[str, Any]:
    return {
        "schema_version": QUALIFICATION_POLICY_SCHEMA_VERSION,
        "minimum_level": "unverified",
        "profile_minimums": {},
        "max_age_days": None,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_QUALIFICATION_BYTES:
            return None
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _profile_name(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_PROFILE.fullmatch(value):
        raise QualificationError("qualification profile must be a safe 1..128 character identifier")
    return value


def _validate_level(value: Any) -> None:
    if value not in _LEVEL_RANK:
        raise QualificationError("invalid qualification level: " + repr(value))


def _timezone_timestamp(value: Any, label: str) -> str:
    text = _string(value, label)
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError(f"{label} must be ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise QualificationError(f"{label} must include a timezone")
    return text


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise QualificationError(f"{label} must be an object with string keys")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{label} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise QualificationError(f"{label} must be a list of non-empty strings")
    result = [item.strip() for item in value]
    if not allow_empty and not result:
        raise QualificationError(f"{label} must not be empty")
    return result


def _string_mapping(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip() for key, item in value.items()
    ):
        raise QualificationError(f"{label} must be an object of non-empty strings")
    return {key.strip(): item.strip() for key, item in value.items()}


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _payload_sha256(payload: Any) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
