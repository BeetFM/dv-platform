"""Independent fail-closed FPGA and ASIC physical evidence normalization."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from dv_platform.domain.models import CLIConfig


class ClosureState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


PHYSICAL_DOMAINS = frozenset({"fpga_implementation", "asic_timing", "asic_cdc_rdc", "asic_power", "asic_memory"})
APPROVED_TOOLS = {
    "spyglass": frozenset({"asic_cdc_rdc"}),
    "primetime": frozenset({"asic_timing", "asic_memory"}),
    "primepower": frozenset({"asic_power", "asic_memory"}),
    "jaspergold": frozenset({"asic_cdc_rdc"}),
    "tempus": frozenset({"asic_timing", "asic_memory"}),
    "voltus": frozenset({"asic_power", "asic_memory"}),
    "vivado": frozenset({"fpga_implementation"}),
}


class PhysicalEvidenceError(ValueError):
    pass


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_FINDING_FIELDS = {
    "finding_id",
    "severity",
    "path",
    "hierarchy",
    "clock_domain",
    "corner",
    "mode",
    "unit",
    "value",
    "waived",
    "waiver_id",
}
_WAIVER_FIELDS = {"waiver_id", "finding_ids", "approved_by", "expires_at", "reason"}


@dataclass(frozen=True)
class PhysicalClosure:
    logical_state: ClosureState
    physical: tuple[tuple[str, ClosureState], ...]

    @property
    def overall(self) -> ClosureState:
        states = tuple(state for _, state in self.physical)
        if self.logical_state is ClosureState.FAILED or ClosureState.FAILED in states:
            return ClosureState.FAILED
        if self.logical_state is ClosureState.UNKNOWN or not states or ClosureState.UNKNOWN in states:
            return ClosureState.UNKNOWN
        return ClosureState.PASSED


def validate_physical_evidence(
    report: dict[str, Any],
    policy: dict[str, Any],
    *,
    verify_signature: Callable[[dict[str, Any]], bool],
    now: datetime | None = None,
) -> tuple[str, ClosureState]:
    domain, tool = _validate_physical_root(report)
    _validate_physical_policy(report, policy, tool)
    current = now or datetime.now(UTC)
    _validate_physical_freshness_and_signature(report, policy, current, verify_signature)
    return domain, _physical_finding_state(report, current)


def _validate_physical_root(report: dict[str, Any]) -> tuple[str, str]:
    fields = {
        "schema_version",
        "domain",
        "tool",
        "tool_version",
        "design",
        "source_sha256",
        "netlist_sha256",
        "constraints_sha256",
        "pdk",
        "pdk_files",
        "libraries",
        "corners",
        "modes",
        "clocks_domains",
        "findings",
        "waivers",
        "units",
        "complete",
        "generated_at",
        "report_sha256",
        "signature",
    }
    if set(report) != fields or report.get("schema_version") != 1:
        raise PhysicalEvidenceError("physical report has unknown, missing, or unsupported fields")
    domain = report["domain"]
    tool = report["tool"]
    if domain not in PHYSICAL_DOMAINS or tool not in APPROVED_TOOLS or domain not in APPROVED_TOOLS[tool]:
        raise PhysicalEvidenceError("unsupported physical domain/tool pairing")
    return domain, tool


def _validate_physical_policy(report: dict[str, Any], policy: dict[str, Any], tool: str) -> None:
    required_policy = {
        "schema_version",
        "tool_versions",
        "design",
        "source_sha256",
        "netlist_sha256",
        "constraints_sha256",
        "pdk",
        "pdk_files",
        "libraries",
        "corners",
        "modes",
        "max_age_hours",
        "allowed_units",
    }
    if set(policy) != required_policy or policy.get("schema_version") != 1:
        raise PhysicalEvidenceError("physical policy is not closed")
    identities = ("design", "source_sha256", "netlist_sha256", "constraints_sha256", "pdk")
    if any(report[key] != policy[key] for key in identities):
        raise PhysicalEvidenceError("physical source, netlist, constraint, design, or PDK identity mismatch")
    collection_identities = ("pdk_files", "libraries", "corners", "modes")
    if any(set(report[key]) != set(policy[key]) for key in collection_identities):
        raise PhysicalEvidenceError("physical libraries, files, corners, or modes are incomplete")
    if policy["tool_versions"].get(tool) != report["tool_version"]:
        raise PhysicalEvidenceError("unlisted physical tool version")
    if not report["complete"] or not report["clocks_domains"] or not report["report_sha256"]:
        raise PhysicalEvidenceError("truncated, partially parsed, or absence-only physical report")
    if not _DIGEST.fullmatch(str(report["report_sha256"])):
        raise PhysicalEvidenceError("physical report digest is invalid")
    if set(report["units"]) - set(policy["allowed_units"]):
        raise PhysicalEvidenceError("physical report contains unknown units")


def _validate_physical_freshness_and_signature(
    report: dict[str, Any],
    policy: dict[str, Any],
    current: datetime,
    verify_signature: Callable[[dict[str, Any]], bool],
) -> None:
    generated = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
    age = current - generated
    if age < timedelta(0) or age > timedelta(hours=policy["max_age_hours"]):
        raise PhysicalEvidenceError("physical report is stale")
    if not verify_signature(report):
        raise PhysicalEvidenceError("physical evidence signature is untrusted")


def _physical_finding_state(report: dict[str, Any], current: datetime) -> ClosureState:
    findings = report["findings"]
    if not isinstance(findings, list) or not findings:
        raise PhysicalEvidenceError("absence-of-findings is not evidence of a completed analysis")
    waivers = _validated_waivers(report["waivers"], current)
    finding_ids: set[str] = set()
    active: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for item in findings:
        if not isinstance(item, dict) or set(item) != _FINDING_FIELDS:
            raise PhysicalEvidenceError("physical finding is partially parsed")
        finding_id = item["finding_id"]
        if not isinstance(finding_id, str) or not finding_id or finding_id in finding_ids:
            raise PhysicalEvidenceError("physical finding identity is missing or duplicated")
        finding_ids.add(finding_id)
        if item["corner"] not in report["corners"] or item["mode"] not in report["modes"]:
            raise PhysicalEvidenceError("physical finding references an unlisted corner or mode")
        if item["unit"] is not None and item["unit"] not in report["units"]:
            raise PhysicalEvidenceError("physical finding references an unlisted unit")
        waived = item["waived"] is True
        waiver_id = item["waiver_id"]
        if waived and (waiver_id not in waivers or finding_id not in waivers[waiver_id]):
            raise PhysicalEvidenceError("physical finding has an absent, stale, or mismatched waiver")
        severity = item["severity"]
        if severity in {"error", "critical"} and not waived:
            active.append(item)
        elif severity not in {"info", "warning", "error", "critical"}:
            unknown.append(item)
    state = ClosureState.UNKNOWN if unknown else ClosureState.FAILED if active else ClosureState.PASSED
    return state


def _validated_waivers(raw: object, current: datetime) -> dict[str, frozenset[str]]:
    if not isinstance(raw, list):
        raise PhysicalEvidenceError("physical waivers must be a list")
    result: dict[str, frozenset[str]] = {}
    for waiver in raw:
        if not isinstance(waiver, dict) or set(waiver) != _WAIVER_FIELDS:
            raise PhysicalEvidenceError("physical waiver is partially parsed")
        waiver_id = waiver["waiver_id"]
        finding_ids = waiver["finding_ids"]
        if (
            not isinstance(waiver_id, str)
            or not waiver_id
            or waiver_id in result
            or not isinstance(finding_ids, list)
            or not finding_ids
            or any(not isinstance(item, str) or not item for item in finding_ids)
            or not waiver["approved_by"]
            or not waiver["reason"]
        ):
            raise PhysicalEvidenceError("physical waiver identity or approval is invalid")
        expires = datetime.fromisoformat(str(waiver["expires_at"]).replace("Z", "+00:00"))
        if expires <= current:
            raise PhysicalEvidenceError("physical waiver is expired")
        result[waiver_id] = frozenset(finding_ids)
    return result


def collect_physical_status(config: CLIConfig) -> dict[str, Any]:
    path = config.work_dir / "physical" / "closure.json"
    required = config.product.required_physical_domains
    if not path.is_file():
        states = {domain: ClosureState.UNKNOWN.value for domain in required}
        return {"present": False, "path": str(path), "domains": states, "overall": "unknown" if required else "passed"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": True, "path": str(path), "domains": {}, "overall": "unknown", "invalid": True}
    domains = payload.get("domains", {}) if isinstance(payload, dict) else {}
    if not isinstance(domains, dict) or any(value not in ClosureState for value in domains.values()):
        return {"present": True, "path": str(path), "domains": {}, "overall": "unknown", "invalid": True}
    selected = tuple(ClosureState(domains.get(domain, "unknown")) for domain in required)
    overall = (
        ClosureState.FAILED
        if ClosureState.FAILED in selected
        else ClosureState.UNKNOWN
        if ClosureState.UNKNOWN in selected
        else ClosureState.PASSED
    )
    return {"present": True, "path": str(path), "domains": domains, "overall": overall.value}
