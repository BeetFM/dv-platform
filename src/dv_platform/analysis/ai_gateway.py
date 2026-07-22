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

from dv_platform.analysis.ai_planning import (
    AIPlanningError,
    LiteLLMModelClient,
    ModelClient,
    ModelRequest,
    ModelResponse,
    _provider_exception,
)
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig
from dv_platform.core.security import resolve_secret


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
        if stage not in self.config.ai.allowed_stages:
            return self._record(self._fallback(stage, context_hash, prompt_hash, "stage_not_allowed"))
        if not self.config.allow_network:
            return self._record(self._fallback(stage, context_hash, prompt_hash, "network_denied"))
        if not self.config.ai.model:
            return self._record(self._fallback(stage, context_hash, prompt_hash, "model_not_configured"))
        api_key = resolve_secret(self.config, self.config.ai.api_key_env) if self.config.ai.api_key_env else None
        if self.config.ai.api_key_env and not api_key:
            return self._record(self._fallback(stage, context_hash, prompt_hash, "credential_missing"))

        diagnostics: list[str] = []
        attempts = self.config.ai.max_repair_attempts + 1
        for attempt in range(1, attempts + 1):
            repair = ""
            if diagnostics:
                repair = "\nReturn a corrected object. Validation errors: " + "; ".join(diagnostics[-1:])
            request = ModelRequest(
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
            try:
                response = self.client.complete(request)
                if validate is not None:
                    validate(response.content)
            except AIPlanningError as error:
                if error.category != "invalid_response":
                    return self._record(
                        self._fallback(stage, context_hash, prompt_hash, error.category, attempt, tuple(diagnostics))
                    )
                diagnostics.append(str(error))
                continue
            except (ValueError, json.JSONDecodeError) as error:
                diagnostics.append(str(error))
                continue
            except Exception as error:
                mapped = _provider_exception(error)
                return self._record(
                    self._fallback(stage, context_hash, prompt_hash, mapped.category, attempt, tuple(diagnostics))
                )
            return self._record(
                GatewayResult(
                    stage=stage,
                    status="accepted",
                    attempts=attempt,
                    context_hash=context_hash,
                    prompt_hash=prompt_hash,
                    proposal_hash=_hash(response.content),
                    response=response,
                    validation_results=tuple(diagnostics),
                )
            )
        return self._record(
            self._fallback(stage, context_hash, prompt_hash, "repair_attempts_exhausted", attempts, tuple(diagnostics))
        )

    def _record(self, result: GatewayResult) -> GatewayResult:
        run_id = uuid.uuid4().hex
        path = self.config.work_dir / "ai" / "runs" / run_id / f"{result.stage}.json"
        response = result.response
        payload = {
            "schema_version": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "purpose": result.stage,
            "endpoint": _endpoint_identity(self.config.ai.api_base),
            "model": self.config.ai.model,
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
