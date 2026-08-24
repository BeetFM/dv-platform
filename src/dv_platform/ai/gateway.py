"""Reusable staged LiteLLM gateway with deterministic, fail-closed fallback."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dv_platform.ai.model_client import (
    AIPlanningError,
    LiteLLMModelClient,
    ModelClient,
    ModelRequest,
    ModelResponse,
    _provider_exception,
)
from dv_platform.ai.optimization import OptimizationMetrics, optimize_model_prompt
from dv_platform.ai.routing import DataClass, PolicyRouter, RoutingAttempt, load_routing_policy
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig
from dv_platform.core.security import resolve_secret
from dv_platform.product import resolve_configured_product_plan
from dv_platform.signing import verify_signed_document


@dataclass(frozen=True)
class GatewayResult:
    stage: str
    status: str
    attempts: int
    context_hash: str
    prompt_hash: str
    proposal_hash: str | None
    response: ModelResponse | None = None
    validation_results: tuple[str, ...] = ()
    fallback_reason: str | None = None
    run_id: str | None = None
    run_record_path: Path | None = None
    optimization_metrics: tuple[OptimizationMetrics, ...] = ()
    provider: str | None = None
    model_snapshot: str | None = None
    endpoint: str | None = None
    routing_attempts: tuple[RoutingAttempt, ...] = ()


class LiteLLMGateway:
    """One configured model, same-model bounded repair, and deterministic fallback."""

    def __init__(self, config: CLIConfig, client: ModelClient | None = None) -> None:
        self.config = config
        self.client = client or LiteLLMModelClient()

    def execute(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        context: str,
        validate: Callable[[str], None] | None = None,
    ) -> GatewayResult:
        context_hash = _hash(context)
        prompt_hash = _hash(system_prompt + "\n" + user_prompt)
        unavailable = self._preflight_fallback(stage, context_hash, prompt_hash)
        if unavailable is not None:
            return self._record(unavailable)
        if self.config.ai.routing_policy_path is not None:
            return self._record(
                self._execute_routed(
                    stage=stage,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                    context_hash=context_hash,
                    prompt_hash=prompt_hash,
                    validate=validate,
                )
            )
        api_key = resolve_secret(self.config, self.config.ai.api_key_env) if self.config.ai.api_key_env else None
        if self.config.ai.api_key_env and not api_key:
            return self._record(self._fallback(stage, context_hash, prompt_hash, "credential_missing"))
        optimized_user_prompt, optimization_metrics = optimize_model_prompt(
            self.config,
            stage=stage,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        prompt_hash = _hash(system_prompt + "\n" + optimized_user_prompt)
        optimizer_failure = self._optimizer_fallback(stage, context_hash, prompt_hash, optimization_metrics)
        if optimizer_failure is not None:
            return self._record(optimizer_failure)
        return self._record(
            self._run_with_repair(
                stage=stage,
                system_prompt=system_prompt,
                user_prompt=optimized_user_prompt,
                response_schema=response_schema,
                context_hash=context_hash,
                prompt_hash=prompt_hash,
                api_key=api_key,
                validate=validate,
                metrics=optimization_metrics,
            )
        )

    def _execute_routed(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        context_hash: str,
        prompt_hash: str,
        validate: Callable[[str], None] | None,
    ) -> GatewayResult:
        policy_path = self.config.ai.routing_policy_path
        trust_root = self.config.ai.routing_trust_root
        if policy_path is None or trust_root is None:
            return self._fallback(stage, context_hash, prompt_hash, "routing_policy_incomplete")
        try:
            document = json.loads(policy_path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("AI routing policy must be an object")
            policy = load_routing_policy(
                document,
                verify_signature=lambda value: verify_signed_document(value, policy_path, trust_root),
            )
            optimized, metrics = optimize_model_prompt(
                self.config,
                stage=stage,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            credentials = {
                cell.provider: secret
                for cell in policy.cells
                if cell.credential_env is not None
                and (secret := resolve_secret(self.config, cell.credential_env)) is not None
            }
            request = ModelRequest(
                model="policy-routed",
                system_prompt=system_prompt,
                user_prompt=optimized,
                response_schema=response_schema,
                api_key=None,
                api_base=None,
                api_version=None,
                timeout_seconds=self.config.ai.timeout_seconds,
                max_retries=0,
                max_output_tokens=self.config.ai.max_output_tokens,
            )
            routed = PolicyRouter(
                policy,
                {cell.provider: self.client for cell in policy.cells},
                credentials=credentials,
            ).execute(
                request,
                data_class=DataClass(self.config.ai.data_class),
                purpose=stage,
                destination=self.config.ai.destination,
                context_digest=context_hash,
                product_plan=resolve_configured_product_plan(self.config),
            )
            if validate is not None:
                validate(routed.response.content)
        except AIPlanningError as exc:
            return self._fallback(stage, context_hash, prompt_hash, exc.category)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._fallback(stage, context_hash, prompt_hash, "routing_policy_invalid", diagnostics=(str(exc),))
        return GatewayResult(
            stage=stage,
            status="accepted",
            attempts=len(routed.attempts),
            context_hash=context_hash,
            prompt_hash=_hash(system_prompt + "\n" + optimized),
            proposal_hash=_hash(routed.response.content),
            response=routed.response,
            optimization_metrics=metrics,
            provider=routed.provider,
            model_snapshot=routed.model_snapshot,
            endpoint=next(cell.endpoint for cell in policy.cells if cell.provider == routed.provider),
            routing_attempts=routed.attempts,
        )

    def _run_with_repair(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        context_hash: str,
        prompt_hash: str,
        api_key: str | None,
        validate: Callable[[str], None] | None,
        metrics: tuple[OptimizationMetrics, ...],
    ) -> GatewayResult:
        diagnostics: list[str] = []
        attempts = self.config.ai.max_repair_attempts + 1
        for attempt in range(1, attempts + 1):
            fallback = self._attempt_request(
                stage=stage,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=response_schema,
                context_hash=context_hash,
                prompt_hash=prompt_hash,
                api_key=api_key,
                attempt=attempt,
                validate=validate,
                diagnostics=diagnostics,
            )
            if fallback is not None:
                return self._with_optimization(fallback, metrics)
        return self._with_optimization(
            self._fallback(stage, context_hash, prompt_hash, "repair_attempts_exhausted", attempts, tuple(diagnostics)),
            metrics,
        )

    def _attempt_request(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        context_hash: str,
        prompt_hash: str,
        api_key: str | None,
        attempt: int,
        validate: Callable[[str], None] | None,
        diagnostics: list[str],
    ) -> GatewayResult | None:
        request = self._build_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema,
            api_key=api_key,
            diagnostics=diagnostics,
        )
        try:
            response = self.client.complete(request)
            if validate is not None:
                validate(response.content)
        except AIPlanningError as error:
            if error.category != "invalid_response":
                return self._fallback(stage, context_hash, prompt_hash, error.category, attempt, tuple(diagnostics))
            diagnostics.append(str(error))
            return None
        except (ValueError, json.JSONDecodeError) as error:
            diagnostics.append(str(error))
            return None
        except Exception as error:
            mapped = _provider_exception(error)
            return self._fallback(stage, context_hash, prompt_hash, mapped.category, attempt, tuple(diagnostics))
        return GatewayResult(
            stage=stage,
            status="accepted",
            attempts=attempt,
            context_hash=context_hash,
            prompt_hash=prompt_hash,
            proposal_hash=_hash(response.content),
            response=response,
            validation_results=tuple(diagnostics),
        )

    def _build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
        api_key: str | None,
        diagnostics: list[str],
    ) -> ModelRequest:
        repair = ""
        if diagnostics:
            repair = "\nReturn a corrected object. Validation errors: " + "; ".join(diagnostics[-1:])
        return ModelRequest(
            model=self.config.ai.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt + repair,
            response_schema=response_schema,
            api_key=api_key,
            api_base=self.config.ai.api_base,
            api_version=self.config.ai.api_version,
            timeout_seconds=self.config.ai.timeout_seconds,
            max_retries=self.config.ai.max_retries,
            max_output_tokens=self.config.ai.max_output_tokens,
        )

    def _preflight_fallback(self, stage: str, context_hash: str, prompt_hash: str) -> GatewayResult | None:
        reason = None
        if stage not in self.config.ai.allowed_stages:
            reason = "stage_not_allowed"
        elif not self.config.allow_network:
            reason = "network_denied"
        elif not self.config.ai.model:
            reason = "model_not_configured"
        if reason is None:
            return None
        return self._fallback(stage, context_hash, prompt_hash, reason)

    def _optimizer_fallback(
        self,
        stage: str,
        context_hash: str,
        prompt_hash: str,
        metrics: tuple[OptimizationMetrics, ...],
    ) -> GatewayResult | None:
        if not self.config.ci:
            return None
        for item in metrics:
            if item.optimizer == "headroom" and item.status != "compressed":
                return self._with_optimization(
                    self._fallback(stage, context_hash, prompt_hash, "headroom_optimization_failed"),
                    metrics,
                )
        return None

    def _record(self, result: GatewayResult) -> GatewayResult:
        run_id = uuid.uuid4().hex
        path = self.config.work_dir / "ai" / "runs" / run_id / f"{result.stage}.json"
        response = result.response
        payload = {
            "schema_version": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "purpose": result.stage,
            "endpoint": result.endpoint or _endpoint_identity(self.config.ai.api_base),
            "model": result.model_snapshot or self.config.ai.model,
            "provider": result.provider,
            "context_hash": result.context_hash,
            "prompt_hash": result.prompt_hash,
            "proposal_hash": result.proposal_hash,
            "cache_status": "not_applicable",
            "status": result.status,
            "attempts": result.attempts,
            "validation_diagnostics": list(result.validation_results),
            "token_usage": {
                "prompt": response.prompt_tokens if response is not None else None,
                "completion": response.completion_tokens if response is not None else None,
                "total": response.total_tokens if response is not None else None,
            },
            "cost": response.cost if response is not None else None,
            "provider_retry_count": response.retry_count if response is not None else 0,
            "fallback_reason": result.fallback_reason,
            "routing_attempts": [
                {
                    "provider": item.provider,
                    "model": item.model_snapshot,
                    "endpoint": _endpoint_identity(item.endpoint),
                    "region": item.region,
                    "status": item.status,
                    "diagnostic": item.diagnostic,
                    "prompt_tokens": item.prompt_tokens,
                    "completion_tokens": item.completion_tokens,
                    "cost": item.cost,
                }
                for item in result.routing_attempts
            ],
            "optimization": [item.to_json() for item in result.optimization_metrics],
        }
        atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        path.chmod(0o600)
        return GatewayResult(**{**result.__dict__, "run_id": run_id, "run_record_path": path})

    @staticmethod
    def _fallback(
        stage: str,
        context_hash: str,
        prompt_hash: str,
        reason: str,
        attempts: int = 0,
        diagnostics: tuple[str, ...] = (),
    ) -> GatewayResult:
        return GatewayResult(
            stage=stage,
            status="fallback",
            attempts=attempts,
            context_hash=context_hash,
            prompt_hash=prompt_hash,
            proposal_hash=None,
            validation_results=diagnostics,
            fallback_reason=reason,
        )

    @staticmethod
    def _with_optimization(result: GatewayResult, metrics: tuple[OptimizationMetrics, ...]) -> GatewayResult:
        return GatewayResult(**{**result.__dict__, "optimization_metrics": metrics})


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _endpoint_identity(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), host.lower(), parsed.path.rstrip("/"), "", ""))


for _legacy_class in (GatewayResult, LiteLLMGateway):
    _legacy_class.__module__ = "dv_platform.analysis.ai_gateway"
del _legacy_class
__name__ = "dv_platform.analysis.ai_gateway"
