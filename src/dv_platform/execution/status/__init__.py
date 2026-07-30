# ruff: noqa: E402,F401,I001
"""Composition root for focused status subsystems."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.analysis.ai_planning import ai_readiness
from dv_platform.execution.coverage import read_coverage_summary
from dv_platform.analysis.plan_store import read_plan_records
from dv_platform.analysis.revisions import read_revisions, revision_state_path
from dv_platform.core.models import CLIConfig, SimulatorConfig, VerificationTarget
from dv_platform.core.paths import is_within
from dv_platform.core.schema import (
    MIN_READABLE_PLAN_SCHEMA_VERSION,
    MIN_READABLE_RTL_FACTS_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    RTL_FACTS_SCHEMA_VERSION,
)
from dv_platform.core.tool_versions import formal_dependency_qualifications, probe_tool_version
from dv_platform.enterprise.store import enterprise_status
from dv_platform.generators.artifacts import validate_generated_directory
from dv_platform.qualification import capability_ledger_status

from dv_platform.execution.status import policy as _part_0
from dv_platform.execution.status import inputs as _part_1
from dv_platform.execution.status import artifacts as _part_2
from dv_platform.execution.status import runs as _part_3
from dv_platform.execution.status import helpers as _part_4
from dv_platform.execution.status.policy import (
    collect_platform_status,
    evaluate_status_policy,
    _coverage_closure_failures,
)
from dv_platform.execution.status.inputs import (
    _rtl_facts_status,
    _plan_status,
    _tool_status,
    _simulator_qualification,
    _generated_status,
)
from dv_platform.execution.status.artifacts import (
    _generated_module_status,
    _missing_expected_generated,
    _unexpected_generated,
    _artifact_integrity,
)
from dv_platform.execution.status.runs import _run_status, _run_summary_status, _revision_closure_status
from dv_platform.execution.status.helpers import _schema_status, _command_available

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
del _part_0, _part_1, _part_2, _part_3, _part_4, _namespace, _part, _parts
__name__ = "dv_platform.analysis.status"
