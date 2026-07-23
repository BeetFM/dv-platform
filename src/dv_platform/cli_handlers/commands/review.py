# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, cast

from dv_platform.core.models import CLIConfig

if TYPE_CHECKING:
    from dv_platform.analysis.review import (
        generate_design_decisions,
        generate_run_feedback_decisions,
        write_review_outputs,
    )
    from dv_platform.analysis.rtl import (
        read_normalized_rtl_facts,
    )
    from dv_platform.core.plugins import LoadedAdapterPlugin
    from dv_platform.core.security import (
        validate_export_destination,
    )


def _review(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded_adapters: tuple[LoadedAdapterPlugin, ...] = (),
) -> int:
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
    exports: list[str] = []
    try:
        for plugin in loaded_adapters:
            if plugin.kind != "report_exporter":
                continue
            exporter = cast(ReportExporter, plugin.adapter)
            output = validate_export_destination(
                config,
                config.work_dir / "review" / "exports" / f"{plugin.name}.json",
            )
            exported = validate_export_destination(config, exporter.export((json_path, markdown_path), output))
            exports.append(str(exported))
    except (OSError, ValueError) as error:
        _emit_error(args, "review", "report_export_failed", str(error))
        return 2

    data = {
        "modules": len(modules),
        "findings": len(decisions),
        "review_db": str(sqlite_path),
        "review_json": str(json_path),
        "review_markdown": str(markdown_path),
        "exports": exports,
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
