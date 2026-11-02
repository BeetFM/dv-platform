"""Audited AI/OpenROAD repair iterations with independent OpenSTA replay."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dv_platform.ai.code_graph import code_graph_context
from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.model_client import ModelClient
from dv_platform.ai.physical_design import propose_physical_repair
from dv_platform.core.models import CLIConfig
from dv_platform.enterprise.adapters import EnterpriseInvocation, OpenROADRunner
from dv_platform.entitlement_leases import acquire_capability_lease
from dv_platform.physical_design import (
    assess_physical_requirements,
    evaluate_physical_candidate,
    file_digest,
    finite_metric,
    load_physical_project,
    physical_driver,
    physical_requirements,
    project_input,
    read_physical_analysis,
    tcl_string,
    write_document,
)
from dv_platform.physical_design import resolved_constraints_digest as _resolved_constraints_digest
from dv_platform.product import (
    ResolvedProductPlan,
    active_product_plan,
    require_capability,
    resolve_configured_product_plan,
)


def run_physical_optimization(
    config: CLIConfig,
    project_path: Path,
    *,
    use_ai: bool = False,
    max_iterations: int = 3,
    model_client: ModelClient | None = None,
) -> dict[str, Any]:
    plan = _validate_request(config, use_ai, max_iterations)
    with acquire_capability_lease(plan, config.work_dir, "cli.enterprise.physical-optimize"):
        return _run_physical_optimization(config, project_path, use_ai, max_iterations, model_client)


def _run_physical_optimization(config, project_path, use_ai, max_iterations, model_client) -> dict[str, Any]:
    project_path = project_path.resolve()
    project = load_physical_project(project_path)
    if project["schema_version"] == 2:
        from dv_platform.sky130 import validate_tool_fingerprints

        validate_tool_fingerprints(project_path.parent, project, ("openroad", "sta", "yosys"))
    source = project_path.parent
    inputs = {name: file_digest(source / name) for name in project["inputs"]}
    tools = {name: _executable(name) for name in ("openroad", "sta")}
    run_id = uuid.uuid4().hex
    output = config.work_dir / "physical-design" / run_id
    output.mkdir(parents=True, mode=0o700)
    record: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "design": project["design"],
        "status": "running",
        "created_at": datetime.now(UTC).isoformat(),
        "ai_requested": use_ai,
        "ai_invoked": False,
        "model_call_count": 0,
        "model_accepted_responses": 0,
        "model_transport": "injected_client" if model_client is not None else "configured_provider",
        "model": config.ai.model if use_ai else None,
        "iterations": [],
        "iteration_budget": max_iterations,
        "stop_reason": "measurement_only",
        "source_inputs": inputs,
        "project_sha256": file_digest(project_path),
        "workflow_sha256": file_digest(Path(__file__)),
        "tools": {name: _version(path) for name, path in tools.items()},
        "output": str(output),
        "logical_equivalence": "not_checked",
        "signoff_approved": False,
    }
    if project["schema_version"] == 2:
        from dv_platform.enterprise.native import snapshot_workflow

        record["workflow_files"] = snapshot_workflow(output / "workflow")
    record_path = output / "run.json"
    write_document(record_path, record)
    try:
        baseline = _execute_case(config, output / "baseline", source, project, inputs, tools, None)
        requirements = physical_requirements(baseline)
        record.update(
            {
                "baseline": baseline,
                "selected": "baseline",
                "best": baseline,
                "requirements": requirements,
                "assessment": assess_physical_requirements(requirements, baseline),
            }
        )
        if record["assessment"]["timing_closed"]:
            record["stop_reason"] = "timing_closed"
        elif use_ai:
            _repair_iterations(config, output, source, project, inputs, tools, record, max_iterations, model_client)
        if record["status"] == "running":
            record["status"] = "timing_closed" if record["assessment"]["timing_closed"] else "timing_open"
        if file_digest(project_path) != record["project_sha256"]:
            raise ValueError("physical project manifest changed during execution")
        _verify_inputs(source, inputs)
        if project["schema_version"] == 2:
            from dv_platform.enterprise.native import verify_current_workflow

            verify_current_workflow(record["workflow_files"])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record.update(status="error", stop_reason="execution_error", error=str(error))
        record["finished_at"] = datetime.now(UTC).isoformat()
        write_document(record_path, record)
        raise ValueError(f"physical design run failed; evidence: {record_path}: {error}") from error
    record["finished_at"] = datetime.now(UTC).isoformat()
    write_document(record_path, record)
    return record


def _validate_request(config: CLIConfig, use_ai: bool, max_iterations: int) -> ResolvedProductPlan:
    plan = (
        resolve_configured_product_plan(config)
        if config.product.entitlement_path is not None
        else active_product_plan() or resolve_configured_product_plan(config)
    )
    require_capability(plan, "adapter.enterprise")
    if not isinstance(use_ai, bool):
        raise ValueError("use_ai must be a boolean")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or not 1 <= max_iterations <= 3:
        raise ValueError("physical optimization must use 1..3 iterations")
    return plan


def _repair_iterations(config, output, source, project, inputs, tools, record, limit, client) -> None:
    gateway = LiteLLMGateway(config, client)
    graph = code_graph_context(config, SimpleNamespace(name=project["design"], source=None))
    record["code_graph"] = {"status": graph.status, "calls": graph.calls, "provenance": graph.provenance}
    if config.ci and graph.status == "error":
        raise RuntimeError("code-graph optimization failed in CI")
    record["stop_reason"] = "iteration_budget_exhausted"
    for index in range(1, limit + 1):
        proposal, decision = propose_physical_repair(
            gateway, record["best"], record["iterations"], record["requirements"], advisory_context=graph.text
        )
        record["ai_invoked"] = record["ai_invoked"] or decision.attempts > 0
        record["model_call_count"] += decision.attempts
        record["model_accepted_responses"] += int(decision.status == "accepted" and decision.response is not None)
        step: dict[str, Any] = {
            "iteration": index,
            "ai_status": decision.status,
            "ai_run_record": str(decision.run_record_path),
            "attempts": decision.attempts,
            "fallback_reason": decision.fallback_reason,
            "proposal": proposal,
            "reference": record["selected"],
        }
        record["iterations"].append(step)
        if project["schema_version"] == 2:
            receipt = decision.run_record_path
            if (
                receipt is None
                or receipt.is_symlink()
                or not receipt.resolve().is_relative_to(config.work_dir.resolve())
            ):
                raise ValueError("AI decision is missing its contained provenance receipt")
            receipts = output / "ai-receipts"
            receipts.mkdir(mode=0o700, exist_ok=True)
            destination = receipts / f"iteration-{index}.json"
            shutil.copyfile(receipt, destination)
            step["ai_receipt_sha256"] = file_digest(destination)
        if decision.status != "accepted" or proposal is None:
            record["status"] = "ai_unavailable"
            record["stop_reason"] = decision.fallback_reason or "ai_unavailable"
            return
        write_document(output / f"proposal-{index}.json", proposal)
        if proposal["repair"] is None:
            record["stop_reason"] = "agent_stopped"
            return
        candidate = _execute_case(
            config, output / f"candidate-{index}", source, project, inputs, tools, proposal["repair"]
        )
        if candidate["metrics"]["repair_design_calls"] < 1 or candidate["metrics"]["repair_timing_calls"] < 1:
            raise ValueError("the supplied flow did not execute both requested repair operations")
        evaluation = evaluate_physical_candidate(record["baseline"], record["best"], candidate)
        step.update({"candidate": candidate, "selected": evaluation["selected"], "evaluation": evaluation})
        if evaluation["selected"]:
            record.update({"best": candidate, "selected": f"candidate-{index}", "assessment": evaluation["assessment"]})
        write_document(output / "run.json", record)
        if record["assessment"]["timing_closed"]:
            record["stop_reason"] = "timing_closed"
            return


def _execute_case(config, work, source, project, inputs, tools, repair) -> dict[str, Any]:
    _verify_inputs(source, inputs)
    work.mkdir(mode=0o700)
    for name in inputs:
        destination = work / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    driver = physical_driver(project, repair)
    (work / "pd-driver.tcl").write_text(driver, encoding="utf-8")
    invocation = EnterpriseInvocation(
        adapter="openroad",
        family="analyzer",
        command=_bounded_openroad_command(tools["openroad"]),
        cwd=work,
        result_path=work / "pd-result.json",
        summary_path=work / "pd-summary.json",
        stdout_path=work / "openroad.stdout.log",
        stderr_path=work / "openroad.stderr.log",
        timeout_seconds=86400 if project["schema_version"] == 2 else 300,
        redact_patterns=config.redact_patterns,
        environment_names=("RESULTS_DIR",),
        environment=(("RESULTS_DIR", "results"),),
    )
    result = OpenROADRunner().execute(invocation, strict=True)
    if not result.passed:
        raise ValueError(f"OpenROAD analysis did not complete: {work}")
    logical_artifacts = []
    if project["schema_version"] == 2:
        from dv_platform.enterprise.timing import export_logical_netlist

        logical_artifacts = export_logical_netlist(work, project, tools["openroad"])
    _verify_inputs(work, inputs)
    parasitics = work / project["parasitics"]
    if (
        not parasitics.resolve().is_relative_to(work.resolve())
        or not parasitics.is_file()
        or not parasitics.stat().st_size
    ):
        raise ValueError("the OpenROAD flow did not produce contained, non-empty parasitics")
    analysis = _primary_analysis(work, project, tools["sta"])
    artifacts = [
        *logical_artifacts,
        "pd-driver.tcl",
        "pd-metrics.json",
        "pd-export.v",
        "pd-export.sdc",
        "pd-final.odb",
        "pd-final.def",
        "pd-timing.rpt",
        "pd-power.rpt",
        "pd-power.json",
        "pd-summary.json",
        "sta-driver.tcl",
        "sta-result.json",
        "openroad.stdout.log",
        "openroad.stderr.log",
        "sta.stdout.log",
        "sta.stderr.log",
        project["parasitics"],
    ]
    analysis.update(
        {
            "repair": repair,
            "artifacts": {name: file_digest(work / name) for name in artifacts},
            "directory": str(work),
            "constraints_sha256": {name: file_digest(work / name) for name in project["constraints"]},
            "resolved_constraints_sha256": _resolved_constraints_digest(work / "pd-export.sdc"),
        }
    )
    if project["schema_version"] == 2:
        from dv_platform.enterprise.timing import augment_analysis, scenario_artifacts

        augment_analysis(analysis, work, project, tools)
        _verify_primary_scenario(analysis, project)
        analysis["artifacts"].update(scenario_artifacts(work, project))
    write_document(work / "analysis.json", analysis)
    return analysis


def _verify_primary_scenario(analysis: dict[str, Any], project: dict[str, Any]) -> None:
    if analysis.get("implementation_view_count", 1) <= 1:
        return
    primary = [
        view
        for view in project["scenarios"]
        if view["pvt"] == "tt_025C_1v80"
        and view["parasitics"] == project["parasitics"]
        and view["constraints"] == project["constraints"]
    ]
    if len(primary) != 1:
        raise ValueError("multi-view implementation requires one declared typical primary scenario")
    replay = analysis["scenarios"][primary[0]["name"]]["embedded_metrics"]
    for key in ("setup_wns_ns", "hold_wns_ns", "setup_tns_ns", "constraints_ok"):
        field = "constraint_slack" if key == "constraints_ok" else key
        expected = float(replay[field] >= 0) if key == "constraints_ok" else replay[field]
        if abs(analysis["standalone_sta"][key] - expected) > 1e-6:
            raise ValueError(f"standalone OpenSTA disagrees with the primary scenario: {key}")


def _primary_analysis(work: Path, project: dict[str, Any], sta: str) -> dict[str, Any]:
    views = 1
    if project["schema_version"] == 2:
        count = finite_metric(json.loads((work / "pd-metrics.json").read_text()), "PD::view_count")
        if count != 1:
            views = len({scenario["pvt"] for scenario in project["scenarios"]})
    analysis = read_physical_analysis(work / "pd-metrics.json", expected_view_count=views)
    analysis["standalone_sta"] = _replay_sta(work, project, sta)
    if views > 1:
        # Aggregate repair timing is compared with all nine independent views below.
        analysis["implementation_view_count"] = views
        return analysis
    for key in ("setup_wns_ns", "hold_wns_ns", "setup_tns_ns"):
        if abs(analysis["standalone_sta"][key] - analysis["metrics"][key]) > 1e-6:
            raise ValueError(f"standalone OpenSTA disagrees with embedded timing: {key}")
    if analysis["standalone_sta"]["constraints_ok"] != analysis["metrics"]["constraints_ok"]:
        raise ValueError("standalone OpenSTA disagrees about constraint completeness")
    return analysis


def _replay_sta(work: Path, project: dict[str, Any], executable: str) -> dict[str, float]:
    libraries = project["libraries"]
    if project["schema_version"] == 2:
        libraries = next(view["libraries"] for view in project["scenarios"] if view["pvt"] == "tt_025C_1v80")
    lines = [f"read_liberty {tcl_string(name)}" for name in libraries]
    lines += [
        "read_verilog pd-export.v",
        f"link_design {tcl_string(project['design'])}",
        "read_sdc pd-export.sdc",
        f"read_spef {tcl_string(project['parasitics'])}",
        "set pd_scale [expr {[sta::time_ui_sta 1.0] * 1e9}]",
        "set pd_output [open sta-result.json w]",
        'puts $pd_output [format {{"setup_wns_ns":%.17g,"hold_wns_ns":%.17g,"setup_tns_ns":%.17g,"constraints_ok":%d}} \\\n'
        "  [expr {[sta::worst_slack -max] * $pd_scale}] [expr {[sta::worst_slack -min] * $pd_scale}] \\\n"
        "  [expr {[sta::total_negative_slack -max] * $pd_scale}] [check_setup -verbose]]",
        "close $pd_output",
        "exit",
    ]
    (work / "sta-driver.tcl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (work / "sta.stdout.log").open("w") as stdout, (work / "sta.stderr.log").open("w") as stderr:
        completed = subprocess.run(
            (executable, "-no_init", "-exit", "sta-driver.tcl"),
            cwd=work,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            check=False,
            timeout=60,
        )
    if completed.returncode != 0:
        raise ValueError("standalone OpenSTA execution failed")
    report = json.loads((work / "sta-result.json").read_text(encoding="utf-8"))
    fields = ("setup_wns_ns", "hold_wns_ns", "setup_tns_ns", "constraints_ok")
    if not isinstance(report, dict) or set(report) != set(fields):
        raise ValueError("standalone OpenSTA report is incomplete")
    return {name: finite_metric(report, name) for name in fields}


def _verify_inputs(root: Path, expected: dict[str, str]) -> None:
    for name, digest in expected.items():
        path = project_input(root, name)
        if file_digest(path) != digest:
            raise ValueError(f"physical project input changed or escaped its project: {name}")


def _bounded_openroad_command(executable: str) -> tuple[str, ...]:
    from dv_platform.enterprise.native import address_space_limit

    limit = address_space_limit(4096)
    return (
        _executable("prlimit"),
        f"--as={limit}",
        "--core=0",
        "--",
        executable,
        "-no_init",
        "-exit",
        "-metrics",
        "pd-metrics.json",
        "pd-driver.tcl",
    )


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ValueError(f"physical design requires the {name} executable")
    return executable


def _version(executable: str) -> str:
    try:
        completed = subprocess.run(
            (executable, "-version"), check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"could not determine physical tool version: {Path(executable).name}") from error
    version = (completed.stdout or completed.stderr).strip()
    if not version:
        raise ValueError(f"physical tool returned an empty version: {Path(executable).name}")
    return version
