"""Independent Slang execution and versioned semantic comparison artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLAssignment,
    RTLBranch,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLModule,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProceduralBlock,
    RTLProperty,
    RTLType,
    RTLTypeMember,
)

SEMANTIC_CROSSCHECK_API_VERSION = 2
SEMANTIC_CROSSCHECK_SCHEMA_VERSION = 2
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
    ) -> None:
        self.run_id = run_id
        self.primary = primary or FrontendMetadata("primary")
        self.reference = reference or FrontendMetadata(self.name)
        self.primary_capabilities = frozenset(primary_capabilities)
        self.reference_capabilities = frozenset(reference_capabilities)
        self.required_capabilities = frozenset(required_capabilities)
        self.unsupported_reasons = unsupported_reasons or {}

    def compare(
        self,
        primary: tuple[RTLModule, ...],
        reference: tuple[RTLModule, ...],
    ) -> SemanticCrossCheckResult:
        issues: list[SemanticCrossCheckIssue] = []
        checked: list[str] = []
        coverage: list[CapabilityCoverage] = []
        unsupported: list[str] = []
        for capability in COMPARABLE_CAPABILITIES:
            required = capability in self.required_capabilities
            if capability not in self.primary_capabilities:
                status = "missing_primary"
            elif capability not in self.reference_capabilities:
                status = "unsupported"
            else:
                status = "checked"
            reason = self.unsupported_reasons.get(capability)
            coverage.append(CapabilityCoverage(capability, status, required, reason))
            if status != "checked":
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
            return SlangRunResult(
                command,
                None,
                version,
                output_path,
                stdout_log,
                stderr_log,
                version_log,
                command_log,
                diagnostics_path,
                error=message,
            )
        atomic_write_text(stdout_log, self.redact(completed.stdout))
        atomic_write_text(stderr_log, self.redact(completed.stderr))
        if completed.returncode != 0 or not output_path.is_file():
            message = self.redact(completed.stderr.strip() or completed.stdout.strip() or "Slang AST output missing")
            _write_diagnostics(diagnostics_path, completed.returncode, "compilation_failed", message)
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
                error=message,
            )
        try:
            document = json.loads(output_path.read_text(encoding="utf-8"))
            modules, capabilities, unsupported, capability_reasons = _normalize_slang_document(
                document, output_path, files
            )
        except (OSError, json.JSONDecodeError, SlangRunError) as error:
            message = f"Slang AST JSON is invalid: {error}"
            _write_diagnostics(diagnostics_path, completed.returncode, "invalid_ast", message)
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
                error=message,
            )
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


def unavailable_crosscheck_result(
    run_id: str,
    primary: FrontendMetadata,
    reference: FrontendMetadata,
    error: str,
) -> SemanticCrossCheckResult:
    """Create the same schema for execution failures as for disagreements."""

    issue = SemanticCrossCheckIssue(
        "*",
        "frontend",
        "available",
        error,
        capability=CAPABILITY_DESIGN_UNITS,
    )
    return SemanticCrossCheckResult(
        primary.name,
        reference.name,
        (),
        (issue,),
        run_id=run_id,
        status="unavailable",
        primary=primary,
        reference=reference,
        capabilities=tuple(
            CapabilityCoverage(item, "unsupported", item in CORE_REQUIRED_CAPABILITIES, error)
            for item in COMPARABLE_CAPABILITIES
        ),
        unsupported_capabilities=COMPARABLE_CAPABILITIES,
    )


def aggregate_crosscheck_results(
    results: tuple[SemanticCrossCheckResult, ...],
) -> SemanticCrossCheckResult:
    """Combine independently checked elaboration points without hiding a failed run."""

    if not results:
        raise ValueError("At least one semantic cross-check result is required")
    capabilities: list[CapabilityCoverage] = []
    for capability in COMPARABLE_CAPABILITIES:
        entries = tuple(item for result in results for item in result.capabilities if item.capability == capability)
        statuses = {item.status for item in entries}
        capabilities.append(
            CapabilityCoverage(
                capability,
                "checked" if statuses == {"checked"} else "unsupported",
                any(item.required for item in entries),
                "; ".join(sorted({item.reason for item in entries if item.reason})) or None,
            )
        )
    issues = tuple(issue for result in results for issue in result.issues)
    status = "passed" if all(result.passed for result in results) else "failed"
    if any(result.status == "unavailable" for result in results):
        status = "unavailable"
    first = results[0]
    return SemanticCrossCheckResult(
        first.primary_name,
        first.reference_name,
        tuple(module for result in results for module in result.checked_modules),
        issues,
        run_id="aggregate",
        status=status,
        primary=first.primary,
        reference=first.reference,
        capabilities=tuple(capabilities),
        unsupported_capabilities=tuple(
            sorted({capability for result in results for capability in result.unsupported_capabilities})
        ),
    )


def classify_slang_version(version: str | None) -> dict[str, str | int | None]:
    """Classify Slang against the qualified major-version compatibility window."""

    match = re.search(r"(?:slang\s+)?(\d+)(?:\.\d+)?", version or "", re.IGNORECASE)
    major = int(match.group(1)) if match else None
    status = (
        "supported"
        if major is not None and SLANG_MIN_TESTED_MAJOR <= major <= SLANG_MAX_TESTED_MAJOR
        else "unsupported"
    )
    return {
        "status": status,
        "major": major,
        "min_tested_major": SLANG_MIN_TESTED_MAJOR,
        "max_tested_major": SLANG_MAX_TESTED_MAJOR,
    }


def benchmark_slang_normalization(document: object) -> SlangNormalizationBenchmark:
    """Normalize a document while measuring the Stage 7 runtime / memory budget."""

    import time
    import tracemalloc

    nodes = sum(1 for _ in _walk_json_objects(document))
    tracemalloc.start()
    started = time.perf_counter()
    modules = _normalize_slang_document(document)[0]
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return SlangNormalizationBenchmark(nodes, elapsed, peak, len(modules))


def capabilities_for_modules(modules: tuple[RTLModule, ...]) -> tuple[str, ...]:
    """Return the Verilator normalizer's declared comparison profile.

    Capability support is independent of whether a particular design contains a
    construct.  Treating an empty fact list as an unsupported capability made it
    impossible to distinguish "there are no properties" from "properties were
    dropped by the mapper".
    """

    del modules
    return COMPARABLE_CAPABILITIES


def required_capabilities_for_modules(modules: tuple[RTLModule, ...]) -> tuple[str, ...]:
    """Require the qualified semantic profile for an enabled cross-check."""

    del modules
    return COMPARABLE_CAPABILITIES


def write_crosscheck_result(path: Path, result: SemanticCrossCheckResult) -> Path:
    """Persist a stable semantic cross-check result artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": result.schema_version,
        "api_version": SEMANTIC_CROSSCHECK_API_VERSION,
        "run_id": result.run_id,
        "status": result.status,
        "passed": result.passed,
        "primary_name": result.primary_name,
        "reference_name": result.reference_name,
        "primary": _frontend_json(result.primary),
        "reference": _frontend_json(result.reference),
        "checked_modules": list(result.checked_modules),
        "capabilities": [
            {
                "capability": item.capability,
                "status": item.status,
                "required": item.required,
                "reason": item.reason,
            }
            for item in result.capabilities
        ],
        "unsupported_capabilities": list(result.unsupported_capabilities),
        "issues": [_issue_json(issue) for issue in result.issues],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _write_diagnostics(path: Path, return_code: int | None, status: str, text: str) -> None:
    atomic_write_text(
        path,
        json.dumps(
            {"schema_version": 1, "status": status, "return_code": return_code, "diagnostics": text},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def _frontend_json(value: FrontendMetadata | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "name": value.name,
        "version": value.version,
        "command": list(value.command),
        "artifact_path": value.artifact_path,
    }


def _issue_json(issue: SemanticCrossCheckIssue) -> dict[str, object]:
    return {
        "module": issue.module,
        "specialization": issue.specialization,
        "capability": issue.capability,
        "field": issue.field,
        "primary": issue.primary,
        "reference": issue.reference,
        "severity": issue.severity,
        "primary_location": issue.primary_location,
        "reference_location": issue.reference_location,
        "primary_evidence": [_evidence_json(item) for item in issue.primary_evidence],
        "reference_evidence": [_evidence_json(item) for item in issue.reference_evidence],
    }


def _evidence_json(value: EvidenceRef) -> dict[str, str | None]:
    return {
        "kind": value.kind.value,
        "source_id": value.source_id,
        "locator": value.locator,
        "summary": value.summary,
    }


def _normalize_slang_document(
    document: object,
    ast_path: Path | None = None,
    source_files: tuple[Path, ...] = (),
) -> tuple[
    tuple[RTLModule, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str], ...],
]:
    if not isinstance(document, dict) or not isinstance(document.get("design"), dict):
        raise SlangRunError("Slang AST JSON does not contain a design object")
    modules: list[RTLModule] = []
    gaps: dict[str, set[str]] = {}
    symbol_index = _slang_symbol_index(document["design"])
    interface_array_ranges = _slang_instance_array_ranges(document["design"])
    global_types = _slang_global_types(document["design"], symbol_index)
    source_generate_scopes = _slang_source_generate_scopes(source_files)
    seen_bodies: set[tuple[str, str]] = set()
    for body in _walk_json_objects(document["design"]):
        if body.get("kind") != "InstanceBody" or not body.get("name"):
            continue
        name = str(body["name"])
        original_name = _slang_original_name(body)
        members = _json_dicts(body.get("members"))
        parameters = tuple(_slang_parameter(item) for item in members if item.get("kind") == "Parameter")
        body_key = (original_name, _specialization_from_parameters(parameters))
        if body_key in seen_bodies:
            continue
        seen_bodies.add(body_key)
        ports = tuple(_slang_port(item, interface_array_ranges) for item in members if _is_slang_port(item))
        parameter_names = {parameter.name for parameter in parameters}
        instances = _slang_instances_with_paths(members, symbol_index)
        continuous_assignments = tuple(
            _slang_assignment(item, parameter_names) for item in members if item.get("kind") == "ContinuousAssign"
        )
        procedure_nodes = tuple(item for item in members if item.get("kind") == "ProceduralBlock")
        procedures = tuple(_slang_procedure(item) for item in procedure_nodes)
        procedural_assignments = tuple(
            assignment
            for procedure in procedure_nodes
            for assignment in _slang_procedural_assignments(procedure, parameter_names)
        )
        assignments = (*continuous_assignments, *procedural_assignments)
        properties = _slang_properties(members)
        imports = _slang_imports(members)
        referenced_interfaces = {port.interface_name for port in ports if port.interface_name is not None}
        types = tuple(_slang_type(item, symbol_index) for item in members if _is_slang_type(item)) + tuple(
            item for item in global_types if item.package_name in imports or item.package_name in referenced_interfaces
        )
        memories = tuple(_slang_memory(item, symbol_index) for item in members if _is_slang_memory(item))
        generate_scopes = _merge_slang_generate_scopes(
            _slang_generate_scopes(members), source_generate_scopes.get(original_name, ())
        )
        expressions = tuple(expression for item in assignments for expression in item.expressions) + tuple(
            expression for item in procedures for expression in item.expressions
        )
        branches = tuple(branch for item in procedures for branch in item.branches)
        domains = tuple(
            domain
            for node, block in zip(procedure_nodes, procedures, strict=True)
            if (domain := _slang_control_domain(node, block)) is not None
        )
        ast_ref = EvidenceRef(
            EvidenceKind.SLANG_AST,
            str(ast_path or body.get("source_file") or "slang-ast"),
            _slang_source_location(body) or name,
            f"Slang instance body {original_name}",
        )
        specialization_id = _canonical_specialization_id(original_name, parameters)
        memory_accesses = _slang_memory_accesses(members, memories, domains)
        memories = tuple(
            replace(
                memory,
                read_during_write=(
                    "not_applicable"
                    if not any(item.memory == memory.name and item.kind == "write" for item in memory_accesses)
                    else "unknown"
                ),
            )
            for memory in memories
        )
        modules.append(
            RTLModule(
                name=name,
                original_name=original_name,
                elaborated_name=name,
                specialization_id=specialization_id,
                source=Path(str(body["source_file"])) if body.get("source_file") else None,
                ports=tuple(port.name for port in ports),
                port_details=ports,
                parameters=tuple(parameter.name for parameter in parameters),
                parameter_details=parameters,
                type_details=types,
                memories=memories,
                memory_accesses=memory_accesses,
                instances=tuple(f"{item.name}:{item.module_name}" for item in instances),
                instance_details=instances,
                continuous_assignments=tuple(
                    _slang_summary(item) for item in members if item.get("kind") == "ContinuousAssign"
                ),
                assignment_details=assignments,
                procedural_blocks=tuple(item.kind for item in procedures),
                procedural_block_details=procedures,
                control_domains=domains,
                assertions=tuple(item.name or item.kind for item in properties if item.kind != "cover"),
                covers=tuple(item.name or item.kind for item in properties if item.kind == "cover"),
                property_details=properties,
                generate_scopes=generate_scopes,
                imports=imports,
                ast_refs=(ast_ref,),
            )
        )
        _collect_slang_capability_gaps(members, gaps)
        if expressions and any(
            expression.kind == "unsupported" for root in expressions for expression in _walk_expressions(root)
        ):
            _add_gap(gaps, CAPABILITY_EXPRESSIONS, "an expression node could not be normalized")
        if branches and any(branch.condition is None and not branch.is_default for branch in branches):
            _add_gap(gaps, CAPABILITY_BRANCHES, "a branch condition could not be normalized")
        if any(item.condition is not None and item.condition.kind == "unsupported" for item in generate_scopes):
            _add_gap(
                gaps,
                CAPABILITY_GENERATE_SCOPES,
                "a source generate condition could not be normalized",
            )
        for prop in properties:
            if prop.support_status != "normalized":
                _add_gap(
                    gaps,
                    CAPABILITY_PROPERTIES,
                    f"{prop.source_location or prop.name or 'property'}: unsupported operators "
                    + ", ".join(prop.unsupported_operators),
                )
    if not modules:
        raise SlangRunError("Slang AST JSON contains no instance bodies")
    module_tuple = tuple(modules)
    capabilities = set(COMPARABLE_CAPABILITIES) - set(gaps)
    unsupported = tuple(item for item in COMPARABLE_CAPABILITIES if item not in capabilities)
    reasons = tuple(
        (capability, "; ".join(sorted(gaps[capability])))
        for capability in COMPARABLE_CAPABILITIES
        if capability in gaps
    )
    return (
        module_tuple,
        tuple(item for item in COMPARABLE_CAPABILITIES if item in capabilities),
        unsupported,
        reasons,
    )


def _modules_from_slang_json(document: object) -> tuple[RTLModule, ...]:
    """Compatibility wrapper used by unit tests and adapter clients."""

    return _normalize_slang_document(document)[0]


def _walk_json_objects(value: object) -> Iterator[dict[str, Any]]:
    """Iterate a large Slang document without recursive tuple materialization."""

    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(reversed(tuple(current.values())))
        elif isinstance(current, (list, tuple)):
            stack.extend(reversed(current))


def _json_dicts(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _slang_original_name(body: dict[str, Any]) -> str:
    for key in ("definitionName", "originalName", "definition", "moduleName"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return _canonical_symbol_name(value)
        if isinstance(value, dict) and value.get("name"):
            return str(value["name"])
    return str(body["name"])


def _specialization_from_parameters(parameters: tuple[RTLParameter, ...]) -> str:
    values = tuple(
        sorted((item.name, _canonical_constant(item.default_value)) for item in parameters if not item.local)
    )
    return repr(values)


def _slang_symbol_index(value: object) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for node in _walk_json_objects(value):
        address = node.get("addr")
        if address is not None:
            index[str(address)] = node
    return index


def _slang_instance_array_ranges(value: object) -> dict[str, tuple[str, ...]]:
    found: dict[str, set[str]] = {}
    for node in _walk_json_objects(value):
        if node.get("kind") != "InstanceArray" or not node.get("name") or not node.get("range"):
            continue
        found.setdefault(str(node["name"]), set()).add(str(node["range"]))
    return {
        name: tuple(_canonical_range(value) or value for value in sorted(ranges))
        for name, ranges in found.items()
        if len(ranges) == 1
    }


def _slang_link(value: object, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    return index.get(value.strip().split(" ", 1)[0])


def _is_slang_port(value: object) -> bool:
    return isinstance(value, dict) and value.get("kind") in {"Port", "InterfacePort"} and bool(value.get("name"))


def _is_slang_instance(value: dict[str, Any]) -> bool:
    return value.get("kind") == "Instance" and bool(value.get("name")) and value.get("body") is not None


def _slang_instance(value: dict[str, Any], symbol_index: dict[str, dict[str, Any]]) -> RTLInstance:
    body = _slang_link(value["body"], symbol_index)
    body_name = (
        str(body.get("name")) if body is not None and body.get("name") else _canonical_symbol_name(str(value["body"]))
    )
    body_members = _json_dicts(body.get("members")) if body is not None else ()
    bindings = tuple(
        RTLParameterBinding(str(item.get("name")), _canonical_constant(item.get("value")))
        for item in body_members
        if item.get("kind") == "Parameter" and item.get("name") and not item.get("isLocal")
    )
    if not bindings:
        bindings = tuple(
            RTLParameterBinding(str(item.get("name")), _canonical_constant(item.get("value")))
            for item in _json_dicts(value.get("parameters") or value.get("parameterAssignments"))
            if item.get("name")
        )
    connections = tuple(
        RTLConnection(
            port_name=_slang_connection_port(item),
            direction=_slang_connection_direction(item),
            signal_refs=_slang_signal_refs(_slang_connection_expression(item)),
            expression=_slang_expression(_slang_connection_expression(item)),
            source_location=_slang_source_location(item),
        )
        for item in _json_dicts(value.get("connections"))
    )
    module_name = _slang_original_name(body) if body is not None and body.get("name") else body_name
    return RTLInstance(
        name=str(value["name"]),
        module_name=module_name,
        elaborated_module_name=body_name,
        specialization_id=_canonical_specialization_id(
            module_name or "unknown",
            tuple(RTLParameter(binding.name, binding.value) for binding in bindings),
        ),
        parameter_bindings=bindings,
        source_location=_slang_source_location(value),
        connections=connections,
    )


def _slang_instances_with_paths(
    members: tuple[dict[str, Any], ...], symbol_index: dict[str, dict[str, Any]]
) -> tuple[RTLInstance, ...]:
    result: list[RTLInstance] = []

    def visit(items: tuple[dict[str, Any], ...], scope: str = "") -> None:
        for item in items:
            kind = str(item.get("kind", ""))
            if kind == "Instance" and _is_slang_instance(item):
                instance = _slang_instance(item, symbol_index)
                result.append(replace(instance, name=f"{scope}.{instance.name}" if scope else instance.name))
                continue
            if kind == "GenerateBlockArray":
                base = str(item.get("name") or "generate")
                for block in _json_dicts(item.get("members")):
                    if block.get("kind") != "GenerateBlock":
                        continue
                    index = _slang_generate_index(block)
                    child_scope = f"{base}[{index}]" if index is not None else base
                    visit(_json_dicts(block.get("members")), child_scope)
                continue
            if kind == "GenerateBlock":
                base = str(item.get("name") or item.get("branchKind") or "generate")
                child_scope = f"{scope}.{base}" if scope else base
                visit(_json_dicts(item.get("members")), child_scope)

    visit(members)
    return tuple(result)


def _slang_connection_port(value: dict[str, Any]) -> str:
    port = value.get("port") or value.get("name")
    if isinstance(port, dict):
        return str(port.get("name") or "")
    return _canonical_symbol_name(str(port)) if port is not None else ""


def _slang_connection_direction(value: dict[str, Any]) -> str | None:
    port = value.get("port")
    if not isinstance(port, dict):
        return None
    return {"In": "input", "Out": "output", "InOut": "inout", "Ref": "ref"}.get(str(port.get("direction")))


def _slang_connection_expression(value: dict[str, Any]) -> object:
    expression = value.get("expr") or value.get("expression") or value.get("value")
    port = value.get("port")
    if (
        isinstance(expression, dict)
        and expression.get("kind") == "Assignment"
        and isinstance(port, dict)
        and port.get("direction") == "Out"
    ):
        return expression.get("left")
    return expression


def _slang_summary(value: dict[str, Any]) -> str:
    return str(value.get("kind", "unknown"))


def _slang_source_location(value: dict[str, Any]) -> str | None:
    source = (
        value.get("source_file")
        or value.get("sourceFile")
        or value.get("source_file_start")
        or value.get("sourceFileStart")
    )
    if source is None:
        return None
    line = value.get(
        "source_line", value.get("sourceLine", value.get("source_line_start", value.get("sourceLineStart", "?")))
    )
    column = value.get(
        "source_column",
        value.get("sourceColumn", value.get("source_column_start", value.get("sourceColumnStart", "?"))),
    )
    return f"{source}:{line}:{column}"


def _slang_procedure_kind(value: dict[str, Any]) -> str:
    return _canonical_operation(str(value.get("procedureKind", "procedural")))


def _slang_procedure(value: dict[str, Any]) -> RTLProceduralBlock:
    kind = _slang_procedure_kind(value)
    body = value.get("body") or value.get("statement") or value
    expressions = tuple(
        expression
        for node in _walk_json_objects(body)
        if _is_expression_node(node) and (expression := _slang_expression(node)) is not None
    )
    branches = _slang_branches(body)
    refs = tuple(sorted(set(_slang_signal_refs(body))))
    return RTLProceduralBlock(
        kind=kind,
        name=str(value["name"]) if value.get("name") else None,
        source_location=_slang_source_location(value),
        summary=kind,
        signal_refs=refs,
        expressions=_dedupe_expressions(expressions),
        branches=branches,
    )


def _slang_assignment(value: dict[str, Any], parameter_names: set[str]) -> RTLAssignment:
    assignment = value.get("assignment") or value.get("expression")
    left = assignment.get("left") if isinstance(assignment, dict) else None
    right = assignment.get("right") if isinstance(assignment, dict) else None
    lhs_refs = tuple(ref for ref in _slang_written_refs(left) if ref not in parameter_names)
    rhs_refs = tuple(ref for ref in _slang_signal_refs(right) if ref not in parameter_names)
    expressions = tuple(item for item in (_slang_expression(right), _slang_expression(left)) if item is not None)
    return RTLAssignment(
        kind="continuous",
        name=str(value["name"]) if value.get("name") else None,
        source_location=_slang_source_location(value),
        summary="ContinuousAssign",
        lhs_signals=lhs_refs,
        rhs_signals=rhs_refs,
        expressions=expressions,
    )


def _slang_procedural_assignments(
    value: dict[str, Any],
    parameter_names: set[str],
) -> tuple[RTLAssignment, ...]:
    assignments: list[RTLAssignment] = []
    for node in _walk_json_objects(value.get("body") or value):
        kind = str(node.get("kind", "")).lower()
        if kind not in {"assignment", "assignmentexpression", "nonblockingassignment"}:
            continue
        left = node.get("left") or node.get("lhs")
        right = node.get("right") or node.get("rhs")
        expressions = tuple(item for raw in (right, left) if (item := _slang_expression(raw)) is not None)
        assignments.append(
            RTLAssignment(
                kind="nonblocking" if "nonblocking" in kind or node.get("isNonBlocking") else "procedural",
                source_location=_slang_source_location(node),
                summary=str(node.get("kind")),
                lhs_signals=tuple(ref for ref in _slang_written_refs(left) if ref not in parameter_names),
                rhs_signals=tuple(ref for ref in _slang_signal_refs(right) if ref not in parameter_names),
                expressions=expressions,
            )
        )
    return tuple(assignments)


def _slang_signal_refs(value: object) -> tuple[str, ...]:
    refs: list[str] = []
    for item in _walk_json_objects(value):
        if item.get("kind") not in {"NamedValue", "HierarchicalValue", "MemberAccess"}:
            continue
        if item.get("constant") is not None:
            continue
        symbol = item.get("symbol") or item.get("name") or item.get("member")
        if not isinstance(symbol, str):
            continue
        name = _canonical_symbol_name(symbol)
        if name and name not in refs:
            refs.append(name)
    return tuple(refs)


def _slang_written_refs(value: object) -> tuple[str, ...]:
    if isinstance(value, dict) and value.get("kind") in {"ElementSelect", "RangeSelect", "MemberAccess"}:
        return _slang_signal_refs(value.get("value") or value.get("base"))[:1]
    return _slang_signal_refs(value)[:1]


def _slang_port(value: dict[str, Any], interface_array_ranges: dict[str, tuple[str, ...]] | None = None) -> RTLPort:
    if value.get("kind") == "InterfacePort":
        return RTLPort(
            name=str(value["name"]),
            direction="interface",
            data_type="interface",
            source_location=_slang_source_location(value),
            interface_name=_canonical_symbol_name(str(value.get("interfaceDef") or "")) or None,
            modport=str(value.get("modport")) if value.get("modport") else None,
            interface_direction="modport",
            unpacked_dimensions=(interface_array_ranges or {}).get(str(value["name"]), ()),
        )
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    type_kind = str(type_data.get("kind", ""))
    range_text = _type_range(type_data)
    interface = type_data.get("interface") or type_data.get("definition")
    modport = type_data.get("modport")
    return RTLPort(
        name=str(value["name"]),
        direction={"In": "input", "Out": "output", "InOut": "inout", "Ref": "ref"}.get(
            str(value.get("direction")), "unknown"
        ),
        data_type=type_kind,
        width=_type_width(type_data),
        signed=_type_signed(type_data),
        packed_range=range_text,
        source_location=_slang_source_location(value),
        interface_name=str(interface) if interface is not None else None,
        modport=str(modport) if modport is not None else None,
        interface_direction=str(value.get("direction")) if interface is not None else None,
        packed_dimensions=_type_dimensions(type_data, "packed"),
        unpacked_dimensions=_type_dimensions(type_data, "unpacked"),
    )


def _slang_parameter(value: dict[str, Any]) -> RTLParameter:
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    return RTLParameter(
        name=str(value["name"]),
        default_value=_canonical_constant(
            value.get("value") if value.get("value") is not None else _expression_constant(value.get("initializer"))
        ),
        data_type=str(type_data.get("kind")) if type_data.get("kind") is not None else None,
        width=_type_width(type_data),
        signed=_type_signed(type_data),
        local=bool(value.get("isLocal", False)),
        source_location=_slang_source_location(value),
    )


def _is_slang_type(value: dict[str, Any]) -> bool:
    return str(value.get("kind", "")) in {
        "TypeAlias",
        "Typedef",
        "EnumType",
        "StructType",
        "UnionType",
        "PackedStructType",
        "PackedUnionType",
    }


def _slang_type(value: dict[str, Any], symbol_index: dict[str, dict[str, Any]] | None = None) -> RTLType:
    raw_type = value.get("type") or value.get("target")
    resolved = _slang_link(raw_type, symbol_index or {}) if raw_type is not None else None
    type_data: dict[str, Any] = resolved if resolved is not None else value
    members = tuple(_json_dicts(type_data.get("members")))
    type_id = str(value.get("id") or value.get("name") or hashlib.sha256(repr(value).encode()).hexdigest()[:12])
    member_details = tuple(
        RTLTypeMember(
            name=str(item.get("name")),
            width=_resolved_slang_type_width(item.get("type"), symbol_index or {}),
            signed=_type_signed(_resolve_slang_type(item.get("type"), symbol_index or {})),
            packed_range=_type_range(_resolve_slang_type(item.get("type"), symbol_index or {})),
            bit_offset=int(item["bitOffset"]) if item.get("bitOffset") is not None else None,
            packed_dimensions=_type_dimensions(_resolve_slang_type(item.get("type"), symbol_index or {}), "packed"),
            unpacked_dimensions=_type_dimensions(_resolve_slang_type(item.get("type"), symbol_index or {}), "unpacked"),
            source_location=_slang_source_location(item),
        )
        for item in members
        if item.get("name") and item.get("kind") != "EnumValue"
    )
    type_width = _type_width(type_data)
    if type_width is None and member_details and all(item.width is not None for item in member_details):
        widths = tuple(item.width for item in member_details if item.width is not None)
        type_width = max(widths) if "Union" in str(type_data.get("kind")) else sum(widths)
    return RTLType(
        type_id=type_id,
        name=str(value.get("name")) if value.get("name") else None,
        kind=_canonical_operation(str(type_data.get("kind", value.get("kind", "type")))),
        width=type_width,
        signed=_type_signed(type_data),
        members=tuple(
            str(item.get("name")) for item in members if item.get("name") and item.get("kind") != "EnumValue"
        ),
        enum_values=tuple(
            str(item.get("name"))
            for item in _json_dicts(type_data.get("values") or type_data.get("members"))
            if item.get("kind") == "EnumValue" and item.get("name")
        ),
        source_location=_slang_source_location(value),
        member_details=member_details,
        packed_dimensions=_type_dimensions(type_data, "packed"),
        unpacked_dimensions=_type_dimensions(type_data, "unpacked"),
        package_name=str(value.get("package")) if value.get("package") else None,
    )


def _slang_global_types(value: object, symbol_index: dict[str, dict[str, Any]]) -> tuple[RTLType, ...]:
    result: list[RTLType] = []
    for owner in _walk_json_objects(value):
        owner_kind = str(owner.get("kind", ""))
        if owner_kind not in {"Package", "InstanceBody"}:
            continue
        owner_name = str(owner.get("name") or "")
        owner_members = _json_dicts(owner.get("members"))
        aliases = {str(item.get("name")) for item in owner_members if item.get("kind") in {"TypeAlias", "Typedef"}}
        for member in owner_members:
            if _is_slang_type(member):
                if (
                    member.get("kind") in {"EnumType", "PackedStructType", "PackedUnionType"}
                    and str(member.get("name")) in aliases
                ):
                    continue
                item = _slang_type(member, symbol_index)
                result.append(
                    RTLType(
                        **{
                            **item.__dict__,
                            "package_name": owner_name or item.package_name,
                        }
                    )
                )
            elif member.get("kind") == "Modport":
                modport_members = tuple(
                    RTLTypeMember(
                        name=str(port.get("name")),
                        width=_type_width(port.get("type")),
                        signed=_type_signed(port.get("type")),
                        packed_range=_type_range(port.get("type")),
                        bit_offset=(int(port["bitOffset"]) if port.get("bitOffset") is not None else None),
                        packed_dimensions=_type_dimensions(port.get("type"), "packed"),
                        unpacked_dimensions=_type_dimensions(port.get("type"), "unpacked"),
                        source_location=_slang_source_location(port),
                    )
                    for port in _json_dicts(member.get("members"))
                    if port.get("kind") == "ModportPort" and port.get("name")
                )
                directions = tuple(
                    f"{port.get('name')}:{str(port.get('direction', '')).lower()}"
                    for port in _json_dicts(member.get("members"))
                    if port.get("kind") == "ModportPort" and port.get("name")
                )
                result.append(
                    RTLType(
                        type_id=f"{owner_name}.{member.get('name')}",
                        name=str(member.get("name")),
                        kind="modport",
                        members=directions,
                        member_details=modport_members,
                        source_location=_slang_source_location(member),
                        package_name=owner_name,
                    )
                )
    return tuple(result)


def _resolve_slang_type(value: object, symbol_index: dict[str, dict[str, Any]]) -> object:
    linked = _slang_link(value, symbol_index)
    if linked is None:
        return value
    if linked.get("kind") in {"TypeAlias", "Typedef"}:
        return _resolve_slang_type(linked.get("target") or linked.get("type"), symbol_index)
    if linked.get("kind") == "EnumType" and isinstance(linked.get("baseType"), dict):
        return linked.get("baseType")
    return linked


def _resolved_slang_type_width(value: object, symbol_index: dict[str, dict[str, Any]]) -> int | None:
    resolved = _resolve_slang_type(value, symbol_index)
    if not isinstance(resolved, dict):
        return _type_width(resolved)
    kind = str(resolved.get("kind", ""))
    if kind == "EnumType":
        return _resolved_slang_type_width(resolved.get("baseType"), symbol_index)
    if kind in {"PackedStructType", "StructType", "PackedUnionType", "UnionType"}:
        widths = tuple(
            _resolved_slang_type_width(item.get("type"), symbol_index)
            for item in _json_dicts(resolved.get("members"))
            if item.get("kind") != "EnumValue"
        )
        if any(item is None for item in widths):
            return None
        known = tuple(item for item in widths if item is not None)
        return max(known, default=0) if "Union" in kind else sum(known)
    return _type_width(resolved)


def _slang_imports(members: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _canonical_symbol_name(str(item.get("package")))
                for item in members
                if item.get("kind") in {"Import", "WildcardImport"} and item.get("package")
            }
        )
    )


def _is_slang_memory(value: dict[str, Any]) -> bool:
    return value.get("kind") in {"Variable", "Net"} and bool(_type_dimensions(value.get("type"), "unpacked"))


def _slang_memory(value: dict[str, Any], symbol_index: dict[str, dict[str, Any]] | None = None) -> RTLMemory:
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    dimensions = _type_dimensions(type_data, "unpacked")
    depths = tuple(_range_width(item) for item in dimensions)
    depth = (
        None if any(item is None for item in depths) else _product(tuple(item for item in depths if item is not None))
    )
    element_width = _resolved_slang_type_width(_slang_memory_element_type(type_data), symbol_index or {})
    return RTLMemory(
        name=str(value.get("name")),
        element_width=element_width,
        depth=depth,
        address_width=(depth - 1).bit_length() if depth and depth > 1 else 1,
        source_location=_slang_source_location(value),
        unpacked_dimensions=dimensions,
    )


def _slang_memory_element_type(value: object) -> object:
    current = value
    while isinstance(current, dict) and str(current.get("kind")) in {
        "FixedSizeUnpackedArrayType",
        "UnpackedArrayType",
    }:
        current = current.get("elementType")
    return current


def _slang_memory_accesses(
    members: tuple[dict[str, Any], ...],
    memories: tuple[RTLMemory, ...],
    domains: tuple[RTLControlDomain, ...],
) -> tuple[RTLMemoryAccess, ...]:
    memory_names = {item.name for item in memories}
    result: list[RTLMemoryAccess] = []

    def record(node: dict[str, Any], synchronous: bool, enables: tuple[str, ...]) -> None:
        left = node.get("left")
        right = node.get("right")
        left_memory = _selected_memory(left, memory_names)
        right_memory = _selected_memory(right, memory_names)
        for kind, memory, selected, data in (
            ("write", left_memory, left, right),
            ("read", right_memory, right, left),
        ):
            if memory is None:
                continue
            address = _slang_select_address(selected)
            refs = tuple(ref for ref in _slang_signal_refs(data) if ref != memory)
            location = _slang_source_location(node)
            result.append(
                RTLMemoryAccess(
                    access_id=f"{memory}:{kind}:{location or len(result)}",
                    memory=memory,
                    kind=kind,
                    address_signals=_slang_signal_refs(address),
                    data_signals=refs,
                    enable_signals=enables,
                    domain_id=domains[0].domain_id if synchronous and domains else None,
                    synchronous=synchronous,
                    source_location=location,
                )
            )

    def visit(value: object, synchronous: bool, enables: tuple[str, ...] = ()) -> None:
        if isinstance(value, list | tuple):
            for child in value:
                visit(child, synchronous, enables)
            return
        if not isinstance(value, dict):
            return
        kind = str(value.get("kind", ""))
        if kind == "Assignment":
            record(value, synchronous, enables)
            return
        if kind == "Conditional":
            conditions = _json_dicts(value.get("conditions"))
            condition_refs = tuple(
                dict.fromkeys(
                    ref for condition in conditions for ref in _slang_signal_refs(condition.get("expr") or condition)
                )
            )
            nested_enables = tuple(dict.fromkeys((*enables, *condition_refs)))
            for key in ("ifTrue", "ifFalse"):
                visit(value.get(key), synchronous, nested_enables)
            return
        for child in value.values():
            visit(child, synchronous, enables)

    for member in members:
        if member.get("kind") == "ProceduralBlock":
            visit(member.get("body"), True)
        elif member.get("kind") == "ContinuousAssign":
            visit(member.get("assignment"), False)
    return tuple(result)


def _selected_memory(value: object, names: set[str]) -> str | None:
    if not isinstance(value, dict) or value.get("kind") not in {"ElementSelect", "RangeSelect"}:
        return None
    refs = _slang_signal_refs(value.get("value") or value.get("base"))
    return next((item for item in refs if item in names), None)


def _slang_select_address(value: object) -> object:
    if not isinstance(value, dict):
        return None
    return value.get("selector") or value.get("index") or value.get("left")


def _slang_expression(value: object) -> RTLExpression | None:
    if not isinstance(value, dict):
        return None
    raw_kind = str(value.get("kind", "unsupported"))
    kind = _canonical_operation(str(value.get("op") or raw_kind))
    if raw_kind in {"Conversion", "ConversionExpression", "Cast"}:
        kind = "cast"
    elif raw_kind in {"ConditionalOp", "ConditionalExpression"}:
        kind = "cond"
    elif raw_kind in {"NamedValue", "HierarchicalValue", "MemberAccess"}:
        kind = "ref" if raw_kind != "MemberAccess" else "member"
    elif raw_kind.endswith("Literal"):
        kind = "literal"
    type_data = value.get("type") if isinstance(value.get("type"), dict) else {}
    assert isinstance(type_data, dict)
    child_values: list[object] = []
    for key in (
        "operand",
        "left",
        "right",
        "predicate",
        "condition",
        "expr",
        "trueExpr",
        "falseExpr",
        "value",
        "selector",
        "base",
        "index",
    ):
        child = value.get(key)
        if isinstance(child, dict):
            child_values.append(child)
    for key in ("operands", "elements", "parts", "arguments", "conditions"):
        for child in _json_dicts(value.get(key)):
            child_values.append(child.get("expr") or child.get("sequence") or child)
    children = tuple(item for child in child_values if (item := _slang_expression(child)) is not None)
    literal = value.get("constant")
    if literal is None and raw_kind.lower().endswith("literal"):
        literal = value.get("value")
    symbol = value.get("symbol") or value.get("name") or value.get("member")
    if raw_kind in {"NamedValue", "HierarchicalValue"} and value.get("constant") is not None:
        kind = "literal"
        symbol = None
        literal = value.get("constant")
    if raw_kind == "SequenceConcat":
        children = tuple(
            RTLExpression(
                kind="delay",
                value=f"{item.get('min')}:{item.get('max')}",
                source_location=_slang_source_location(item.get("sequence") or item),
                children=tuple(
                    expression for expression in (_slang_expression(item.get("sequence")),) if expression is not None
                ),
            )
            for item in _json_dicts(value.get("elements"))
        )
    return RTLExpression(
        kind=kind,
        name=_canonical_symbol_name(str(symbol)) if symbol is not None else None,
        value=_canonical_constant(literal),
        source_location=_slang_source_location(value),
        children=children,
        width=_type_width(type_data),
        signed=_type_signed(type_data) if type_data else None,
        cast_kind=(
            str(value.get("conversionKind") or value.get("castKind") or type_data.get("name") or "implicit")
            if kind == "cast"
            else None
        ),
        packed_range=_type_range(type_data),
    )


def _slang_branches(value: object) -> tuple[RTLBranch, ...]:
    branches: list[RTLBranch] = []
    for node in _walk_json_objects(value):
        kind = str(node.get("kind", "")).lower()
        if kind in {"if", "ifstatement", "conditionalstatement", "conditional"}:
            conditions = _json_dicts(node.get("conditions"))
            condition_value = (
                conditions[0].get("expr") if conditions else node.get("condition") or node.get("predicate")
            )
            branches.append(
                RTLBranch(
                    "if",
                    _slang_source_location(node),
                    _slang_expression(condition_value),
                    mutually_exclusive=True,
                )
            )
        elif kind in {"case", "casestatement", "casez", "casex"}:
            condition = str(node.get("condition", "Normal"))
            case_kind = {
                "Normal": "case",
                "WildcardJustZ": "casez",
                "WildcardXOrZ": "casex",
                "Inside": "caseinside",
            }.get(condition, str(node.get("caseKind", kind)).lower())
            exclusive = True if case_kind == "case" or node.get("unique") or node.get("priority") else None
            selector = _slang_expression(node.get("expr") or node.get("expression") or node.get("selector"))
            for item in _json_dicts(node.get("items")):
                labels = tuple(
                    label
                    for raw in _json_dicts(item.get("expressions") or item.get("labels") or item.get("expressions"))
                    if (label := _slang_expression(raw)) is not None
                )
                branches.append(
                    RTLBranch(
                        case_kind,
                        _slang_source_location(item),
                        selector,
                        labels,
                        bool(item.get("isDefault", False) or not labels),
                        exclusive,
                    )
                )
            default = node.get("defaultCase")
            if default is not None:
                branches.append(
                    RTLBranch(
                        case_kind,
                        _slang_source_location(default) if isinstance(default, dict) else _slang_source_location(node),
                        selector,
                        (),
                        True,
                        exclusive,
                    )
                )
    return tuple(branches)


_PROPERTY_KINDS = {
    "assertionstatement",
    "concurrentassertionstatement",
    "immediateassertionstatement",
    "assumeproperty",
    "assertproperty",
    "coverproperty",
    "coversequencestatement",
    "concurrentassertion",
    "immediateassertion",
}


def _slang_properties(members: tuple[dict[str, Any], ...]) -> tuple[RTLProperty, ...]:
    properties: list[RTLProperty] = []
    consumed: set[int] = set()
    for wrapper in _walk_json_objects(members):
        body = wrapper.get("body")
        if not isinstance(body, dict) or str(body.get("kind", "")).lower() not in _PROPERTY_KINDS:
            continue
        consumed.add(id(body))
        label = wrapper.get("block") or wrapper.get("name")
        properties.append(_slang_property(body, _canonical_symbol_name(str(label)) if label else None))
    for node in _walk_json_objects(members):
        if id(node) in consumed or str(node.get("kind", "")).lower() not in _PROPERTY_KINDS:
            continue
        properties.append(_slang_property(node))
    return tuple(properties)


def _slang_property(value: dict[str, Any], name: str | None = None) -> RTLProperty:
    raw_kind = str(value.get("kind", "assert")).lower()
    assertion_kind = str(value.get("assertionKind", ""))
    kind_text = f"{raw_kind} {assertion_kind}".lower()
    kind = "cover" if "cover" in kind_text else "assume" if "assume" in kind_text else "assert"
    concurrent = "concurrent" in raw_kind or "property" in raw_kind
    spec = value.get("propertySpec") or value.get("property") or value.get("expression")
    if not isinstance(spec, dict):
        spec = value.get("cond") or value.get("condition")
    clock_node: object = None
    disable: object = None
    body_node = spec
    if isinstance(body_node, dict) and body_node.get("kind") == "Clocking":
        clock_node = body_node.get("clocking")
        body_node = body_node.get("expr")
    if isinstance(body_node, dict) and body_node.get("kind") == "DisableIff":
        disable = body_node.get("condition")
        body_node = body_node.get("expr")
    body = _slang_expression(body_node)
    known_property_nodes = {
        "Binary",
        "Clocking",
        "DisableIff",
        "Simple",
        "SequenceConcat",
        "Unary",
        "StrongWeak",
        "FirstMatch",
        "Conditional",
        "Parenthesized",
    }
    unsupported = tuple(
        sorted(
            {
                str(item.get("kind"))
                for item in _walk_json_objects(spec)
                if _looks_like_property_expression(item) and str(item.get("kind")) not in known_property_nodes
            }
        )
    )
    return RTLProperty(
        kind,
        name or (str(value.get("name")) if value.get("name") else None),
        concurrent=concurrent,
        clock=_first_signal(clock_node or value.get("clocking") or value.get("clock")),
        clock_edge=_event_edge(clock_node or value.get("clocking") or value.get("clock")),
        disable_condition=_slang_expression(disable or value.get("disableCondition") or value.get("disable")),
        body=body,
        source_location=_slang_source_location(value),
        support_status="unsupported" if unsupported or body is None else "normalized",
        unsupported_operators=unsupported,
    )


def _looks_like_property_expression(value: dict[str, Any]) -> bool:
    kind = str(value.get("kind", ""))
    return kind in {
        "Binary",
        "Clocking",
        "DisableIff",
        "Simple",
        "SequenceConcat",
        "Unary",
        "StrongWeak",
        "FirstMatch",
        "Conditional",
        "Parenthesized",
        "Intersect",
        "Throughout",
        "Within",
        "Abort",
        "Repetition",
    }


def _slang_generate_scope(value: dict[str, Any]) -> RTLGenerateScope:
    name = str(value.get("name") or value.get("scope") or "generate")
    condition = _slang_expression(value.get("condition") or value.get("selector") or value.get("stopExpression"))
    selected = value.get("selected")
    if not isinstance(selected, bool) and "isUninstantiated" in value:
        selected = not bool(value.get("isUninstantiated"))
    index = value.get("index")
    if not isinstance(index, int):
        index = _slang_generate_index(value)
    return RTLGenerateScope(
        scope_id=str(value.get("id") or name),
        name=name,
        kind=_canonical_operation(str(value.get("branchKind") or value.get("kind", "generate"))),
        source_location=_slang_source_location(value),
        instance_names=tuple(
            str(item.get("name"))
            for item in _walk_json_objects(value.get("members"))
            if item.get("kind") == "Instance" and item.get("name")
        ),
        condition=condition,
        selected=bool(selected) if isinstance(selected, bool) else None,
        iteration_index=int(index) if isinstance(index, int) else None,
    )


def _slang_generate_index(value: dict[str, Any]) -> int | None:
    index_parameter = next(
        (item for item in _json_dicts(value.get("members")) if item.get("kind") == "Parameter" and item.get("isLocal")),
        None,
    )
    if index_parameter is None:
        return None
    raw_index = _canonical_constant(index_parameter.get("value"))
    return int(raw_index) if raw_index is not None and raw_index.lstrip("-").isdigit() else None


def _slang_generate_scopes(members: tuple[dict[str, Any], ...]) -> tuple[RTLGenerateScope, ...]:
    scopes: list[RTLGenerateScope] = []
    for item in members:
        kind = str(item.get("kind", ""))
        if kind == "GenerateBlockArray":
            parent = _slang_generate_scope(item)
            scopes.append(replace(parent, selected=True))
            base = str(item.get("name") or "generate")
            for block in _json_dicts(item.get("members")):
                if block.get("kind") != "GenerateBlock":
                    continue
                index = _slang_generate_index(block)
                child = _slang_generate_scope(block)
                scopes.append(
                    replace(
                        child,
                        name=f"{base}[{index}]" if index is not None else base,
                        scope_id=f"{parent.scope_id}[{index}]" if index is not None else child.scope_id,
                    )
                )
        elif kind == "GenerateBlock":
            scopes.append(_slang_generate_scope(item))
    return tuple(scopes)


def _merge_slang_generate_scopes(
    elaborated: tuple[RTLGenerateScope, ...],
    declared: tuple[RTLGenerateScope, ...],
) -> tuple[RTLGenerateScope, ...]:
    by_name = {item.name: item for item in elaborated}
    for declaration in declared:
        current = by_name.get(declaration.name)
        if current is None:
            by_name[declaration.name] = replace(declaration, selected=False)
        elif current.condition is None:
            by_name[declaration.name] = replace(
                current,
                condition=declaration.condition,
                selected=True if current.selected is None else current.selected,
            )
    ordered = [by_name[item.name] for item in elaborated]
    ordered.extend(by_name[item.name] for item in declared if item.name not in {value.name for value in elaborated})
    return tuple(ordered)


def _slang_source_generate_scopes(
    source_files: tuple[Path, ...],
) -> dict[str, tuple[RTLGenerateScope, ...]]:
    result: dict[str, list[RTLGenerateScope]] = {}
    module_pattern = re.compile(r"\bmodule\s+(?P<name>[A-Za-z_$][\w$]*)\b(?P<body>.*?)\bendmodule\b", re.S)
    patterns = (
        ("conditional", re.compile(r"\bif\s*\((?P<condition>[^)]*)\)\s*begin\s*:\s*(?P<name>[A-Za-z_$][\w$]*)")),
        (
            "loop",
            re.compile(r"\bfor\s*\([^;]*;(?P<condition>[^;]*);[^)]*\)\s*begin\s*:\s*(?P<name>[A-Za-z_$][\w$]*)"),
        ),
    )
    for path in source_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for module_match in module_pattern.finditer(text):
            module = module_match.group("name")
            body = module_match.group("body")
            body_offset = module_match.start("body")
            for kind, pattern in patterns:
                for match in pattern.finditer(body):
                    name = match.group("name")
                    location_offset = body_offset + match.start()
                    line = text.count("\n", 0, location_offset) + 1
                    column = location_offset - text.rfind("\n", 0, location_offset)
                    result.setdefault(module, []).append(
                        RTLGenerateScope(
                            scope_id=f"source:{module}:{name}",
                            name=name,
                            kind=kind,
                            source_location=f"{path}:{line}:{column}",
                            condition=_slang_source_expression(match.group("condition")),
                        )
                    )
    return {name: tuple(items) for name, items in result.items()}


def _slang_source_expression(value: str) -> RTLExpression:
    text = value.strip()
    if text.startswith("!"):
        return RTLExpression("not", children=(_slang_source_expression(text[1:]),))
    for token, operation in (
        ("<=", "lessequal"),
        (">=", "greaterequal"),
        ("==", "equal"),
        ("!=", "notequal"),
        ("<", "lessthan"),
        (">", "greaterthan"),
    ):
        if token in text:
            left, right = text.split(token, 1)
            return RTLExpression(
                operation,
                children=(_slang_source_expression(left), _slang_source_expression(right)),
            )
    if text.lstrip("-").isdigit():
        return RTLExpression("literal", value=str(int(text)))
    if re.fullmatch(r"[A-Za-z_$][\w$]*", text):
        return RTLExpression("ref", name=text)
    return RTLExpression("unsupported", value=text)


def _slang_control_domain(
    node: dict[str, Any],
    block: RTLProceduralBlock,
) -> RTLControlDomain | None:
    if not block.kind.startswith("always"):
        return None
    event_root = node.get("timing") or node.get("eventControl") or node
    events: list[tuple[str, str]] = []
    for item in _walk_json_objects(event_root):
        raw_edge = str(item.get("edge", item.get("edgeKind", item.get("kind", "")))).lower()
        if "posedge" in raw_edge or "positive" in raw_edge:
            edge = "pos"
        elif "negedge" in raw_edge or "negative" in raw_edge:
            edge = "neg"
        else:
            continue
        refs = _slang_signal_refs(item)
        if refs and (refs[0], edge) not in events:
            events.append((refs[0], edge))
    if not events:
        return None
    clock, clock_edge = events[0]
    reset = events[1][0] if len(events) > 1 else None
    reset_edge = events[1][1] if len(events) > 1 else None
    reset_active_low: bool | None = reset_edge == "neg" if reset_edge else None
    if reset is None:
        for branch in _slang_branches(node):
            refs = _slang_signal_refs_from_expression(branch.condition)
            candidate = next(
                (item for item in refs if item != clock and re.search(r"(?:^|_)(?:rst|reset)(?:_|$)", item, re.I)),
                None,
            )
            if candidate is not None:
                reset = candidate
                reset_active_low = _expression_is_active_low(branch.condition)
                break
    return RTLControlDomain(
        domain_id=f"{clock}:{reset or 'none'}",
        clock=clock,
        clock_edge=clock_edge,
        reset=reset,
        reset_edge=reset_edge,
        reset_active_low=reset_active_low,
        asynchronous_reset=len(events) > 1,
        source_location=block.source_location,
    )


def _slang_signal_refs_from_expression(value: RTLExpression | None) -> tuple[str, ...]:
    if value is None:
        return ()
    refs: list[str] = []
    for item in _walk_expressions(value):
        if item.name and item.kind in {"ref", "member"} and item.name not in refs:
            refs.append(item.name)
    return tuple(refs)


def _expression_is_active_low(value: RTLExpression | None) -> bool | None:
    if value is None:
        return None
    if value.kind in {"logicalnot", "bitwisenot", "not"}:
        return True
    return False


def _modules_by_specialization(modules: tuple[RTLModule, ...]) -> dict[tuple[str, str], tuple[RTLModule, ...]]:
    grouped: dict[tuple[str, str], list[RTLModule]] = {}
    for module in modules:
        key = (module.original_name or module.name, _specialization_signature(module))
        grouped.setdefault(key, []).append(module)
    return {
        key: tuple(sorted(items, key=lambda item: (item.elaborated_name or "", item.name)))
        for key, items in grouped.items()
    }


def _specialization_signature(module: RTLModule) -> str:
    parameters = tuple(
        sorted(
            (parameter.name, _canonical_parameter_constant(parameter.default_value))
            for parameter in module.parameter_details
            if not parameter.local
        )
    )
    return ",".join(f"{name}={value}" for name, value in parameters) if parameters else "default"


def _display_specialization(module: str, specialization: str) -> str:
    return module if specialization == "default" else f"{module}[{specialization}]"


def _compare_module(
    primary: RTLModule,
    reference: RTLModule,
    specialization: str,
    capabilities: frozenset[str],
    issues: list[SemanticCrossCheckIssue],
) -> None:
    comparisons: tuple[tuple[str, str, object, object], ...] = (
        (CAPABILITY_PORTS, "ports", tuple(sorted(primary.ports)), tuple(sorted(reference.ports))),
        (CAPABILITY_PARAMETERS, "parameters", _parameter_signature(primary), _parameter_signature(reference)),
        (CAPABILITY_HIERARCHY, "instances", _instance_signature(primary), _instance_signature(reference)),
        (CAPABILITY_TYPES, "type_details", _type_signature(primary), _type_signature(reference)),
        (CAPABILITY_PORTS, "port_details", _port_signature(primary), _port_signature(reference)),
        (CAPABILITY_ASSIGNMENTS, "assignments", _assignment_signature(primary), _assignment_signature(reference)),
        (
            CAPABILITY_PROCEDURAL_BLOCKS,
            "procedural_blocks",
            _procedural_signature(primary),
            _procedural_signature(reference),
        ),
        (CAPABILITY_EXPRESSIONS, "expressions", _expression_signature(primary), _expression_signature(reference)),
        (CAPABILITY_BRANCHES, "branches", _branch_signature(primary), _branch_signature(reference)),
        (CAPABILITY_CONTROL_DOMAINS, "control_domains", _domain_signature(primary), _domain_signature(reference)),
        (CAPABILITY_PROPERTIES, "properties", _property_signature(primary), _property_signature(reference)),
        (CAPABILITY_IMPORTS, "imports", tuple(sorted(primary.imports)), tuple(sorted(reference.imports))),
        (CAPABILITY_GENERATE_SCOPES, "generate_scopes", _generate_signature(primary), _generate_signature(reference)),
        (CAPABILITY_MEMORIES, "memories", _memory_signature(primary), _memory_signature(reference)),
    )
    for capability, field, left, right in comparisons:
        if capability in capabilities:
            _compare_value(primary, reference, specialization, capability, field, left, right, issues)


def _compare_value(
    primary_module: RTLModule,
    reference_module: RTLModule,
    specialization: str,
    capability: str,
    field: str,
    primary: object,
    reference: object,
    issues: list[SemanticCrossCheckIssue],
) -> None:
    if primary == reference:
        return
    issues.append(
        SemanticCrossCheckIssue(
            primary_module.original_name or primary_module.name,
            field,
            repr(primary),
            repr(reference),
            capability=capability,
            specialization=specialization,
            primary_evidence=primary_module.ast_refs,
            reference_evidence=reference_module.ast_refs,
            primary_location=_module_field_location(primary_module, field),
            reference_location=_module_field_location(reference_module, field),
        )
    )


def _module_field_location(module: RTLModule, field: str) -> str | None:
    values: tuple[object, ...]
    if field == "port_details":
        values = module.port_details
    elif field == "assignments":
        values = module.assignment_details
    elif field == "procedural_blocks":
        values = module.procedural_block_details
    elif field == "properties":
        values = module.property_details
    else:
        values = ()
    for value in values:
        location = getattr(value, "source_location", None)
        if isinstance(location, str):
            return location
    return str(module.source) if module.source is not None else None


def _port_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                port.name,
                port.direction.lower(),
                port.width if port.width is not None else 1,
                bool(port.signed),
                port.interface_name,
                port.modport,
                port.interface_direction,
                tuple(_canonical_range(item) for item in port.packed_dimensions),
                tuple(_canonical_range(item) for item in port.unpacked_dimensions),
            )
            for port in module.port_details
        )
    )


