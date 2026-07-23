# ruff: noqa: E402,F401,I001
"""Composition root for focused coverage subsystems."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from defusedxml.ElementTree import parse

from dv_platform.execution.closure import apply_coverage_feedback_to_stored_plans
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, CoveragePolicy

COVERAGE_SCHEMA_VERSION = 3
MIN_READABLE_COVERAGE_SCHEMA_VERSION = 1
METRICS = ("line", "branch", "toggle", "functional")
CLOSURE_STATES = (
    "covered",
    "uncovered",
    "bounded_pass",
    "unsupported",
    "failed",
    "waived",
    "unreachable",
    "excluded",
)
CLOSED_STATES = {"covered", "waived", "unreachable"}
TRACEABLE_POINT_KINDS = {"assertion", "cover", "covergroup", "coverpoint", "formal", "formal_property", "functional"}

from dv_platform.execution.coverage import importer as _part_0
from dv_platform.execution.coverage import loaders as _part_1
from dv_platform.execution.coverage import closure as _part_2
from dv_platform.execution.coverage import policy as _part_3
from dv_platform.execution.coverage import views as _part_4
from dv_platform.execution.coverage.importer import (
    CoverageImporter,
    import_coverage_reports,
    read_coverage_summary,
    _migrate_coverage_summary,
    _parameter_sweep_coverage,
)
from dv_platform.execution.coverage.loaders import (
    _load_report,
    _load_lcov,
    _load_json,
    _normalize_json_report,
    _load_xml,
    _normalize_metrics,
    _merge_reports,
)
from dv_platform.execution.coverage.closure import (
    _load_json_closure,
    _normalize_coverage_point,
    _normalize_disposition,
    _merge_closure_reports,
)
from dv_platform.execution.coverage.policy import (
    _required_string,
    _string_list,
    _optional_string,
    _string_mapping,
    _protocol_transaction,
    _merge_metric,
    _metric,
    _percentage_metric,
    _evaluate_gates,
    _coverage_gaps,
    _policy_values,
)
from dv_platform.execution.coverage.views import (
    _coverage_markdown,
    _coverage_sarif,
    _yaml_dump,
    _yaml_lines,
    _yaml_scalar,
    _display_percentage,
    _markdown_cell,
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _legacy_class in (CoverageImporter,):
    _legacy_class.__module__ = "dv_platform.analysis.coverage"
del _legacy_class
del _part_0, _part_1, _part_2, _part_3, _part_4, _namespace, _part, _parts
__name__ = "dv_platform.analysis.coverage"
