"""Shared domain models for RTL verification generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class VerificationTarget(StrEnum):
    """Supported verification code generation targets."""

    COCOTB = "cocotb"
    SYSTEMVERILOG = "systemverilog"
    UVM = "uvm"
    VHDL = "vhdl"
    VERILOG = "verilog"
    FORMAL = "formal"


class ArtifactKind(StrEnum):
    """Types of generated verification output."""

    TESTBENCH = "testbench"
    ASSERTION = "assertion"
    FORMAL_HARNESS = "formal_harness"
    RUN_SCRIPT = "run_script"
    REPORT = "report"


class Severity(StrEnum):
    """Severity used for design feedback and verification gaps."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceKind(StrEnum):
    """Evidence channels used to support claims and generated artifacts."""

    VERILATOR_AST = "verilator_ast"
    DOCUMENT_CHUNK = "document_chunk"
    TOOL_LOG = "tool_log"
    GENERATED_ARTIFACT = "generated_artifact"


class ClaimStatus(StrEnum):
    """Claim-check state after evidence validation."""

    UNCHECKED = "unchecked"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MISSING_EVIDENCE = "missing_evidence"


class ClaimType(StrEnum):
    """Categories of claims produced by planners, checkers, and reviewers."""

    RTL_STRUCTURE = "rtl_structure"
    RTL_BEHAVIOR = "rtl_behavior"
    DOCUMENTATION_INTENT = "documentation_intent"
    PLANNED_CHECK = "planned_check"
    DESIGN_RECOMMENDATION = "design_recommendation"


@dataclass(frozen=True)
class HDLFile:
    """An RTL source file in the input project."""

    path: Path
    language: str
    library: str | None = None


@dataclass(frozen=True)
class EvidenceRef:
    """Traceable evidence for a claim, requirement, plan, or artifact."""

    kind: EvidenceKind
    source_id: str
    locator: str
    summary: str | None = None


@dataclass(frozen=True)
class DocumentationChunk:
    """A semantically retrievable documentation chunk."""

    chunk_id: str
    source: Path
    text: str
    start_offset: int | None = None
    end_offset: int | None = None
    content_hash: str | None = None
    embedding_model: str | None = None


@dataclass(frozen=True)
class VerificationClaim:
    """A claim that must be checked against RTL or documentation evidence."""

    claim_id: str
    scope: str
    statement: str
    claim_type: ClaimType = ClaimType.PLANNED_CHECK
    severity: Severity = Severity.MEDIUM
    generation_precondition: bool = False
    status: ClaimStatus = ClaimStatus.UNCHECKED
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class VerificationRequirement:
    """A structured design requirement synthesized from source documentation."""

    requirement_id: str
    scope: str
    statement: str
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class VerificationBehavior:
    """A structured RTL behavior selected for generated verification checks."""

    behavior_id: str
    scope: str
    kind: str
    target: str
    control: str | None = None
    value: str | None = None
    source: str | None = None
    confidence: str = "shape"
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class RTLModule:
    """Module or entity metadata extracted from RTL and documentation."""

    name: str
    source: Path | None = None
    ports: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    clocks: tuple[str, ...] = ()
    resets: tuple[str, ...] = ()
    clock_details: tuple["RTLClock", ...] = ()
    reset_details: tuple["RTLReset", ...] = ()
    instances: tuple[str, ...] = ()
    continuous_assignments: tuple[str, ...] = ()
    procedural_blocks: tuple[str, ...] = ()
    assertions: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()
    documentation_refs: tuple[str, ...] = ()
    ast_refs: tuple[EvidenceRef, ...] = ()
    port_details: tuple["RTLPort", ...] = ()
    instance_details: tuple["RTLInstance", ...] = ()
    assignment_details: tuple["RTLAssignment", ...] = ()
    procedural_block_details: tuple["RTLProceduralBlock", ...] = ()


@dataclass(frozen=True)
class RTLPort:
    """Structured RTL port metadata extracted from a source-of-truth parser."""

    name: str
    direction: str
    dtype_id: str | None = None
    data_type: str | None = None
    width: int | None = None
    signed: bool = False
    packed_range: str | None = None
    source_location: str | None = None


@dataclass(frozen=True)
class RTLClock:
    """Classified clock input metadata inferred from structured ports."""

    name: str
    direction: str
    width: int | None = None
    source_location: str | None = None
    classification: str = "name_heuristic"


