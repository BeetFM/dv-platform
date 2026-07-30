# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    EvidenceRef,
    RTLModule,
)

SEMANTIC_CROSSCHECK_API_VERSION = 3
SEMANTIC_CROSSCHECK_SCHEMA_VERSION = 3
SLANG_MIN_TESTED_MAJOR = 11
SLANG_MAX_TESTED_MAJOR = 11

CAPABILITY_DESIGN_UNITS = "design_units"
CAPABILITY_SPECIALIZATIONS = "specializations"
CAPABILITY_PORTS = "ports"
CAPABILITY_PARAMETERS = "parameters"
CAPABILITY_TYPES = "types"
CAPABILITY_HIERARCHY = "hierarchy"
CAPABILITY_ASSIGNMENTS = "assignments"
CAPABILITY_PROCEDURAL_BLOCKS = "procedural_blocks"
CAPABILITY_EXPRESSIONS = "expressions"
CAPABILITY_BRANCHES = "branches"
CAPABILITY_CONTROL_DOMAINS = "control_domains"
CAPABILITY_PROPERTIES = "properties"
CAPABILITY_INTERFACES = "interfaces"
CAPABILITY_IMPORTS = "imports"
CAPABILITY_GENERATE_SCOPES = "generate_scopes"
CAPABILITY_MEMORIES = "memories"

CORE_REQUIRED_CAPABILITIES = (
    CAPABILITY_DESIGN_UNITS,
    CAPABILITY_SPECIALIZATIONS,
    CAPABILITY_PORTS,
    CAPABILITY_PARAMETERS,
)
BASE_STRUCTURAL_CAPABILITIES = (
    *CORE_REQUIRED_CAPABILITIES,
    CAPABILITY_HIERARCHY,
    CAPABILITY_ASSIGNMENTS,
    CAPABILITY_PROCEDURAL_BLOCKS,
)
COMPARABLE_CAPABILITIES = (
    *CORE_REQUIRED_CAPABILITIES,
    CAPABILITY_TYPES,
    CAPABILITY_HIERARCHY,
    CAPABILITY_ASSIGNMENTS,
    CAPABILITY_PROCEDURAL_BLOCKS,
    CAPABILITY_EXPRESSIONS,
    CAPABILITY_BRANCHES,
    CAPABILITY_CONTROL_DOMAINS,
    CAPABILITY_PROPERTIES,
    CAPABILITY_INTERFACES,
    CAPABILITY_IMPORTS,
    CAPABILITY_GENERATE_SCOPES,
    CAPABILITY_MEMORIES,
)


@dataclass(frozen=True)
class FrontendMetadata:
    """Identity and reproducibility metadata for one semantic frontend."""

    name: str
    version: str | None = None
    command: tuple[str, ...] = ()
    artifact_path: str | None = None


@dataclass(frozen=True)
class CapabilityCoverage:
    """Whether a frontend supplied one comparison capability."""

    capability: str
    status: str
    required: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class SemanticCrossCheckIssue:
    """One fail-closed disagreement or capability gap."""

    module: str
    field: str
    primary: str
    reference: str
    severity: str = "error"
    capability: str = CAPABILITY_DESIGN_UNITS
    specialization: str | None = None
    primary_evidence: tuple[EvidenceRef, ...] = ()
    reference_evidence: tuple[EvidenceRef, ...] = ()
    primary_location: str | None = None
    reference_location: str | None = None


@dataclass(frozen=True)
class SemanticCrossCheckResult:
    """Auditable, versioned result of comparing two semantic views."""

    primary_name: str
    reference_name: str
    checked_modules: tuple[str, ...]
    issues: tuple[SemanticCrossCheckIssue, ...] = ()
    schema_version: int = SEMANTIC_CROSSCHECK_SCHEMA_VERSION
    run_id: str = "default"
    status: str = "passed"
    primary: FrontendMetadata | None = None
    reference: FrontendMetadata | None = None
    capabilities: tuple[CapabilityCoverage, ...] = ()
    unsupported_capabilities: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "passed" and not any(issue.severity == "error" for issue in self.issues)


@dataclass(frozen=True)
class SlangRunResult:
    """All persisted outputs from one Slang AST extraction."""

    command: tuple[str, ...]
    return_code: int | None
    version: str | None
    ast_path: Path
    stdout_log: Path
    stderr_log: Path
    version_log: Path
    command_log: Path
    diagnostics_path: Path
    modules: tuple[RTLModule, ...] = ()
    capabilities: tuple[str, ...] = ()
    unsupported_capabilities: tuple[str, ...] = ()
    capability_reasons: tuple[tuple[str, str], ...] = ()
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 and self.error is None and bool(self.modules)


@dataclass(frozen=True)
class SlangNormalizationBenchmark:
    """Measured full-document normalization cost for qualification."""

    nodes: int
    elapsed_seconds: float
    peak_bytes: int
    modules: int


