"""Configuration and evidence models for the OpenROAD workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class EvidenceKind(StrEnum):
    CODE_GRAPH_CONTEXT = "code_graph_context"


@dataclass(frozen=True)
class EvidenceRef:
    """Traceable evidence for a claim, requirement, plan, or artifact."""

    kind: EvidenceKind
    source_id: str
    locator: str
    summary: str | None = None


@dataclass(frozen=True)
class ProductConfig:
    """Offline product entitlement and trust configuration."""

    organization: str | None = None
    entitlement_path: Path | None = None
    trust_policy_path: Path | None = None
    revocation_path: Path | None = None
    require_enterprise: bool = False
    required_physical_domains: tuple[str, ...] = ()
    signoff_trust_policy_path: Path | None = None
    require_production_signoff: bool = False


@dataclass(frozen=True)
class CLIConfig:
    """Local enterprise CLI configuration."""

    repo_root: Path
    work_dir: Path
    output_dir: Path
    allow_network: bool = False
    strict: bool = False
    ci: bool = False
    adapter_plugins: tuple[AdapterPluginConfig, ...] = ()
    audit_enabled: bool = True
    redact_patterns: tuple[str, ...] = ()
    approved_plugin_publishers: tuple[str, ...] = ()
    export_roots: tuple[Path, ...] = ()
    secret_provider: str = "environment"
    retention_days: int = 30
    product: ProductConfig = field(default_factory=lambda: ProductConfig())
    ai: AIConfig = field(default_factory=lambda: AIConfig())
    context_optimization: ContextOptimizationConfig = field(default_factory=lambda: ContextOptimizationConfig())


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
    allowed_stages: tuple[str, ...] = ("physical_design",)
    max_repair_attempts: int = 2
    fallback: str = "deterministic"
    routing_policy_path: Path | None = None
    routing_trust_root: Path | None = None
    data_class: str = "internal"
    destination: str = "external"


@dataclass(frozen=True)
class ContextOptimizationConfig:
    """Optional external context optimizers for AI calls."""

    headroom_mode: str = "off"
    code_graph_mode: str = "off"
    stages: tuple[str, ...] = ("physical_design",)
    headroom_endpoint: str = "http://127.0.0.1:8787"
    headroom_timeout_seconds: float = 5.0
    code_graph_command: str = "code-review-graph"
    code_graph_timeout_seconds: float = 10.0
    code_graph_max_context_chars: int = 4000
    code_graph_detail_level: str = "minimal"
    code_graph_auto_update: bool = False


@dataclass(frozen=True)
class AdapterPluginConfig:
    """An explicitly enabled versioned plugin for one adapter boundary."""

    kind: str
    name: str
    api_version: int = 1
    publisher: str | None = None
    package_sha256: str | None = None
    signature_kind: str | None = None
    signature_path: str | None = None
    certificate_identity: str | None = None
    certificate_issuer: str | None = None
    trust_root: str | None = None
