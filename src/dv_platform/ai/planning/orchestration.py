# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Optional, evidence-bounded AI augmentation for deterministic plans."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from dv_platform.core.config import validate_ai_config
from dv_platform.core.models import (
    AgentPlanProvenance,
    CLIConfig,
    DocumentationChunk,
    RTLModule,
    VerificationPlan,
)
from dv_platform.core.paths import validate_path_component
from dv_platform.core.security import resolve_secret

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


def augment_plans(
    config: CLIConfig,
    modules: tuple[RTLModule, ...],
    plans: tuple[VerificationPlan, ...],
    documentation_chunks: tuple[DocumentationChunk, ...],
    selected_modules: tuple[str, ...],
    *,
    refresh: bool = False,
    model_client: ModelClient | None = None,
) -> AIPlanningRunResult:
    """Augment selected module plans, preserving deterministic plans on every failure."""

    selected, modules_by_name, plans_by_name = _validated_ai_selection(config, modules, plans, selected_modules)
    run_id = uuid.uuid4().hex
    provider = _provider_name(config.ai.model)
    augmented = fallback = cache_hits = 0
    records = []
    for module_name in selected:
        updated, outcome = _augment_one_plan(
            config,
            modules_by_name[module_name],
            plans_by_name[module_name],
            documentation_chunks,
            run_id,
            provider,
            refresh,
            model_client,
        )
        plans_by_name[module_name] = updated
        augmented += int(outcome["augmented"])
        fallback += int(not outcome["augmented"])
        cache_hits += int(outcome["cache_hit"])
        records.append(outcome["record_path"])
    return AIPlanningRunResult(
        plans=tuple(plans_by_name[plan.module] for plan in plans),
        requested_modules=len(selected),
        augmented_modules=augmented,
        fallback_modules=fallback,
        cache_hit_modules=cache_hits,
        run_record_paths=tuple(records),
        run_id=run_id,
    )


def _validated_ai_selection(config, modules, plans, selected_modules):
    errors = tuple(diagnostic.message for diagnostic in validate_ai_config(config.ai) if diagnostic.severity == "error")
    if errors:
        raise ValueError("Invalid AI planning configuration: " + "; ".join(errors))
    selected = tuple(dict.fromkeys(selected_modules))
    maximum = min(20, config.ai.max_modules_per_run)
    if len(selected) > maximum:
        raise ValueError(f"AI planning selected {len(selected)} modules; the configured limit is {maximum}.")
    modules_by_name = {module.name: module for module in modules}
    plans_by_name = {plan.module: plan for plan in plans}
    unknown = tuple(name for name in selected if name not in modules_by_name or name not in plans_by_name)
    if unknown:
        raise ValueError(f"Unknown AI planning module selection: {', '.join(unknown)}")
    for module_name in selected:
        validate_path_component(module_name, "AI planning module")
    return selected, modules_by_name, plans_by_name


def _augment_one_plan(config, module, baseline, documentation_chunks, run_id, provider, refresh, client):
    started = time.monotonic()
    attempt = _planning_proposal_attempt(config, module, baseline, documentation_chunks, refresh, client)
    proposal = attempt["proposal"]
    accepted_requirements = ()
    accepted_checks = ()
    updated = baseline
    if proposal is not None:
        proposal_hash = _sha256_text(_canonical_json(_proposal_to_json(proposal)))
        attempt["proposal_hash"] = proposal_hash
        try:
            merged, accepted_requirements, accepted_checks = merge_proposal(
                module, baseline, proposal, attempt["context"].evidence_by_id
            )
            updated = replace(
                merged,
                agent_provenance=_agent_provenance(
                    config,
                    run_id,
                    provider,
                    attempt,
                    "augmented",
                    accepted_requirements,
                    accepted_checks,
                ),
            )
        except Exception as error:
            attempt["error_category"] = "invalid_response"
            attempt["error_message"] = _planning_error_message(config, attempt, str(error))
            proposal = None
            attempt["proposal"] = None
    if proposal is None:
        updated = replace(
            baseline,
            agent_provenance=_agent_provenance(config, run_id, provider, attempt, "fallback", (), ()),
        )
    record_path = _write_ai_planning_record(
        config,
        module.name,
        run_id,
        provider,
        attempt,
        accepted_requirements,
        accepted_checks,
        int((time.monotonic() - started) * 1000),
    )
    return updated, {
        "augmented": proposal is not None,
        "cache_hit": attempt["cache_status"] == "hit",
        "record_path": record_path,
    }


def _planning_proposal_attempt(config, module, baseline, documentation_chunks, refresh, client):
    context = build_planning_context(config, module, baseline, documentation_chunks)
    system_prompt, user_prompt = _prompts(module.name, context.text)
    prompt_hash = _sha256_text(system_prompt + "\n" + user_prompt)
    cache_key = _proposal_cache_key(config.ai, context.context_hash)
    cache_status = "disabled" if not config.ai.cache else "miss"
    proposal = None
    if "planning" in config.ai.allowed_stages and config.ai.cache and not refresh:
        proposal = _read_cached_proposal(config, cache_key, module, context)
        if proposal is not None:
            cache_status = "hit"
    attempt = {
        "context": context,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "prompt_hash": prompt_hash,
        "cache_key": cache_key,
        "cache_status": cache_status,
        "proposal": proposal,
        "proposal_hash": None,
        "response": None,
        "error_category": None,
        "error_message": None,
        "gateway_attempts": 0,
        "optimization_metrics": (),
    }
    if proposal is None:
        _request_planning_proposal(config, module, client, attempt)
    return attempt


