# ruff: noqa: E402,F401,I001
"""Composition root for isolated AI planning subsystems."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import math
import re
import time
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from dv_platform.analysis.docs import retrieve_chunks
from dv_platform.core.config import validate_ai_config
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    AgentPlanningNote,
    AgentPlanProvenance,
    AIConfig,
    CLIConfig,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    VerificationCheck,
    VerificationPlan,
    VerificationRequirement,
)
from dv_platform.core.paths import is_within, validate_path_component
from dv_platform.core.security import redact_text, resolve_secret
from dv_platform.verification.planning import (
    _build_check_details,
    _check_category,
    _conflict_claim,
    _conflict_open_question,
    _find_requirement_conflicts,
    _requirement_category,
    _requirement_driven_checks,
    _requirement_open_questions,
)
from dv_platform.verification.scenarios import link_scenario_coverage, validate_scenario

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

from dv_platform.ai import model_client as _part_0
from dv_platform.ai import planning_contracts as _part_1
from dv_platform.ai import proposal_validation as _part_2
from dv_platform.ai import planning_context as _part_3
from dv_platform.ai import planning_orchestration as _part_4
from dv_platform.ai import proposal_merge as _part_5
from dv_platform.ai import proposal_cache as _part_6
from dv_platform.ai.model_client import (
    AIPlanningError,
    ModelRequest,
    ModelResponse,
    ModelClient,
    LiteLLMModelClient,
    ai_dependency_available,
    ai_readiness,
    _provider_exception,
    _supports_response_schema,
    _response_content,
    _attribute_or_key,
    _provider_name,
    _truncate,
    _optional_int,
)
from dv_platform.ai.planning_contracts import (
    ProposalRequirement,
    ProposalCheck,
    ProposalNote,
    ProposalScenario,
    PlanningProposal,
    PlanningContext,
    AIPlanningRunResult,
)
from dv_platform.ai.proposal_validation import (
    proposal_json_schema,
    validate_proposal,
    _parse_requirement,
    _parse_check,
    _parse_scenario,
    _parse_note,
    _bounded_list,
    _object,
    _known_fields,
    _required_fields,
    _bounded_string,
    _optional_bounded_string,
    _proposal_id,
    _unique_strings,
    _validated_evidence_ids,
    _strict_json_loads,
)
from dv_platform.ai.planning_context import (
    build_planning_context,
    _source_snippets,
    _bounded_context_json,
    _known_module_signals,
    _prompts,
    _source_line_number,
    _safe_display_path,
    _safe_endpoint_identity,
    _canonical_statement,
    _canonical_json,
    _sha256_text,
)
from dv_platform.ai.planning_orchestration import augment_plans
from dv_platform.ai.proposal_merge import merge_proposal
from dv_platform.ai.proposal_cache import (
    _proposal_cache_key,
    _read_cached_proposal,
    _write_cached_proposal,
    _proposal_to_json,
    _owner_write_json,
    _sanitize_error,
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
    _part_5,
    _part_6,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _legacy_class in (
    AIPlanningError,
    ProposalRequirement,
    ProposalCheck,
    ProposalNote,
    ProposalScenario,
    PlanningProposal,
    PlanningContext,
    ModelRequest,
    ModelResponse,
    LiteLLMModelClient,
    AIPlanningRunResult,
):
    _legacy_class.__module__ = "dv_platform.analysis.ai_planning"
del _part_0, _part_1, _part_2, _part_3, _part_4, _part_5, _part_6, _legacy_class, _namespace, _part, _parts
__name__ = "dv_platform.analysis.ai_planning"
