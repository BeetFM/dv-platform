# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""VHDL and mixed-language RTL analysis handlers."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from dv_platform.analysis.rtl import (
    normalize_verilator_xml,
    run_verilator_xml,
    write_normalized_rtl_facts,
    write_rtl_facts_summary,
)
from dv_platform.analysis.vhdl import normalize_vhdl_sources
from dv_platform.cli_handlers.output import _emit_error, _emit_success
from dv_platform.cli_handlers.rtl_support import _semantic_crosscheck_enforced, _sweep_identity
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig
from dv_platform.core.security import append_audit_event


def _analyze_vhdl_rtl(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    vhdl_files: tuple[Any, ...],
    sweep_runs: tuple[tuple[CLIConfig, tuple[str, ...] | None], ...],
    dry_run_data: dict[str, object],
    cache_path: Path,
    input_fingerprint: str,
) -> int:
    """Run the bounded VHDL source normalizer without invoking Verilator."""

    from dv_platform.analysis.vhdl import (
        VHDL_NORMALIZER_VERSION,
        VHDLNormalizationError,
        validate_vhdl_elaboration,
    )

    if _semantic_crosscheck_enforced(config):
        _emit_error(
            args,
            "analyze-rtl",
            "vhdl_semantic_crosscheck_unsupported",
            "The qualified Slang cross-check does not support VHDL; required cross-check mode fails closed.",
            data=dry_run_data,
        )
        return 2

    normalized_runs = []
    append_audit_event(
        config,
        "rtl_analysis.start",
        {"frontend": VHDL_NORMALIZER_VERSION, "source_files": [str(item.path) for item in vhdl_files]},
    )
    try:
        normalized_runs = _normalize_vhdl_runs(config, vhdl_files, sweep_runs, validate_vhdl_elaboration)
    except (OSError, VHDLNormalizationError) as error:
        append_audit_event(
            config,
            "rtl_analysis.finish",
            {"frontend": VHDL_NORMALIZER_VERSION, "status": "failed", "reason": str(error)},
        )
        _emit_error(args, "analyze-rtl", "vhdl_normalization_failed", str(error), data=dry_run_data)
        return 2

    modules = tuple(module for run_modules in normalized_runs for module in run_modules)
    append_audit_event(
        config,
        "rtl_analysis.finish",
        {"frontend": VHDL_NORMALIZER_VERSION, "status": "passed", "normalized_modules": len(modules)},
    )
    return _persist_vhdl_analysis(
        args, config, modules, sweep_runs, dry_run_data, cache_path, input_fingerprint, VHDL_NORMALIZER_VERSION
    )


def _normalize_vhdl_runs(
    config: CLIConfig, vhdl_files: tuple[Any, ...], sweep_runs: tuple[Any, ...], validate_elaboration: Any
) -> list[tuple[Any, ...]]:
    normalized_runs = []
    for run_config, overrides in sweep_runs:
        run_modules = normalize_vhdl_sources(
            tuple(item.path for item in vhdl_files),
            parameter_overrides=run_config.parameter_overrides,
            top_modules=run_config.top_modules,
            identity_suffix=_sweep_identity(overrides) if overrides is not None else None,
            production_protocol_bindings=config.production_protocol_bindings,
        )
        validate_elaboration(
            tuple(item.path for item in vhdl_files),
            tuple(module.original_name or module.name for module in run_modules),
            run_config.work_dir / "ghdl-elaboration",
        )
        normalized_runs.append(run_modules)
    return normalized_runs