@dataclass(frozen=True)
class RTLReset:
    """Classified reset input metadata inferred from structured ports."""

    name: str
    direction: str
    width: int | None = None
    active_low: bool | None = None
    source_location: str | None = None
    classification: str = "name_heuristic"


@dataclass(frozen=True)
class RTLInstance:
    """Structured child-instance metadata extracted from module hierarchy."""

    name: str
    module_name: str | None = None
    kind: str | None = None
    source_location: str | None = None


@dataclass(frozen=True)
class RTLAssignment:
    """Structured continuous assignment metadata extracted from RTL."""

    kind: str
    name: str | None = None
    source_location: str | None = None
    summary: str | None = None
    lhs_signals: tuple[str, ...] = ()
    rhs_signals: tuple[str, ...] = ()
    expressions: tuple["RTLExpression", ...] = ()


@dataclass(frozen=True)
class RTLExpression:
    """Normalized expression-tree node extracted from RTL parser output."""

    kind: str
    name: str | None = None
    value: str | None = None
    dtype_id: str | None = None
    source_location: str | None = None
    children: tuple["RTLExpression", ...] = ()


@dataclass(frozen=True)
class RTLProceduralBlock:
    """Structured procedural block metadata extracted from RTL."""

    kind: str
    name: str | None = None
    source_location: str | None = None
    summary: str | None = None
    signal_refs: tuple[str, ...] = ()
    expressions: tuple["RTLExpression", ...] = ()
    patterns: tuple["RTLProceduralPattern", ...] = ()


@dataclass(frozen=True)
class RTLProceduralPattern:
    """Conservative semantic pattern detected inside procedural logic."""

    kind: str
    target: str
    control: str | None = None
    value: str | None = None
    source: str | None = None
    confidence: str = "shape"


@dataclass(frozen=True)
class DesignDecision:
    """A design recommendation, risk, or tradeoff tied to RTL structure."""

    scope: str
    title: str
    rationale: str
    severity: Severity = Severity.INFO
    recommendation: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class VerificationPlan:
    """A generated plan for producing and running verification collateral."""

    module: str
    targets: tuple[VerificationTarget, ...]
    ports: tuple[RTLPort, ...] = ()
    requirements: tuple[str, ...] = ()
    structured_requirements: tuple[VerificationRequirement, ...] = ()
    behaviors: tuple[VerificationBehavior, ...] = ()
    claims: tuple[VerificationClaim, ...] = ()
    checks: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactQualityRequirement:
    """A pre-write quality gate for generated executable collateral."""

    requirement_id: str
    description: str
    satisfied: bool
    reason: str | None = None


@dataclass(frozen=True)
class GeneratedArtifact:
    """A generated file or report with traceability to the plan."""

    path: Path
    kind: ArtifactKind
    target: VerificationTarget
    content: str
    source_plan_module: str
    provenance_refs: tuple[EvidenceRef, ...] = ()
    quality_requirements: tuple[ArtifactQualityRequirement, ...] = ()


@dataclass(frozen=True)
class CLIConfig:
    """Local enterprise CLI configuration."""

    repo_root: Path
    work_dir: Path
    output_dir: Path
    documentation_paths: tuple[Path, ...] = ()
    rtl_filelists: tuple[Path, ...] = ()
    include_paths: tuple[Path, ...] = ()
    defines: tuple[str, ...] = ()
    top_modules: tuple[str, ...] = ()
    verilator_executable: str = "verilator"
    retrieval_index_dir: Path | None = None
    allow_network: bool = False
    strict: bool = False
    ci: bool = False
    simulators: tuple["SimulatorConfig", ...] = ()
    formal_tools: tuple["FormalToolConfig", ...] = ()
    generator_plugins: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimulatorConfig:
    """Configured simulator adapter for a verification target."""

    target: VerificationTarget
    name: str
    command: str


@dataclass(frozen=True)
class FormalToolConfig:
    """Configured formal tool adapter."""

    name: str
    command: str


@dataclass
class RTLProject:
    """The complete input and output context for one RTL repository."""

    root: Path
    hdl_files: list[HDLFile] = field(default_factory=list)
    documentation: list[Path] = field(default_factory=list)
    documentation_chunks: list[DocumentationChunk] = field(default_factory=list)
    modules: list[RTLModule] = field(default_factory=list)
    preferred_targets: list[VerificationTarget] = field(default_factory=list)
    cli_config: CLIConfig | None = None

    def module_by_name(self, name: str) -> RTLModule | None:
        """Return the first known module with the requested name."""

        return next((module for module in self.modules if module.name == name), None)
