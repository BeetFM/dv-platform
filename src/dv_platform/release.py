"""Immutable release bundles and independently authorized sign-off approvals."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dv_platform.physical_design import file_digest, load_physical_project, project_input, write_document
from dv_platform.signing import certificate_public_key
from dv_platform.signoff import (
    REQUIRED_CHECKS,
    closed,
    digest,
    identity,
    load_requirements,
    read_document,
    requirements_gaps,
    timestamp,
    verify_artifacts,
    verify_role,
)

WAIVABLE_CHECKS = {
    "drc_magic": ("drc_violations", "/magic.json"),
    "drc_klayout": ("violations", "/drc.rdb"),
    "antenna": ("antenna_violations", "/magic.json"),
    "density": ("violations", "-density.stdout.log"),
}


def build_release(
    project_path: Path,
    run_path: Path,
    checks: dict[str, Any],
    destination: Path,
) -> Path:
    project = load_physical_project(project_path)
    if project["schema_version"] != 2:
        raise ValueError("production release requires a v2 SKY130 project")
    run = read_document(run_path)
    selected = run.get("selected")
    if selected not in {"baseline", "candidate-1", "candidate-2", "candidate-3"}:
        raise ValueError("release has no selected implementation")
    case = project_input(run_path.parent, f"{selected}/analysis.json").parent
    if set(run["source_inputs"]) != set(project["inputs"]):
        raise ValueError("run omits declared project inputs")
    verify_artifacts(project_path.parent, run["source_inputs"])
    verify_artifacts(case, run["source_inputs"])
    verify_artifacts(run_path.parent / "workflow", run["workflow_files"])
    if file_digest(project_path) != run.get("project_sha256"):
        raise ValueError("run and project identities differ")
    if set(checks) != set(REQUIRED_CHECKS):
        raise ValueError("release must report every required check")
    destination.mkdir(parents=True, exist_ok=False)
    _copy_files(project_path.parent, destination / "project", project["inputs"])
    _copy_files(run_path.parent / "workflow", destination / "workflow", list(run["workflow_files"]))
    receipts = run_path.parent / "ai-receipts"
    if receipts.exists():
        for step in run.get("iterations", []):
            name = f"iteration-{step['iteration']}.json"
            if step.get("ai_receipt_sha256") is not None:
                verify_artifacts(receipts, {name: step["ai_receipt_sha256"]})
                _copy_files(receipts, destination / "ai-receipts", [name])
    shutil.copyfile(project_path, destination / "project/project.json")
    case_files = set(read_document(case / "analysis.json")["artifacts"])
    case_files.update(project["deliverables"].values())
    case_files.update(name for check in checks.values() for name in check["artifacts"])
    case_files.add("analysis.json")
    present = [name for name in sorted(case_files) if (case / name).is_file()]
    _copy_files(case, destination / "artifacts", present)
    shutil.copyfile(run_path, destination / "artifacts/run.json")
    artifacts = {
        p.relative_to(destination).as_posix(): file_digest(p) for p in sorted(destination.rglob("*")) if p.is_file()
    }
    current = datetime.now(UTC)
    policy = load_requirements(project_path.parent / project["signoff_policy"], project)
    expiry = min(timestamp(policy["expires_at"]), current + timedelta(days=1))
    manifest = {
        "schema_version": 1,
        "kind": "sky130_release",
        "design": project["design"],
        "project": "project/project.json",
        "run": "artifacts/run.json",
        "checks": checks,
        "artifacts": artifacts,
        "generated_at": current.isoformat(),
        "expires_at": expiry.isoformat(),
    }
    path = destination / "release.json"
    write_document(path, manifest)
    return path


def _copy_files(source: Path, target: Path, names: list[str] | set[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        original = project_input(source, name)
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)


def verify_release(path: Path, trust_path: Path | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    release = read_document(path)
    closed(
        release,
        {"schema_version", "kind", "design", "project", "run", "checks", "artifacts", "generated_at", "expires_at"},
        "release bundle",
    )
    if (
        type(release["schema_version"]) is not int
        or release["schema_version"] != 1
        or release["kind"] != "sky130_release"
        or release["project"] != "project/project.json"
        or release["run"] != "artifacts/run.json"
    ):
        raise ValueError("unsupported release bundle")
    verify_artifacts(path.parent, release["artifacts"])
    if release["project"] not in release["artifacts"] or release["run"] not in release["artifacts"]:
        raise ValueError("release omits its project or run artifact")
    project_path = project_input(path.parent, release["project"])
    project = load_physical_project(project_path)
    if project["schema_version"] != 2 or project["design"] != release["design"]:
        raise ValueError("release project identity mismatch")
    _verify_bundle_sources(path.parent, release, project_path, project)
    policy_path = project_path.parent / project["signoff_policy"]
    policy = load_requirements(policy_path, project)
    current = now or datetime.now(UTC)
    reasons = _release_gaps(release, project, policy, current)
    policy_error = None
    try:
        if trust_path is None:
            raise ValueError("sign-off trust policy is not configured")
        verify_role(policy, policy_path, trust_path, "engineering", now=current)
    except (OSError, ValueError, TypeError, KeyError) as error:
        policy_error = str(error)
        reasons.append(policy_error)
    status = {
        "present": True,
        "release": str(path),
        "release_sha256": file_digest(path),
        "design": release["design"],
        "checks": release["checks"],
        "requirements_gaps": reasons,
        "engineering_ready": not reasons,
        "requirements_valid": policy_error is None and not requirements_gaps(policy, project),
        "waived_checks": [],
        "engineering_approved": False,
        "manufacturing_approved": False,
        "signoff_approved": False,
    }
    if trust_path is not None and policy_error is None:
        _approval_status(path, project_path, project, trust_path, current, status, release, policy)
    return status


def _verify_bundle_sources(root: Path, release: dict[str, Any], project_path: Path, project: dict[str, Any]) -> None:
    run = read_document(project_input(root, release["run"]))
    if file_digest(project_path) != run.get("project_sha256") or set(run["source_inputs"]) != set(project["inputs"]):
        raise ValueError("release run and project inputs differ")
    for directory, inputs in (("project", run["source_inputs"]), ("workflow", run["workflow_files"])):
        verify_artifacts(root / directory, inputs)
        if any(release["artifacts"].get(directory + "/" + name) != expected for name, expected in inputs.items()):
            raise ValueError("release omits bound source or workflow evidence")
    analysis = read_document(project_input(root, "artifacts/analysis.json"))
    verify_artifacts(root / "artifacts", analysis["artifacts"])
    if "artifacts/analysis.json" not in release["artifacts"] or any(
        release["artifacts"].get("artifacts/" + name) != expected for name, expected in analysis["artifacts"].items()
    ):
        raise ValueError("release omits bound native analysis evidence")


def _release_gaps(
    release: dict[str, Any],
    project: dict[str, Any],
    policy: dict[str, Any],
    current: datetime,
    waived: set[str] | None = None,
) -> list[str]:
    checks = closed(release["checks"], set(REQUIRED_CHECKS), "release checks")
    reasons = requirements_gaps(policy, project)
    reasons.extend(
        f"missing deliverable: {kind}"
        for kind, name in project["deliverables"].items()
        if "artifacts/" + name not in release["artifacts"]
    )
    if not timestamp(release["generated_at"]) <= current < timestamp(release["expires_at"]):
        reasons.append("release evidence is expired or future-dated")
    for name, check in checks.items():
        closed(check, {"status", "tool", "reason", "artifacts", "metrics"}, "release check")
        if check["status"] not in {"passed", "failed", "unknown"}:
            raise ValueError("invalid release check state")
        if (
            not isinstance(check["artifacts"], list)
            or not isinstance(check["metrics"], dict)
            or any(not isinstance(item, str) for item in check["artifacts"])
            or len(check["artifacts"]) != len(set(check["artifacts"]))
            or not isinstance(check["tool"], str)
            or not check["tool"].strip()
            or not isinstance(check["reason"], str)
        ):
            raise ValueError("invalid release check evidence")
        if check["status"] != "passed" and name not in (waived or set()):
            reasons.append(f"{name}: {check['reason']}")
        if name != "requirements" and check["status"] == "passed" and not check["artifacts"]:
            raise ValueError("passing release check has no native evidence")
        for artifact in check["artifacts"]:
            if "artifacts/" + artifact not in release["artifacts"]:
                raise ValueError("release check references unbound evidence")
    return reasons


def import_approval(release_path: Path, approval_path: Path, trust_path: Path) -> dict[str, Any]:
    status = verify_release(release_path, trust_path)
    if not status["requirements_valid"]:
        raise ValueError("approval requires complete passing engineering evidence and approved requirements")
    project_path = release_path.parent / "project/project.json"
    project = load_physical_project(project_path)
    approval = read_document(approval_path)
    role = approval.get("role")
    if role not in {"engineering", "manufacturing"}:
        raise ValueError("unsupported approval role")
    if role == "manufacturing" and not status["engineering_approved"]:
        raise ValueError("manufacturing approval requires valid engineering approval")
    _verify_approval(approval, approval_path, release_path, project_path, project, trust_path, datetime.now(UTC))
    if role == "engineering":
        release = read_document(release_path)
        waived = _verified_waivers(approval, release, datetime.now(UTC))
        policy = load_requirements(project_path.parent / project["signoff_policy"], project)
        if _release_gaps(release, project, policy, datetime.now(UTC), waived):
            raise ValueError("approval cannot bypass missing, failed, or inconclusive required evidence")
    directory = release_path.parent / "approvals"
    directory.mkdir(mode=0o700, exist_ok=True)
    certificate = project_input(approval_path.parent, approval["signature"]["certificate_file"])
    certificate_name = f"{role}-{digest(approval['signature']['certificate_sha256'])}.pem"
    shutil.copyfile(certificate, directory / certificate_name)
    copied = {**approval, "signature": {**approval["signature"], "certificate_file": certificate_name}}
    write_document(directory / f"{role}.json", copied)
    return verify_release(release_path, trust_path)


def _verify_approval(
    approval: dict[str, Any],
    path: Path,
    release_path: Path,
    project_path: Path,
    project: dict[str, Any],
    trust_path: Path,
    current: datetime,
) -> None:
    closed(
        approval,
        {
            "schema_version",
            "role",
            "release_sha256",
            "technology_sha256",
            "policy_sha256",
            "reviewer",
            "generated_at",
            "expires_at",
            "signature",
            "waivers",
            "engineering_approval_sha256",
        },
        "sign-off approval",
    )
    if type(approval["schema_version"]) is not int or approval["schema_version"] != 1:
        raise ValueError("unsupported approval schema")
    identities = {
        "release_sha256": file_digest(release_path),
        "technology_sha256": file_digest(project_path.parent / project["technology_lock"]),
        "policy_sha256": file_digest(project_path.parent / project["signoff_policy"]),
    }
    if any(approval[key] != value for key, value in identities.items()):
        raise ValueError("approval binds a different release, policy, or technology")
    if not isinstance(approval["reviewer"], str) or not approval["reviewer"].strip():
        raise ValueError("approval reviewer is missing")
    _verify_approval_link(approval, release_path)
    verify_role(approval, path, trust_path, approval["role"], now=current)
    if approval["role"] == "manufacturing":
        own_key = certificate_public_key(project_input(path.parent, approval["signature"]["certificate_file"]))
        for engineering_path in (
            release_path.parent / "approvals/engineering.json",
            project_path.parent / project["signoff_policy"],
        ):
            engineering = read_document(engineering_path)
            certificate = project_input(engineering_path.parent, engineering["signature"]["certificate_file"])
            if own_key == certificate_public_key(certificate):
                raise ValueError("engineering and manufacturing must use distinct signing keys")


def _verify_approval_link(approval: dict[str, Any], release_path: Path) -> None:
    if approval["role"] == "engineering":
        if approval["engineering_approval_sha256"] is not None:
            raise ValueError("engineering approval cannot reference itself")
    elif approval["role"] == "manufacturing":
        if approval["waivers"] != []:
            raise ValueError("manufacturing approval must accept the exact engineering waiver decision")
        path = release_path.parent / "approvals/engineering.json"
        if digest(approval["engineering_approval_sha256"]) != approval_identity(read_document(path)):
            raise ValueError("manufacturing approval binds a different engineering decision")
    else:
        raise ValueError("unsupported approval role")


def approval_identity(document: dict[str, Any]) -> str:
    # Moving the certificate file during import must not change the signed approval's identity.
    normalized = {
        **document,
        "signature": {key: value for key, value in document["signature"].items() if key != "certificate_file"},
    }
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _verified_waivers(approval: dict[str, Any], release: dict[str, Any], current: datetime) -> set[str]:
    if not isinstance(approval["waivers"], list):
        raise ValueError("waivers must be an explicit list")
    waived: set[str] = set()
    identities: set[str] = set()
    for waiver in approval["waivers"]:
        closed(
            waiver,
            {"waiver_id", "check_id", "artifact", "report_sha256", "finding_count", "reason", "expires_at"},
            "release waiver",
        )
        waiver_id, name = identity(waiver["waiver_id"]), waiver["check_id"]
        if name not in WAIVABLE_CHECKS or name in waived or waiver_id in identities:
            raise ValueError("waiver is duplicated or targets a non-waivable check")
        check = release["checks"][name]
        field, suffix = WAIVABLE_CHECKS[name]
        if check["status"] != "failed" or type(check["metrics"].get(field)) is not int or check["metrics"][field] < 1:
            raise ValueError("waivers require completed analysis with counted physical findings")
        artifact = waiver["artifact"]
        if (
            not isinstance(artifact, str)
            or not artifact.endswith(suffix)
            or artifact not in check["artifacts"]
            or release["artifacts"].get("artifacts/" + artifact) != digest(waiver["report_sha256"])
        ):
            raise ValueError("waiver does not bind the exact native report")
        if type(waiver["finding_count"]) is not int or waiver["finding_count"] != check["metrics"][field]:
            raise ValueError("waiver finding count differs from the frozen report")
        if (
            timestamp(waiver["expires_at"]) <= current
            or not isinstance(waiver["reason"], str)
            or not waiver["reason"].strip()
        ):
            raise ValueError("waiver is expired or has no engineering rationale")
        waived.add(name)
        identities.add(waiver_id)
    return waived


def _approval_status(
    path: Path,
    project_path: Path,
    project: dict[str, Any],
    trust_path: Path,
    current: datetime,
    status: dict[str, Any],
    release: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    for role in ("engineering", "manufacturing"):
        approval_path = path.parent / "approvals" / f"{role}.json"
        if not approval_path.exists():
            continue
        try:
            approval = read_document(approval_path)
            if approval.get("role") != role:
                raise ValueError("approval file contains the wrong role")
            _verify_approval(approval, approval_path, path, project_path, project, trust_path, current)
            if role == "engineering":
                waived = _verified_waivers(approval, release, current)
                reasons = _release_gaps(release, project, policy, current, waived)
                status.update(
                    waived_checks=sorted(waived),
                    requirements_gaps=reasons,
                    engineering_ready=not reasons,
                    engineering_approved=not reasons,
                    engineering_approval_sha256=approval_identity(approval),
                )
            elif status["engineering_approved"]:
                status["manufacturing_approved"] = True
        except (OSError, ValueError, TypeError, KeyError) as error:
            status.setdefault("approval_errors", {})[role] = str(error)
    status["signoff_approved"] = status["engineering_approved"] and status["manufacturing_approved"]


def collect_signoff_status(config: Any) -> dict[str, Any]:
    pointer = config.work_dir / "signoff/latest.json"
    absent = {"present": False, "engineering_ready": False, "signoff_approved": False}
    if not pointer.exists():
        return absent
    try:
        index = read_document(pointer)
        closed(index, {"release", "sha256"}, "release index")
        release_path = project_input(config.work_dir, index["release"])
        if file_digest(release_path) != digest(index["sha256"]):
            raise ValueError("release index identity mismatch")
        return verify_release(release_path, config.product.signoff_trust_policy_path)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {**absent, "invalid": True, "error": str(error)}
