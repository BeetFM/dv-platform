# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any, cast

from dv_platform.core.config import (
    validate_ai_config,
)
from dv_platform.core.models import CLIConfig, VerificationTarget

if TYPE_CHECKING:
    from dv_platform.analysis.ai_planning import augment_plans
    from dv_platform.analysis.docs import (
        EmbeddingProvider,
        VectorStore,
        read_configured_document_index,
    )
    from dv_platform.analysis.plan_store import write_plan_outputs
    from dv_platform.analysis.planner import create_initial_plan
    from dv_platform.analysis.registers import (
        RegisterAnalysis,
        extract_registers_from_documentation,
        extract_registers_from_rtl,
        load_register_map,
        merge_register_sources,
    )
    from dv_platform.analysis.rtl import (
        read_normalized_rtl_facts,
    )
    from dv_platform.core.plugins import LoadedAdapterPlugin
    from dv_platform.requirements import read_requirements_baseline


def _plan(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded_adapters: tuple[LoadedAdapterPlugin, ...] = (),
) -> int:
    if not _semantic_crosscheck_gate(args, config, "plan"):
        return 2
    inputs = _planning_inputs(args, config)
    if inputs is None:
        return 2
    modules, documentation_chunks, targets, register_analyses = inputs
    selected_ai_modules = _selected_ai_modules(args, config, modules)
    adapters = _planning_adapters(args, loaded_adapters)
    if selected_ai_modules is None or adapters is None:
        return 2
    providers, stores = adapters
    plans = _initial_plans(config, modules, documentation_chunks, targets, register_analyses, providers, stores)
    ai_result = None
    if args.ai:
        try:
            ai_result = augment_plans(
                config, modules, plans, documentation_chunks, selected_ai_modules, refresh=args.ai_refresh
            )
        except ValueError as error:
            _emit_error(args, "plan", "ai_preflight_failed", str(error))
            return 2
        plans = ai_result.plans
    outputs = write_plan_outputs(config, plans, strict=config.strict or config.ci)
    _emit_plan_result(args, modules, documentation_chunks, plans, outputs, ai_result)
    return 0


