# ruff: noqa: E402,F401,I001
"""Compatibility composition root for focused execution subsystems."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.sandbox import sandbox_command
from dv_platform.core.security import append_audit_event, redact_text, redact_value
from dv_platform.core.tool_versions import (
    TOOL_VERSION_POLICIES,
    classify_tool_output,
    formal_dependency_qualifications,
    probe_tool_version,
)
from dv_platform.core.validation import validation_result_from_coverage
from dv_platform.generators.artifacts import EXECUTION_MANIFEST_NAME, validate_generated_directory
from dv_platform.generators.signals import vhdl_identifier

from dv_platform.formal import execution as _part_0
from dv_platform.execution import simulation as _part_1
from dv_platform.execution import process_control as _part_2
from dv_platform.execution import summaries as _part_3
from dv_platform.formal.execution import (
    FormalResults,
    FormalRun,
    prepare_formal_run,
    execute_formal_run,
    _write_formal_command,
    _write_formal_summary,
    _formal_check_statuses,
    _formal_cdc_verification,
    _write_run_sby,
    _replace_sby_section,
    parse_formal_results,
    _trace_path_from_line,
    _formal_trace_paths,
    _yosys_quote,
)
from dv_platform.execution.simulation import (
    CocotbResults,
    NativeResults,
    SimulationRun,
    prepare_simulation_run,
    execute_simulation_run,
    _write_command,
    _simulation_tool_qualification,
    _cocotb_trace_statuses,
    _native_trace_statuses,
    _write_cocotb_runner_script,
    _write_iverilog_runner_script,
    _write_ghdl_runner_script,
    parse_cocotb_results,
    parse_native_results,
    _testcase_failed,
    _testcase_name,
    _generated_test_path,
)
from dv_platform.execution.process_control import (
    _ProcessResult,
    _set_process_memory_limit,
    _terminate_process_group,
    _capture_process_stream,
    _run_bounded_process,
    _redact_process_output,
    _process_output,
)
from dv_platform.execution.summaries import (
    discover_generated_modules,
    write_aggregate_run_summary,
    _write_summary,
    _generated_traceability,
    _verification_coverage,
    _normalized_coverage_points,
    _triage,
    _repair_suggestions,
    _provenance_sha256,
    _text_tail,
    _strip_namespace,
    _safe_identifier,
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _legacy_class in (
    FormalResults,
    CocotbResults,
    NativeResults,
    SimulationRun,
    FormalRun,
    _ProcessResult,
):
    _legacy_class.__module__ = "dv_platform.run"
del _part_0, _part_1, _part_2, _part_3, _legacy_class, _namespace, _part, _parts
