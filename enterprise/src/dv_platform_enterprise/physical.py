"""Enterprise physical-evidence importer and normalized closure persistence."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.domain.models import CLIConfig
from dv_platform.physical import validate_physical_evidence
from dv_platform.product import ResolvedProductPlan, require_capability

_DOMAIN_CAPABILITY = {
    "fpga_implementation": "physical.fpga",
    "asic_timing": "physical.asic.timing",
    "asic_cdc_rdc": "physical.asic.cdc_rdc",
    "asic_power": "physical.asic.power",
    "asic_memory": "physical.asic.memory",
}

COMMERCIAL_PHYSICAL_CELLS = {
    "spyglass": ("asic_cdc_rdc",),
    "primetime": ("asic_timing", "asic_memory"),
    "primepower": ("asic_power", "asic_memory"),
    "jaspergold": ("asic_cdc_rdc",),
    "tempus": ("asic_timing", "asic_memory"),
    "voltus": ("asic_power", "asic_memory"),
}


class PhysicalEvidenceAdapter:
    """Normalize a version-pinned structured exporter without inferring pass."""

    api_version = 2
    kind = "physical_evidence_importer"
    sandbox_aware = True
    audit_schema_version = 1

    def __init__(self, tool: str, domain: str) -> None:
        if tool not in COMMERCIAL_PHYSICAL_CELLS or domain not in COMMERCIAL_PHYSICAL_CELLS[tool]:
            raise ValueError("unsupported commercial physical adapter cell")
        self.tool = tool
        self.domain = domain

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("tool") != self.tool or raw.get("domain") != self.domain:
            raise ValueError("commercial report tool/domain identity mismatch")
        findings = raw.get("findings")
        if not isinstance(findings, list) or not findings:
            raise ValueError("summary-only commercial reports are rejected")
        normalized = dict(raw)
        normalized["findings"] = [self._finding(item) for item in findings]
        normalized["clocks_domains"] = [
            {str(key): str(value) for key, value in sorted(item.items())}
            for item in raw.get("clocks_domains", [])
            if isinstance(item, dict)
        ]
        if not normalized["clocks_domains"]:
            raise ValueError("commercial report lacks parsed clock/domain identity")
        return normalized

    @staticmethod
    def _finding(item: object) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("commercial finding must be an object")
        normalized = dict(item)
        for field in ("path", "hierarchy"):
            value = normalized.get(field)
            if isinstance(value, str):
                normalized[field] = value.replace("\\", "/").removeprefix("./")
        return normalized


class SpyGlassCDCRDCAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("spyglass", "asic_cdc_rdc")


class PrimeTimeTimingAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("primetime", "asic_timing")


class PrimeTimeMemoryAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("primetime", "asic_memory")


class PrimePowerAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("primepower", "asic_power")


class JasperGoldCDCRDCAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("jaspergold", "asic_cdc_rdc")


class TempusTimingAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("tempus", "asic_timing")


class TempusMemoryAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("tempus", "asic_memory")


class VoltusPowerAdapter(PhysicalEvidenceAdapter):
    def __init__(self) -> None:
        super().__init__("voltus", "asic_power")


def import_physical_evidence(
    config: CLIConfig,
    report_path: Path,
    policy_path: Path,
    product_plan: ResolvedProductPlan,
    *,
    verify_signature: Callable[[dict[str, Any]], bool],
) -> Path:
    """Validate exact signed evidence before updating independent closure."""

    report = _document(report_path)
    policy = _document(policy_path)
    domain = report.get("domain")
    if domain not in _DOMAIN_CAPABILITY:
        raise ValueError("physical report domain is not supported")
    require_capability(product_plan, _DOMAIN_CAPABILITY[str(domain)])
    normalized_domain, state = validate_physical_evidence(
        report,
        policy,
        verify_signature=verify_signature,
    )
    path = config.work_dir / "physical" / "closure.json"
    existing = _document(path) if path.is_file() else {"schema_version": 1, "domains": {}}
    domains = existing.get("domains", {})
    if not isinstance(domains, dict):
        raise ValueError("existing physical closure is invalid")
    domains[str(normalized_domain)] = state.value
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "domains": dict(sorted(domains.items())),
        "source_report_sha256": report["report_sha256"],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value
