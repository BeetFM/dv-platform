# ruff: noqa: E402,F401,I001
"""Composition root for purpose-specific deterministic scenarios."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    ScenarioTargetState,
    ScenarioTargetSupport,
    VerificationCheck,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.verification.target_support import scenario_target_support

from dv_platform.verification import scenario_core as _part_0
from dv_platform.verification import scenario_profiles as _part_1
from dv_platform.verification import scenario_peripheral as _part_2
from dv_platform.verification import scenario_formal as _part_3
from dv_platform.verification import scenario_memory as _part_4
from dv_platform.verification import scenario_cdc as _part_5
from dv_platform.verification import scenario_apb as _part_6
from dv_platform.verification import scenario_axi as _part_7
from dv_platform.verification import scenario_ahb as _part_8
from dv_platform.verification import scenario_reset as _part_9
from dv_platform.verification.scenario_core import (
    build_deterministic_scenarios,
    link_scenario_coverage,
    validate_scenario,
    _target_states,
    _qualified_target_states,
    _executable_targets,
    _check_ids,
    _register_check_ids,
    _requirement_ids,
    _scenario_id,
)
from dv_platform.verification.scenario_profiles import _production_protocol_scenarios, _profile_targets
from dv_platform.verification.scenario_peripheral import _peripheral_scenarios
from dv_platform.verification.scenario_formal import _formal_contract_scenarios
from dv_platform.verification.scenario_memory import _memory_scenarios
from dv_platform.verification.scenario_cdc import _cdc_scenarios, _async_fifo_scenarios
from dv_platform.verification.scenario_apb import _apb4_scenarios
from dv_platform.verification.scenario_axi import _axi4_lite_scenarios
from dv_platform.verification.scenario_ahb import _ahb_lite_scenarios
from dv_platform.verification.scenario_reset import _reset_scenarios

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
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
del _part_0, _part_1, _part_2, _part_3, _part_4, _part_5, _part_6, _part_7, _part_8, _part_9, _namespace, _part, _parts
