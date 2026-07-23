# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Auditable enterprise qualification without requiring proprietary licenses."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import Any

from dv_platform.core.models import (
    CLIConfig,
)
from dv_platform.enterprise.adapters import EnterpriseAdapterError, _load_result
from dv_platform.enterprise.profiles import enterprise_profile

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


for _legacy_class in (
    QualificationError,
    QualificationCheck,
    QualifiedTool,
    QualificationRecord,
    SurrogateProbe,
):
    _legacy_class.__module__ = "dv_platform.enterprise.qualification"
del _legacy_class
