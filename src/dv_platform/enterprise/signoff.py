"""Native SKY130 qualification and release orchestration; approval is always separate."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from dv_platform.enterprise.layout import density_check, klayout_drc, magic_extract, netgen_lvs, stream_layout
from dv_platform.enterprise.native import verify_current_workflow
from dv_platform.enterprise.physical_design import run_physical_optimization
from dv_platform.enterprise.power import analyze_power, current_density_bound, electrical_connectivity
from dv_platform.enterprise.timing import replay_period_proposal
from dv_platform.enterprise.transition_equivalence import prove_mapped_equivalence as prove_equivalence
from dv_platform.entitlement_leases import acquire_capability_lease
from dv_platform.physical_design import (
    assess_physical_requirements,
    file_digest,
    load_physical_project,
    physical_requirements,
    project_input,
    write_document,
)
from dv_platform.product import active_product_plan, require_capability, resolve_configured_product_plan
from dv_platform.release import build_release, collect_signoff_status, import_approval, verify_release
from dv_platform.signoff import (
    REQUIRED_CHECKS,
    load_requirements,
    read_document,
    requirements_gaps,
    verify_artifacts,
    verify_role,
)


def characterize(config: Any, project_path: Path) -> dict[str, Any]:
    plan = _signoff_plan(config)
    project = load_physical_project(project_path)
    if project["schema_version"] != 2:
        raise ValueError("SKY130 characterization requires a v2 project")
    run = run_physical_optimization(config, project_path)
    policy = load_requirements(project_path.parent / project["signoff_policy"], project)
    tools = {name: shutil.which(name) for name in ("openroad", "sta")}
    if any(executable is None for executable in tools.values()):
        raise FileNotFoundError("period characterization requires OpenROAD and standalone OpenSTA")
    with acquire_capability_lease(plan, config.work_dir, "cli.enterprise.signoff"):
        exploration = replay_period_proposal(
            Path(run["best"]["directory"]),
            project,
            run["best"],
            {name: str(executable) for name, executable in tools.items()},
            policy["limits"],
        )
    report = {
        "status": "characterized",
        "run": str(Path(run["output"]) / "run.json"),
        "design": project["design"],
        "timing_status": run["status"],
        "metrics": run["best"]["metrics"],
        "scenarios": run["best"]["scenarios"],
        "period_exploration": exploration,
        "requirements_gaps": requirements_gaps(policy, project),
        "engineering_ready": False,
        "signoff_approved": False,
        "next_step": "Approve boundary assumptions and explicit budgets, sign the requirements, and run closure against that immutable contract.",
    }
    write_document(Path(run["output"]) / "characterization.json", report)
    return report


def check_release(
    config: Any,
    project_path: Path,
    run_path: Path,
    *,
    output: Path | None = None,
    trust_path: Path | None = None,
    equivalence_memory_mb: int = 4096,
) -> dict[str, Any]:
    plan = _signoff_plan(config)
    if type(equivalence_memory_mb) is not int or not 256 <= equivalence_memory_mb <= 262144:
        raise ValueError("sign-off equivalence memory budget must be within 256..262144 MiB")
    with acquire_capability_lease(plan, config.work_dir, "cli.enterprise.signoff"):
        return _check_release(
            config,
            project_path,
            run_path,
            output=output,
            trust_path=trust_path,
            equivalence_memory_mb=equivalence_memory_mb,
        )


def _signoff_plan(config: Any) -> Any:
    plan = (
        resolve_configured_product_plan(config)
        if config.product.entitlement_path is not None
        else active_product_plan() or resolve_configured_product_plan(config)
    )
    require_capability(plan, "adapter.enterprise")
    return plan


def _check_release(
    config: Any,
    project_path: Path,
    run_path: Path,
    *,
    output: Path | None = None,
    trust_path: Path | None = None,
    equivalence_memory_mb: int = 4096,
) -> dict[str, Any]:
    project_path, run_path = project_path.resolve(), run_path.resolve()
    project = load_physical_project(project_path)
    if project["schema_version"] != 2:
        raise ValueError("sign-off requires a v2 SKY130 project")
    run = read_document(run_path)
    selected = run.get("selected")
    if selected not in {"baseline", "candidate-1", "candidate-2", "candidate-3"}:
        raise ValueError("sign-off needs an executed, selected implementation")
    work = project_input(run_path.parent, f"{selected}/analysis.json").parent
    analysis = read_document(work / "analysis.json")
    verify_artifacts(work, analysis["artifacts"])
    if set(run["source_inputs"]) != set(project["inputs"]):
        raise ValueError("run omits declared project inputs")
    verify_artifacts(project_path.parent, run["source_inputs"])
    verify_artifacts(work, run["source_inputs"])
    verify_artifacts(run_path.parent / "workflow", run["workflow_files"])
    verify_current_workflow(run["workflow_files"])
    if file_digest(project_path) != run.get("project_sha256"):
        raise ValueError("project changed after the selected run")
    policy = load_requirements(work / project["signoff_policy"], project)
    trust = trust_path or config.product.signoff_trust_policy_path
    checks = _native_checks(work, project, policy, analysis, trust, equivalence_memory_mb)
    verify_current_workflow(run["workflow_files"])
    verify_artifacts(work, run["source_inputs"])
    verify_artifacts(work, analysis["artifacts"])
    receipts = {name for check in checks.values() for name in check["artifacts"] if name.endswith(".receipt.json")}
    for name in receipts:
        receipt = project_input(work, name)
        verify_artifacts(receipt.parent, read_document(receipt)["artifacts"])
    destination = output or config.work_dir / "signoff/releases" / uuid.uuid4().hex
    if not destination.resolve().is_relative_to(config.work_dir.resolve()):
        raise ValueError("release output must remain inside the configured work directory")
    release_path = build_release(project_path, run_path, checks, destination)
    write_document(
        config.work_dir / "signoff/latest.json",
        {
            "release": release_path.relative_to(config.work_dir).as_posix(),
            "sha256": file_digest(release_path),
        },
    )
    return verify_release(release_path, trust)


def _native_checks(
    work: Path,
    project: dict[str, Any],
    policy: dict[str, Any],
    analysis: dict[str, Any],
    trust: Path | None,
    equivalence_memory_mb: int = 4096,
) -> dict[str, Any]:
    stage = work / "verification" / uuid.uuid4().hex
    stage.mkdir(parents=True)
    checks = {
        name: _result("unknown", "not_executed", "required analysis has not completed") for name in REQUIRED_CHECKS
    }
    checks["requirements"] = _requirements_check(work, project, policy, trust)
    assessment = assess_physical_requirements(physical_requirements(analysis), analysis)
    checks["timing"] = _result(
        "passed" if assessment["timing_closed"] else "failed",
        "OpenROAD/OpenSTA",
        ", ".join(assessment["unmet_requirements"]) or "every required timing scenario passes",
        ["analysis.json", "scenarios.json"],
        analysis["metrics"],
    )
    _equivalence_checks(work, project, stage, checks, equivalence_memory_mb)
    streamed = _perform(work, stage, "stream", "KLayout", lambda: {"files": stream_layout(work, project, stage)})
    if streamed["status"] == "passed":
        checks["drc_klayout"] = _perform(
            work, stage, "drc_klayout", "KLayout", lambda: klayout_drc(work, project, stage)
        )
        magic = _perform(work, stage, "drc_magic", "Magic", lambda: magic_extract(work, project, stage))
        checks["drc_magic"] = magic
        if magic["metrics"].get("complete") is True:
            checks["antenna"] = _result(
                "passed" if magic["metrics"]["antenna_violations"] == 0 else "failed",
                "Magic/OpenROAD",
                "final-layout antenna analysis",
                magic["artifacts"],
                magic["metrics"],
            )
            checks["lvs"] = _perform(work, stage, "lvs", "Netgen", lambda: netgen_lvs(work, project, stage))
        checks["density"] = _perform(work, stage, "density", "Magic", lambda: density_check(work, project, stage))
    else:
        for name in ("drc_klayout", "drc_magic", "antenna", "lvs", "density"):
            checks[name] = _result(streamed["status"], streamed["tool"], streamed["reason"], streamed["artifacts"])
    _power_checks(work, project, policy, stage, checks)
    coverage = min(view["activity_coverage_percent"] for view in analysis["scenarios"].values())
    ready = project["activity"] is not None and coverage >= policy["activity_min_coverage_percent"]
    checks["activity"] = _result(
        "unknown" if project["activity"] is None else "passed" if ready else "failed",
        "OpenSTA",
        "measured VCD annotation coverage",
        ["scenarios.json"],
        {"minimum_coverage_percent": coverage},
    )
    return checks


def _requirements_check(
    work: Path, project: dict[str, Any], policy: dict[str, Any], trust: Path | None
) -> dict[str, Any]:
    gaps = requirements_gaps(policy, project)
    try:
        if trust is None:
            raise ValueError("independent sign-off trust policy is not configured")
        verify_role(policy, work / project["signoff_policy"], trust, "engineering")
    except (OSError, ValueError, KeyError, TypeError) as error:
        gaps.append(str(error))
    return _result(
        "passed" if not gaps else "unknown", "requirements_policy", ", ".join(gaps) or "approved requirements"
    )


def _equivalence_checks(
    work: Path, project: dict[str, Any], stage: Path, checks: dict[str, Any], memory_mb: int = 4096
) -> None:
    libraries = [work / name for name in project["libraries"] if "tt_025C_1v80" in name]
    for name, gold, gate in (
        ("equivalence_source", work / project["reference_netlist"], work / "mapped.v"),
        ("equivalence_final", work / "mapped.v", work / project["deliverables"]["netlist"]),
    ):
        checks[name] = _perform(
            work,
            stage,
            name,
            "Yosys",
            partial(
                prove_equivalence,
                gold,
                gate,
                libraries,
                project["design"],
                stage / name,
                timeout=86400,
                memory_mb=memory_mb,
            ),
        )


def _power_checks(
    work: Path, project: dict[str, Any], policy: dict[str, Any], stage: Path, checks: dict[str, Any]
) -> None:
    electrical = _perform(work, stage, "erc", "OpenROAD/OpenDB", lambda: electrical_connectivity(work, project, stage))
    checks["erc"] = electrical
    power = _perform(work, stage, "power_grid", "OpenROAD/PDNSim", lambda: analyze_power(work, project, policy, stage))
    checks["power_grid"] = power
    if power["status"] != "passed":
        for name in ("ir_drop", "em"):
            checks[name] = _result(power["status"], power["tool"], power["reason"], power["artifacts"])
        return
    actual, target = power["metrics"]["worst_ir_drop_v"], policy["limits"]["ir_drop_max_v"]
    checks["ir_drop"] = _limit_check("OpenROAD/PDNSim", "worst_ir_drop_v", actual, target, power["artifacts"])
    if electrical["status"] == "passed":
        density = _perform(
            work,
            stage,
            "em",
            "OpenROAD/PDNSim",
            lambda: {
                "max_current_density_a_um2": current_density_bound(electrical["metrics"], power["metrics"], policy)
            },
        )
        if density["status"] == "passed":
            density = _limit_check(
                "OpenROAD/PDNSim",
                "max_current_density_a_um2",
                density["metrics"]["max_current_density_a_um2"],
                policy["limits"]["em_max_current_density_a_um2"],
                power["artifacts"] + electrical["artifacts"],
            )
        checks["em"] = density


def _limit_check(tool: str, name: str, value: float, target: float | None, artifacts: list[str]) -> dict[str, Any]:
    state = "unknown" if target is None else "passed" if value <= target else "failed"
    return _result(
        state,
        tool,
        "approved limit is missing" if target is None else f"{name} <= {target}",
        artifacts,
        {name: value, "target": target},
    )


def _perform(work: Path, stage: Path, name: str, tool: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    status, metrics, reason = "passed", {}, "native analysis completed"
    try:
        metrics = action()
        violations = next((metrics[key] for key in ("violations", "drc_violations") if key in metrics), 0)
        if violations != 0:
            status, reason = "failed", f"{violations} violations"
    except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError) as error:
        status, reason = "unknown", str(error)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        status, reason = "failed", str(error)
    paths = [p.relative_to(work).as_posix() for p in sorted(stage.rglob("*")) if p.is_file()]
    paths += [p.name for p in sorted(work.glob(stage.name + "-*.*")) if p.is_file()]
    return _result(status, tool, reason, paths, metrics)


def _result(
    status: str, tool: str, reason: str, artifacts: list[str] | None = None, metrics: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "status": status,
        "tool": tool,
        "reason": reason,
        "artifacts": sorted(set(artifacts or [])),
        "metrics": metrics or {},
    }


def dispatch_signoff(args: Any, config: Any) -> tuple[dict[str, Any], bool]:
    trust = args.trust_policy or config.product.signoff_trust_policy_path
    if args.action == "characterize":
        if args.project is None:
            raise ValueError("characterize requires --project")
        return characterize(config, args.project.resolve()), True
    if args.action == "check":
        if args.project is None or args.run is None:
            raise ValueError("check requires --project and --run")
        result = check_release(
            config,
            args.project,
            args.run,
            output=args.output,
            trust_path=trust,
            equivalence_memory_mb=args.equivalence_memory_mb,
        )
        return result, result["engineering_ready"]
    if args.action == "import-approval":
        if args.release is None or args.approval is None or trust is None:
            raise ValueError("import-approval requires --release, --approval, and independent --trust-policy")
        return import_approval(args.release, args.approval, trust), True
    result = verify_release(args.release, trust) if args.release is not None else collect_signoff_status(config)
    return result, args.policy != "ci" or result["signoff_approved"]
