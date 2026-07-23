# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

from dv_platform.core.config import (
    validate_target_tools,
)
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, VerificationTarget

if TYPE_CHECKING:
    from dv_platform.analysis.dependencies import build_dependency_graph
    from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans
    from dv_platform.analysis.revisions import (
        plan_hash,
        project_manifest_hash,
        read_revision_plan,
        read_revisions,
        record_revision_generation,
    )
    from dv_platform.generators import (
        CocotbGenerator,
        FormalGenerator,
        GeneratorRegistry,
        SystemVerilogGenerator,
        UvmGenerator,
        VerilogGenerator,
        VhdlGenerator,
        load_generator_plugins,
        write_generated_artifacts,
    )


def _generate(args: argparse.Namespace, config: CLIConfig) -> int:
    target = _generation_target(args, config)
    if target is None:
        return 2
    loaded = _load_generation_plans(args, config)
    if loaded is None:
        return 2
    plans, records = loaded

    selection = _select_revision(args, config, plans, records)
    if selection is None:
        return 2
    plans, records, selected_revision = selection

    blocked = tuple(record for record in records if not bool(record["gate"]["allowed"]))
    if blocked:
        modules = ", ".join(str(record["module"]) for record in blocked)
        _emit_error(
            args,
            "generate",
            "claim_gate_blocked",
            f"Generation blocked by claim gate for modules: {modules}",
            data={"blocked_modules": [str(record["module"]) for record in blocked]},
        )
        return 2

    selected_plans = tuple(plan for plan in plans if target in plan.targets)
    generated = _generate_artifacts(args, config, target, selected_plans, selected_revision)
    if generated is None:
        return 2
    loaded_plugins, result = generated
    revision_state = _record_generated_revision(args, config, target, selected_revision, result)
    if revision_state is False:
        return 2
    _emit_generation_result(
        args, target, selected_plans, loaded_plugins, result, revision_state if revision_state is not False else None
    )
    return 0


def _generate_artifacts(
    args: argparse.Namespace,
    config: CLIConfig,
    target: VerificationTarget,
    selected_plans: tuple[Any, ...],
    selected_revision: Any,
) -> tuple[tuple[str, ...], Any] | None:
    registry = GeneratorRegistry()
    registry.register(CocotbGenerator())
    registry.register(FormalGenerator(args.cdc_policy, args.cdc_bmc_depth))
    registry.register(SystemVerilogGenerator())
    registry.register(VerilogGenerator())
    registry.register(VhdlGenerator())
    registry.register(UvmGenerator())
    try:
        loaded_plugins = load_generator_plugins(
            registry,
            config.generator_plugins,
            trusted_plugins=config.adapter_plugins,
            approved_publishers=config.approved_plugin_publishers,
        )
    except (LookupError, TypeError) as error:
        _emit_error(args, "generate", "plugin_load_failed", str(error))
        return None
    try:
        artifacts = tuple(artifact for plan in selected_plans for artifact in registry.get(target).generate(plan))
    except ValueError as error:
        _emit_error(args, "generate", "generation_policy_blocked", str(error))
        return None
    affected_paths = _revision_affected_paths(config, target, selected_plans, artifacts, selected_revision)
    try:
        result = write_generated_artifacts(
            config,
            artifacts,
            # A selected revision updates only its module and must preserve every
            # unrelated target/module directory byte-for-byte.
            replace_target=None if args.revision is not None else target,
            expected_modules=None if args.revision is not None else tuple(plan.module for plan in selected_plans),
            affected_paths=affected_paths,
        )
    except ValueError as error:
        _emit_error(args, "generate", "artifact_write_failed", str(error))
        return None
    return loaded_plugins, result


