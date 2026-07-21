"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    ConfigDiagnostic,
    default_config,
    load_config,
    normalize_config,
    validate_ai_config,
    validate_config,
    validate_target_tools,
    write_config,
)
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget

if TYPE_CHECKING:
    from dv_platform.analysis.ai_planning import augment_plans
    from dv_platform.analysis.coverage import CoverageImporter, import_coverage_reports
    from dv_platform.analysis.discovery import build_verilator_dry_run_command, discover_project, write_project_manifest
    from dv_platform.analysis.docs import (
        chunk_documents,
        discover_documentation_files,
        load_documents,
        read_configured_document_index,
        write_document_index,
    )
    from dv_platform.analysis.feedback import normalize_feedback
    from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans, write_plan_outputs
    from dv_platform.analysis.planner import create_initial_plan
    from dv_platform.analysis.registers import (
        RegisterAnalysis,
        extract_registers_from_documentation,
        extract_registers_from_rtl,
        load_register_map,
        merge_register_sources,
    )
    from dv_platform.analysis.review import (
        generate_design_decisions,
        generate_run_feedback_decisions,
        write_review_outputs,
    )
    from dv_platform.analysis.revisions import create_feedback_revision, read_revisions
    from dv_platform.analysis.rtl import (
        classify_verilator_version,
        normalize_verilator_xml,
        read_normalized_rtl_facts,
        run_verilator_xml,
        write_normalized_rtl_facts,
        write_rtl_facts_summary,
        write_verilator_failure_summary,
    )
    from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
    from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
    from dv_platform.core.security import append_audit_event
    from dv_platform.enterprise.store import read_requirements_baseline
    from dv_platform.generators import (
        CocotbGenerator,
        FormalGenerator,
        GeneratorRegistry,
        SystemVerilogGenerator,
        UvmGenerator,
        VerilogGenerator,
        VhdlGenerator,
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
    init.add_argument(
        "--parameter",
        action="append",
        default=None,
        metavar="NAME=VALUE",
        help="Override a top-level RTL parameter during Verilator elaboration. May be repeated.",
    )
    init.add_argument(
        "--parameter-sweep",
        action="append",
        default=None,
        metavar="NAME=VALUE[,NAME=VALUE...]",
        help="Add one parameter elaboration point. May be repeated.",
    )
    init.add_argument("--top-module", action="append", default=None)
    init.add_argument("--verilator-executable", default=None)
    init.add_argument("--slang-executable", default=None)
    init.add_argument(
        "--semantic-crosscheck",
        choices=("off", "report", "required"),
        default=None,
        help="Configure independent Slang checking. Defaults to off.",
    )

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
    analyze_rtl.add_argument(
        "--force",
        action="store_true",
        help="Ignore a matching RTL analysis cache and invoke Verilator again.",
    )
    plan = subcommands.add_parser("plan", help="Generate evidence-backed verification plans.")
    plan.add_argument(
        "--target",
        action="append",
        choices=[target.value for target in VerificationTarget],
        default=None,
        help="Verification target to include. May be repeated. Defaults to cocotb.",
    )
    plan.add_argument(
        "--ai",
        action="store_true",
        help="Request optional evidence-bounded AI augmentation of deterministic plans.",
    )
    plan.add_argument(
        "--module",
        action="append",
        default=None,
        help="Module to augment with AI. May be repeated; deterministic plans are still written for every module.",
    )
    plan.add_argument(
        "--ai-refresh",
        action="store_true",
        help="Bypass validated AI proposal caches and request fresh proposals.",
    )
    generate = subcommands.add_parser("generate", help="Generate verification collateral.")
    generate.add_argument(
        "--target",
        required=True,
        choices=[target.value for target in VerificationTarget],
        help="Verification target to generate.",
    )
    generate.add_argument(
        "--cdc-policy",
        choices=("fail-closed", "bounded", "structural"),
        default="fail-closed",
        help="CDC evidence policy for formal generation. Defaults to fail-closed.",
    )
    generate.add_argument(
        "--cdc-bmc-depth",
        type=int,
        default=20,
        help="Bounded CDC verification depth when --cdc-policy bounded is selected.",
    )
    generate.add_argument("--revision", default=None, help="Plan revision ID (defaults to latest valid plan).")
    run = subcommands.add_parser("run", help="Run configured simulation and formal tools.")
    run.add_argument(
        "--target",
        required=True,
        choices=[target.value for target in VerificationTarget],
        help="Verification target to run.",
    )
    coverage = subcommands.add_parser("coverage", help="Import, merge, and gate local coverage reports.")
    coverage.add_argument(
        "--input",
        type=Path,
        action="append",
        help=("LCOV, JSON, Cobertura-style XML, or configured adapter report. May be repeated."),
    )
    coverage.add_argument(
        "--from-runs",
        action="store_true",
        help="Import all persisted simulation and formal module run summaries.",
    )
    coverage.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="ISO date used to evaluate waiver expiration reproducibly.",
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
    feedback = subcommands.add_parser("feedback", help="Normalize run feedback and create an immutable plan revision.")
    feedback_modules = feedback.add_mutually_exclusive_group(required=True)
    feedback_modules.add_argument("--module", help="Module whose feedback should be revised.")
    feedback_modules.add_argument(
        "--all", action="store_true", help="Create feedback revisions for every stored module."
    )
    feedback.add_argument(
        "--input",
        type=Path,
        action="append",
        default=None,
        help="JSON summary or per-check result file; may be repeated.",
    )
    feedback.add_argument("--target", choices=[target.value for target in VerificationTarget], default="cocotb")
    feedback.add_argument("--dry-run", action="store_true", help="Recommend changes without writing revisions.")
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
            register_map_paths=config.register_map_paths,
            rtl_filelists=config.rtl_filelists,
            include_paths=config.include_paths,
            defines=config.defines,
            parameter_overrides=config.parameter_overrides,
            parameter_sweeps=config.parameter_sweeps,
            top_modules=config.top_modules,
            verilator_executable=config.verilator_executable,
            slang_executable=config.slang_executable,
            semantic_crosscheck=config.semantic_crosscheck,
            retrieval_index_dir=retrieval_index_dir,
            allow_network=args.allow_network or config.allow_network,
            strict=args.strict or args.ci or config.strict,
            ci=args.ci or config.ci,
            simulators=config.simulators,
            formal_tools=config.formal_tools,
            generator_plugins=config.generator_plugins,
            adapter_plugins=config.adapter_plugins,
            protocol_profiles=config.protocol_profiles,
            depth_policies=config.depth_policies,
            coverage_policy=config.coverage_policy,
            audit_enabled=config.audit_enabled,
            redact_patterns=config.redact_patterns,
            max_parallel_modules=config.max_parallel_modules,
            ai=config.ai,
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
    _load_command_dependencies(str(args.command))
    loaded_adapters: tuple[LoadedAdapterPlugin, ...] = ()
    if args.command != "status":
        try:
            loaded_adapters = load_adapter_plugins(config.adapter_plugins)
        except (LookupError, TypeError) as error:
            _emit_error(args, str(args.command), "adapter_plugin_error", str(error))
            return 2
        append_audit_event(
            config,
            "cli.command",
            {
                "command": str(args.command),
                "adapter_plugins": [f"{plugin.kind}/{plugin.name}" for plugin in loaded_adapters],
            },
        )
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
    if args.command == "coverage":
        return _coverage(args, config, loaded_adapters)
    if args.command == "review":
        return _review(args, config)
    if args.command == "feedback":
        return _feedback(args, config)
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


def _load_command_dependencies(command: str) -> None:
    """Load only the implementation graph needed by a selected command."""

    global append_audit_event, load_adapter_plugins, LoadedAdapterPlugin
    from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
    from dv_platform.core.security import append_audit_event

    if command == "index-docs":
        global \
            chunk_documents, \
            discover_documentation_files, \
            load_documents, \
            read_configured_document_index, \
            write_document_index
        from dv_platform.analysis.docs import (
            chunk_documents,
            discover_documentation_files,
            load_documents,
            read_configured_document_index,
            write_document_index,
        )
    elif command == "analyze-rtl":
        global \
            build_verilator_dry_run_command, \
            discover_project, \
            write_project_manifest, \
            read_normalized_rtl_facts, \
            run_verilator_xml, \
            write_normalized_rtl_facts, \
            write_rtl_facts_summary, \
            write_verilator_failure_summary, \
            classify_verilator_version, \
            normalize_verilator_xml
        from dv_platform.analysis.discovery import (
            build_verilator_dry_run_command,
            discover_project,
            write_project_manifest,
        )
        from dv_platform.analysis.rtl import (
            classify_verilator_version,
            normalize_verilator_xml,
            read_normalized_rtl_facts,
            run_verilator_xml,
            write_normalized_rtl_facts,
            write_rtl_facts_summary,
            write_verilator_failure_summary,
        )
    elif command == "plan":
        global \
            augment_plans, \
            create_initial_plan, \
            read_normalized_rtl_facts, \
            read_stored_plans, \
            write_plan_outputs, \
            read_configured_document_index, \
            RegisterAnalysis, \
            extract_registers_from_documentation, \
            extract_registers_from_rtl, \
            load_register_map, \
            merge_register_sources, \
            read_requirements_baseline
        from dv_platform.analysis.ai_planning import augment_plans
        from dv_platform.analysis.docs import read_configured_document_index
        from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
        from dv_platform.analysis.planner import create_initial_plan
        from dv_platform.analysis.registers import (
            RegisterAnalysis,
            extract_registers_from_documentation,
            extract_registers_from_rtl,
            load_register_map,
            merge_register_sources,
        )
        from dv_platform.analysis.rtl import read_normalized_rtl_facts
        from dv_platform.enterprise.store import read_requirements_baseline
    elif command == "generate":
        global \
            GeneratorRegistry, \
            load_generator_plugins, \
            write_generated_artifacts, \
            read_stored_plans, \
            read_plan_records, \
            generate_design_decisions, \
            read_revisions, \
            CDCProofPolicy, \
            CocotbGenerator, \
            FormalGenerator, \
            SystemVerilogGenerator, \
            VerilogGenerator, \
            VhdlGenerator, \
            UvmGenerator
        from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans
        from dv_platform.analysis.review import generate_design_decisions
        from dv_platform.analysis.revisions import read_revisions
        from dv_platform.generators import (
            CocotbGenerator,
            FormalGenerator,
            GeneratorRegistry,
            SystemVerilogGenerator,
            UvmGenerator,
            VerilogGenerator,
            VhdlGenerator,
            load_generator_plugins,
            write_generated_artifacts,
        )
        from dv_platform.generators.formal import CDCProofPolicy
    elif command == "run":
        global \
            discover_generated_modules, \
            execute_formal_run, \
            execute_simulation_run, \
            prepare_formal_run, \
            prepare_simulation_run, \
            write_aggregate_run_summary
        from dv_platform.run import (
            discover_generated_modules,
            execute_formal_run,
            execute_simulation_run,
            prepare_formal_run,
            prepare_simulation_run,
            write_aggregate_run_summary,
        )
    elif command == "coverage":
        global CoverageImporter, import_coverage_reports
        from dv_platform.analysis.coverage import CoverageImporter, import_coverage_reports
    elif command == "review":
        global generate_design_decisions, generate_run_feedback_decisions, read_stored_plans, write_review_outputs
        from dv_platform.analysis.plan_store import read_stored_plans
        from dv_platform.analysis.review import (
            generate_design_decisions,
            generate_run_feedback_decisions,
            write_review_outputs,
        )
    elif command == "feedback":
        global normalize_feedback, create_feedback_revision, read_revisions, read_stored_plans
        from dv_platform.analysis.feedback import normalize_feedback
        from dv_platform.analysis.plan_store import read_stored_plans
        from dv_platform.analysis.revisions import create_feedback_revision, read_revisions
    elif command == "status":
        global collect_platform_status, evaluate_status_policy
        from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy


def _init_config_from_args(args: argparse.Namespace) -> CLIConfig:
    config = default_config(args.repo_root or Path.cwd())
    documentation_paths = args.documentation_path or config.documentation_paths
    verilator_executable = args.verilator_executable or config.verilator_executable
    slang_executable = args.slang_executable or config.slang_executable
    semantic_crosscheck = args.semantic_crosscheck or config.semantic_crosscheck

    return normalize_config(
        CLIConfig(
            repo_root=args.repo_root or config.repo_root,
            work_dir=args.work_dir or config.work_dir,
            output_dir=args.output_dir or config.output_dir,
            documentation_paths=tuple(documentation_paths),
            register_map_paths=config.register_map_paths,
            rtl_filelists=tuple(args.rtl_filelist or ()),
            include_paths=tuple(args.include_path or ()),
            defines=tuple(args.define or ()),
            parameter_overrides=tuple(args.parameter or ()),
            parameter_sweeps=tuple(
                tuple(item.strip() for item in sweep.split(",") if item.strip())
                for sweep in (args.parameter_sweep or ())
            ),
            top_modules=tuple(args.top_module or ()),
            verilator_executable=verilator_executable,
            slang_executable=slang_executable,
            semantic_crosscheck=semantic_crosscheck,
            retrieval_index_dir=(args.work_dir or config.work_dir) / "rag-index",
            allow_network=args.allow_network,
            strict=args.strict or args.ci,
            ci=args.ci,
            generator_plugins=config.generator_plugins,
            adapter_plugins=config.adapter_plugins,
            protocol_profiles=config.protocol_profiles,
            depth_policies=config.depth_policies,
            coverage_policy=config.coverage_policy,
            audit_enabled=config.audit_enabled,
            redact_patterns=config.redact_patterns,
            max_parallel_modules=config.max_parallel_modules,
            ai=config.ai,
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

    sweep_runs = _parameter_sweep_configs(config)
    verilator_command = build_verilator_dry_run_command(config, inventory)
    sweep_commands = [list(build_verilator_dry_run_command(run_config, inventory)) for run_config, _ in sweep_runs]
    slang_analyzer = None
    slang_version = None
    slang_commands: tuple[tuple[str, ...], ...] = ()
    if config.semantic_crosscheck != "off":
        from dv_platform.analysis.semantic_crosscheck import SlangAnalyzer
        from dv_platform.core.security import redact_text

        slang_analyzer = SlangAnalyzer(config.slang_executable, redact=lambda value: redact_text(config, value))
        slang_version = slang_analyzer.detect_version()
        slang_commands = tuple(
            slang_analyzer.build_command(
                tuple(item.path for item in inventory.hdl_files),
                run_config.work_dir / "slang" / "ast.json",
                top_modules=run_config.top_modules,
                include_paths=inventory.include_paths,
                defines=inventory.defines,
                parameter_overrides=run_config.parameter_overrides,
            )
            for run_config, _ in sweep_runs
        )
    manifest_path = write_project_manifest(
        config,
        inventory,
        verilator_command,
        diagnostics,
        slang_commands,
        slang_version,
    )

    dry_run_data = {
        "dry_run": args.dry_run,
        "repo_root": str(config.repo_root),
        "hdl_files": len(inventory.hdl_files),
        "documentation_files": len(inventory.documentation_files),
        "include_paths": len(inventory.include_paths),
        "defines": len(inventory.defines),
        "manifest": str(manifest_path),
        "verilator_command": list(verilator_command),
        "parameter_sweeps": [list(overrides) for _, overrides in sweep_runs if overrides is not None],
        "verilator_commands": sweep_commands,
        "semantic_crosscheck_mode": config.semantic_crosscheck,
        "slang_version": slang_version or "unknown",
        "slang_commands": [list(command) for command in slang_commands],
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
                f"semantic_crosscheck_mode={config.semantic_crosscheck}",
            ),
        )
        return 0

    input_fingerprint = _rtl_input_fingerprint(manifest_path, inventory)
    cache_path = config.work_dir / "rtl-facts" / "cache.json"
    if not config.parameter_sweeps and not args.force and _rtl_cache_matches(config, cache_path, input_fingerprint):
        modules = read_normalized_rtl_facts(config)
        facts_path = config.work_dir / "rtl-facts" / "modules.json"
        summary_path = config.work_dir / "rtl-facts" / "summary.json"
        payload = json.loads(facts_path.read_text(encoding="utf-8"))
        version = str(payload.get("verilator_version") or "unknown")
        crosscheck_path = config.work_dir / "semantic-crosscheck" / "result.json"
        crosscheck_payload = _read_crosscheck_payload(crosscheck_path)
        crosscheck_status = str(crosscheck_payload.get("status", "off")) if crosscheck_payload else "off"
        if _semantic_crosscheck_enforced(config) and crosscheck_status != "passed":
            _emit_error(
                args,
                "analyze-rtl",
                "semantic_crosscheck_failed",
                "Cached semantic cross-check does not satisfy the configured policy.",
                data={"semantic_crosscheck_status": crosscheck_status, "semantic_crosscheck": str(crosscheck_path)},
            )
            return 2
        _emit_success(
            args,
            "analyze-rtl",
            {
                **dry_run_data,
                "cache_hit": True,
                "verilator_version": version,
                "normalized_modules": len(modules),
                "rtl_facts": str(facts_path),
                "rtl_facts_summary": str(summary_path),
                "semantic_crosscheck_status": crosscheck_status,
                "semantic_crosscheck": str(crosscheck_path) if crosscheck_payload else None,
            },
            (
                "command=analyze-rtl",
                "cache_hit=true",
                f"normalized_modules={len(modules)}",
                f"rtl_facts={facts_path}",
                f"rtl_facts_summary={summary_path}",
                f"semantic_crosscheck_status={crosscheck_status}",
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

    run_results = []
    for run_config, overrides in sweep_runs:
        try:
            run_result = run_verilator_xml(run_config, inventory)
        except OSError as error:
            _emit_error(args, "analyze-rtl", "verilator_execution_failed", str(error))
            return 2
        run_results.append((run_result, overrides))
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

    run_result = run_results[0][0]

    compatibility = classify_verilator_version(run_result.version)
    if (config.strict or config.ci) and compatibility["status"] != "supported":
        _emit_error(
            args,
            "analyze-rtl",
            "unsupported_verilator_version",
            "Strict RTL analysis requires a Verilator major version covered by the XML compatibility fixtures.",
            data={"verilator_version": run_result.version, "verilator_compatibility": compatibility},
        )
        return 2

    normalized_runs = tuple(
        (
            normalize_verilator_xml(
                result.xml_files,
                config.protocol_profiles,
                identity_suffix=_sweep_identity(overrides) if overrides is not None else None,
            ),
            result,
            run_config,
            overrides,
        )
        for (result, overrides), (run_config, _configured_overrides) in zip(run_results, sweep_runs, strict=True)
    )
    modules = tuple(module for run_modules, _result, _config, _overrides in normalized_runs for module in run_modules)
    crosscheck_result = None
    crosscheck_path = config.work_dir / "semantic-crosscheck" / "result.json"
    slang_compatibility: dict[str, object] | None = None
    if slang_analyzer is not None:
        from dv_platform.analysis.semantic_crosscheck import (
            FrontendMetadata,
            NormalizedFactCrossChecker,
            aggregate_crosscheck_results,
            capabilities_for_modules,
            classify_slang_version,
            required_capabilities_for_modules,
            unavailable_crosscheck_result,
            write_crosscheck_result,
        )

        point_results = []
        for run_modules, verilator_result, run_config, overrides in normalized_runs:
            run_id = _sweep_identity(overrides) if overrides is not None else "default"
            append_audit_event(
                config,
                "semantic_crosscheck.start",
                {"run_id": run_id, "frontend": "slang", "mode": config.semantic_crosscheck},
            )
            slang_result = slang_analyzer.run(
                tuple(item.path for item in inventory.hdl_files),
                run_config.work_dir / "slang" / "ast.json",
                top_modules=run_config.top_modules,
                include_paths=inventory.include_paths,
                defines=inventory.defines,
                parameter_overrides=run_config.parameter_overrides,
            )
            append_audit_event(
                config,
                "semantic_crosscheck.finish",
                {
                    "run_id": run_id,
                    "frontend": "slang",
                    "return_code": slang_result.return_code,
                    "succeeded": slang_result.succeeded,
                },
            )
            primary_metadata = FrontendMetadata(
                "verilator",
                verilator_result.version,
                verilator_result.command,
                str(verilator_result.xml_files[0]) if verilator_result.xml_files else None,
            )
            reference_metadata = FrontendMetadata(
                "slang",
                slang_result.version,
                slang_result.command,
                str(slang_result.ast_path),
            )
            if slang_result.succeeded:
                point_result = NormalizedFactCrossChecker(
                    run_id=run_id,
                    primary=primary_metadata,
                    reference=reference_metadata,
                    primary_capabilities=capabilities_for_modules(run_modules),
                    reference_capabilities=slang_result.capabilities,
                    required_capabilities=required_capabilities_for_modules(run_modules),
                    unsupported_reasons=dict(slang_result.capability_reasons),
                ).compare(run_modules, slang_result.modules)
            else:
                point_result = unavailable_crosscheck_result(
                    run_id,
                    primary_metadata,
                    reference_metadata,
                    slang_result.error or "Slang execution failed",
                )
            write_crosscheck_result(run_config.work_dir / "slang" / "crosscheck.json", point_result)
            point_results.append(point_result)
        crosscheck_result = aggregate_crosscheck_results(tuple(point_results))
        write_crosscheck_result(crosscheck_path, crosscheck_result)
        slang_compatibility = cast(dict[str, object], classify_slang_version(slang_version))
    facts_path = write_normalized_rtl_facts(config, modules, run_result.version)
    summary_path = write_rtl_facts_summary(config, modules, run_result.version)
    atomic_write_text(
        cache_path,
        json.dumps(
            {
                "schema_version": 2,
                "input_fingerprint": input_fingerprint,
                "semantic_crosscheck_status": crosscheck_result.status if crosscheck_result is not None else "off",
                "slang_version": slang_version,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    data = {
        **dry_run_data,
        "verilator_return_code": run_result.return_code,
        "verilator_version": run_result.version or "unknown",
        "verilator_compatibility": compatibility,
        "verilator_version_log": str(run_result.version_log),
        "verilator_stdout_log": str(run_result.stdout_log),
        "verilator_stderr_log": str(run_result.stderr_log),
        "verilator_xml_files": sum(len(result.xml_files) for result, _ in run_results),
        "parameter_sweeps": [list(overrides) for _, overrides in run_results if overrides is not None],
        "normalized_modules": len(modules),
        "rtl_facts": str(facts_path),
        "rtl_facts_summary": str(summary_path),
        "semantic_crosscheck_status": crosscheck_result.status if crosscheck_result is not None else "off",
        "semantic_crosscheck_passed": crosscheck_result.passed if crosscheck_result is not None else None,
        "semantic_crosscheck_issues": len(crosscheck_result.issues) if crosscheck_result is not None else 0,
        "semantic_crosscheck": str(crosscheck_path) if crosscheck_result is not None else None,
        "slang_version": slang_version or "unknown",
        "slang_compatibility": slang_compatibility,
    }
    policy_failure = crosscheck_result is not None and (
        (_semantic_crosscheck_enforced(config) and not crosscheck_result.passed)
        or (
            (config.strict or config.ci)
            and slang_compatibility is not None
            and slang_compatibility.get("status") != "supported"
        )
    )
    if policy_failure:
        _emit_error(
            args,
            "analyze-rtl",
            "semantic_crosscheck_failed",
            "Slang semantic cross-check does not satisfy the configured policy.",
            data=data,
        )
        return 2
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
            f"verilator_xml_files={sum(len(result.xml_files) for result, _ in run_results)}",
            f"parameter_sweeps={len(config.parameter_sweeps)}",
            f"normalized_modules={len(modules)}",
            f"rtl_facts={facts_path}",
            f"rtl_facts_summary={summary_path}",
            f"semantic_crosscheck_status={data['semantic_crosscheck_status']}",
            f"semantic_crosscheck={data['semantic_crosscheck'] or ''}",
        ),
    )
    return 0


def _parameter_sweep_configs(config: CLIConfig) -> tuple[tuple[CLIConfig, tuple[str, ...] | None], ...]:
    """Return isolated analysis configs for the selected elaboration points."""

    if not config.parameter_sweeps:
        return ((config, None),)
    return tuple(
        (
            replace(
                config,
                work_dir=config.work_dir / "sweeps" / _sweep_identity(overrides),
                parameter_overrides=overrides,
                parameter_sweeps=(),
            ),
            overrides,
        )
        for overrides in config.parameter_sweeps
    )


def _sweep_identity(overrides: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\0".join(overrides).encode("utf-8")).hexdigest()[:12]
    return f"sweep_{digest}"


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
    if not _semantic_crosscheck_gate(args, config, "plan"):
        return 2
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
    register_analyses: dict[str, RegisterAnalysis] = {}
    try:
        for module in modules:
            documented = extract_registers_from_documentation(documentation_chunks, module.name)
            configured = tuple(
                (str(path), tuple(load_register_map(path, module.name))) for path in config.register_map_paths
            )
            register_analyses[module.name] = merge_register_sources(
                module, (("rtl", extract_registers_from_rtl(module)), ("documentation", documented), *configured)
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(args, "plan", "register_map_failed", str(error))
        return 2
    if (args.module or args.ai_refresh) and not args.ai:
        _emit_error(
            args,
            "plan",
            "ai_preflight_failed",
            "--module and --ai-refresh are valid only with plan --ai.",
        )
        return 2
    selected_ai_modules = tuple(dict.fromkeys(args.module or (module.name for module in modules))) if args.ai else ()
    if args.ai:
        ai_diagnostics = validate_ai_config(config.ai)
        unknown_modules = tuple(name for name in selected_ai_modules if name not in {module.name for module in modules})
        module_limit = min(20, config.ai.max_modules_per_run)
        if unknown_modules:
            _emit_error(
                args,
                "plan",
                "ai_preflight_failed",
                f"Unknown AI planning module selection: {', '.join(unknown_modules)}",
            )
            return 2
        if len(selected_ai_modules) > module_limit:
            _emit_error(
                args,
                "plan",
                "ai_preflight_failed",
                f"AI planning selected {len(selected_ai_modules)} modules; the configured limit is {module_limit}.",
            )
            return 2
        if ai_diagnostics:
            _emit_error(
                args,
                "plan",
                "ai_preflight_failed",
                "AI planning configuration is invalid.",
                diagnostics=ai_diagnostics,
            )
            return 2
    plans = tuple(
        create_initial_plan(
            module,
            targets=targets,
            documentation_chunks=documentation_chunks,
            retrieval_index_dir=config.retrieval_index_dir or config.work_dir / "rag-index",
            depth_policies=config.depth_policies,
            imported_requirements=read_requirements_baseline(config),
            register_models=register_analyses[module.name].registers,
            register_conflicts=register_analyses[module.name].conflicts,
            register_open_questions=register_analyses[module.name].open_questions,
        )
        for module in modules
    )
    ai_result = None
    if args.ai:
        try:
            ai_result = augment_plans(
                config,
                modules,
                plans,
                documentation_chunks,
                selected_ai_modules,
                refresh=args.ai_refresh,
            )
        except ValueError as error:
            _emit_error(args, "plan", "ai_preflight_failed", str(error))
            return 2
        plans = ai_result.plans
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
        "ai_requested": bool(args.ai),
        "ai_requested_modules": ai_result.requested_modules if ai_result is not None else 0,
        "ai_augmented_modules": ai_result.augmented_modules if ai_result is not None else 0,
        "ai_fallback_modules": ai_result.fallback_modules if ai_result is not None else 0,
        "ai_cache_hit_modules": ai_result.cache_hit_modules if ai_result is not None else 0,
        "ai_run_id": ai_result.run_id if ai_result is not None else None,
        "ai_run_records": [str(path) for path in ai_result.run_record_paths] if ai_result is not None else [],
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
            f"ai_requested={str(data['ai_requested']).lower()}",
            f"ai_requested_modules={data['ai_requested_modules']}",
            f"ai_augmented_modules={data['ai_augmented_modules']}",
            f"ai_fallback_modules={data['ai_fallback_modules']}",
            f"ai_cache_hit_modules={data['ai_cache_hit_modules']}",
            *(f"ai_run_record={path}" for path in (ai_result.run_record_paths if ai_result is not None else ())),
        ),
    )
    return 0


def _generate(args: argparse.Namespace, config: CLIConfig) -> int:
    if not _semantic_crosscheck_gate(args, config, "generate"):
        return 2
    target = VerificationTarget(args.target)
    if args.cdc_bmc_depth <= 0:
        _emit_error(args, "generate", "invalid_cdc_bmc_depth", "--cdc-bmc-depth must be greater than zero.")
        return 2
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

    if args.revision is not None:
        revisions = tuple(revision for plan in plans for revision in read_revisions(config.work_dir, plan.module))
        selected_revision = next((revision for revision in revisions if revision.revision_id == args.revision), None)
        if selected_revision is None:
            _emit_error(args, "generate", "unknown_revision", f"Plan revision is not readable: {args.revision}")
            return 2
        plans = tuple(plan for plan in plans if plan.module == selected_revision.module)
        records = tuple(record for record in records if record["module"] == selected_revision.module)

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
    registry.register(FormalGenerator(args.cdc_policy, args.cdc_bmc_depth))
    registry.register(SystemVerilogGenerator())
    registry.register(VerilogGenerator())
    registry.register(VhdlGenerator())
    registry.register(UvmGenerator())
    try:
        loaded_plugins = load_generator_plugins(registry, config.generator_plugins)
    except (LookupError, TypeError) as error:
        _emit_error(args, "generate", "plugin_load_failed", str(error))
        return 2
    try:
        artifacts = tuple(artifact for plan in selected_plans for artifact in registry.get(target).generate(plan))
    except ValueError as error:
        _emit_error(args, "generate", "generation_policy_blocked", str(error))
        return 2
    try:
        result = write_generated_artifacts(
            config,
            artifacts,
            replace_target=target,
            expected_modules=tuple(plan.module for plan in selected_plans),
        )
    except ValueError as error:
        _emit_error(args, "generate", "artifact_write_failed", str(error))
        return 2

    data = {
        "target": str(target),
        "plans": len(selected_plans),
        "generator_plugins": list(loaded_plugins),
        "cdc_policy": args.cdc_policy if target == VerificationTarget.FORMAL else None,
        "cdc_bmc_depth": args.cdc_bmc_depth if target == VerificationTarget.FORMAL else None,
        "artifacts": len(result.artifact_paths),
        "artifact_paths": [str(path) for path in result.artifact_paths],
        "provenance_manifests": len(result.provenance_paths),
        "provenance_paths": [str(path) for path in result.provenance_paths],
        "revision": args.revision,
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


def _feedback(args: argparse.Namespace, config: CLIConfig) -> int:
    plans_db = config.work_dir / "plans" / "plans.sqlite"
    if not plans_db.is_file():
        _emit_error(args, "feedback", "missing_plans", f"Plans are missing; run plan first: {plans_db}")
        return 2
    try:
        plans = read_stored_plans(plans_db)
        selected = tuple(plan for plan in plans if args.all or plan.module == args.module)
        if not selected:
            _emit_error(args, "feedback", "module_not_found", "No stored plan matches the requested module.")
            return 2
        records: list[dict[str, object]] = []
        for path in args.input or ():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                records.extend(item for item in payload if isinstance(item, dict))
            elif isinstance(payload, dict):
                checks = payload.get("checks", payload.get("results", ()))
                if isinstance(checks, list):
                    records.extend(item for item in checks if isinstance(item, dict))
        target = VerificationTarget(args.target)
        revisions = []
        for plan in selected:
            scoped = tuple(
                record for record in records if not record.get("module") or record.get("module") == plan.module
            )
            if not scoped:
                scoped = tuple({"check_id": check.check_id, "outcome": "unexecuted"} for check in plan.check_details)
            events = normalize_feedback(scoped, target=target, module=plan.module, source_run="cli-feedback")
            revisions.append(create_feedback_revision(config.work_dir, plan, events, dry_run=args.dry_run))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(args, "feedback", "feedback_failed", str(error))
        return 2
    _emit_success(
        args,
        "feedback",
        {
            "modules": len(revisions),
            "dry_run": args.dry_run,
            "revisions": [revision.revision_id for revision in revisions],
        },
        (
            "command=feedback",
            f"modules={len(revisions)}",
            f"dry_run={str(args.dry_run).lower()}",
            *(f"revision={revision.revision_id}" for revision in revisions),
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
    ai = status["ai"]
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
        f"ai_dependency_available={str(ai['dependency_available']).lower()}",
        f"ai_configured={str(ai['configured']).lower()}",
        f"ai_credential_present={str(ai['credential_present']).lower() if ai['credential_present'] is not None else 'not-required'}",
        f"ai_ready_for_live_request={str(ai['ready_for_live_request']).lower()}",
        f"generated_modules={summary['generated_modules']}",
        f"generated_artifacts={summary['generated_artifacts']}",
        f"quality_missing={summary['quality_missing']}",
        f"quality_failed={summary['quality_failed']}",
        f"artifacts_missing={summary['artifacts_missing']}",
        f"provenance_invalid={summary['provenance_invalid']}",
        f"integrity_missing={summary['integrity_missing']}",
        f"integrity_failed={summary['integrity_failed']}",
        f"tool_validation_missing={summary['tool_validation_missing']}",
        f"tool_validation_failed={summary['tool_validation_failed']}",
        f"traceability_missing={summary['traceability_missing']}",
        f"execution_manifest_invalid={summary['execution_manifest_invalid']}",
        f"expected_generated_missing={summary['expected_generated_missing']}",
        f"unexpected_generated={summary['unexpected_generated']}",
        f"unsafe_generated_roots={summary['unsafe_generated_roots']}",
        f"run_summaries={summary['run_summaries']}",
        f"failed_runs={summary['failed_runs']}",
        f"expected_runs_missing={summary['expected_runs_missing']}",
        f"coverage_status={summary['coverage_status']}",
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
    try:
        modules = discover_generated_modules(config, target)
    except ValueError as error:
        print(f"error={error}")
        return 2
    if not modules:
        print(f"error=No generated modules found for target {target}; run generate first.")
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
            with ThreadPoolExecutor(max_workers=min(config.max_parallel_modules, len(modules))) as executor:
                results = tuple(executor.map(execute_module, modules))
    except (OSError, ValueError) as error:
        print(f"error={error}")
        return 2
    return_codes = [return_code for return_code, _summary in results]
    module_summaries = [summary for _return_code, summary in results]

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
    try:
        modules = discover_generated_modules(config, target)
    except ValueError as error:
        print(f"error={error}")
        return 2
    if not modules:
        print(f"error=No generated modules found for target {target}; run generate first.")
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
            with ThreadPoolExecutor(max_workers=min(config.max_parallel_modules, len(modules))) as executor:
                results = tuple(executor.map(execute_module, modules))
    except (OSError, ValueError) as error:
        print(f"error={error}")
        return 2
    return_codes = [return_code for return_code, _summary in results]
    module_summaries = [summary for _return_code, summary in results]

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


def _rtl_input_fingerprint(manifest_path: Path, inventory: Any) -> str:
    manifest_bytes = manifest_path.read_bytes()
    digest = hashlib.sha256(manifest_bytes)
    inputs = {hdl.path for hdl in inventory.hdl_files}
    try:
        manifest = json.loads(manifest_bytes)
        inputs.update(
            path
            for item in manifest.get("verilator_command", ())
            if isinstance(item, str) and (path := Path(item).expanduser().resolve(strict=False)).is_file()
        )
    except (json.JSONDecodeError, AttributeError):
        pass
    for include_path in inventory.include_paths:
        if include_path.is_dir():
            inputs.update(
                path
                for path in include_path.rglob("*")
                if path.is_file() and path.suffix.lower() in {".v", ".vh", ".sv", ".svh"}
            )
    for path in sorted(inputs, key=lambda item: item.as_posix()):
        digest.update(str(path).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _rtl_cache_matches(config: CLIConfig, cache_path: Path, fingerprint: str) -> bool:
    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    if not cache_path.is_file() or not facts_path.is_file() or not summary_path.is_file():
        return False
    if config.semantic_crosscheck != "off" and not (config.work_dir / "semantic-crosscheck" / "result.json").is_file():
        return False
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("input_fingerprint") == fingerprint


def _semantic_crosscheck_enforced(config: CLIConfig) -> bool:
    return config.semantic_crosscheck == "required" or (
        config.semantic_crosscheck == "report" and (config.strict or config.ci)
    )


def _read_crosscheck_payload(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _semantic_crosscheck_gate(args: argparse.Namespace, config: CLIConfig, command: str) -> bool:
    if not _semantic_crosscheck_enforced(config):
        return True
    path = config.work_dir / "semantic-crosscheck" / "result.json"
    payload = _read_crosscheck_payload(path)
    if payload.get("schema_version") == 2 and payload.get("status") == "passed" and payload.get("passed") is True:
        return True
    _emit_error(
        args,
        command,
        "semantic_crosscheck_gate_failed",
        "Generation trust policy requires a passing Slang cross-check; run analyze-rtl successfully first.",
        data={
            "semantic_crosscheck_mode": config.semantic_crosscheck,
            "semantic_crosscheck_status": payload.get("status", "missing"),
            "semantic_crosscheck": str(path),
        },
    )
    return False


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