def _parameter_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                item.name,
                _canonical_parameter_constant(item.default_value),
                item.width,
                bool(item.signed),
                bool(item.local),
            )
            for item in module.parameter_details
        )
    )


def _instance_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    if not module.instance_details:
        return tuple(sorted((item, None, (), ()) for item in module.instances))
    return tuple(
        sorted(
            (
                item.name,
                item.module_name,
                tuple(
                    sorted(
                        (binding.name, _canonical_parameter_constant(binding.value))
                        for binding in item.parameter_bindings
                    )
                ),
                tuple(
                    sorted(
                        (
                            connection.port_name,
                            tuple(sorted(connection.signal_refs)),
                            _expression_node_signature(connection.expression),
                        )
                        for connection in item.connections
                    )
                ),
            )
            for item in module.instance_details
        )
    )


def _assignment_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                _canonical_assignment_kind(item.kind),
                tuple(sorted(item.lhs_signals)),
                tuple(sorted(item.rhs_signals)),
                tuple(_expression_node_signature(expression) for expression in item.expressions),
            )
            for item in module.assignment_details
        )
    )


def _procedural_signature(module: RTLModule) -> tuple[str, ...]:
    return tuple(sorted(_canonical_procedure_kind(item.kind) for item in module.procedural_block_details))


