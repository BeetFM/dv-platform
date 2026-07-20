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


CHECK_MAPPINGS = tuple(
    CheckMapping(protocol, "protocol", target, f"{target.value}_{protocol}_protocol")
    for protocol in ("AXI4-Lite", "APB4", "AHB-Lite")
    for target in VerificationTarget
)

CHECK_MAPPINGS += tuple(
    CheckMapping("register", "register_access", target, f"{target.value}_register_access")
    for target in VerificationTarget
)


def mappings_for(feature: str, target: VerificationTarget) -> tuple[CheckMapping, ...]:
    return tuple(item for item in CHECK_MAPPINGS if item.feature == feature and item.target == target)
