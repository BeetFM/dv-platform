# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from dv_platform.core.config import (
    default_config,
    normalize_config,
    write_config,
)
from dv_platform.core.models import CLIConfig

if TYPE_CHECKING:
    from dv_platform.analysis.status import collect_platform_status
    from dv_platform.core.operations import backup_project_state, governed_destruction, migrate_project_state
    from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
    from dv_platform.core.security import (
        append_audit_event,
        purge_retained_files,
        write_support_bundle,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "init":
        return _initialize(args)
    config = config_from_args(args)
    _load_command_dependencies(str(args.command))
    _synchronize_command_globals()
    loaded_adapters = _load_adapters(args, config)
    if loaded_adapters is None:
        return 2
    outcome = _dispatch_known_command(args, config, loaded_adapters)
    if outcome is not None:
        return outcome
    return _emit_configuration(args, config)


def _initialize(args: argparse.Namespace) -> int:
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


def _load_adapters(args: argparse.Namespace, config: CLIConfig) -> tuple[LoadedAdapterPlugin, ...] | None:
    if args.command in {"status", "context-optimize", "support-bundle", "purge", "backup", "migrate", "destroy"}:
        return ()
    try:
        loaded = load_adapter_plugins(
            tuple(plugin for plugin in config.adapter_plugins if plugin.kind != "generator"),
            approved_publishers=config.approved_plugin_publishers,
        )
    except (LookupError, TypeError) as error:
        _emit_error(args, str(args.command), "adapter_plugin_error", str(error))
        return None
    append_audit_event(
        config,
        "cli.command",
        {
            "command": str(args.command),
            "adapter_plugins": [f"{plugin.kind}/{plugin.name}" for plugin in loaded],
        },
    )
    return loaded


def _dispatch_known_command(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded_adapters: tuple[LoadedAdapterPlugin, ...],
) -> int | None:
    adapters_handlers = {
        "index-docs": _index_docs,
        "plan": _plan,
        "coverage": _coverage,
        "review": _review,
    }
    direct_handlers = {
        "analyze-rtl": _analyze_rtl,
        "generate": _generate,
        "run": _run,
        "feedback": _feedback,
        "status": _status,
        "context-optimize": _context_optimize,
    }
    if args.command in adapters_handlers:
        return adapters_handlers[args.command](args, config, loaded_adapters)
    if args.command in direct_handlers:
        return direct_handlers[args.command](args, config)
    state_handlers = {
        "support-bundle": _support_bundle,
        "purge": _purge,
        "backup": _backup,
        "migrate": _migrate,
        "destroy": _destroy,
    }
    handler = state_handlers.get(args.command)
    return handler(args, config) if handler is not None else None


def _support_bundle(args: argparse.Namespace, config: CLIConfig) -> int:
    status = collect_platform_status(config)
    path = write_support_bundle(config, status)
    _emit_success(args, "support-bundle", {"path": str(path)}, (f"support_bundle={path}",))
    return 0


def _context_optimize(args: argparse.Namespace, config: CLIConfig) -> int:
    action = args.context_optimize_command
    if action == "status":
        optimizer = optimizer_readiness(config)
        optimizer["code_graph"] = code_graph_status(config)
        lines = (
            "command=context-optimize status",
            f"enabled={str(optimizer['enabled']).lower()}",
            f"headroom_health={optimizer['headroom']['health']}",
            f"code_graph_available={str(optimizer['code_graph']['available']).lower()}",
            f"code_graph_present={str(optimizer['code_graph']['graph_present']).lower()}",
        )
        _emit_success(args, "context-optimize", optimizer, lines)
        return 0
    if action in {"build-graph", "update-graph"}:
        try:
            completed = run_code_graph_command(config, action, getattr(args, "base", None))
        except (OSError, ValueError, TimeoutError) as error:
            _emit_error(args, "context-optimize", "code_graph_failed", str(error))
            return 2
        data = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        if completed.returncode != 0:
            _emit_error(args, "context-optimize", "code_graph_failed", "code-review-graph command failed.", data=data)
            if not getattr(args, "json_output", False):
                for line in (
                    f"command=context-optimize {action}",
                    f"returncode={completed.returncode}",
                ):
                    print(line)
            return 2
        _emit_success(
            args,
            "context-optimize",
            data,
            (
                f"command=context-optimize {action}",
                f"returncode={completed.returncode}",
            ),
        )
        return 0
    _emit_error(args, "context-optimize", "unknown_action", str(action))
    return 2


def _purge(args: argparse.Namespace, config: CLIConfig) -> int:
    as_of = args.as_of or date.today()
    try:
        paths = purge_retained_files(config, as_of=as_of, apply=args.apply)
    except (OSError, ValueError) as error:
        _emit_error(args, "purge", "retention_purge_failed", str(error))
        return 2
    append_audit_event(
        config,
        "retention.purge",
        {
            "apply": args.apply,
            "as_of": as_of.isoformat(),
            "retention_days": config.retention_days,
            "files": len(paths),
        },
    )
    data = {
        "apply": args.apply,
        "as_of": as_of.isoformat(),
        "retention_days": config.retention_days,
        "files": [str(path) for path in paths],
    }
    _emit_success(args, "purge", data, (f"apply={str(args.apply).lower()}", f"expired_files={len(paths)}"))
    return 0


def _backup(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        items = backup_project_state(config, args.output, apply=args.apply)
    except (OSError, ValueError) as error:
        _emit_error(args, "backup", "backup_failed", str(error))
        return 2
    append_audit_event(config, "state.backup", {"apply": args.apply, "files": len(items)})
    _emit_success(
        args,
        "backup",
        {"apply": args.apply, "output": str(args.output), "files": len(items)},
        (f"apply={str(args.apply).lower()}", f"files={len(items)}"),
    )
    return 0


def _migrate(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        items = migrate_project_state(config, backup=args.backup, apply=args.apply)
    except (OSError, ValueError) as error:
        _emit_error(args, "migrate", "migration_failed", str(error))
        return 2
    append_audit_event(config, "state.migrate", {"apply": args.apply, "files": len(items)})
    _emit_success(
        args,
        "migrate",
        {"apply": args.apply, "backup": str(args.backup), "files": len(items)},
        (f"apply={str(args.apply).lower()}", f"files={len(items)}"),
    )
    return 0


def _destroy(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        items = governed_destruction(
            config,
            retention_class=args.retention_class,
            target=args.target,
            authorization=args.authorization,
            legal_holds=args.legal_holds,
            recovery_backup=args.recovery_backup,
            apply=args.apply,
        )
    except (OSError, ValueError) as error:
        _emit_error(args, "destroy", "governed_destruction_failed", str(error))
        return 2
    append_audit_event(
        config,
        "state.destroy",
        {
            "apply": args.apply,
            "retention_class": args.retention_class,
            "authorization": args.authorization,
            "files": len(items),
        },
    )
    _emit_success(
        args,
        "destroy",
        {
            "apply": args.apply,
            "retention_class": args.retention_class,
            "target": str(args.target),
            "authorization": args.authorization,
            "files": len(items),
        },
        (f"apply={str(args.apply).lower()}", f"files={len(items)}"),
    )
    return 0


def _emit_configuration(args: argparse.Namespace, config: CLIConfig) -> int:
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

    global \
        append_audit_event, \
        purge_retained_files, \
        validate_export_destination, \
        write_support_bundle, \
        load_adapter_plugins, \
        LoadedAdapterPlugin
    from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
    from dv_platform.core.security import (
        append_audit_event,
        purge_retained_files,
        validate_export_destination,
        write_support_bundle,
    )

    if command in {"backup", "migrate", "destroy"}:
        global backup_project_state, migrate_project_state, governed_destruction
        from dv_platform.core.operations import backup_project_state, governed_destruction, migrate_project_state

    if command == "index-docs":
        global \
            chunk_documents, \
            discover_documentation_files, \
            load_documents_with_adapters, \
            read_configured_document_index, \
            write_document_index_with_adapters, \
            LocalHashEmbeddingProvider, \
            LocalJsonVectorStore, \
            DocumentLoader, \
            EmbeddingProvider, \
            VectorStore
        from dv_platform.analysis.docs import (
            DocumentLoader,
            EmbeddingProvider,
            LocalHashEmbeddingProvider,
            LocalJsonVectorStore,
            VectorStore,
            chunk_documents,
            discover_documentation_files,
            load_documents_with_adapters,
            read_configured_document_index,
            write_document_index_with_adapters,
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
            normalize_verilator_xml, \
            normalize_vhdl_sources
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
        from dv_platform.analysis.vhdl import normalize_vhdl_sources
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
            read_requirements_baseline, \
            EmbeddingProvider, \
            VectorStore
        from dv_platform.analysis.ai_planning import augment_plans
        from dv_platform.analysis.docs import EmbeddingProvider, VectorStore, read_configured_document_index
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
            plan_hash, \
            project_manifest_hash, \
            record_revision_generation, \
            read_revision_plan, \
            read_revisions, \
            CDCProofPolicy, \
            CocotbGenerator, \
            FormalGenerator, \
            SystemVerilogGenerator, \
            VerilogGenerator, \
            VhdlGenerator, \
            UvmGenerator, \
            build_dependency_graph
        from dv_platform.analysis.dependencies import build_dependency_graph
        from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans
        from dv_platform.analysis.review import generate_design_decisions
        from dv_platform.analysis.revisions import (
            plan_hash,
            project_manifest_hash,
            read_revision_plan,
            read_revisions,
            record_revision_generation,
        )
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
        global \
            generate_design_decisions, \
            generate_run_feedback_decisions, \
            read_normalized_rtl_facts, \
            write_review_outputs
        from dv_platform.analysis.review import (
            generate_design_decisions,
            generate_run_feedback_decisions,
            write_review_outputs,
        )
        from dv_platform.analysis.rtl import read_normalized_rtl_facts
    elif command == "feedback":
        global \
            normalize_feedback, \
            create_feedback_revision, \
            read_revisions, \
            read_revision_plan, \
            read_stored_plans, \
            LiteLLMGateway, \
            propose_feedback_operations, \
            synthesize_scenario_selections
        from dv_platform.analysis.ai_feedback import propose_feedback_operations
        from dv_platform.analysis.ai_gateway import LiteLLMGateway
        from dv_platform.analysis.ai_scenarios import synthesize_scenario_selections
        from dv_platform.analysis.feedback import normalize_feedback
        from dv_platform.analysis.plan_store import read_stored_plans
        from dv_platform.analysis.revisions import create_feedback_revision, read_revision_plan, read_revisions
    elif command in {"status", "support-bundle"}:
        global collect_platform_status, evaluate_status_policy
        from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
    elif command == "context-optimize":
        global code_graph_status, optimizer_readiness, run_code_graph_command
        from dv_platform.ai.code_graph import code_graph_status, run_code_graph_command
        from dv_platform.ai.optimization import optimizer_readiness


def _synchronize_command_globals() -> None:
    """Share lazily loaded dependencies with the selected focused handler."""

    dependencies = {
        name: value
        for name, value in globals().items()
        if not name.startswith("__") and name not in {"_synchronize_command_globals"}
    }
    for module_name, module in tuple(sys.modules.items()):
        if module_name.startswith("dv_platform.cli_handlers.") and module is not None:
            module.__dict__.update(dependencies)


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
            parameter_matrix=config.parameter_matrix,
            parameter_constraints=config.parameter_constraints,
            max_parameter_points=config.max_parameter_points,
            cross_language_bindings=config.cross_language_bindings,
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
            production_protocol_bindings=config.production_protocol_bindings,
            depth_policies=config.depth_policies,
            coverage_policy=config.coverage_policy,
            audit_enabled=config.audit_enabled,
            redact_patterns=config.redact_patterns,
            max_parallel_modules=config.max_parallel_modules,
            max_process_memory_mb=config.max_process_memory_mb,
            max_total_process_memory_mb=config.max_total_process_memory_mb,
            max_output_bytes=config.max_output_bytes,
            license_tokens=config.license_tokens,
            sandbox_enabled=config.sandbox_enabled,
            sandbox_runtime=config.sandbox_runtime,
            sandbox_image=config.sandbox_image,
            sandbox_environment=config.sandbox_environment,
            ai=config.ai,
            context_optimization=config.context_optimization,
        )
    )