def _canonical_assignment_kind(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    if compact in {"procedural", "assignment", "assign"}:
        return "assign"
    if compact in {"nonblocking", "nonblockingassignment", "assigndly"}:
        return "assigndly"
    kind = _canonical_operation(value)
    if kind in {"continuous", "contassign"}:
        return "contassign"
    if kind in {"procedural", "assignment", "assign"}:
        return "assign"
    if kind in {"nonblocking", "nonblockingassignment", "assigndly"}:
        return "assigndly"
    return kind


def _canonical_procedure_kind(value: str) -> str:
    kind = _canonical_operation(value)
    return "always" if kind in {"always", "alwaysff", "alwayscomb", "alwayslatch", "alwayslat"} else kind


def _type_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                _canonical_symbol_name(item.name) if item.name else None,
                _canonical_type_kind(item.kind),
                item.width,
                bool(item.signed),
                tuple(item.members),
                tuple(item.enum_values),
                tuple(
                    (
                        member.name,
                        member.width,
                        bool(member.signed),
                        _canonical_range(member.packed_range),
                        member.bit_offset,
                        tuple(_canonical_range(value) for value in member.packed_dimensions),
                        tuple(_canonical_range(value) for value in member.unpacked_dimensions),
                    )
                    for member in item.member_details
                ),
                tuple(_canonical_range(value) for value in item.packed_dimensions),
                tuple(_canonical_range(value) for value in item.unpacked_dimensions),
                item.package_name,
            )
            for item in module.type_details
            if item.members
            or item.enum_values
            or item.package_name is not None
            or any(
                token in _canonical_operation(item.kind)
                for token in ("enum", "struct", "union", "interface", "modport")
            )
        )
    )


