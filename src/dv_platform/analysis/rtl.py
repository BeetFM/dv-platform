# ruff: noqa: E402,F401,I001
"""Compatibility-complete composition of focused Verilator subsystems."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import parse

from dv_platform.agent.protocols import ProtocolChannel, ProtocolModel, RegisterConflict, RegisterField, RegisterModel
from dv_platform.analysis.discovery import ProjectInventory, build_verilator_dry_run_command
from dv_platform.analysis.protocols import recognize_protocols
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    CLIConfig,
    EvidenceKind,
    EvidenceRef,
    ProductionProtocolBinding,
    ProtocolProfile,
    RTLAssignment,
    RTLBranch,
    RTLCDCPath,
    RTLClock,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLModule,
    RTLParameter,
    RTLParameterBinding,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProperty,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    RTLTypeMember,
    VerificationTarget,
)
from dv_platform.core.schema import MIN_READABLE_RTL_FACTS_SCHEMA_VERSION, RTL_FACTS_SCHEMA_VERSION
from dv_platform.core.security import append_audit_event, redact_text, redact_value

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5

from dv_platform.rtl.verilator import behavior as _part_6
from dv_platform.rtl.verilator import evidence as _part_3
from dv_platform.rtl.verilator import fact_codec as _part_2
from dv_platform.rtl.verilator import hierarchy as _part_5
from dv_platform.rtl.verilator import normalization as _part_0
from dv_platform.rtl.verilator import persistence as _part_1
from dv_platform.rtl.verilator import types as _part_4
from dv_platform.rtl.verilator.behavior import (
    _cast_kind,
    _dtype_by_id,
    _dtype_width,
    _element_summary,
    _expression_type,
    _literal_width,
    _local_name,
    _looks_like_clock,
    _looks_like_reset,
    _module_source,
    _packed_width,
    _property_clock_edge,
    _reset_active_low,
    _source_location,
    _unpacked_depth,
    _unpacked_range,
    _verilator_integer,
)
from dv_platform.rtl.verilator.evidence import (
    _address_width,
    _detect_verilator_version,
    _evidence_ref,
    _evidence_refs,
    _instance_details,
    _instance_names,
    _interface_direction,
    _interface_name,
    _is_parameter,
    _memory_details,
    _modport_member,
    _modport_name,
    _parameter_details,
    _parameter_names,
    _type_details,
    _type_member_from_element,
)
from dv_platform.rtl.verilator.fact_codec import (
    _assignment_from_json,
    _branch_from_json,
    _cdc_path_from_json,
    _cdc_path_to_json,
    _connection_from_json,
    _control_domain_from_json,
    _evidence_from_json,
    _evidence_to_json,
    _expression_from_json,
    _expression_to_json,
    _generate_scope_from_json,
    _generate_scope_to_json,
    _instance_from_json,
    _memory_access_from_json,
    _procedural_block_from_json,
    _procedural_pattern_from_json,
    _property_from_json,
    _property_to_json,
    _protocol_from_json,
    _protocol_model_from_json,
    _protocol_model_to_json,
    _register_conflict_from_json,
    _register_conflict_to_json,
    _register_model_from_json,
    _register_model_to_json,
    _semantic_feature_from_json,
    _type_from_json,
    _type_to_json,
)
from dv_platform.rtl.verilator.hierarchy import (
    _branch_details,
    _cdc_paths,
    _collect_signal_flow,
    _constant_value,
    _first_signal_ref,
    _increment_source,
    _is_one_constant,
    _matching_element_summaries,
    _memories_with_access_policy,
    _memory_accesses_from_assignment,
    _memory_accesses_from_expression,
    _memory_selection,
    _pattern_from_assign,
    _patterns_from_expression,
    _procedural_patterns,
    _property_clock,
    _property_details,
    _protocols,
    _synchronizer_chain,
    _written_signal_refs,
)
from dv_platform.rtl.verilator.normalization import (
    VerilatorRunResult,
    _design_unit_kind,
    _ModuleCandidate,
    _specialization_id,
    normalize_verilator_xml,
    run_verilator_xml,
    write_normalized_rtl_facts,
)
from dv_platform.rtl.verilator.persistence import (
    _BLACK_BOX_SAFE_TARGETS,
    _clock_details,
    _clock_from_json,
    _FEATURE_TARGETS,
    _memory_access_to_json,
    _memory_from_json,
    _module_from_json,
    _parameter_from_json,
    _port_details,
    _port_from_json,
    _port_names,
    _reset_details,
    _reset_from_json,
    _semantic_features,
    _sensitivity_controls,
    _text_tail,
    _UNSUPPORTED_FEATURE_TAGS,
    _validate_rtl_facts_schema,
    classify_verilator_version,
    read_normalized_rtl_facts,
    write_rtl_facts_summary,
    write_verilator_failure_summary,
)
from dv_platform.rtl.verilator.types import (
    _assignment_details,
    _assignment_signal_refs,
    _child_expressions,
    _control_domain_spec,
    _control_domains_and_blocks,
    _element_summaries,
    _expression_from_element,
    _expression_signal_refs,
    _expression_value,
    _generate_iteration_index,
    _generate_scopes,
    _imports,
    _instance_connections,
    _instance_module_name,
    _looks_like_signal_ref,
    _memory_accesses,
    _module_child_elements,
    _original_module_name,
    _procedural_block_details,
    _scoped_instance_elements,
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
    _part_5,
    _part_6,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _class in (
    VerilatorRunResult,
    _ModuleCandidate,
):
    _class.__module__ = "dv_platform.analysis.rtl"
del _part_0, _part_1, _part_2, _part_3, _part_4, _part_5, _part_6, _class, _namespace, _part, _parts