def _request_planning_proposal(config, module, client, attempt) -> None:
    from dv_platform.ai.gateway import LiteLLMGateway

    context = attempt["context"]
    validated: PlanningProposal | None = None

    def validate_response(
        raw: str,
        module_name: str = module.name,
        evidence_ids: frozenset[str] = frozenset(context.evidence_by_id),
        signals: frozenset[str] = context.known_signals,
    ) -> None:
        nonlocal validated
        validated = validate_proposal(
            raw,
            module=module_name,
            evidence_ids=evidence_ids,
            known_signals=signals,
            max_chars=max(16_384, config.ai.max_output_tokens * 8),
        )

    result = LiteLLMGateway(config, client).execute(
        stage="planning",
        system_prompt=attempt["system_prompt"],
        user_prompt=attempt["user_prompt"],
        response_schema=proposal_json_schema(),
        context=context.text,
        validate=validate_response,
    )
    attempt["gateway_attempts"] = result.attempts
    attempt["prompt_hash"] = result.prompt_hash
    attempt["optimization_metrics"] = result.optimization_metrics
    attempt["response"] = result.response
    attempt["proposal"] = validated if result.status == "accepted" else None
    if attempt["proposal"] is not None and config.ai.cache:
        _write_cached_proposal(config, attempt["cache_key"], attempt["proposal"])
    if attempt["proposal"] is None:
        attempt["error_category"] = result.fallback_reason or "provider_error"
        diagnostic = result.validation_results[-1] if result.validation_results else attempt["error_category"]
        attempt["error_message"] = _planning_error_message(config, attempt, diagnostic)


def _planning_error_message(config, attempt, diagnostic):
    api_key = resolve_secret(config, config.ai.api_key_env) if config.ai.api_key_env else None
    return _sanitize_error(
        config,
        diagnostic,
        api_key,
        attempt["context"].text,
        attempt["system_prompt"],
        attempt["user_prompt"],
    )


def _agent_provenance(config, run_id, provider, attempt, status, requirements, checks):
    return AgentPlanProvenance(
        agent_version=AGENT_VERSION,
        prompt_version=PROMPT_VERSION,
        run_id=run_id,
        model=config.ai.model,
        provider=provider,
        context_hash=attempt["context"].context_hash,
        prompt_hash=attempt["prompt_hash"],
        proposal_hash=attempt["proposal_hash"],
        cache_key=attempt["cache_key"] if config.ai.cache else None,
        cache_status=attempt["cache_status"],
        status=status,
        error_category=(attempt["error_category"] or "provider_error") if status == "fallback" else None,
        accepted_requirement_ids=requirements,
        accepted_check_ids=checks,
    )


def _write_ai_planning_record(
    config,
    module_name,
    run_id,
    provider,
    attempt,
    accepted_requirements,
    accepted_checks,
    duration_ms,
):
    proposal = attempt["proposal"]
    response = attempt["response"]
    error_message = attempt["error_message"]
    record = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "module": module_name,
        "agent_version": AGENT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "provider": provider,
        "model": config.ai.model,
        "purpose": "planning",
        "endpoint": _safe_endpoint_identity(config.ai.api_base),
        "stage": "planning",
        "attempt": attempt["gateway_attempts"],
        "context_hash": attempt["context"].context_hash,
        "prompt_hash": attempt["prompt_hash"],
        "proposal_hash": attempt["proposal_hash"],
        "cache_key": attempt["cache_key"] if config.ai.cache else None,
        "cache_status": attempt["cache_status"],
        "status": "augmented" if proposal is not None else "fallback",
        "error_category": attempt["error_category"],
        "error_message": error_message,
        "fallback_reason": attempt["error_category"] if proposal is None else None,
        "validation_results": ["schema_valid", "evidence_valid", "semantic_merge_valid"]
        if proposal is not None
        else [],
        "validation_diagnostics": (
            ["schema_valid", "evidence_valid", "semantic_merge_valid"]
            if proposal is not None
            else ([error_message] if error_message else [])
        ),
        "duration_ms": duration_ms,
        "retry_count": response.retry_count if response is not None else 0,
        "token_usage": {
            "prompt": response.prompt_tokens if response is not None else None,
            "completion": response.completion_tokens if response is not None else None,
            "total": response.total_tokens if response is not None else None,
        },
        "cost": response.cost if response is not None else None,
        "structured_output": response.structured_output if response is not None else None,
        "optimization": [item.to_json() for item in attempt["optimization_metrics"]],
        "accepted_requirement_ids": list(accepted_requirements),
        "accepted_check_ids": list(accepted_checks),
    }
    path = config.work_dir / "ai" / "runs" / run_id / f"{validate_path_component(module_name)}.json"
    _owner_write_json(path, record)
    return path
