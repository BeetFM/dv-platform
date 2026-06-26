"""Read-only local platform status and compatibility reporting."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil

from dv_platform.analysis.plan_store import MIN_READABLE_PLAN_SCHEMA_VERSION, PLAN_SCHEMA_VERSION, read_plan_records
from dv_platform.analysis.rtl import MIN_READABLE_RTL_FACTS_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.core.models import CLIConfig, VerificationTarget


def collect_platform_status(config: CLIConfig) -> dict[str, object]:
    """Collect local dv-platform state without modifying project files."""

    rtl_status = _rtl_facts_status(config)
    plan_status = _plan_status(config)
    generated = _generated_status(config)
    runs = _run_status(config)
    return {
        "schemas": {
            "rtl_facts": rtl_status,
            "plans": plan_status,
        },
        "tools": _tool_status(config, rtl_status),
        "generated": generated,
        "runs": runs,
        "summary": {
            "rtl_facts_status": rtl_status["status"],
            "plan_status": plan_status["status"],
            "generated_modules": len(generated["modules"]),
            "generated_artifacts": sum(int(module["artifacts"]) for module in generated["modules"]),
            "quality_failed": generated["quality_failed"],
            "run_summaries": len(runs["summaries"]),
            "failed_runs": runs["failed"],
        },
    }


def evaluate_status_policy(
    status: dict[str, object],
    require_tools: bool = True,
) -> tuple[dict[str, object], ...]:
    """Return CI policy failures for a collected platform status report."""

    failures: list[dict[str, object]] = []
    schemas = status["schemas"]
    for name, schema in (("rtl_facts", schemas["rtl_facts"]), ("plans", schemas["plans"])):
        schema_status = schema["status"]
        if schema_status in {"future", "unsupported", "invalid"}:
            failures.append(
                {
                    "code": f"{name}_schema_{schema_status}",
                    "message": f"{name} schema status is {schema_status}",
                }
            )

    generated = status["generated"]
    if int(generated["quality_failed"]) > 0:
        failures.append(
            {
                "code": "generated_quality_failed",
                "message": f"{generated['quality_failed']} generated artifact quality requirements failed",
            }
        )

    runs = status["runs"]
    if int(runs["failed"]) > 0:
        failures.append(
            {
                "code": "runs_failed",
                "message": f"{runs['failed']} run summaries are not passing",
            }
        )

    if require_tools:
        tools = status["tools"]
        if not bool(tools["verilator"]["available"]):
            failures.append(
                {
                    "code": "verilator_missing",
                    "message": "Configured Verilator command is not available",
                }
            )
        for simulator in tools["simulators"]:
            if not bool(simulator["available"]):
                failures.append(
                    {
                        "code": "simulator_missing",
                        "message": f"Configured simulator is not available: {simulator['name']}",
                    }
                )
        for tool in tools["formal_tools"]:
            if not bool(tool["available"]):
                failures.append(
                    {
                        "code": "formal_tool_missing",
                        "message": f"Configured formal tool is not available: {tool['name']}",
                    }
                )

    return tuple(failures)


def _rtl_facts_status(config: CLIConfig) -> dict[str, object]:
    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    result: dict[str, object] = {
        "current_schema_version": RTL_FACTS_SCHEMA_VERSION,
        "min_readable_schema_version": MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
        "path": str(facts_path),
        "summary_path": str(summary_path),
        "present": facts_path.is_file(),
        "stored_schema_version": None,
        "verilator_version": None,
        "modules": 0,
        "status": "missing",
    }
    if not facts_path.is_file():
        return result
    try:
        payload = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["status"] = "invalid"
        result["error"] = str(error)
        return result
    stored_version = int(payload.get("schema_version", 1))
    result["stored_schema_version"] = stored_version
    result["verilator_version"] = payload.get("verilator_version")
    modules = payload.get("modules", ())
    result["modules"] = len(modules) if isinstance(modules, list) else 0
    result["status"] = _schema_status(
        stored_version,
        current=RTL_FACTS_SCHEMA_VERSION,
        minimum=MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
    )
    return result


def _plan_status(config: CLIConfig) -> dict[str, object]:
    plans_path = config.work_dir / "plans" / "plans.sqlite"
    result: dict[str, object] = {
        "current_schema_version": PLAN_SCHEMA_VERSION,
        "min_readable_schema_version": MIN_READABLE_PLAN_SCHEMA_VERSION,
        "path": str(plans_path),
        "present": plans_path.is_file(),
        "stored_schema_versions": [],
        "plans": 0,
        "status": "missing",
    }
    if not plans_path.is_file():
        return result
    try:
        records = read_plan_records(plans_path)
    except (OSError, ValueError) as error:
        result["status"] = "invalid"
        result["error"] = str(error)
        return result
    versions = tuple(sorted({int(record["plan"].get("schema_version", 1)) for record in records}))
    result["stored_schema_versions"] = list(versions)
    result["plans"] = len(records)
    statuses = tuple(
        _schema_status(version, current=PLAN_SCHEMA_VERSION, minimum=MIN_READABLE_PLAN_SCHEMA_VERSION)
        for version in versions
    )
    if not statuses:
        result["status"] = "empty"
    elif any(status == "future" for status in statuses):
        result["status"] = "future"
    elif any(status == "unsupported" for status in statuses):
        result["status"] = "unsupported"
    elif any(status == "legacy" for status in statuses):
        result["status"] = "legacy"
    else:
        result["status"] = "current"
    return result


def _tool_status(config: CLIConfig, rtl_status: dict[str, object]) -> dict[str, object]:
    return {
        "verilator": {
            "command": config.verilator_executable,
            "available": _command_available(config.verilator_executable),
            "stored_version": rtl_status.get("verilator_version"),
        },
        "simulators": [
            {
                "target": str(simulator.target),
                "name": simulator.name,
                "command": simulator.command,
                "available": _command_available(simulator.command),
            }
            for simulator in config.simulators
        ],
        "formal_tools": [
            {
                "name": tool.name,
                "command": tool.command,
                "available": _command_available(tool.command),
            }
            for tool in config.formal_tools
        ],
    }


def _generated_status(config: CLIConfig) -> dict[str, object]:
    modules: list[dict[str, object]] = []
    for target in VerificationTarget:
        modules_dir = (
            config.output_dir / "formal" / "modules"
            if target == VerificationTarget.FORMAL
            else config.output_dir / "simulation" / str(target) / "modules"
        )
        if not modules_dir.is_dir():
            continue
        for module_dir in sorted((path for path in modules_dir.iterdir() if path.is_dir()), key=lambda path: path.name):
            modules.append(_generated_module_status(target, module_dir))
    quality_failed = sum(int(module["quality_failed"]) for module in modules)
    return {
        "modules": modules,
        "quality_failed": quality_failed,
    }


def _generated_module_status(target: VerificationTarget, module_dir: Path) -> dict[str, object]:
    provenance_path = module_dir / "provenance.json"
    result: dict[str, object] = {
        "target": str(target),
        "module": module_dir.name,
        "path": str(module_dir),
        "provenance": str(provenance_path),
        "provenance_present": provenance_path.is_file(),
        "artifacts": 0,
        "quality_total": 0,
        "quality_failed": 0,
        "status": "missing_provenance",
    }
    if not provenance_path.is_file():
        return result
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["status"] = "invalid_provenance"
        result["error"] = str(error)
        return result
    artifacts = provenance.get("artifacts", ())
    if not isinstance(artifacts, list):
        result["status"] = "invalid_provenance"
        result["error"] = "artifacts is not a list"
        return result
    quality_requirements = [
        requirement
        for artifact in artifacts
        if isinstance(artifact, dict)
        for requirement in artifact.get("quality_requirements", ())
        if isinstance(requirement, dict)
    ]
    failed = tuple(requirement for requirement in quality_requirements if not bool(requirement.get("satisfied")))
    result["artifacts"] = len(artifacts)
    result["quality_total"] = len(quality_requirements)
    result["quality_failed"] = len(failed)
    result["status"] = "quality_failed" if failed else "ok"
    return result


def _run_status(config: CLIConfig) -> dict[str, object]:
    runs_dir = config.work_dir / "runs"
    summaries: list[dict[str, object]] = []
    if runs_dir.is_dir():
        for summary_path in sorted(runs_dir.rglob("summary.json"), key=lambda path: path.as_posix()):
            summaries.append(_run_summary_status(summary_path))
    failed = sum(1 for summary in summaries if summary.get("status") not in {"passed", "pass"})
    return {
        "summaries": summaries,
        "failed": failed,
    }


def _run_summary_status(summary_path: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "path": str(summary_path),
        "target": None,
        "module": None,
        "status": "invalid",
        "return_code": None,
    }
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["error"] = str(error)
        return result
    result["target"] = payload.get("target")
    result["module"] = payload.get("module")
    result["status"] = payload.get("status", payload.get("formal_status", "unknown"))
    result["return_code"] = payload.get("return_code")
    return result


def _schema_status(stored: int, current: int, minimum: int) -> str:
    if stored > current:
        return "future"
    if stored < minimum:
        return "unsupported"
    if stored < current:
        return "legacy"
    return "current"


def _command_available(command: str) -> bool:
    parts = shlex.split(command)
    if not parts:
        return False
    executable = parts[0]
    if Path(executable).is_absolute() or "/" in executable:
        return Path(executable).exists()
    return shutil.which(executable) is not None
