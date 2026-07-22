"""Secure command and result contract for enterprise EDA tools."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.enterprise.profiles import EnterpriseToolProfile, enterprise_profile

ENTERPRISE_RESULT_SCHEMA_VERSION = 1
MAX_ENTERPRISE_RESULT_BYTES = 32 * 1024 * 1024
MAX_ENTERPRISE_LOG_BYTES = 64 * 1024 * 1024
MAX_ENTERPRISE_TIMEOUT_SECONDS = 24 * 60 * 60
_SAFE_ENVIRONMENT = frozenset({"PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL"})
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_CHECK_STATES = frozenset({"passed", "failed", "skipped", "unknown"})


class EnterpriseAdapterError(ValueError):
    """Raised for unsafe invocation or invalid enterprise evidence."""


@dataclass(frozen=True)
class EnterpriseInvocation:
    adapter: str
    family: str
    command: tuple[str, ...]
    cwd: Path
    result_path: Path
    summary_path: Path
    stdout_path: Path
    stderr_path: Path
    timeout_seconds: float = 3600.0
    environment_names: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    redact_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnterpriseCheckResult:
    check_id: str
    module: str
    kind: str
    status: str
    message: str | None = None
    source_location: str | None = None


@dataclass(frozen=True)
class EnterpriseArtifact:
    kind: str
    path: Path


@dataclass(frozen=True)
class EnterpriseExecutionResult:
    adapter: str
    family: str
    status: str
    return_code: int | None
    duration_seconds: float
    checks: tuple[EnterpriseCheckResult, ...]
    artifacts: tuple[EnterpriseArtifact, ...]
    diagnostics: tuple[str, ...]
    traceability_complete: bool
    summary_path: Path

    @property
    def passed(self) -> bool:
        return self.status == "passed" and all(check.status == "passed" for check in self.checks)


class EnterpriseCommandAdapter:
    """Execute one configured tool command without a shell and normalize evidence."""

    kind = "enterprise_runner"
    api_version = 1
    profile_name = ""

    @property
    def profile(self) -> EnterpriseToolProfile:
        return enterprise_profile(self.profile_name)

    def execute(self, invocation: EnterpriseInvocation, *, strict: bool = False) -> EnterpriseExecutionResult:
        _validate_invocation(invocation, self.profile, self.kind)
        invocation.cwd.mkdir(parents=True, exist_ok=True)
        for path in (
            invocation.result_path,
            invocation.summary_path,
            invocation.stdout_path,
            invocation.stderr_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
        environment = _environment(invocation, self.profile)
        started = time.monotonic()
        return_code: int | None = None
        timed_out = False
        with (
            invocation.stdout_path.open("w", encoding="utf-8") as stdout_file,
            invocation.stderr_path.open("w", encoding="utf-8") as stderr_file,
        ):
            process = subprocess.Popen(
                invocation.command,
                cwd=invocation.cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                start_new_session=True,
            )
            try:
                return_code = process.wait(timeout=invocation.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        duration = time.monotonic() - started
        _sanitize_log(invocation.stdout_path, invocation.redact_patterns)
        _sanitize_log(invocation.stderr_path, invocation.redact_patterns)

        diagnostics: list[str] = []
        if timed_out:
            status = "timeout"
            checks: tuple[EnterpriseCheckResult, ...] = ()
            artifacts: tuple[EnterpriseArtifact, ...] = ()
            traceability_complete = False
            diagnostics.append("enterprise tool timed out")
        elif invocation.result_path.is_file():
            status, checks, artifacts, parsed_diagnostics = _load_result(invocation.result_path, invocation.cwd)
            diagnostics.extend(parsed_diagnostics)
            traceability_complete = bool(checks) and all(check.check_id for check in checks)
            if return_code != 0 and status == "passed":
                status = "failed"
                diagnostics.append("tool returned non-zero after reporting passed")
        else:
            status = "passed" if return_code == 0 else "failed"
            checks = ()
            artifacts = ()
            traceability_complete = False
            diagnostics.append("normalized enterprise result manifest is missing")

        if strict and not traceability_complete:
            status = "failed"
            diagnostics.append("strict enterprise execution requires traceable check results")
        if strict and any(check.status in {"skipped", "unknown"} for check in checks):
            status = "failed"
            diagnostics.append("strict enterprise execution rejects skipped or unknown checks")
        points = [
            {
                "id": f"enterprise:{invocation.family}:{check.check_id}",
                "module": check.module,
                "kind": check.kind,
                "hits": 1 if check.status == "passed" else 0,
                "status": (
                    "covered" if check.status == "passed" else "failed" if check.status == "failed" else "uncovered"
                ),
                "check_id": check.check_id,
                "source_locator": check.source_location,
            }
            for check in checks
        ]
        summary = {
            "schema_version": ENTERPRISE_RESULT_SCHEMA_VERSION,
            "adapter": invocation.adapter,
            "profile": self.profile.name,
            "family": invocation.family,
            "status": status,
            "return_code": return_code,
            "duration_seconds": round(duration, 6),
            "command": {"executable": Path(invocation.command[0]).name, "argument_count": len(invocation.command) - 1},
            "environment_names": sorted(environment.keys() & set(invocation.environment_names)),
            "checks": [check.__dict__ for check in checks],
            "coverage_points": points if invocation.family != "formal" else [],
            "formal_points": points if invocation.family == "formal" else [],
            "artifacts": [{"kind": item.kind, "path": str(item.path)} for item in artifacts],
            "diagnostics": diagnostics,
            "traceability_complete": traceability_complete,
            "stdout": str(invocation.stdout_path),
            "stderr": str(invocation.stderr_path),
        }
        atomic_write_text(invocation.summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return EnterpriseExecutionResult(
            invocation.adapter,
            invocation.family,
            status,
            return_code,
            duration,
            checks,
            artifacts,
            tuple(diagnostics),
            traceability_complete,
            invocation.summary_path,
        )


class EnterpriseSimulatorRunner(EnterpriseCommandAdapter):
    kind = "simulator_runner"


class EnterpriseFormalRunner(EnterpriseCommandAdapter):
    kind = "formal_runner"


class EnterpriseAnalyzerRunner(EnterpriseCommandAdapter):
    kind = "analyzer_runner"


class QuestaSimulatorRunner(EnterpriseSimulatorRunner):
    profile_name = "questa"


class VCSSimulatorRunner(EnterpriseSimulatorRunner):
    profile_name = "vcs"


class XceliumSimulatorRunner(EnterpriseSimulatorRunner):
    profile_name = "xcelium"


class RivieraProSimulatorRunner(EnterpriseSimulatorRunner):
    profile_name = "riviera_pro"


class VivadoXSimSimulatorRunner(EnterpriseSimulatorRunner):
    profile_name = "vivado_xsim"


class JasperGoldFormalRunner(EnterpriseFormalRunner):
    profile_name = "jaspergold"


class VCFormalRunner(EnterpriseFormalRunner):
    profile_name = "vc_formal"


class QuestaFormalRunner(EnterpriseFormalRunner):
    profile_name = "questa_formal"


class SpyGlassAnalyzerRunner(EnterpriseAnalyzerRunner):
    profile_name = "spyglass"


class ALINTProAnalyzerRunner(EnterpriseAnalyzerRunner):
    profile_name = "alint_pro"


def _validate_invocation(invocation: EnterpriseInvocation, profile: EnterpriseToolProfile, adapter_kind: str) -> None:
    if invocation.family not in profile.families:
        raise EnterpriseAdapterError(f"profile {profile.name} does not provide {invocation.family} capability")
    expected_kind = f"{invocation.family}_runner"
    if adapter_kind != expected_kind:
        raise EnterpriseAdapterError(f"adapter kind {adapter_kind} cannot execute {invocation.family} invocation")
    if not invocation.command or any(not item or "\x00" in item for item in invocation.command):
        raise EnterpriseAdapterError("enterprise command must contain non-empty NUL-free arguments")
    if not 0 < invocation.timeout_seconds <= MAX_ENTERPRISE_TIMEOUT_SECONDS:
        raise EnterpriseAdapterError(f"enterprise timeout must be within 1..{MAX_ENTERPRISE_TIMEOUT_SECONDS} seconds")
    root = invocation.cwd.resolve()
    for path in (
        invocation.result_path,
        invocation.summary_path,
        invocation.stdout_path,
        invocation.stderr_path,
    ):
        if not path.resolve().is_relative_to(root):
            raise EnterpriseAdapterError(f"enterprise output escapes working directory: {path}")
    supplied_names = [name for name, _ in invocation.environment]
    if len(supplied_names) != len(set(supplied_names)):
        raise EnterpriseAdapterError("enterprise environment contains duplicate names")
    allowed = _SAFE_ENVIRONMENT | set(invocation.environment_names) | set(profile.license_environment)
    for name in supplied_names:
        if not _ENVIRONMENT_NAME.fullmatch(name) or name not in allowed:
            raise EnterpriseAdapterError(f"enterprise environment variable is not allowed: {name}")
    for pattern in invocation.redact_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise EnterpriseAdapterError(f"invalid redaction pattern: {pattern}") from exc


def _environment(invocation: EnterpriseInvocation, profile: EnterpriseToolProfile) -> dict[str, str]:
    names = _SAFE_ENVIRONMENT | set(invocation.environment_names) | set(profile.license_environment)
    environment = {name: value for name in names if (value := os.environ.get(name)) is not None}
    environment.update(dict(invocation.environment))
    return environment


def _load_result(
    path: Path, work_root: Path
) -> tuple[
    str,
    tuple[EnterpriseCheckResult, ...],
    tuple[EnterpriseArtifact, ...],
    tuple[str, ...],
]:
    root = work_root.resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise EnterpriseAdapterError(f"enterprise result escapes working directory: {path}")
    raw = path.read_bytes()
    if len(raw) > MAX_ENTERPRISE_RESULT_BYTES:
        raise EnterpriseAdapterError(f"enterprise result exceeds {MAX_ENTERPRISE_RESULT_BYTES} byte limit: {path}")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EnterpriseAdapterError(f"invalid enterprise result JSON in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise EnterpriseAdapterError("enterprise result must be a JSON object")
    unknown = set(document) - {"schema_version", "status", "checks", "artifacts", "diagnostics"}
    if unknown:
        raise EnterpriseAdapterError(f"unknown enterprise result fields: {', '.join(sorted(unknown))}")
    if document.get("schema_version") != ENTERPRISE_RESULT_SCHEMA_VERSION:
        raise EnterpriseAdapterError("unsupported enterprise result schema_version")
    status = document.get("status")
    if status not in {"passed", "failed", "error"}:
        raise EnterpriseAdapterError(f"invalid enterprise result status: {status!r}")
    checks: list[EnterpriseCheckResult] = []
    identities: set[str] = set()
    for index, item in enumerate(_object_list(document.get("checks", []), "checks")):
        unknown_check = set(item) - {
            "check_id",
            "module",
            "kind",
            "status",
            "message",
            "source_location",
        }
        if unknown_check:
            raise EnterpriseAdapterError(f"unknown check fields at checks[{index}]: {', '.join(sorted(unknown_check))}")
        check_id = _result_string(item, "check_id", f"checks[{index}]")
        if check_id in identities:
            raise EnterpriseAdapterError(f"duplicate enterprise check_id: {check_id}")
        identities.add(check_id)
        check_status = _result_string(item, "status", f"checks[{index}]")
        if check_status not in _CHECK_STATES:
            raise EnterpriseAdapterError(f"invalid enterprise check status: {check_status}")
        checks.append(
            EnterpriseCheckResult(
                check_id,
                _result_string(item, "module", f"checks[{index}]"),
                _result_string(item, "kind", f"checks[{index}]"),
                check_status,
                _result_optional_string(item, "message"),
                _result_optional_string(item, "source_location"),
            )
        )
    artifacts: list[EnterpriseArtifact] = []
    for index, item in enumerate(_object_list(document.get("artifacts", []), "artifacts")):
        if set(item) - {"kind", "path"}:
            raise EnterpriseAdapterError(f"unknown artifact fields at artifacts[{index}]")
        artifact_path = Path(_result_string(item, "path", f"artifacts[{index}]"))
        resolved = (root / artifact_path).resolve() if not artifact_path.is_absolute() else artifact_path.resolve()
        if not resolved.is_relative_to(root):
            raise EnterpriseAdapterError(f"enterprise artifact escapes working directory: {artifact_path}")
        if not resolved.is_file():
            raise EnterpriseAdapterError(f"enterprise artifact does not exist: {artifact_path}")
        artifacts.append(EnterpriseArtifact(_result_string(item, "kind", f"artifacts[{index}]"), resolved))
    diagnostics = document.get("diagnostics", [])
    if not isinstance(diagnostics, list) or not all(isinstance(item, str) for item in diagnostics):
        raise EnterpriseAdapterError("enterprise diagnostics must be a list of strings")
    return status, tuple(checks), tuple(artifacts), tuple(diagnostics)


def _object_list(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise EnterpriseAdapterError(f"enterprise {label} must be a list of objects")
    return tuple(value)


def _result_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise EnterpriseAdapterError(f"{label}.{key} must be a non-empty string")
    return item.strip()


def _result_optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise EnterpriseAdapterError(f"{key} must be a non-empty string when provided")
    return item.strip()


def _sanitize_log(path: Path, patterns: tuple[str, ...]) -> None:
    with path.open("rb") as stream:
        raw = stream.read(MAX_ENTERPRISE_LOG_BYTES + 1)
    truncated = len(raw) > MAX_ENTERPRISE_LOG_BYTES
    text = raw[:MAX_ENTERPRISE_LOG_BYTES].decode("utf-8", errors="replace")
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    if truncated:
        text += "\n[dv-platform log truncated]\n"
    path.write_text(text, encoding="utf-8")
