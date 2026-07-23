"""Compatibility facade for focused protocol generation modules."""

# ruff: noqa: F401

import __future__

import json

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import VerificationPlan, VerificationScenario, VerificationTarget
from dv_platform.generators.protocol_cocotb import (
    cocotb_ahb_lite_scenario_lines,
    cocotb_apb4_scenario_lines,
    cocotb_axi4_lite_scenario_lines,
)
from dv_platform.generators.protocol_common import (
    _OPEN_FORMAL_RESPONSE_BOUND,
    _cocotb_avalon_response,
    _cocotb_model_probe,
    _cocotb_packet_completion,
    _cocotb_profile_handshake,
    _cocotb_profile_scenario,
    _cocotb_register_probe,
    _cocotb_wishbone_response,
    _identifier,
    _profile_drive_value,
    _profile_handshake_specs,
    _profile_payload_fields,
    _python_identifier,
    cocotb_profile_scenario_lines,
    cocotb_protocol_lines,
    haddr,
    input_signal,
    signal,
)
from dv_platform.generators.protocol_formal import (
    _formal_axi4_semantics,
    _formal_packet_state_lines,
    _formal_profile_model_assertions,
    _formal_profile_semantic_assertions,
    _formal_wishbone_semantics,
    _sv_model_assertions,
    formal_profile_assertions,
    formal_profile_declarations,
    sv_protocol_assertions,
)
from dv_platform.generators.protocol_formal_standard import (
    _ahb_lite_scenario_payload,
    _apb4_reset_value,
    _apb4_scenario_payload,
    _axi4_lite_scenario_payload,
    _protocol_identifier,
    formal_ahb_lite_assertions,
    formal_ahb_lite_declarations,
    formal_apb4_assertions,
    formal_apb4_declarations,
    formal_axi4_lite_assertions,
    formal_axi4_lite_declarations,
)
from dv_platform.generators.protocol_native import (
    _native_ahb_semantic_checks,
    _native_apb_tasks,
    _native_avalon_mm_semantic_checks,
    _native_avalon_st_semantic_checks,
    _native_axi_semantic_checks,
    _native_axi_tasks,
    _native_profile_semantic_checks,
    _native_profile_task,
    _native_profile_tasks,
    _native_stream_semantic_checks,
    _native_tilelink_semantic_checks,
    _native_wishbone_semantic_checks,
    _register_value_after_write,
    native_protocol_accesses,
    native_protocol_task_declarations,
    sv_register_accesses,
)
from dv_platform.generators.protocol_vhdl import (
    _vhdl_profile_accesses,
    _vhdl_profile_literal,
    _vhdl_profile_semantics,
    vhdl_protocol_accesses,
)
from dv_platform.generators.scenario_registry import scenario_is_executable

annotations = __future__.annotations