def _expression_signature(module: RTLModule) -> tuple[object, ...]:
    roots = tuple(
        expression for assignment in module.assignment_details for expression in assignment.expressions
    ) + tuple(expression for block in module.procedural_block_details for expression in block.expressions)
    return tuple(sorted((_expression_node_signature(item) for item in roots), key=repr))


def _expression_node_signature(expression: RTLExpression | None) -> object:
    if expression is None:
        return None
    return (
        _canonical_operation(expression.kind),
        expression.name,
        _canonical_constant(expression.value),
        expression.width,
        expression.signed,
        _canonical_range(expression.packed_range),
        _canonical_operation(expression.cast_kind) if expression.cast_kind else None,
        tuple(_expression_node_signature(item) for item in expression.children),
    )


def _branch_signature(module: RTLModule) -> tuple[object, ...]:
    return tuple(
        sorted(
            [
                (
                    _canonical_operation(branch.kind),
                    _expression_node_signature(branch.condition),
                    tuple(_expression_node_signature(item) for item in branch.labels),
                    branch.is_default,
                    branch.mutually_exclusive,
                )
                for block in module.procedural_block_details
                for branch in block.branches
            ],
            key=repr,
        )
    )


def _domain_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                (
                    item.clock,
                    item.clock_edge,
                    item.reset,
                    item.reset_edge,
                    item.reset_active_low,
                    item.asynchronous_reset,
                )
                for item in module.control_domains
            ),
            key=repr,
        )
    )


