# ruff: noqa: E402,F401,I001
"""Compatibility-complete composition of focused VHDL subsystems."""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    ProductionProtocolBinding,
    RTLAssignment,
    RTLClock,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLModule,
    RTLParameter,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    RTLTypeMember,
    VerificationTarget,
)

VHDL_NORMALIZER_VERSION = "vhdl-source-normalizer/2"

from dv_platform.rtl import vhdl_elaboration as _elaboration
from dv_platform.rtl import vhdl_normalization as _part_0
from dv_platform.rtl import vhdl_protocols as _part_1
from dv_platform.rtl import vhdl_parsing as _part_2
from dv_platform.rtl.vhdl_elaboration import validate_vhdl_elaboration
from dv_platform.rtl.vhdl_normalization import (
    VHDLNormalizationError,
    _Entity,
    _Architecture,
    _VHDLTypeDefinition,
    normalize_vhdl_sources,
    _production_protocol_models,
    _ready_valid_protocols,
    _entities,
)
from dv_platform.rtl.vhdl_protocols import (
    _architectures,
    _generic_details,
    _port_details,
    _vhdl_type,
    _package_type_definitions,
    _resolve_named_type,
    _vhdl_range_length,
    _rtl_type,
)
from dv_platform.rtl.vhdl_parsing import (
    _generate_scopes,
    _vhdl_boolean_expression,
    _clock_details,
    _reset_details,
    _procedural_details,
    _concurrent_assignments,
    _interface_block,
    _declarations,
    _integer_expression,
    _parameter_override_map,
    _specialization_id,
    _evidence,
    _strip_comments,
    _line,
    _source_line,
    _looks_like_clock,
    _looks_like_reset,
)

_parts = (
    _elaboration,
    _part_0,
    _part_1,
    _part_2,
)
_namespace = {name: value for name, value in globals().items() if not name.startswith("__")}
for _part in _parts:
    _part.__dict__.update(_namespace)
for _class in (
    VHDLNormalizationError,
    _Entity,
    _Architecture,
    _VHDLTypeDefinition,
):
    _class.__module__ = "dv_platform.analysis.vhdl"
del _elaboration, _part_0, _part_1, _part_2, _class, _namespace, _part, _parts
