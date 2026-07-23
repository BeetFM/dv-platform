# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Optional, evidence-bounded AI augmentation for deterministic plans."""

from __future__ import annotations

import importlib
import importlib.util
import json
import math
from dataclasses import dataclass
from typing import Any, Protocol

from dv_platform.core.config import validate_ai_config
from dv_platform.core.models import (
    CLIConfig,
)
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


class AIPlanningError(RuntimeError):
    """An expected model-planning failure with a stable public category."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class ModelRequest:
    model: str
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any]
    api_key: str | None
    api_base: str | None
    api_version: str | None
    timeout_seconds: float
    max_retries: int
    max_output_tokens: int


@dataclass(frozen=True)
class ModelResponse:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    retry_count: int = 0
    structured_output: bool = False


class ModelClient(Protocol):
    """Narrow boundary used by the planner and network-free test doubles."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Return one module proposal response."""


class LiteLLMModelClient:
    """Lazily imported LiteLLM client with no callbacks, tools, or fallback models."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            litellm = importlib.import_module("litellm")
        except ImportError as error:
            raise AIPlanningError("dependency_missing", "LiteLLM is not installed; install dv-platform[ai].") from error

        structured_output = _supports_response_schema(litellm, request.model)
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "timeout": request.timeout_seconds,
            "num_retries": request.max_retries,
            "temperature": 0,
        }
        if request.api_key is not None:
            kwargs["api_key"] = request.api_key
        if request.api_base is not None:
            kwargs["api_base"] = request.api_base
        if request.api_version is not None:
            kwargs["api_version"] = request.api_version
        if structured_output:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "planning_proposal",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }

        try:
            response = litellm.completion(**kwargs)
        except Exception as error:
            raise _provider_exception(error) from error

        content = _response_content(response)
        usage = _attribute_or_key(response, "usage")
        cost: float | None = None
        completion_cost = getattr(litellm, "completion_cost", None)
        if callable(completion_cost):
            try:
                calculated = completion_cost(completion_response=response)
                candidate_cost = float(calculated) if calculated is not None else None
                cost = candidate_cost if candidate_cost is not None and math.isfinite(candidate_cost) else None
            except Exception:
                cost = None
        return ModelResponse(
            content=content,
            prompt_tokens=_optional_int(_attribute_or_key(usage, "prompt_tokens")),
            completion_tokens=_optional_int(_attribute_or_key(usage, "completion_tokens")),
            total_tokens=_optional_int(_attribute_or_key(usage, "total_tokens")),
            cost=cost,
            retry_count=_optional_int(_attribute_or_key(response, "retry_count")) or 0,
            structured_output=structured_output,
        )


def ai_dependency_available() -> bool:
    """Check optional dependency availability without importing LiteLLM."""

    return importlib.util.find_spec("litellm") is not None


def ai_readiness(config: CLIConfig) -> dict[str, object]:
    """Report local AI readiness without importing or contacting a provider."""

    api_key_env = config.ai.api_key_env
    key_required = api_key_env is not None
    key_present = bool(resolve_secret(config, api_key_env)) if api_key_env is not None else None
    configuration_errors = tuple(
        diagnostic.message for diagnostic in validate_ai_config(config.ai) if diagnostic.severity == "error"
    )
    configured = not configuration_errors
    dependency = ai_dependency_available()
    return {
        "dependency_available": dependency,
        "configured": configured,
        "configuration_errors": list(configuration_errors),
        "model": config.ai.model or None,
        "provider": _provider_name(config.ai.model) if configured else None,
        "api_key_env": config.ai.api_key_env,
        "credential_required": key_required,
        "credential_present": key_present,
        "network_allowed": config.allow_network,
        "cache_enabled": config.ai.cache,
        "stages": {
            "planning": "active" if "planning" in config.ai.allowed_stages else "disabled",
            "scenario_synthesis": "active" if "scenario_synthesis" in config.ai.allowed_stages else "disabled",
            "feedback_analysis": "active" if "feedback_analysis" in config.ai.allowed_stages else "disabled",
        },
        "ready_for_live_request": bool(
            dependency and configured and config.allow_network and (not key_required or key_present)
        ),
    }


def _provider_exception(error: Exception) -> AIPlanningError:
    name = type(error).__name__.lower()
    message = str(error)
    normalized = message.lower()
    if isinstance(error, (TimeoutError,)) or "timeout" in name or "timed out" in normalized:
        category = "timeout"
    elif "authentication" in name or "permissiondenied" in name or "unauthorized" in normalized:
        category = "authentication_failed"
    elif "ratelimit" in name or "rate limit" in normalized or "too many requests" in normalized:
        category = "rate_limited"
    elif isinstance(error, (json.JSONDecodeError, UnicodeDecodeError)):
        category = "invalid_response"
    else:
        category = "provider_error"
    return AIPlanningError(category, message or type(error).__name__)


def _supports_response_schema(litellm: Any, model: str) -> bool:
    capability = getattr(litellm, "supports_response_schema", None)
    if not callable(capability):
        return False
    try:
        return bool(capability(model=model))
    except Exception:
        return False


def _response_content(response: object) -> str:
    choices = _attribute_or_key(response, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        raise AIPlanningError("invalid_response", "Provider response did not contain choices.")
    message = _attribute_or_key(choices[0], "message")
    content = _attribute_or_key(message, "content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            text = _attribute_or_key(item, "text")
            if isinstance(text, str):
                pieces.append(text)
        if pieces:
            return "".join(pieces)
    raise AIPlanningError("invalid_response", "Provider response did not contain textual JSON content.")


def _attribute_or_key(value: object, name: str) -> object:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _provider_name(model: str) -> str:
    prefix, separator, _remainder = model.partition("/")
    return prefix if separator and prefix else "unknown"


def _truncate(value: str | None, maximum: int) -> str | None:
    if value is None or len(value) <= maximum:
        return value
    return value[: maximum - 1] + "…"


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, (str, bytes, bytearray, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


for _legacy_class in (AIPlanningError, ModelRequest, ModelResponse, ModelClient, LiteLLMModelClient):
    _legacy_class.__module__ = "dv_platform.analysis.ai_planning"
del _legacy_class
