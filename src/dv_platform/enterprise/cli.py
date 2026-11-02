"""Entitled OpenROAD execution commands."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

from dv_platform.cli import platform_status
from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    default_config,
    load_config,
    normalize_config,
    validate_config,
)
from dv_platform.core.models import AdapterPluginConfig, CLIConfig
from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
from dv_platform.enterprise.adapters import EnterpriseCommandAdapter, EnterpriseInvocation
from dv_platform.enterprise.profiles import ENTERPRISE_TOOL_PROFILES
from dv_platform.entitlement_leases import acquire_capability_lease
from dv_platform.product import active_product_plan, require_capability, resolve_configured_product_plan

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class _PrivateEntryPoint:
    group = "dv_platform.analyzer_runner"
    name = "openroad"
    distribution_name = "dv-platform"

    def load(self) -> object:
        return importlib.import_module("dv_platform.enterprise.adapters").OpenROADRunner


_PRIVATE_ENTRY_POINTS = (_PrivateEntryPoint(),)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dv-enterprise")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--allow-network", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    physical = commands.add_parser("physical-optimize", help="measure and iteratively repair physical timing")
    physical.add_argument("--project", type=Path, required=True)
    physical.add_argument("--ai", action="store_true")
    physical.add_argument("--max-iterations", type=int, choices=range(1, 4), default=3)
    rtl = commands.add_parser("rtl-optimize", help="prove and physically measure document-grounded RTL changes")
    rtl.add_argument("--project", type=Path, required=True)
    rtl.add_argument("--max-iterations", type=int, choices=range(1, 4), default=3)
    _add_signoff_parser(commands)
    run = commands.add_parser("run", help="execute a configured OpenROAD command")
    run.add_argument("--adapter", choices=("openroad",), default="openroad")
    run.add_argument("--family", choices=("analyzer",), default="analyzer")
    run.add_argument("--run-id", required=True)
    run.add_argument("--timeout-seconds", type=float, default=3600.0)
    run.add_argument("--strict", action="store_true")
    run.add_argument("tool_command", nargs=argparse.REMAINDER)
    status = commands.add_parser("status")
    status.add_argument("--policy", choices=("report", "ci"), default="report")
    commands.add_parser("profiles")
    return parser


def _add_signoff_parser(commands: Any) -> None:
    signoff = commands.add_parser("signoff", help="characterize, verify, and independently approve SKY130 releases")
    signoff.add_argument("action", choices=("characterize", "check", "import-approval", "status"))
    for name in ("project", "run", "release", "approval", "output"):
        signoff.add_argument("--" + name, type=Path)
    signoff.add_argument("--signoff-trust-policy", dest="trust_policy", type=Path)
    signoff.add_argument("--policy", choices=("report", "ci"), default="report")
    signoff.add_argument("--equivalence-memory-mb", type=int, default=4096)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = _config(args.repo_root.resolve(), args.config)
        if args.allow_network:
            config = replace(config, allow_network=True)
        diagnostics = validate_config(config)
        if diagnostics:
            raise ValueError("; ".join(item.message for item in diagnostics if item.severity == "error"))
        plan = resolve_configured_product_plan(config, fail_invalid=True)
        if config.product.entitlement_path is None:
            plan = active_product_plan() or plan
        require_capability(plan, "cli.enterprise")
        if args.command == "rtl-optimize":
            from dv_platform.enterprise.rtl_optimization import run_rtl_optimization

            data = run_rtl_optimization(config, args.project, max_iterations=args.max_iterations)
            return _emit(args, data["status"] == "improved", data)
        if args.command == "signoff":
            from dv_platform.enterprise.signoff import dispatch_signoff

            data, passed = dispatch_signoff(args, config)
            return _emit(args, passed, data)
        if args.command == "physical-optimize":
            from dv_platform.enterprise.physical_design import run_physical_optimization

            data = run_physical_optimization(config, args.project, use_ai=args.ai, max_iterations=args.max_iterations)
            return _emit(args, data["status"] == "timing_closed", data)
        if args.command == "run":
            configured = config.adapter_plugins or (
                AdapterPluginConfig(kind="analyzer_runner", name="openroad", api_version=1),
            )
            loaded = load_adapter_plugins(
                configured,
                entry_points=_PRIVATE_ENTRY_POINTS,
                product_plan=plan,
                approved_publishers=config.approved_plugin_publishers,
            )
            return _run(args, config, loaded)
        if args.command == "status":
            data = platform_status(config)
            data["product"] = plan.redacted()
            passed = (
                data["signoff"]["signoff_approved"]
                if config.product.require_production_signoff
                else data["physical"]["overall"] in {"passed", "not_required"}
            )
            return _emit(args, args.policy == "report" or passed, data)
        return _emit(args, True, {"profiles": [asdict(profile) for profile in ENTERPRISE_TOOL_PROFILES]})
    except (LookupError, OSError, TypeError, ValueError) as error:
        return _emit(args, False, {}, str(error))


def _run(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded: tuple[LoadedAdapterPlugin, ...],
) -> int:
    if not _RUN_ID.fullmatch(args.run_id):
        raise ValueError("run-id must be 1..128 safe filename characters")
    command = tuple(args.tool_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("enterprise run requires a command after --")
    kind = f"{args.family}_runner"
    adapter = cast(EnterpriseCommandAdapter, _adapter(loaded, kind, args.adapter))
    root = config.work_dir / "enterprise-runs" / args.run_id
    result_path = root / "result.json"
    invocation = EnterpriseInvocation(
        adapter=args.adapter,
        family=args.family,
        command=command,
        cwd=root,
        result_path=result_path,
        summary_path=root / "summary.json",
        stdout_path=root / "stdout.log",
        stderr_path=root / "stderr.log",
        timeout_seconds=args.timeout_seconds,
        environment_names=("DV_PLATFORM_RESULT_PATH",),
        environment=(("DV_PLATFORM_RESULT_PATH", str(result_path)),),
        redact_patterns=config.redact_patterns,
    )
    plan = active_product_plan() or resolve_configured_product_plan(config, fail_invalid=True)
    with acquire_capability_lease(plan, config.work_dir, "cli.enterprise.run"):
        result = adapter.execute(invocation, strict=args.strict or config.strict or config.ci)
    return _emit(
        args,
        result.passed,
        {
            "status": result.status,
            "summary": str(result.summary_path),
            "return_code": result.return_code,
            "traceability_complete": result.traceability_complete,
            "checks": len(result.checks),
        },
    )


def _config(repo_root: Path, config_path: Path | None) -> CLIConfig:
    path = config_path or repo_root / DEFAULT_CONFIG_FILENAME
    if config_path is not None and not path.is_file():
        raise FileNotFoundError(f"configuration does not exist: {path}")
    if path.is_file():
        return normalize_config(load_config(path), repo_root)
    return normalize_config(default_config(repo_root), repo_root)


def _adapter(loaded: tuple[LoadedAdapterPlugin, ...], kind: str, name: str) -> object:
    matches = [item.adapter for item in loaded if item.kind == kind and item.name == name]
    if len(matches) != 1:
        raise LookupError(f"configured adapter not found or ambiguous: {kind}/{name}")
    return matches[0]


def _emit(
    args: argparse.Namespace,
    ok: bool,
    data: dict[str, Any],
    error: str | None = None,
) -> int:
    payload = {"command": args.command, "ok": ok, "data": data}
    if error:
        payload["error"] = {"code": "enterprise_command_failed", "message": error}
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif ok:
        for key, value in data.items():
            print(f"{key}={value}")
    else:
        print(f"error={error or 'enterprise policy failed'}", file=sys.stderr)
    return 0 if ok else 1
