"""Auditable enterprise qualification without requiring proprietary licenses."""

from __future__ import annotations

import json
import os
import re
import subprocess
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest
from importlib import resources
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from dv_platform.core.io import atomic_write_text
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
from dv_platform.enterprise.adapters import EnterpriseAdapterError, _load_result
from dv_platform.enterprise.profiles import EnterpriseToolProfile, enterprise_profile
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


class QualificationError(ValueError):
    """Raised when qualification evidence is incomplete, corrupt, or unsafe."""


@dataclass(frozen=True)
class QualificationCheck:
    check_id: str
    family: str
    status: str
    tool: str
    message: str
    evidence_sha256: str


@dataclass(frozen=True)
class QualifiedTool:
    name: str
    version: str


@dataclass(frozen=True)
class QualificationRecord:
    profile: str
    level: str
    mode: str
    qualified_at: str
    families: tuple[str, ...]
    languages: tuple[str, ...]
    tools: tuple[QualifiedTool, ...]
    fixture_hashes: tuple[tuple[str, str], ...]
    checks: tuple[QualificationCheck, ...]
    attestation_sha256: str | None = None
    signature: dict[str, str] | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema_version": QUALIFICATION_SCHEMA_VERSION,
            "profile": self.profile,
            "level": self.level,
            "mode": self.mode,
            "qualified_at": self.qualified_at,
            "families": list(self.families),
            "languages": list(self.languages),
            "tools": [asdict(item) for item in self.tools],
            "fixture_hashes": dict(self.fixture_hashes),
            "checks": [asdict(item) for item in self.checks],
            "attestation_sha256": self.attestation_sha256,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class SurrogateProbe:
    name: str
    family: str
    languages: tuple[str, ...]
    executables: tuple[str, ...]
    version_args: tuple[str, ...]
    steps: tuple[tuple[str, ...], ...]
    fixture_names: tuple[str, ...]


SURROGATE_PROBES = (
    SurrogateProbe(
        "verilator_lint",
        "analyzer",
        ("systemverilog", "verilog"),
        ("verilator",),
        ("--version",),
        (("verilator", "--lint-only", "-Wall", "-Wno-fatal", "--top-module", "dv_qualification", "surrogate.sv"),),
        ("surrogate.sv",),
    ),
    SurrogateProbe(
        "verilator_simulator",
        "simulator",
        ("systemverilog", "verilog"),
        ("verilator",),
        ("--version",),
        (
            (
                "verilator",
                "--binary",
                "--timing",
                "-Wno-fatal",
                "--top-module",
                "dv_qualification",
                "--Mdir",
                "obj_dir",
                "surrogate.sv",
            ),
            ("{work}/obj_dir/Vdv_qualification",),
        ),
        ("surrogate.sv",),
    ),
    SurrogateProbe(
        "iverilog",
        "simulator",
        ("systemverilog", "verilog"),
        ("iverilog", "vvp"),
        ("-V",),
        (
            ("iverilog", "-g2012", "-s", "dv_qualification", "-o", "{work}/qualification.vvp", "surrogate.sv"),
            ("vvp", "{work}/qualification.vvp"),
        ),
        ("surrogate.sv",),
    ),
    SurrogateProbe(
        "ghdl",
        "simulator",
        ("vhdl",),
        ("ghdl",),
        ("--version",),
        (
            ("ghdl", "-a", "--std=08", "surrogate.vhd"),
            ("ghdl", "-e", "--std=08", "dv_qualification"),
            ("ghdl", "-r", "--std=08", "dv_qualification", "--assert-level=error"),
        ),
        ("surrogate.vhd",),
    ),
    SurrogateProbe(
        "yosys",
        "formal",
        ("systemverilog", "verilog"),
        ("yosys",),
        ("-V",),
        (
            (
                "yosys",
                "-p",
                "read_verilog -formal -sv formal.sv; prep -top dv_formal; sat -verify -prove-asserts -seq 4",
            ),
        ),
        ("formal.sv",),
    ),
    SurrogateProbe(
        "symbiyosys",
        "formal",
        ("systemverilog", "verilog"),
        ("sby",),
        ("--version",),
        (("sby", "-f", "surrogate.sby"),),
        ("formal.sv", "surrogate.sby"),
    ),
)