def _property_signature(module: RTLModule) -> tuple[object, ...]:
    return tuple(
        sorted(
            [
                (
                    item.kind,
                    item.name,
                    item.concurrent,
                    item.clock,
                    item.clock_edge,
                    _expression_node_signature(item.disable_condition),
                    _expression_node_signature(item.body),
                    item.support_status,
                    tuple(item.unsupported_operators),
                )
                for item in module.property_details
            ],
            key=repr,
        )
    )


def _generate_signature(module: RTLModule) -> tuple[object, ...]:
    return tuple(
        sorted(
            [
                (
                    item.name,
                    "generate",
                    tuple(sorted(name.rsplit(".", 1)[-1] for name in item.instance_names)),
                    _expression_node_signature(item.condition),
                    True if item.selected is None else item.selected,
                    item.iteration_index,
                )
                for item in module.generate_scopes
            ],
            key=repr,
        )
    )


def _memory_signature(module: RTLModule) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                item.name,
                item.element_width,
                item.depth,
                tuple(_canonical_range(value) for value in item.unpacked_dimensions),
                item.read_during_write,
            )
            for item in module.memories
        )
    )


_OPERATION_NAMES = {
    "binaryexpression": "binary",
    "unaryexpression": "unary",
    "conversion": "cast",
    "conversionexpression": "cast",
    "conditionalop": "cond",
    "conditionalexpression": "cond",
    "concatenation": "concat",
    "namedvalue": "ref",
    "hierarchicalvalue": "ref",
    "varref": "ref",
    "varxref": "ref",
    "integerliteral": "literal",
    "const": "literal",
    "constint": "literal",
    "constant": "literal",
    "elementselect": "select",
    "arraysel": "select",
    "bitsel": "select",
    "rangeselect": "range",
    "sel": "range",
    "subtract": "sub",
    "logicalnot": "not",
    "lognot": "not",
    "realliteral": "literal",
    "stringliteral": "literal",
    "procedural": "always",
    "alwaysff": "alwaysff",
    "alwayscomb": "alwayscomb",
    "alwayslatch": "alwayslatch",
    "continuous": "contassign",
}


