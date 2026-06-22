"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from dv_platform.analysis.discovery import (
    build_verilator_dry_run_command,
    discover_project,
    write_project_manifest,
)
from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    default_config,
    load_config,
    normalize_config,
    write_config,
)
from dv_platform.core.models import CLIConfig


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

    subcommands = parser.add_subparsers(dest="command")
    init = subcommands.add_parser("init", help="Create a local project configuration.")
    init.add_argument("--documentation-path", type=Path, action="append", default=None)
    init.add_argument("--rtl-filelist", type=Path, action="append", default=None)
    init.add_argument("--include-path", type=Path, action="append", default=None)
    init.add_argument("--define", action="append", default=None)
    init.add_argument("--top-module", action="append", default=None)
    init.add_argument("--verilator-executable", default=None)

    subcommands.add_parser("index-docs", help="Build or refresh the documentation RAG index.")
    analyze_rtl = subcommands.add_parser("analyze-rtl", help="Extract RTL facts through configured tools.")
    analyze_rtl.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover inputs and print tool commands without invoking Verilator.",
    )
    subcommands.add_parser("plan", help="Generate evidence-backed verification plans.")
    subcommands.add_parser("generate", help="Generate verification collateral.")
    subcommands.add_parser("run", help="Run configured simulation and formal tools.")
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
    if args.command == "analyze-rtl":
        return _analyze_rtl(args, config)

    print(f"command={args.command}")
    print(f"repo_root={config.repo_root}")
    print(f"work_dir={config.work_dir}")
    print(f"output_dir={config.output_dir}")
    print(f"retrieval_index_dir={config.retrieval_index_dir}")
    print(f"allow_network={config.allow_network}")
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
        )
    )


def _analyze_rtl(args: argparse.Namespace, config: CLIConfig) -> int:
    if not args.dry_run:
        print("analyze-rtl currently supports --dry-run only; Verilator execution starts in Stage 2.")
        return 2

    inventory = discover_project(config)
    verilator_command = build_verilator_dry_run_command(config, inventory)
    manifest_path = write_project_manifest(config, inventory, verilator_command)

    print("command=analyze-rtl")
    print("dry_run=True")
    print(f"repo_root={config.repo_root}")
    print(f"hdl_files={len(inventory.hdl_files)}")
    print(f"documentation_files={len(inventory.documentation_files)}")
    print(f"include_paths={len(inventory.include_paths)}")
    print(f"defines={len(inventory.defines)}")
    print(f"manifest={manifest_path}")
    print("verilator_command=" + " ".join(verilator_command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
