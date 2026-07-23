# ruff: noqa: E402,F401,I001
"""Composition root for focused enterprise semantics subsystems."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLAssignment,
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
    RTLProtocol,
    RTLReset,
    RTLSemanticFeature,
    RTLType,
    VerificationTarget,
)

SEMANTIC_MANIFEST_SCHEMA_VERSION = 2
MIN_READABLE_SEMANTIC_MANIFEST_SCHEMA_VERSION = 0
MAX_SEMANTIC_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_EXPRESSION_DEPTH = 64
SUPPORTED_LANGUAGES = frozenset({"systemverilog", "verilog", "vhdl"})
SUPPORTED_STANDARDS = {
    "systemverilog": frozenset({"1800-2005", "1800-2009", "1800-2012", "1800-2017", "1800-2023"}),
    "verilog": frozenset({"1364-1995", "1364-2001", "1364-2005"}),
    "vhdl": frozenset({"1076-1987", "1076-1993", "1076-2000", "1076-2002", "1076-2008", "1076-2019"}),
}
DESIGN_UNIT_KINDS = {
    "systemverilog": frozenset({"module", "interface", "program", "package", "checker"}),
    "verilog": frozenset({"module", "primitive", "configuration"}),
    "vhdl": frozenset({"entity", "architecture", "package", "configuration", "context"}),
}
COMPLETENESS_STATES = frozenset({"complete", "partial", "unsupported", "not_applicable"})
SEMANTIC_CATEGORIES = (
    "lexical_preprocessing",
    "libraries_compilation_units",
    "design_units",
    "declarations",
    "types",
    "expressions",
    "statements",
    "subprograms",
    "hierarchy",
    "elaboration",
    "parameters_generics",
    "ports",
    "packages_imports",
    "interfaces_modports",
    "classes_randomization",
    "assignments",
    "processes",
    "assertions",
    "functional_coverage",
    "generates",
    "memories",
    "timing_specify",
    "foreign_interfaces",
    "attributes_pragmas",
    "file_io",
    "clocks_resets",
    "cdc",
    "protocols",
)

T = TypeVar("T")

from dv_platform.enterprise.semantics import contracts as _part_0
from dv_platform.enterprise.semantics import modules as _part_1
from dv_platform.enterprise.semantics import records as _part_2
from dv_platform.enterprise.semantics import validation as _part_3
from dv_platform.enterprise.semantics.contracts import (
    SemanticImportError,
    SemanticDiagnostic,
    SemanticCompleteness,
    SemanticImportResult,
    SemanticManifestImporter,
    _migrate_manifest,
)
from dv_platform.enterprise.semantics.modules import _module
from dv_platform.enterprise.semantics.records import (
    _completeness,
    _port,
    _parameter,
    _type,
    _expression,
    _connection,
    _instance,
    _assignment,
    _block,
    _memory,
    _memory_access,
    _clock,
    _reset,
    _feature,
    _domain,
    _cdc,
    _generate,
    _protocol,
)
from dv_platform.enterprise.semantics.validation import (
    _diagnostic,
    _convert,
    _labeled,
    _record_list,
    _mapping,
    _keys,
    _known_keys,
    _required_string,
    _optional_string,
    _strings,
    _optional_int,
    _int,
    _bool,
    _optional_bool,
    _target,
    _safe_source,
    _validate_module_semantics,
    _unique,
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
    SemanticImportError,
    SemanticDiagnostic,
    SemanticCompleteness,
    SemanticImportResult,
    SemanticManifestImporter,
):
    _legacy_class.__module__ = "dv_platform.enterprise.semantics"
del _part_0, _part_1, _part_2, _part_3, _legacy_class, _namespace, _part, _parts
