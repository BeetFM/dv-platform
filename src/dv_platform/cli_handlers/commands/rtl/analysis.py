# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from dv_platform.cli_handlers.commands.rtl.languages import _analyze_mixed_rtl, _analyze_vhdl_rtl
from dv_platform.core.config import (
    validate_config,
)
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig

if TYPE_CHECKING:
    from dv_platform.analysis.discovery import build_verilator_dry_run_command, discover_project, write_project_manifest
    from dv_platform.analysis.rtl import (
        classify_verilator_version,
        normalize_verilator_xml,
        read_normalized_rtl_facts,
        run_verilator_xml,
        write_normalized_rtl_facts,
        write_rtl_facts_summary,
        write_verilator_failure_summary,
    )
    from dv_platform.core.security import (
        append_audit_event,
    )


def _analyze_rtl(args: argparse.Namespace, config: CLIConfig) -> int:
    setup = _rtl_analysis_setup(args, config)
    if setup is None:
        return 2
    (
        diagnostics,
        inventory,
        vhdl_files,
        verilator_files,
        verilator_inventory,
        analysis_mode,
        sweep_runs,
        verilator_command,
        sweep_commands,
    ) = setup
    slang_analyzer, slang_version, slang_commands = _slang_analysis_setup(
        config, inventory, vhdl_files, verilator_files, verilator_inventory, sweep_runs
    )
    manifest_path = write_project_manifest(
        config, inventory, verilator_command, diagnostics, slang_commands, slang_version
    )
    dry_run_data = _rtl_dry_run_data(
        args,
        config,
        diagnostics,
        inventory,
        analysis_mode,
        sweep_runs,
        verilator_command,
        sweep_commands,
        slang_version,
        slang_commands,
        manifest_path,
    )
    if args.dry_run:
        _emit_rtl_dry_run(args, config, inventory, manifest_path, verilator_command, dry_run_data)
        return 0
    return _dispatch_rtl_analysis(
        args,
        config,
        inventory,
        vhdl_files,
        verilator_files,
        verilator_inventory,
        sweep_runs,
        verilator_command,
        slang_analyzer,
        slang_version,
        manifest_path,
        dry_run_data,
    )


def _rtl_analysis_setup(args: argparse.Namespace, config: CLIConfig) -> tuple[Any, ...] | None:
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
        return None

    try:
        inventory = discover_project(config)
    except (OSError, ValueError) as error:
        _emit_error(args, "analyze-rtl", "discovery_failed", str(error))
        return None

    vhdl_files = tuple(item for item in inventory.hdl_files if item.language == "vhdl")
    verilator_files = tuple(item for item in inventory.hdl_files if item.language != "vhdl")
    verilator_inventory = replace(inventory, hdl_files=verilator_files)
    analysis_mode = (
        "vhdl"
        if vhdl_files and not verilator_files
        else "verilator"
        if verilator_files and not vhdl_files
        else "mixed"
        if vhdl_files and verilator_files
        else "empty"
    )
    sweep_runs = _parameter_sweep_configs(config)
    verilator_command = build_verilator_dry_run_command(config, verilator_inventory) if verilator_files else ()
    sweep_commands = [
        list(build_verilator_dry_run_command(run_config, verilator_inventory))
        for run_config, _ in sweep_runs
        if verilator_files
    ]
    return (
        diagnostics,
        inventory,
        vhdl_files,
        verilator_files,
        verilator_inventory,
        analysis_mode,
        sweep_runs,
        verilator_command,
        sweep_commands,
    )


def _slang_analysis_setup(
    config: CLIConfig,
    inventory: Any,
    vhdl_files: tuple[Any, ...],
    verilator_files: tuple[Any, ...],
    verilator_inventory: Any,
    sweep_runs: tuple[Any, ...],
) -> tuple[Any, str | None, tuple[tuple[str, ...], ...]]:
    slang_analyzer = None
    slang_version = None
    slang_commands: tuple[tuple[str, ...], ...] = ()
    if config.semantic_crosscheck != "off" and verilator_files and not vhdl_files:
        from dv_platform.analysis.semantic_crosscheck import SlangAnalyzer
        from dv_platform.core.security import redact_text

        slang_analyzer = SlangAnalyzer(config.slang_executable, redact=lambda value: redact_text(config, value))
        slang_version = slang_analyzer.detect_version()
        slang_commands = tuple(
            slang_analyzer.build_command(
                tuple(item.path for item in verilator_inventory.hdl_files),
                run_config.work_dir / "slang" / "ast.json",
                top_modules=run_config.top_modules,
                include_paths=inventory.include_paths,
                defines=inventory.defines,
                parameter_overrides=run_config.parameter_overrides,
            )
            for run_config, _ in sweep_runs
        )
    return slang_analyzer, slang_version, slang_commands