class SemanticCrossChecker(Protocol):
    """Adapter contract for an independent frontend comparison."""

    api_version: int
    name: str

    def compare(
        self,
        primary: tuple[RTLModule, ...],
        reference: tuple[RTLModule, ...],
    ) -> SemanticCrossCheckResult:
        """Compare normalized facts without merging either frontend's facts."""


class NormalizedFactCrossChecker:
    """Capability-aware, specialization-stable normalized fact comparator."""

    api_version = SEMANTIC_CROSSCHECK_API_VERSION
    name = "normalized-facts"

    def __init__(
        self,
        *,
        run_id: str = "default",
        primary: FrontendMetadata | None = None,
        reference: FrontendMetadata | None = None,
        primary_capabilities: tuple[str, ...] = COMPARABLE_CAPABILITIES,
        reference_capabilities: tuple[str, ...] = COMPARABLE_CAPABILITIES,
        required_capabilities: tuple[str, ...] = CORE_REQUIRED_CAPABILITIES,
        unsupported_reasons: dict[str, str] | None = None,
        nonrequired_severity: str = "error",
    ) -> None:
        self.run_id = run_id
        self.primary = primary or FrontendMetadata("primary")
        self.reference = reference or FrontendMetadata(self.name)
        self.primary_capabilities = frozenset(primary_capabilities)
        self.reference_capabilities = frozenset(reference_capabilities)
        self.required_capabilities = frozenset(required_capabilities)
        self.unsupported_reasons = unsupported_reasons or {}
        if nonrequired_severity not in {"error", "warning"}:
            raise ValueError("nonrequired semantic issue severity must be error or warning")
        self.nonrequired_severity = nonrequired_severity

    def compare(
        self,
        primary: tuple[RTLModule, ...],
        reference: tuple[RTLModule, ...],
    ) -> SemanticCrossCheckResult:
        issues: list[SemanticCrossCheckIssue] = []
        checked: list[str] = []
        coverage, unsupported, capability_issues = self._capability_coverage()
        issues.extend(capability_issues)

        if CAPABILITY_DESIGN_UNITS in self.primary_capabilities & self.reference_capabilities:
            primary_by_key = _modules_by_specialization(primary)
            reference_by_key = _modules_by_specialization(reference)
            for key in sorted(set(primary_by_key) | set(reference_by_key)):
                module_name, specialization = key
                left_candidates = primary_by_key.get(key, ())
                right_candidates = reference_by_key.get(key, ())
                if len(left_candidates) != 1 or len(right_candidates) != 1:
                    field = "module" if not left_candidates or not right_candidates else "specialization_identity"
                    issues.append(
                        SemanticCrossCheckIssue(
                            module_name,
                            field,
                            str(len(left_candidates)),
                            str(len(right_candidates)),
                            capability=CAPABILITY_SPECIALIZATIONS,
                            specialization=specialization,
                            primary_evidence=tuple(ref for item in left_candidates for ref in item.ast_refs),
                            reference_evidence=tuple(ref for item in right_candidates for ref in item.ast_refs),
                        )
                    )
                    continue
                left = left_candidates[0]
                right = right_candidates[0]
                checked.append(_display_specialization(module_name, specialization))
                _compare_module(
                    left,
                    right,
                    specialization,
                    self.primary_capabilities & self.reference_capabilities,
                    self.required_capabilities,
                    self.nonrequired_severity,
                    issues,
                )

        status = "passed" if not any(issue.severity == "error" for issue in issues) else "failed"
        return SemanticCrossCheckResult(
            primary_name=self.primary.name,
            reference_name=self.reference.name,
            checked_modules=tuple(checked),
            issues=tuple(issues),
            run_id=self.run_id,
            status=status,
            primary=self.primary,
            reference=self.reference,
            capabilities=tuple(coverage),
            unsupported_capabilities=tuple(unsupported),
        )

    def _capability_coverage(
        self,
    ) -> tuple[list[CapabilityCoverage], list[str], list[SemanticCrossCheckIssue]]:
        coverage: list[CapabilityCoverage] = []
        unsupported: list[str] = []
        issues: list[SemanticCrossCheckIssue] = []
        for capability in COMPARABLE_CAPABILITIES:
            required = capability in self.required_capabilities
            if capability not in self.primary_capabilities:
                status = "missing_primary"
            elif capability not in self.reference_capabilities:
                status = "unsupported"
            else:
                status = "checked"
            coverage.append(CapabilityCoverage(capability, status, required, self.unsupported_reasons.get(capability)))
            if status == "checked":
                continue
            unsupported.append(capability)
            if required:
                issues.append(
                    SemanticCrossCheckIssue(
                        module="*",
                        field="capability",
                        primary="available" if capability in self.primary_capabilities else "missing",
                        reference="available" if capability in self.reference_capabilities else "unsupported",
                        capability=capability,
                    )
                )
        return coverage, unsupported, issues


class SlangRunError(RuntimeError):
    """Raised when Slang cannot produce a trustworthy AST result."""


