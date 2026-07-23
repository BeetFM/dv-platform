# ruff: noqa: E402,F401,I001
"""Compatibility-complete composition of focused Slang subsystems."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLAssignment,
    RTLBranch,
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
    RTLProperty,
    RTLType,
    RTLTypeMember,
)

SEMANTIC_CROSSCHECK_API_VERSION = 2
SEMANTIC_CROSSCHECK_SCHEMA_VERSION = 2
SLANG_MIN_TESTED_MAJOR = 11
SLANG_MAX_TESTED_MAJOR = 11

CAPABILITY_DESIGN_UNITS = "design_units"
CAPABILITY_SPECIALIZATIONS = "specializations"
CAPABILITY_PORTS = "ports"
CAPABILITY_PARAMETERS = "parameters"
CAPABILITY_TYPES = "types"
CAPABILITY_HIERARCHY = "hierarchy"
CAPABILITY_ASSIGNMENTS = "assignments"
CAPABILITY_PROCEDURAL_BLOCKS = "procedural_blocks"
CAPABILITY_EXPRESSIONS = "expressions"
CAPABILITY_BRANCHES = "branches"
CAPABILITY_CONTROL_DOMAINS = "control_domains"
CAPABILITY_PROPERTIES = "properties"
CAPABILITY_INTERFACES = "interfaces"
CAPABILITY_IMPORTS = "imports"
CAPABILITY_GENERATE_SCOPES = "generate_scopes"
CAPABILITY_MEMORIES = "memories"

CORE_REQUIRED_CAPABILITIES = (
    CAPABILITY_DESIGN_UNITS,
    CAPABILITY_SPECIALIZATIONS,
    CAPABILITY_PORTS,
    CAPABILITY_PARAMETERS,
)
BASE_STRUCTURAL_CAPABILITIES = (
    *CORE_REQUIRED_CAPABILITIES,
    CAPABILITY_HIERARCHY,
    CAPABILITY_ASSIGNMENTS,
    CAPABILITY_PROCEDURAL_BLOCKS,
)
COMPARABLE_CAPABILITIES = (
    *CORE_REQUIRED_CAPABILITIES,
    CAPABILITY_TYPES,
    CAPABILITY_HIERARCHY,
    CAPABILITY_ASSIGNMENTS,
    CAPABILITY_PROCEDURAL_BLOCKS,
    CAPABILITY_EXPRESSIONS,
    CAPABILITY_BRANCHES,
    CAPABILITY_CONTROL_DOMAINS,
    CAPABILITY_PROPERTIES,
    CAPABILITY_INTERFACES,
    CAPABILITY_IMPORTS,
    CAPABILITY_GENERATE_SCOPES,
    CAPABILITY_MEMORIES,
)

_PROPERTY_KINDS = {
    "assertionstatement",
    "concurrentassertionstatement",
    "immediateassertionstatement",
    "assumeproperty",
    "assertproperty",
    "coverproperty",
    "coversequencestatement",
    "concurrentassertion",
    "immediateassertion",
}

_OPERATION_NAMES = {
    "binaryexpression": "binary",
    "unaryexpression": "unary",
    "conversion": "cast",
    "conversionexpression": "cast",
    "conditionalop": "cond",
    "conditionalexpression": "cond",
    "concatenation": "concat",
    "namedvalue": "ref",
    "hierarchicalvalue": "ref",
    "varref": "ref",
    "varxref": "ref",
    "integerliteral": "literal",
    "const": "literal",
    "constint": "literal",
    "constant": "literal",
    "elementselect": "select",
    "arraysel": "select",
    "bitsel": "select",
    "rangeselect": "range",
    "sel": "range",
    "subtract": "sub",
    "logicalnot": "not",
    "lognot": "not",
    "realliteral": "literal",
    "stringliteral": "literal",
    "procedural": "always",
    "alwaysff": "alwaysff",
    "alwayscomb": "alwayscomb",
    "alwayslatch": "alwayslatch",
    "continuous": "contassign",
}

_SLANG_EXPRESSION_KINDS = {
    "Assignment",
    "BinaryOp",
    "UnaryOp",
    "Conversion",
    "ConditionalOp",
    "Concatenation",
    "Replication",
    "Streaming",
    "NamedValue",
    "HierarchicalValue",
    "MemberAccess",
    "IntegerLiteral",
    "UnbasedUnsizedIntegerLiteral",
    "RealLiteral",
    "TimeLiteral",
    "StringLiteral",
    "NullLiteral",
    "RangeSelect",
    "ElementSelect",
    "Call",
    "MinTypMax",
    "Inside",
    "TaggedUnion",
    "Simple",
    "Binary",
    "SequenceConcat",
}

_SLANG_UNSUPPORTED_EXPRESSION_KINDS = {
    "NewClass",
    "NewArray",
    "CopyClass",
    "Dist",
    "ClockingEvent",
}

from dv_platform.rtl import slang_contracts as _part_0
from dv_platform.rtl import slang_runner as _part_1
from dv_platform.rtl import slang_normalization as _part_2
from dv_platform.rtl import slang_semantics as _part_3
from dv_platform.rtl import slang_comparison as _part_4
from dv_platform.rtl import slang_canonicalization as _part_5
from dv_platform.rtl.slang_contracts import (
    FrontendMetadata,
    CapabilityCoverage,
    SemanticCrossCheckIssue,
    SemanticCrossCheckResult,
    SlangRunResult,
    SlangNormalizationBenchmark,
    SemanticCrossChecker,
    NormalizedFactCrossChecker,
    SlangRunError,
    SlangAnalyzer,
)
from dv_platform.rtl.slang_runner import (
    unavailable_crosscheck_result,
    aggregate_crosscheck_results,
    classify_slang_version,
    benchmark_slang_normalization,
    capabilities_for_modules,
    required_capabilities_for_modules,
    write_crosscheck_result,
    _write_diagnostics,
    _frontend_json,
    _issue_json,
    _evidence_json,
    _normalize_slang_document,
    _modules_from_slang_json,
    _walk_json_objects,
    _json_dicts,
    _slang_original_name,
    _specialization_from_parameters,
    _slang_symbol_index,
    _slang_instance_array_ranges,
    _slang_link,
    _is_slang_port,
    _is_slang_instance,
)
from dv_platform.rtl.slang_normalization import (
    _slang_instance,
    _slang_instances_with_paths,
    _slang_connection_port,
    _slang_connection_direction,
    _slang_connection_expression,
    _slang_summary,
    _slang_source_location,
    _slang_procedure_kind,
    _slang_procedure,
    _slang_assignment,
    _slang_procedural_assignments,
    _slang_signal_refs,
    _slang_written_refs,
    _slang_port,
    _slang_parameter,
    _is_slang_type,
    _slang_type,
    _slang_global_types,
    _resolve_slang_type,
    _resolved_slang_type_width,
    _slang_imports,
    _is_slang_memory,
)
from dv_platform.rtl.slang_semantics import (
    _slang_memory,
    _slang_memory_element_type,
    _slang_memory_accesses,
    _selected_memory,
    _slang_select_address,
    _slang_expression,
    _slang_branches,
    _slang_properties,
    _slang_property,
    _looks_like_property_expression,
    _slang_generate_scope,
    _slang_generate_index,
    _slang_generate_scopes,
    _merge_slang_generate_scopes,
)
from dv_platform.rtl.slang_comparison import (
    _slang_source_generate_scopes,
    _slang_source_expression,
    _slang_control_domain,
    _slang_signal_refs_from_expression,
    _expression_is_active_low,
    _modules_by_specialization,
    _specialization_signature,
    _display_specialization,
    _compare_module,
    _compare_value,
    _module_field_location,
    _port_signature,
    _parameter_signature,
    _instance_signature,
    _assignment_signature,
    _procedural_signature,
    _canonical_assignment_kind,
    _canonical_procedure_kind,
    _type_signature,
    _expression_signature,
    _expression_node_signature,
    _branch_signature,
)
from dv_platform.rtl.slang_canonicalization import (
    _domain_signature,
    _property_signature,
    _generate_signature,
    _memory_signature,
    _canonical_operation,
    _canonical_type_kind,
    _canonical_symbol_name,
    _canonical_constant,
    _canonical_parameter_constant,
    _expression_constant,
    _canonical_range,
    _canonical_specialization_id,
    _type_range,
    _type_width,
    _type_signed,
    _type_dimensions,
    _range_width,
    _product,
    _is_expression_node,
    _add_gap,
    _collect_slang_capability_gaps,
    _walk_expressions,
    _dedupe_expressions,
    _first_signal,
    _event_edge,
)

_parts = (
    _part_0,
    _part_1,
    _part_2,
    _part_3,
    _part_4,
    _part_5,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _class in (
    FrontendMetadata,
    CapabilityCoverage,
    SemanticCrossCheckIssue,
    SemanticCrossCheckResult,
    SlangRunResult,
    SlangNormalizationBenchmark,
    SemanticCrossChecker,
    NormalizedFactCrossChecker,
    SlangRunError,
    SlangAnalyzer,
):
    _class.__module__ = "dv_platform.analysis.semantic_crosscheck"
del _part_0, _part_1, _part_2, _part_3, _part_4, _part_5, _class, _namespace, _part, _parts
