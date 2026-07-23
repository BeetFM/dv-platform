# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from dv_platform.core.models import CLIConfig

if TYPE_CHECKING:
    from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy


def _status(args: argparse.Namespace, config: CLIConfig) -> int:
    status = collect_platform_status(config)
    policy_mode = args.policy == "ci" or config.ci
    policy_failures = evaluate_status_policy(status, require_tools=not args.no_require_tools) if policy_mode else ()
    status = {**status, "policy": {"mode": "ci" if policy_mode else "report", "failures": list(policy_failures)}}
    summary = status["summary"]
    schemas = status["schemas"]
    rtl_schema = schemas["rtl_facts"]
    plan_schema = schemas["plans"]
    tools = status["tools"]
    ai = status["ai"]
    optimizer = status["context_optimization"]
    headroom = optimizer["headroom"]
    code_graph = optimizer["code_graph"]
    lines = (
        "command=status",
        f"rtl_facts_schema={rtl_schema['status']}",
        f"rtl_facts_stored_schema={rtl_schema['stored_schema_version']}",
        f"rtl_facts_modules={rtl_schema['modules']}",
        f"plan_schema={plan_schema['status']}",
        f"plan_stored_schemas={','.join(str(item) for item in plan_schema['stored_schema_versions'])}",
        f"plans={plan_schema['plans']}",
        f"verilator_available={str(tools['verilator']['available']).lower()}",
        f"verilator_stored_version={tools['verilator']['stored_version']}",
        f"simulators={len(tools['simulators'])}",
        f"formal_tools={len(tools['formal_tools'])}",
        f"ai_dependency_available={str(ai['dependency_available']).lower()}",
        f"ai_configured={str(ai['configured']).lower()}",
        f"ai_credential_present={str(ai['credential_present']).lower() if ai['credential_present'] is not None else 'not-required'}",
        f"ai_ready_for_live_request={str(ai['ready_for_live_request']).lower()}",
        f"ai_scenario_synthesis={ai['stages']['scenario_synthesis']}",
        f"context_optimization_enabled={str(optimizer['enabled']).lower()}",
        f"headroom_health={headroom['health']}",
        f"code_graph_available={str(code_graph['available']).lower()}",
        f"code_graph_present={str(code_graph['graph_present']).lower()}",
        f"generated_modules={summary['generated_modules']}",
        f"generated_artifacts={summary['generated_artifacts']}",
        f"quality_missing={summary['quality_missing']}",
        f"quality_failed={summary['quality_failed']}",
        f"artifacts_missing={summary['artifacts_missing']}",
        f"provenance_invalid={summary['provenance_invalid']}",
        f"integrity_missing={summary['integrity_missing']}",
        f"integrity_failed={summary['integrity_failed']}",
        f"tool_validation_missing={summary['tool_validation_missing']}",
        f"tool_validation_failed={summary['tool_validation_failed']}",
        f"traceability_missing={summary['traceability_missing']}",
        f"execution_manifest_invalid={summary['execution_manifest_invalid']}",
        f"expected_generated_missing={summary['expected_generated_missing']}",
        f"unexpected_generated={summary['unexpected_generated']}",
        f"unsafe_generated_roots={summary['unsafe_generated_roots']}",
        f"run_summaries={summary['run_summaries']}",
        f"failed_runs={summary['failed_runs']}",
        f"expected_runs_missing={summary['expected_runs_missing']}",
        f"coverage_status={summary['coverage_status']}",
        f"policy_mode={status['policy']['mode']}",
        f"policy_failures={len(policy_failures)}",
    )
    if policy_failures:
        _emit_error(
            args,
            "status",
            "status_policy_failed",
            "Status CI policy failed.",
            data=status,
        )
        if not getattr(args, "json_output", False):
            for line in lines:
                print(line)
            for failure in policy_failures:
                print(f"policy_failure={failure['code']}:{failure['message']}")
        return 2
    _emit_success(args, "status", status, lines)
    return 0
