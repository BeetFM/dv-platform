"""Closed SKY130 project, requirements, and role-authorized approval contracts."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dv_platform.physical_design import file_digest, project_input
from dv_platform.signing import verify_signed_document

SKY130_REVISION = "0fe599b2afb6708d281543108caf8310912f54af"
PVT_CORNERS = ("tt_025C_1v80", "ss_100C_1v60", "ff_n40C_1v95")
RC_CORNERS = ("min", "nom", "max")
REQUIRED_CHECKS = (
    "requirements",
    "timing",
    "equivalence_source",
    "equivalence_final",
    "drc_magic",
    "drc_klayout",
    "lvs",
    "antenna",
    "density",
    "erc",
    "power_grid",
    "ir_drop",
    "em",
    "activity",
)
LIMIT_FIELDS = {
    "setup_margin_ns",
    "hold_margin_ns",
    "area_max_um2",
    "power_max_watts",
    "ir_drop_max_v",
    "em_max_current_density_a_um2",
}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def read_document(path: Path, *, maximum: int = 32 * 1024 * 1024) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError(f"missing, linked, or oversized sign-off document: {path.name}")
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
    )
    if not isinstance(value, dict):
        raise ValueError("sign-off document must be an object")
    return value


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate sign-off field: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-finite sign-off number: {value}")


def closed(value: object, fields: set[str], description: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{description} has unknown or missing fields")
    return value


def digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError("invalid sign-off SHA-256")
    return value


def identity(value: object) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise ValueError("invalid bounded sign-off identity")
    return value


def number(value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("sign-off limit must be a finite number")
    try:
        converted = float(value)
    except OverflowError as error:
        raise ValueError("sign-off limit must be a finite number") from error
    if not math.isfinite(converted):
        raise ValueError("sign-off limit must be a finite number")
    if value < 0 or positive and value == 0:
        raise ValueError("sign-off limit must be non-negative (positive for physical budgets)")
    return converted


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("sign-off timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid sign-off timestamp") from error
    if result.tzinfo is None:
        raise ValueError("sign-off timestamp needs a timezone")
    return result.astimezone(UTC)


def validate_technology(path: Path) -> dict[str, Any]:
    technology = read_document(path)
    closed(technology, {"schema_version", "pdk", "library", "revision", "files", "tools"}, "technology lock")
    if (
        type(technology["schema_version"]) is not int
        or technology["schema_version"] != 1
        or technology["pdk"] != "sky130A"
        or technology["library"] != "sky130_fd_sc_hd"
        or technology["revision"] != SKY130_REVISION
    ):
        raise ValueError("production technology must be the pinned sky130A HD build")
    verify_artifacts(path.parent, technology["files"])
    if any(technology["files"].get(name) != expected for name, expected in _pinned_sky130_files().items()):
        raise ValueError("technology files differ from the pinned upstream SKY130 assets")
    if not isinstance(technology["tools"], dict) or not {"openroad", "sta", "yosys"} <= set(technology["tools"]):
        raise ValueError("technology lock must identify implementation and equivalence tools")
    for name, tool in technology["tools"].items():
        identity(name)
        closed(tool, {"version", "sha256"}, "locked tool")
        digest(tool["sha256"])
        if not isinstance(tool["version"], str) or not tool["version"].strip():
            raise ValueError("locked tool version is empty")
    return technology


def _pinned_sky130_files() -> dict[str, str]:
    return read_document(Path(__file__).with_name("sky130-pin.json"))["files"]


def verify_artifacts(root: Path, artifacts: object) -> None:
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("sign-off artifacts must be a non-empty path/digest map")
    for name, expected in artifacts.items():
        if file_digest(project_input(root, name)) != digest(expected):
            raise ValueError(f"sign-off artifact digest mismatch: {name}")


def validate_project_v2(project: dict[str, Any], root: Path) -> None:
    for key in ("technology_lock", "reference_netlist", "signoff_policy"):
        if project[key] not in project["inputs"]:
            raise ValueError(f"{key} must be an explicit project input")
        project_input(root, project[key])
    validate_technology(root / project["technology_lock"])
    scenarios = project["scenarios"]
    if not isinstance(scenarios, list) or not 9 <= len(scenarios) <= 128:
        raise ValueError("SKY130 needs a complete bounded timing scenario matrix")
    names: set[str] = set()
    modes: set[str] = set()
    observed: set[tuple[str, str, str]] = set()
    for scenario in scenarios:
        closed(scenario, {"name", "mode", "pvt", "rc", "libraries", "constraints", "parasitics"}, "scenario")
        name, mode = identity(scenario["name"]), identity(scenario["mode"])
        if name in names or scenario["pvt"] not in PVT_CORNERS or scenario["rc"] not in RC_CORNERS:
            raise ValueError("duplicate scenario or unsupported SKY130 corner")
        names.add(name)
        modes.add(mode)
        point = (mode, scenario["pvt"], scenario["rc"])
        if point in observed:
            raise ValueError("duplicate timing scenario coverage")
        observed.add(point)
        _scenario_inputs(scenario, project)
    if observed != {(mode, pvt, rc) for mode in modes for pvt in PVT_CORNERS for rc in RC_CORNERS}:
        raise ValueError("timing matrix omits required PVT/RC combinations")
    if "functional" not in modes:
        raise ValueError("CPU sign-off needs functional timing scenarios")
    _deliverables(project)
    _validate_rc_scenarios(project)
    _validate_activity(project)


def _validate_activity(project: dict[str, Any]) -> None:
    if project["activity"] is None:
        return
    closed(project["activity"], {"file", "scope", "workload"}, "activity input")
    if project["activity"]["file"] not in project["inputs"]:
        raise ValueError("activity file must be an explicit input")
    if any(
        not isinstance(project["activity"][key], str) or not project["activity"][key] for key in ("scope", "workload")
    ):
        raise ValueError("activity requires scope and workload provenance")


def _scenario_inputs(scenario: dict[str, Any], project: dict[str, Any]) -> None:
    from dv_platform.physical_design import _relative

    for field in ("libraries", "constraints"):
        values = scenario[field]
        if (
            not isinstance(values, list)
            or not values
            or len(values) != len(set(values))
            or any(value not in project[field] for value in values)
        ):
            raise ValueError("scenario references undeclared timing inputs")
    _relative(scenario["parasitics"])
    if scenario["parasitics"] in project["inputs"]:
        raise ValueError("scenario parasitics must be generated by the current run")
    if scenario["libraries"] != [f"technology/lib/{scenario['pvt']}.lib"]:
        raise ValueError("scenario PVT identity does not match its pinned Liberty library")


def _validate_rc_scenarios(project: dict[str, Any]) -> None:
    by_corner = {rc: {view["parasitics"] for view in project["scenarios"] if view["rc"] == rc} for rc in RC_CORNERS}
    if any(len(paths) != 1 for paths in by_corner.values()):
        raise ValueError("each physical RC corner must identify one extracted parasitics file")
    if len(set.union(*by_corner.values())) != len(RC_CORNERS):
        raise ValueError("minimum, nominal, and maximum RC must use distinct extractions")
    if project["parasitics"] not in by_corner["nom"]:
        raise ValueError("primary analysis must use the nominal RC extraction")
    reserved = {*project["inputs"], *project["deliverables"].values(), "analysis.json", "scenarios.json"}
    if any(
        not path.startswith("results/") or not path.endswith(".spef") or path in reserved
        for paths in by_corner.values()
        for path in paths
    ):
        raise ValueError("RC extractions must use distinct generated results/*.spef outputs")


def _deliverables(project: dict[str, Any]) -> None:
    from dv_platform.physical_design import _relative

    closed(project["deliverables"], {"gds", "netlist", "def", "odb"}, "release deliverables")
    if any(
        project["deliverables"][kind] != name
        for kind, name in (("netlist", "pd-export.v"), ("def", "pd-final.def"), ("odb", "pd-final.odb"))
    ):
        raise ValueError("release deliverables must use the measured implementation exports")
    values = list(project["deliverables"].values())
    if len(values) != len(set(values)):
        raise ValueError("release deliverables alias each other")
    for name in values:
        _relative(name)
        if name in project["inputs"]:
            raise ValueError("release deliverables must be generated")


def load_requirements(path: Path, project: dict[str, Any]) -> dict[str, Any]:
    policy = read_document(path)
    closed(
        policy,
        {
            "schema_version",
            "design",
            "technology_sha256",
            "scenarios",
            "limits",
            "boundary",
            "supplies",
            "activity_min_coverage_percent",
            "metal_thickness_um",
            "required_checks",
            "generated_at",
            "expires_at",
            "signature",
        },
        "sign-off requirements",
    )
    if (
        type(policy["schema_version"]) is not int
        or policy["schema_version"] != 1
        or policy["design"] != project["design"]
    ):
        raise ValueError("requirements design or schema mismatch")
    if digest(policy["technology_sha256"]) != file_digest(path.parent / project["technology_lock"]):
        raise ValueError("requirements bind a different technology lock")
    expected = {scenario["name"] for scenario in project["scenarios"]}
    if (
        not isinstance(policy["scenarios"], list)
        or len(policy["scenarios"]) != len(expected)
        or set(policy["scenarios"]) != expected
    ):
        raise ValueError("requirements omit timing scenarios")
    closed(policy["limits"], LIMIT_FIELDS, "production limits")
    for key, value in policy["limits"].items():
        if value is not None:
            number(value, positive=key not in {"setup_margin_ns", "hold_margin_ns"})
    if policy["required_checks"] != list(REQUIRED_CHECKS):
        raise ValueError("production requirements cannot omit required checks")
    _validate_boundary(policy["boundary"], project, path.parent)
    _validate_power_policy(policy)
    if timestamp(policy["expires_at"]) <= timestamp(policy["generated_at"]):
        raise ValueError("requirements validity interval is empty")
    return policy


def _validate_boundary(boundary: object, project: dict[str, Any], root: Path) -> None:
    boundary = closed(boundary, {"complete", "constraints_sha256", "assumptions"}, "boundary requirements")
    if type(boundary["complete"]) is not bool or not isinstance(boundary["assumptions"], list):
        raise ValueError("invalid boundary completeness or assumptions")
    if any(not isinstance(item, str) or not item.strip() for item in boundary["assumptions"]):
        raise ValueError("boundary assumptions must be non-empty strings")
    expected = {name: file_digest(root / name) for name in project["constraints"]}
    if boundary["constraints_sha256"] != expected:
        raise ValueError("boundary constraints do not match the immutable project")


def _validate_power_policy(policy: dict[str, Any]) -> None:
    coverage = number(policy["activity_min_coverage_percent"], positive=True)
    if coverage > 100:
        raise ValueError("activity coverage cannot exceed 100 percent")
    if not isinstance(policy["metal_thickness_um"], dict) or not isinstance(policy["supplies"], dict):
        raise ValueError("power requirements must declare supplies and conductor thickness")
    for layer, thickness in policy["metal_thickness_um"].items():
        identity(layer)
        number(thickness, positive=True)
    for net, supply in policy["supplies"].items():
        identity(net)
        closed(supply, {"voltage", "sources"}, "supply")
        number(supply["voltage"])
        if supply["sources"] is not None and not isinstance(supply["sources"], str):
            raise ValueError("supply sources must identify a project input")


def requirements_gaps(policy: dict[str, Any], project: dict[str, Any]) -> list[str]:
    gaps = [key for key, value in policy["limits"].items() if value is None]
    if not policy["boundary"]["complete"]:
        gaps.append("boundary_constraints")
    if project["activity"] is None:
        gaps.append("activity_workload")
    if set(policy["supplies"]) != {"VPWR", "VGND"} or any(
        item["sources"] is None or item["sources"] not in project["inputs"] for item in policy["supplies"].values()
    ):
        gaps.append("power_supply_sources")
    if not policy["metal_thickness_um"]:
        gaps.append("conductor_cross_sections")
    return gaps


def verify_role(
    document: dict[str, Any], path: Path, trust_path: Path, role: str, *, now: datetime | None = None
) -> None:
    trust = read_document(trust_path)
    closed(trust, {"schema_version", "roles", "revoked_certificate_sha256"}, "sign-off trust policy")
    if type(trust["schema_version"]) is not int or trust["schema_version"] != 1:
        raise ValueError("unsupported sign-off trust policy")
    roles = closed(trust["roles"], {"engineering", "manufacturing"}, "approval roles")
    allowed = closed(roles[role], {"trust_root", "certificate_sha256"}, "approval role")
    signature = document.get("signature")
    if not isinstance(signature, dict):
        raise ValueError(f"{role} signature is required")
    signer = digest(signature.get("certificate_sha256"))
    _validate_signer_lists(roles, trust["revoked_certificate_sha256"])
    if signer not in allowed["certificate_sha256"] or signer in trust["revoked_certificate_sha256"]:
        raise ValueError(f"signer is not authorized for {role}")
    current = now or datetime.now(UTC)
    if not timestamp(document["generated_at"]) <= current < timestamp(document["expires_at"]):
        raise ValueError("sign-off document is expired or future-dated")
    root = project_input(trust_path.parent, allowed["trust_root"])
    if not verify_signed_document(document, path, root):
        raise ValueError("untrusted sign-off document signature")


def _validate_signer_lists(roles: dict[str, Any], revoked: object) -> None:
    if not isinstance(revoked, list):
        raise ValueError("revoked signers must be a list")
    for value in revoked:
        digest(value)
    for item in roles.values():
        closed(item, {"trust_root", "certificate_sha256"}, "approval role")
        signers = item["certificate_sha256"]
        if not isinstance(signers, list) or not signers or len(signers) != len(set(signers)):
            raise ValueError("approval role needs unique authorized signer fingerprints")
        for value in signers:
            digest(value)
    if set(roles["engineering"]["certificate_sha256"]) & set(roles["manufacturing"]["certificate_sha256"]):
        raise ValueError("engineering and manufacturing approvals need distinct signers")
