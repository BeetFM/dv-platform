"""Entitlement-first Enterprise command line."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dv_platform.product import activate_product_plan, require_capability, resolve_product_plan


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        import sys

        argv = sys.argv[1:]
    if not argv or argv == ["--help"]:
        parser = argparse.ArgumentParser(prog="dv-enterprise")
        parser.add_argument("--entitlement", type=Path, required=True)
        parser.add_argument("--trust-policy", type=Path, required=True)
        parser.add_argument("--organization")
        parser.add_argument("command", nargs="?", help="entitlement, status, import, run, or qualification command")
        parser.print_help()
        return 0
    bootstrap = argparse.ArgumentParser(prog="dv-enterprise", add_help=False)
    bootstrap.add_argument("--entitlement", type=Path, required=True)
    bootstrap.add_argument("--trust-policy", type=Path, required=True)
    bootstrap.add_argument("--organization")
    args, remaining = bootstrap.parse_known_args(argv)
    plan = resolve_product_plan(
        entitlement=args.entitlement,
        trust_policy=args.trust_policy,
        organization=args.organization,
    )
    if remaining[:1] == ["entitlement"]:
        if len(remaining) != 2 or remaining[1] not in {"verify", "status"}:
            bootstrap.error("entitlement requires verify or status")
        require_capability(plan, f"entitlement.{remaining[1]}")
        print(json.dumps(plan.redacted(), sort_keys=True))
        return 0
    require_capability(plan, "cli.enterprise")
    activate_product_plan(plan)
    from dv_platform.enterprise.cli import main as enterprise_main

    return enterprise_main(remaining)
