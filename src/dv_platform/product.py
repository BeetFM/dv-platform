"""Fail-closed product capability resolution shared by public compatibility shims."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dv_platform.domain.models import CLIConfig

FREE_CAPABILITIES = frozenset(
    {
        "cli.public",
        "api.public",
        "plugin.coverage.ucis",
        "plugin.coverage.verilator",
        "provider.ai.openai",
    }
)

ENTERPRISE_CAPABILITIES = frozenset(
    {
        "cli.enterprise",
        "entitlement.status",
        "entitlement.verify",
        "adapter.enterprise",
        "evidence.enterprise.import",
        "board.arty_a7.qualify",
        "ai.executable.propose",
        "ai.executable.apply",
        "ai.provider.anthropic",
        "ai.provider.moonshot",
        "physical.fpga",
        "physical.asic.timing",
        "physical.asic.cdc_rdc",
        "physical.asic.power",
        "physical.asic.memory",
        "release.enterprise.publish",
    }
)

OPERATION_CAPABILITIES = {
    "cli.dv-platform": "cli.public",
    "cli.dv-enterprise": "cli.enterprise",
    "cli.entitlement.verify": "entitlement.verify",
    "cli.entitlement.status": "entitlement.status",
    "plugin.document_loader": "adapter.enterprise",
    "plugin.report_exporter": "adapter.enterprise",
    "plugin.redaction_policy": "adapter.enterprise",
    "plugin.semantic_importer": "evidence.enterprise.import",
    "plugin.requirements_importer": "evidence.enterprise.import",
    "plugin.simulator_runner": "adapter.enterprise",
    "plugin.formal_runner": "adapter.enterprise",
    "plugin.analyzer_runner": "adapter.enterprise",
    "plugin.physical_evidence_importer": "evidence.enterprise.import",
    "provider.openai": "provider.ai.openai",
    "provider.anthropic": "ai.provider.anthropic",
    "provider.moonshot": "ai.provider.moonshot",
    "ai.executable.propose": "ai.executable.propose",
    "ai.executable.apply": "ai.executable.apply",
    "board.arty_a7.qualify": "board.arty_a7.qualify",
    "physical.fpga.import": "physical.fpga",
    "physical.asic.timing.import": "physical.asic.timing",
    "physical.asic.cdc_rdc.import": "physical.asic.cdc_rdc",
    "physical.asic.power.import": "physical.asic.power",
    "physical.asic.memory.import": "physical.asic.memory",
    "release.enterprise.publish": "release.enterprise.publish",
    **{
        f"cli.public.{command}": "cli.public"
        for command in (
            "init",
            "index-docs",
            "analyze-rtl",
            "plan",
            "generate",
            "run",
            "coverage",
            "review",
            "feedback",
            "status",
            "context-optimize",
            "support-bundle",
            "purge",
            "backup",
            "migrate",
            "destroy",
        )
    },
    **{
        f"cli.enterprise.{command}": capability
        for command, capability in {
            "import-semantics": "evidence.enterprise.import",
            "import-requirements": "evidence.enterprise.import",
            "run": "adapter.enterprise",
            "status": "cli.enterprise",
            "qualify": "adapter.enterprise",
            "qualification-bundle": "adapter.enterprise",
            "qualification-policy": "adapter.enterprise",
            "profiles": "cli.enterprise",
            "benchmark": "adapter.enterprise",
            "qualify-external-design": "adapter.enterprise",
            "verify-evidence": "evidence.enterprise.import",
            "verify-qualification-signature": "evidence.enterprise.import",
            "qualification-signing-payload": "evidence.enterprise.import",
            "verify-protocol-trace": "evidence.enterprise.import",
        }.items()
    },
}

PLUGIN_CAPABILITIES = {
    operation.removeprefix("plugin."): capability
    for operation, capability in OPERATION_CAPABILITIES.items()
    if operation.startswith("plugin.")
}

_ACTIVE_PLAN: ResolvedProductPlan | None = None


class CapabilityDeniedError(PermissionError):
    """Stable error raised before an unavailable capability performs side effects."""

    code = "DV-CAPABILITY-DENIED"

    def __init__(self, capability_id: str, reason: str) -> None:
        self.capability_id = capability_id
        self.reason = reason
        super().__init__(f"{self.code}: capability {capability_id!r} is unavailable: {reason}")


@dataclass(frozen=True)
class ResolvedProductPlan:
    distribution: str
    organization: str | None
    plan: str
    capabilities: frozenset[str]
    entitlement_state: str
    concurrency_limit: int
    publication_allowed: bool
    diagnostics: tuple[str, ...] = ()

    def redacted(self) -> dict[str, object]:
        return {
            "distribution": self.distribution,
            "organization_configured": self.organization is not None,
            "plan": self.plan,
            "capabilities": sorted(self.capabilities),
            "entitlement_state": self.entitlement_state,
            "concurrency_limit": self.concurrency_limit,
            "publication_allowed": self.publication_allowed,
            "diagnostics": list(self.diagnostics),
        }


def resolve_product_plan(
    *,
    entitlement: Path | None = None,
    trust_policy: Path | None = None,
    organization: str | None = None,
    now: datetime | None = None,
    revoked_keys: Iterable[str] = (),
) -> ResolvedProductPlan:
    """Resolve Free or Enterprise without probing credentials, network, or plugins."""

    if entitlement is None:
        return ResolvedProductPlan("free", None, "free", FREE_CAPABILITIES, "not_configured", 1, False)
    if trust_policy is None:
        raise CapabilityDeniedError("cli.enterprise", "entitlement trust policy is not configured")

    from dv_platform.entitlement import verify_entitlement

    verified = verify_entitlement(
        entitlement,
        trust_policy,
        expected_organization=organization,
        now=now,
        revoked_keys=frozenset(revoked_keys),
    )
    capabilities = FREE_CAPABILITIES | verified.capabilities
    publication_allowed = verified.state == "valid" and "release.enterprise.publish" in capabilities
    return ResolvedProductPlan(
        "enterprise",
        verified.organization,
        verified.plan,
        capabilities,
        verified.state,
        verified.concurrency_limit,
        publication_allowed,
        verified.diagnostics,
    )


def resolve_configured_product_plan(
    config: CLIConfig,
    *,
    now: datetime | None = None,
    fail_invalid: bool = False,
) -> ResolvedProductPlan:
    """Resolve configuration without importing Enterprise code or credentials."""

    product = config.product
    try:
        return resolve_product_plan(
            entitlement=product.entitlement_path,
            trust_policy=product.trust_policy_path,
            organization=product.organization,
            now=now,
            revoked_keys=_configured_revocations(product.revocation_path),
        )
    except (CapabilityDeniedError, OSError, ValueError) as exc:
        if fail_invalid or product.require_enterprise:
            raise CapabilityDeniedError("cli.enterprise", str(exc)) from exc
        return ResolvedProductPlan(
            "free",
            product.organization,
            "invalid",
            FREE_CAPABILITIES,
            "invalid",
            1,
            False,
            (str(exc),),
        )


def capability_for_operation(operation_id: str) -> str:
    try:
        return OPERATION_CAPABILITIES[operation_id]
    except KeyError as exc:
        raise CapabilityDeniedError(operation_id, "operation is absent from the closed capability registry") from exc


def require_operation(plan: ResolvedProductPlan, operation_id: str, *, publication: bool = False) -> None:
    require_capability(plan, capability_for_operation(operation_id), publication=publication)


def require_capability(
    plan: ResolvedProductPlan,
    capability_id: str,
    *,
    publication: bool = False,
) -> None:
    """Fail before the caller imports an implementation or performs a side effect."""

    if capability_id not in FREE_CAPABILITIES | ENTERPRISE_CAPABILITIES:
        raise CapabilityDeniedError(capability_id, "unknown capability identifier")
    if capability_id not in plan.capabilities:
        raise CapabilityDeniedError(capability_id, "not granted by the resolved product plan")
    if publication and not plan.publication_allowed:
        raise CapabilityDeniedError(capability_id, "publication is blocked during entitlement grace")


def activate_product_plan(plan: ResolvedProductPlan) -> None:
    """Activate a verified plan for lazy compatibility imports in this process."""

    require_capability(plan, "cli.enterprise")
    global _ACTIVE_PLAN
    _ACTIVE_PLAN = plan


def active_product_plan() -> ResolvedProductPlan | None:
    return _ACTIVE_PLAN


def product_status(config: CLIConfig) -> dict[str, object]:
    return resolve_configured_product_plan(config).redacted()


def historical_enterprise_status(config: CLIConfig) -> dict[str, object]:
    """Read normalized historical state when private readers are installed."""

    try:
        from dv_platform.enterprise.store import enterprise_status
    except ImportError:
        return {
            "schema_version": 1,
            "present": False,
            "passed": True,
            "failures": [],
            "diagnostic": "Enterprise package is not installed; normalized historical state remains untouched.",
        }
    return enterprise_status(config)


def _configured_revocations(path: Path | None) -> frozenset[str]:
    if path is None:
        return frozenset()
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "revoked_key_ids"}
        or value.get("schema_version") != 1
        or not isinstance(value.get("revoked_key_ids"), list)
        or any(not isinstance(item, str) or not item for item in value["revoked_key_ids"])
    ):
        raise ValueError("revocation document is not closed schema version 1")
    return frozenset(value["revoked_key_ids"])