def _canonical_operation(value: str | None) -> str:
    if not value:
        return ""
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    return _OPERATION_NAMES.get(compact, compact)


def _canonical_type_kind(value: str) -> str:
    kind = _canonical_operation(value)
    if "enum" in kind:
        return "enum"
    if "struct" in kind:
        return "struct"
    if "union" in kind:
        return "union"
    if "modport" in kind:
        return "modport"
    if "interface" in kind or "ifaceref" in kind:
        return "interface"
    return kind


def _canonical_symbol_name(value: str) -> str:
    stripped = value.strip()
    if " " in stripped and stripped.split(" ", 1)[0].isdigit():
        stripped = stripped.split(" ", 1)[1]
    return stripped.rsplit("::", 1)[-1]


def _canonical_constant(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    text = str(value).strip().replace("_", "").lower()
    match = re.fullmatch(r"(?:(\d+))?'([s]?)([bodh])([0-9a-fxz?]+)", text)
    if not match:
        return text
    width, signed, radix, digits = match.groups()
    if any(character in digits for character in "xz?"):
        return f"{width or ''}'{signed}{radix}{digits}"
    number = int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[radix])
    return f"{width or ''}:{'s' if signed else 'u'}:{number}"


def _canonical_parameter_constant(value: object) -> str | None:
    canonical = _canonical_constant(value)
    if canonical is None:
        return None
    normalized = re.fullmatch(r"(?:\d*):[su]:(-?\d+)", canonical)
    if normalized:
        return str(int(normalized.group(1)))
    if canonical.lstrip("-").isdigit():
        return str(int(canonical))
    return canonical


