"""Private Enterprise distribution.

Implementations are imported lazily so entitlement resolution can happen before
plugin discovery, environment access, or tool execution.
"""

from __future__ import annotations

from pathlib import Path

from dv_platform.product import ResolvedProductPlan, activate_product_plan, resolve_product_plan

__version__ = "1.0.0rc3"


def activate(
    *,
    entitlement: Path,
    trust_policy: Path,
    organization: str | None = None,
) -> ResolvedProductPlan:
    """Verify and activate an Enterprise plan before importing implementations."""

    plan = resolve_product_plan(
        entitlement=entitlement,
        trust_policy=trust_policy,
        organization=organization,
    )
    activate_product_plan(plan)
    return plan
