"""Shared domain models for RTL verification generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dv_platform.agent.protocols import ProtocolModel, RegisterConflict, RegisterModel


class VerificationTarget(StrEnum):
    """Supported verification code generation targets."""

    COCOTB = "cocotb"
    SYSTEMVERILOG = "systemverilog"
    UVM = "uvm"
    VHDL = "vhdl"
    VERILOG = "verilog"
    FORMAL = "formal"


class ScenarioTargetState(StrEnum):
    """Truthful generation state for one scenario on one target."""

    EXECUTABLE = "executable"
    SCAFFOLD = "scaffold"
    UNSUPPORTED = "unsupported"


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
    VHDL_SOURCE = "vhdl_source"
    SLANG_AST = "slang_ast"
    DOCUMENT_CHUNK = "document_chunk"
    TOOL_LOG = "tool_log"
    GENERATED_ARTIFACT = "generated_artifact"
    CONFIGURATION = "configuration"
    SEMANTIC_MANIFEST = "semantic_manifest"
    REQUIREMENTS_EXPORT = "requirements_export"


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
    source_locator: str | None = None


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
    category: str = "general"
    signals: tuple[str, ...] = ()
    expected_value: str | None = None
    condition: str | None = None
    confidence: str = "lexical"
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class VerificationCheck:
    """One stable planned check and whether a backend can execute it."""

    check_id: str
    statement: str
    category: str = "general"
    executable: bool = False
    evidence_refs: tuple[EvidenceRef, ...] = ()
    closure_status: str | None = None
    coverage_point_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioStimulus:
    """One typed, deterministic action in an executable verification scenario."""

    kind: str
    signal: str | None = None
    value: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScenarioOracle:
    """The observation that independently decides a scenario outcome."""

    kind: str
    actual: str | None = None
    expected: str | None = None
    condition: str | None = None


@dataclass(frozen=True)
class ScenarioCompletion:
    """A bounded completion rule; executable scenarios may never wait forever."""

    kind: str
    signal: str | None = None
    value: str | None = None
    timeout_cycles: int = 32


@dataclass(frozen=True)
class ScenarioCoverageGoal:
    """A coverage point owned by exactly one verification scenario."""

    goal_id: str
    kind: str
    bins: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioTargetSupport:
    """Renderer-backed support claimed for one scenario target."""

    target: VerificationTarget
    state: ScenarioTargetState
    renderer_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class VerificationScenario:
    """Versioned executable intent shared by deterministic generation backends."""

    scenario_id: str
    kind: str
    stimulus: tuple[ScenarioStimulus, ...]
    oracle: ScenarioOracle
    completion: ScenarioCompletion
    coverage_goals: tuple[ScenarioCoverageGoal, ...]
    supported_targets: tuple[VerificationTarget, ...]
    target_states: tuple[ScenarioTargetSupport, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    check_ids: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    executable: bool = False


@dataclass(frozen=True)
class RequirementConflict:
    """A deterministic conflict between two structured requirements."""

    conflict_id: str
    scope: str
    requirement_ids: tuple[str, ...]
    reason: str
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
    domain_id: str | None = None
    confidence: str = "shape"
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class RTLModule:
    """Module or entity metadata extracted from RTL and documentation."""

    name: str
    original_name: str | None = None
    elaborated_name: str | None = None
    specialization_id: str | None = None
    design_unit_kind: str = "module"
    source: Path | None = None
    ports: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    parameter_details: tuple[RTLParameter, ...] = ()
    type_details: tuple[RTLType, ...] = ()
    memories: tuple[RTLMemory, ...] = ()
    memory_accesses: tuple[RTLMemoryAccess, ...] = ()
    clocks: tuple[str, ...] = ()
    resets: tuple[str, ...] = ()
    clock_details: tuple[RTLClock, ...] = ()
    reset_details: tuple[RTLReset, ...] = ()
    semantic_features: tuple[RTLSemanticFeature, ...] = ()
    instances: tuple[str, ...] = ()
    continuous_assignments: tuple[str, ...] = ()
    procedural_blocks: tuple[str, ...] = ()
    assertions: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()
    documentation_refs: tuple[str, ...] = ()
    ast_refs: tuple[EvidenceRef, ...] = ()
    port_details: tuple[RTLPort, ...] = ()
    instance_details: tuple[RTLInstance, ...] = ()
    assignment_details: tuple[RTLAssignment, ...] = ()
    procedural_block_details: tuple[RTLProceduralBlock, ...] = ()
    control_domains: tuple[RTLControlDomain, ...] = ()
    cdc_paths: tuple[RTLCDCPath, ...] = ()
    generate_scopes: tuple[RTLGenerateScope, ...] = ()
    imports: tuple[str, ...] = ()
    protocols: tuple[RTLProtocol, ...] = ()
    protocol_models: tuple[ProtocolModel, ...] = ()
    register_models: tuple[RegisterModel, ...] = ()
    register_conflicts: tuple[RegisterConflict, ...] = ()
    property_details: tuple[RTLProperty, ...] = ()


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
    interface_name: str | None = None
    modport: str | None = None
    interface_direction: str | None = None
    packed_dimensions: tuple[str, ...] = ()
    unpacked_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RTLClock:
    """Classified clock input metadata inferred from structured ports."""

    name: str
    direction: str
    width: int | None = None
    source_location: str | None = None
    classification: str = "name_heuristic"
    confidence: str = "low"


@dataclass(frozen=True)
class RTLReset:
    """Classified reset input metadata inferred from structured ports."""

    name: str
    direction: str
    width: int | None = None
    active_low: bool | None = None
    source_location: str | None = None
    classification: str = "name_heuristic"
    confidence: str = "low"


@dataclass(frozen=True)
class RTLParameter:
    """Elaborated parameter metadata for the analyzed top configuration."""

    name: str
    default_value: str | None = None
    dtype_id: str | None = None
    data_type: str | None = None
    width: int | None = None
    signed: bool = False
    local: bool = False
    source_location: str | None = None


@dataclass(frozen=True)
class RTLMemory:
    """Normalized unpacked storage metadata visible in a module."""

    name: str
    dtype_id: str | None = None
    element_width: int | None = None
    depth: int | None = None
    address_width: int | None = None
    read_during_write: str = "unknown"
    source_location: str | None = None
    unpacked_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RTLMemoryAccess:
    """One normalized read or write of an unpacked memory."""

    access_id: str
    memory: str
    kind: str
    address_signals: tuple[str, ...] = ()
    data_signals: tuple[str, ...] = ()
    enable_signals: tuple[str, ...] = ()
    domain_id: str | None = None
    synchronous: bool = False
    source_location: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class RTLType:
    """A named or referenced RTL type relevant to ports and state."""

    type_id: str
    name: str | None
    kind: str
    width: int | None = None
    signed: bool = False
    members: tuple[str, ...] = ()
    enum_values: tuple[str, ...] = ()
    source_location: str | None = None
    member_details: tuple[RTLTypeMember, ...] = ()
    packed_dimensions: tuple[str, ...] = ()
    unpacked_dimensions: tuple[str, ...] = ()
    package_name: str | None = None


@dataclass(frozen=True)
class RTLTypeMember:
    """Resolved layout facts for one packed aggregate member."""

    name: str
    dtype_id: str | None = None
    width: int | None = None
    signed: bool | None = None
    packed_range: str | None = None
    bit_offset: int | None = None
    packed_dimensions: tuple[str, ...] = ()
    unpacked_dimensions: tuple[str, ...] = ()
    source_location: str | None = None


@dataclass(frozen=True)
class RTLGenerateScope:
    """An elaborated generate or named scope retained for hierarchy review."""

    scope_id: str
    name: str
    kind: str
    source_location: str | None = None
    instance_names: tuple[str, ...] = ()
    condition: RTLExpression | None = None
    selected: bool | None = None
    iteration_index: int | None = None


@dataclass(frozen=True)
class RTLSemanticFeature:
    """An RTL semantic construct relevant to safe executable generation."""

    kind: str
    name: str | None = None
    source_location: str | None = None
    confidence: str = "parser"
    generation_supported: bool = False
    supported_targets: tuple[VerificationTarget, ...] = ()

    def supports_target(self, target: VerificationTarget) -> bool:
        """Return whether generation is safe for this construct and target."""

        return self.generation_supported or target in self.supported_targets


@dataclass(frozen=True)
class RTLConnection:
    """One elaborated child-instance port connection."""

    port_name: str
    direction: str | None = None
    signal_refs: tuple[str, ...] = ()
    expression: RTLExpression | None = None
    source_location: str | None = None


@dataclass(frozen=True)
class RTLInstance:
    """Structured child-instance metadata extracted from module hierarchy."""

    name: str
    module_name: str | None = None
    elaborated_module_name: str | None = None
    plan_module_name: str | None = None
    specialization_id: str | None = None
    parameter_bindings: tuple[RTLParameterBinding, ...] = ()
    kind: str | None = None
    source_location: str | None = None
    connections: tuple[RTLConnection, ...] = ()


@dataclass(frozen=True)
class RTLParameterBinding:
    """One elaborated parameter value bound on a child instance."""

    name: str
    value: str | None = None


@dataclass(frozen=True)
class RTLAssignment:
    """Structured continuous assignment metadata extracted from RTL."""

    kind: str
    name: str | None = None
    source_location: str | None = None
    summary: str | None = None
    lhs_signals: tuple[str, ...] = ()
    rhs_signals: tuple[str, ...] = ()
    expressions: tuple[RTLExpression, ...] = ()


@dataclass(frozen=True)
class RTLExpression:
    """Normalized expression-tree node extracted from RTL parser output."""

    kind: str
    name: str | None = None
    value: str | None = None
    dtype_id: str | None = None
    source_location: str | None = None
    children: tuple[RTLExpression, ...] = ()
    width: int | None = None
    signed: bool | None = None
    cast_kind: str | None = None
    packed_range: str | None = None


@dataclass(frozen=True)
class RTLBranch:
    """One normalized conditional or case branch."""

    kind: str
    source_location: str | None = None
    condition: RTLExpression | None = None
    labels: tuple[RTLExpression, ...] = ()
    is_default: bool = False
    mutually_exclusive: bool | None = None


@dataclass(frozen=True)
class RTLProperty:
    """Structured immediate or concurrent assertion / coverage property."""

    kind: str
    name: str | None = None
    concurrent: bool = False
    clock: str | None = None
    clock_edge: str | None = None
    disable_condition: RTLExpression | None = None
    body: RTLExpression | None = None
    source_location: str | None = None
    support_status: str = "unsupported"
    unsupported_operators: tuple[str, ...] = ()


@dataclass(frozen=True)
class RTLProceduralBlock:
    """Structured procedural block metadata extracted from RTL."""

    kind: str
    name: str | None = None
    source_location: str | None = None
    summary: str | None = None
    signal_refs: tuple[str, ...] = ()
    expressions: tuple[RTLExpression, ...] = ()
    patterns: tuple[RTLProceduralPattern, ...] = ()
    domain_id: str | None = None
    branches: tuple[RTLBranch, ...] = ()


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
class RTLControlDomain:
    """A clock/reset domain derived from one or more procedural blocks."""

    domain_id: str
    clock: str
    clock_edge: str = "pos"
    reset: str | None = None
    reset_edge: str | None = None
    reset_active_low: bool | None = None
    asynchronous_reset: bool = False
    source_location: str | None = None


@dataclass(frozen=True)
class RTLCDCPath:
    """A signal path crossing two normalized control domains."""

    path_id: str
    signal: str
    source_domain: str
    destination_domain: str
    classification: str = "direct"
    synchronizer_stages: int = 0
    stage_signals: tuple[str, ...] = ()
    safe: bool = False
    reset_compatible: bool | None = None
    source_location: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class RTLProtocol:
    """A structured protocol channel inferred from compatible module ports."""

    protocol_id: str
    kind: str
    name: str
    role: str
    valid: str
    ready: str
    data: str | None = None
    data_width: int | None = None
    clock: str | None = None
    reset: str | None = None
    confidence: str = "naming"
    profile: str = "builtin"
    signal_map: tuple[tuple[str, str], ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class DesignDecision:
    """A design recommendation, risk, or tradeoff tied to RTL structure."""

    scope: str
    title: str
    rationale: str
    severity: Severity = Severity.INFO
    confidence: str = "high"
    recommendation: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class VerificationPlan:
    """A generated plan for producing and running verification collateral."""

    module: str
    targets: tuple[VerificationTarget, ...]
    design_unit: str | None = None
    elaborated_design_unit: str | None = None
    specialization_id: str | None = None
    design_unit_kind: str = "module"
    ports: tuple[RTLPort, ...] = ()
    clocks: tuple[RTLClock, ...] = ()
    resets: tuple[RTLReset, ...] = ()
    semantic_features: tuple[RTLSemanticFeature, ...] = ()
    parameters: tuple[RTLParameter, ...] = ()
    memories: tuple[RTLMemory, ...] = ()
    memory_accesses: tuple[RTLMemoryAccess, ...] = ()
    type_details: tuple[RTLType, ...] = ()
    instances: tuple[RTLInstance, ...] = ()
    control_domains: tuple[RTLControlDomain, ...] = ()
    cdc_paths: tuple[RTLCDCPath, ...] = ()
    generate_scopes: tuple[RTLGenerateScope, ...] = ()
    imports: tuple[str, ...] = ()
    protocols: tuple[RTLProtocol, ...] = ()
    protocol_models: tuple[ProtocolModel, ...] = ()
    register_models: tuple[RegisterModel, ...] = ()
    register_conflicts: tuple[RegisterConflict, ...] = ()
    property_details: tuple[RTLProperty, ...] = ()
    depth_policies: tuple[VerificationDepthPolicy, ...] = ()
    requirements: tuple[str, ...] = ()
    structured_requirements: tuple[VerificationRequirement, ...] = ()
    requirement_conflicts: tuple[RequirementConflict, ...] = ()
    behaviors: tuple[VerificationBehavior, ...] = ()
    claims: tuple[VerificationClaim, ...] = ()
    checks: tuple[str, ...] = ()
    check_details: tuple[VerificationCheck, ...] = ()
    scenarios: tuple[VerificationScenario, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    agent_assumptions: tuple[AgentPlanningNote, ...] = ()
    agent_open_questions: tuple[AgentPlanningNote, ...] = ()
    agent_provenance: AgentPlanProvenance | None = None


@dataclass(frozen=True)
class AgentPlanProvenance:
    """Safe per-module provenance for optional AI plan augmentation."""

    agent_version: str
    prompt_version: str
    run_id: str
    model: str
    provider: str
    context_hash: str
    prompt_hash: str
    proposal_hash: str | None = None
    cache_key: str | None = None
    cache_status: str = "disabled"
    status: str = "fallback"
    error_category: str | None = None
    accepted_requirement_ids: tuple[str, ...] = ()
    accepted_check_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentPlanningNote:
    """An AI-proposed assumption or question linked to existing evidence."""

    note_id: str
    statement: str
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class ArtifactQualityRequirement:
    """A pre-write quality gate for generated executable collateral."""

    requirement_id: str
    description: str
    satisfied: bool
    reason: str | None = None


@dataclass(frozen=True)
class ArtifactTrace:
    """Mapping from generated executable symbols back to plan records."""

    trace_id: str
    generated_symbol: str
    check_indexes: tuple[int, ...] = ()
    check_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    behavior_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    protocol_ids: tuple[str, ...] = ()
    register_ids: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class GeneratedArtifact:
    """A generated file or report with traceability to the plan."""

    path: Path
    kind: ArtifactKind
    target: VerificationTarget
    content: str
    source_plan_module: str
    design_unit: str | None = None
    elaborated_design_unit: str | None = None
    specialization_id: str | None = None
    elaborated_parameters: tuple[RTLParameter, ...] = ()
    provenance_refs: tuple[EvidenceRef, ...] = ()
    quality_requirements: tuple[ArtifactQualityRequirement, ...] = ()
    traceability: tuple[ArtifactTrace, ...] = ()


@dataclass(frozen=True)
class CLIConfig:
    """Local enterprise CLI configuration."""

    repo_root: Path
    work_dir: Path
    output_dir: Path
    documentation_paths: tuple[Path, ...] = ()
    register_map_paths: tuple[Path, ...] = ()
    rtl_filelists: tuple[Path, ...] = ()
    include_paths: tuple[Path, ...] = ()
    defines: tuple[str, ...] = ()
    parameter_overrides: tuple[str, ...] = ()
    parameter_sweeps: tuple[tuple[str, ...], ...] = ()
    top_modules: tuple[str, ...] = ()
    verilator_executable: str = "verilator"
    slang_executable: str = "slang"
    semantic_crosscheck: str = "off"
    retrieval_index_dir: Path | None = None
    allow_network: bool = False
    strict: bool = False
    ci: bool = False
    simulators: tuple[SimulatorConfig, ...] = ()
    formal_tools: tuple[FormalToolConfig, ...] = ()
    generator_plugins: tuple[str, ...] = ()
    adapter_plugins: tuple[AdapterPluginConfig, ...] = ()
    protocol_profiles: tuple[ProtocolProfile, ...] = ()
    depth_policies: tuple[VerificationDepthPolicy, ...] = ()
    coverage_policy: CoveragePolicy = field(default_factory=lambda: CoveragePolicy())
    audit_enabled: bool = True
    redact_patterns: tuple[str, ...] = ()
    max_parallel_modules: int = 1
    max_process_memory_mb: int = 768
    max_total_process_memory_mb: int = 4096
    max_output_bytes: int = 1_048_576
    ai: AIConfig = field(default_factory=lambda: AIConfig())


@dataclass(frozen=True)
class AIConfig:
    """Configuration for the optional bring-your-own-key planning model."""

    model: str = ""
    api_key_env: str | None = None
    api_base: str | None = None
    api_version: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_output_tokens: int = 4096
    max_context_chars: int = 32000
    max_modules_per_run: int = 20
    cache: bool = True
    allowed_stages: tuple[str, ...] = ("planning", "feedback_analysis")
    max_repair_attempts: int = 2
    fallback: str = "deterministic"


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


@dataclass(frozen=True)
class AdapterPluginConfig:
    """An explicitly enabled versioned plugin for one adapter boundary."""

    kind: str
    name: str
    api_version: int = 1


@dataclass(frozen=True)
class ProtocolProfile:
    """Declarative naming profile used to recognize a handshake protocol."""

    name: str
    kind: str = "ready_valid"
    valid_suffix: str = "_valid"
    ready_suffix: str = "_ready"
    data_suffixes: tuple[str, ...] = ("_data", "_payload", "_bits")


@dataclass(frozen=True)
class VerificationDepthPolicy:
    """Explicit project intent required for otherwise ambiguous deep verification."""

    kind: str
    module: str
    subject: str
    parameters: tuple[tuple[str, str], ...] = ()

    def parameter(self, name: str) -> str | None:
        return next((value for key, value in self.parameters if key == name), None)


@dataclass(frozen=True)
class CoveragePolicy:
    """Configured minimum imported coverage percentages."""

    line_minimum: float | None = None
    branch_minimum: float | None = None
    toggle_minimum: float | None = None
    functional_minimum: float | None = None


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
