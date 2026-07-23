# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Auditable enterprise qualification without requiring proprietary licenses."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
)
from dv_platform.enterprise.adapters import EnterpriseAdapterError, _load_result
from dv_platform.enterprise.profiles import EnterpriseToolProfile, enterprise_profile

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
    root = _attestation_root(raw)
    request, result, command = _attestation_payloads(root, profile)
    executed_at = _timezone_timestamp(root.get("executed_at"), "executed_at")
    tool = _object(root.get("tool"), "qualification tool")
    tool_name = _string(tool.get("name"), "tool.name")
    tool_version = _string(tool.get("version"), "tool.version")
    checks, result_digest = _validated_vendor_result(result, root, request)
    families = tuple(_string_list(request.get("required_families"), "required_families"))
    fixture_hashes = _string_mapping(request.get("fixtures"), "fixtures")
    family_by_check = {_FAMILY_CHECKS[family]: family for family in families}
    if request.get("scope") == "generated_uvm":
        family_by_check[_GENERATED_UVM_CHECK] = "simulator"
    level, mode, signature = _vendor_signature(path, executed_at, signature_manifest, trust_policy)
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


def _attestation_root(raw: bytes) -> dict[str, Any]:
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
    return root


def _attestation_payloads(
    root: dict[str, Any], profile: EnterpriseToolProfile
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
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
    return request, result, command


def _validated_vendor_result(
    result: dict[str, Any],
    root: dict[str, Any],
    request: dict[str, Any],
):
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
    return checks, _string(root.get("result_sha256"), "result_sha256")


def _vendor_signature(
    path: Path,
    executed_at: str,
    signature_manifest: Path | None,
    trust_policy: Path | None,
) -> tuple[str, str, dict[str, str] | None]:
    if (signature_manifest is None) != (trust_policy is None):
        raise QualificationError("signature_manifest and trust_policy must be supplied together")
    if signature_manifest is None or trust_policy is None:
        return "vendor_verified", "vendor", None
    from dv_platform.enterprise.signatures import (
        SignatureVerificationError,
        verify_qualification_signature,
    )

    try:
        verified = verify_qualification_signature(path, signature_manifest, trust_policy)
    except SignatureVerificationError as exc:
        raise QualificationError(str(exc)) from exc
    signed_timestamp = datetime.fromisoformat(verified.signed_at.replace("Z", "+00:00"))
    executed_timestamp = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
    if signed_timestamp < executed_timestamp:
        raise QualificationError("qualification signature predates vendor execution")
    return "independently_signed", "signed_vendor", verified.as_payload()


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
