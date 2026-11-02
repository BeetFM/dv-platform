"""Entitled RTL experiments with immutable contracts, native proofs, and measured selection."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.rtl import propose_rtl_edit
from dv_platform.enterprise.native import snapshot_workflow, verify_current_workflow
from dv_platform.enterprise.physical_design import _validate_request
from dv_platform.enterprise.rtl import _read, lower_rtl_sources, prove_rtl_candidate, snapshot_rtl
from dv_platform.enterprise.rtl_frontend import freeze_frontend
from dv_platform.enterprise.rtl_physical import freeze_physical_project, load_rtl_project, measure_rtl
from dv_platform.entitlement_leases import acquire_capability_lease
from dv_platform.physical_design import evaluate_physical_candidate, file_digest, physical_requirements, write_document
from dv_platform.signoff import verify_artifacts


def run_rtl_optimization(config, project_path: Path, *, max_iterations: int = 3, model_client=None) -> dict[str, Any]:
    plan = _validate_request(config, True, max_iterations)
    project_path = project_path.resolve()
    project = load_rtl_project(project_path)
    with acquire_capability_lease(plan, config.work_dir, "cli.enterprise.rtl-optimize"):
        return _run(config, project_path, project, max_iterations, model_client)


def _run(config, path, project, limit, client) -> dict[str, Any]:
    output = config.work_dir / "rtl-optimization" / uuid.uuid4().hex
    output.mkdir(parents=True, mode=0o700)
    record: dict[str, Any] = {
        "schema_version": 1,
        "design": project["design"],
        "status": "running",
        "output": str(output),
        "project_sha256": file_digest(path),
        "signoff_approved": False,
        "iterations": [],
        "selected": "baseline",
        "model_call_count": 0,
        "model_transport": "injected_client" if client is not None else "configured_provider",
        "objective": project["objective"],
        "iteration_budget": limit,
    }
    write_document(output / "run.json", record)
    try:
        shutil.copyfile(path, output / "rtl-project.json")
        if file_digest(output / "rtl-project.json") != record["project_sha256"]:
            raise ValueError("RTL project manifest changed during capture")
        snapshot = snapshot_rtl(path.parent, project["sources"], project["documents"], output / "snapshot")
        snapshot["editable_sources"] = project.get("editable_sources", snapshot["sources"])
        write_document(output / "snapshot/snapshot.json", snapshot)
        record["snapshot"] = snapshot
        if "frontend" in project:
            record["frontend"] = freeze_frontend(path.parent, project["frontend"], output / "frontend")
            write_document(output / "frontend/config.json", record["frontend"])
        template = output / "physical-template"
        hashes = freeze_physical_project(path.parent / project["physical_project"], template)
        record["physical_inputs"] = hashes
        record["workflow_files"] = snapshot_workflow(output / "workflow")
        logical = lower_rtl_sources(
            output / "snapshot/inputs",
            snapshot["sources"],
            project["design"],
            output / "baseline-source",
            frontend=record.get("frontend"),
            memory_mb=project.get("memory_mb", 6144),
        )
        baseline = measure_rtl(
            config,
            project,
            template,
            logical,
            output / "baseline",
            rtl_inputs=_source_inputs(output, snapshot, output / "snapshot/inputs"),
        )
        record.update(baseline=baseline, best=baseline)
        _iterations(config, project, output, record, limit, client)
        verify_artifacts(output / "snapshot/inputs", snapshot["sha256"])
        verify_artifacts(template, hashes)
        if "frontend" in record:
            verify_artifacts(output / "frontend", {"sv2v": record["frontend"]["sha256"]})
        verify_current_workflow(record["workflow_files"])
        if file_digest(path) != record["project_sha256"]:
            raise ValueError("RTL project manifest changed during execution")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record.update(status="error", error=str(error))
    write_document(output / "run.json", record)
    return record


def _iterations(config, project, output, record, limit, client) -> None:
    snapshot = record["snapshot"]
    root = output / "snapshot/inputs"
    sources = {name: _read(root, name).decode("utf-8") for name in snapshot["editable_sources"]}
    documents = {name: _read(root, name).decode("utf-8") for name in snapshot["documents"]}
    gateway = LiteLLMGateway(config, client)
    record.update(status="no_improvement", stop_reason="iteration_budget_exhausted")
    for index in range(1, limit + 1):
        proposal, decision = propose_rtl_edit(
            gateway,
            sources,
            documents,
            record["best"]["analysis"],
            physical_requirements(record["baseline"]["analysis"]),
            _decision_history(record["iterations"]),
            project["objective"],
        )
        record["model_call_count"] += decision.attempts
        step: dict[str, Any] = {
            "iteration": index,
            "proposal": proposal,
            "ai_status": decision.status,
            "selected": False,
        }
        record["iterations"].append(step)
        _retain_receipt(config, output, step, decision)
        if proposal is None:
            record.update(status="ai_unavailable", stop_reason=decision.fallback_reason or "ai_unavailable")
            return
        if proposal["edits"] is None:
            record["stop_reason"] = "agent_stopped"
            return
        _candidate(config, project, output, record, step, index)
        write_document(output / "run.json", record)


def _decision_history(history) -> list[dict[str, Any]]:
    previous = []
    for step in history:
        item = {key: step[key] for key in ("iteration", "proposal", "selected")}
        item.update({key: step[key] for key in ("proof_status", "rejection", "evaluation") if key in step})
        if "candidate" in step:
            item["metrics"] = step["candidate"]["analysis"]["metrics"]
        previous.append(item)
    return previous


def _retain_receipt(config, output, step, decision) -> None:
    receipt = decision.run_record_path
    if receipt is None or receipt.is_symlink() or not receipt.resolve().is_relative_to(config.work_dir.resolve()):
        raise ValueError("RTL decision is missing its contained provenance receipt")
    destination = output / "ai-receipts" / f"iteration-{step['iteration']}.json"
    destination.parent.mkdir(exist_ok=True)
    shutil.copyfile(receipt, destination)
    step["ai_receipt"] = destination.relative_to(output).as_posix()
    step["ai_receipt_sha256"] = file_digest(destination)


def _candidate(config, project, output, record, step, index) -> None:
    work = output / f"candidate-{index}"
    try:
        proof = prove_rtl_candidate(
            output / "snapshot",
            record["snapshot"],
            step["proposal"]["edits"],
            project["design"],
            work,
            frontend=record.get("frontend"),
            memory_mb=project.get("memory_mb", 6144),
        )
        step["proof_status"] = proof["status"]
        if proof["status"] != "equivalent":
            step["rejection"] = proof.get("error", "RTL equivalence failed")
            return
        rtl_inputs = _source_inputs(output, record["snapshot"], work / "inputs")
        rtl_inputs.update(
            {
                "decision/receipt.json": output / step["ai_receipt"],
                "decision/source-proof.json": work / "candidate.json",
            }
        )
        candidate = measure_rtl(
            config,
            project,
            output / "physical-template",
            work / "candidate/logical.v",
            work / "physical",
            reference=output / "baseline-source/logical.v",
            rtl_inputs=rtl_inputs,
        )
        evaluation = evaluate_physical_candidate(
            record["baseline"]["analysis"], record["best"]["analysis"], candidate["analysis"]
        )
        objective = project["objective"]
        delta = candidate["analysis"]["metrics"][objective] - record["best"]["analysis"]["metrics"][objective]
        improved = delta > 1e-6 if objective == "setup_wns_ns" else delta < -1e-6
        selected = not evaluation["regressions"] and improved
        step.update(candidate=candidate, evaluation={**evaluation, "selected": selected}, selected=selected)
        if selected:
            record.update(best=candidate, selected=f"candidate-{index}", status="improved")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        step["rejection"] = str(error)


def _source_inputs(output, snapshot, selected) -> dict[str, Path]:
    inputs = {
        f"{label}/{name}": root / name
        for label, root in (("baseline", output / "snapshot/inputs"), ("selected", selected))
        for name in snapshot["sources"] + snapshot["documents"]
    }
    inputs["tools/rtl-project.json"] = output / "rtl-project.json"
    for name in ("sv2v", "config.json"):
        path = output / "frontend" / name
        if path.is_file():
            inputs["tools/" + name] = path
    return inputs