def _rtl_dry_run_data(
    args: argparse.Namespace,
    config: CLIConfig,
    diagnostics: Any,
    inventory: Any,
    analysis_mode: str,
    sweep_runs: tuple[Any, ...],
    verilator_command: tuple[str, ...],
    sweep_commands: list[list[str]],
    slang_version: str | None,
    slang_commands: tuple[tuple[str, ...], ...],
    manifest_path: Path,
) -> dict[str, Any]:
    return {
        "dry_run": args.dry_run,
        "analysis_mode": analysis_mode,
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


def _emit_rtl_dry_run(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    manifest_path: Path,
    verilator_command: tuple[str, ...],
    dry_run_data: dict[str, Any],
) -> None:
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


def _dispatch_rtl_analysis(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    vhdl_files: tuple[Any, ...],
    verilator_files: tuple[Any, ...],
    verilator_inventory: Any,
    sweep_runs: tuple[Any, ...],
    verilator_command: tuple[str, ...],
    slang_analyzer: Any,
    slang_version: str | None,
    manifest_path: Path,
    dry_run_data: dict[str, Any],
) -> int:
    if vhdl_files and verilator_files:
        return _analyze_mixed_rtl(
            args,
            config,
            inventory,
            verilator_inventory,
            vhdl_files,
            sweep_runs,
            dry_run_data,
            cache_path=config.work_dir / "rtl-facts" / "cache.json",
            input_fingerprint=_rtl_input_fingerprint(manifest_path, inventory),
        )

    input_fingerprint = _rtl_input_fingerprint(manifest_path, inventory)
    cache_path = config.work_dir / "rtl-facts" / "cache.json"
    if not config.parameter_sweeps and not args.force and _rtl_cache_matches(config, cache_path, input_fingerprint):
        return _emit_cached_analysis(args, config, dry_run_data)
    if vhdl_files:
        return _analyze_vhdl_rtl(
            args,
            config,
            inventory,
            vhdl_files,
            sweep_runs,
            dry_run_data,
            cache_path,
            input_fingerprint,
        )
    return _analyze_verilator_rtl(
        args,
        config,
        inventory,
        sweep_runs,
        dry_run_data,
        manifest_path,
        verilator_command,
        slang_analyzer,
        slang_version,
        input_fingerprint,
        cache_path,
    )


def _analyze_verilator_rtl(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    sweep_runs: tuple[Any, ...],
    dry_run_data: dict[str, Any],
    manifest_path: Path,
    verilator_command: tuple[str, ...],
    slang_analyzer: Any,
    slang_version: str | None,
    input_fingerprint: str,
    cache_path: Path,
) -> int:
    _print_verilator_context(args, config, inventory, manifest_path, verilator_command)
    run_results, failure = _run_verilator_sweeps(args, config, inventory, sweep_runs, dry_run_data)
    if failure is not None:
        return failure
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
    normalized_runs = _normalize_verilator_runs(config, run_results, sweep_runs)
    modules = tuple(module for run_modules, _result, _config, _overrides in normalized_runs for module in run_modules)
    crosscheck, slang_compatibility, crosscheck_path = _crosscheck_verilator_runs(
        config, inventory, normalized_runs, slang_analyzer, slang_version
    )
    return _finish_verilator_analysis(
        args,
        config,
        modules,
        run_results,
        run_result,
        compatibility,
        crosscheck,
        slang_compatibility,
        crosscheck_path,
        slang_version,
        dry_run_data,
        cache_path,
        input_fingerprint,
    )


def _run_verilator_sweeps(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    sweep_runs: tuple[Any, ...],
    dry_run_data: dict[str, Any],
) -> tuple[list[tuple[Any, Any]], int | None]:
    results = []
    for run_config, overrides in sweep_runs:
        try:
            result = run_verilator_xml(run_config, inventory)
        except OSError as error:
            _emit_error(args, "analyze-rtl", "verilator_execution_failed", str(error))
            return [], 2
        results.append((result, overrides))
        if result.return_code != 0:
            _emit_verilator_failure(args, config, result, dry_run_data)
            return results, result.return_code
    return results, None


def _emit_verilator_failure(
    args: argparse.Namespace, config: CLIConfig, result: Any, dry_run_data: dict[str, Any]
) -> None:
    summary_path = write_verilator_failure_summary(config, result)
    data = {
        **dry_run_data,
        "verilator_return_code": result.return_code,
        "verilator_version": result.version or "unknown",
        "verilator_version_log": str(result.version_log),
        "verilator_stdout_log": str(result.stdout_log),
        "verilator_stderr_log": str(result.stderr_log),
        "verilator_xml_files": len(result.xml_files),
        "verilator_failure_summary": str(summary_path),
    }
    if not getattr(args, "json_output", False):
        for key in (
            "verilator_return_code",
            "verilator_version",
            "verilator_version_log",
            "verilator_stdout_log",
            "verilator_stderr_log",
            "verilator_xml_files",
            "verilator_failure_summary",
        ):
            print(f"{key}={data[key]}")
    _emit_error(
        args,
        "analyze-rtl",
        "verilator_failed",
        f"Verilator exited with return code {result.return_code}.",
        data=data,
    )


def _normalize_verilator_runs(
    config: CLIConfig, run_results: list[tuple[Any, Any]], sweep_runs: tuple[Any, ...]
) -> tuple[Any, ...]:
    return tuple(
        (
            normalize_verilator_xml(
                result.xml_files,
                config.protocol_profiles,
                config.production_protocol_bindings,
                identity_suffix=_sweep_identity(overrides) if overrides is not None else None,
            ),
            result,
            run_config,
            overrides,
        )
        for (result, overrides), (run_config, _configured_overrides) in zip(run_results, sweep_runs, strict=True)
    )


def _crosscheck_verilator_runs(
    config: CLIConfig, inventory: Any, normalized_runs: tuple[Any, ...], analyzer: Any, slang_version: str | None
) -> tuple[Any, dict[str, object] | None, Path]:
    crosscheck_path = config.work_dir / "semantic-crosscheck" / "result.json"
    if analyzer is None:
        return None, None, crosscheck_path
    from dv_platform.analysis.semantic_crosscheck import (
        aggregate_crosscheck_results,
        classify_slang_version,
        write_crosscheck_result,
    )

    points = tuple(_crosscheck_verilator_point(config, inventory, analyzer, *item) for item in normalized_runs)
    result = aggregate_crosscheck_results(points)
    write_crosscheck_result(crosscheck_path, result)
    return result, cast(dict[str, object], classify_slang_version(slang_version)), crosscheck_path


def _crosscheck_verilator_point(
    config: CLIConfig,
    inventory: Any,
    analyzer: Any,
    modules: tuple[Any, ...],
    verilator_result: Any,
    run_config: CLIConfig,
    overrides: tuple[str, ...] | None,
) -> Any:
    from dv_platform.analysis.semantic_crosscheck import (
        FrontendMetadata,
        NormalizedFactCrossChecker,
        capabilities_for_modules,
        required_capabilities_for_modules,
        unavailable_crosscheck_result,
        write_crosscheck_result,
    )

    run_id = _sweep_identity(overrides) if overrides is not None else "default"
    append_audit_event(
        config, "semantic_crosscheck.start", {"run_id": run_id, "frontend": "slang", "mode": config.semantic_crosscheck}
    )
    result = analyzer.run(
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
        {"run_id": run_id, "frontend": "slang", "return_code": result.return_code, "succeeded": result.succeeded},
    )
    primary = FrontendMetadata(
        "verilator",
        verilator_result.version,
        verilator_result.command,
        str(verilator_result.xml_files[0]) if verilator_result.xml_files else None,
    )
    reference = FrontendMetadata("slang", result.version, result.command, str(result.ast_path))
    if result.succeeded:
        point = NormalizedFactCrossChecker(
            run_id=run_id,
            primary=primary,
            reference=reference,
            primary_capabilities=capabilities_for_modules(modules),
            reference_capabilities=result.capabilities,
            required_capabilities=required_capabilities_for_modules(modules),
            unsupported_reasons=dict(result.capability_reasons),
        ).compare(modules, result.modules)
    else:
        point = unavailable_crosscheck_result(run_id, primary, reference, result.error or "Slang execution failed")
    write_crosscheck_result(run_config.work_dir / "slang" / "crosscheck.json", point)
    return point


def _finish_verilator_analysis(
    args: argparse.Namespace,
    config: CLIConfig,
    modules: tuple[Any, ...],
    run_results: list[tuple[Any, Any]],
    run_result: Any,
    compatibility: dict[str, object],
    crosscheck: Any,
    slang_compatibility: dict[str, object] | None,
    crosscheck_path: Path,
    slang_version: str | None,
    dry_run_data: dict[str, Any],
    cache_path: Path,
    input_fingerprint: str,
) -> int:
    facts_path = write_normalized_rtl_facts(config, modules, run_result.version)
    summary_path = write_rtl_facts_summary(config, modules, run_result.version)
    status = crosscheck.status if crosscheck is not None else "off"
    atomic_write_text(
        cache_path,
        json.dumps(
            {
                "schema_version": 2,
                "input_fingerprint": input_fingerprint,
                "semantic_crosscheck_status": status,
                "slang_version": slang_version,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    data = _verilator_result_data(
        dry_run_data,
        modules,
        run_results,
        run_result,
        compatibility,
        crosscheck,
        slang_compatibility,
        crosscheck_path,
        slang_version,
        facts_path,
        summary_path,
    )
    policy_failure = crosscheck is not None and (
        (_semantic_crosscheck_enforced(config) and not crosscheck.passed)
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
    _emit_success(args, "analyze-rtl", data, _verilator_result_lines(config, data, run_result, run_results))
    return 0


def _verilator_result_data(
    dry_run_data: dict[str, Any],
    modules: tuple[Any, ...],
    run_results: list[tuple[Any, Any]],
    result: Any,
    compatibility: dict[str, object],
    crosscheck: Any,
    slang_compatibility: dict[str, object] | None,
    crosscheck_path: Path,
    slang_version: str | None,
    facts_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    return {
        **dry_run_data,
        "verilator_return_code": result.return_code,
        "verilator_version": result.version or "unknown",
        "verilator_compatibility": compatibility,
        "verilator_version_log": str(result.version_log),
        "verilator_stdout_log": str(result.stdout_log),
        "verilator_stderr_log": str(result.stderr_log),
        "verilator_xml_files": sum(len(item.xml_files) for item, _ in run_results),
        "parameter_sweeps": [list(overrides) for _, overrides in run_results if overrides is not None],
        "normalized_modules": len(modules),
        "rtl_facts": str(facts_path),
        "rtl_facts_summary": str(summary_path),
        "semantic_crosscheck_status": crosscheck.status if crosscheck is not None else "off",
        "semantic_crosscheck_passed": crosscheck.passed if crosscheck is not None else None,
        "semantic_crosscheck_issues": len(crosscheck.issues) if crosscheck is not None else 0,
        "semantic_crosscheck": str(crosscheck_path) if crosscheck is not None else None,
        "slang_version": slang_version or "unknown",
        "slang_compatibility": slang_compatibility,
    }


def _verilator_result_lines(
    config: CLIConfig, data: dict[str, Any], result: Any, run_results: list[tuple[Any, Any]]
) -> tuple[str, ...]:
    return (
        f"verilator_return_code={result.return_code}",
        f"verilator_version={result.version or 'unknown'}",
        f"verilator_version_log={result.version_log}",
        f"verilator_stdout_log={result.stdout_log}",
        f"verilator_stderr_log={result.stderr_log}",
        f"verilator_xml_files={sum(len(item.xml_files) for item, _ in run_results)}",
        f"parameter_sweeps={len(config.parameter_sweeps)}",
        f"normalized_modules={data['normalized_modules']}",
        f"rtl_facts={data['rtl_facts']}",
        f"rtl_facts_summary={data['rtl_facts_summary']}",
        f"semantic_crosscheck_status={data['semantic_crosscheck_status']}",
        f"semantic_crosscheck={data['semantic_crosscheck'] or ''}",
    )


def _print_verilator_context(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    manifest_path: Path,
    verilator_command: tuple[str, ...],
) -> None:
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


def _emit_cached_analysis(
    args: argparse.Namespace,
    config: CLIConfig,
    dry_run_data: dict[str, Any],
) -> int:
    modules = read_normalized_rtl_facts(config)
    facts_path = config.work_dir / "rtl-facts" / "modules.json"
    summary_path = config.work_dir / "rtl-facts" / "summary.json"
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    version = str(payload.get("verilator_version") or "unknown")
    frontends = [str(item) for item in payload.get("normalization_frontends", ())]
    crosscheck_path = config.work_dir / "semantic-crosscheck" / "result.json"
    crosscheck_payload = _read_crosscheck_payload(crosscheck_path)
    vhdl_frontend = any(item.startswith("vhdl-source-normalizer/") for item in frontends)
    crosscheck_status = (
        str(crosscheck_payload.get("status", "off"))
        if crosscheck_payload
        else "unsupported"
        if vhdl_frontend and config.semantic_crosscheck == "report"
        else "off"
    )
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
            "normalization_frontends": frontends,
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
