# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Auditable enterprise qualification without requiring proprietary licenses."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from shutil import which
from typing import Any

from dv_platform.core.models import (
    CLIConfig,
)

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


def qualification_status(config: CLIConfig) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    policy = _load_qualification_policy(config, failures)
    configured = sorted(
        {
            item.name
            for item in config.adapter_plugins
            if item.kind in {"simulator_runner", "formal_runner", "analyzer_runner"}
        }
    )
    overrides = _string_mapping(policy["profile_minimums"], "profile_minimums")
    records = [_profile_qualification(config, name, policy, overrides, failures) for name in configured]
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "policy": policy,
        "policy_path": str(_policy_path(config)),
        "records": records,
        "failures": failures,
        "passed": not failures,
    }


def _load_qualification_policy(config: CLIConfig, failures: list[dict[str, str]]) -> dict[str, Any]:
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
    return policy


def _profile_qualification(
    config: CLIConfig,
    profile_name: str,
    policy: dict[str, Any],
    overrides: dict[str, str],
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    path = _record_path(config, profile_name)
    raw_record = _read_json(path)
    level, qualified_at, valid = _record_identity(path, raw_record, profile_name, failures)
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
    return {
        "profile": profile_name,
        "level": level,
        "minimum_level": minimum,
        "qualified_at": qualified_at,
        "present": raw_record is not None,
        "valid": valid,
        "path": str(path),
    }


def _record_identity(
    path: Path, raw_record: dict[str, Any] | None, profile_name: str, failures: list[dict[str, str]]
) -> tuple[str, str | None, bool]:
    if path.is_file() and raw_record is None:
        failures.append(
            {
                "code": "qualification_record_invalid",
                "message": f"Qualification record is unreadable or invalid JSON: {path}",
            }
        )
        return "unverified", None, False
    if raw_record is None:
        return "unverified", None, False
    try:
        _validate_record(raw_record, profile_name)
        return str(raw_record["level"]), str(raw_record["qualified_at"]), True
    except QualificationError as exc:
        failures.append(
            {
                "code": "qualification_record_invalid",
                "message": f"Invalid qualification record for {profile_name}: {exc}",
            }
        )
        return "unverified", None, False


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
