"""Entitlement-first Enterprise command line."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, default_config, load_config
from dv_platform.product import activate_product_plan, require_capability, resolve_configured_product_plan


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    bootstrap = argparse.ArgumentParser(prog="dv-enterprise", add_help=False)
    bootstrap.add_argument("--entitlement", type=Path)
    bootstrap.add_argument("--trust-policy", type=Path)
    bootstrap.add_argument("--organization")
    bootstrap.add_argument("--config", type=Path)
    bootstrap.add_argument("--repo-root", type=Path, default=Path.cwd())
    if not argv or argv == ["--help"]:
        bootstrap.description = (
            "OpenROAD physical-optimize, rtl-optimize, signoff, run, profiles, status, and entitlement verify/status."
        )
        bootstrap.print_help()
        return 0
    args, remaining = bootstrap.parse_known_args(argv)
    try:
        path = args.config or args.repo_root / DEFAULT_CONFIG_FILENAME
        if args.config is not None and not path.is_file():
            raise FileNotFoundError(f"configuration does not exist: {path}")
        config = load_config(path) if path.is_file() else default_config(args.repo_root)
        config = replace(
            config,
            product=replace(
                config.product,
                entitlement_path=args.entitlement or config.product.entitlement_path,
                trust_policy_path=args.trust_policy or config.product.trust_policy_path,
                organization=args.organization or config.product.organization,
            ),
        )
        plan = resolve_configured_product_plan(config, fail_invalid=True)
        entitlement_args = [item for item in remaining if item != "--json"]
        if entitlement_args[:1] == ["entitlement"]:
            if len(entitlement_args) != 2 or entitlement_args[1] not in {"verify", "status"}:
                raise ValueError("entitlement requires verify or status")
            require_capability(plan, f"entitlement.{entitlement_args[1]}")
            print(json.dumps(plan.redacted(), sort_keys=True))
            return 0
        require_capability(plan, "cli.enterprise")
        activate_product_plan(plan)
        from dv_platform.enterprise.cli import main as enterprise_main

        forwarded = ["--repo-root", str(args.repo_root)]
        if args.config is not None:
            forwarded += ["--config", str(args.config)]
        return enterprise_main([*forwarded, *remaining])
    except (LookupError, OSError, TypeError, ValueError) as error:
        if "--json" in argv:
            print(json.dumps({"ok": False, "error": {"code": "enterprise_command_failed", "message": str(error)}}))
        else:
            print(f"error={error}", file=sys.stderr)
        return 1
