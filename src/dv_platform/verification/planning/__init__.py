# ruff: noqa: E402,F401,I001
"""Composition root for deterministic verification plan construction."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path

from dv_platform.agent.protocols import RegisterConflict, RegisterModel
from dv_platform.analysis.docs import EmbeddingProvider, VectorStore, retrieve_chunks, retrieve_chunks_with_vectors
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    RTLClock,
    RTLExpression,
    RTLModule,
    RTLPort,
    RTLProtocol,
    RTLReset,
    Severity,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)
from dv_platform.verification.planning.claims import (
    check_clock_claim,
    check_module_ports_claim,
    check_requirement_behavior_claim,
    check_reset_claim,
)
from dv_platform.verification.depth import build_depth_checks, validate_depth_policies
from dv_platform.verification.scenarios import build_deterministic_scenarios, link_scenario_coverage

from dv_platform.verification.planning import assembly as _part_0
from dv_platform.verification.planning import checks as _part_1
from dv_platform.verification.planning import requirements as _part_2
from dv_platform.verification.planning.assembly import create_initial_plan
from dv_platform.verification.planning.checks import (
    _build_check_details,
    _check_category,
    _check_is_executable,
    _check_structural_evidence,
    _plan_ports,
    _plan_clocks,
    _plan_resets,
    _requirement_driven_checks,
    _behaviors_from_patterns,
    _behavior_evidence_refs,
    _checks_for_behaviors,
    _checks_for_requirement,
    _checks_for_protocols,
    _checks_for_protocol_models,
    _protocol_transfer_check,
    _matching_ports,
    _mentions_any,
    _contains_term,
)
from dv_platform.verification.planning.requirements import (
    _retrieve_documentation_refs,
    _merge_imported_requirements,
    _synthesize_requirements,
    _find_requirement_conflicts,
    _conflict_claim,
    _conflict_open_question,
    _requirement_open_questions,
    _relevant_requirement_sentences,
    _structured_requirement_fragments,
    _markdown_cells,
    _table_requirement_statement,
    _walk_expressions,
    _canonical_requirement,
    _requirement_category,
    _requirement_expected_value,
    _requirement_condition,
    _requirement_summary,
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
del _part_0, _part_1, _part_2, _namespace, _part, _parts
