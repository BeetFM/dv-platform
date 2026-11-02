"""Local configuration, status, and token-optimization commands for physical design."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from dv_platform.ai.model_client import ai_readiness
from dv_platform.ai.optimization import optimizer_readiness
from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    default_config,
    load_config,
    normalize_config,
    validate_config,
    write_config,
)
from dv_platform.core.models import CLIConfig
from dv_platform.core.security import purge_retained_files, write_support_bundle
from dv_platform.physical import collect_physical_status
from dv_platform.product import product_status, require_operation, resolve_configured_product_plan
from dv_platform.release import collect_signoff_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dv-platform")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--ci", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="write a local physical-design configuration")
    status = commands.add_parser("status", help="report AI readiness and signed physical closure")
    status.add_argument("--policy", choices=("report", "ci"), default="report")
    context = commands.add_parser("context-optimize", help="inspect context optimizers or maintain the code graph")
    context.add_argument("action", choices=("status", "build-graph", "update-graph"), default="status", nargs="?")
    context.add_argument("--base")
    commands.add_parser("support-bundle", help="export redacted diagnostic metadata")
    purge = commands.add_parser("purge", help="remove expired transient diagnostics")
    purge.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    purge.add_argument("--apply", action="store_true")
    return parser


def platform_status(config: CLIConfig) -> dict[str, Any]:
    return {
        "product": product_status(config),
        "ai": ai_readiness(config),
        "context_optimization": optimizer_readiness(config),
        "physical": collect_physical_status(config),
        "signoff": collect_signoff_status(config),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.repo_root.resolve()
        path = args.config or root / DEFAULT_CONFIG_FILENAME
        if args.config is not None and args.command != "init" and not path.is_file():
            raise FileNotFoundError(f"configuration does not exist: {path}")
        config = load_config(path) if path.is_file() else default_config(root)
        config = normalize_config(
            replace(config, allow_network=config.allow_network or args.allow_network, ci=config.ci or args.ci)
        )
        require_operation(resolve_configured_product_plan(config), "cli.public." + args.command)
        diagnostics = validate_config(config)
        if any(item.severity == "error" for item in diagnostics):
            raise ValueError("; ".join(item.message for item in diagnostics if item.severity == "error"))
        data, ok = _dispatch(args, config, path)
        payload = {"command": args.command, "ok": ok, "data": data}
    except (LookupError, OSError, TypeError, ValueError) as error:
        payload = {"command": args.command, "ok": False, "error": str(error)}
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload["ok"]:
        for key, value in payload.get("data", {}).items():
            print(f"{key}={value}")
    else:
        print(f"error={payload.get('error', 'physical requirements remain open')}", file=sys.stderr)
    return 0 if payload["ok"] else 1


def _dispatch(args: argparse.Namespace, config: CLIConfig, path: Path) -> tuple[dict[str, Any], bool]:
    if args.command == "init":
        if path.exists():
            raise ValueError(f"configuration already exists: {path}")
        write_config(config, path)
        return {"config": str(path)}, True
    if args.command == "status":
        data = platform_status(config)
        passed = (
            data["signoff"]["signoff_approved"]
            if config.product.require_production_signoff
            else data["physical"]["overall"] in {"passed", "not_required"}
        )
        return data, args.policy == "report" or passed
    if args.command == "context-optimize":
        if args.action == "status":
            return optimizer_readiness(config), True
        from dv_platform.ai.code_graph import run_code_graph_command

        result = run_code_graph_command(config, args.action, args.base)
        return {"stdout": result.stdout, "stderr": result.stderr}, result.returncode == 0
    if args.command == "support-bundle":
        return {"bundle": str(write_support_bundle(config, platform_status(config)))}, True
    return {
        "paths": [str(path) for path in purge_retained_files(config, as_of=args.as_of, apply=args.apply)],
        "applied": args.apply,
    }, True
