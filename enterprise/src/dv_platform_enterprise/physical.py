"""Enterprise physical-evidence importer and normalized closure persistence."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dv_platform.core.io import atomic_write_text
from dv_platform.domain.models import CLIConfig
from dv_platform.physical import APPROVED_TOOLS, validate_physical_evidence
from dv_platform.product import ResolvedProductPlan, require_capability

_DOMAIN_CAPABILITY = {
    "asic_timing": "physical.asic.timing",
    "asic_power": "physical.asic.power",
    "asic_memory": "physical.asic.memory",
}


class OpenROADPhysicalEvidenceAdapter:
    """Normalize structured OpenROAD evidence without inferring pass."""

    api_version = 2
    kind = "physical_evidence_importer"
    sandbox_aware = True
    audit_schema_version = 1

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("tool") != "openroad" or raw.get("domain") not in APPROVED_TOOLS["openroad"]:
            raise ValueError("OpenROAD report tool/domain identity mismatch")
        findings = raw.get("findings")
        if not isinstance(findings, list) or not findings:
            raise ValueError("summary-only OpenROAD reports are rejected")
        normalized = dict(raw)
        normalized["findings"] = [self._finding(item) for item in findings]
        clocks = raw.get("clocks_domains")
        if not isinstance(clocks, list) or not clocks or any(not isinstance(item, dict) or not item for item in clocks):
            raise ValueError("OpenROAD report has incomplete clock/domain metadata")
        normalized["clocks_domains"] = [
            {str(key): str(value) for key, value in sorted(item.items())} for item in clocks
        ]
        if not normalized["clocks_domains"]:
            raise ValueError("OpenROAD report lacks parsed clock/domain identity")
        return normalized

    @staticmethod
    def _finding(item: object) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("OpenROAD finding must be an object")
        normalized = dict(item)
        for field in ("path", "hierarchy"):
            value = normalized.get(field)
            if isinstance(value, str):
                normalized[field] = value.replace("\\", "/").removeprefix("./")
        return normalized


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
    deadlines = existing.get("valid_until", {})
    if not isinstance(domains, dict) or not isinstance(deadlines, dict):
        raise ValueError("existing physical closure is invalid")
    identity = {key: report[key] for key in ("design", "source_sha256", "netlist_sha256", "constraints_sha256", "pdk")}
    if existing.get("identity") != identity:
        domains, deadlines = {}, {}
    deadline = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00")) + timedelta(
        hours=policy["max_age_hours"]
    )
    if report["waivers"]:
        deadline = min(
            deadline, *(datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00")) for item in report["waivers"])
        )
    domains[str(normalized_domain)] = state.value
    deadlines[str(normalized_domain)] = deadline.isoformat()
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "domains": dict(sorted(domains.items())),
        "valid_until": dict(sorted(deadlines.items())),
        "identity": identity,
        "source_report_sha256": report["report_sha256"],
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _document(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError(f"physical JSON document exceeds 32 MiB: {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value
