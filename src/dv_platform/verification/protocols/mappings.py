"""Deterministic mapping registry between semantic intent and target checks."""

from __future__ import annotations

from dataclasses import dataclass

from dv_platform.core.models import VerificationTarget


@dataclass(frozen=True)
class CheckMapping:
    feature: str
    category: str
    target: VerificationTarget
    template: str
    executable: bool = True
    required_evidence: tuple[str, ...] = ()


_MAPPED_TARGETS = (
    VerificationTarget.COCOTB,
    VerificationTarget.SYSTEMVERILOG,
    VerificationTarget.FORMAL,
)

CHECK_MAPPINGS = tuple(
    CheckMapping(protocol, "protocol", target, f"{target.value}_{protocol.lower().replace('-', '_')}_protocol")
    for protocol in ("AXI4-Lite", "APB4", "AHB-Lite")
    for target in _MAPPED_TARGETS
) + tuple(
    CheckMapping("register", "register_access", target, f"{target.value}_register_access") for target in _MAPPED_TARGETS
)


def mappings_for(feature: str, target: VerificationTarget) -> tuple[CheckMapping, ...]:
    return tuple(item for item in CHECK_MAPPINGS if item.feature == feature and item.target == target)


def scenario_mapping_for(kind: str, target: VerificationTarget) -> str | None:
    """Return an executable renderer ID from the authoritative registry."""

    from dv_platform.core.models import ScenarioTargetState
    from dv_platform.verification.planning.targets import SCENARIO_RENDERERS

    registration = SCENARIO_RENDERERS.get(kind, target)
    return registration.renderer_id if registration.state == ScenarioTargetState.EXECUTABLE else None


for _name, _value in tuple(globals().items()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.agent.mappings"
