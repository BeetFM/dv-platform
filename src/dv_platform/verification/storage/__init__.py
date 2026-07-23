# ruff: noqa: E402,F401,I001
"""Composition root for focused verification plan persistence and codecs."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from dv_platform.agent.protocols import ProtocolChannel, ProtocolModel, RegisterConflict, RegisterField, RegisterModel
from dv_platform.verification.planning.claims import GenerationGate, gate_generation, write_claim_reports
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    AgentPlanningNote,
    AgentPlanProvenance,
    ClaimStatus,
    ClaimType,
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    RTLCDCPath,
    RTLClock,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProperty,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    RTLTypeMember,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    Severity,
    VerificationBehavior,
    VerificationCheck,
    VerificationClaim,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationRequirement,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.core.paths import contained_path, validate_path_component
from dv_platform.core.schema import MIN_READABLE_PLAN_SCHEMA_VERSION, PLAN_SCHEMA_VERSION

from dv_platform.verification.storage import plan_persistence as _part_0
from dv_platform.verification.storage import plan_markdown as _part_1
from dv_platform.verification.storage import plan_codec as _part_2
from dv_platform.verification.storage import rtl_fact_codec as _part_3
from dv_platform.verification.storage import verification_intent_codec as _part_4
from dv_platform.verification.storage.plan_persistence import (
    write_plan_outputs,
    read_plan_records,
    read_stored_plans,
    _write_sqlite,
)
from dv_platform.verification.storage.plan_markdown import (
    _write_module_markdown,
    _write_index_markdown,
    _remove_stale_plan_views,
    _bullet_lines,
    _escape_markdown_cell,
)
from dv_platform.verification.storage.plan_codec import (
    _plan_to_json,
    _gate_to_json,
    _plan_from_json,
    _migrate_plan_json,
    _agent_provenance_to_json,
    _agent_note_to_json,
    _agent_note_from_json,
    _agent_provenance_from_json,
    plan_to_json,
    plan_from_json,
)
from dv_platform.verification.storage.rtl_fact_codec import (
    _port_from_json,
    _clock_from_json,
    _reset_from_json,
    _semantic_feature_from_json,
    _parameter_to_json,
    _parameter_from_json,
    _memory_to_json,
    _memory_from_json,
    _memory_access_to_json,
    _memory_access_from_json,
    _type_to_json,
    _type_from_json,
    _expression_to_json,
    _expression_from_json,
    _connection_to_json,
    _connection_from_json,
    _instance_to_json,
    _instance_from_json,
    _control_domain_to_json,
    _control_domain_from_json,
    _cdc_path_to_json,
    _cdc_path_from_json,
    _generate_scope_to_json,
    _generate_scope_from_json,
    _property_to_json,
    _property_from_json,
    _protocol_to_json,
    _protocol_from_json,
)
from dv_platform.verification.storage.verification_intent_codec import (
    _protocol_model_to_json,
    _protocol_model_from_json,
    _register_model_to_json,
    _register_model_from_json,
    _register_conflict_to_json,
    _register_conflict_from_json,
    _check_to_json,
    _check_from_json,
    _scenario_to_json,
    _scenario_from_json,
    _requirement_from_json,
    _conflict_from_json,
    _behavior_from_json,
    _claim_from_json,
    _evidence_from_json,
    _evidence_to_json,
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
del _part_0, _part_1, _part_2, _part_3, _part_4, _namespace, _part, _parts
