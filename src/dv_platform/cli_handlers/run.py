# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, cast

from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    validate_target_tools,
)
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget

if TYPE_CHECKING:
    from dv_platform.analysis.coverage import CoverageImporter, import_coverage_reports
    from dv_platform.core.plugins import LoadedAdapterPlugin
    from dv_platform.run import (
        discover_generated_modules,
        execute_formal_run,
        execute_simulation_run,
        prepare_formal_run,
        prepare_simulation_run,
        write_aggregate_run_summary,
    )


def _run(args: argparse.Namespace, config: CLIConfig) -> int:
    target = VerificationTarget(args.target)
    if args.timeout_seconds <= 0:
        _emit_error(args, "run", "invalid_timeout", "--timeout-seconds must be greater than zero.")
        return 2
    target_tool_diagnostics = validate_target_tools(config, (target,))
    if not getattr(args, "json_output", False):
        _print_diagnostics(target_tool_diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in target_tool_diagnostics):
        _emit_error(
            args,
            "run",
            "tool_configuration_error",
            "Target tool configuration is invalid.",
            diagnostics=target_tool_diagnostics,
        )
        return 2
    if target == VerificationTarget.FORMAL:
        return _run_formal(args, config, target)
    return _run_simulation(args, config, target)


def _run_formal(args: argparse.Namespace, config: CLIConfig, target: VerificationTarget) -> int:
    tool = config.formal_tools[0] if config.formal_tools else None
    if tool is None:
        _emit_error(
            args,
            "run",
            "missing_formal_tool",
            f"No formal tools configured for target {target}; add [[formal_tools]] to {DEFAULT_CONFIG_FILENAME}.",
        )
        return 2
    if args.all:
        return _run_all_formal_modules(args, config, tool, target)
    try:
        formal_run = prepare_formal_run(config, tool, args.module, timeout_seconds=args.timeout_seconds)
    except ValueError as error:
        _emit_error(args, "run", "invalid_module", str(error))
        return 2
    try:
        return_code = execute_formal_run(config, formal_run)
    except OSError as error:
        _emit_error(args, "run", "formal_execution_failed", str(error))
        return 2
    _emit_success(
        args,
        "run",
        {
            "target": str(target),
            "module": str(args.module),
            "formal_tool": tool.name,
            "formal_tool_command": tool.command,
            "run_dir": str(formal_run.run_dir),
            "summary": str(formal_run.summary_path),
            "return_code": return_code,
        },
        (
            "command=run",
            f"target={target}",
            f"module={args.module}",
            f"formal_tool={tool.name}",
            f"formal_tool_command={tool.command}",
            f"run_dir={formal_run.run_dir}",
            f"summary={formal_run.summary_path}",
            f"return_code={return_code}",
        ),
    )
    return return_code


def _run_simulation(args: argparse.Namespace, config: CLIConfig, target: VerificationTarget) -> int:
    simulator = next((item for item in config.simulators if item.target == target), None)
    if simulator is None:
        _emit_error(
            args,
            "run",
            "missing_simulator",
            f"No simulator configured for target {target}; add [[simulators]] to {DEFAULT_CONFIG_FILENAME}.",
        )
        return 2

    if args.all:
        return _run_all_generated_modules(args, config, simulator, target)

    try:
        simulation_run = prepare_simulation_run(config, simulator, args.module, timeout_seconds=args.timeout_seconds)
    except ValueError as error:
        _emit_error(args, "run", "invalid_module", str(error))
        return 2
    try:
        return_code = execute_simulation_run(simulation_run)
    except OSError as error:
        _emit_error(args, "run", "simulation_execution_failed", str(error))
        return 2

    _emit_success(
        args,
        "run",
        {
            "target": str(target),
            "module": str(args.module),
            "simulator": simulator.name,
            "simulator_command": simulator.command,
            "run_dir": str(simulation_run.run_dir),
            "summary": str(simulation_run.summary_path),
            "return_code": return_code,
        },
        (
            "command=run",
            f"target={target}",
            f"module={args.module}",
            f"simulator={simulator.name}",
            f"simulator_command={simulator.command}",
            f"run_dir={simulation_run.run_dir}",
            f"summary={simulation_run.summary_path}",
            f"return_code={return_code}",
        ),
    )
    return return_code