def _expression_constant(value: object) -> object:
    if not isinstance(value, dict):
        return None
    if value.get("constant") is not None:
        return value.get("constant")
    if str(value.get("kind", "")).endswith("Literal"):
        return value.get("value")
    return None


def _canonical_range(value: str | None) -> str | None:
    if value is None:
        return None
    match = re.fullmatch(r"\[?\s*(-?\d+)\s*:\s*(-?\d+)\s*\]?", value)
    return f"[{int(match.group(1))}:{int(match.group(2))}]" if match else value.replace(" ", "")


def _canonical_specialization_id(name: str, parameters: tuple[RTLParameter, ...]) -> str:
    signature = "\0".join(
        (
            name,
            *(
                f"{item.name}={_canonical_parameter_constant(item.default_value)}"
                for item in parameters
                if not item.local
            ),
        )
    )
    return hashlib.sha256(signature.encode()).hexdigest()[:16]


def _type_range(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("range") or value.get("packedRange")
    if raw is not None:
        return _canonical_range(str(raw))
    dimensions = _type_dimensions(value, "packed")
    return dimensions[0] if dimensions else None


def _type_width(value: object) -> int | None:
    if isinstance(value, str):
        return None
    if not isinstance(value, dict) or not value:
        return None
    width = value.get("bitWidth") or value.get("width")
    if isinstance(width, int):
        return width
    kind = str(value.get("kind", ""))
    if kind == "EnumType":
        return _type_width(value.get("baseType"))
    if kind in {"PredefinedIntegerType", "IntegerType"}:
        name = str(value.get("name", "")).lower()
        return {"byte": 8, "shortint": 16, "int": 32, "integer": 32, "longint": 64}.get(name, 32)
    if kind in {"PackedStructType", "PackedUnionType", "StructType", "UnionType"}:
        widths = tuple(_type_width(item.get("type")) for item in _json_dicts(value.get("members")))
        known = tuple(item for item in widths if item is not None)
        if len(known) != len(widths):
            return None
        return max(known, default=0) if "Union" in kind else sum(known)
    range_width = _range_width(_type_range(value))
    element_width = _type_width(value.get("elementType"))
    if range_width is not None and element_width is not None:
        return range_width * element_width
    return range_width if range_width is not None else 1


def _type_signed(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if "isSigned" in value:
        return bool(value.get("isSigned"))
    if value.get("kind") == "PredefinedIntegerType":
        return str(value.get("name", "")).lower() not in {"bit", "logic", "reg"}
    return _type_signed(value.get("elementType"))


def _type_dimensions(value: object, category: str) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    keys = (f"{category}Dimensions", f"{category}_dimensions")
    raw: object = None
    for key in keys:
        if key in value:
            raw = value[key]
            break
    explicit = (
        tuple(_canonical_range(str(item.get("range") if isinstance(item, dict) else item)) or "" for item in raw)
        if isinstance(raw, list)
        else ()
    )
    kind = str(value.get("kind", ""))
    is_dimension = (category == "packed" and kind in {"PackedArrayType", "PackedDimensionType"}) or (
        category == "unpacked" and kind in {"FixedSizeUnpackedArrayType", "UnpackedArrayType", "DynamicArrayType"}
    )
    own = (_canonical_range(str(value.get("range"))) or "",) if is_dimension and value.get("range") else ()
    nested = _type_dimensions(value.get("elementType"), category)
    return (*explicit, *own, *nested)


def _range_width(value: str | None) -> int | None:
    if value is None:
        return 1
    match = re.fullmatch(r"\[(-?\d+):(-?\d+)\]", value.strip())
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else None


def _product(values: tuple[int, ...]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def _is_expression_node(value: dict[str, Any]) -> bool:
    return str(value.get("kind", "")) in _SLANG_EXPRESSION_KINDS


_SLANG_EXPRESSION_KINDS = {
    "Assignment",
    "BinaryOp",
    "UnaryOp",
    "Conversion",
    "ConditionalOp",
    "Concatenation",
    "Replication",
    "Streaming",
    "NamedValue",
    "HierarchicalValue",
    "MemberAccess",
    "IntegerLiteral",
    "UnbasedUnsizedIntegerLiteral",
    "RealLiteral",
    "TimeLiteral",
    "StringLiteral",
    "NullLiteral",
    "RangeSelect",
    "ElementSelect",
    "Call",
    "MinTypMax",
    "Inside",
    "TaggedUnion",
    "Simple",
    "Binary",
    "SequenceConcat",
}

_SLANG_UNSUPPORTED_EXPRESSION_KINDS = {
    "NewClass",
    "NewArray",
    "CopyClass",
    "Dist",
    "ClockingEvent",
}


def _add_gap(gaps: dict[str, set[str]], capability: str, reason: str) -> None:
    gaps.setdefault(capability, set()).add(reason)


def _collect_slang_capability_gaps(value: object, gaps: dict[str, set[str]]) -> None:
    for node in _walk_json_objects(value):
        kind = str(node.get("kind", ""))
        location = _slang_source_location(node)
        prefix = f"{location}: " if location else ""
        if kind in _SLANG_UNSUPPORTED_EXPRESSION_KINDS:
            _add_gap(gaps, CAPABILITY_EXPRESSIONS, f"{prefix}unsupported expression {kind}")
        if kind in {"PatternCase", "RandCase", "RandSequence"}:
            _add_gap(gaps, CAPABILITY_BRANCHES, f"{prefix}unsupported branch {kind}")
        if kind in {"AssociativeArrayType", "QueueType", "VirtualInterfaceType"}:
            _add_gap(gaps, CAPABILITY_TYPES, f"{prefix}unsupported type {kind}")
        if kind in {"CheckerInstance", "PrimitiveInstance"}:
            _add_gap(gaps, CAPABILITY_HIERARCHY, f"{prefix}unsupported instance {kind}")
        if kind in {"GenerateBlock", "GenerateBlockArray"}:
            if kind == "GenerateBlock" and not node.get("name") and not node.get("branchKind"):
                _add_gap(
                    gaps,
                    CAPABILITY_GENERATE_SCOPES,
                    f"{prefix}generate block has no stable name or branch identity",
                )


def _walk_expressions(value: RTLExpression) -> tuple[RTLExpression, ...]:
    return (value, *(item for child in value.children for item in _walk_expressions(child)))


def _dedupe_expressions(values: tuple[RTLExpression, ...]) -> tuple[RTLExpression, ...]:
    seen: set[str] = set()
    result: list[RTLExpression] = []
    for value in values:
        key = repr(_expression_node_signature(value))
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _first_signal(value: object) -> str | None:
    refs = _slang_signal_refs(value)
    return refs[0] if refs else None


def _event_edge(value: object) -> str | None:
    for item in _walk_json_objects(value):
        edge = str(item.get("edge", item.get("kind", ""))).lower()
        if "posedge" in edge:
            return "pos"
        if "negedge" in edge:
            return "neg"
    return None
