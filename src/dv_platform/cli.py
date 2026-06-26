"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dv_platform.analysis.docs import (
    chunk_documents,
    discover_documentation_files,
    load_documents,
    read_configured_document_index,
    write_document_index,
)
from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans, write_plan_outputs
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.review import generate_design_decisions, generate_run_feedback_decisions, write_review_outputs
from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
from dv_platform.analysis.discovery import (
    build_verilator_dry_run_command,
    discover_project,
    write_project_manifest,
)
from dv_platform.analysis.rtl import (
    normalize_verilator_xml,
    read_normalized_rtl_facts,
    run_verilator_xml,
    write_normalized_rtl_facts,
    write_rtl_facts_summary,
    write_verilator_failure_summary,
)
from dv_platform.core.config import (
    ConfigDiagnostic,
    DEFAULT_CONFIG_FILENAME,
    default_config,
    load_config,
    normalize_config,
    validate_config,
    validate_target_tools,
    write_config,
)
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.generators import (
    CocotbGenerator,
    FormalGenerator,
    GeneratorRegistry,
    SystemVerilogGenerator,
    VerilogGenerator,
    VhdlGenerator,
    UvmGenerator,
    load_generator_plugins,
    write_generated_artifacts,
)
from dv_platform.run import (
    discover_generated_modules,
    execute_formal_run,
    execute_simulation_run,
    prepare_formal_run,
    prepare_simulation_run,
    write_aggregate_run_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dv-platform",
        description="Local agentic RTL verification generation CLI.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Path to project config. Defaults to <repo-root>/{DEFAULT_CONFIG_FILENAME}.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="RTL repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Local work directory for ASTs, indexes, logs, and intermediate state.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated verification collateral and reports.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Permit configured network calls. Disabled by default.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat incomplete local configuration as an error for input-consuming commands.",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Enable CI behavior. Implies strict validation for input-consuming commands.",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit a single machine-readable JSON response for supported commands.",
    )

    subcommands = parser.add_subparsers(dest="command")
    init = subcommands.add_parser("init", help="Create a local project configuration.")
    init.add_argument("--documentation-path", type=Path, action="append", default=None)
    init.add_argument("--rtl-filelist", type=Path, action="append", default=None)
    init.add_argument("--include-path", type=Path, action="append", default=None)
    init.add_argument("--define", action="append", default=None)
    init.add_argument("--top-module", action="append", default=None)
    init.add_argument("--verilator-executable", default=None)

    index_docs = subcommands.add_parser("index-docs", help="Build or refresh the documentation RAG index.")
    index_docs.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Maximum characters per documentation chunk.",
    )
    analyze_rtl = subcommands.add_parser("analyze-rtl", help="Extract RTL facts through configured tools.")
    analyze_rtl.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover inputs and print tool commands without invoking Verilator.",
    )
    plan = subcommands.add_parser("plan", help="Generate evidence-backed verification plans.")
    plan.add_argument(
        "--target",
        action="append",
        choices=[target.value for target in VerificationTarget],
        default=None,
        help="Verification target to include. May be repeated. Defaults to cocotb.",
    )
    generate = subcommands.add_parser("generate", help="Generate verification collateral.")
    generate.add_argument(
        "--target",
        required=True,
        choices=[target.value for target in VerificationTarget],
        help="Verification target to generate.",
    )
    run = subcommands.add_parser("run", help="Run configured simulation and formal tools.")
    run.add_argument(
        "--target",
        required=True,
        choices=[target.value for target in VerificationTarget],
        help="Verification target to run.",
    )
    run_module = run.add_mutually_exclusive_group(required=True)
    run_module.add_argument(
        "--module",
        help="Generated module to run.",
    )
    run_module.add_argument(
        "--all",
        action="store_true",
        help="Run every generated module for the target.",
    )
    run.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="Maximum simulator runtime before marking the run as timed out.",
    )
    subcommands.add_parser("review", help="Generate module design decision reports.")
    status = subcommands.add_parser("status", help="Report local platform state and schema compatibility.")
    status.add_argument(
        "--policy",
        choices=("report", "ci"),
        default="report",
        help="Use report-only status or CI policy failures. Defaults to report.",
    )
    status.add_argument(
        "--no-require-tools",
        action="store_true",
        help="In CI policy mode, do not fail only because configured tool commands are unavailable.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> CLIConfig:
    repo_root = args.repo_root or Path.cwd()
    config = default_config(repo_root)

    config_path = resolved_config_path(args, repo_root=config.repo_root)
    if args.command != "init" and config_path.is_file():
        config = load_config(config_path)

    work_dir = args.work_dir if args.work_dir is not None else config.work_dir
    output_dir = args.output_dir if args.output_dir is not None else config.output_dir
    repo_root = args.repo_root if args.repo_root is not None else config.repo_root
    retrieval_index_dir = args.work_dir / "rag-index" if args.work_dir is not None else config.retrieval_index_dir

    return normalize_config(
        CLIConfig(
            repo_root=repo_root,
            work_dir=work_dir,
            output_dir=output_dir,
            documentation_paths=config.documentation_paths,
            rtl_filelists=config.rtl_filelists,
            include_paths=config.include_paths,
            defines=config.defines,
            top_modules=config.top_modules,
            verilator_executable=config.verilator_executable,
            retrieval_index_dir=retrieval_index_dir,
            allow_network=args.allow_network or config.allow_network,
            strict=args.strict or args.ci or config.strict,
            ci=args.ci or config.ci,
            simulators=config.simulators,
            formal_tools=config.formal_tools,
            generator_plugins=config.generator_plugins,
        )
    )


def resolved_config_path(args: argparse.Namespace, repo_root: Path | None = None) -> Path:
    if args.config is not None:
        return args.config.expanduser().resolve(strict=False)
    root = (repo_root or args.repo_root or Path.cwd()).expanduser().resolve(strict=False)
    return root / DEFAULT_CONFIG_FILENAME


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        config = _init_config_from_args(args)
        config_path = resolved_config_path(args, repo_root=config.repo_root)
        write_config(config, config_path)
        _emit_success(
            args,
            "init",
            {
                "created_config": str(config_path),
                "repo_root": str(config.repo_root),
                "work_dir": str(config.work_dir),
                "output_dir": str(config.output_dir),
            },
            (f"created_config={config_path}",),
        )
        return 0

    config = config_from_args(args)
    if args.command == "index-docs":
        return _index_docs(args, config)
    if args.command == "analyze-rtl":
        return _analyze_rtl(args, config)
    if args.command == "plan":
        return _plan(args, config)
    if args.command == "generate":
        return _generate(args, config)
    if args.command == "run":
        return _run(args, config)
    if args.command == "review":
        return _review(args, config)
    if args.command == "status":
        return _status(args, config)

    print(f"command={args.command}")
    print(f"repo_root={config.repo_root}")
    print(f"work_dir={config.work_dir}")
    print(f"output_dir={config.output_dir}")
    print(f"retrieval_index_dir={config.retrieval_index_dir}")
    print(f"allow_network={config.allow_network}")
    print(f"strict={config.strict}")
    print(f"ci={config.ci}")
    return 0


def _init_config_from_args(args: argparse.Namespace) -> CLIConfig:
    config = default_config(args.repo_root or Path.cwd())
    documentation_paths = args.documentation_path or config.documentation_paths
    verilator_executable = args.verilator_executable or config.verilator_executable

    return normalize_config(
        CLIConfig(
            repo_root=args.repo_root or config.repo_root,
            work_dir=args.work_dir or config.work_dir,
            output_dir=args.output_dir or config.output_dir,
            documentation_paths=tuple(documentation_paths),
            rtl_filelists=tuple(args.rtl_filelist or ()),
            include_paths=tuple(args.include_path or ()),
            defines=tuple(args.define or ()),
            top_modules=tuple(args.top_module or ()),
            verilator_executable=verilator_executable,
            retrieval_index_dir=(args.work_dir or config.work_dir) / "rag-index",
            allow_network=args.allow_network,
            strict=args.strict or args.ci,
            ci=args.ci,
            generator_plugins=config.generator_plugins,
        )
    )


def _analyze_rtl(args: argparse.Namespace, config: CLIConfig) -> int:
    diagnostics = validate_config(config)
    if not getattr(args, "json_output", False):
        _print_diagnostics(diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in diagnostics):
        _emit_error(
            args,
            "analyze-rtl",
            "configuration_error",
            "RTL analysis configuration is invalid.",
            diagnostics=diagnostics,
        )
        return 2

    try:
        inventory = discover_project(config)
    except (OSError, ValueError) as error:
        _emit_error(args, "analyze-rtl", "discovery_failed", str(error))
        return 2

    verilator_command = build_verilator_dry_run_command(config, inventory)
    manifest_path = write_project_manifest(config, inventory, verilator_command, diagnostics)

    dry_run_data = {
        "dry_run": args.dry_run,
        "repo_root": str(config.repo_root),
        "hdl_files": len(inventory.hdl_files),
        "documentation_files": len(inventory.documentation_files),
        "include_paths": len(inventory.include_paths),
        "defines": len(inventory.defines),
        "manifest": str(manifest_path),
        "verilator_command": list(verilator_command),
        "diagnostics": _diagnostics_json(diagnostics),
    }
    if args.dry_run:
        _emit_success(
            args,
            "analyze-rtl",
            dry_run_data,
            (
                "command=analyze-rtl",
                f"dry_run={args.dry_run}",
                f"repo_root={config.repo_root}",
                f"hdl_files={len(inventory.hdl_files)}",
                f"documentation_files={len(inventory.documentation_files)}",
                f"include_paths={len(inventory.include_paths)}",
                f"defines={len(inventory.defines)}",
                f"manifest={manifest_path}",
                "verilator_command=" + " ".join(verilator_command),
            ),
        )
        return 0
    for line in (
        "command=analyze-rtl",
        f"dry_run={args.dry_run}",
        f"repo_root={config.repo_root}",
        f"hdl_files={len(inventory.hdl_files)}",
        f"documentation_files={len(inventory.documentation_files)}",
        f"include_paths={len(inventory.include_paths)}",
        f"defines={len(inventory.defines)}",
        f"manifest={manifest_path}",
        "verilator_command=" + " ".join(verilator_command),
    ):
        if not getattr(args, "json_output", False):
            print(line)

    try:
        run_result = run_verilator_xml(config, inventory)
    except OSError as error:
        _emit_error(args, "analyze-rtl", "verilator_execution_failed", str(error))
        return 2

    if run_result.return_code != 0:
        summary_path = write_verilator_failure_summary(config, run_result)
        data = {
            **dry_run_data,
            "verilator_return_code": run_result.return_code,
            "verilator_version": run_result.version or "unknown",
            "verilator_version_log": str(run_result.version_log),
            "verilator_stdout_log": str(run_result.stdout_log),
            "verilator_stderr_log": str(run_result.stderr_log),
            "verilator_xml_files": len(run_result.xml_files),
            "verilator_failure_summary": str(summary_path),
        }
        if not getattr(args, "json_output", False):
            for line in (
                f"verilator_return_code={run_result.return_code}",
                f"verilator_version={run_result.version or 'unknown'}",
                f"verilator_version_log={run_result.version_log}",
                f"verilator_stdout_log={run_result.stdout_log}",
                f"verilator_stderr_log={run_result.stderr_log}",
                f"verilator_xml_files={len(run_result.xml_files)}",
                f"verilator_failure_summary={summary_path}",
            ):
                print(line)
        _emit_error(
            args,
            "analyze-rtl",
            "verilator_failed",
            f"Verilator exited with return code {run_result.return_code}.",
            data=data,
        )
        return run_result.return_code

    modules = normalize_verilator_xml(run_result.xml_files)
    facts_path = write_normalized_rtl_facts(config, modules, run_result.version)
    summary_path = write_rtl_facts_summary(config, modules, run_result.version)
    data = {
        **dry_run_data,
        "verilator_return_code": run_result.return_code,
        "verilator_version": run_result.version or "unknown",
        "verilator_version_log": str(run_result.version_log),
        "verilator_stdout_log": str(run_result.stdout_log),
        "verilator_stderr_log": str(run_result.stderr_log),
        "verilator_xml_files": len(run_result.xml_files),
        "normalized_modules": len(modules),
        "rtl_facts": str(facts_path),
        "rtl_facts_summary": str(summary_path),
    }
    _emit_success(
        args,
        "analyze-rtl",
        data,
        (
            f"verilator_return_code={run_result.return_code}",
            f"verilator_version={run_result.version or 'unknown'}",
            f"verilator_version_log={run_result.version_log}",
            f"verilator_stdout_log={run_result.stdout_log}",
            f"verilator_stderr_log={run_result.stderr_log}",
            f"verilator_xml_files={len(run_result.xml_files)}",
            f"normalized_modules={len(modules)}",
            f"rtl_facts={facts_path}",
            f"rtl_facts_summary={summary_path}",
        ),
    )
    return 0


def _index_docs(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        documentation_files = discover_documentation_files(config.documentation_paths)
        documents = load_documents(documentation_files)
        chunks = chunk_documents(documents, max_chars=args.chunk_size)
        index_path = write_document_index(config, chunks)
    except (OSError, ValueError) as error:
        _emit_error(args, "index-docs", "index_failed", str(error))
        return 2

    _emit_success(
        args,
        "index-docs",
        {
            "repo_root": str(config.repo_root),
            "documentation_files": len(documentation_files),
            "chunks": len(chunks),
            "index": str(index_path),
        },
        (
            "command=index-docs",
            f"repo_root={config.repo_root}",
            f"documentation_files={len(documentation_files)}",
            f"chunks={len(chunks)}",
            f"index={index_path}",
        ),
    )
    return 0


def _plan(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        modules = read_normalized_rtl_facts(config)
    except OSError as error:
        _emit_error(args, "plan", "missing_rtl_facts", f"RTL facts are missing; run analyze-rtl first: {error}")
        return 2
    except ValueError as error:
        _emit_error(args, "plan", "invalid_rtl_facts", str(error))
        return 2

    try:
        documentation_chunks = read_configured_document_index(config)
    except OSError:
        documentation_chunks = ()

    targets = tuple(VerificationTarget(target) for target in (args.target or (VerificationTarget.COCOTB.value,)))
    plans = tuple(
        create_initial_plan(
            module,
            targets=targets,
            documentation_chunks=documentation_chunks,
            retrieval_index_dir=config.retrieval_index_dir or config.work_dir / "rag-index",
        )
        for module in modules
    )
    sqlite_path, module_paths, index_path, claim_report_paths = write_plan_outputs(
        config,
        plans,
        strict=config.strict or config.ci,
    )

    data = {
        "modules": len(modules),
        "documentation_chunks": len(documentation_chunks),
        "plans": len(plans),
        "plans_db": str(sqlite_path),
        "plan_index": str(index_path),
        "plan_markdown_files": len(module_paths),
        "claim_report_files": len(claim_report_paths),
    }
    _emit_success(
        args,
        "plan",
        data,
        (
            "command=plan",
            f"modules={data['modules']}",
            f"documentation_chunks={data['documentation_chunks']}",
            f"plans={data['plans']}",
            f"plans_db={sqlite_path}",
            f"plan_index={index_path}",
            f"plan_markdown_files={len(module_paths)}",
            f"claim_report_files={len(claim_report_paths)}",
        ),
    )
    return 0


def _generate(args: argparse.Namespace, config: CLIConfig) -> int:
    target = VerificationTarget(args.target)
    target_tool_diagnostics = validate_target_tools(config, (target,))
    if not getattr(args, "json_output", False):
        _print_diagnostics(target_tool_diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in target_tool_diagnostics):
        _emit_error(
            args,
            "generate",
            "tool_configuration_error",
            "Target tool configuration is invalid.",
            diagnostics=target_tool_diagnostics,
        )
        return 2

    if target not in {
        VerificationTarget.COCOTB,
        VerificationTarget.FORMAL,
        VerificationTarget.SYSTEMVERILOG,
        VerificationTarget.VERILOG,
        VerificationTarget.VHDL,
        VerificationTarget.UVM,
    }:
        _emit_error(args, "generate", "missing_generator", f"No generator registered for target: {target}")
        return 2

    plans_db = config.work_dir / "plans" / "plans.sqlite"
    if not plans_db.is_file():
        _emit_error(args, "generate", "missing_plans", f"Plans are missing; run plan first: {plans_db}")
        return 2

    try:
        plans = read_stored_plans(plans_db)
        records = read_plan_records(plans_db)
    except OSError as error:
        _emit_error(args, "generate", "missing_plans", f"Plans are missing; run plan first: {error}")
        return 2
    except ValueError as error:
        _emit_error(args, "generate", "invalid_plans", str(error))
        return 2

    blocked = tuple(record for record in records if not bool(record["gate"]["allowed"]))
    if blocked:
        modules = ", ".join(str(record["module"]) for record in blocked)
        _emit_error(
            args,
            "generate",
            "claim_gate_blocked",
            f"Generation blocked by claim gate for modules: {modules}",
            data={"blocked_modules": [str(record["module"]) for record in blocked]},
        )
        return 2

    selected_plans = tuple(plan for plan in plans if target in plan.targets)
    registry = GeneratorRegistry()
    registry.register(CocotbGenerator())
    registry.register(FormalGenerator())
    registry.register(SystemVerilogGenerator())
    registry.register(VerilogGenerator())
    registry.register(VhdlGenerator())
    registry.register(UvmGenerator())
    try:
        loaded_plugins = load_generator_plugins(registry, config.generator_plugins)
    except (LookupError, TypeError) as error:
        _emit_error(args, "generate", "plugin_load_failed", str(error))
        return 2
    artifacts = tuple(artifact for plan in selected_plans for artifact in registry.get(target).generate(plan))
    try:
        result = write_generated_artifacts(config, artifacts)
    except ValueError as error:
        _emit_error(args, "generate", "artifact_write_failed", str(error))
        return 2

    data = {
        "target": str(target),
        "plans": len(selected_plans),
        "generator_plugins": list(loaded_plugins),
        "artifacts": len(result.artifact_paths),
        "artifact_paths": [str(path) for path in result.artifact_paths],
        "provenance_manifests": len(result.provenance_paths),
        "provenance_paths": [str(path) for path in result.provenance_paths],
    }
    _emit_success(
        args,
        "generate",
        data,
        (
            "command=generate",
            f"target={target}",
            f"plans={len(selected_plans)}",
            f"generator_plugins={','.join(loaded_plugins)}",
            f"artifacts={len(result.artifact_paths)}",
            f"provenance_manifests={len(result.provenance_paths)}",
        ),
    )
    return 0


def _run(args: argparse.Namespace, config: CLIConfig) -> int:
    target = VerificationTarget(args.target)
    target_tool_diagnostics = validate_target_tools(config, (target,))
    if not getattr(args, "json_output", False):
        _print_diagnostics(target_tool_diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in target_tool_diagnostics):
        _emit_error(args, "run", "tool_configuration_error", "Target tool configuration is invalid.", diagnostics=target_tool_diagnostics)
        return 2
    if target == VerificationTarget.FORMAL:
        tool = config.formal_tools[0] if config.formal_tools else None
        if tool is None:
            _emit_error(args, "run", "missing_formal_tool", f"No formal tools configured for target {target}; add [[formal_tools]] to {DEFAULT_CONFIG_FILENAME}.")
            return 2
        if args.all:
            return _run_all_formal_modules(args, config, tool, target)
        run = prepare_formal_run(config, tool, args.module, timeout_seconds=args.timeout_seconds)
        try:
            return_code = execute_formal_run(config, run)
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
                "run_dir": str(run.run_dir),
                "summary": str(run.summary_path),
                "return_code": return_code,
            },
            (
                "command=run",
                f"target={target}",
                f"module={args.module}",
                f"formal_tool={tool.name}",
                f"formal_tool_command={tool.command}",
                f"run_dir={run.run_dir}",
                f"summary={run.summary_path}",
                f"return_code={return_code}",
            ),
        )
        return return_code

    simulator = next((item for item in config.simulators if item.target == target), None)
    if simulator is None:
        _emit_error(args, "run", "missing_simulator", f"No simulator configured for target {target}; add [[simulators]] to {DEFAULT_CONFIG_FILENAME}.")
        return 2

    if args.all:
        return _run_all_generated_modules(args, config, simulator, target)

    run = prepare_simulation_run(config, simulator, args.module, timeout_seconds=args.timeout_seconds)
    try:
        return_code = execute_simulation_run(run)
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
            "run_dir": str(run.run_dir),
            "summary": str(run.summary_path),
            "return_code": return_code,
        },
        (
            "command=run",
            f"target={target}",
            f"module={args.module}",
            f"simulator={simulator.name}",
            f"simulator_command={simulator.command}",
            f"run_dir={run.run_dir}",
            f"summary={run.summary_path}",
            f"return_code={return_code}",
        ),
    )
    return return_code