def _planning_inputs(
    args: argparse.Namespace, config: CLIConfig
) -> tuple[tuple[Any, ...], tuple[Any, ...], tuple[VerificationTarget, ...], dict[str, RegisterAnalysis]] | None:
    try:
        modules = read_normalized_rtl_facts(config)
    except OSError as error:
        _emit_error(args, "plan", "missing_rtl_facts", f"RTL facts are missing; run analyze-rtl first: {error}")
        return None
    except ValueError as error:
        _emit_error(args, "plan", "invalid_rtl_facts", str(error))
        return None

    try:
        documentation_chunks = read_configured_document_index(config)
    except OSError:
        documentation_chunks = ()

    targets = tuple(VerificationTarget(target) for target in (args.target or (VerificationTarget.COCOTB.value,)))
    register_analyses: dict[str, RegisterAnalysis] = {}
    try:
        for module in modules:
            documented = extract_registers_from_documentation(documentation_chunks, module.name)
            configured = tuple(
                (str(path), tuple(load_register_map(path, module.name))) for path in config.register_map_paths
            )
            register_analyses[module.name] = merge_register_sources(
                module, (("rtl", extract_registers_from_rtl(module)), ("documentation", documented), *configured)
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(args, "plan", "register_map_failed", str(error))
        return None
    return modules, documentation_chunks, targets, register_analyses


def _planning_adapters(
    args: argparse.Namespace, loaded_adapters: tuple[LoadedAdapterPlugin, ...]
) -> tuple[tuple[EmbeddingProvider, ...], tuple[VectorStore, ...]] | None:
    providers = tuple(
        cast(EmbeddingProvider, plugin.adapter) for plugin in loaded_adapters if plugin.kind == "embedding_provider"
    )
    stores = tuple(cast(VectorStore, plugin.adapter) for plugin in loaded_adapters if plugin.kind == "vector_store")
    if len(providers) > 1 or len(stores) > 1:
        _emit_error(
            args,
            "plan",
            "retrieval_adapter_ambiguous",
            "plan accepts at most one embedding_provider and one vector_store adapter",
        )
        return None
    return providers, stores


def _initial_plans(
    config: CLIConfig,
    modules: tuple[Any, ...],
    documentation_chunks: tuple[Any, ...],
    targets: tuple[VerificationTarget, ...],
    register_analyses: dict[str, RegisterAnalysis],
    providers: tuple[EmbeddingProvider, ...],
    stores: tuple[VectorStore, ...],
) -> tuple[Any, ...]:
    requirements = read_requirements_baseline(config)
    return tuple(
        create_initial_plan(
            module,
            targets=targets,
            documentation_chunks=documentation_chunks,
            retrieval_index_dir=config.retrieval_index_dir or config.work_dir / "rag-index",
            embedding_provider=providers[0] if providers else None,
            vector_store=stores[0] if stores else None,
            depth_policies=config.depth_policies,
            imported_requirements=requirements,
            register_models=register_analyses[module.name].registers,
            register_conflicts=register_analyses[module.name].conflicts,
            register_open_questions=register_analyses[module.name].open_questions,
        )
        for module in modules
    )


def _emit_plan_result(
    args: argparse.Namespace,
    modules: tuple[Any, ...],
    documentation_chunks: tuple[Any, ...],
    plans: tuple[Any, ...],
    outputs: tuple[Any, Any, Any, Any],
    ai_result: Any,
) -> None:
    sqlite_path, module_paths, index_path, claim_report_paths = outputs
    data = {
        "modules": len(modules),
        "documentation_chunks": len(documentation_chunks),
        "plans": len(plans),
        "plans_db": str(sqlite_path),
        "plan_index": str(index_path),
        "plan_markdown_files": len(module_paths),
        "claim_report_files": len(claim_report_paths),
        "ai_requested": bool(args.ai),
        "ai_requested_modules": ai_result.requested_modules if ai_result is not None else 0,
        "ai_augmented_modules": ai_result.augmented_modules if ai_result is not None else 0,
        "ai_fallback_modules": ai_result.fallback_modules if ai_result is not None else 0,
        "ai_cache_hit_modules": ai_result.cache_hit_modules if ai_result is not None else 0,
        "ai_run_id": ai_result.run_id if ai_result is not None else None,
        "ai_run_records": [str(path) for path in ai_result.run_record_paths] if ai_result is not None else [],
    }
    _emit_success(
        args,
        "plan",
        data,
        (
            "command=plan",
            f"modules={data['modules']}",
            f"documentation_chunks={data['documentation_chunks']}",
            f"plans={data['plans']}",
            f"plans_db={sqlite_path}",
            f"plan_index={index_path}",
            f"plan_markdown_files={len(module_paths)}",
            f"claim_report_files={len(claim_report_paths)}",
            f"ai_requested={str(data['ai_requested']).lower()}",
            f"ai_requested_modules={data['ai_requested_modules']}",
            f"ai_augmented_modules={data['ai_augmented_modules']}",
            f"ai_fallback_modules={data['ai_fallback_modules']}",
            f"ai_cache_hit_modules={data['ai_cache_hit_modules']}",
            *(f"ai_run_record={path}" for path in (ai_result.run_record_paths if ai_result is not None else ())),
        ),
    )


def _selected_ai_modules(
    args: argparse.Namespace,
    config: CLIConfig,
    modules: tuple[Any, ...],
) -> tuple[str, ...] | None:
    if (args.module or args.ai_refresh) and not args.ai:
        _emit_error(
            args,
            "plan",
            "ai_preflight_failed",
            "--module and --ai-refresh are valid only with plan --ai.",
        )
        return None
    if not args.ai:
        return ()
    module_names = {module.name for module in modules}
    selected = tuple(dict.fromkeys(args.module or module_names))
    unknown = tuple(name for name in selected if name not in module_names)
    if unknown:
        _emit_error(
            args,
            "plan",
            "ai_preflight_failed",
            f"Unknown AI planning module selection: {', '.join(unknown)}",
        )
        return None
    module_limit = min(20, config.ai.max_modules_per_run)
    if len(selected) > module_limit:
        _emit_error(
            args,
            "plan",
            "ai_preflight_failed",
            f"AI planning selected {len(selected)} modules; the configured limit is {module_limit}.",
        )
        return None
    diagnostics = validate_ai_config(config.ai)
    if diagnostics:
        _emit_error(
            args,
            "plan",
            "ai_preflight_failed",
            "AI planning configuration is invalid.",
            diagnostics=diagnostics,
        )
        return None
    return selected