def qualify_contract(config: CLIConfig, profile_name: str) -> dict[str, Any]:
    profile = enterprise_profile(profile_name)
    families = _required_families(profile)
    checks: list[QualificationCheck] = []
    fixture_hashes: dict[str, str] = {}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for family in families:
            fixture_name = _FAMILY_FIXTURES[family]
            raw = _asset_bytes(fixture_name)
            path = root / fixture_name
            path.write_bytes(raw)
            fixture_hashes[fixture_name] = sha256(raw).hexdigest()
            try:
                status, results, _, diagnostics = _load_result(path, root)
            except EnterpriseAdapterError as exc:
                raise QualificationError(f"invalid contract fixture {fixture_name}: {exc}") from exc
            expected = _FAMILY_CHECKS[family]
            if status != "passed" or {item.check_id for item in results} != {expected}:
                raise QualificationError(f"contract fixture {fixture_name} does not prove {expected}")
            if any(item.status != "passed" for item in results):
                raise QualificationError(f"contract fixture {fixture_name} contains an unsuccessful check")
            checks.append(
                QualificationCheck(
                    expected,
                    family,
                    "passed",
                    "dv-platform-contract",
                    "; ".join(diagnostics) or "normalized contract accepted",
                    fixture_hashes[fixture_name],
                )
            )
    record = QualificationRecord(
        profile.name,
        "contract_verified",
        "fixture",
        _utc_now(),
        families,
        profile.languages,
        (QualifiedTool("dv-platform-contract", f"schema-{QUALIFICATION_SCHEMA_VERSION}"),),
        tuple(sorted(fixture_hashes.items())),
        tuple(checks),
    )
    _persist_record(config, record)
    return record.as_payload()


