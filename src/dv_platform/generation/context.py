"""Build the single validated context consumed by generation backends."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

from dv_platform.core.models import (
    CLIConfig,
    DocumentationChunk,
    EvidenceRef,
    RTLModule,
    VerificationPlan,
    VerificationRequirement,
    VerificationTarget,
)

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    raise TypeError(f"Render context contains unsupported value: {type(value).__name__}")


class RenderContextBuilder:
    """Combine normalized inputs into one nested, JSON-compatible mapping."""

    def build(
        self,
        *,
        rtl_module: RTLModule,
        plan: VerificationPlan,
        documentation: tuple[DocumentationChunk, ...] = (),
        requirements: tuple[VerificationRequirement, ...] = (),
        config: CLIConfig | None = None,
        provenance: tuple[EvidenceRef, ...] = (),
    ) -> dict[str, JsonValue]:
        if plan.module != rtl_module.name:
            raise ValueError(f"Plan module {plan.module!r} does not match RTL module {rtl_module.name!r}")
        context = {
            "schema_version": 1,
            "rtl": _json_value(rtl_module),
            "verification": _json_value(plan),
            "documentation": _json_value(documentation),
            "requirements": _json_value(requirements),
            "configuration": _json_value(config),
            "provenance": _json_value(provenance),
        }
        return _json_value(context)  # type: ignore[return-value]

    def build_for_target(
        self,
        *,
        target: VerificationTarget | str,
        plan: VerificationPlan,
        presentation: Mapping[str, object],
        rtl_module: RTLModule | None = None,
        documentation: tuple[DocumentationChunk, ...] = (),
        requirements: tuple[VerificationRequirement, ...] = (),
        config: CLIConfig | None = None,
        provenance: tuple[EvidenceRef, ...] = (),
    ) -> dict[str, JsonValue]:
        """Build the validated envelope consumed by one package-owned template."""

        if rtl_module is not None and plan.module != rtl_module.name:
            raise ValueError(f"Plan module {plan.module!r} does not match RTL module {rtl_module.name!r}")
        target_name = target.value if isinstance(target, VerificationTarget) else target
        if not target_name:
            raise ValueError("Render target must not be empty")
        context = {
            "schema_version": 1,
            "target": target_name,
            "rtl": _json_value(rtl_module),
            "verification": _json_value(plan),
            "documentation": _json_value(documentation),
            "requirements": _json_value(requirements),
            "configuration": _json_value(config),
            "provenance": _json_value(provenance),
            "presentation": _json_value(presentation),
        }
        return _json_value(context)  # type: ignore[return-value]


_CONTEXT_BUILDER = RenderContextBuilder()


def build_target_context(
    plan: VerificationPlan,
    target: VerificationTarget | str,
    presentation: Mapping[str, object],
) -> dict[str, JsonValue]:
    """Build a target envelope for generators that already hold normalized plan facts."""

    return _CONTEXT_BUILDER.build_for_target(target=target, plan=plan, presentation=presentation)
