# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Optional, evidence-bounded AI augmentation for deterministic plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dv_platform.core.models import (
    EvidenceRef,
    VerificationPlan,
)

AGENT_VERSION = "litellm-gateway-v2"
PROMPT_VERSION = "planning-proposal-v2"
PROPOSAL_SCHEMA_VERSION = 2
RUN_RECORD_SCHEMA_VERSION = 2
CACHE_SCHEMA_VERSION = 1
MAX_PROPOSAL_ITEMS = 100
MAX_STATEMENT_CHARS = 4096
MAX_SMALL_VALUE_CHARS = 512
SOURCE_CONTEXT_RADIUS = 3
MAX_SOURCE_SNIPPETS = 24
MAX_SOURCE_SNIPPET_LINES = 12


@dataclass(frozen=True)
class ProposalRequirement:
    proposal_id: str
    statement: str
    signals: tuple[str, ...]
    condition: str | None
    expected_value: str | None
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProposalCheck:
    proposal_id: str
    statement: str
    requirement_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProposalNote:
    statement: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProposalScenario:
    """Evidence-backed intent only; providers cannot supply source code, paths, or commands."""

    proposal_id: str
    kind: str
    requirement_ids: tuple[str, ...]
    check_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PlanningProposal:
    schema_version: int
    module: str
    requirements: tuple[ProposalRequirement, ...]
    checks: tuple[ProposalCheck, ...]
    scenarios: tuple[ProposalScenario, ...]
    assumptions: tuple[ProposalNote, ...]
    open_questions: tuple[ProposalNote, ...]


@dataclass(frozen=True)
class PlanningContext:
    text: str
    context_hash: str
    evidence_by_id: dict[str, EvidenceRef]
    known_signals: frozenset[str]


@dataclass(frozen=True)
class AIPlanningRunResult:
    plans: tuple[VerificationPlan, ...]
    requested_modules: int
    augmented_modules: int
    fallback_modules: int
    cache_hit_modules: int
    run_record_paths: tuple[Path, ...]
    run_id: str


for _legacy_class in (
    ProposalRequirement,
    ProposalCheck,
    ProposalNote,
    ProposalScenario,
    PlanningProposal,
    PlanningContext,
    AIPlanningRunResult,
):
    _legacy_class.__module__ = "dv_platform.analysis.ai_planning"
del _legacy_class
