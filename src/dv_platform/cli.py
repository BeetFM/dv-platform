# ruff: noqa: E402,F401,I001
"""Compatibility composition root for focused CLI handlers."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from dv_platform.core.config import (
    DEFAULT_CONFIG_FILENAME,
    ConfigDiagnostic,
    default_config,
    load_config,
    normalize_config,
    validate_ai_config,
    validate_config,
    validate_target_tools,
    write_config,
)
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget

if TYPE_CHECKING:
    from dv_platform.analysis.ai_feedback import propose_feedback_operations
    from dv_platform.analysis.ai_gateway import LiteLLMGateway
    from dv_platform.analysis.ai_planning import augment_plans
    from dv_platform.analysis.ai_scenarios import synthesize_scenario_selections
    from dv_platform.analysis.coverage import CoverageImporter, import_coverage_reports
    from dv_platform.analysis.dependencies import build_dependency_graph
    from dv_platform.analysis.discovery import build_verilator_dry_run_command, discover_project, write_project_manifest
    from dv_platform.analysis.docs import (
        DocumentLoader,
        EmbeddingProvider,
        LocalHashEmbeddingProvider,
        LocalJsonVectorStore,
        LocalSQLiteFTSStore,
        VectorStore,
        chunk_documents,
        discover_documentation_files,
        load_documents_with_adapters,
        read_configured_document_index,
        write_document_index_with_adapters,
    )
    from dv_platform.analysis.feedback import normalize_feedback
    from dv_platform.analysis.plan_store import read_plan_records, read_stored_plans, write_plan_outputs
    from dv_platform.analysis.planner import create_initial_plan
    from dv_platform.analysis.registers import (
        RegisterAnalysis,
        extract_registers_from_documentation,
        extract_registers_from_rtl,
        load_register_map,
        merge_register_sources,
    )
    from dv_platform.analysis.review import (
        generate_design_decisions,
        generate_run_feedback_decisions,
        write_review_outputs,
    )
    from dv_platform.analysis.revisions import (
        create_feedback_revision,
        plan_hash,
        project_manifest_hash,
        read_revision_plan,
        read_revisions,
        record_revision_generation,
    )
    from dv_platform.analysis.rtl import (
        classify_verilator_version,
        normalize_verilator_xml,
        read_normalized_rtl_facts,
        run_verilator_xml,
        write_normalized_rtl_facts,
        write_rtl_facts_summary,
        write_verilator_failure_summary,
    )
    from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
    from dv_platform.analysis.vhdl import normalize_vhdl_sources
    from dv_platform.core.operations import backup_project_state, governed_destruction, migrate_project_state
    from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
    from dv_platform.core.security import (
        append_audit_event,
        purge_retained_files,
        validate_export_destination,
        write_support_bundle,
    )
    from dv_platform.requirements import read_requirements_baseline
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
    from dv_platform.run import (
        discover_generated_modules,
        execute_formal_run,
        execute_simulation_run,
        prepare_formal_run,
        prepare_simulation_run,
        write_aggregate_run_summary,
    )

from dv_platform.cli_handlers import parser as _part_0
from dv_platform.cli_handlers import dispatch as _part_1
from dv_platform.cli_handlers.commands.rtl import analysis as _part_2
from dv_platform.cli_handlers.commands.rtl import support as _part_3
from dv_platform.cli_handlers.commands import documentation as _part_4
from dv_platform.cli_handlers.commands import planning as _part_5
from dv_platform.cli_handlers.commands import generation as _part_6
from dv_platform.cli_handlers.commands import run as _part_7
from dv_platform.cli_handlers.commands import review as _part_8
from dv_platform.cli_handlers.commands import feedback as _part_9
from dv_platform.cli_handlers.commands import status as _part_10
from dv_platform.cli_handlers import output as _part_11
from dv_platform.cli_handlers.parser import ReportExporter, build_parser, config_from_args, resolved_config_path
from dv_platform.cli_handlers.dispatch import main, _load_command_dependencies, _init_config_from_args
from dv_platform.cli_handlers.commands.rtl.analysis import _analyze_rtl, _analyze_vhdl_rtl, _analyze_mixed_rtl
from dv_platform.cli_handlers.commands.rtl.support import (
    _parameter_sweep_configs,
    _sweep_identity,
    _rtl_input_fingerprint,
    _rtl_cache_matches,
    _semantic_crosscheck_enforced,
    _read_crosscheck_payload,
    _semantic_crosscheck_gate,
)
from dv_platform.cli_handlers.commands.documentation import _index_docs
from dv_platform.cli_handlers.commands.planning import _plan
from dv_platform.cli_handlers.commands.generation import _generate
from dv_platform.cli_handlers.commands.run import (
    _run,
    _coverage,
    _coverage_run_summaries,
    _bounded_execution_workers,
    _run_all_generated_modules,
    _run_all_formal_modules,
)
from dv_platform.cli_handlers.commands.review import _review
from dv_platform.cli_handlers.commands.feedback import (
    _feedback,
    _known_affected_artifact_paths,
    _feedback_run_summaries,
)
from dv_platform.cli_handlers.commands.status import _status
from dv_platform.cli_handlers.output import _print_diagnostics, _emit_success, _emit_error, _diagnostics_json

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
    _part_5,
    _part_6,
    _part_7,
    _part_8,
    _part_9,
    _part_10,
    _part_11,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _legacy_class in (ReportExporter,):
    _legacy_class.__module__ = "dv_platform.cli"
del (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
    _part_5,
    _part_6,
    _part_7,
    _part_8,
    _part_9,
    _part_10,
    _part_11,
    _legacy_class,
    _namespace,
    _part,
    _parts,
)