class SlangAnalyzer:
    """Run Slang's AST JSON frontend and persist all operational evidence."""

    api_version = SEMANTIC_CROSSCHECK_API_VERSION
    name = "slang"

    def __init__(
        self,
        executable: str | Path = "slang",
        standard: str = "1800-2017",
        redact: Callable[[str], str] | None = None,
    ) -> None:
        self.executable = str(executable)
        self.standard = standard
        self.redact = redact or (lambda value: value)

    def build_command(
        self,
        files: tuple[Path, ...],
        output_path: Path,
        *,
        top_modules: tuple[str, ...] = (),
        include_paths: tuple[Path, ...] = (),
        defines: tuple[str, ...] = (),
        parameter_overrides: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        command = [
            *shlex.split(self.executable),
            "--std",
            self.standard,
            "--quiet",
            "--ast-json",
            str(output_path),
            "--ast-json-source-info",
            "--ast-json-detailed-types",
        ]
        command.extend(f"-I{path}" for path in include_paths)
        command.extend(f"-D{define}" for define in defines)
        for override in parameter_overrides:
            command.extend(("-G", override))
        for top in top_modules:
            command.extend(("--top", top))
        command.extend(str(path) for path in files)
        return tuple(command)

    def detect_version(self) -> str | None:
        try:
            completed = subprocess.run(
                (*shlex.split(self.executable), "--version"),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        text = (completed.stdout or completed.stderr).strip()
        return text.splitlines()[0] if completed.returncode == 0 and text else None

    def run(
        self,
        files: tuple[Path, ...],
        output_path: Path,
        *,
        top_modules: tuple[str, ...] = (),
        include_paths: tuple[Path, ...] = (),
        defines: tuple[str, ...] = (),
        parameter_overrides: tuple[str, ...] = (),
    ) -> SlangRunResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logs_dir = output_path.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_log = logs_dir / "slang.stdout.log"
        stderr_log = logs_dir / "slang.stderr.log"
        version_log = output_path.parent / "slang-version.txt"
        command_log = output_path.parent / "slang-command.json"
        diagnostics_path = output_path.parent / "diagnostics.json"
        command = self.build_command(
            files,
            output_path,
            top_modules=top_modules,
            include_paths=include_paths,
            defines=defines,
            parameter_overrides=parameter_overrides,
        )
        output_path.unlink(missing_ok=True)
        version = self.detect_version()
        atomic_write_text(version_log, (version or "unknown") + "\n")
        atomic_write_text(command_log, json.dumps(list(command), indent=2) + "\n")
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
        except OSError as error:
            message = self.redact(str(error))
            atomic_write_text(stdout_log, "")
            atomic_write_text(stderr_log, message + "\n")
            _write_diagnostics(diagnostics_path, None, "unavailable", message)
            return _slang_run_result(command, None, version, output_path, logs_dir, message)
        atomic_write_text(stdout_log, self.redact(completed.stdout))
        atomic_write_text(stderr_log, self.redact(completed.stderr))
        if completed.returncode != 0 or not output_path.is_file():
            message = self.redact(completed.stderr.strip() or completed.stdout.strip() or "Slang AST output missing")
            _write_diagnostics(diagnostics_path, completed.returncode, "compilation_failed", message)
            return _slang_run_result(command, completed.returncode, version, output_path, logs_dir, message)
        try:
            document = json.loads(output_path.read_text(encoding="utf-8"))
            modules, capabilities, unsupported, capability_reasons = _normalize_slang_document(
                document, output_path, files
            )
        except (OSError, json.JSONDecodeError, SlangRunError) as error:
            message = f"Slang AST JSON is invalid: {error}"
            _write_diagnostics(diagnostics_path, completed.returncode, "invalid_ast", message)
            return _slang_run_result(command, completed.returncode, version, output_path, logs_dir, message)
        _write_diagnostics(
            diagnostics_path,
            completed.returncode,
            "succeeded",
            self.redact(completed.stderr.strip()),
        )
        return SlangRunResult(
            command,
            completed.returncode,
            version,
            output_path,
            stdout_log,
            stderr_log,
            version_log,
            command_log,
            diagnostics_path,
            modules,
            capabilities,
            unsupported,
            capability_reasons,
        )

    def analyze(
        self,
        files: tuple[Path, ...],
        output_path: Path,
        *,
        top_modules: tuple[str, ...] = (),
        include_paths: tuple[Path, ...] = (),
        defines: tuple[str, ...] = (),
        parameter_overrides: tuple[str, ...] = (),
    ) -> tuple[RTLModule, ...]:
        result = self.run(
            files,
            output_path,
            top_modules=top_modules,
            include_paths=include_paths,
            defines=defines,
            parameter_overrides=parameter_overrides,
        )
        if not result.succeeded:
            raise SlangRunError(result.error or "Slang did not produce semantic facts")
        return result.modules


def _slang_run_result(command, return_code, version, output_path, logs_dir, error):
    return SlangRunResult(
        command,
        return_code,
        version,
        output_path,
        logs_dir / "slang.stdout.log",
        logs_dir / "slang.stderr.log",
        output_path.parent / "slang-version.txt",
        output_path.parent / "slang-command.json",
        output_path.parent / "diagnostics.json",
        error=error,
    )