def _review(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        modules = read_normalized_rtl_facts(config)
    except OSError as error:
        _emit_error(args, "review", "missing_rtl_facts", f"RTL facts are missing; run analyze-rtl first: {error}")
        return 2
    except ValueError as error:
        _emit_error(args, "review", "invalid_rtl_facts", str(error))
        return 2

    decisions = (*generate_design_decisions(modules), *generate_run_feedback_decisions(config))
    sqlite_path, json_path, markdown_path = write_review_outputs(config, decisions)

    data = {
        "modules": len(modules),
        "findings": len(decisions),
        "review_db": str(sqlite_path),
        "review_json": str(json_path),
        "review_markdown": str(markdown_path),
    }
    _emit_success(
        args,
        "review",
        data,
        (
            "command=review",
            f"modules={len(modules)}",
            f"findings={len(decisions)}",
            f"review_db={sqlite_path}",
            f"review_json={json_path}",
            f"review_markdown={markdown_path}",
        ),
    )
    return 0


def _status(args: argparse.Namespace, config: CLIConfig) -> int:
    status = collect_platform_status(config)
    policy_mode = args.policy == "ci" or config.ci
    policy_failures = evaluate_status_policy(status, require_tools=not args.no_require_tools) if policy_mode else ()
    status = {**status, "policy": {"mode": "ci" if policy_mode else "report", "failures": list(policy_failures)}}
    summary = status["summary"]
    schemas = status["schemas"]
    rtl_schema = schemas["rtl_facts"]
    plan_schema = schemas["plans"]
    tools = status["tools"]
    lines = (
        "command=status",
        f"rtl_facts_schema={rtl_schema['status']}",
        f"rtl_facts_stored_schema={rtl_schema['stored_schema_version']}",
        f"rtl_facts_modules={rtl_schema['modules']}",
        f"plan_schema={plan_schema['status']}",
        f"plan_stored_schemas={','.join(str(item) for item in plan_schema['stored_schema_versions'])}",
        f"plans={plan_schema['plans']}",
        f"verilator_available={str(tools['verilator']['available']).lower()}",
        f"verilator_stored_version={tools['verilator']['stored_version']}",
        f"simulators={len(tools['simulators'])}",
        f"formal_tools={len(tools['formal_tools'])}",
        f"generated_modules={summary['generated_modules']}",
        f"generated_artifacts={summary['generated_artifacts']}",
        f"quality_missing={summary['quality_missing']}",
        f"quality_failed={summary['quality_failed']}",
        f"run_summaries={summary['run_summaries']}",
        f"failed_runs={summary['failed_runs']}",
        f"policy_mode={status['policy']['mode']}",
        f"policy_failures={len(policy_failures)}",
    )
    if policy_failures:
        _emit_error(
            args,
            "status",
            "status_policy_failed",
            "Status CI policy failed.",
            data=status,
        )
        if not getattr(args, "json_output", False):
            for line in lines:
                print(line)
            for failure in policy_failures:
                print(f"policy_failure={failure['code']}:{failure['message']}")
        return 2
    _emit_success(args, "status", status, lines)
    return 0


def _run_all_generated_modules(
    args: argparse.Namespace,
    config: CLIConfig,
    simulator: SimulatorConfig,
    target: VerificationTarget,
) -> int:
    modules = discover_generated_modules(config, target)
    if not modules:
        print(f"error=No generated modules found for target {target}; run generate first.")
        return 2

    module_summaries: list[dict[str, object]] = []
    return_codes: list[int] = []
    for module in modules:
        run = prepare_simulation_run(config, simulator, module, timeout_seconds=args.timeout_seconds)
        try:
            return_code = execute_simulation_run(run)
        except OSError as error:
            print(f"error={error}")
            return 2
        return_codes.append(return_code)
        summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
        module_summaries.append(
            {
                "module": module,
                "status": summary["status"],
                "return_code": return_code,
                "summary": str(run.summary_path),
            }
        )

    aggregate_path = write_aggregate_run_summary(config, target, tuple(module_summaries))
    final_return_code = max(return_codes) if any(return_codes) else 0

    print("command=run")
    print(f"target={target}")
    print("modules=" + ",".join(modules))
    print(f"simulator={simulator.name}")
    print(f"simulator_command={simulator.command}")
    print(f"aggregate_summary={aggregate_path}")
    print(f"return_code={final_return_code}")
    return final_return_code


def _run_all_formal_modules(
    args: argparse.Namespace,
    config: CLIConfig,
    tool: FormalToolConfig,
    target: VerificationTarget,
) -> int:
    modules = discover_generated_modules(config, target)
    if not modules:
        print(f"error=No generated modules found for target {target}; run generate first.")
        return 2

    module_summaries: list[dict[str, object]] = []
    return_codes: list[int] = []
    for module in modules:
        run = prepare_formal_run(config, tool, module, timeout_seconds=args.timeout_seconds)
        try:
            return_code = execute_formal_run(config, run)
        except OSError as error:
            print(f"error={error}")
            return 2
        return_codes.append(return_code)
        summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
        module_summaries.append(
            {
                "module": module,
                "status": summary["status"],
                "return_code": return_code,
                "summary": str(run.summary_path),
            }
        )

    aggregate_path = write_aggregate_run_summary(config, target, tuple(module_summaries))
    final_return_code = max(return_codes) if any(return_codes) else 0

    print("command=run")
    print(f"target={target}")
    print("modules=" + ",".join(modules))
    print(f"formal_tool={tool.name}")
    print(f"formal_tool_command={tool.command}")
    print(f"aggregate_summary={aggregate_path}")
    print(f"return_code={final_return_code}")
    return final_return_code


def _print_diagnostics(diagnostics: tuple[ConfigDiagnostic, ...]) -> None:
    for diagnostic in diagnostics:
        print(f"{diagnostic.severity}={diagnostic.message}")


def _emit_success(
    args: argparse.Namespace,
    command: str,
    data: dict[str, object],
    text_lines: tuple[str, ...],
) -> None:
    if getattr(args, "json_output", False):
        print(json.dumps({"ok": True, "command": command, "data": data}, indent=2, sort_keys=True))
        return
    for line in text_lines:
        print(line)


def _emit_error(
    args: argparse.Namespace,
    command: str,
    code: str,
    message: str,
    data: dict[str, object] | None = None,
    diagnostics: tuple[ConfigDiagnostic, ...] = (),
) -> None:
    if getattr(args, "json_output", False):
        payload: dict[str, object] = {
            "ok": False,
            "command": command,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if data:
            payload["data"] = data
        if diagnostics:
            payload["diagnostics"] = _diagnostics_json(diagnostics)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"error={message}")


def _diagnostics_json(diagnostics: tuple[ConfigDiagnostic, ...]) -> list[dict[str, str]]:
    return [{"severity": diagnostic.severity, "message": diagnostic.message} for diagnostic in diagnostics]


if __name__ == "__main__":
    raise SystemExit(main())
