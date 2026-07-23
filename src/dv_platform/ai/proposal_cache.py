# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Optional, evidence-bounded AI augmentation for deterministic plans."""

from __future__ import annotations

import json
from pathlib import Path

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    AIConfig,
    CLIConfig,
    RTLModule,
)
from dv_platform.core.security import redact_text

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


def _proposal_cache_key(ai: AIConfig, context_hash: str) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "model": ai.model,
        "api_base": _safe_endpoint_identity(ai.api_base),
        "api_version": ai.api_version,
        "api_key_env": ai.api_key_env,
        "timeout_seconds": ai.timeout_seconds,
        "max_retries": ai.max_retries,
        "max_output_tokens": ai.max_output_tokens,
        "max_context_chars": ai.max_context_chars,
        "context_hash": context_hash,
    }
    return _sha256_text(_canonical_json(payload))


def _read_cached_proposal(
    config: CLIConfig,
    cache_key: str,
    module: RTLModule,
    context: PlanningContext,
) -> PlanningProposal | None:
    path = config.work_dir / "ai" / "cache" / f"{cache_key}.json"
    try:
        if not path.is_file() or path.stat().st_size > 1_048_576:
            return None
        wrapper = _strict_json_loads(path.read_text(encoding="utf-8"))
        if not isinstance(wrapper, dict) or set(wrapper) != {"schema_version", "proposal"}:
            return None
        if wrapper["schema_version"] != CACHE_SCHEMA_VERSION:
            return None
        return validate_proposal(
            wrapper["proposal"],
            module=module.name,
            evidence_ids=frozenset(context.evidence_by_id),
            known_signals=context.known_signals,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, AIPlanningError):
        return None


def _write_cached_proposal(config: CLIConfig, cache_key: str, proposal: PlanningProposal) -> Path:
    path = config.work_dir / "ai" / "cache" / f"{cache_key}.json"
    _owner_write_json(path, {"schema_version": CACHE_SCHEMA_VERSION, "proposal": _proposal_to_json(proposal)})
    return path


def _proposal_to_json(proposal: PlanningProposal) -> dict[str, object]:
    return {
        "schema_version": proposal.schema_version,
        "module": proposal.module,
        "requirements": [
            {
                "proposal_id": item.proposal_id,
                "statement": item.statement,
                "signals": list(item.signals),
                "condition": item.condition,
                "expected_value": item.expected_value,
                "evidence_ids": list(item.evidence_ids),
            }
            for item in proposal.requirements
        ],
        "checks": [
            {
                "proposal_id": item.proposal_id,
                "statement": item.statement,
                "requirement_ids": list(item.requirement_ids),
                "evidence_ids": list(item.evidence_ids),
            }
            for item in proposal.checks
        ],
        "scenarios": [
            {
                "proposal_id": item.proposal_id,
                "kind": item.kind,
                "requirement_ids": list(item.requirement_ids),
                "check_ids": list(item.check_ids),
                "evidence_ids": list(item.evidence_ids),
                "parameters": dict(item.parameters),
            }
            for item in proposal.scenarios
        ],
        "assumptions": [
            {"statement": item.statement, "evidence_ids": list(item.evidence_ids)} for item in proposal.assumptions
        ],
        "open_questions": [
            {"statement": item.statement, "evidence_ids": list(item.evidence_ids)} for item in proposal.open_questions
        ],
    }


def _owner_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def _sanitize_error(config: CLIConfig, message: str, *sensitive_values: str | None) -> str:
    sanitized = message
    for value in sorted((item for item in sensitive_values if item), key=len, reverse=True):
        sanitized = sanitized.replace(value, "[REDACTED]")
    return redact_text(config, sanitized)[:1000]
