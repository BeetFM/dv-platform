"""Optional external prompt/context optimization boundaries."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dv_platform.core.models import CLIConfig


@dataclass(frozen=True)
class OptimizationMetrics:
    """Content-free optimizer provenance for AI run records."""

    stage: str
    optimizer: str
    status: str
    endpoint: str | None = None
    original_hash: str | None = None
    optimized_hash: str | None = None
    chars_before: int | None = None
    chars_after: int | None = None
    saved_chars: int | None = None
    tokens_before: int | None = None
    tokens_after: int | None = None
    saved_tokens: int | None = None
    transforms: tuple[str, ...] = ()
    reason: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "optimizer": self.optimizer,
            "status": self.status,
            "endpoint": self.endpoint,
            "original_hash": self.original_hash,
            "optimized_hash": self.optimized_hash,
            "chars_before": self.chars_before,
            "chars_after": self.chars_after,
            "saved_chars": self.saved_chars,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "saved_tokens": self.saved_tokens,
            "transforms": list(self.transforms),
            "reason": self.reason,
        }


class HeadroomClient:
    """Small stdlib client for a locally managed Headroom proxy."""

    def __init__(self, endpoint: str, timeout_seconds: float) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def compress_user_prompt(self, *, stage: str, system_prompt: str, user_prompt: str) -> tuple[str, OptimizationMetrics]:
        anchors = _required_anchors(user_prompt)
        original_hash = _hash(user_prompt)
        try:
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "compress": {"roles": ["user"]},
            }
            request = urllib.request.Request(
                f"{self.endpoint}/v1/compress",
                data=json.dumps(payload).encode("utf-8"),
                headers={"content-type": "application/json", "accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(4 * 1024 * 1024)
            parsed = json.loads(raw.decode("utf-8"))
            compressed = _compressed_user_content(parsed)
            if compressed is None:
                return user_prompt, _metrics(stage, "malformed_response", original_hash, user_prompt, user_prompt, self.endpoint)
            missing = tuple(anchor for anchor in anchors if anchor not in compressed)
            if missing:
                return (
                    user_prompt,
                    _metrics(
                        stage,
                        "anchor_removed",
                        original_hash,
                        user_prompt,
                        user_prompt,
                        self.endpoint,
                        reason="missing_required_anchor",
                    ),
                )
            metadata = parsed if isinstance(parsed, dict) else {}
            return compressed, _metrics(
                stage,
                "compressed",
                original_hash,
                user_prompt,
                compressed,
                self.endpoint,
                tokens_before=_optional_int(metadata.get("tokens_before")),
                tokens_after=_optional_int(metadata.get("tokens_after")),
                transforms=_string_tuple(metadata.get("transforms")),
            )
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as error:
            return user_prompt, _metrics(
                stage, "fallback", original_hash, user_prompt, user_prompt, self.endpoint, reason=type(error).__name__
            )


def optimize_model_prompt(
    config: CLIConfig,
    *,
    stage: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, tuple[OptimizationMetrics, ...]]:
    """Return an optimized user prompt when optional optimizers are enabled and applicable."""

    options = config.context_optimization
    if not _optimization_enabled_for_ai(config) or stage not in options.stages:
        return user_prompt, ()
    optimized, metrics = HeadroomClient(options.headroom_endpoint, options.headroom_timeout_seconds).compress_user_prompt(
        stage=stage,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    return optimized, (metrics,)


def optimizer_readiness(config: CLIConfig) -> dict[str, object]:
    """Report optimizer configuration and local availability without mutating project state."""

    options = config.context_optimization
    active = _optimization_enabled_for_ai(config)
    return {
        "enabled": active,
        "stages": list(options.stages),
        "headroom": {
            "enabled": active,
            "endpoint": _endpoint_identity(options.headroom_endpoint),
            "health": _headroom_health(options) if active else "disabled",
        },
    }


def _optimization_enabled_for_ai(config: CLIConfig) -> bool:
    return bool(config.ai.model.strip())


def _headroom_health(options) -> str:
    try:
        request = urllib.request.Request(f"{options.headroom_endpoint.rstrip('/')}/health", method="GET")
        with urllib.request.urlopen(request, timeout=min(options.headroom_timeout_seconds, 2.0)) as response:
            return "available" if 200 <= response.status < 500 else "unavailable"
    except Exception:
        return "unavailable"


def _compressed_user_content(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("compressed_prompt", "compressed", "content", "text", "output"):
            if isinstance(payload.get(key), str):
                return payload[key]
        messages = payload.get("messages") or payload.get("compressed_messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict) and message.get("role") == "user" and isinstance(message.get("content"), str):
                    return message["content"]
    return None


def _required_anchors(user_prompt: str) -> tuple[str, ...]:
    anchors = {"<UNTRUSTED_EVIDENCE_DATA>", "</UNTRUSTED_EVIDENCE_DATA>"}
    anchors.update(re.findall(r"\bE\d{4}\b", user_prompt))
    for pattern in (r"module\s+([A-Za-z_$][A-Za-z0-9_$]*)", r"schema version\s+(\d+)"):
        match = re.search(pattern, user_prompt)
        if match:
            anchors.add(match.group(1))
    return tuple(sorted(anchors))


def _metrics(
    stage: str,
    status: str,
    original_hash: str,
    original_prompt: str,
    prompt: str,
    endpoint: str,
    *,
    tokens_before: int | None = None,
    tokens_after: int | None = None,
    transforms: tuple[str, ...] = (),
    reason: str | None = None,
) -> OptimizationMetrics:
    before_chars = len(original_prompt)
    after_chars = len(prompt)
    return OptimizationMetrics(
        stage=stage,
        optimizer="headroom",
        status=status,
        endpoint=_endpoint_identity(endpoint),
        original_hash=original_hash,
        optimized_hash=_hash(prompt),
        chars_before=before_chars,
        chars_after=after_chars,
        saved_chars=(before_chars - after_chars) if before_chars is not None else None,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        saved_tokens=(tokens_before - tokens_after) if tokens_before is not None and tokens_after is not None else None,
        transforms=transforms,
        reason=reason,
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


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list) else ()
