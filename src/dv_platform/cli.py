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
from dv_platform.generators import CocotbGenerator, FormalGenerator, GeneratorRegistry, write_generated_artifacts
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
        print(f"created_config={config_path}")
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
        )
    )


def _analyze_rtl(args: argparse.Namespace, config: CLIConfig) -> int:
    diagnostics = validate_config(config)
    _print_diagnostics(diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in diagnostics):
        return 2

    try:
        inventory = discover_project(config)
    except (OSError, ValueError) as error:
        print(f"error={error}")
        return 2

    verilator_command = build_verilator_dry_run_command(config, inventory)
    manifest_path = write_project_manifest(config, inventory, verilator_command, diagnostics)

    print("command=analyze-rtl")
    print(f"dry_run={args.dry_run}")
    print(f"repo_root={config.repo_root}")
    print(f"hdl_files={len(inventory.hdl_files)}")
    print(f"documentation_files={len(inventory.documentation_files)}")
    print(f"include_paths={len(inventory.include_paths)}")
    print(f"defines={len(inventory.defines)}")
    print(f"manifest={manifest_path}")
    print("verilator_command=" + " ".join(verilator_command))
    if args.dry_run:
        return 0

    try:
        run_result = run_verilator_xml(config, inventory)
    except OSError as error:
        print(f"error={error}")
        return 2

    print(f"verilator_return_code={run_result.return_code}")
    print(f"verilator_version={run_result.version or 'unknown'}")
    print(f"verilator_version_log={run_result.version_log}")
    print(f"verilator_stdout_log={run_result.stdout_log}")
    print(f"verilator_stderr_log={run_result.stderr_log}")
    print(f"verilator_xml_files={len(run_result.xml_files)}")
    if run_result.return_code != 0:
        summary_path = write_verilator_failure_summary(config, run_result)
        print(f"verilator_failure_summary={summary_path}")
        return run_result.return_code

    modules = normalize_verilator_xml(run_result.xml_files)
    facts_path = write_normalized_rtl_facts(config, modules, run_result.version)
    print(f"normalized_modules={len(modules)}")
    print(f"rtl_facts={facts_path}")
    return 0


def _index_docs(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        documentation_files = discover_documentation_files(config.documentation_paths)
        documents = load_documents(documentation_files)
        chunks = chunk_documents(documents, max_chars=args.chunk_size)
        index_path = write_document_index(config, chunks)
    except (OSError, ValueError) as error:
        print(f"error={error}")
        return 2

    print("command=index-docs")
    print(f"repo_root={config.repo_root}")
    print(f"documentation_files={len(documentation_files)}")
    print(f"chunks={len(chunks)}")
    print(f"index={index_path}")
    return 0


def _plan(args: argparse.Namespace, config: CLIConfig) -> int:
    try:
        modules = read_normalized_rtl_facts(config)
    except OSError as error:
        print(f"error=RTL facts are missing; run analyze-rtl first: {error}")
        return 2
    except ValueError as error:
        print(f"error={error}")
        return 2

    try:
        documentation_chunks = read_configured_document_index(config)
    except OSError:
        documentation_chunks = ()

    targets = tuple(VerificationTarget(target) for target in (args.target or (VerificationTarget.COCOTB.value,)))
    plans = tuple(
        create_initial_plan(module, targets=targets, documentation_chunks=documentation_chunks)
        for module in modules
    )
    sqlite_path, module_paths, index_path, claim_report_paths = write_plan_outputs(
        config,
        plans,
        strict=config.strict or config.ci,
    )

    print("command=plan")
    print(f"modules={len(modules)}")
    print(f"documentation_chunks={len(documentation_chunks)}")
    print(f"plans={len(plans)}")
    print(f"plans_db={sqlite_path}")
    print(f"plan_index={index_path}")
    print(f"plan_markdown_files={len(module_paths)}")
    print(f"claim_report_files={len(claim_report_paths)}")
    return 0


def _generate(args: argparse.Namespace, config: CLIConfig) -> int:
    target = VerificationTarget(args.target)
    target_tool_diagnostics = validate_target_tools(config, (target,))
    _print_diagnostics(target_tool_diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in target_tool_diagnostics):
        return 2

    if target not in {VerificationTarget.COCOTB, VerificationTarget.FORMAL}:
        print(f"error=No generator registered for target: {target}")
        return 2

    plans_db = config.work_dir / "plans" / "plans.sqlite"
    if not plans_db.is_file():
        print(f"error=Plans are missing; run plan first: {plans_db}")
        return 2

    try:
        plans = read_stored_plans(plans_db)
        records = read_plan_records(plans_db)
    except OSError as error:
        print(f"error=Plans are missing; run plan first: {error}")
        return 2

    blocked = tuple(record for record in records if not bool(record["gate"]["allowed"]))
    if blocked:
        modules = ", ".join(str(record["module"]) for record in blocked)
        print(f"error=Generation blocked by claim gate for modules: {modules}")
        return 2

    selected_plans = tuple(plan for plan in plans if target in plan.targets)
    registry = GeneratorRegistry()
    registry.register(CocotbGenerator())
    registry.register(FormalGenerator())
    artifacts = tuple(artifact for plan in selected_plans for artifact in registry.get(target).generate(plan))
    try:
        result = write_generated_artifacts(config, artifacts)
    except ValueError as error:
        print(f"error={error}")
        return 2

    print("command=generate")
    print(f"target={target}")
    print(f"plans={len(selected_plans)}")
    print(f"artifacts={len(result.artifact_paths)}")
    print(f"provenance_manifests={len(result.provenance_paths)}")
    return 0


def _run(args: argparse.Namespace, config: CLIConfig) -> int:
    target = VerificationTarget(args.target)
    target_tool_diagnostics = validate_target_tools(config, (target,))
    _print_diagnostics(target_tool_diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in target_tool_diagnostics):
        return 2
    if target == VerificationTarget.FORMAL:
        tool = config.formal_tools[0] if config.formal_tools else None
        if tool is None:
            print(f"error=No formal tools configured for target {target}; add [[formal_tools]] to {DEFAULT_CONFIG_FILENAME}.")
            return 2
        if args.all:
            return _run_all_formal_modules(args, config, tool, target)
        run = prepare_formal_run(config, tool, args.module, timeout_seconds=args.timeout_seconds)
        try:
            return_code = execute_formal_run(config, run)
        except OSError as error:
            print(f"error={error}")
            return 2

        print("command=run")
        print(f"target={target}")
        print(f"module={args.module}")
        print(f"formal_tool={tool.name}")
        print(f"formal_tool_command={tool.command}")
        print(f"run_dir={run.run_dir}")
        print(f"summary={run.summary_path}")
        print(f"return_code={return_code}")
        return return_code

    simulator = next((item for item in config.simulators if item.target == target), None)
    if simulator is None:
        print(f"error=No simulator configured for target {target}; add [[simulators]] to {DEFAULT_CONFIG_FILENAME}.")
        return 2

    if args.all:
        return _run_all_generated_modules(args, config, simulator, target)

    run = prepare_simulation_run(config, simulator, args.module, timeout_seconds=args.timeout_seconds)
    try:
        return_code = execute_simulation_run(run)
    except OSError as error:
        print(f"error={error}")
        return 2

    print("command=run")
    print(f"target={target}")
    print(f"module={args.module}")
    print(f"simulator={simulator.name}")
    print(f"simulator_command={simulator.command}")
    print(f"run_dir={run.run_dir}")
    print(f"summary={run.summary_path}")
    print(f"return_code={return_code}")
    return return_code


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


if __name__ == "__main__":
    raise SystemExit(main())