def _coverage(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded_adapters: tuple[LoadedAdapterPlugin, ...] = (),
) -> int:
    coverage_importers = tuple(
        cast(CoverageImporter, plugin.adapter) for plugin in loaded_adapters if plugin.kind == "coverage_importer"
    )
    inputs = tuple(args.input or ())
    if args.from_runs:
        inputs = tuple(dict.fromkeys((*inputs, *_coverage_run_summaries(config))))
    try:
        summary_path, summary = import_coverage_reports(
            config,
            inputs,
            coverage_importers=coverage_importers,
            as_of=args.as_of,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(args, "coverage", "coverage_import_failed", str(error))
        return 2
    data = {
        "coverage_summary": str(summary_path),
        "passed": bool(summary["passed"]),
        "metrics": summary["metrics"],
        "gates": summary["gates"],
        "gaps": summary["gaps"],
        "closure": summary["closure"],
        "closure_gaps": summary["closure_gaps"],
        "plan_feedback": summary["plan_feedback"],
        "parameter_sweeps": summary["parameter_sweeps"],
        "exports": summary["exports"],
    }
    if summary["passed"]:
        _emit_success(
            args,
            "coverage",
            data,
            (f"coverage_summary={summary_path}", "coverage_status=passed"),
        )
        return 0
    _emit_error(
        args,
        "coverage",
        "coverage_gate_failed",
        "One or more configured coverage thresholds were not met.",
        data=data,
    )
    return 1


def _coverage_run_summaries(config: CLIConfig) -> tuple[Path, ...]:
    runs_dir = config.work_dir / "runs"
    enterprise_runs_dir = config.work_dir / "enterprise-runs"
    run_summaries = (
        tuple(
            path
            for path in runs_dir.rglob("summary.json")
            if path.parent.name != "formal" and path.parent.parent.name != "simulation"
        )
        if runs_dir.is_dir()
        else ()
    )
    enterprise_summaries = tuple(enterprise_runs_dir.rglob("summary.json")) if enterprise_runs_dir.is_dir() else ()
    return tuple(sorted((*run_summaries, *enterprise_summaries), key=lambda item: item.as_posix()))


def _bounded_execution_workers(config: CLIConfig, target: VerificationTarget, module_count: int) -> int:
    """Bound fan-out by both the user setting and the child-process memory budget."""

    processes_per_run = 2 if target == VerificationTarget.FORMAL else 1
    memory_workers = config.max_total_process_memory_mb // (processes_per_run * config.max_process_memory_mb)
    return max(1, min(config.max_parallel_modules, module_count, memory_workers, config.license_tokens))


def _run_all_generated_modules(
    args: argparse.Namespace,
    config: CLIConfig,
    simulator: SimulatorConfig,
    target: VerificationTarget,
) -> int:
    try:
        modules = discover_generated_modules(config, target)
    except ValueError as error:
        _emit_error(args, "run", "generated_modules_invalid", str(error))
        return 2
    if not modules:
        _emit_error(
            args,
            "run",
            "generated_modules_missing",
            f"No generated modules found for target {target}; run generate first.",
        )
        return 2

    def execute_module(module: str) -> tuple[int, dict[str, object]]:
        run = prepare_simulation_run(config, simulator, module, timeout_seconds=args.timeout_seconds)
        return_code = execute_simulation_run(run)
        summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
        return return_code, {
            "module": module,
            "status": summary["status"],
            "return_code": return_code,
            "summary": str(run.summary_path),
        }

    try:
        if config.max_parallel_modules == 1:
            results = tuple(execute_module(module) for module in modules)
        else:
            with ThreadPoolExecutor(max_workers=_bounded_execution_workers(config, target, len(modules))) as executor:
                results = tuple(executor.map(execute_module, modules))
    except (OSError, ValueError) as error:
        _emit_error(args, "run", "aggregate_run_failed", str(error))
        return 2
    return_codes = [return_code for return_code, _summary in results]
    module_summaries = [summary for _return_code, summary in results]

    aggregate_path = write_aggregate_run_summary(config, target, tuple(module_summaries))
    final_return_code = max(return_codes) if any(return_codes) else 0

    data = {
        "target": str(target),
        "modules": list(modules),
        "runner": {"family": "simulator", "name": simulator.name, "command": simulator.command},
        "results": module_summaries,
        "aggregate_summary": str(aggregate_path),
        "return_code": final_return_code,
    }
    _emit_success(
        args,
        "run",
        data,
        (
            f"target={target}",
            "modules=" + ",".join(modules),
            f"simulator={simulator.name}",
            f"simulator_command={simulator.command}",
            f"aggregate_summary={aggregate_path}",
            f"return_code={final_return_code}",
        ),
    )
    return final_return_code


def _run_all_formal_modules(
    args: argparse.Namespace,
    config: CLIConfig,
    tool: FormalToolConfig,
    target: VerificationTarget,
) -> int:
    try:
        modules = discover_generated_modules(config, target)
    except ValueError as error:
        _emit_error(args, "run", "generated_modules_invalid", str(error))
        return 2
    if not modules:
        _emit_error(
            args,
            "run",
            "generated_modules_missing",
            f"No generated modules found for target {target}; run generate first.",
        )
        return 2

    def execute_module(module: str) -> tuple[int, dict[str, object]]:
        run = prepare_formal_run(config, tool, module, timeout_seconds=args.timeout_seconds)
        return_code = execute_formal_run(config, run)
        summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
        return return_code, {
            "module": module,
            "status": summary["status"],
            "return_code": return_code,
            "summary": str(run.summary_path),
        }

    try:
        if config.max_parallel_modules == 1:
            results = tuple(execute_module(module) for module in modules)
        else:
            with ThreadPoolExecutor(max_workers=_bounded_execution_workers(config, target, len(modules))) as executor:
                results = tuple(executor.map(execute_module, modules))
    except (OSError, ValueError) as error:
        _emit_error(args, "run", "aggregate_run_failed", str(error))
        return 2
    return_codes = [return_code for return_code, _summary in results]
    module_summaries = [summary for _return_code, summary in results]

    aggregate_path = write_aggregate_run_summary(config, target, tuple(module_summaries))
    final_return_code = max(return_codes) if any(return_codes) else 0

    data = {
        "target": str(target),
        "modules": list(modules),
        "runner": {"family": "formal", "name": tool.name, "command": tool.command},
        "results": module_summaries,
        "aggregate_summary": str(aggregate_path),
        "return_code": final_return_code,
    }
    _emit_success(
        args,
        "run",
        data,
        (
            f"target={target}",
            "modules=" + ",".join(modules),
            f"formal_tool={tool.name}",
            f"formal_tool_command={tool.command}",
            f"aggregate_summary={aggregate_path}",
            f"return_code={final_return_code}",
        ),
    )
    return final_return_code
