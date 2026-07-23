# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Auditable enterprise qualification without requiring proprietary licenses."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
)
from dv_platform.enterprise.profiles import EnterpriseToolProfile

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
    families = _validate_record_scope(payload)
    _validate_record_tools(payload)
    _validate_record_checks(payload, families)
    _validate_record_attestation(payload)
    _validate_record_signature(payload)


def _validate_record_scope(payload: dict[str, Any]) -> list[str]:
    families = _string_list(payload.get("families"), "families")
    if len(families) != len(set(families)) or not set(families) <= set(_FAMILY_FIXTURES):
        raise QualificationError("qualification families must be unique supported execution families")
    languages = _string_list(payload.get("languages"), "languages", allow_empty=True)
    if len(languages) != len(set(languages)):
        raise QualificationError("qualification languages must be unique")
    fixture_hashes = _string_mapping(payload.get("fixture_hashes"), "fixture_hashes")
    if not fixture_hashes or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in fixture_hashes.values()):
        raise QualificationError("qualification fixture hashes must be lowercase SHA-256 digests")
    return families


def _validate_record_tools(payload: dict[str, Any]) -> None:
    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools or not all(isinstance(item, dict) for item in tools):
        raise QualificationError("qualification tools must be a non-empty list of objects")
    for item in tools:
        if set(item) != {"name", "version"}:
            raise QualificationError("qualification tool fields must be name and version")
        _string(item.get("name"), "tool.name")
        _string(item.get("version"), "tool.version")


def _validate_record_checks(payload: dict[str, Any], families: list[str]) -> None:
    checks = payload.get("checks")
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


def _validate_record_attestation(payload: dict[str, Any]) -> None:
    attestation_digest = payload.get("attestation_sha256")
    if attestation_digest is not None and (
        not isinstance(attestation_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", attestation_digest)
    ):
        raise QualificationError("qualification attestation hash must be a lowercase SHA-256 digest or null")


def _validate_record_signature(payload: dict[str, Any]) -> None:
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
