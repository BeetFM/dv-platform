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
    embedding_model: str | None = None


@dataclass(frozen=True)
class VerificationClaim:
    """A claim that must be checked against RTL or documentation evidence."""

    claim_id: str
    scope: str
    statement: str
    status: ClaimStatus = ClaimStatus.UNCHECKED
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
    instances: tuple[str, ...] = ()
    documentation_refs: tuple[str, ...] = ()
    ast_refs: tuple[EvidenceRef, ...] = ()


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
    requirements: tuple[str, ...] = ()
    claims: tuple[VerificationClaim, ...] = ()
    checks: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedArtifact:
    """A generated file or report with traceability to the plan."""

    path: Path
    kind: ArtifactKind
    target: VerificationTarget
    content: str
    source_plan_module: str
    provenance_refs: tuple[EvidenceRef, ...] = ()


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