def _record_generated_revision(
    args: argparse.Namespace, config: CLIConfig, target: VerificationTarget, selected_revision: Any, result: Any
) -> Any:
    if selected_revision is None:
        return None
    provenance_path = next(
        (path for path in result.provenance_paths if path.parent.name == selected_revision.module),
        None,
    )
    if provenance_path is None:
        _emit_error(
            args,
            "generate",
            "revision_state_failed",
            f"Generated revision has no provenance for module: {selected_revision.module}",
        )
        return False
    try:
        return record_revision_generation(config.work_dir, selected_revision, target.value, provenance_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit_error(args, "generate", "revision_state_failed", str(error))
        return False


def _emit_generation_result(
    args: argparse.Namespace,
    target: VerificationTarget,
    selected_plans: tuple[Any, ...],
    loaded_plugins: tuple[str, ...],
    result: Any,
    revision_state: Any,
) -> None:
    data = {
        "target": str(target),
        "plans": len(selected_plans),
        "generator_plugins": list(loaded_plugins),
        "cdc_policy": args.cdc_policy if target == VerificationTarget.FORMAL else None,
        "cdc_bmc_depth": args.cdc_bmc_depth if target == VerificationTarget.FORMAL else None,
        "artifacts": len(result.artifact_paths),
        "artifact_paths": [str(path) for path in result.artifact_paths],
        "provenance_manifests": len(result.provenance_paths),
        "provenance_paths": [str(path) for path in result.provenance_paths],
        "revision": args.revision,
        "revision_state": str(revision_state) if revision_state is not None else None,
    }
    _emit_success(
        args,
        "generate",
        data,
        (
            "command=generate",
            f"target={target}",
            f"plans={len(selected_plans)}",
            f"generator_plugins={','.join(loaded_plugins)}",
            f"artifacts={len(result.artifact_paths)}",
            f"provenance_manifests={len(result.provenance_paths)}",
        ),
    )


def _generation_target(args: argparse.Namespace, config: CLIConfig) -> VerificationTarget | None:
    if not _semantic_crosscheck_gate(args, config, "generate"):
        return None
    target = VerificationTarget(args.target)
    if args.cdc_bmc_depth <= 0:
        _emit_error(args, "generate", "invalid_cdc_bmc_depth", "--cdc-bmc-depth must be greater than zero.")
        return None
    diagnostics = validate_target_tools(config, (target,))
    if not getattr(args, "json_output", False):
        _print_diagnostics(diagnostics)
    if any(diagnostic.severity == "error" for diagnostic in diagnostics):
        _emit_error(
            args,
            "generate",
            "tool_configuration_error",
            "Target tool configuration is invalid.",
            diagnostics=diagnostics,
        )
        return None
    supported = {
        VerificationTarget.COCOTB,
        VerificationTarget.FORMAL,
        VerificationTarget.SYSTEMVERILOG,
        VerificationTarget.VERILOG,
        VerificationTarget.VHDL,
        VerificationTarget.UVM,
    }
    if target not in supported:
        _emit_error(args, "generate", "missing_generator", f"No generator registered for target: {target}")
        return None
    return target


def _load_generation_plans(
    args: argparse.Namespace, config: CLIConfig
) -> tuple[tuple[Any, ...], tuple[dict[str, Any], ...]] | None:
    plans_db = config.work_dir / "plans" / "plans.sqlite"
    if not plans_db.is_file():
        _emit_error(args, "generate", "missing_plans", f"Plans are missing; run plan first: {plans_db}")
        return None
    try:
        return read_stored_plans(plans_db), read_plan_records(plans_db)
    except OSError as error:
        _emit_error(args, "generate", "missing_plans", f"Plans are missing; run plan first: {error}")
    except ValueError as error:
        _emit_error(args, "generate", "invalid_plans", str(error))
    return None


def _select_revision(
    args: argparse.Namespace,
    config: CLIConfig,
    plans: tuple[Any, ...],
    records: tuple[dict[str, Any], ...],
) -> tuple[tuple[Any, ...], tuple[dict[str, Any], ...], Any | None] | None:
    if args.revision is None:
        return plans, records, None
    revisions = tuple(revision for plan in plans for revision in read_revisions(config.work_dir, plan.module))
    selected = next((revision for revision in revisions if revision.revision_id == args.revision), None)
    if selected is None:
        _emit_error(args, "generate", "unknown_revision", f"Plan revision is not readable: {args.revision}")
        return None
    revision_plan = read_revision_plan(config.work_dir, selected.revision_id)
    if revision_plan is None:
        _emit_error(
            args,
            "generate",
            "stale_revision",
            f"Plan revision has no immutable snapshot: {args.revision}",
        )
        return None
    if plan_hash(revision_plan) != selected.resulting_plan_hash:
        _emit_error(
            args,
            "generate",
            "stale_revision",
            f"Plan revision snapshot hash does not match its record: {args.revision}",
        )
        return None
    canonical = next((plan for plan in plans if plan.module == selected.module), None)
    if _revision_inputs_changed(config, canonical, selected):
        _emit_error(
            args,
            "generate",
            "stale_revision",
            f"Canonical plan or RTL inputs changed after revision creation: {args.revision}",
        )
        return None
    if not _revision_parent_matches(revisions, selected):
        _emit_error(
            args,
            "generate",
            "stale_revision",
            f"Parent revision snapshot changed or is unavailable: {args.revision}",
        )
        return None
    selected_records = tuple(record for record in records if record["module"] == selected.module)
    return (revision_plan,), selected_records, selected


def _revision_inputs_changed(config: CLIConfig, canonical: Any | None, revision: Any) -> bool:
    if canonical is None:
        return True
    if revision.canonical_plan_hash is not None and plan_hash(canonical) != revision.canonical_plan_hash:
        return True
    return (
        revision.rtl_manifest_hash is not None and project_manifest_hash(config.work_dir) != revision.rtl_manifest_hash
    )


def _revision_parent_matches(revisions: tuple[Any, ...], revision: Any) -> bool:
    if revision.parent_revision_id is None or revision.parent_snapshot_hash is None:
        return True
    parent = next((item for item in revisions if item.revision_id == revision.parent_revision_id), None)
    return parent is not None and parent.resulting_plan_hash == revision.parent_snapshot_hash


def _revision_affected_paths(
    config: CLIConfig,
    target: VerificationTarget,
    plans: tuple[Any, ...],
    artifacts: tuple[Any, ...],
    revision: Any | None,
) -> dict[tuple[VerificationTarget, str], set[str]] | None:
    if revision is None:
        return None
    graph = build_dependency_graph(plans[0], artifacts)
    seeds = (
        *(f"check:{check_id}" for check_id in revision.affected_check_ids),
        *(f"scenario:{scenario_id}" for scenario_id in revision.affected_scenario_ids),
        *(f"requirement:{requirement_id}" for requirement_id in revision.changed_requirement_ids),
    )
    affected = graph.affected(seeds)
    paths = {
        artifact_id.split("/", 2)[2]
        for artifact_id in affected.artifact_paths
        if artifact_id.startswith(f"{target.value}/{revision.module}/")
    }
    paths.update(revision.affected_artifact_paths)
    dependency_path = config.work_dir / "plans" / "revision-dependencies" / f"{revision.revision_id}.json"
    atomic_write_text(
        dependency_path,
        json.dumps(
            {
                "schema_version": 1,
                "revision_id": revision.revision_id,
                "edges": list(graph.edges),
                "affected": {
                    "checks": list(affected.check_ids),
                    "scenarios": list(affected.scenario_ids),
                    "symbols": list(affected.generated_symbols),
                    "artifacts": list(affected.artifact_paths),
                    "runs": list(affected.run_targets),
                    "coverage": list(affected.coverage_point_ids),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return {(target, revision.module): paths}