def _persist_vhdl_analysis(
    args: argparse.Namespace,
    config: CLIConfig,
    modules: tuple[Any, ...],
    sweep_runs: tuple[Any, ...],
    dry_run_data: dict[str, object],
    cache_path: Path,
    input_fingerprint: str,
    normalizer_version: str,
) -> int:
    frontends = (normalizer_version, "ghdl-elaboration")
    facts_path = write_normalized_rtl_facts(
        config,
        modules,
        normalization_frontends=frontends,
    )
    summary_path = write_rtl_facts_summary(
        config,
        modules,
        normalization_frontends=frontends,
    )
    crosscheck_status = "unsupported" if config.semantic_crosscheck == "report" else "off"
    atomic_write_text(
        cache_path,
        json.dumps(
            {
                "schema_version": 2,
                "input_fingerprint": input_fingerprint,
                "semantic_crosscheck_status": crosscheck_status,
                "normalization_frontends": list(frontends),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    data = {
        **dry_run_data,
        "cache_hit": False,
        "normalization_frontends": list(frontends),
        "normalized_modules": len(modules),
        "parameter_sweeps": [list(overrides) for _, overrides in sweep_runs if overrides is not None],
        "rtl_facts": str(facts_path),
        "rtl_facts_summary": str(summary_path),
        "semantic_crosscheck_status": crosscheck_status,
    }
    _emit_success(
        args,
        "analyze-rtl",
        data,
        (
            f"normalization_frontend={normalizer_version}",
            f"normalized_modules={len(modules)}",
            f"parameter_sweeps={len(config.parameter_sweeps)}",
            f"rtl_facts={facts_path}",
            f"rtl_facts_summary={summary_path}",
            f"semantic_crosscheck_status={crosscheck_status}",
        ),
    )
    return 0


def _analyze_mixed_rtl(
    args: argparse.Namespace,
    config: CLIConfig,
    inventory: Any,
    verilator_inventory: Any,
    vhdl_files: tuple[Any, ...],
    sweep_runs: tuple[tuple[CLIConfig, tuple[str, ...] | None], ...],
    dry_run_data: dict[str, object],
    cache_path: Path,
    input_fingerprint: str,
) -> int:
    """Normalize explicitly bound language partitions and reconcile their interfaces."""

    from dv_platform.analysis.bindings import (
        binding_units,
        load_cross_language_bindings,
        validate_cross_language_bindings,
    )
    from dv_platform.analysis.vhdl import (
        VHDL_NORMALIZER_VERSION,
        VHDLNormalizationError,
        validate_vhdl_elaboration,
    )

    if config.cross_language_bindings is None:
        _emit_error(
            args,
            "analyze-rtl",
            "cross_language_bindings_required",
            "Mixed-language analysis requires an explicit rtl.cross_language_bindings manifest.",
            data=dry_run_data,
        )
        return 2
    if config.semantic_crosscheck != "off":
        _emit_error(
            args,
            "analyze-rtl",
            "mixed_language_crosscheck_unsupported",
            "Mixed-language analysis cannot currently satisfy a configured Slang semantic cross-check.",
            data=dry_run_data,
        )
        return 2
    try:
        bindings, normalized_runs, versions, ghdl_versions = _normalize_mixed_runs(
            config,
            verilator_inventory,
            vhdl_files,
            sweep_runs,
            load_cross_language_bindings,
            binding_units,
            validate_cross_language_bindings,
            validate_vhdl_elaboration,
        )
    except (OSError, ValueError, VHDLNormalizationError) as error:
        _emit_error(args, "analyze-rtl", "mixed_language_normalization_failed", str(error), data=dry_run_data)
        return 2

    modules = tuple(module for run_modules in normalized_runs for module in run_modules)
    return _persist_mixed_analysis(
        args,
        config,
        modules,
        bindings,
        versions,
        ghdl_versions,
        dry_run_data,
        cache_path,
        input_fingerprint,
        VHDL_NORMALIZER_VERSION,
    )


def _normalize_mixed_runs(
    config: CLIConfig,
    verilator_inventory: Any,
    vhdl_files: tuple[Any, ...],
    sweep_runs: tuple[Any, ...],
    load_bindings: Any,
    units_for: Any,
    validate_bindings: Any,
    validate_elaboration: Any,
) -> tuple[Any, list[tuple[Any, ...]], list[str], list[str]]:
    bindings = load_bindings(config.cross_language_bindings)
    verilog_units = units_for(bindings, {"verilog", "systemverilog"})
    vhdl_units = units_for(bindings, {"vhdl"})
    if not verilog_units or not vhdl_units:
        raise ValueError("binding manifest must connect VHDL and Verilog/SystemVerilog units")
    normalized_runs, versions, ghdl_versions = [], [], []
    architecture_bindings = tuple(
        (binding.child_unit, binding.architecture)
        for binding in bindings
        if binding.child_language == "vhdl" and binding.architecture is not None
    )
    for run_config, overrides in sweep_runs:
        suffix = _sweep_identity(overrides) if overrides is not None else None
        sv_result = run_verilator_xml(replace(run_config, top_modules=verilog_units), verilator_inventory)
        if sv_result.return_code != 0:
            raise ValueError(
                f"Verilator mixed-language partition failed with return code {sv_result.return_code}; "
                f"see {sv_result.stderr_log}"
            )
        versions.append(sv_result.version or "unknown")
        ghdl_versions.append(
            validate_elaboration(
                tuple(item.path for item in vhdl_files), vhdl_units, run_config.work_dir / "ghdl-elaboration"
            )
        )
        modules = (
            *normalize_verilator_xml(
                sv_result.xml_files,
                config.protocol_profiles,
                config.production_protocol_bindings,
                identity_suffix=suffix,
            ),
            *normalize_vhdl_sources(
                tuple(item.path for item in vhdl_files),
                parameter_overrides=run_config.parameter_overrides,
                top_modules=vhdl_units,
                identity_suffix=suffix,
                production_protocol_bindings=config.production_protocol_bindings,
                architecture_bindings=architecture_bindings,
            ),
        )
        validate_bindings(bindings, modules)
        normalized_runs.append(modules)
    return bindings, normalized_runs, versions, ghdl_versions


def _persist_mixed_analysis(
    args: argparse.Namespace,
    config: CLIConfig,
    modules: tuple[Any, ...],
    bindings: Any,
    versions: list[str],
    ghdl_versions: list[str],
    dry_run_data: dict[str, object],
    cache_path: Path,
    input_fingerprint: str,
    normalizer_version: str,
) -> int:
    frontends = ("verilator", normalizer_version, "ghdl-elaboration", "cross-language-bindings/1")
    version = versions[0] if versions and len(set(versions)) == 1 else "mixed"
    facts_path = write_normalized_rtl_facts(config, modules, version, normalization_frontends=frontends)
    summary_path = write_rtl_facts_summary(config, modules, version, normalization_frontends=frontends)
    atomic_write_text(
        cache_path,
        json.dumps(
            {
                "schema_version": 2,
                "input_fingerprint": input_fingerprint,
                "semantic_crosscheck_status": "off",
                "normalization_frontends": list(frontends),
                "binding_manifest": str(config.cross_language_bindings),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    data = {
        **dry_run_data,
        "cache_hit": False,
        "normalization_frontends": list(frontends),
        "normalized_modules": len(modules),
        "rtl_facts": str(facts_path),
        "rtl_facts_summary": str(summary_path),
        "binding_manifest": str(config.cross_language_bindings),
        "binding_count": len(bindings),
        "ghdl_version": ghdl_versions[0] if ghdl_versions else "unknown",
        "semantic_crosscheck_status": "off",
    }
    _emit_success(
        args,
        "analyze-rtl",
        data,
        (
            "normalization_frontends=" + ",".join(frontends),
            f"normalized_modules={len(modules)}",
            f"binding_count={len(bindings)}",
            f"rtl_facts={facts_path}",
        ),
    )
    return 0
