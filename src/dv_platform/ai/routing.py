"""Policy-pinned, classification-aware multi-provider routing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol

from dv_platform.ai.model_client import AIPlanningError, ModelRequest, ModelResponse
from dv_platform.product import ResolvedProductPlan


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


RETRYABLE_FAILURES = frozenset({"timeout", "rate_limited", "provider_unavailable", "provider_error"})


@dataclass(frozen=True)
class ProviderCell:
    provider: str
    model_snapshot: str
    endpoint: str
    destination: str
    region: str
    credential_env: str | None
    allowed_data_classes: frozenset[DataClass]
    allowed_purposes: frozenset[str]
    retention: str
    per_request_cost_limit: float
    daily_cost_limit: float
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.provider not in {"openai", "anthropic", "moonshot"}:
            raise ValueError("provider is not approved")
        if not _exact_snapshot(self.model_snapshot):
            raise ValueError("model aliases are forbidden; configure an exact model snapshot")
        if not self.endpoint.startswith("https://") or not self.destination or not self.region:
            raise ValueError("provider endpoint, destination, and region must be pinned")
        if self.per_request_cost_limit <= 0 or self.daily_cost_limit < self.per_request_cost_limit:
            raise ValueError("provider cost limits are invalid")
        if self.provider == "moonshot" and "k3" in self.model_snapshot.lower() and not self.enabled:
            return


@dataclass(frozen=True)
class RoutingPolicy:
    policy_version: str
    cells: tuple[ProviderCell, ...]
    order: tuple[str, ...] = ("openai", "anthropic", "moonshot")

    def __post_init__(self) -> None:
        if not self.policy_version or tuple(cell.provider for cell in self.cells) != self.order:
            raise ValueError("routing cells must exactly match the pinned routing order")


def load_routing_policy(
    document: dict[str, Any],
    *,
    verify_signature: Callable[[dict[str, Any]], bool] | None = None,
) -> RoutingPolicy:
    """Parse a closed, deployment-signed provider policy."""

    fields = {"schema_version", "policy_version", "order", "cells", "signature"}
    if set(document) != fields or document.get("schema_version") != 1:
        raise ValueError("AI routing policy has unknown, missing, or unsupported fields")
    if verify_signature is not None and not verify_signature(document):
        raise ValueError("AI routing policy signature is invalid")
    order = document.get("order")
    cells = document.get("cells")
    if order != ["openai", "anthropic", "moonshot"] or not isinstance(cells, list) or len(cells) != 3:
        raise ValueError("AI routing policy must contain the exact provider order")
    parsed: list[ProviderCell] = []
    cell_fields = {
        "provider",
        "model_snapshot",
        "endpoint",
        "destination",
        "region",
        "credential_env",
        "allowed_data_classes",
        "allowed_purposes",
        "retention",
        "per_request_cost_limit",
        "daily_cost_limit",
        "enabled",
    }
    for raw in cells:
        if not isinstance(raw, dict) or set(raw) != cell_fields:
            raise ValueError("AI provider cell is not closed")
        classes = raw["allowed_data_classes"]
        purposes = raw["allowed_purposes"]
        if not isinstance(classes, list) or not isinstance(purposes, list) or not purposes:
            raise ValueError("AI provider data classes and purposes must be non-empty lists")
        parsed.append(
            ProviderCell(
                provider=str(raw["provider"]),
                model_snapshot=str(raw["model_snapshot"]),
                endpoint=str(raw["endpoint"]),
                destination=str(raw["destination"]),
                region=str(raw["region"]),
                credential_env=str(raw["credential_env"]) if raw["credential_env"] is not None else None,
                allowed_data_classes=frozenset(DataClass(str(item)) for item in classes),
                allowed_purposes=frozenset(str(item) for item in purposes),
                retention=str(raw["retention"]),
                per_request_cost_limit=float(raw["per_request_cost_limit"]),
                daily_cost_limit=float(raw["daily_cost_limit"]),
                enabled=raw["enabled"] is True,
            )
        )
    return RoutingPolicy(str(document["policy_version"]), tuple(parsed), tuple(order))


@dataclass(frozen=True)
class RoutingAttempt:
    provider: str
    model_snapshot: str
    endpoint: str
    region: str
    status: str
    diagnostic: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None


@dataclass(frozen=True)
class RoutedResponse:
    response: ModelResponse
    provider: str
    model_snapshot: str
    attempts: tuple[RoutingAttempt, ...]
    cache_key: str


class RoutedClient(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


class PolicyRouter:
    """Continue only for availability failures; never cross a policy boundary."""

    def __init__(
        self,
        policy: RoutingPolicy,
        clients: Mapping[str, RoutedClient],
        *,
        credentials: Mapping[str, str],
        spent_today: Mapping[str, float] | None = None,
    ) -> None:
        self.policy = policy
        self.clients = clients
        self.credentials = credentials
        self.spent_today = spent_today or {}

    def execute(
        self,
        request: ModelRequest,
        *,
        data_class: DataClass,
        purpose: str,
        destination: str,
        context_digest: str,
        product_plan: ResolvedProductPlan,
    ) -> RoutedResponse:
        attempts: list[RoutingAttempt] = []
        for cell in self.policy.cells:
            reason = self._ineligible(cell, data_class, purpose, destination, product_plan)
            if reason is not None:
                attempts.append(_attempt(cell, "skipped", reason))
                continue
            credential = self.credentials.get(cell.provider)
            routed = ModelRequest(
                model=cell.model_snapshot,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                response_schema=request.response_schema,
                api_key=credential,
                api_base=cell.endpoint,
                api_version=request.api_version,
                timeout_seconds=request.timeout_seconds,
                max_retries=0,
                max_output_tokens=request.max_output_tokens,
            )
            try:
                response = self.clients[cell.provider].complete(routed)
            except AIPlanningError as exc:
                attempts.append(_attempt(cell, "failed", exc.category))
                if exc.category in RETRYABLE_FAILURES:
                    continue
                raise
            if response.cost is None or response.cost > cell.per_request_cost_limit:
                raise AIPlanningError("cost_policy", "provider did not return acceptable bounded cost evidence")
            attempts.append(
                RoutingAttempt(
                    cell.provider,
                    cell.model_snapshot,
                    cell.endpoint,
                    cell.region,
                    "accepted",
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    cost=response.cost,
                )
            )
            key = routing_cache_key(
                cell,
                self.policy.policy_version,
                data_class,
                purpose,
                destination,
                request.system_prompt,
                request.user_prompt,
                context_digest,
            )
            return RoutedResponse(response, cell.provider, cell.model_snapshot, tuple(attempts), key)
        raise AIPlanningError("provider_unavailable", "no eligible provider route succeeded")

    def _ineligible(
        self,
        cell: ProviderCell,
        data_class: DataClass,
        purpose: str,
        destination: str,
        plan: ResolvedProductPlan,
    ) -> str | None:
        if not cell.enabled:
            return "route_disabled"
        if data_class is DataClass.RESTRICTED:
            return "restricted_data_local_only"
        if data_class not in cell.allowed_data_classes or purpose not in cell.allowed_purposes:
            return "data_policy"
        if destination != cell.destination:
            return "destination_mismatch"
        if cell.credential_env and cell.provider not in self.credentials:
            return "credential_missing"
        if self.spent_today.get(cell.provider, 0.0) >= cell.daily_cost_limit:
            return "daily_cost_limit"
        if cell.provider == "anthropic" and "ai.provider.anthropic" not in plan.capabilities:
            return "entitlement_missing"
        if cell.provider == "moonshot" and "ai.provider.moonshot" not in plan.capabilities:
            return "entitlement_missing"
        return None


def routing_cache_key(
    cell: ProviderCell,
    policy_version: str,
    data_class: DataClass,
    purpose: str,
    destination: str,
    system_prompt: str,
    user_prompt: str,
    context_digest: str,
) -> str:
    parts = (
        cell.provider,
        cell.model_snapshot,
        destination,
        cell.region,
        data_class.value,
        purpose,
        policy_version,
        sha256(system_prompt.encode()).hexdigest(),
        sha256(user_prompt.encode()).hexdigest(),
        context_digest,
    )
    return sha256("\0".join(parts).encode()).hexdigest()


def _exact_snapshot(model: str) -> bool:
    lowered = model.lower()
    return (
        bool(model)
        and not lowered.endswith(("-latest", "/latest", ":latest"))
        and lowered
        not in {
            "gpt-4",
            "gpt-5",
            "claude",
            "kimi",
            "kimi-k3",
        }
    )


def _attempt(cell: ProviderCell, status: str, diagnostic: str) -> RoutingAttempt:
    return RoutingAttempt(cell.provider, cell.model_snapshot, cell.endpoint, cell.region, status, diagnostic)
