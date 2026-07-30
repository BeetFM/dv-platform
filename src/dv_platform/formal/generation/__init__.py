# ruff: noqa: E402,F401,I001
"""Composition root for focused formal collateral generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import parse

from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    ArtifactTrace,
    GeneratedArtifact,
    RTLCDCPath,
    RTLPort,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generation.rendering import render_target
from dv_platform.generators.peripherals import (
    formal_peripheral_assertions,
    formal_peripheral_output_signals,
    peripheral_mapped_outputs,
)
from dv_platform.generators.protocols import (
    formal_ahb_lite_assertions,
    formal_ahb_lite_declarations,
    formal_apb4_assertions,
    formal_apb4_declarations,
    formal_axi4_lite_assertions,
    formal_axi4_lite_declarations,
    formal_profile_assertions,
    formal_profile_declarations,
)
from dv_platform.generators.scenario_registry import scenario_is_executable
from dv_platform.generators.signals import (
    artifact_trace,
    artifact_trace_for_scenario,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    safe_parameter_value,
    sv_parameter_clause,
)

from dv_platform.formal.generation import harness as _part_0
from dv_platform.formal.generation import sby as _part_1
from dv_platform.formal.generation import memory as _part_2
from dv_platform.formal.generation import contracts as _part_3
from dv_platform.formal.generation import cdc as _part_4
from dv_platform.formal.generation.harness import (
    CDCProofPolicy,
    _CDCPathEvidence,
    FormalGenerator,
    _formal_traceability,
    _cdc_report_traceability,
    _sby_mapping_header,
    _harness_content,
    _harness_presentation,
)
from dv_platform.formal.generation.sby import (
    _sby_content,
    _sby_presentation,
    _proof_depth,
    _quality_requirements,
    _port_names_from_plan,
    _structured_ports,
    _input_ports,
    _scalar_input_ports,
    _output_ports,
    _clock_name,
    _reset_name,
    _reset_active_low,
    _reset_zero_outputs,
    _increment_checks,
    _hold_checks,
    _output_wire_declarations,
    _input_reg_declarations,
    _memory_write_assertions,
)
from dv_platform.formal.generation.memory import (
    _ready_valid_assertions,
    _memory_collision_assertions,
    _bounded_sram_assertions,
    _qualified_formal_contract_policies,
    _formal_contract_output_signals,
    _formal_contract_declarations,
    _formal_contract_assertions,
    _formal_assumption_assertions,
    _async_fifo_policies,
    _qualified_reset_policies,
    _reset_domain_output_signals,
    _reset_domain_assertions,
)
from dv_platform.formal.generation.contracts import (
    _qualified_bounded_sram_policies,
    _bounded_sram_output_signals,
    _bounded_sram_declarations,
    _async_fifo_output_signals,
    _async_fifo_assertions,
    _cdc_assertions,
)
from dv_platform.formal.generation.cdc import (
    _cdc_scheme_assertions,
    _reconvergent_cdc_assertions,
    _cdc_evidence,
    _cdc_report_content,
    _cdc_report_payload,
    _formal_signal_ref,
    _output_wire_declaration,
    _verilator_port_dtype,
    _verilator_port_dtype_id,
    _verilator_dtype,
    _local_name,
    _safe_sv_bound,
    _safe_packed_range,
    _is_zero_value,
    _looks_like_scalar_input,
    _looks_like_output,
    _comma_terminate,
    _safe_identifier,
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
for _legacy_class in (
    CDCProofPolicy,
    _CDCPathEvidence,
    FormalGenerator,
):
    _legacy_class.__module__ = "dv_platform.generators.formal"
del _legacy_class
del _part_0, _part_1, _part_2, _part_3, _part_4, _namespace, _part, _parts
__name__ = "dv_platform.generators.formal"
