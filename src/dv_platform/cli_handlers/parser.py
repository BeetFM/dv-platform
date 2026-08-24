# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    default_config,
    load_config,
    normalize_config,
)
from dv_platform.core.models import CLIConfig, VerificationTarget

if TYPE_CHECKING:
    pass


class ReportExporter(Protocol):
    """Configured adapter for deterministic review report export."""

    def export(self, reports: tuple[Path, ...], output: Path) -> Path: ...


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
    feedback.add_argument(
        "--from-runs",
        action="store_true",
        help="Read persisted simulation and formal module summaries as feedback input.",
    )
    feedback.add_argument(
        "--ai",
        action="store_true",
        help="Request an evidence-bounded additive candidate revision; deterministic fallback is automatic.",
    )
    feedback.add_argument("--target", choices=[target.value for target in VerificationTarget], default="cocotb")
    feedback.add_argument("--dry-run", action="store_true", help="Recommend changes without writing revisions.")
    feedback.add_argument(
        "--fork-input-change",
        action="store_true",
        help="Start a new revision chain when canonical plan or RTL inputs changed.",
    )
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
    context_optimize = subcommands.add_parser(
        "context-optimize", help="Inspect or maintain optional AI context optimizers."
    )
    context_actions = context_optimize.add_subparsers(dest="context_optimize_command", required=True)
    context_actions.add_parser("status", help="Report Headroom and code-review-graph readiness.")
    context_actions.add_parser("build-graph", help="Build code-review-graph state for the repository.")
    update_graph = context_actions.add_parser("update-graph", help="Update code-review-graph state from a base ref.")
    update_graph.add_argument("--base", required=True, help="Git base ref for graph update.")
    subcommands.add_parser(
        "support-bundle",
        help="Write redacted configuration shape, status, versions, and content-free log digests.",
    )
    purge = subcommands.add_parser("purge", help="List or remove expired transient state under the work directory.")
    purge.add_argument("--apply", action="store_true", help="Delete listed files; the default is a dry run.")
    purge.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Explicit ISO date for reproducible retention evaluation. Defaults to today.",
    )
    backup = subcommands.add_parser("backup", help="Plan or create a verified backup of durable platform state.")
    backup.add_argument("--output", type=Path, required=True, help="New backup directory outside the work directory.")
    backup.add_argument("--apply", action="store_true", help="Create and verify the backup; default is a dry run.")
    migrate = subcommands.add_parser("migrate", help="Plan or apply adjacent state-schema migrations.")
    migrate.add_argument("--backup", type=Path, required=True, help="Previously verified project backup directory.")
    migrate.add_argument("--apply", action="store_true", help="Apply migrations; default is a dry run.")
    destroy = subcommands.add_parser(
        "destroy", help="Plan or apply governed destruction with backup and legal-hold checks."
    )
    destroy.add_argument(
        "--retention-class",
        choices=("run-evidence", "counterexamples", "generated-collateral", "backups"),
        required=True,
    )
    destroy.add_argument("--target", type=Path, required=True)
    destroy.add_argument(
        "--authorization", required=True, help="Change, ticket, or approval reference recorded in audit evidence."
    )
    destroy.add_argument("--legal-holds", type=Path, required=True, help="Versioned legal-hold registry JSON.")
    destroy.add_argument(
        "--recovery-backup", type=Path, required=True, help="Verified recovery backup required before destruction."
    )
    destroy.add_argument("--apply", action="store_true", help="Delete the governed target; default is a dry run.")
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
            parameter_matrix=config.parameter_matrix,
            parameter_constraints=config.parameter_constraints,
            max_parameter_points=config.max_parameter_points,
            cross_language_bindings=config.cross_language_bindings,
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
            production_protocol_bindings=config.production_protocol_bindings,
            depth_policies=config.depth_policies,
            coverage_policy=config.coverage_policy,
            audit_enabled=config.audit_enabled,
            redact_patterns=config.redact_patterns,
            approved_plugin_publishers=config.approved_plugin_publishers,
            export_roots=config.export_roots,
            secret_provider=config.secret_provider,
            retention_days=config.retention_days,
            max_parallel_modules=config.max_parallel_modules,
            max_process_memory_mb=config.max_process_memory_mb,
            max_total_process_memory_mb=config.max_total_process_memory_mb,
            max_output_bytes=config.max_output_bytes,
            license_tokens=config.license_tokens,
            sandbox_enabled=config.sandbox_enabled,
            sandbox_runtime=config.sandbox_runtime,
            sandbox_image=config.sandbox_image,
            sandbox_environment=config.sandbox_environment,
            product=config.product,
            ai=config.ai,
            context_optimization=config.context_optimization,
        )
    )


def resolved_config_path(args: argparse.Namespace, repo_root: Path | None = None) -> Path:
    if args.config is not None:
        return args.config.expanduser().resolve(strict=False)
    root = (repo_root or args.repo_root or Path.cwd()).expanduser().resolve(strict=False)
    return root / DEFAULT_CONFIG_FILENAME


for _legacy_class in (ReportExporter,):
    _legacy_class.__module__ = "dv_platform.cli"
del _legacy_class