def qualify_surrogate(
    config: CLIConfig,
    profile_name: str,
    *,
    probe_names: tuple[str, ...] = (),
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    if not 0 < timeout_seconds <= MAX_PROBE_TIMEOUT_SECONDS:
        raise QualificationError(f"surrogate timeout must be within 1..{MAX_PROBE_TIMEOUT_SECONDS} seconds")
    profile = enterprise_profile(profile_name)
    required_families = set(_required_families(profile))
    known = {probe.name: probe for probe in SURROGATE_PROBES}
    unknown = sorted(set(probe_names) - set(known))
    if unknown:
        raise QualificationError("unknown surrogate probes: " + ", ".join(unknown))
    candidates = tuple(known[name] for name in probe_names) if probe_names else SURROGATE_PROBES
    candidates = tuple(probe for probe in candidates if probe.family in required_families)
    available = tuple(probe for probe in candidates if all(which(name) for name in probe.executables))
    if not available:
        raise QualificationError("no applicable open-source surrogate tools are installed")

    checks: list[QualificationCheck] = []
    tools: dict[str, QualifiedTool] = {}
    fixture_hashes: dict[str, str] = {}
    passed_families: set[str] = set()
    passed_languages: set[str] = set()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for asset_name in sorted({name for probe in available for name in probe.fixture_names}):
            raw = _asset_bytes(asset_name)
            (root / asset_name).write_bytes(raw)
            fixture_hashes[asset_name] = sha256(raw).hexdigest()
        for probe in available:
            check, version = _execute_probe(probe, root, timeout_seconds)
            checks.append(check)
            tools[probe.name] = QualifiedTool(probe.name, version)
            if check.status == "passed":
                passed_families.add(probe.family)
                passed_languages.update(set(probe.languages) & set(profile.languages))
    missing = sorted(required_families - passed_families)
    if missing:
        failures = "; ".join(item.message for item in checks if item.status != "passed")
        raise QualificationError("surrogate qualification is missing families " + ", ".join(missing) + f": {failures}")
    record = QualificationRecord(
        profile.name,
        "surrogate_verified",
        "surrogate",
        _utc_now(),
        tuple(sorted(passed_families)),
        tuple(sorted(passed_languages)),
        tuple(tools[name] for name in sorted(tools)),
        tuple(sorted(fixture_hashes.items())),
        tuple(checks),
    )
    _persist_record(config, record)
    return record.as_payload()


def create_vendor_qualification_bundle(
    profile_name: str,
    output: Path,
    *,
    include_generated_uvm: bool = False,
) -> dict[str, Any]:
    profile = enterprise_profile(profile_name)
    if output.suffix.lower() != ".zip":
        raise QualificationError("qualification bundle output must use a .zip suffix")
    families = _required_families(profile)
    fixture_names = sorted(
        {
            *(_FAMILY_FIXTURES[family] for family in families),
            *(name for family in families for name in _FAMILY_SOURCE_FIXTURES[family]),
        }
    )
    fixture_payloads = {name: _asset_bytes(name) for name in fixture_names}
    if include_generated_uvm:
        if "simulator" not in profile.families or "uvm" not in profile.capabilities:
            raise QualificationError(f"profile {profile.name} cannot qualify generated UVM")
        fixture_payloads.update(_generated_uvm_fixture_bytes())
    fixture_hashes = {name: sha256(raw).hexdigest() for name, raw in fixture_payloads.items()}
    required_checks = [_FAMILY_CHECKS[family] for family in families]
    if include_generated_uvm:
        required_checks.append(_GENERATED_UVM_CHECK)
    request = {
        "schema_version": QUALIFICATION_REQUEST_SCHEMA_VERSION,
        "request_id": str(uuid4()),
        "created_at": _utc_now(),
        "profile": profile.name,
        "required_families": list(families),
        "required_check_ids": required_checks,
        "fixtures": fixture_hashes,
        "result_schema_version": 1,
        "scope": "generated_uvm" if include_generated_uvm else "reference",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("qualification-request.json", _canonical_json(request) + "\n")
        archive.writestr("run_qualification.py", _asset_bytes("vendor_runner.py"))
        if profile.name == "vivado_xsim":
            archive.writestr("run_vivado_xsim.py", _asset_bytes("vivado_xsim_runner.py"))
        archive.writestr("enterprise-result-v1.schema.json", _schema_bytes("enterprise-result-v1.schema.json"))
        archive.writestr("README.txt", _bundle_readme(profile))
        for name, raw in sorted(fixture_payloads.items()):
            archive.writestr(f"fixtures/{name}", raw)
    return {
        "profile": profile.name,
        "bundle": str(output),
        "request_sha256": _payload_sha256(request),
        "fixture_hashes": fixture_hashes,
    }


def import_vendor_attestation(
    config: CLIConfig,
    profile_name: str,
    path: Path,
    *,
    signature_manifest: Path | None = None,
    trust_policy: Path | None = None,
) -> dict[str, Any]:
    profile = enterprise_profile(profile_name)
    raw = path.read_bytes()
    if len(raw) > MAX_QUALIFICATION_BYTES:
        raise QualificationError(f"qualification attestation exceeds {MAX_QUALIFICATION_BYTES} byte limit")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QualificationError(f"invalid qualification attestation JSON: {exc}") from exc
    root = _object(document, "qualification attestation")
    allowed = {
        "schema_version",
        "request",
        "request_sha256",
        "tool",
        "executed_at",
        "command",
        "result",
        "result_sha256",
        "integrity_sha256",
    }
    if unknown := sorted(set(root) - allowed):
        raise QualificationError("unknown qualification attestation fields: " + ", ".join(unknown))
    if root.get("schema_version") != QUALIFICATION_ATTESTATION_SCHEMA_VERSION:
        raise QualificationError("unsupported qualification attestation schema_version")
    integrity_payload = dict(root)
    integrity = _string(integrity_payload.pop("integrity_sha256", None), "integrity_sha256")
    if not compare_digest(integrity, _payload_sha256(integrity_payload)):
        raise QualificationError("qualification attestation integrity check failed")

    request = _object(root.get("request"), "qualification request")
    if root.get("request_sha256") != _payload_sha256(request):
        raise QualificationError("qualification request digest does not match")
    _validate_request(request, profile)
    result = _object(root.get("result"), "qualification result")
    if root.get("result_sha256") != _payload_sha256(result):
        raise QualificationError("qualification result digest does not match")
    command = _object(root.get("command"), "qualification command")
    if command.get("return_code") != 0:
        raise QualificationError("vendor qualification command did not exit successfully")

    executed_at = _timezone_timestamp(root.get("executed_at"), "executed_at")
    tool = _object(root.get("tool"), "qualification tool")
    tool_name = _string(tool.get("name"), "tool.name")
    tool_version = _string(tool.get("version"), "tool.version")
    with TemporaryDirectory() as directory:
        result_path = Path(directory) / "result.json"
        result_path.write_text(_canonical_json(result), encoding="utf-8")
        try:
            status, checks, _, _ = _load_result(result_path, Path(directory))
        except EnterpriseAdapterError as exc:
            raise QualificationError(f"invalid normalized vendor result: {exc}") from exc
    expected_checks = set(_string_list(request.get("required_check_ids"), "required_check_ids"))
    observed_checks = {item.check_id for item in checks if item.status == "passed"}
    if status != "passed" or not expected_checks <= observed_checks:
        raise QualificationError("vendor result does not pass every required qualification check")
    result_digest = _string(root.get("result_sha256"), "result_sha256")
    families = tuple(_string_list(request.get("required_families"), "required_families"))
    fixture_hashes = _string_mapping(request.get("fixtures"), "fixtures")
    family_by_check = {_FAMILY_CHECKS[family]: family for family in families}
    if request.get("scope") == "generated_uvm":
        family_by_check[_GENERATED_UVM_CHECK] = "simulator"
    if (signature_manifest is None) != (trust_policy is None):
        raise QualificationError("signature_manifest and trust_policy must be supplied together")
    signature: dict[str, str] | None = None
    level = "vendor_verified"
    mode = "vendor"
    if signature_manifest is not None and trust_policy is not None:
        from dv_platform.enterprise.signatures import (
            SignatureVerificationError,
            verify_qualification_signature,
        )

        try:
            verified_signature = verify_qualification_signature(path, signature_manifest, trust_policy)
        except SignatureVerificationError as exc:
            raise QualificationError(str(exc)) from exc
        signed_timestamp = datetime.fromisoformat(verified_signature.signed_at.replace("Z", "+00:00"))
        executed_timestamp = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
        if signed_timestamp < executed_timestamp:
            raise QualificationError("qualification signature predates vendor execution")
        signature = verified_signature.as_payload()
        level = "independently_signed"
        mode = "signed_vendor"
    record = QualificationRecord(
        profile.name,
        level,
        mode,
        executed_at,
        families,
        profile.languages,
        (QualifiedTool(tool_name, tool_version),),
        tuple(sorted(fixture_hashes.items())),
        tuple(
            QualificationCheck(
                item.check_id,
                family_by_check[item.check_id],
                "passed",
                tool_name,
                item.message or "vendor check passed",
                result_digest,
            )
            for item in checks
            if item.check_id in family_by_check
        ),
        sha256(raw).hexdigest(),
        signature,
    )
    _persist_record(config, record)
    return record.as_payload()


def set_qualification_policy(
    config: CLIConfig,
    minimum_level: str,
    *,
    profile: str | None = None,
    max_age_days: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    _validate_level(minimum_level)
    path = _policy_path(config)
    existing = _read_json(path)
    if existing is None or existing.get("schema_version") != QUALIFICATION_POLICY_SCHEMA_VERSION:
        payload: dict[str, Any] = {
            "schema_version": QUALIFICATION_POLICY_SCHEMA_VERSION,
            "minimum_level": "unverified",
            "profile_minimums": {},
            "max_age_days": None,
        }
    else:
        payload = dict(existing)
    if profile is None:
        payload["minimum_level"] = minimum_level
    else:
        _profile_name(profile)
        overrides = dict(_string_mapping(payload.get("profile_minimums", {}), "profile_minimums"))
        overrides[profile] = minimum_level
        payload["profile_minimums"] = overrides
    if max_age_days is not None:
        if max_age_days <= 0:
            raise QualificationError("qualification max_age_days must be positive")
        payload["max_age_days"] = max_age_days
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path, payload


def qualification_status(config: CLIConfig) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    policy_path = _policy_path(config)
    raw_policy = _read_json(policy_path)
    if policy_path.is_file() and raw_policy is None:
        policy = _default_policy()
        failures.append(
            {
                "code": "qualification_policy_invalid",
                "message": f"Qualification policy is unreadable or invalid JSON: {policy_path}",
            }
        )
    else:
        try:
            policy = _validate_policy(raw_policy) if raw_policy is not None else _default_policy()
        except QualificationError as exc:
            policy = _default_policy()
            failures.append({"code": "qualification_policy_invalid", "message": str(exc)})
    configured = sorted(
        {
            item.name
            for item in config.adapter_plugins
            if item.kind in {"simulator_runner", "formal_runner", "analyzer_runner"}
        }
    )
    records: list[dict[str, Any]] = []
    overrides = _string_mapping(policy["profile_minimums"], "profile_minimums")
    for profile_name in configured:
        path = _record_path(config, profile_name)
        raw_record = _read_json(path)
        level = "unverified"
        qualified_at: str | None = None
        valid = raw_record is not None
        if path.is_file() and raw_record is None:
            failures.append(
                {
                    "code": "qualification_record_invalid",
                    "message": f"Qualification record is unreadable or invalid JSON: {path}",
                }
            )
        elif raw_record is not None:
            try:
                _validate_record(raw_record, profile_name)
                level = str(raw_record["level"])
                qualified_at = str(raw_record["qualified_at"])
            except QualificationError as exc:
                valid = False
                failures.append(
                    {
                        "code": "qualification_record_invalid",
                        "message": f"Invalid qualification record for {profile_name}: {exc}",
                    }
                )
        minimum = overrides.get(profile_name, str(policy["minimum_level"]))
        if _LEVEL_RANK[level] < _LEVEL_RANK[minimum]:
            failures.append(
                {
                    "code": "enterprise_qualification_below_policy",
                    "message": f"Enterprise profile {profile_name} is {level}; policy requires {minimum}.",
                }
            )
        max_age_days = policy.get("max_age_days")
        if qualified_at is not None and isinstance(max_age_days, int):
            age = datetime.now(UTC) - datetime.fromisoformat(qualified_at.replace("Z", "+00:00"))
            if age.days > max_age_days:
                failures.append(
                    {
                        "code": "enterprise_qualification_stale",
                        "message": f"Enterprise qualification for {profile_name} is {age.days} days old.",
                    }
                )
        records.append(
            {
                "profile": profile_name,
                "level": level,
                "minimum_level": minimum,
                "qualified_at": qualified_at,
                "present": raw_record is not None,
                "valid": valid,
                "path": str(path),
            }
        )
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "policy": policy,
        "policy_path": str(policy_path),
        "records": records,
        "failures": failures,
        "passed": not failures,
    }


def _execute_probe(probe: SurrogateProbe, work: Path, timeout_seconds: float) -> tuple[QualificationCheck, str]:
    resolved = {name: which(name) for name in probe.executables}
    if any(path is None for path in resolved.values()):
        raise QualificationError(f"surrogate probe became unavailable: {probe.name}")
    environment = {
        name: value
        for name in ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL")
        if (value := os.environ.get(name)) is not None
    }
    version_command = [str(resolved[probe.executables[0]]), *probe.version_args]
    version_result = subprocess.run(
        version_command,
        cwd=work,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=min(timeout_seconds, 30.0),
        check=False,
    )
    version_text = (version_result.stdout or version_result.stderr).strip().splitlines()
    version = version_text[0][:512] if version_text else "version unavailable"
    output = bytearray()
    status = "passed"
    message = "open-source surrogate probe passed"
    for raw_step in probe.steps:
        command = [item.format(work=str(work)) for item in raw_step]
        if command[0] in resolved:
            command[0] = str(resolved[command[0]])
        try:
            result = subprocess.run(
                command,
                cwd=work,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            status = "failed"
            message = f"surrogate probe timed out after {timeout_seconds:g} seconds"
            break
        except OSError as exc:
            status = "failed"
            message = f"surrogate probe could not execute: {exc}"
            break
        output.extend(result.stdout[:MAX_PROBE_OUTPUT_BYTES])
        output.extend(result.stderr[:MAX_PROBE_OUTPUT_BYTES])
        if result.returncode != 0:
            status = "failed"
            message = f"surrogate probe returned {result.returncode}"
            break
    return (
        QualificationCheck(
            f"SURROGATE-{probe.name.upper().replace('_', '-')}",
            probe.family,
            status,
            probe.name,
            message,
            sha256(bytes(output[:MAX_PROBE_OUTPUT_BYTES])).hexdigest(),
        ),
        version,
    )


def _persist_record(config: CLIConfig, record: QualificationRecord) -> None:
    payload = record.as_payload()
    _validate_record(payload, record.profile)
    history = config.work_dir / "qualification" / "history" / record.profile
    history_name = record.qualified_at.replace(":", "-") + f"-{record.mode}.json"
    atomic_write_text(history / history_name, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    current = _read_json(_record_path(config, record.profile))
    if current is not None and current.get("level") in _LEVEL_RANK:
        if _LEVEL_RANK[str(current["level"])] > _LEVEL_RANK[record.level]:
            return
    atomic_write_text(_record_path(config, record.profile), json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _validate_record(payload: dict[str, Any], profile_name: str) -> None:
    allowed = {
        "schema_version",
        "profile",
        "level",
        "mode",
        "qualified_at",
        "families",
        "languages",
        "tools",
        "fixture_hashes",
        "checks",
        "attestation_sha256",
        "signature",
    }
    if unknown := sorted(set(payload) - allowed):
        raise QualificationError("unknown qualification record fields: " + ", ".join(unknown))
    if payload.get("schema_version") != QUALIFICATION_SCHEMA_VERSION:
        raise QualificationError("unsupported qualification record schema_version")
    if payload.get("profile") != profile_name:
        raise QualificationError("qualification profile does not match record path")
    _profile_name(profile_name)
    _validate_level(payload.get("level"))
    mode = payload.get("mode")
    if not isinstance(mode, str):
        raise QualificationError("qualification mode must be a string")
    expected_level = {
        "fixture": "contract_verified",
        "surrogate": "surrogate_verified",
        "vendor": "vendor_verified",
        "signed_vendor": "independently_signed",
    }.get(mode)
    if expected_level != payload.get("level"):
        raise QualificationError("qualification mode and level are inconsistent")
    _timezone_timestamp(payload.get("qualified_at"), "qualified_at")
    families = _string_list(payload.get("families"), "families")
    if len(families) != len(set(families)) or not set(families) <= set(_FAMILY_FIXTURES):
        raise QualificationError("qualification families must be unique supported execution families")
    languages = _string_list(payload.get("languages"), "languages", allow_empty=True)
    if len(languages) != len(set(languages)):
        raise QualificationError("qualification languages must be unique")
    fixture_hashes = _string_mapping(payload.get("fixture_hashes"), "fixture_hashes")
    if not fixture_hashes or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in fixture_hashes.values()):
        raise QualificationError("qualification fixture hashes must be lowercase SHA-256 digests")
    tools = payload.get("tools")
    checks = payload.get("checks")
    if not isinstance(tools, list) or not tools or not all(isinstance(item, dict) for item in tools):
        raise QualificationError("qualification tools must be a non-empty list of objects")
    for item in tools:
        if set(item) != {"name", "version"}:
            raise QualificationError("qualification tool fields must be name and version")
        _string(item.get("name"), "tool.name")
        _string(item.get("version"), "tool.version")
    if not isinstance(checks, list) or not checks or not all(isinstance(item, dict) for item in checks):
        raise QualificationError("qualification checks must be a non-empty list of objects")
    check_ids: set[str] = set()
    for item in checks:
        if set(item) != {"check_id", "family", "status", "tool", "message", "evidence_sha256"}:
            raise QualificationError("qualification check contains unknown or missing fields")
        check_id = _string(item.get("check_id"), "check.check_id")
        if check_id in check_ids:
            raise QualificationError(f"duplicate qualification check_id: {check_id}")
        check_ids.add(check_id)
        if item.get("family") not in families:
            raise QualificationError("qualification check family is outside the record scope")
        if item.get("status") != "passed":
            raise QualificationError("qualification record contains unsuccessful checks")
        _string(item.get("tool"), "check.tool")
        _string(item.get("message"), "check.message")
        evidence_digest = _string(item.get("evidence_sha256"), "check.evidence_sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_digest):
            raise QualificationError("qualification check evidence must be a lowercase SHA-256 digest")
    attestation_digest = payload.get("attestation_sha256")
    if attestation_digest is not None and (
        not isinstance(attestation_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", attestation_digest)
    ):
        raise QualificationError("qualification attestation hash must be a lowercase SHA-256 digest or null")
    signature = payload.get("signature")
    if payload.get("level") == "independently_signed":
        if not isinstance(signature, dict) or set(signature) != {
            "kind",
            "identity",
            "issuer",
            "certificate_sha256",
            "manifest_sha256",
            "signed_at",
        }:
            raise QualificationError("independently signed qualification requires exact signature metadata")
        if signature.get("kind") != "enterprise_pki":
            raise QualificationError("unsupported qualification signature kind")
        _string(signature.get("identity"), "signature.identity")
        _string(signature.get("issuer"), "signature.issuer")
        _timezone_timestamp(signature.get("signed_at"), "signature.signed_at")
        for field in ("certificate_sha256", "manifest_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", _string(signature.get(field), f"signature.{field}")):
                raise QualificationError(f"signature.{field} must be a lowercase SHA-256 digest")
    elif signature is not None:
        raise QualificationError("unsigned qualification record cannot contain signature metadata")


def _validate_policy(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != QUALIFICATION_POLICY_SCHEMA_VERSION:
        raise QualificationError("unsupported qualification policy schema_version")
    _validate_level(payload.get("minimum_level"))
    overrides = _string_mapping(payload.get("profile_minimums"), "profile_minimums")
    for profile_name, level in overrides.items():
        _profile_name(profile_name)
        _validate_level(level)
    max_age = payload.get("max_age_days")
    if max_age is not None and (not isinstance(max_age, int) or isinstance(max_age, bool) or max_age <= 0):
        raise QualificationError("qualification policy max_age_days must be a positive integer or null")
    return payload


def _validate_request(request: dict[str, Any], profile: EnterpriseToolProfile) -> None:
    if request.get("schema_version") != QUALIFICATION_REQUEST_SCHEMA_VERSION:
        raise QualificationError("unsupported qualification request schema_version")
    if request.get("profile") != profile.name:
        raise QualificationError("qualification request profile does not match")
    _timezone_timestamp(request.get("created_at"), "request.created_at")
    families = tuple(_string_list(request.get("required_families"), "required_families"))
    if families != _required_families(profile):
        raise QualificationError("qualification request families do not match the profile")
    scope = request.get("scope", "reference")
    if scope not in {"reference", "generated_uvm"}:
        raise QualificationError("qualification request scope is unsupported")
    expected_checks = tuple(_FAMILY_CHECKS[family] for family in families)
    if scope == "generated_uvm":
        if "simulator" not in profile.families or "uvm" not in profile.capabilities:
            raise QualificationError("qualification profile does not support generated UVM")
        expected_checks = (*expected_checks, _GENERATED_UVM_CHECK)
    if tuple(_string_list(request.get("required_check_ids"), "required_check_ids")) != expected_checks:
        raise QualificationError("qualification request check identities do not match")
    fixtures = _string_mapping(request.get("fixtures"), "fixtures")
    expected_names = {
        *(_FAMILY_FIXTURES[family] for family in families),
        *(name for family in families for name in _FAMILY_SOURCE_FIXTURES[family]),
    }
    expected_payloads = {name: _asset_bytes(name) for name in expected_names}
    if scope == "generated_uvm":
        expected_payloads.update(_generated_uvm_fixture_bytes())
    expected = {name: sha256(raw).hexdigest() for name, raw in expected_payloads.items()}
    if fixtures != expected:
        raise QualificationError("qualification request fixture hashes do not match this release")


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
